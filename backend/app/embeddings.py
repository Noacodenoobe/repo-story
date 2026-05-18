"""
Indeksowanie kodu i wyszukiwanie semantyczne (RAG).

Mała, samowystarczalna implementacja:
- chunking plików kodu (z nakładką),
- embeddingi z Ollamy (nomic-embed-text),
- przechowywanie w pickle (jeden plik na repo) - bez zewnętrznych baz wektorowych,
- wyszukiwanie po kosinusowym podobieństwie (numpy).

Świadoma decyzja: nie używamy ChromaDB. Powód - zgodnie z regulaminem ma być
minimum zależności i łatwo odwracalna instalacja. Tutaj wystarczy
``numpy + pickle`` i mamy pełną kontrolę.
"""
from __future__ import annotations

import logging
import math
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from . import config
from .llm_client import OllamaClient, get_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
_PARAGRAPH_RE = re.compile(r"\n\s*\n")


def _split_paragraphs(text: str) -> List[str]:
    """Dzieli tekst po pustych linijkach - naturalne granice w kodzie."""
    return [p for p in _PARAGRAPH_RE.split(text) if p.strip()]


def chunk_text(text: str, chunk_size: int = config.CHUNK_SIZE,
               overlap: int = config.CHUNK_OVERLAP) -> List[str]:
    """
    Dzieli tekst na fragmenty z nakładką.

    Strategia: najpierw próbujemy łączyć całe akapity. Jeśli akapit jest sam
    w sobie zbyt długi, tniemy go po znakach z nakładką.
    """
    if not text:
        return []

    paragraphs = _split_paragraphs(text) or [text]
    chunks: List[str] = []
    buffer = ""

    for para in paragraphs:
        if len(para) > chunk_size:
            # Drobny akapit-monster - tnij go znakowo
            if buffer:
                chunks.append(buffer)
                buffer = ""
            step = max(1, chunk_size - overlap)
            for i in range(0, len(para), step):
                chunks.append(para[i:i + chunk_size])
            continue

        if len(buffer) + len(para) + 2 <= chunk_size:
            buffer = f"{buffer}\n\n{para}" if buffer else para
        else:
            if buffer:
                chunks.append(buffer)
            buffer = para

    if buffer:
        chunks.append(buffer)
    return chunks


# ---------------------------------------------------------------------------
# Magazyn embeddingów
# ---------------------------------------------------------------------------
@dataclass
class CodeChunk:
    """Pojedynczy fragment kodu z metadanymi."""
    text: str
    file_path: str          # ścieżka względna w repo
    chunk_index: int
    embedding: Optional[np.ndarray] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "chunk_index": self.chunk_index,
            "preview": self.text[:200],
        }


class VectorIndex:
    """Prosty in-memory store wektorów z zapisem do pliku pickle."""

    def __init__(self, name: str, storage_dir: Path = config.INDEXES_DIR) -> None:
        self.name = name
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.storage_dir / f"{name}.pkl"
        self.chunks: List[CodeChunk] = []
        self._matrix: Optional[np.ndarray] = None

    # ----------------------------------------------------------- I/O
    def save(self) -> None:
        with open(self.path, "wb") as f:
            pickle.dump({"chunks": self.chunks}, f)
        logger.info("Zapisano indeks: %s (%d fragmentów)", self.path, len(self.chunks))

    def load(self) -> bool:
        if not self.path.exists():
            return False
        with open(self.path, "rb") as f:
            data = pickle.load(f)
        self.chunks = data.get("chunks", [])
        self._matrix = None  # przy następnym search zostanie zbudowane
        logger.info("Załadowano indeks: %s (%d fragmentów)", self.path, len(self.chunks))
        return True

    # ----------------------------------------------------------- mutators
    def add(self, chunk: CodeChunk) -> None:
        self.chunks.append(chunk)
        self._matrix = None

    def _ensure_matrix(self) -> None:
        if self._matrix is not None:
            return
        if not self.chunks:
            self._matrix = np.zeros((0, 0))
            return
        rows = []
        for c in self.chunks:
            if c.embedding is None:
                continue
            rows.append(np.asarray(c.embedding, dtype=np.float32))
        self._matrix = np.vstack(rows) if rows else np.zeros((0, 0))

    # ----------------------------------------------------------- search
    def search(self, query_emb: List[float], top_k: int = config.TOP_K_RETRIEVAL) -> List[Tuple[CodeChunk, float]]:
        """Zwraca k najlepszych fragmentów posortowanych malejąco po podobieństwie."""
        self._ensure_matrix()
        if self._matrix is None or self._matrix.size == 0 or not self.chunks:
            return []

        q = np.asarray(query_emb, dtype=np.float32)
        q_norm = q / (np.linalg.norm(q) + 1e-8)
        mat = self._matrix
        mat_norm = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8)
        sims = mat_norm @ q_norm

        top_idx = np.argsort(-sims)[:top_k]
        return [(self.chunks[i], float(sims[i])) for i in top_idx]


# ---------------------------------------------------------------------------
# Wysokopoziomowy indekser
# ---------------------------------------------------------------------------
class CodeEmbedder:
    """Buduje indeks RAG dla danego repozytorium."""

    def __init__(self, client: Optional[OllamaClient] = None) -> None:
        self.client = client or get_client()

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            logger.debug("Nie udało się odczytać %s: %s", path, e)
            return ""

    def build_index(self, repo_path: Path, *, index_name: Optional[str] = None,
                    max_files: int = config.MAX_FILES_TO_ANALYZE) -> VectorIndex:
        """
        Tworzy indeks dla wszystkich plików kodu w repozytorium.

        Parameters
        ----------
        repo_path : Path
            Katalog ze sklonowanym repo.
        index_name : str, optional
            Nazwa indeksu (domyślnie nazwa katalogu).
        max_files : int
            Maksymalna liczba plików, żeby ograniczyć czas i miejsce.
        """
        repo_path = Path(repo_path)
        index = VectorIndex(name=index_name or repo_path.name)

        files_processed = 0
        chunks_processed = 0

        for p in sorted(repo_path.rglob("*")):
            if files_processed >= max_files:
                logger.warning("Osiągnięto limit %d plików.", max_files)
                break
            if any(part in config.IGNORE_DIRS for part in p.parts):
                continue
            if p.is_dir() or not p.is_file():
                continue
            if p.suffix.lower() not in config.CODE_EXTENSIONS:
                continue
            try:
                if p.stat().st_size > config.MAX_FILE_SIZE_KB * 1024:
                    continue
            except OSError:
                continue

            text = self._read_text(p)
            if not text.strip():
                continue

            rel_path = str(p.relative_to(repo_path))
            chunks = chunk_text(text)
            for i, ch in enumerate(chunks):
                emb = self.client.embed(ch)
                index.add(CodeChunk(
                    text=ch,
                    file_path=rel_path,
                    chunk_index=i,
                    embedding=np.asarray(emb, dtype=np.float32),
                ))
                chunks_processed += 1
            files_processed += 1

        logger.info("Zindeksowano %d plików, %d fragmentów.", files_processed, chunks_processed)
        index.save()
        return index

    def search(self, index: VectorIndex, query: str,
               top_k: int = config.TOP_K_RETRIEVAL) -> List[Tuple[CodeChunk, float]]:
        """Wyszukiwanie semantyczne."""
        q_emb = self.client.embed(query)
        return index.search(q_emb, top_k=top_k)


# ---------------------------------------------------------------------------
# Funkcje pomocnicze - przydatne w testach i CLI
# ---------------------------------------------------------------------------
def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Klasyczne podobieństwo kosinusowe (do testów i debug)."""
    a_arr = np.asarray(a, dtype=np.float32)
    b_arr = np.asarray(b, dtype=np.float32)
    denom = (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)) + 1e-8
    return float(a_arr @ b_arr / denom)


__all__ = [
    "chunk_text",
    "CodeChunk",
    "VectorIndex",
    "CodeEmbedder",
    "cosine_similarity",
]

"""
Klient HTTP do Ollama.

Cienka warstwa nad REST API Ollamy - jeden moduł komunikacyjny dla wszystkich
modeli (koderskiego, polskiego, embeddingów). Używa biblioteki ``requests``
zamiast oficjalnego SDK, żeby zachować minimalne zależności.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Iterator, List, Optional

import requests

from . import config

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Generyczny błąd komunikacji z Ollamą."""


@dataclass
class GenerationResult:
    """Wynik wygenerowania tekstu przez LLM."""

    model: str
    prompt: str
    response: str
    total_duration_ms: Optional[int] = None
    eval_count: Optional[int] = None
    prompt_eval_count: Optional[int] = None


class OllamaClient:
    """
    Cienki klient REST do Ollamy.

    Wszystkie metody są synchroniczne - FastAPI obsługuje je w threadpoolu.
    """

    def __init__(self, host: str = config.OLLAMA_HOST, timeout: int = config.OLLAMA_TIMEOUT) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    # ---------------------------------------------------------------- helpers
    def _url(self, path: str) -> str:
        return f"{self.host}{path}"

    def ping(self) -> bool:
        """Czy Ollama odpowiada na ``/api/tags``?"""
        try:
            r = self._session.get(self._url("/api/tags"), timeout=5)
            return r.status_code == 200
        except requests.RequestException as e:
            logger.warning("Ollama ping failed: %s", e)
            return False

    def list_models(self) -> List[dict]:
        """Lista zainstalowanych modeli Ollamy."""
        try:
            r = self._session.get(self._url("/api/tags"), timeout=self.timeout)
            r.raise_for_status()
            return r.json().get("models", [])
        except requests.RequestException as e:
            raise OllamaError(f"Nie udało się pobrać listy modeli: {e}") from e

    def has_model(self, name: str) -> bool:
        """Sprawdza, czy dany model jest zainstalowany lokalnie."""
        try:
            models = self.list_models()
        except OllamaError:
            return False
        # nazwy mogą występować jako "name" lub "model"
        wanted = name.lower()
        for m in models:
            for key in ("name", "model"):
                if key in m and m[key].lower() == wanted:
                    return True
        return False

    # ---------------------------------------------------------- generation
    def generate(
        self,
        prompt: str,
        model: str,
        system: Optional[str] = None,
        temperature: float = config.LLM_TEMPERATURE,
        num_ctx: int = config.LLM_NUM_CTX,
        max_tokens: int = config.LLM_MAX_TOKENS,
    ) -> GenerationResult:
        """
        Synchroniczne generowanie tekstu (``/api/generate`` z ``stream=False``).
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        try:
            r = self._session.post(self._url("/api/generate"), json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            raise OllamaError(f"Generowanie nieudane (model={model}): {e}") from e
        except json.JSONDecodeError as e:
            raise OllamaError(f"Nieprawidłowa odpowiedź JSON z Ollamy: {e}") from e

        return GenerationResult(
            model=model,
            prompt=prompt,
            response=data.get("response", "").strip(),
            total_duration_ms=int(data["total_duration"] / 1_000_000) if "total_duration" in data else None,
            eval_count=data.get("eval_count"),
            prompt_eval_count=data.get("prompt_eval_count"),
        )

    def stream_generate(
        self,
        prompt: str,
        model: str,
        system: Optional[str] = None,
        temperature: float = config.LLM_TEMPERATURE,
        num_ctx: int = config.LLM_NUM_CTX,
        max_tokens: int = config.LLM_MAX_TOKENS,
    ) -> Iterator[str]:
        """
        Streamuje wygenerowany tekst fragment po fragmencie.

        Yielduje kolejne kawałki ``response`` - przydatne do UI, gdzie chcemy
        pokazywać postęp w trakcie generowania.
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        try:
            with self._session.post(
                self._url("/api/generate"),
                json=payload,
                stream=True,
                timeout=self.timeout,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    chunk = obj.get("response", "")
                    if chunk:
                        yield chunk
                    if obj.get("done"):
                        break
        except requests.RequestException as e:
            raise OllamaError(f"Streaming nieudany (model={model}): {e}") from e

    # ----------------------------------------------------------- embeddings
    def embed(self, text: str, model: str = config.MODEL_EMBED) -> List[float]:
        """Generuje embedding dla pojedynczego tekstu."""
        payload = {"model": model, "prompt": text}
        try:
            r = self._session.post(
                self._url("/api/embeddings"),
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            raise OllamaError(f"Embedding nieudany (model={model}): {e}") from e

        emb = data.get("embedding")
        if not emb:
            raise OllamaError("Ollama zwróciła pustą odpowiedź embeddings.")
        return emb

    def embed_batch(self, texts: List[str], model: str = config.MODEL_EMBED) -> List[List[float]]:
        """
        Generuje embeddingi dla listy tekstów.

        Ollama nie ma natywnego batch-API dla wszystkich modeli, więc lecimy
        sekwencyjnie. Dla nomic-embed-text jest to wystarczająco szybkie.
        """
        result: List[List[float]] = []
        for t in texts:
            result.append(self.embed(t, model=model))
        return result


# Globalna instancja - możemy ją importować w pozostałych modułach
_default_client: Optional[OllamaClient] = None


def get_client() -> OllamaClient:
    """Zwraca współdzieloną instancję klienta."""
    global _default_client
    if _default_client is None:
        _default_client = OllamaClient()
    return _default_client

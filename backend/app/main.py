"""
Główny serwer FastAPI dla Repo Opowieść.

Prezentacja edukacyjna „zero tech” + opcjonalna analiza techniczna.
"""
from __future__ import annotations

import logging
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .code_analyzer import LlmAnalyzer, StaticAnalyzer
from .diagram_generator import build_all_diagrams
from .embeddings import CodeEmbedder
from .knowledge_base import KnowledgeBase
from .llm_client import OllamaError, get_client
from .repo_fetcher import RepoFetcher, is_valid_git_url
from .report_generator import PolishReportGenerator
from .story_generator import StoryGenerator


config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = config.LOGS_DIR / "server.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("repo_story")


class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="URL repozytorium Git")
    force_reclone: bool = Field(False, description="Czy pobrać repo od nowa")
    skip_story: bool = Field(False, description="Pomiń prezentację (tylko statystyki)")
    include_technical: bool = Field(
        False,
        description="Dodaj pełną analizę techniczną (wolniejsze)",
    )


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    models_available: List[str]
    missing_models: List[str]


class GenericMessage(BaseModel):
    detail: str


app = FastAPI(
    title="Repo Opowieść",
    description="Wklej link do GitHub — dostaniesz prezentację, nie raport inżynierski.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fetcher = RepoFetcher()
static_analyzer = StaticAnalyzer()
embedder = CodeEmbedder()
llm_analyzer = LlmAnalyzer(embedder=embedder)
report_generator = PolishReportGenerator()
story_generator = StoryGenerator()
kb = KnowledgeBase()


@app.get("/api/health", response_model=HealthResponse)
def health() -> Dict[str, Any]:
    """Status serwera i wymaganych modeli."""
    client = get_client()
    ollama_ok = client.ping()
    available: List[str] = []
    missing: List[str] = []

    if ollama_ok:
        try:
            for m in client.list_models():
                name = m.get("name") or m.get("model") or ""
                if name:
                    available.append(name)
        except OllamaError:
            ollama_ok = False

    required = [config.MODEL_POLISH]
    for m in required:
        if not any(a.lower() == m.lower() for a in available):
            missing.append(m)

    return {
        "status": "ok" if ollama_ok else "ollama_offline",
        "ollama": ollama_ok,
        "models_available": available,
        "missing_models": missing,
    }


@app.get("/api/config")
def get_config() -> Dict[str, Any]:
    return config.summary()


@app.get("/api/models")
def get_models() -> Dict[str, Any]:
    client = get_client()
    try:
        return {"models": client.list_models()}
    except OllamaError as e:
        raise HTTPException(status_code=503, detail=f"Ollama niedostępna: {e}") from e


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> Dict[str, Any]:
    """Analiza repozytorium z prezentacją edukacyjną."""
    started = time.time()

    if not is_valid_git_url(req.url):
        raise HTTPException(status_code=400, detail="Nieprawidłowy URL repozytorium Git.")

    client = get_client()
    if not req.skip_story and not client.ping():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Ollama nie odpowiada pod adresem {config.OLLAMA_HOST}. "
                "Uruchom `ollama serve` i spróbuj ponownie."
            ),
        )

    try:
        logger.info("ANALIZA START: %s", req.url)
        repo = fetcher.clone(req.url, force=req.force_reclone)
        static = static_analyzer.analyze(repo.path)
        diagrams = build_all_diagrams(repo, static.languages, static.frameworks, static.dependencies)

        lesson_deck: Dict[str, Any] = {}
        llm_result = None
        polish_report = ""

        if not req.skip_story:
            if not client.has_model(config.MODEL_POLISH):
                raise HTTPException(
                    status_code=503,
                    detail=f"Brak modelu polskiego: {config.MODEL_POLISH}. "
                    f"Pobierz: ollama pull {config.MODEL_POLISH}",
                )
            logger.info("Generuję prezentację edukacyjną...")
            deck = story_generator.generate(repo, static)
            lesson_deck = deck.to_dict()

        if req.include_technical:
            if not client.has_model(config.MODEL_EMBED):
                raise HTTPException(
                    status_code=503,
                    detail=f"Brak modelu embeddingów: {config.MODEL_EMBED}",
                )
            if not client.has_model(config.MODEL_CODER):
                raise HTTPException(
                    status_code=503,
                    detail=f"Brak modelu koderskiego: {config.MODEL_CODER}",
                )
            logger.info("Indeksowanie i analiza techniczna...")
            index = embedder.build_index(repo.path, index_name=repo.slug)
            llm_result = llm_analyzer.run_full(index, repo, static)
            if client.has_model(config.MODEL_POLISH):
                polish_report = report_generator.generate(repo, static, llm_result)
                report_generator.save_to_file(polish_report, repo.slug)

        record = kb.new_record(url=req.url, slug=repo.slug)
        record.repo_info = repo.to_dict()
        record.static = static.to_dict()
        record.diagrams = diagrams
        record.lesson_deck = lesson_deck
        record.llm = llm_result.to_dict() if llm_result else {}
        record.polish_report = polish_report
        kb.save(record)

        duration = round(time.time() - started, 2)
        logger.info("ANALIZA OK: %s (%.2fs)", req.url, duration)

        return {
            "id": record.id,
            "duration_s": duration,
            "repo_info": repo.to_dict(),
            "static": static.to_dict(),
            "lesson_deck": lesson_deck,
            "llm": record.llm,
            "diagrams": diagrams,
            "polish_report": polish_report,
        }

    except HTTPException:
        raise
    except OllamaError as e:
        logger.error("Błąd Ollamy: %s", e)
        raise HTTPException(status_code=503, detail=f"Błąd Ollamy: {e}") from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.error("Nieoczekiwany błąd: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Nieoczekiwany błąd: {e}") from e


@app.get("/api/reports")
def list_reports(q: Optional[str] = Query(None)) -> Dict[str, Any]:
    if q:
        items = kb.search(q)
    else:
        items = kb.list_records()
    return {"count": len(items), "items": items}


@app.get("/api/reports/{record_id}")
def get_report(record_id: str) -> Dict[str, Any]:
    record = kb.load(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Brak raportu: {record_id}")
    return record.to_dict()


@app.delete("/api/reports/{record_id}", response_model=GenericMessage)
def delete_report(record_id: str) -> Dict[str, str]:
    if kb.delete(record_id):
        return {"detail": "Usunięto."}
    raise HTTPException(status_code=404, detail=f"Brak raportu: {record_id}")


@app.get("/api/reports/{record_id}/markdown", response_class=PlainTextResponse)
def get_report_markdown(record_id: str) -> str:
    record = kb.load(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Brak raportu: {record_id}")
    if record.polish_report:
        return record.polish_report
    deck = record.lesson_deck
    if deck:
        lines = [f"# {deck.get('title', 'Prezentacja')}", "", deck.get("essence", "")]
        for slide in deck.get("slides") or []:
            lines.extend(["", f"## {slide.get('title', '')}", slide.get("body", "")])
        return "\n".join(lines)
    raise HTTPException(status_code=404, detail="Brak treści do eksportu.")


if config.FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(config.FRONTEND_DIR / "index.html")

    @app.get("/css/{name:path}", include_in_schema=False)
    def serve_css(name: str) -> FileResponse:
        path = config.FRONTEND_DIR / "css" / name
        if not path.exists():
            raise HTTPException(status_code=404, detail="Brak pliku CSS")
        return FileResponse(path)

    @app.get("/js/{name:path}", include_in_schema=False)
    def serve_js(name: str) -> FileResponse:
        path = config.FRONTEND_DIR / "js" / name
        if not path.exists():
            raise HTTPException(status_code=404, detail="Brak pliku JS")
        return FileResponse(path)
else:
    logger.warning("Katalog frontendu nie istnieje: %s", config.FRONTEND_DIR)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):  # type: ignore[override]
    logger.error("Niezłapany wyjątek: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": "Wewnętrzny błąd serwera."})


def run() -> None:
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=config.API_RELOAD,
    )


if __name__ == "__main__":
    run()

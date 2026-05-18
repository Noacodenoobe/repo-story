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
from .education_generator import EducationGenerator
from .guide_indexer import GuideIndexer
from .html_exporter import HtmlExporter
from .knowledge_store import KnowledgeStore
from .rag_chat import RagChatService
from .system_profile import SystemProfileService


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
    version="4.0.0",
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
education_generator = EducationGenerator()
kb = KnowledgeBase()
guide_indexer = GuideIndexer()
html_exporter = HtmlExporter()
rag_chat = RagChatService()
system_profile_svc = SystemProfileService()
knowledge_store = KnowledgeStore()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = Field(None, description="Optional chat session id")


class ProfileUploadRequest(BaseModel):
    profile: Dict[str, Any] = Field(..., description="System profile JSON object")


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

        education_pack: Dict[str, Any] = {}
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
            logger.info("Generuję pakiet edukacyjny (przewodnik + diagramy)...")
            pack = education_generator.generate(repo, static)
            education_pack = pack.to_dict()
            lesson_deck = {
                "title": pack.title,
                "essence": pack.essence,
                "summary_3": pack.summary_3,
                "slides": pack.story_slides,
                "quiz": pack.quiz,
            }

        if req.include_technical:
            try:
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
            except (HTTPException, OllamaError) as tech_exc:
                logger.warning(
                    "Analiza techniczna nie powiodła się — prezentacja zostaje: %s", tech_exc
                )
                if not education_pack:
                    raise

        record = kb.new_record(url=req.url, slug=repo.slug)
        record.repo_info = repo.to_dict()
        record.static = static.to_dict()
        record.diagrams = diagrams
        record.lesson_deck = lesson_deck
        record.education_pack = education_pack
        record.llm = llm_result.to_dict() if llm_result else {}
        record.polish_report = polish_report
        json_path = kb.save(record)

        if config.AUTO_INDEX_GUIDES and education_pack:
            try:
                guide_indexer.index_record(record, json_path=str(json_path))
            except Exception as idx_exc:  # noqa: BLE001
                logger.warning("Guide indexing failed: %s", idx_exc)

        if config.AUTO_EXPORT_HTML and education_pack:
            try:
                html_exporter.export(record)
            except Exception as html_exc:  # noqa: BLE001
                logger.warning("HTML export failed: %s", html_exc)

        duration = round(time.time() - started, 2)
        logger.info("ANALIZA OK: %s (%.2fs)", req.url, duration)

        return {
            "id": record.id,
            "duration_s": duration,
            "repo_info": repo.to_dict(),
            "static": static.to_dict(),
            "education_pack": education_pack,
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
    edu = record.education_pack or record.lesson_deck
    if edu:
        lines = [f"# {edu.get('title', 'Przewodnik')}", "", edu.get("essence", "")]
        ov = edu.get("overview") or {}
        for key, label in [("what", "Czym jest"), ("why", "Po co"), ("how_it_works", "Jak działa")]:
            if ov.get(key):
                lines.extend(["", f"## {label}", ov[key]])
        for step in edu.get("howto") or []:
            lines.extend(["", f"## Krok {step.get('step')}: {step.get('title')}", step.get("body", "")])
        return "\n".join(lines)
    raise HTTPException(status_code=404, detail="Brak treści do eksportu.")


@app.get("/api/reports/{record_id}/export.html", include_in_schema=False)
def get_report_html(record_id: str) -> FileResponse:
    """Download standalone HTML guide."""
    record = kb.load(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Brak raportu: {record_id}")
    path = html_exporter.get_path(record_id)
    if not path:
        path = html_exporter.export(record)
    return FileResponse(path, media_type="text/html", filename=f"przewodnik-{record_id[:8]}.html")


@app.get("/api/knowledge/stats")
def knowledge_stats() -> Dict[str, Any]:
    """RAG / SQLite diagnostics."""
    return knowledge_store.stats()


@app.post("/api/chat")
def chat(req: ChatRequest) -> Dict[str, Any]:
    """Global RAG chat over guides and system profile."""
    if not get_client().ping():
        raise HTTPException(status_code=503, detail="Ollama niedostępna.")
    return rag_chat.chat(req.message, session_id=req.session_id)


@app.get("/api/system-profile")
def get_system_profile() -> Dict[str, Any]:
    """Latest collected system profile."""
    data = system_profile_svc.get()
    if not data:
        return {"profile": None, "message": "Brak profilu — uruchom zbieranie."}
    return data


@app.post("/api/system-profile/refresh")
def refresh_system_profile() -> Dict[str, Any]:
    """Run collect script and re-index profile."""
    try:
        return system_profile_svc.refresh()
    except Exception as exc:  # noqa: BLE001
        logger.error("Profile refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/system-profile/upload")
def upload_system_profile(req: ProfileUploadRequest) -> Dict[str, Any]:
    """Upload profile JSON collected outside the server."""
    try:
        return system_profile_svc.upload(req.profile)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/knowledge/index-host-rules")
def index_host_rules_endpoint() -> Dict[str, Any]:
    """Index Linux AI regulamin and project standard into RAG."""
    from .host_rules import index_host_rules
    return index_host_rules(knowledge_store)


@app.post("/api/knowledge/migrate")
def migrate_knowledge() -> Dict[str, Any]:
    """Index all existing JSON reports into SQLite."""
    from .migrate_reports import migrate_all
    count = migrate_all()
    return {"migrated": count, "stats": knowledge_store.stats()}


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

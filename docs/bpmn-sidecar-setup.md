# BPMN — Ollama (domyślnie) i opcjonalny sidecar Docker

Repo Opowieść generuje **diagramy BPMN 2.0 lokalnie przez Ollamę** (`BPMN_USE_OLLAMA=true` — domyślnie).
**Nie potrzebujesz kluczy API chmurowych.**

Sidecar `bpmn-assistant` (Docker) jest **opcjonalny** — służy do:
- konwersji XML → JSON (`/bpmn_to_json`, bez kluczy LLM)
- pełnego edytora UI na porcie 9749

## Wymagania (tryb lokalny)

```bash
ollama serve
ollama pull qwen3.5:9b              # BPMN_OLLAMA_MODEL (domyślnie, lżejszy niż qwen3-coder)
ollama pull SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M  # opisy po polsku
```

Opcjonalnie w `.env` repo-story:

```bash
BPMN_USE_OLLAMA=true
BPMN_OLLAMA_MODEL=qwen3.5:9b
```

Sprawdzenie:

```bash
curl -s http://127.0.0.1:9743/api/bpmn-assistant/health | python3 -m json.tool
# engine: "ollama", ollama_ok: true
```

## Sidecar Docker (opcjonalnie)

Port **8000** na hoście jest często zajęty — mapowanie **9748 / 9749 / 3017**:

| Usługa | Port hosta | Kontener |
|--------|------------|----------|
| API | 9748 | 8000 |
| UI | 9749 | 80 |
| Layout | 3017 | 3001 |

```bash
cd /mnt/ollama/projekty/repo-story
./scripts/setup-bpmn-sidecar.sh
./scripts/check-bpmn-sidecar.sh
```

Używaj **`docker compose`** (plugin), nie legacy `docker-compose`.

Klucze w `src/bpmn_assistant/.env` sidecar są potrzebne **tylko** gdy ustawisz `BPMN_USE_OLLAMA=false`.

## Podział ról

| Warstwa | Silnik |
|---------|--------|
| RAG, plany wdrożenia, opisy PL | Ollama / Bielik |
| Diagram BPMN 2.0 XML | Ollama (`qwen3-coder` domyślnie) |
| Edytor / XML→JSON | opcjonalny sidecar Docker |

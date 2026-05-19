# BPMN Assistant sidecar setup (Phase C1)

Repo Opowieść uses **bpmn-assistant** as a Docker sidecar for BPMN 2.0 diagrams.
RAG and deployment plans stay in repo-story; diagram generation calls the sidecar API.

## Prerequisites

- Docker and docker-compose
- At least one cloud LLM API key (OpenAI, Anthropic, Google, or Fireworks)
- Install path under `/mnt/ollama/projekty/` (host regulamin)

## Install

```bash
cd /mnt/ollama/projekty
git clone https://github.com/jtlicardo/bpmn-assistant.git
cd bpmn-assistant/src/bpmn_assistant
cp .env.example .env
# Edit .env — add API keys (never commit)
cd ../..
docker-compose up --build -d
```

## Ports

| Service | Port | Role |
|---------|------|------|
| bpmn_assistant API | 8000 | POST /modify |
| bpmn_frontend | 8080 | Full editor UI |
| bpmn_layout_server | 3001 | Layout |

## Verify

```bash
./scripts/check-bpmn-sidecar.sh
curl -s http://127.0.0.1:9743/api/bpmn-assistant/health | python3 -m json.tool
```

## Repo Opowieść config (optional `.env`)

```bash
BPMN_ASSISTANT_URL=http://127.0.0.1:8000
BPMN_ASSISTANT_FRONTEND_URL=http://127.0.0.1:8080
BPMN_ASSISTANT_ENV_FILE=/mnt/ollama/projekty/bpmn-assistant/src/bpmn_assistant/.env
```

Keys are read from the sidecar `.env` file on the server — not indexed into `knowledge.db`.

## Notes

- **Ollama/Bielik** — Polish narratives and deployment plans (local)
- **Sidecar cloud keys** — BPMN XML generation via `/modify`
- Do not use `pip install bpmn-assistant` (not the upstream project on PyPI)

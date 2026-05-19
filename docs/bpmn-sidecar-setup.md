# BPMN Assistant sidecar setup (Phase C1)

Repo Opowieść uses **bpmn-assistant** as a Docker sidecar for BPMN 2.0 diagrams.
RAG and deployment plans stay in repo-story; diagram generation calls the sidecar API.

**Default host ports (avoid busy 8000/8080 on this machine):**

| Service | Host port | Container |
|---------|-----------|-----------|
| API | **9748** | 8000 |
| UI | **9749** | 8080 |
| Layout | 3017 | 3001 |

## Prerequisites

- Docker and docker-compose
- At least one cloud LLM API key (OpenAI, Anthropic, Google, or Fireworks)
- Install path under `/mnt/ollama/projekty/` (host regulamin)

## Install (one command from repo-story)

```bash
cd /mnt/ollama/projekty/repo-story
./scripts/setup-bpmn-sidecar.sh
```

Uses **`docker compose`** (plugin), not legacy `docker-compose`. Manual steps:

```bash
cd /mnt/ollama/projekty
git clone https://github.com/jtlicardo/bpmn-assistant.git
cd bpmn-assistant/src/bpmn_assistant
cp .env.example .env   # add API keys
cd ../..
# Edit docker-compose.yml ports → 9748:8000, 9749:80, 3017:3001
docker compose up --build -d
```

Host ports (port 8000 is often busy on this machine):

| Service | Host port | Container |
|---------|-----------|-----------|
| API | **9748** | 8000 |
| UI | **9749** | 80 (nginx) |
| Layout | 3017 | 3001 |
curl -s http://127.0.0.1:9743/api/bpmn-assistant/health | python3 -m json.tool
curl -s http://127.0.0.1:9748/
```

## Repo Opowieść config (optional `.env`)

```bash
BPMN_ASSISTANT_URL=http://127.0.0.1:9748
BPMN_ASSISTANT_FRONTEND_URL=http://127.0.0.1:9749
BPMN_ASSISTANT_ENV_FILE=/mnt/ollama/projekty/bpmn-assistant/src/bpmn_assistant/.env
```

Keys are read from the sidecar `.env` file on the server — not indexed into `knowledge.db`.

## Notes

- **Ollama/Bielik** — Polish narratives and deployment plans (local)
- **Sidecar cloud keys** — BPMN XML generation via `/modify`
- Do not use `pip install bpmn-assistant` (not the upstream project on PyPI)

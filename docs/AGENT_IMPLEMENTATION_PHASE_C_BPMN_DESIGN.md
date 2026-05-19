# Repo Opowieść — Faza C: Asystent projektowania procesów BPMN

**Wersja dokumentu:** 2026-05-19  
**Status:** **PLAN / DO WDROŻENIA** (nie ukończone)  
**Poprzedniki (OBOWIĄZKOWE):**

1. [`AGENT_IMPLEMENTATION_LIVE_ASSISTANT.md`](./AGENT_IMPLEMENTATION_LIVE_ASSISTANT.md) — Fazy 1–3 (czat RAG, głos, SSE)
2. [`AGENT_IMPLEMENTATION_PHASE_AB.md`](./AGENT_IMPLEMENTATION_PHASE_AB.md) — Fazy A i B (notatnik, akcje, projekty, checklisty)

**Projekt:** `/mnt/ollama/projekty/repo-story` · port **9743**  
**GitHub:** https://github.com/Noacodenoobe/repo-story  
**Projekt zewnętrzny (umiejętności BPMN):** https://github.com/jtlicardo/bpmn-assistant  

**Cel użytkownika (Faza C):** Repo Opowieść ma wykorzystywać **umiejętności BPMN Asystenta** — przy projektowaniu procesów prezentować **szczegółowe diagramy BPMN 2.0** (jak w oryginalnym repo), a nie tylko ogólne diagramy Mermaid z przewodnika edukacyjnego. Dodatkowo: **plan wdrożenia** na sprzęcie użytkownika (ścieżki `/mnt/ollama`, kroki howto, komendy z whitelisty).

---

## 0. Wizja produktu

| Warstwa | Dziś (repo-story) | Docelowo (Faza C) |
|---------|-------------------|-------------------|
| **Edukacja o repo** | `EducationPack` + Mermaid (flow, zależności) | Bez zmian |
| **Rozmowa RAG** | Tekst + opcjonalnie ` ```run ` | + tryb **process_design** z diagramem BPMN |
| **Projektowanie procesu** | Brak | Opis słowny → **BPMN XML/JSON** → podgląd **bpmn-js** |
| **Instalacja narzędzia** | Chunki howto w RAG (często źle trafiane) | **DeploymentPlan** (JSON) + poprawiony focus retrieval |
| **Silnik BPMN** | Brak | **Sidecar** `bpmn-assistant` (Docker, porty 8000/8080) lub iframe |

**Zasada:** Repo Opowieść = **orkiestrator i warstwa polska** (RAG, regulamin hosta, głos, bezpieczne akcje). **BPMN Asystent** = **silnik diagramów** (create/edit/interpret BPMN) — nie duplikować logiki modelowania w pierwszej iteracji.

---

## 1. Stan wyjściowy (sesja 2026-05-19)

### 1.1 Co już działa (nie psuj)

- Czat RAG: `POST /api/chat`, `POST /api/chat/stream`, `rag_chat.py`, `rag_retrieval.py`, `chat_grounding.py`
- Fazy A/B (lokalnie, **sprawdź `git status`** — mogą być niezacommitowane): notatnik, `action_runner`, projekty, checklisty, Supertonic, grounding czatu
- Przewodnik **„BPMN Asystent”** w `data/knowledge.db` (33 chunki, sekcja `howto` z `git clone`, `cd`, `docker-compose`)
- UI przewodnika: Mermaid w zakładkach Opowieść / Przepływ / Instrukcja

### 1.2 Znane problemy (naprawić w C0 przed integracją API)

| Problem | Przykład | Plik |
|---------|----------|------|
| Zły focus przy „bpmn-assistent**a**” | Trafia w Layout Generator zamiast Asystenta | `rag_retrieval.py` |
| Halucynacje instalacji | `pip install bpmn-assistant`, złe URL | `conversation_config.py`, `chat_grounding.py` |
| Brak trybu strukturalnego | Wolny tekst zamiast planu wdrożenia | **do zbudowania** `deployment_plan.py` |

### 1.3 BPMN Asystent — fakty techniczne (upstream)

Źródło: README i `src/bpmn_assistant/app.py` w https://github.com/jtlicardo/bpmn-assistant

**Docker Compose (lokalnie):**

| Usługa | Port | Rola |
|--------|------|------|
| `bpmn_assistant` | **8000** | FastAPI: modelowanie BPMN |
| `bpmn_layout_server` | 3001 | Layout diagramów |
| `bpmn_frontend` | **8080** | UI (bpmn-js + czat) |

**Kluczowe endpointy API (port 8000):**

| Metoda | Ścieżka | Zwraca |
|--------|---------|--------|
| GET | `/` | health |
| POST | `/modify` | `{ "bpmn_xml", "bpmn_json" }` — tworzy lub edytuje proces |
| POST | `/determine_intent` | intencja użytkownika |
| POST | `/talk` | stream odpowiedzi konwersacyjnej |
| POST | `/bpmn_to_json` | konwersja XML → JSON |

**Wymagania upstream:** co najmniej jeden klucz API (**OpenAI / Anthropic / Google / Fireworks**) w `.env` — **nie używa Ollamy/Bielika domyślnie**.

**Implikacja dla hosta użytkownika:** Faza C musi jasno komunikować: tryb diagramów BPMN wymaga kluczy chmurowych (lub hostowanej wersji web) — regulamin `/mnt/ollama` dotyczy **miejsca instalacji Dockera**, nie zastępuje kluczy LLM BPMN Asystenta.

**Rekomendowana ścieżka instalacji sidecar (z przewodnika w KB):**

```text
/mnt/ollama/projekty/bpmn-assistant/
  git clone https://github.com/jtlicardo/bpmn-assistant.git
  cd src/bpmn_assistant && cp .env.example .env   # uzupełnij klucze API
  cd ../.. && docker-compose up --build
  UI: http://127.0.0.1:8080
  API: http://127.0.0.1:8000
```

---

## 2. Architektura docelowa (Faza C)

```mermaid
flowchart TB
  subgraph ui [Repo Opowieść UI :9743]
    Chat[Rozmowa]
    Design[Zakładka Projektuj BPMN]
    Deploy[Panel Plan wdrożenia]
    BpmnView[Podgląd bpmn-js]
  end

  subgraph rs [FastAPI repo-story]
    Router[Intent router]
    RAG[rag_chat + retrieval]
    DepPlan[deployment_plan_service]
    BpmnClient[bpmn_assistant_client]
    Session[process_design_sessions]
  end

  subgraph kb [(knowledge.db)]
    Guides[Przewodnik BPMN Asystent]
    Rules[Regulamin hosta]
  end

  subgraph sidecar [bpmn-assistant Docker]
    API["POST /modify :8000"]
    FE[Frontend :8080]
    Layout[layout :3001]
  end

  Chat --> Router
  Router -->|install / meta| RAG
  Router -->|process_design| BpmnClient
  Router -->|install| DepPlan
  RAG --> kb
  DepPlan --> kb
  BpmnClient --> API
  Design --> FE
  BpmnClient --> BpmnView
  API --> Layout
```

### 2.1 Tryby odpowiedzi czatu (`response_mode`)

Rozszerzyć `ChatRequest` w `main.py`:

| `response_mode` | Kiedy | Output |
|-----------------|-------|--------|
| `default` | Ogólne pytania | Tekst RAG (jak dziś) |
| `deployment` | Instalacja, ścieżki, „czy widzisz pliki” | JSON **DeploymentPlan** + skrót PL |
| `process_design` | „zaprojektuj proces”, „diagram BPMN dla…” | JSON **ProcessDesignArtifact** + BPMN XML + podgląd |

**Wykrywanie intencji (kolejność):**

1. Reguły słów kluczowych (PL/EN): `proces`, `bpmn`, `diagram procesu`, `workflow`, `stwórz diagram`
2. Opcjonalnie: `POST /determine_intent` sidecar (jeśli healthy)
3. Fallback: `default`

### 2.2 Schematy danych (nowe moduły)

#### `DeploymentPlan` — `backend/app/deployment_plan.py`

```python
# Pola logiczne (Pydantic) — kod po angielsku
# visibility: live_disk_access, indexed_sources[]
# project: guide_title, guide_slug, confidence
# host_rules: []  # z regulaminu
# recommended_paths: { clone_root, venv_root }  # /mnt/ollama/...
# steps: [{ order, title, body, paths[], commands[], source_section }]
# gaps: []
# citations: []
```

Generacja: **hybryda** — deterministycznie z chunków `howto` + profil/regulamin; LLM tylko do sformułowania `title`/`body` (opcjonalnie).

#### `ProcessDesignArtifact` — `backend/app/process_design.py`

```python
# user_prompt: str
# bpmn_xml: str
# bpmn_json: list[dict]  # z /modify
# narrative_pl: str        # skrót po polsku (Bielik lub /talk stream)
# model_used: str
# sidecar_status: ok | unavailable | missing_api_keys
# revision: int
```

### 2.3 Klient sidecar — `backend/app/bpmn_assistant_client.py`

```text
class BpmnAssistantClient:
    base_url: str  # config.BPMN_ASSISTANT_URL default http://127.0.0.1:8000
    health() -> bool
    modify(message_history, process=None, model=..., api_keys=...) -> dict
    # api_keys: z config/env BPMN_ASSISTANT_API_KEYS_JSON lub proxy do .env sidecar
```

**Bezpieczeństwo:** klucze API **nigdy** w logach; nie commitować `.env`; opcjonalnie tylko odczyt z `/mnt/ollama/projekty/bpmn-assistant/src/bpmn_assistant/.env` (ścieżka w config).

### 2.4 Sesje projektowe — `process_design_sessions` (SQLite)

Tabela w `knowledge_store.py` lub osobny plik:

| Kolumna | Opis |
|---------|------|
| `id` | UUID |
| `session_id` | powiązanie z czatem |
| `title` | np. „Proces zamówienia pizzy” |
| `bpmn_xml` | ostatnia wersja |
| `history_json` | message_history dla /modify |
| `updated_at` | ISO |

API:

- `GET /api/process-design/sessions`
- `GET /api/process-design/sessions/{id}`
- `POST /api/process-design/generate` — body: `{ session_id?, message, model? }`
- `POST /api/process-design/revise` — edycja istniejącego XML

---

## 3. UI (frontend)

### 3.1 Nowa zakładka: **„Projektuj BPMN”**

Pliki: `frontend/public/index.html`, `js/app.js`, `css/styles.css`

| Element | Opis |
|---------|------|
| Status sidecar | 🟢 API :8000 / 🔴 uruchom Docker (link do howto) |
| Panel lewy | Czat / pole opisu procesu (PL) |
| Panel prawy | **bpmn-js** renderujący `bpmn_xml` z API |
| Akcje | „Generuj”, „Popraw”, „Eksportuj .bpmn”, „Otwórz pełny edytor” (link :8080) |
| Fallback | iframe `http://127.0.0.1:8080` gdy integracja API nie gotowa |

**Biblioteka:** `bpmn-js` (CDN lub vendor w `frontend/public/vendor/`) — ten sam ekosystem co upstream.

### 3.2 Rozmowa — tryb process_design

- Po wykryciu intencji: banner „Tryb projektowania BPMN”
- SSE event `meta`: `{ response_mode, process_design_id, sidecar_ok }`
- SSE event `bpmn`: `{ bpmn_xml }` (osobny event przed końcem tekstu)
- Cytowania: przewodnik BPMN Asystent + regulamin (ścieżki hosta)

### 3.3 Plan wdrożenia (deployment)

- Renderer JSON → karty kroków (jak checklisty B3)
- Przyciski `▶ Wykonaj` tylko dla komend z `action_runner` whitelist
- Sekcje: „Widoczność systemu” | „Gdzie na dysku” | „Kroki instalacji”

---

## 4. Plan sprintów (kolejność dla agenta)

### Sprint C0 — Fundament (1–2 dni) **BLOCKER**

| ID | Zadanie | Pliki |
|----|---------|-------|
| C0.1 | Alias focus: `bpmn-assistent`, `assistent`, `assist*`; kara Layout Generator | `rag_retrieval.py`, testy |
| C0.2 | `missing_howto` gdy focus OK bez chunków howto | `rag_chat.py` |
| C0.3 | Moduł `deployment_plan.py` + `build_deployment_plan()` z chunków | nowy + testy |
| C0.4 | `response_mode` w `ChatRequest`; routing w `rag_chat.py` | `main.py`, `rag_chat.py` |
| C0.5 | Prompt `deployment` w `conversation_config.py` | rozszerzenie |
| C0.6 | UI renderer DeploymentPlan | `app.js`, `styles.css` |
| C0.7 | Smoke: pytanie użytkownika o „bpmn-assistenta” → focus Asystent + howto | skrypt / test |

**Kryterium akceptacji C0:** Na pytanie o instalację i pliki — **nie** ma `pip install bpmn-assistant`; jest plan z `git clone` jtlicardo i ścieżkami `/mnt/ollama`.

---

### Sprint C1 — Sidecar i health (1 dzień)

| ID | Zadanie |
|----|---------|
| C1.1 | `config.py`: `BPMN_ASSISTANT_URL`, `BPMN_ASSISTANT_ENABLED`, timeout |
| C1.2 | `bpmn_assistant_client.py` + `GET /api/bpmn-assistant/health` |
| C1.3 | Dokument `docs/bpmn-sidecar-setup.md` (instalacja Docker, .env, porty) |
| C1.4 | Skrypt `scripts/check-bpmn-sidecar.sh` |
| C1.5 | UI: wskaźnik statusu w zakładce Projektuj |

**Kryterium:** `curl /api/bpmn-assistant/health` → `{ "ok": true }` gdy docker działa.

---

### Sprint C2 — Generowanie BPMN z Repo Opowieść (2–3 dni)

| ID | Zadanie |
|----|---------|
| C2.1 | `process_design.py` + `ProcessDesignService` |
| C2.2 | `POST /api/process-design/generate` wywołuje `/modify` |
| C2.3 | Mapowanie `message_history` (format upstream `MessageItem`) |
| C2.4 | Konfiguracja modelu: `BPMN_ASSISTANT_MODEL` (domyślnie z .env sidecar) |
| C2.5 | Zapis sesji w SQLite |
| C2.6 | Testy z mockiem HTTP (bez prawdziwych kluczy API) |

**Kryterium:** Opis PL „proces zamówienia pizzy: przyjęcie → pieczenie → dostawa” → zwrot poprawnego `bpmn_xml` (niepusty, parseable).

---

### Sprint C3 — UI diagramu i czat zintegrowany (2 dni)

| ID | Zadanie |
|----|---------|
| C3.1 | Zakładka Projektuj BPMN + bpmn-js |
| C3.2 | SSE: event `bpmn` w `rag_chat.chat_stream` dla `process_design` |
| C3.3 | Intent router w czacie |
| C3.4 | Eksport `.bpmn` (download) |
| C3.5 | Link „Otwórz w pełnym edytorze” → :8080 |

---

### Sprint C4 — Interpretacja i RAG wzmacniający (1–2 dni)

| ID | Zadanie |
|----|---------|
| C4.1 | Po wygenerowaniu: skrót PL przez Bielik na podstawie `bpmn_json` (lokalnie) |
| C4.2 | Opcjonalnie stream `/talk` sidecar dla szczegółowego komentarza |
| C4.3 | Indeksowanie **własnych** diagramów użytkownika jako `user_notes` (opis + ścieżka pliku) — bez auto-uploadu |
| C4.4 | Quiz / slajdy — **nie** mieszać z BPMN 2.0 (osobne tryby) |

---

### Sprint C5 — Opcjonalnie: Ollama w BPMN (przyszłość)

| ID | Zadanie | Uwaga |
|----|---------|-------|
| C5.1 | Fork `bpmn-assistant` + provider Ollama | Duży zakres |
| C5.2 | Lub: lokalny generator BPMN XML w repo-story | Wymaga walidatora BPMN |

**Nie wdrażać C5** bez explicit polecenia użytkownika.

---

## 5. Konfiguracja (`config.py` — propozycja)

```python
BPMN_ASSISTANT_ENABLED = os.getenv("BPMN_ASSISTANT_ENABLED", "true").lower() == "true"
BPMN_ASSISTANT_URL = os.getenv("BPMN_ASSISTANT_URL", "http://127.0.0.1:8000")
BPMN_ASSISTANT_FRONTEND_URL = os.getenv("BPMN_ASSISTANT_FRONTEND_URL", "http://127.0.0.1:8080")
BPMN_ASSISTANT_MODEL = os.getenv("BPMN_ASSISTANT_MODEL", "gpt-4.1")  # przykład
BPMN_ASSISTANT_TIMEOUT_S = float(os.getenv("BPMN_ASSISTANT_TIMEOUT_S", "120"))
# Ścieżka do .env sidecar (opcjonalnie, tylko odczyt kluczy po stronie serwera)
BPMN_ASSISTANT_ENV_FILE = os.getenv(
    "BPMN_ASSISTANT_ENV_FILE",
    "/mnt/ollama/projekty/bpmn-assistant/src/bpmn_assistant/.env",
)
```

`.env.example` w repo-story — dodać sekcję BPMN (bez wartości kluczy).

---

## 6. Regulamin hosta — zasady dla agenta

1. **Instalacja sidecar:** klon pod `/mnt/ollama/projekty/`, nie w `$HOME` ani `/` bez potrzeby.
2. **Brak `sudo`** w `action_runner` dla docker — użytkownik uruchamia `docker-compose` ręcznie lub przez zatwierdzony skrypt.
3. **Klucze API chmurowe** — przechowywać tylko w `.env` sidecar; nie indeksować do `knowledge.db`.
4. **Ollama/Bielik** — opisy i plany wdrożenia; **diagramy BPMN 2.0** — sidecar (chyba że C5).
5. **Nie mieszać** z `repo-analyzer` (9742).

---

## 7. Testy

| Plik | Zakres |
|------|--------|
| `test_rag_retrieval.py` | focus `bpmn-assistenta`, brak Layout Generator |
| `test_deployment_plan.py` | budowa planu z mock chunków howto |
| `test_bpmn_assistant_client.py` | mock `httpx` / `requests` na `/modify` |
| `test_process_design.py` | sesje, revise |
| `test_chat_modes.py` | routing `response_mode` |

**Smoke E2E (ręczny):**

```bash
# 1. Sidecar
cd /mnt/ollama/projekty/bpmn-assistant && docker-compose up -d
curl -s http://127.0.0.1:8000/

# 2. Repo Opowieść
cd /mnt/ollama/projekty/repo-story && ./run.sh
curl -s http://127.0.0.1:9743/api/bpmn-assistant/health | python3 -m json.tool

# 3. Generowanie
curl -s -X POST http://127.0.0.1:9743/api/process-design/generate \
  -H 'Content-Type: application/json' \
  -d '{"message":"Proces: klient składa zamówienie, kuchnia przygotowuje, kurier dostarcza."}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('bpmn_xml','')))"
```

---

## 8. Pliki do utworzenia / zmiany (checklist)

```text
backend/app/
  deployment_plan.py          # C0
  bpmn_assistant_client.py    # C1
  process_design.py           # C2
  intent_router.py            # C0/C2
  rag_retrieval.py            # C0 (aliasy)
  rag_chat.py                 # C0/C2/C3 (modes, SSE bpmn)
  conversation_config.py      # C0 (prompty)
  config.py                   # C1
  knowledge_store.py          # C2 (tabela sesji)
  main.py                     # endpointy

frontend/public/
  index.html                  # zakładka Projektuj
  js/app.js                   # bpmn-js, deployment UI, SSE bpmn
  css/styles.css

docs/
  bpmn-sidecar-setup.md       # C1
  AGENT_IMPLEMENTATION_PHASE_C_BPMN_DESIGN.md  # ten plik

scripts/
  check-bpmn-sidecar.sh       # C1

tests/
  test_deployment_plan.py
  test_bpmn_assistant_client.py
  test_process_design.py
  test_chat_modes.py
```

---

## 9. Wersjonowanie Git

Po **C0:** tag `v4.5.0-deployment-plan`  
Po **C2+C3:** tag `v4.6.0-bpmn-design`  

Commit messages (przykład):

```text
feat(chat): deployment plan mode and BPMN focus aliases (C0)
feat(bpmn): sidecar client and process-design API (C1-C2)
feat(ui): BPMN designer tab with bpmn-js viewer (C3)
```

**Nie commitować:** `data/knowledge.db`, `.env`, kluczy API.

---

## 10. Czego agent NIE powinien robić

- Nie implementować własnego silnika BPMN od zera przed podłączeniem `/modify`.
- Nie obiecywać użytkownikowi dostępu do całego dysku — tylko zindeksowana baza + wygenerowane artefakty.
- Nie używać `pip install bpmn-assistant` (nie istnieje na PyPI jako ten projekt).
- Nie wdrażać Poziomu D (agent 24/7) przed ukończeniem C0–C3.
- Nie modyfikować `repo-analyzer` bez polecenia.

---

## 11. Prompt startowy — nowa sesja agenta (Faza C)

Skopiuj do nowego czatu:

```text
Wdrażasz Repo Opowieść — Fazę C (integracja BPMN Asystenta + plan wdrożenia).

Przeczytaj OBOWIĄZKOWO (w tej kolejności):
1. /mnt/ollama/projekty/repo-story/docs/AGENT_IMPLEMENTATION_LIVE_ASSISTANT.md
2. /mnt/ollama/projekty/repo-story/docs/AGENT_IMPLEMENTATION_PHASE_AB.md
3. /mnt/ollama/projekty/repo-story/docs/AGENT_IMPLEMENTATION_PHASE_C_BPMN_DESIGN.md  ← TEN PLIK
4. /mnt/ollama/system-control/info wazne/regulamin_linux_ai.md

Na start:
  cd /mnt/ollama/projekty/repo-story
  git fetch origin && git status -sb && git log -3 --oneline

Kontekst:
- Port repo-story: 9743. Nie ruszaj repo-analyzer (9742).
- BPMN Asystent upstream: https://github.com/jtlicardo/bpmn-assistant
  API :8000 (/modify), UI :8080 (docker-compose).
- W knowledge.db jest przewodnik „BPMN Asystent” z howto — użyć w DeploymentPlan.

Kolejność prac (zatwierdzona przez użytkownika 2026-05-19):
  C0: focus retrieval + DeploymentPlan + response_mode deployment
  C1: bpmn_assistant_client + health endpoint + docs sidecar
  C2: process-design API (/modify) + sesje SQLite
  C3: UI zakładka Projektuj BPMN + bpmn-js + SSE event bpmn
  C4: interpretacja PL (Bielik) + opcjonalnie /talk
  NIE wdrażaj C5 (Ollama w BPMN) bez polecenia.

Po każdym sprincie: testy + restart uvicorn 9743 + smoke z sekcji 7.
Kod i komentarze po angielsku; UI i odpowiedzi użytkownikowi po polsku.
Commit/push tylko na wyraźną prośbę użytkownika.
```

---

## 12. Odpowiedź na pytanie użytkownika (kontekst biznesowy)

**Czy obecna odpowiedź czatu jest poprawna?**  
Nie — to ogólny regulamin + halucynacja `pip install`. Poprawny kierunek to **DeploymentPlan** z howto + jasne „nie widzę dysku na żywo”.

**Czy możemy zaprojektować output narzędzia?**  
Tak — dwa typy artefaktów:

1. **DeploymentPlan** — szczegółowa instrukcja na Twoim sprzęcie (foldery, komendy, regulamin).
2. **ProcessDesignArtifact** — diagram BPMN 2.0 jak w oryginalnym repo (przez sidecar), z podglądem w UI.

Repo Opowieść staje się **jednym miejscem**: uczysz się projektu (przewodnik), rozmawiasz (RAG), instalujesz (plan), projektujesz procesy (BPMN).

---

*Koniec dokumentu Fazy C.*

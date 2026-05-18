# Repo Opowieść — Fazy A i B (kontynuacja dla agenta)

**Wersja dokumentu:** 2026-05-18 (sesja 2)  
**Poprzednik (OBOWIĄZKOWY kontekst):** [`AGENT_IMPLEMENTATION_LIVE_ASSISTANT.md`](./AGENT_IMPLEMENTATION_LIVE_ASSISTANT.md)  
**Projekt:** `/mnt/ollama/projekty/repo-story` · port **9743**  
**GitHub:** https://github.com/Noacodenoobe/repo-story  
**Tag bazowy po głosie:** `v4.3.0-voice-assistant` (commit `687c8f6`)

Użytkownik zaakceptował kierunki **Poziom A** (szybkie usprawnienia) i **Poziom B** (pomocnik z bezpiecznymi akcjami). Ten plik jest **jedynym źródłem prawdy** dla nowej sesji wdrożeniowej A→B.

---

## 0. Stan wyjściowy (co już działa — nie psuj)

### 0.1 Fazy 1–3 — ZROBIONE (sesja 2026-05-18)

| Faza | Funkcja | API / pliki |
|------|---------|-------------|
| **1** | Streaming tekstu (SSE) | `POST /api/chat/stream`, `rag_chat.chat_stream()`, `sse.py` |
| **2** | Mikrofon STT | `POST /api/stt/transcribe`, `stt_service.py`, `scripts/transcribe_file.py` |
| **3** | TTS Piper + UX głosu | `POST /api/tts/speak`, `tts_service.py`, `conversation_config.py` |

**UX głosu (ostateczny):**

- Mikrofon: **klik = start / klik = stop** (nie przytrzymywanie).
- Po 🎤: auto włączenie odtwarzania głosu + `voice_mode` w czacie.
- Filtr halucynacji STT (`stt_quality.py`) — m.in. „Amara.org” na ciszy.
- Pasek 🗣️: Zatrzymaj / Ponów; przy odpowiedzi: 🔊 Odtwórz / ⏹ Stop.
- Dyktowanie systemowe: `scripts/system-dictation.sh`.

### 0.2 Baza wiedzy — jak działa

| Źródło | `source_type` | Jak trafia |
|--------|---------------|------------|
| Przewodniki z analiz repo | `guide` / sekcje | Auto po `POST /api/analyze` + `guide_indexer` |
| Profil systemu | `system` | `POST /api/system-profile/refresh` |
| Regulamin hosta | `rules` | `host_rules.py` + refresh profilu |
| Migracja starych raportów | `guide` | `POST /api/knowledge/migrate` |

Plik: `data/knowledge.db` (SQLite). **Nie commitować** do Git.

### 0.3 Czego NIE ma (to buduje Faza A/B)

| Brak | Faza docelowa |
|------|----------------|
| Supertonic / wybór TTS | **A1** |
| Notatnik użytkownika w RAG | **A2** |
| Lepszy multi-turn w UI | **A3** |
| Alerty „pusta baza” | **A4** |
| Wykonanie poleceń z potwierdzeniem | **B1** |
| Katalog „Moje projekty” | **B2** |
| Checklisty instalacji | **B3** |
| Cron profilu systemu | **B4** |

### 0.4 Środowisko (nie zmieniać bez testu)

| Zasób | Ścieżka |
|-------|---------|
| Piper bin | `/home/zarou/.local/bin/piper` |
| Piper model (domyślny) | `/mnt/ollama/modele/piper/pl_PL-gosia-medium.onnx` |
| STT venv | `/mnt/ollama/ai-envs/audio-core/.venv/bin/python` |
| Whisper modele | `/mnt/ollama/whisper_models` |
| Regulamin | `/mnt/ollama/system-control/info wazne/*.md` |

**CUDA STT:** w subprocess często brak `libcublas` → skrypt `transcribe_file.py` **fallback na CPU**. To OK.

---

## 1. Architektura po Fazach A i B (docelowa)

```mermaid
flowchart TB
  subgraph ui [Frontend 9743]
    Chat[Rozmowa RAG + głos]
    Notes[Notatnik użytkownika A2]
    Projects[Moje projekty B2]
    Checklist[Checklisty B3]
    Actions[Wykonaj krok B1]
  end

  subgraph api [FastAPI]
    RAG[chat / chat/stream]
    STT[stt/transcribe]
    TTS[tts/speak - Piper lub Supertonic]
    UserNotes[api/user-notes - A2]
    ActionRun[api/actions/run - B1]
  end

  subgraph kb [(knowledge.db)]
    Guides[guides]
    Profile[system + rules]
    NotesChunks[user_notes - A2]
  end

  ui --> api
  api --> kb
  ActionRun --> Shell[subprocess whitelist]
```

---

## 2. Faza A — szybkie usprawnienia

### A1 — Supertonic TTS (lepszy polski głos)

**Cel:** Naturalniejsza mowa niż Piper; offline; język `pl`.

**Referencje:**

- https://github.com/supertone-inc/supertonic
- https://github.com/supertone-inc/supertonic-py
- `pip install supertonic` lub `supertonic serve` (port np. 7788)

**Zasada regulaminu:** osobne venv, **nie** w `repo-story/.venv`:

```text
/mnt/ollama/ai-envs/tts-supertonic/.venv
```

**Projekt techniczny:**

1. Utwórz venv na `/mnt/ollama/ai-envs/tts-supertonic`, zainstaluj `supertonic` (+ zależności ONNX).
2. Pobierz modele (HF: `Supertone/supertonic-3`) do `/mnt/ollama/modele/supertonic/` (Git LFS).
3. Rozszerz `backend/app/tts_service.py`:
   - `TTS_BACKEND=piper|supertonic` (env).
   - Dla `supertonic`: subprocess lub HTTP do lokalnego `supertonic serve`.
4. `config.py`: `SUPERTONIC_URL`, `SUPERTONIC_LANG=pl`, `TTS_BACKEND`.
5. UI: dropdown „Głos: Piper / Supertonic” (opcjonalnie) lub tylko env.

**Weryfikacja A1:**

| # | Test | Oczekiwany wynik |
|---|------|------------------|
| A1.1 | CLI: synteza jednego zdania PL | Plik WAV/odsłuch OK |
| A1.2 | `POST /api/tts/speak` z backend=supertonic | HTTP 200, WAV |
| A1.3 | UI checkbox głosu | Słyszalna poprawa jakości vs Piper |

**Kryterium akceptacji:** użytkownik słyszy wyraźnie naturalniejszą polszczyznę; fallback na Piper przy błędzie.

---

### A2 — Notatnik użytkownika w RAG

**Cel:** Własne notatki („moje ustawienia NoiseTorch”, „ścieżki projektów”) indeksowane i cytowane w czacie.

**Schemat SQLite** (rozszerzenie `knowledge_store.py`):

```sql
CREATE TABLE IF NOT EXISTS user_notes (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tags TEXT,
  created_at REAL,
  updated_at REAL
);
```

Chunki: `source_type='user_note'`, `guide_id=NULL`, sekcja = tytuł.

**API (nowe):**

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| GET | `/api/user-notes` | Lista notatek |
| POST | `/api/user-notes` | Utwórz `{title, body, tags?}` |
| PUT | `/api/user-notes/{id}` | Edycja |
| DELETE | `/api/user-notes/{id}` | Usuń |
| POST | `/api/user-notes/reindex` | Przebuduj embeddingi |

**Frontend:** zakładka lub panel w **Rozmowa** / **Diagnostyka**: prosty edytor + lista.

**Indexer:** wykorzystaj `GuideIndexer._add()` wzorzec z `guide_id=None`.

**Weryfikacja A2:**

| # | Test | Oczekiwany wynik |
|---|------|------------------|
| A2.1 | Dodaj notatkę z unikalną frazą | HTTP 201 |
| A2.2 | `GET /api/knowledge/stats` | Więcej chunków |
| A2.3 | Czat: zapytaj o frazę z notatki | Cytowanie `user_note` |

---

### A3 — Lepszy multi-turn w UI

**Cel:** Użytkownik widzi historię sesji; Bielik pamięta poprzednie tury (już częściowo w `rag_chat` przez `CHAT_HISTORY_LIMIT`).

**Backend (już jest):** `get_chat_history(session_id)` + `voice_mode` w `ChatRequest`.

**Do zrobienia w UI:**

1. Nie czyść `#chat-messages` między pytaniami w tej samej sesji (dziś już tak — utrzymać).
2. Wyświetl `session_id` skrócony w Diagnostyce (opcjonalnie).
3. Przycisk **„Nowa rozmowa”** → nowy `session_id`.
4. Parametr `voice_mode` synchronizowany z checkboxem (już jest).

**Weryfikacja A3:**

| # | Test | Oczekiwany wynik |
|---|------|------------------|
| A3.1 | Dwa pytania w jednej sesji | Drugie nawiązuje do pierwszego |
| A3.2 | „Nowa rozmowa” | Brak kontekstu z poprzedniej |

---

### A4 — Alerty i onboarding bazy

**Cel:** Gdy baza pusta — jasny komunikat zamiast ogólnych odpowiedzi.

**Implementacja:**

1. `GET /api/knowledge/stats` — już zwraca `guides`, `chunks`.
2. W `app.js` przy wejściu w **Rozmowa**:
   - jeśli `chunks < 5` → banner: „Wygeneruj przewodnik (zakładka Nowy) lub uruchom migrację / refresh profilu”.
3. Linki przycisków: wywołaj `POST /api/knowledge/migrate`, `POST /api/system-profile/refresh`.

**Weryfikacja A4:** pusta baza → widoczny banner z instrukcją PL.

---

### Sprint A — kolejność commitów

1. [ ] A2 notatnik (największa wartość dla „pomocnika”)
2. [ ] A4 alerty (mały diff)
3. [ ] A3 UI sesji (mały diff)
4. [ ] A1 Supertonic (osobny venv + test jakości)

Tag po A: `v4.4.0-assistant-a`

---

## 3. Faza B — pomocnik z bezpiecznymi akcjami

### B1 — „Wykonaj krok” z potwierdzeniem (NAJWAŻNIEJSZE)

**Cel:** Asystent proponuje komendy; użytkownik **klika aby wykonać** — bez pełnego autonomicznego agenta.

**Zasady bezpieczeństwa (OBOWIĄZKOWE):**

1. **Whitelist** komend — tylko wzorce z listy (np. `apt-cache`, `apt install`, `systemctl --user`, `ls`, `cat`, `pw-cli`, `ollama list`).
2. **Bez** `sudo` w automatycznym wykonaniu (chyba że użytkownik wklei ręcznie).
3. **Bez** `rm`, `mkfs`, `dd`, przekierowania `> /etc/`.
4. Timeout subprocess np. 60 s.
5. Log do `logs/actions.log` (ścieżka w `config.py`).

**Format odpowiedzi LLM (opcjonalna struktura):**

W `conversation_config.py` dodać instrukcję: komendy w blokach:

```markdown
```run
apt install noisetorch
```
```

**Backend:**

- `backend/app/action_runner.py` — `validate_command(cmd) -> bool`, `run_command(cmd) -> {stdout, stderr, exit_code}`.
- `POST /api/actions/run` body: `{ "command": "...", "confirmed": true }`.
- Jeśli `confirmed` false → zwróć tylko analizę ryzyka (słowa kluczowe).

**Frontend:**

- Parser odpowiedzi: wykryj bloki ```run ... ```.
- Przycisk **„Wykonaj”** przy każdym bloku.
- Modal: „Czy na pewno? [Tak] [Nie]”.
- Wynik w `<pre>` pod wiadomością.

**Weryfikacja B1:**

| # | Test | Oczekiwany wynik |
|---|------|------------------|
| B1.1 | `ollama list` z whitelist | exit 0, stdout w UI |
| B1.2 | `rm -rf /` | Odrzucone przed wykonaniem |
| B1.3 | Komenda bez confirm | HTTP 400 |

---

### B2 — Katalog „Moje projekty”

**Cel:** Lista przeanalizowanych repo + link do przewodnika + status notatki.

**Dane:** tabela `analyzed_repos` lub widok na `reports/*.json` + `knowledge.db` guides.

**API:**

- `GET /api/projects` → `[{slug, title, url, report_id, analyzed_at, has_guide_in_kb}]`

**Frontend:** zakładka **Moje projekty** lub sekcja w Historii.

**Weryfikacja B2:** po analizie NoiseTorch wpis widoczny na liście.

---

### B3 — Checklisty instalacji z przewodnika

**Cel:** Z `EducationPack` / sekcji `install_steps` → interaktywna lista z odhaczaniem (localStorage).

**Implementacja:**

1. Endpoint lub embed w istniejącym `GET /api/reports/{id}` — pole `install_checklist: [{id, text, done?}]`.
2. UI w widoku przewodnika: checkboxy; stan w `localStorage` klucz `checklist-{report_id}`.

**Weryfikacja B3:** odhaczenie przetrwa odświeżenie strony.

---

### B4 — Cron profilu systemu

**Cel:** Profil i RAG zawsze aktualne.

**Już jest:** `docs/system-profile-cron.md`.

**Do zrobienia:**

1. Zweryfikuj przykładowy wpis cron w docs.
2. Skrypt `scripts/refresh-profile-cron.sh` wywołujący curl `POST /api/system-profile/refresh` (serwer musi działać lub CLI Python).

**Weryfikacja B4:** po cron `GET /api/knowledge/stats` — świeży `collected_at` w profilu.

---

### Sprint B — kolejność commitów

1. [ ] B1 action runner + UI (rdzeń „pomocnika”)
2. [ ] B2 katalog projektów
3. [ ] B3 checklisty
4. [ ] B4 cron helper

Tag po B: `v4.5.0-assistant-b`

**Zależność:** B1 po stabilnym A2 (notatki) — opcjonalnie równolegle.

---

## 4. Mapa plików (stan po v4.3 — orientacja)

```text
repo-story/
├── backend/app/
│   ├── main.py
│   ├── rag_chat.py          # chat, chat_stream, prepare_context
│   ├── sse.py
│   ├── stt_service.py
│   ├── stt_quality.py
│   ├── tts_service.py
│   ├── conversation_config.py
│   ├── knowledge_store.py   # rozszerzyć: user_notes (A2)
│   ├── host_rules.py
│   └── action_runner.py     # DO UTWORZENIA (B1)
├── scripts/
│   ├── transcribe_file.py
│   ├── system-dictation.sh
│   └── refresh-profile-cron.sh  # DO UTWORZENIA (B4)
├── tests/
│   ├── test_rag_chat_stream.py
│   ├── test_stt_*.py
│   └── test_tts_service.py
├── docs/
│   ├── AGENT_IMPLEMENTATION_LIVE_ASSISTANT.md
│   └── AGENT_IMPLEMENTATION_PHASE_AB.md   # ten plik
└── data/knowledge.db          # runtime, nie w git
```

---

## 5. Smoke test (każda sesja agenta)

```bash
cd /mnt/ollama/projekty/repo-story
git fetch origin && git status -sb && git log origin/main -3 --oneline
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

```bash
# Terminal 2
curl -s http://127.0.0.1:9743/api/health | python3 -m json.tool
curl -s http://127.0.0.1:9743/api/knowledge/stats | python3 -m json.tool
curl -N -X POST http://127.0.0.1:9743/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"Test","voice_mode":true}' | head -20
curl -s -X POST http://127.0.0.1:9743/api/tts/speak \
  -H 'Content-Type: application/json' \
  -d '{"text":"Test głosu."}' -o /tmp/tts.wav && file /tmp/tts.wav
```

UI: http://127.0.0.1:9743/ → Rozmowa → 🎤 → checkbox głosu → 🔊 Stop.

---

## 6. GitHub po każdym sprincie

```bash
cd /mnt/ollama/projekty/repo-story
git add -A   # respektuje .gitignore
GIT_AUTHOR_NAME="Noacodenoobe" GIT_AUTHOR_EMAIL="Noacodenoobe@users.noreply.github.com" \
GIT_COMMITTER_NAME="Noacodenoobe" GIT_COMMITTER_EMAIL="Noacodenoobe@users.noreply.github.com" \
git commit -m "feat(assistant): opis zmiany"
git push origin main
git tag -a v4.4.0-assistant-a -m "Phase A: ..."
git push origin v4.4.0-assistant-a
```

**Nie commitować:** `data/knowledge.db`, `reports/`, `.env`, logów.

---

## 7. Czego agent NIE powinien robić

- Modyfikować `repo-analyzer` (9742) bez polecenia.
- `pip install torch` w `repo-story/.venv`.
- Autonomiczne `sudo` lub pełny shell bez whitelist (B1).
- Usuwać działające endpointy v4.3.
- Wdrażać Poziom C (agent 24/7) przed ukończeniem A i B.

---

## 8. Prompt startowy — nowa sesja (Fazy A i B)

```text
Wdrażasz Repo Opowieść — Fazy A i B (pomocnik osobisty).

Przeczytaj OBOWIĄZKOWO (w tej kolejności):
1. /mnt/ollama/projekty/repo-story/docs/AGENT_IMPLEMENTATION_LIVE_ASSISTANT.md (kontekst v4.3)
2. /mnt/ollama/projekty/repo-story/docs/AGENT_IMPLEMENTATION_PHASE_AB.md (zadania A i B)
3. /mnt/ollama/system-control/info wazne/regulamin_linux_ai.md

Na start:
  cd /mnt/ollama/projekty/repo-story
  git fetch origin && git status -sb && git log origin/main -3 --oneline

GitHub: https://github.com/Noacodenoobe/repo-story
Bazowy tag: v4.3.0-voice-assistant
Port: 9743

Kolejność prac (zatwierdzona przez użytkownika):
  Sprint A: A2 notatnik → A4 alerty → A3 UI sesji → A1 Supertonic
  Sprint B: B1 wykonaj krok (whitelist) → B2 projekty → B3 checklisty → B4 cron

Po każdym sprincie: testy + commit + push (sekcja 6 dokumentu PHASE_AB).
Nie ruszaj repo-analyzer (9742).
Pisz kod i komentarze w kodzie po angielsku; komunikaty UI po polsku.
```

---

*Koniec dokumentu Faz A i B.*

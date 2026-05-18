# Repo Opowieść

> Wklej link do projektu na GitHub — dostaniesz **interaktywną prezentację po polsku**, bez żargonu informatycznego.

Wersja edukacyjna narzędzia [Repo Analyzer](https://github.com/Noacodenoobe/repo-analyzer). Oryginał (raport techniczny) działa na porcie **9742**; ta aplikacja na **9743**.

## Szybki start

```bash
cd /mnt/ollama/projekty/repo-story
./setup.sh
ollama pull SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M
./run.sh
```

Otwórz: **http://127.0.0.1:9743**

## Co otrzymujesz (v4.3)

- **Przewodnik interaktywny** — przegląd, zastosowania, przepływ, instrukcja, wykresy, mapa połączeń
- **Opowieść i quiz** — krótkie podsumowanie po polsku
- **Rozmowa (RAG)** — czat z bazą SQLite (`data/knowledge.db`): przewodniki, profil systemu, regulamin hosta
- **Asystent głosowy** — mikrofon (toggle), streaming odpowiedzi, TTS (Piper), sterowanie odtwarzaniem
- **Diagnostyka** — profil sprzętu/narzędzi, statystyki bazy wiedzy
- **Eksport** — Markdown i HTML offline
- **Dyktowanie systemowe** — `scripts/system-dictation.sh` (skrót klawiszowy → STT → wklejenie tekstu)

Szczegóły wdrożenia: `docs/AGENT_IMPLEMENTATION_LIVE_ASSISTANT.md` (Fazy 1–3, ukończone)  
Kolejne kroki (A i B): `docs/AGENT_IMPLEMENTATION_PHASE_AB.md`

### Baza wiedzy — co robi, czego nie robi

| Tak | Nie (jeszcze) |
|-----|----------------|
| Indeksuje wygenerowane przewodniki po analizie repo | Nie wykonuje poleceń w systemie (brak agenta-akcji) |
| Profil sprzętu + zasady z `/mnt/ollama/system-control` | Nie edytuje plików ani nie uruchamia skryptów za Ciebie |
| Wyszukiwanie semantyczne (embeddings) + odpowiedź Bielik | Nie jest pełnym „Jarvisem” 24/7 w tle |
| Migracja starych raportów: `POST /api/knowledge/migrate` | |

GitHub: https://github.com/Noacodenoobe/repo-story

## Konfiguracja

| Zmienna | Domyślnie |
|---------|-----------|
| `API_PORT` | `9743` |
| `MODEL_POLISH` | `SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M` |

Prompty edukacyjne: `backend/prompts/zero_tech/`

## Licencja

MIT

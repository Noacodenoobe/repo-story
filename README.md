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

## Co otrzymujesz (v4)

- **Przewodnik interaktywny** — przegląd, zastosowania, przepływ, instrukcja, wykresy, mapa połączeń
- **Opowieść i quiz** — krótkie podsumowanie po polsku
- **Rozmowa (RAG)** — czat z bazą zapisanych przewodników i profilem Twojego systemu
- **Diagnostyka** — profil sprzętu/narzędzi, indeks wiedzy SQLite
- **Eksport** — Markdown i HTML offline
- **Szczegóły techniczne** — opcjonalnie (wolniejsze, wymaga embeddingów)

Plan rozwoju (asystent głosowy): `docs/AGENT_IMPLEMENTATION_LIVE_ASSISTANT.md`

## Konfiguracja

| Zmienna | Domyślnie |
|---------|-----------|
| `API_PORT` | `9743` |
| `MODEL_POLISH` | `SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M` |

Prompty edukacyjne: `backend/prompts/zero_tech/`

## Licencja

MIT

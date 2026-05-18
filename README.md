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

## Co otrzymujesz

- **Slajdy** — jeden pomysł na ekran, analogie, „co to dla Ciebie”
- **Quiz** — 2–3 proste pytania na koniec
- **Słowniczek** — trudne słowa po kliknięciu
- **Szczegóły techniczne** — opcjonalnie, w zwiniętej sekcji

## Konfiguracja

| Zmienna | Domyślnie |
|---------|-----------|
| `API_PORT` | `9743` |
| `MODEL_POLISH` | `SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M` |

Prompty edukacyjne: `backend/prompts/zero_tech/`

## Licencja

MIT

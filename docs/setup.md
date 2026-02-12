# Setup local

## Pré-requis

- Python 3.11+ recommandé (ce repo fonctionne déjà avec `python3` en 3.11).

## Venv

Création:
- `python3 -m venv .venv`

Activation (macOS / Linux):
- `source .venv/bin/activate`

Vérification:
- `python --version`

## Dépendances

Installation:
- `python -m pip install -r requirements.txt`

## Variables d'environnement (.env)

Crée un fichier `.env` à la racine et renseigne au minimum:

- `TAVILY_API_KEY=...`
- `ALPACA_API_KEY=...`
- `ALPACA_API_SECRET=...`
- `ALPACA_PAPER=true`
- optionnel: `XAI_API_KEY=...`

Les scripts de smoke test chargent `.env` depuis la racine du repo.

## Smoke tests

- Alpaca (read-only): `python scripts/smoke/alpaca_api_test.py`
- xAI/Grok: `python scripts/smoke/grok_api_test.py`
- Conclusion de marché legacy (web Tavily + x_search Grok): `python grok_tools_test.py` (prompts dans `prompts/`)

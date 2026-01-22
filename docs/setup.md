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

1. Copie le template: `.env.example` → `.env`
2. Renseigne tes clés (ne commit jamais `.env`).

Les scripts de smoke test chargent `.env` depuis la racine du repo.

## Smoke tests

- Alpaca (read-only): `python alpaca_api_test.py`
- xAI/Grok: `python grok_api_test.py`
- Conclusion de marché (web_search + x_search): `python grok_tools_test.py` (prompts dans `prompts/`)

# Trading Agent (paper trading)

Ce dépôt est le point de départ d'un agent de trading piloté par un LLM (paper trading d'abord).

## Démarrage rapide

1. Crée et active le venv:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
2. Installe les dépendances:
   - `python -m pip install -r requirements.txt`
3. Ajoute tes clés:
   - copie `.env.example` → `.env` puis remplis les valeurs
4. Smoke tests:
   - `python alpaca_api_test.py`
   - `python grok_api_test.py`

## Documentation

Voir `docs/README.md`.


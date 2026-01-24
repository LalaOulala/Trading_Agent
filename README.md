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
   - `python grok_tools_test.py` (conclusion de marché via `web_search` + `x_search`, prompts dans `prompts/`)
5. Agent "Reflex Trader" (questions prix + conclusion, outputs dans `reflex_trader/`):
   - (pré-requis: avoir un report récent dans `responses/`, ex via `python grok_tools_test.py`)
   - `python reflex_trader_agent.py`
6. Agent "Grok Chef" (décision + exécution Alpaca, outputs dans `grok_chef/`):
   - (pré-requis: avoir un report récent dans `responses/` + une sortie trader dans `reflex_trader/`)
   - dry-run (recommandé): `python grok_chef_agent.py`
   - paper trading (soumet des ordres): `python grok_chef_agent.py --execute`
7. Workflow complet (recherche -> trader -> chef):
   - dry-run: `python run.py`
   - paper trading: `python run.py --execute`

## Bugs / points à corriger (branche `test-chef-trader`)

- `ModuleNotFoundError: No module named 'pytz'` lors du fetch Market Data (import `alpaca.data`) si le venv n'a pas toutes les deps: `python -m pip install -r requirements.txt` (ou utiliser le fallback HTTP implémenté dans cette branche).
- Le trader peut demander des symboles non supportés par Alpaca Market Data (ex: `^TNX`): il faut filtrer/mapper côté prompts ou normaliser strictement côté pipeline.
- Le feed Market Data dépend du compte (`iex` vs `sip`): configurable via `ALPACA_DATA_FEED` (défaut `iex`).

## Documentation

Voir `docs/README.md`.

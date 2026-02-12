# Trading Agent

Projet de trading algorithmique piloté par agents IA, avec deux couches:

- `V1` (legacy): scripts historiques (`run.py`, `grok_tools_test.py`, `reflex_trader_agent.py`).
- `V2` (recommandée): pipeline segmentée orientée objets (`run_v2.py`, `trading_pipeline/`).

## Arborescence (propre)

```text
trading_pipeline/   # coeur applicatif V2 (collectors, agents, finance, execution, workflow)
scripts/            # utilitaires (smoke tests, benchmark data)
tests/              # tests unitaires / pipeline
docs/               # documentation (dont tutoriel détaillé)
prompts/            # prompts legacy
run_v2.py           # point d’entrée V2
run.py              # point d’entrée legacy
```

## Démarrage rapide

1. Créer le venv:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
2. Installer les dépendances:
   - `python -m pip install -r requirements.txt`
3. Créer un `.env` local avec au minimum:
   - `TAVILY_API_KEY=...`
   - `ALPACA_API_KEY=...`
   - `ALPACA_API_SECRET=...`
   - `ALPACA_PAPER=true`
   - optionnel: `XAI_API_KEY=...`
4. Lancer les tests:
   - `.venv/bin/python -m unittest discover -s tests -v`

## Commandes utiles

- Smoke tests API:
  - `.venv/bin/python scripts/smoke/alpaca_api_test.py`
  - `.venv/bin/python scripts/smoke/grok_api_test.py`
- Benchmark recherche web Tavily:
  - `.venv/bin/python scripts/data/tavily_search_example.py --query "S&P 500 market drivers today" --topic finance --time-range day --max-results 8 --include-answer`
- Validation branche Yahoo Finance:
  - `.venv/bin/python scripts/data/testyfinance.py`
  - `.venv/bin/python scripts/data/testyfinance_advanced.py`
- Pipeline V2:
  - `.venv/bin/python run_v2.py --query "S&P 500 market drivers today" --web-topic finance --web-time-range day --financial-provider yahoo --once`
- Interface graphique Streamlit:
  - `.venv/bin/python -m streamlit run streamlit_app.py`
  - Multi-pages:
    - `Dashboard Workflow` (run + ordres + portefeuille + timings)
    - `Reflexions Agents` (historique eurodate + ouverture run JSON)
    - `Fichiers Logs TXT/JSON` (explorateur cliquable des fichiers)

## Sorties générées

- `responses/` : rapports de recherche + exports Tavily (`responses/tavily_search/`).
- `pipeline_runs_v2/` : artefacts JSON complets du workflow V2.
- `price_history/` : CSV d'historique Yahoo Finance (scripts de validation).
- `reflex_trader/` : sorties du flux legacy trader.

## Documentation

- Index: `docs/README.md`
- Tutoriel détaillé pas-à-pas: `docs/tutorial_v2.md`
- Architecture technique V2: `docs/new_architecture.md`

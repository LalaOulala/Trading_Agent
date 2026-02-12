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

## Lancer `run_v2.py` (guide complet)

### 1) Préparer l'environnement

```bash
cd /Users/lala/CascadeProjects/trading_agent1
source .venv/bin/activate
set -a
source .env
set +a
```

Variables utiles dans `.env`:
- `TAVILY_API_KEY`: obligatoire (branche web/fresh data).
- `ALPACA_API_KEY`: obligatoire pour exécution ordres et vérification marché.
- `ALPACA_API_SECRET`: obligatoire pour exécution ordres et vérification marché.
- `ALPACA_PAPER=true`: recommandé en paper trading.

### 2) Mode simple: un seul cycle (dry-run)

```bash
.venv/bin/python run_v2.py \
  --query "S&P 500 market drivers today" \
  --financial-provider yahoo \
  --once
```

### 3) Mode exécution ordres (confirmation manuelle)

```bash
.venv/bin/python run_v2.py \
  --query "S&P 500 market drivers today" \
  --financial-provider yahoo \
  --execute-orders \
  --once
```

Le terminal affiche le résumé des ordres Alpaca et attend `yes` pour envoyer.

### 4) Mode exécution ordres (auto-accept)

```bash
.venv/bin/python run_v2.py \
  --query "S&P 500 market drivers today" \
  --financial-provider yahoo \
  --execute-orders \
  --auto-accept-orders \
  --once
```

Alias accepté: `--auto-confirm-orders`.

### 5) Mode boucle (trading continu)

Par défaut, `run_v2.py` est en boucle continue tant que tu ne mets pas `--once`.

```bash
.venv/bin/python run_v2.py \
  --query "S&P 500 market drivers today" \
  --financial-provider yahoo \
  --execute-orders \
  --auto-accept-orders \
  --interval-seconds 300 \
  --stop-if-market-closed
```

Comportement:
- lance un cycle complet;
- dort `interval-seconds`;
- recommence jusqu'à `Ctrl+C`;
- si `--stop-if-market-closed` est actif et que le marché est fermé, affiche:
  - `Le marché est fermé, il réouvre dans ...`
  - puis quitte proprement.

### 6) Paramètres CLI principaux

- `--query`: prompt de recherche macro/market.
- `--financial-provider {yahoo|placeholder}`: source données financières.
- `--financial-mock-file`: JSON mock utilisé si provider `placeholder`.
- `--execute-orders`: active l'envoi d'ordres Alpaca (sinon simulation).
- `--auto-accept-orders`: bypass de la confirmation interactive (`yes`).
- `--order-qty`: quantité unitaire par ordre (défaut `1.0`).
- `--interval-seconds`: pause entre cycles en mode boucle (défaut `300`).
- `--once`: force un seul cycle puis sortie.
- `--stop-if-market-closed`: check Alpaca clock avant cycle; quitte si marché fermé.
- `--web-topic`, `--web-time-range`, `--web-max-results`, `--web-include-domains`, `--web-exclude-domains`: réglages de la collecte Tavily.

### 7) Artefacts et logs

Chaque cycle écrit un artefact JSON dans:
- `pipeline_runs_v2/`

Le résumé terminal affiche notamment:
- l'action (`LONG`/`SHORT`/`HOLD`);
- les symboles ciblés;
- le statut broker (`submitted`, `skipped`, `error`);
- le chemin de l'artefact.

### 8) Dépannage: erreur short Alpaca

Symptôme typique:
- `APIError: {"code":40310000,"message":"account is not allowed to short"}`

Diagnostic du compte actif:

```bash
curl -s https://paper-api.alpaca.markets/v2/account \
  -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_API_SECRET" | jq '{account_number,equity,multiplier,shorting_enabled}'
```

Interprétation:
- si `shorting_enabled=false` ou `multiplier="1"`, le short est interdit.
- pour shorter, viser `equity >= 2000`, `multiplier="2"`, `shorting_enabled=true`.

Vérifier aussi que l'actif est shortable:

```bash
curl -s https://paper-api.alpaca.markets/v2/assets/SPY \
  -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_API_SECRET" | jq '{symbol,tradable,shortable,easy_to_borrow}'
```

Si `shorting_enabled` est `false`:
- créer un paper account avec fonds >= 2000;
- générer de nouvelles clés API pour ce compte;
- mettre à jour `.env` (`ALPACA_API_KEY`, `ALPACA_API_SECRET`);
- redémarrer le process `run_v2.py` (important si ancien process lancé avec d'anciennes clés).

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

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
6. Workflow complet (recherche -> trader):
   - `python run.py`

## Workflow détaille (exemple réel)

Exemple exécuté le `2026-02-12` sur `master`:

```bash
.venv/bin/python run.py
```

Sortie CLI observée:

```text
[Research] running…
[Research] done -> responses/2026-02-12_10-16-09/report.txt | Titre : Conclusion de marché actions (périmètre US / S&P 500) — 2026-02-12 10:16 CET
[Trader] running…
[Trader] done -> reflex_trader/2026-02-12_10-16-30.txt | portfolio=True | requested symbols: SPY, CSCO, QQQ, XLF

=== Outputs ===
- Research report: responses/2026-02-12_10-16-09/report.txt
- Trader report: reflex_trader/2026-02-12_10-16-30.txt
```

### Étape 1: Recherche de marché (`grok_tools_test.py`)

Entrées:
- Prompt système: `prompts/redaction.txt`
- Prompt utilisateur (format de sortie): `prompts/presentation.txt`

Sorties du run:
- Rapport principal: `responses/2026-02-12_10-16-09/report.txt`
- Log technique: `responses/2026-02-12_10-16-09/debug.txt`

Extrait du rapport généré:

```text
Synthèse en une minute : Aujourd’hui, le marché a été principalement influencé par le rapport emplois de janvier (NFP) plus fort que prévu, puis par les futures en hausse en pré-market.
...
Le point à surveiller maintenant est le CPI vendredi (inflation clé influençant la politique monétaire).
```

Extrait du debug:

```text
Model: grok-4-1-fast
Tools used (billed): {'SERVER_SIDE_TOOL_X_SEARCH': 1, 'SERVER_SIDE_TOOL_WEB_SEARCH': 3}
```

Tool calls observés sur ce run:
- `web_search`: "S&P 500 market drivers today latest news last 24 hours"
- `web_search`: "US stock futures premarket drivers February 12 2026 OR latest"
- `web_search`: "earnings reports surprises S&P 500 companies last 24 hours"
- `x_semantic_search`: "S&P 500 futures macro drivers earnings"

### Étape 2: Réflexion trader (`reflex_trader_agent.py`)

Entrées injectées dans ce run:
- Reports utilisés: `['responses/2026-02-12_10-16-09/report.txt']`
- Snapshot portefeuille Alpaca: `Portfolio available: True`
- Analyse derniers jours: placeholder (`TODO`)

Sortie du run:
- `reflex_trader/2026-02-12_10-16-30.txt`

Extrait JSON produit:

```json
{
  "requested_market_data": [
    {"symbol": "SPY", "fields": ["last_trade_price", "1d_change_pct", "5d_change_pct"]},
    {"symbol": "CSCO", "fields": ["last_trade_price", "1d_change_pct", "5d_change_pct"]},
    {"symbol": "QQQ", "fields": ["last_trade_price", "1d_change_pct", "5d_change_pct"]},
    {"symbol": "XLF", "fields": ["last_trade_price", "1d_change_pct", "5d_change_pct"]}
  ],
  "questions": [
    "NFP dope-t-il vraiment SPY/QQQ malgré yields up ?",
    "Cisco slide contamine-t-il tech plus largement ?",
    "Financials (XLF) outperform-ils déjà ?"
  ]
}
```

### Lecture rapide des artefacts

- `responses/<run>/report.txt`: conclusion de marché lisible humain.
- `responses/<run>/debug.txt`: traçabilité LLM (modèle, usage tokens, tool calls, citations).
- `reflex_trader/<run>.txt`: synthèse trader structurée + liste des données de prix à récupérer.

En pratique, `run.py` orchestre les 2 scripts, vérifie que les fichiers existent et sont non vides, puis affiche un résumé court (titre report + symboles demandés).

## Documentation

Voir `docs/README.md`.

# Discord Bot (Render + Flask keep-alive)

Ce dossier contient un bot Discord prêt pour un déploiement continu.

## Fonctionnalités

- Envoi automatique d'un rapport toutes les heures (configurable).
- Commandes slash:
  - `/ping`
  - `/status` (envoi immédiat du rapport).
- Serveur Flask `keep_alive` pour endpoint health (`/`) côté Render.
- Rapport basé sur:
  - historique des ordres (`runtime_history/run_v2_trade_events.jsonl`)
  - portefeuille Alpaca (si clés présentes)
  - estimation coûts API (Tavily + xAI) depuis artefacts locaux.

## Lancement local

```bash
cd /Users/lala/CascadeProjects/trading_agent1
source .venv/bin/activate
python -m bot
```

## Variables `.env` minimales

```env
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=123456789012345678
```

## Variables optionnelles

- `BOT_REPORT_INTERVAL_MINUTES` (défaut: `60`)
- `BOT_TIMEZONE` (défaut: `Europe/Paris`)
- `BOT_ARTIFACTS_DIR` (défaut: `pipeline_runs_v2`)
- `BOT_RESPONSES_DIR` (défaut: `responses`)
- `BOT_RUNTIME_HISTORY_FILE` (défaut: `runtime_history/run_v2_terminal_events.jsonl`)
- `BOT_TRADE_HISTORY_FILE` (défaut: `runtime_history/run_v2_trade_events.jsonl`)
- `BOT_ENABLE_KEEP_ALIVE` (défaut: `true`)
- `KEEP_ALIVE_HOST` (défaut: `0.0.0.0`)
- `KEEP_ALIVE_PORT` (défaut: `PORT` ou `8000`)
- `BOT_MAX_POSITIONS_IN_REPORT` (défaut: `8`)

Le bot réutilise aussi les clés Alpaca existantes (`ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_PAPER`) pour le snapshot portefeuille.

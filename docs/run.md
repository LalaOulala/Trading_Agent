# run.py (workflow complet)

`run.py` orchestre le workflow de bout en bout:

1) `grok_tools_test.py` (recherche) → `responses/*/report.txt`  
2) `reflex_trader_agent.py` (trader) → `reflex_trader/*.txt`

## Exécution

- Run continu par défaut (toutes les 5 minutes):
  - `python run.py --interval-seconds 300`
- Run unique (sans boucle):
  - `python run.py --once`

## Options utiles

- Réutiliser des outputs existants:
  - `python run.py --skip-research` (utilise le dernier `responses/*/report.txt`)
  - `python run.py --skip-trader` (utilise le dernier `reflex_trader/*.txt`)
- Forcer des chemins:
  - `python run.py --research-report responses/<run>/report.txt --trader-report reflex_trader/<run>.txt`
- Debug:
  - `python run.py --verbose`
- Run unique + debug:
  - `python run.py --once --verbose`
- Boucle continue:
  - `python run.py --interval-seconds 600` (exemple 10 minutes)

Arrêt:
- `Ctrl+C` stoppe proprement la boucle.

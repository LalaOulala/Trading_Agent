# run.py (workflow complet)

`run.py` orchestre le workflow de bout en bout:

1) `grok_tools_test.py` (recherche) → `responses/*/report.txt`  
2) `reflex_trader_agent.py` (trader) → `reflex_trader/*.txt`  
3) `grok_chef_agent.py` (chef) → `grok_chef/*.txt` (+ ordres optionnels)

## Exécution

- Dry-run (recommandé):
  - `python run.py`
- Soumettre des ordres (paper):
  - `python run.py --execute`

## Options utiles

- Réutiliser des outputs existants:
  - `python run.py --skip-research` (utilise le dernier `responses/*/report.txt`)
  - `python run.py --skip-trader` (utilise le dernier `reflex_trader/*.txt`)
- Forcer des chemins:
  - `python run.py --research-report responses/<run>/report.txt --trader-report reflex_trader/<run>.txt`
- Affichage:
  - `python run.py --verbose` (affiche les commandes exécutées)

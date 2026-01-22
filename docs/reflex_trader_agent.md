# Reflex Trader Agent

Ce module démarre l’implémentation d’un agent “trader” qui:

- prend en entrée les **derniers reports** produits par `grok_tools_test.py` (`responses/*/report.txt`), un **snapshot portefeuille** (Alpaca), et une **analyse derniers jours** (placeholder ou fichier),
- produit en sortie une **liste de données de marché (prix) à récupérer** sur certains actifs, plus une **conclusion courte**,
- sauvegarde chaque run dans `reflex_trader/YYYY-MM-DD_HH-MM-SS.txt`.

## Fichiers

- Script: `reflex_trader_agent.py`
- Prompts:
  - `prompts/reflex_trader_redaction.txt` (rôle + méthode)
  - `prompts/reflex_trader_presentation.txt` (format JSON strict)

## Exécution

Pré-requis:
- `XAI_API_KEY` doit être défini (dans `.env` ou dans ton shell).
- Pour inclure le portefeuille: clés Alpaca (`ALPACA_API_KEY`, `ALPACA_API_SECRET`) + `ALPACA_PAPER=true|false`.
- Univers actuel: **actions US uniquement**.

Commandes:
- Run simple (lit le dernier report, demande des prix, conclut):
  - `python reflex_trader_agent.py`
- Inclure plusieurs reports:
  - `python reflex_trader_agent.py --reports-count 3`
- Ajouter une analyse “derniers jours” depuis un fichier:
  - `python reflex_trader_agent.py --analysis-file path/to/analysis.txt`
- Optionnel: récupérer automatiquement les derniers prix via Alpaca Market Data:
  - `python reflex_trader_agent.py --fetch-prices`

## Sorties

- Chaque run écrit un fichier:
  - `reflex_trader/YYYY-MM-DD_HH-MM-SS.txt`
- Le dossier `reflex_trader/` est ignoré par git (outputs générés).

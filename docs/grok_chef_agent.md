# Grok Chef Agent (exécution Alpaca)

Ce module implémente un agent “chef” qui:

- prend en entrée un **report recherche** (`responses/*/report.txt`) + la sortie de l’agent trader (`reflex_trader/*.txt` ou un JSON direct),
- récupère les **prix** (latest trade) des symboles demandés via **Alpaca Market Data**,
- demande à Grok un **plan d’ordres** (JSON strict),
- valide ce plan (garde-fous) puis **soumet** (optionnellement) les ordres via **Alpaca Trading API**.

## Fichiers

- Script: `grok_chef_agent.py`
- Prompts:
  - `prompts/grok_chef_redaction.txt`
  - `prompts/grok_chef_presentation.txt`

## Exécution

Pré-requis:
- `XAI_API_KEY` doit être défini (dans `.env` ou ton shell).
- Clés Alpaca: `ALPACA_API_KEY`, `ALPACA_API_SECRET`.
- `ALPACA_PAPER=true|false` (défaut: `true`).

Commandes:
- Dry-run (recommandé):
  - `python grok_chef_agent.py`
- Soumettre des ordres (paper):
  - `python grok_chef_agent.py --execute`
- Spécifier explicitement les inputs:
  - `python grok_chef_agent.py --research-report responses/<run>/report.txt --trader-report reflex_trader/<run>.txt`
- Exécution live (désactivée par défaut):
  - nécessite `ALPACA_PAPER=false` + `--allow-live --execute`

## Sorties

- Chaque run écrit un fichier:
  - `grok_chef/YYYY-MM-DD_HH-MM-SS.txt`


# grok_tools_test.py (conclusion de marché)

Ce script génère une **conclusion de marché actions** (par défaut **US / S&P 500**) avec:

- **Web**: recherche collectée via **Tavily** côté script (injectée dans le prompt),
- **Social**: tool serveur Grok **`x_search`** uniquement (signaux X/Twitter).

## Prompts

Les prompts sont externalisés dans le dossier `prompts/` :

- `prompts/redaction.txt` : rôle + méthode + contraintes de recherche.
- `prompts/presentation.txt` : format de sortie attendu (structure du rapport).

## Exécution

Pré-requis :

- `XAI_API_KEY` doit être défini (dans `.env` ou dans ton shell),
- `TAVILY_API_KEY` doit être défini (dans `.env` ou dans ton shell).

Commande :

- `python grok_tools_test.py`

## Sorties

Chaque run crée un sous-dossier horodaté :

- `responses/YYYY-MM-DD_HH-MM-SS/report.txt` : rapport final (format demandé).
- `responses/YYYY-MM-DD_HH-MM-SS/debug.txt` : métadonnées (usage, tool calls, citations, prompts utilisés).

Note : `responses/` est ignoré par git (outputs générés).

Ces `report.txt` peuvent ensuite servir d’entrée à l’agent `reflex_trader_agent.py`.

## Contrôle des coûts

Dans `grok_tools_test.py`, les garde-fous principaux sont :

- `MAX_TURNS` : nombre maximum de tours agentiques (ne correspond pas forcément au nombre exact de tool calls).
- `MAX_TOKENS` : limite de tokens pour la réponse.
- `TAVILY_MAX_RESULTS` : nombre max de résultats web injectés.
- `X_LOOKBACK_HOURS` : fenêtre temporelle pour `x_search`.

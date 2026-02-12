# Architecture V2 (segmentée OO)

La V2 introduit une séparation explicite des responsabilités:

1. **Fresh Data Branch**
   - Web: collecteur Tavily.
   - Social: collecteur X placeholder (cache JSON ou vide).
2. **IA Branch 1**
   - `PreAnalysisAgent`: premier traitement des signaux frais.
3. **IA Branch 2**
   - `FocusTraderAgent`: filtre et shortlist des symboles à creuser.
4. **Financial Data Branch**
   - `YahooFinancePoolProvider`: branche finance dédiée (connectée au pool Yahoo Finance).
   - `YahooPlaceholderProvider`: fallback mock pour tests hors réseau.
5. **IA Branch 3**
   - `FinalTraderAgent`: décision finale (LONG/SHORT/HOLD) + ordres proposés.
6. **Execution Branch**
   - `AlpacaTradeExecutor`: envoi d’ordres Alpaca (dry-run par défaut).

## Arborescence

```text
trading_pipeline/
  collectors/
  agents/
  financial/
  execution/
  workflow/
run_v2.py
```

## Exécution

```bash
python run_v2.py \
  --query "S&P 500 market drivers today" \
  --web-topic finance \
  --web-time-range day \
  --web-max-results 8 \
  --financial-provider yahoo
```

Le script écrit un artefact JSON complet dans `pipeline_runs_v2/`.

## Notes

- L’architecture V2 est ajoutée sans casser les scripts historiques (`run.py`, `grok_tools_test.py`, `reflex_trader_agent.py`).
- Le provider Yahoo réel peut être remplacé par le placeholder via `--financial-provider placeholder --financial-mock-file ...`.

# Tavily Search (exemple)

Ce document décrit le script `scripts/data/tavily_search_example.py`, utilisé pour évaluer/régler la pertinence de Tavily (source web utilisée par le flux legacy et la V2).

## Pré-requis

- `TAVILY_API_KEY` défini dans `.env` ou dans le shell.
- Dépendances installées (`pip install -r requirements.txt`).

## Commande type

```bash
python scripts/data/tavily_search_example.py \
  --query "S&P 500 market drivers today" \
  --topic finance \
  --time-range day \
  --max-results 8 \
  --include-answer
```

## Ce que le script affiche

- Métadonnées de run: query, topic, profondeur, fenêtre temporelle.
- Nombre de résultats, temps de réponse, crédits consommés (si disponible).
- Liste triée des résultats (`score`, `title`, `url`).
- Ratio de résultats sur une liste de domaines "trusted" configurable.

Le script sauvegarde aussi la réponse JSON brute dans:
- `responses/tavily_search/tavily_search_<timestamp>.json` (par défaut), ou
- un chemin personnalisé avec `--out`.

## Paramètres utiles

- `--topic`: `general`, `news`, `finance`
- `--search-depth`: `basic`, `advanced`, `fast`, `ultra-fast`
- `--include-domains`: liste CSV de domaines à favoriser
- `--exclude-domains`: liste CSV de domaines à exclure
- `--trusted-domains`: domaines utilisés pour le ratio de pertinence affiché

## Objectif d'évaluation

Comparer, sur les mêmes requêtes de marché:
- qualité des sources,
- stabilité des résultats,
- latence,
- coût en crédits.

Cette étape reste séparée des workflows `run.py` / `run_v2.py` pour permettre un benchmark propre et répétable.

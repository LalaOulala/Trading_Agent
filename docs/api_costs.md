# Coûts API

## Objectif

Garder les coûts (LLM + broker + données) prévisibles, traçables et plafonnés.

## LLM

- Documenter le modèle utilisé (actuellement en dur dans les scripts).
- Mettre en place un budget (par jour / par run) dès que l'agent fera des appels récurrents.
- Réduire la fréquence des appels: cache, résumés, batching, “no-op” si signal inchangé.

## Broker / données de marché

- Utiliser des endpoints read-only pour les tests de connectivité.
- Mettre des rate limits côté client, et des backoffs.

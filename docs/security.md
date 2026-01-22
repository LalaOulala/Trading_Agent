# Sécurité

## Principes

- Paper trading par défaut (pas d'ordres live sans étape explicite).
- Secrets exclusivement via variables d'environnement (fichier `.env` local ignoré par git).
- Principe du moindre privilège: clés séparées paper/live, rotation régulière, scopes minimaux.

## Bonnes pratiques

- Ne jamais logger une clé/API secret (même partiellement).
- Ne jamais commiter `.env` (cf. `.gitignore`) ; utiliser `.env.example` comme référence.
- Préférer des comptes “paper” et des limites strictes dès le début.


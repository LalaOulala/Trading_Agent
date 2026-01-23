# Reflex Trader Agent

Ce module lance l’implémentation d’un agent “trader” qui:

- prend en entrée les **derniers reports** produits par `grok_tools_test.py` (`responses/*/report.txt`), un **snapshot portefeuille** (Alpaca), et une **analyse derniers jours** (placeholder ou fichier),
- produit en sortie une **liste de données de marché (prix) à récupérer** sur certains actifs, plus une **conclusion courte**,
- sauvegarde chaque run dans `reflex_trader/YYYY-MM-DD_HH-MM-SS.txt`.

> **Note importante**
> Ce script ne passe **aucun ordre**. Il sert à produire une réflexion structurée (JSON) et, optionnellement, à récupérer des prix via l’API de Market Data d’Alpaca.

## Fichiers et dépendances

- Script: `reflex_trader_agent.py`
- Prompts:
  - `prompts/reflex_trader_redaction.txt` (rôle + méthode du modèle)
  - `prompts/reflex_trader_presentation.txt` (format JSON strict)
- Entrées externes:
  - `responses/*/report.txt` (générés par `grok_tools_test.py`)
  - `.env` (si présent dans le dossier du script)

### Variables d’environnement

- `XAI_API_KEY` (**obligatoire**) : clé d’API xAI/Grok.
- `REFLEX_TRADER_MODEL` (optionnel) : modèle à utiliser (par défaut `grok-4-1-fast`).
- `ALPACA_API_KEY` / `APCA_API_KEY_ID` : clé Alpaca.
- `ALPACA_API_SECRET` / `ALPACA_SECRET` / `APCA_API_SECRET_KEY` : secret Alpaca.
- `ALPACA_PAPER` (optionnel) : `true` par défaut, passe en réel si `false`/`0`/`no`.

## Exécution rapide

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

## Workflow détaillé

Voici le déroulé précis de `reflex_trader_agent.py`:

1. **Chargement de l’environnement**
   - Le script cherche un `.env` **dans le même dossier que le script** et charge les variables si elles ne sont pas déjà présentes (`_load_env`).
2. **Validation de la clé xAI**
   - La variable `XAI_API_KEY` est requise, sinon le script lève une erreur dès le démarrage.
3. **Lecture des prompts**
   - Les prompts `reflex_trader_redaction.txt` et `reflex_trader_presentation.txt` sont lus via `_read_text_file` (qui échoue si le fichier est vide).
4. **Préparation du contexte (inputs)**
   - Horodatages local + UTC.
   - Chargement des *N* derniers reports (`_load_latest_reports`).
   - Snapshot portefeuille via Alpaca Trading API (`_load_portfolio_snapshot`).
   - Texte d’analyse: placeholder par défaut ou contenu du fichier passé via `--analysis-file`.
5. **Construction du prompt utilisateur**
   - Le script assemble tous les blocs précédents dans un prompt complet, envoyé au modèle (avec l’instruction système contenue dans `reflex_trader_redaction.txt`).
6. **Appel du modèle Grok**
   - Appel via `xai_sdk` avec `max_tokens` et le modèle spécifié.
7. **Extraction JSON stricte**
   - Le script tente d’extraire le premier objet JSON trouvable (`_extract_json_object`).
   - Si le parse échoue, il enregistre la réponse brute et lève une erreur.
8. **Normalisation des tickers**
   - Les symboles sont filtrés par `_normalize_us_equity_symbol` (format actions US: A-Z, 0-9, “.”, max 10 chars).
   - Limite globale de 10 symboles (`MAX_REQUESTED_SYMBOLS`).
9. **Récupération optionnelle des prix**
   - Si `--fetch-prices` est fourni, le script récupère le dernier trade via Alpaca Market Data (`_fetch_latest_trades`).
   - En cas d’échec, l’erreur est affichée dans l’output.
10. **Sauvegarde de la réflexion**
    - Un fichier horodaté est écrit dans `reflex_trader/`.
    - Le contenu inclut les inputs, la sortie JSON (ou la réponse brute), et éventuellement les prix.

## Détails des méthodes principales

### Chargement et validation

- `_load_env(script_dir)`
  - Charge `.env` dans le même dossier que le script.
  - Ne remplace pas les variables déjà définies dans le shell.

- `_read_text_file(path)`
  - Lit un fichier UTF-8.
  - Lève `ValueError` si le fichier est vide après `strip()`.

- `_get_env_value(names)`
  - Retourne la première variable non vide parmi une liste (utile pour gérer plusieurs noms possibles).

### Données portefeuille (Alpaca Trading API)

- `_get_paper_flag()`
  - Détermine si l’environnement Alpaca est en mode paper (`ALPACA_PAPER`, défaut `true`).

- `_get_alpaca_credentials()`
  - Résout `ALPACA_API_KEY` / `ALPACA_API_SECRET` (avec variantes possibles).

- `_load_portfolio_snapshot()`
  - Si les credentials sont absents: retourne un objet `available: false` sans lever d’erreur.
  - Sinon: récupère `account` + `positions` et normalise les champs clés (qty, market_value, etc.).

### Reports d’entrée

- `_load_latest_reports(responses_dir, count)`
  - Parcourt `responses/` par ordre décroissant (run le plus récent en premier).
  - Ignore les runs sans `report.txt` ou vides.

- `_truncate(text, max_chars)`
  - Tronque chaque report pour limiter la taille globale envoyée au modèle.
  - Ajoute un suffixe `[...] (tronqué)` quand nécessaire.

### Format JSON et extraction

- `_extract_json_object(text)`
  - Extrait la **première occurrence** d’un objet JSON plausible (`{...}`).
  - Utilisé si le modèle ajoute du texte avant/après le JSON.

- `_normalize_us_equity_symbol(raw_symbol)`
  - Normalise le ticker en majuscules.
  - Refuse les formats invalides (caractères non autorisés, longueur, etc.).

### Prix de marché (optionnel)

- `_fetch_latest_trades(symbols)`
  - Récupère le **dernier trade** par ticker (Alpaca Market Data).
  - Nécessite `alpaca.data` (et donc `pytz` via `requirements.txt`).
  - Retourne un dict `{symbol: {price, timestamp}}`.

## Détail des entrées / sorties

### Entrées principales

- **Reports Grok** (fichiers `report.txt`):
  - Sources de signaux/contextes générés par `grok_tools_test.py`.

- **Snapshot portefeuille** (Alpaca Trading API):
  - Champs principaux:
    - `account`: `status`, `equity`, `cash`, `buying_power`
    - `positions`: `symbol`, `qty`, `side`, `avg_entry_price`, `market_value`, `unrealized_pl`, `unrealized_plpc`

- **Analyse “derniers jours”**:
  - Texte libre (placeholder si non fourni).

### Sortie JSON attendue (modèle)

Le prompt de présentation exige un JSON strict. Le script attend au minimum:

- `requested_market_data`: liste d’objets, contenant au moins un champ `symbol`.
- `conclusion`: texte court (en général).

Le script ne valide pas toutes les clés, mais utilise `requested_market_data` pour limiter les tickers et, si demandé, récupérer les prix.

### Fichier de sortie

Chaque run génère un fichier texte dans `reflex_trader/` contenant:

- Un en-tête horodaté.
- Un bloc **Inputs** (reports utilisés, disponibilité du portefeuille, analyse).
- La sortie JSON du modèle **ou** la réponse brute si parse échoue.
- Les prix récupérés via Alpaca Market Data (si `--fetch-prices`).

Le dossier `reflex_trader/` est ignoré par git (outputs générés).

## CLI et options

- `--reports-count N`
  - Nombre de reports récents à inclure (par défaut 1).

- `--responses-dir PATH`
  - Chemin du dossier contenant `responses/YYYY.../report.txt`.

- `--analysis-file PATH`
  - Fichier texte à inclure en tant qu’analyse “derniers jours”.

- `--out-dir PATH`
  - Dossier de sortie des réflexions (par défaut `reflex_trader/`).

- `--model MODEL_NAME`
  - Modèle Grok utilisé (par défaut `grok-4-1-fast` ou `REFLEX_TRADER_MODEL`).

- `--max-tokens N`
  - Garde-fou du nombre de tokens maximal pour la réponse LLM (par défaut 1200).

- `--fetch-prices`
  - Active la récupération automatique des prix via Alpaca Market Data.

- `--max-report-chars N`
  - Tronque chaque report à N caractères avant envoi au modèle (par défaut 6000).

## Erreurs et cas limites

- **Absence de `XAI_API_KEY`**: le script échoue immédiatement.
- **Reports manquants**: le script continue avec `(Aucun report trouvé.)`.
- **Analyse absente**: utilise un placeholder.
- **JSON invalide**: réponse brute enregistrée, puis `RuntimeError`.
- **Credentials Alpaca absents**:
  - Le snapshot portefeuille est marqué `available: false`.
  - Le fetch de prix échoue si `--fetch-prices` est activé.

## Sorties

- Chaque run écrit un fichier:
  - `reflex_trader/YYYY-MM-DD_HH-MM-SS.txt`
- Le dossier `reflex_trader/` est ignoré par git (outputs générés).

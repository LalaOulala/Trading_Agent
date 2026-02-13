"""
Agent "Reflex Trader" (début d'implémentation).

Objectif:
    - Entrées: derniers reports de `grok_tools_test.py` (ex: `responses/*/report.txt`),
      état du portefeuille actions, et une analyse "derniers jours" (placeholder pour l'instant).
    - Sorties: une liste structurée des données de marché (prix) à récupérer sur certains actifs,
      plus une conclusion courte.
    - Persistance: chaque exécution écrit un fichier horodaté dans `reflex_trader/`.

Notes:
    - Ce script n'exécute aucun ordre.
    - Univers: actions US uniquement.
    - La récupération des prix via Alpaca Market Data est optionnelle (`--fetch-prices`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpaca.trading.client import TradingClient
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import system, user


DEFAULT_REASONING_MODEL = "grok-4-1-fast-reasoning-latest"
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_MAX_TOKENS = 1200
MAX_REQUESTED_SYMBOLS = 10

PROMPTS_DIRNAME = "prompts"
REDACTION_PROMPT_FILENAME = "reflex_trader_redaction.txt"
PRESENTATION_PROMPT_FILENAME = "reflex_trader_presentation.txt"

_US_EQUITY_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")


@dataclass(frozen=True)
class Report:
    """Un report (texte) produit par `grok_tools_test.py`."""

    path: Path
    content: str


def _load_env(script_dir: Path) -> None:
    """
    Charge un fichier `.env` local (dans le même dossier que ce script).

    Remarque:
        On ne surcharge pas les variables déjà présentes dans le shell.

    Paramètres:
        script_dir: Dossier contenant ce script.
    """
    env_path = script_dir / ".env"
    load_dotenv(dotenv_path=env_path, override=False)


def _read_text_file(path: Path) -> str:
    """
    Lit un fichier texte UTF-8 et retourne un contenu non vide.

    Paramètres:
        path: Chemin du fichier à lire.

    Retours:
        Contenu du fichier, avec espaces de début/fin supprimés.

    Exceptions:
        FileNotFoundError: si le fichier n'existe pas.
        ValueError: si le fichier est vide (après `.strip()`).
    """
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Fichier vide: {path}")
    return content


def _truncate(text: str, max_chars: int) -> str:
    """
    Tronque un texte à un nombre max de caractères (garde-fou tokens).

    Paramètres:
        text: Texte à tronquer.
        max_chars: Nombre maximum de caractères à conserver.

    Retours:
        Le texte initial si déjà court, sinon une version tronquée.
    """
    if max_chars <= 0:
        return ""

    if len(text) <= max_chars:
        return text

    suffix = "\n\n[...] (tronqué)"
    if max_chars <= len(suffix) + 10:
        return text[:max_chars].rstrip()

    return text[: max_chars - len(suffix)].rstrip() + suffix


def _get_env_value(names: list[str]) -> str | None:
    """
    Retourne la première variable d'environnement non vide parmi `names`.

    Paramètres:
        names: Liste ordonnée de noms de variables à tester.

    Retours:
        Valeur trouvée ou `None`.
    """
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _get_paper_flag() -> bool:
    """
    Détermine si on utilise l'environnement paper (par défaut `true`).

    Source:
        - `ALPACA_PAPER=true|false`
    """
    raw = os.environ.get("ALPACA_PAPER", "true").strip().lower()
    return raw not in {"0", "false", "no"}


def _get_alpaca_credentials() -> tuple[str | None, str | None]:
    """
    Résout la clé et le secret Alpaca depuis l'environnement.

    Variables supportées:
        - `ALPACA_API_KEY` ou `APCA_API_KEY_ID`
        - `ALPACA_API_SECRET` ou `ALPACA_SECRET` ou `APCA_API_SECRET_KEY`

    Retours:
        Tuple `(api_key, api_secret)` (valeurs possibles `None`).
    """
    api_key = _get_env_value(["ALPACA_API_KEY", "APCA_API_KEY_ID"])
    api_secret = _get_env_value(
        ["ALPACA_API_SECRET", "ALPACA_SECRET", "APCA_API_SECRET_KEY"]
    )
    return api_key, api_secret


def _load_portfolio_snapshot() -> dict[str, Any]:
    """
    Charge un snapshot du portefeuille actions via Alpaca Trading API.

    Remarque:
        Si les credentials Alpaca sont absents, retourne un objet indiquant que la
        source n'est pas disponible (pas d'exception).
    """
    api_key, api_secret = _get_alpaca_credentials()
    if not api_key or not api_secret:
        return {
            "source": "alpaca",
            "available": False,
            "reason": "Credentials Alpaca manquants (ALPACA_API_KEY/ALPACA_API_SECRET).",
        }

    paper = _get_paper_flag()
    try:
        client = TradingClient(api_key=api_key, secret_key=api_secret, paper=paper)
        account = client.get_account()
        positions = client.get_all_positions()
    except Exception as exc:
        return {
            "source": "alpaca",
            "available": False,
            "paper": paper,
            "reason": (
                "Snapshot Alpaca indisponible "
                f"({type(exc).__name__}: {exc})."
            ),
        }

    def _pos_to_dict(pos: Any) -> dict[str, Any]:
        return {
            "symbol": getattr(pos, "symbol", None),
            "qty": getattr(pos, "qty", None),
            "side": getattr(pos, "side", None),
            "avg_entry_price": getattr(pos, "avg_entry_price", None),
            "market_value": getattr(pos, "market_value", None),
            "unrealized_pl": getattr(pos, "unrealized_pl", None),
            "unrealized_plpc": getattr(pos, "unrealized_plpc", None),
        }

    return {
        "source": "alpaca",
        "available": True,
        "paper": paper,
        "account": {
            "status": getattr(account, "status", None),
            "equity": getattr(account, "equity", None),
            "last_equity": getattr(account, "last_equity", None),
            "cash": getattr(account, "cash", None),
            "buying_power": getattr(account, "buying_power", None),
            "daytrading_buying_power": getattr(account, "daytrading_buying_power", None),
            "shorting_enabled": getattr(account, "shorting_enabled", None),
            "multiplier": getattr(account, "multiplier", None),
            "portfolio_value": getattr(account, "portfolio_value", None),
        },
        "positions": [_pos_to_dict(p) for p in positions],
    }


def _normalize_reasoning_effort(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value not in {"low", "high"}:
        return DEFAULT_REASONING_EFFORT
    return value


def _load_latest_reports(responses_dir: Path, count: int) -> list[Report]:
    """
    Charge les `count` derniers reports générés par `grok_tools_test.py`.

    Attendu:
        - Dossiers runs dans `responses/` (ex: `responses/YYYY-MM-DD_HH-MM-SS/`)
        - Fichier `report.txt` dans chaque run.

    Paramètres:
        responses_dir: Répertoire racine `responses/`.
        count: Nombre de reports à charger.
    """
    if count <= 0:
        return []
    if not responses_dir.exists():
        return []

    run_dirs = sorted(
        [p for p in responses_dir.iterdir() if p.is_dir()],
        reverse=True,
    )

    reports: list[Report] = []
    for run_dir in run_dirs:
        report_path = run_dir / "report.txt"
        if not report_path.exists():
            continue
        content = report_path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        reports.append(Report(path=report_path, content=content))
        if len(reports) >= count:
            break
    return reports


def _extract_json_object(text: str) -> dict[str, Any]:
    """
    Extrait et parse le premier objet JSON valide depuis `text`.

    Comportement:
        - Tolère du texte avant/après le JSON.
        - Ignore les blocs `{...}` non-JSON.
        - Retourne le premier objet JSON (`dict`) parseable.
    """
    if not (text or "").strip():
        raise ValueError("Réponse vide: aucun JSON à parser.")

    errors: list[str] = []
    i = 0
    found_braces = False

    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break

        depth = 0
        in_string = False
        escape = False
        end: int | None = None

        for j in range(start, len(text)):
            ch = text[j]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    found_braces = True
                    break

        if end is None:
            break

        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(
                f"{exc.msg} (ligne {exc.lineno}, colonne {exc.colno})"
            )
            i = end + 1
            continue

        if isinstance(parsed, dict):
            return parsed

        errors.append("Le JSON détecté n'est pas un objet à la racine.")
        i = end + 1

    if errors:
        raise ValueError(
            "Aucun objet JSON valide détecté dans la réponse du modèle. "
            f"Première erreur: {errors[0]}"
        )
    if found_braces:
        raise ValueError(
            "Des blocs '{...}' ont été détectés mais aucun objet JSON valide n'a pu être parsé."
        )
    raise ValueError("Réponse non-JSON (aucun bloc '{...}' équilibré détecté).")


def _normalize_us_equity_symbol(raw_symbol: str) -> str | None:
    """
    Normalise un ticker action US attendu (format simple).

    Règles:
        - MAJUSCULES
        - pas d'espace
        - caractères autorisés: A-Z, 0-9, '.' (ex: BRK.B)

    Retours:
        Le ticker normalisé, ou `None` si le format est invalide.
    """
    symbol = raw_symbol.strip().upper()
    if not symbol:
        return None
    if not _US_EQUITY_SYMBOL_RE.fullmatch(symbol):
        return None
    return symbol


def _fetch_latest_trades(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """
    Récupère le dernier trade connu pour une liste de tickers (Alpaca Market Data).

    Remarque:
        Importé dynamiquement car `alpaca.data` dépend de `pytz` (à installer).
    """
    api_key, api_secret = _get_alpaca_credentials()
    if not api_key or not api_secret:
        raise RuntimeError(
            "Impossible de récupérer les prix (credentials Alpaca manquants)."
        )

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestTradeRequest
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "alpaca.data indisponible. Installe les dépendances (ex: `pip install -r requirements.txt`)."
        ) from exc

    client = StockHistoricalDataClient(api_key=api_key, secret_key=api_secret)
    request = StockLatestTradeRequest(symbol_or_symbols=symbols)
    trades = client.get_stock_latest_trade(request)

    out: dict[str, dict[str, Any]] = {}
    for symbol, trade in trades.items():
        out[symbol] = {
            "price": getattr(trade, "price", None),
            "timestamp": getattr(trade, "timestamp", None).isoformat()
            if getattr(trade, "timestamp", None)
            else None,
        }
    return out


def main() -> None:
    """
    Point d'entrée CLI.

    Rôle:
        - charge `.env`
        - collecte les inputs (reports + portefeuille + analyse)
        - appelle le LLM (JSON strict)
        - écrit un fichier horodaté dans `reflex_trader/`
    """
    parser = argparse.ArgumentParser(
        description="Agent Reflex Trader: lit reports/portefeuille, demande des prix, conclut, et sauvegarde."
    )
    parser.add_argument(
        "--reports-count",
        type=int,
        default=1,
        help="Nombre de reports récents à inclure (depuis `responses/`).",
    )
    parser.add_argument(
        "--responses-dir",
        type=Path,
        default=Path("responses"),
        help="Répertoire contenant les runs de reports (`responses/YYYY.../report.txt`).",
    )
    parser.add_argument(
        "--analysis-file",
        type=Path,
        default=None,
        help="Fichier texte optionnel: analyse des derniers jours (si absent: placeholder).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("reflex_trader"),
        help="Répertoire de sortie pour les réflexions (fichiers .txt).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("REFLEX_TRADER_MODEL", DEFAULT_REASONING_MODEL),
        help="Modèle xAI à utiliser (défaut: grok-4-1-fast-reasoning-latest).",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "high"],
        default=os.environ.get("REFLEX_TRADER_REASONING_EFFORT", DEFAULT_REASONING_EFFORT),
        help="Effort de raisonnement xAI (défaut: high).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help="Garde-fou: tokens max pour la réponse LLM.",
    )
    parser.add_argument(
        "--fetch-prices",
        action="store_true",
        help="Optionnel: récupère automatiquement les derniers prix (trade) via Alpaca Market Data.",
    )
    parser.add_argument(
        "--max-report-chars",
        type=int,
        default=6000,
        help="Garde-fou: tronque chaque report à N caractères avant envoi au LLM.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    _load_env(script_dir)

    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Définis `XAI_API_KEY` dans `.env` (ou dans ton shell) avant de lancer ce script."
        )

    prompts_dir = script_dir / PROMPTS_DIRNAME
    redaction_prompt_path = prompts_dir / REDACTION_PROMPT_FILENAME
    presentation_prompt_path = prompts_dir / PRESENTATION_PROMPT_FILENAME
    redaction_prompt = _read_text_file(redaction_prompt_path)
    presentation_prompt = _read_text_file(presentation_prompt_path)

    now = datetime.now(timezone.utc)
    now_local = now.astimezone()
    now_local_str = now_local.strftime("%Y-%m-%d %H:%M:%S %Z")
    now_utc_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    reports = _load_latest_reports(args.responses_dir, args.reports_count)
    reports_block = (
        "\n\n".join(
            [
                f"--- Report {idx+1} ({r.path}) ---\n{_truncate(r.content, args.max_report_chars)}"
                for idx, r in enumerate(reports)
            ]
        ).strip()
        if reports
        else "(Aucun report trouvé.)"
    )

    portfolio_snapshot = _load_portfolio_snapshot()

    analysis_text = "TODO: analyse des derniers jours non implémentée."
    if args.analysis_file:
        if not args.analysis_file.exists():
            raise FileNotFoundError(
                "analysis-file introuvable: "
                f"{args.analysis_file.resolve() if not args.analysis_file.is_absolute() else args.analysis_file}"
            )
        analysis_text = _read_text_file(args.analysis_file)

    user_prompt = f"""
{presentation_prompt}

Horodatage :
- Local: {now_local_str}
- UTC: {now_utc_str}

Derniers reports (le plus récent en premier) :
{reports_block}

Portefeuille actions (snapshot) :
{json.dumps(portfolio_snapshot, indent=2, ensure_ascii=False)}

Analyse des derniers jours :
{analysis_text}
""".strip()

    reasoning_effort = _normalize_reasoning_effort(args.reasoning_effort)
    client = Client(api_key=api_key)
    chat = client.chat.create(
        model=args.model,
        max_tokens=args.max_tokens,
        reasoning_effort=reasoning_effort,
    )
    chat.append(system(redaction_prompt))
    chat.append(user(user_prompt))
    response = chat.sample()

    raw_content = (response.content or "").strip()

    parsed: dict[str, Any] | None = None
    parse_error: str | None = None
    try:
        parsed = _extract_json_object(raw_content)
    except Exception as exc:
        parse_error = str(exc)

    requested_symbols: list[str] = []
    seen_symbols: set[str] = set()
    if parsed and isinstance(parsed.get("requested_market_data"), list):
        for item in parsed["requested_market_data"]:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            if isinstance(symbol, str) and symbol.strip():
                normalized = _normalize_us_equity_symbol(symbol)
                if normalized and normalized not in seen_symbols:
                    requested_symbols.append(normalized)
                    seen_symbols.add(normalized)
            if len(requested_symbols) >= MAX_REQUESTED_SYMBOLS:
                break

    prices: dict[str, dict[str, Any]] | None = None
    prices_error: str | None = None
    if args.fetch_prices and requested_symbols:
        try:
            prices = _fetch_latest_trades(requested_symbols)
        except Exception as exc:
            prices_error = str(exc)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / now_local.strftime("%Y-%m-%d_%H-%M-%S.txt")

    lines: list[str] = []
    lines.append(f"Reflex Trader — {now_local_str} (UTC: {now_utc_str})")
    lines.append("")
    lines.append("Inputs")
    lines.append(f"- Reports: {[str(r.path) for r in reports] if reports else '[]'}")
    lines.append(f"- Portfolio available: {portfolio_snapshot.get('available')}")
    lines.append(f"- Analysis file: {str(args.analysis_file) if args.analysis_file else '(placeholder)'}")
    lines.append("")

    if parse_error:
        lines.append("LLM output (raw)")
        lines.append(raw_content or "(vide)")
        lines.append("")
        lines.append(f"ERROR: impossible de parser le JSON: {parse_error}")
    else:
        lines.append("LLM output (JSON)")
        lines.append(json.dumps(parsed, indent=2, ensure_ascii=False))

    if args.fetch_prices:
        lines.append("")
        lines.append("Fetched prices (Alpaca latest trade)")
        if prices_error:
            lines.append(f"ERROR: {prices_error}")
        elif prices is None:
            lines.append("(Aucun prix demandé.)")
        else:
            lines.append(json.dumps(prices, indent=2, ensure_ascii=False))

    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Réflexion écrite dans: {out_path}")

    if parse_error:
        raise RuntimeError(
            "Le modèle n'a pas renvoyé un JSON exploitable: "
            f"{parse_error}. "
            f"Contenu brut sauvegardé dans: {out_path}"
        )


if __name__ == "__main__":
    main()

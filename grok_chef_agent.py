"""
Agent "Grok Chef" (exécution Alpaca, paper trading par défaut).

Rôle:
    - Entrées: un report "recherche" (ex: `responses/*/report.txt`), la sortie de l'agent
      trader (JSON demandé par `reflex_trader_agent.py`), et les prix correspondant aux
      symboles demandés (récupérés via Alpaca Market Data).
    - Décision: Grok produit un plan d'ordres (JSON strict) et l'agent applique des garde-fous.
    - Exécution: par défaut en dry-run. Pour réellement soumettre des ordres: `--execute`.

Sécurité:
    - Paper trading par défaut (`ALPACA_PAPER=true`).
    - Si `ALPACA_PAPER=false`, l'exécution requiert `--allow-live` + `--execute`.
    - Limites: nombre d'ordres, notional max par ordre, notional total max.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import system, user


DEFAULT_MODEL = "grok-4-1-fast"
DEFAULT_MAX_TOKENS = 1400

PROMPTS_DIRNAME = "prompts"
REDACTION_PROMPT_FILENAME = "grok_chef_redaction.txt"
PRESENTATION_PROMPT_FILENAME = "grok_chef_presentation.txt"

MAX_REQUESTED_SYMBOLS = 12

_US_EQUITY_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")


@dataclass(frozen=True)
class RiskConfig:
    max_orders: int
    max_notional_per_order_usd: Decimal
    max_total_notional_usd: Decimal
    allow_shorts: bool


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    qty: Decimal
    limit_price: Decimal | None
    time_in_force: Literal["day"]
    reason: str | None


def _load_env(script_dir: Path) -> None:
    env_path = script_dir / ".env"
    load_dotenv(dotenv_path=env_path, override=False)


def _read_text_file(path: Path) -> str:
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Fichier vide: {path}")
    return content


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    suffix = "\n\n[...] (tronqué)"
    if max_chars <= len(suffix) + 10:
        return text[:max_chars].rstrip()
    return text[: max_chars - len(suffix)].rstrip() + suffix


def _get_env_value(names: list[str]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _get_paper_flag() -> bool:
    raw = os.environ.get("ALPACA_PAPER", "true").strip().lower()
    return raw not in {"0", "false", "no"}


def _get_alpaca_credentials() -> tuple[str | None, str | None]:
    api_key = _get_env_value(["ALPACA_API_KEY", "APCA_API_KEY_ID"])
    api_secret = _get_env_value(
        ["ALPACA_API_SECRET", "ALPACA_SECRET", "APCA_API_SECRET_KEY"]
    )
    return api_key, api_secret


def _require_alpaca_credentials() -> tuple[str, str]:
    api_key, api_secret = _get_alpaca_credentials()
    if not api_key or not api_secret:
        raise RuntimeError(
            "Credentials Alpaca manquants (ALPACA_API_KEY/ALPACA_API_SECRET)."
        )
    return api_key, api_secret


def _normalize_us_equity_symbol(raw_symbol: str) -> str | None:
    symbol = raw_symbol.strip().upper()
    if not symbol:
        return None
    if not _US_EQUITY_SYMBOL_RE.fullmatch(symbol):
        return None
    return symbol


def _parse_positive_decimal(raw: Any, field_name: str) -> Decimal:
    if isinstance(raw, (int, float, str)):
        try:
            value = Decimal(str(raw))
        except InvalidOperation as exc:
            raise ValueError(f"{field_name}: nombre invalide ({raw!r}).") from exc
        if value <= 0:
            raise ValueError(f"{field_name}: doit être > 0 (reçu: {raw!r}).")
        return value
    raise ValueError(f"{field_name}: type invalide ({type(raw).__name__}).")


def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    """
    Extrait et parse tous les objets JSON trouvés dans un texte.

    Stratégie:
        - scan caractère par caractère en respectant les chaînes JSON
        - extrait chaque bloc `{...}` équilibré et tente `json.loads`
    """
    objects: list[dict[str, Any]] = []

    i = 0
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
                    break

        if end is None:
            break

        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except Exception:
            i = end + 1
            continue

        if isinstance(parsed, dict):
            objects.append(parsed)
        i = end + 1

    return objects


def _load_latest_response_report(responses_dir: Path) -> Path | None:
    if not responses_dir.exists():
        return None
    run_dirs = sorted(
        [p for p in responses_dir.iterdir() if p.is_dir()],
        reverse=True,
    )
    for run_dir in run_dirs:
        report = run_dir / "report.txt"
        if report.exists() and report.stat().st_size > 0:
            return report
    return None


def _load_latest_reflex_trader_output(reflex_dir: Path) -> Path | None:
    if not reflex_dir.exists():
        return None
    candidates = sorted([p for p in reflex_dir.iterdir() if p.suffix == ".txt"])
    return candidates[-1] if candidates else None


def _load_trader_json(trader_json_path: Path | None, trader_report_path: Path) -> dict[str, Any]:
    if trader_json_path:
        content = _read_text_file(trader_json_path)
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("trader-json: attendu un objet JSON.")
        return parsed

    content = _read_text_file(trader_report_path)
    candidates = _extract_json_objects(content)
    for obj in candidates:
        if isinstance(obj.get("requested_market_data"), list):
            return obj
    raise ValueError(
        "Impossible de trouver le JSON de l'agent trader dans le report (clé `requested_market_data`)."
    )


def _extract_requested_symbols(trader_json: dict[str, Any]) -> list[str]:
    requested: list[str] = []
    seen: set[str] = set()

    rmd = trader_json.get("requested_market_data")
    if isinstance(rmd, list):
        for item in rmd:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            if not isinstance(symbol, str):
                continue
            normalized = _normalize_us_equity_symbol(symbol)
            if normalized and normalized not in seen:
                requested.append(normalized)
                seen.add(normalized)
            if len(requested) >= MAX_REQUESTED_SYMBOLS:
                break

    realtime = trader_json.get("realtime")
    if isinstance(realtime, dict):
        symbols = realtime.get("symbols")
        if isinstance(symbols, list):
            for symbol in symbols:
                if not isinstance(symbol, str):
                    continue
                normalized = _normalize_us_equity_symbol(symbol)
                if normalized and normalized not in seen:
                    requested.append(normalized)
                    seen.add(normalized)
                if len(requested) >= MAX_REQUESTED_SYMBOLS:
                    break

    return requested


def _fetch_latest_trades(symbols: list[str]) -> dict[str, dict[str, Any]]:
    api_key, api_secret = _require_alpaca_credentials()

    feed = os.environ.get("ALPACA_DATA_FEED", "iex").strip() or "iex"

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestTradeRequest
    except Exception as exc:  # pragma: no cover
        # Fallback: appel direct REST (évite des dépendances optionnelles comme `pytz`).
        # Docs: https://docs.alpaca.markets/reference/stocklatesttrades-1
        import urllib.parse
        import urllib.request

        url = (
            "https://data.alpaca.markets/v2/stocks/trades/latest?"
            + urllib.parse.urlencode(
                {
                    "symbols": ",".join(symbols),
                    "feed": feed,
                }
            )
        )
        req = urllib.request.Request(
            url,
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = resp.read().decode("utf-8")
        except Exception as http_exc:
            raise RuntimeError(
                f"Impossible de récupérer les derniers trades (fallback HTTP): {http_exc}"
            ) from http_exc

        try:
            data = json.loads(payload)
        except Exception as json_exc:
            raise RuntimeError(
                "Réponse Market Data invalide (fallback HTTP): JSON non parseable."
            ) from json_exc

        trades = data.get("trades", {})
        out: dict[str, dict[str, Any]] = {}
        for symbol in symbols:
            item = trades.get(symbol) if isinstance(trades, dict) else None
            out[symbol] = {
                "price": item.get("p") if isinstance(item, dict) else None,
                "timestamp": item.get("t") if isinstance(item, dict) else None,
            }
        return out

    client = StockHistoricalDataClient(api_key=api_key, secret_key=api_secret)
    request = StockLatestTradeRequest(symbol_or_symbols=symbols, feed=feed)
    trades = client.get_stock_latest_trade(request)

    out: dict[str, dict[str, Any]] = {}
    for symbol, trade in trades.items():
        ts = getattr(trade, "timestamp", None)
        out[symbol] = {
            "price": getattr(trade, "price", None),
            "timestamp": ts.isoformat() if ts else None,
        }
    return out


def _load_portfolio_snapshot() -> dict[str, Any]:
    api_key, api_secret = _require_alpaca_credentials()
    paper = _get_paper_flag()
    client = TradingClient(api_key=api_key, secret_key=api_secret, paper=paper)

    account = client.get_account()
    positions = client.get_all_positions()

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
            "cash": getattr(account, "cash", None),
            "buying_power": getattr(account, "buying_power", None),
        },
        "positions": [_pos_to_dict(p) for p in positions],
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    candidates = _extract_json_objects(text)
    if not candidates:
        raise ValueError("Réponse non-JSON (aucun objet `{...}` parseable).")
    return candidates[0]


def _positions_qty_by_symbol(portfolio_snapshot: dict[str, Any]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    positions = portfolio_snapshot.get("positions")
    if not isinstance(positions, list):
        return out
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        symbol = pos.get("symbol")
        qty = pos.get("qty")
        if not isinstance(symbol, str):
            continue
        normalized = _normalize_us_equity_symbol(symbol)
        if not normalized:
            continue
        if qty is None:
            continue
        try:
            out[normalized] = Decimal(str(qty))
        except InvalidOperation:
            continue
    return out


def _parse_order_intents(
    plan: dict[str, Any],
    latest_trades: dict[str, dict[str, Any]],
    positions_qty: dict[str, Decimal],
    risk: RiskConfig,
) -> tuple[bool, list[OrderIntent], list[str]]:
    """
    Convertit le plan JSON (LLM) en intentions d'ordres validées.

    Retour:
        (approved, intents, warnings)
    """
    warnings: list[str] = []

    approved = plan.get("approved")
    if not isinstance(approved, bool):
        raise ValueError("Plan JSON invalide: champ `approved` bool requis.")

    orders = plan.get("orders", [])
    if orders is None:
        orders = []
    if not isinstance(orders, list):
        raise ValueError("Plan JSON invalide: champ `orders` doit être une liste.")

    if not approved:
        if orders:
            warnings.append("Plan: `approved=false` mais `orders` non vide (ignorés).")
        return False, [], warnings

    if len(orders) > risk.max_orders:
        raise ValueError(
            f"Plan refuse: trop d'ordres ({len(orders)} > max_orders={risk.max_orders})."
        )

    intents: list[OrderIntent] = []
    total_notional = Decimal("0")

    for idx, raw in enumerate(orders, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Ordre #{idx}: attendu un objet.")

        raw_symbol = raw.get("symbol")
        if not isinstance(raw_symbol, str):
            raise ValueError(f"Ordre #{idx}: `symbol` manquant/invalide.")
        symbol = _normalize_us_equity_symbol(raw_symbol)
        if not symbol:
            raise ValueError(f"Ordre #{idx}: `symbol` invalide (US equity): {raw_symbol!r}.")

        side_raw = raw.get("side")
        if not isinstance(side_raw, str):
            raise ValueError(f"Ordre #{idx} ({symbol}): `side` manquant/invalide.")
        side = side_raw.strip().lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"Ordre #{idx} ({symbol}): `side` doit être buy|sell.")

        order_type_raw = raw.get("order_type", "market")
        if not isinstance(order_type_raw, str):
            raise ValueError(f"Ordre #{idx} ({symbol}): `order_type` invalide.")
        order_type = order_type_raw.strip().lower()
        if order_type not in {"market", "limit"}:
            raise ValueError(f"Ordre #{idx} ({symbol}): `order_type` doit être market|limit.")

        tif_raw = raw.get("time_in_force", "day")
        if not isinstance(tif_raw, str):
            raise ValueError(f"Ordre #{idx} ({symbol}): `time_in_force` invalide.")
        tif = tif_raw.strip().lower()
        if tif != "day":
            raise ValueError(f"Ordre #{idx} ({symbol}): `time_in_force` supporté: day.")

        qty = _parse_positive_decimal(raw.get("qty"), f"Ordre #{idx} ({symbol}) qty")

        limit_price: Decimal | None = None
        if order_type == "limit":
            limit_price = _parse_positive_decimal(
                raw.get("limit_price"), f"Ordre #{idx} ({symbol}) limit_price"
            )

        reason = raw.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError(f"Ordre #{idx} ({symbol}): `reason` doit être une string si présent.")

        trade_info = latest_trades.get(symbol, {})
        raw_price = trade_info.get("price")
        if raw_price is None:
            raise ValueError(
                f"Ordre #{idx} ({symbol}): prix manquant (latest trade)."
            )
        est_price = _parse_positive_decimal(raw_price, f"Ordre #{idx} ({symbol}) price")
        est_notional = (qty * est_price).copy_abs()

        if est_notional > risk.max_notional_per_order_usd:
            raise ValueError(
                f"Ordre #{idx} ({symbol}): notional estimé ${est_notional} "
                f"> max_notional_per_order_usd=${risk.max_notional_per_order_usd}."
            )

        total_notional += est_notional
        if total_notional > risk.max_total_notional_usd:
            raise ValueError(
                f"Plan refuse: notional total estimé ${total_notional} "
                f"> max_total_notional_usd=${risk.max_total_notional_usd}."
            )

        if side == "sell" and not risk.allow_shorts:
            held = positions_qty.get(symbol, Decimal("0"))
            if qty > held:
                raise ValueError(
                    f"Ordre #{idx} ({symbol}): vente qty={qty} > position={held} (short interdit)."
                )

        if order_type == "limit" and limit_price is not None:
            if side == "buy" and limit_price > est_price * Decimal("1.05"):
                warnings.append(
                    f"Ordre #{idx} ({symbol}): limit_price très au-dessus du dernier trade."
                )
            if side == "sell" and limit_price < est_price * Decimal("0.95"):
                warnings.append(
                    f"Ordre #{idx} ({symbol}): limit_price très en-dessous du dernier trade."
                )

        intents.append(
            OrderIntent(
                symbol=symbol,
                side=side,  # type: ignore[arg-type]
                order_type=order_type,  # type: ignore[arg-type]
                qty=qty,
                limit_price=limit_price,
                time_in_force="day",
                reason=reason.strip() if isinstance(reason, str) and reason.strip() else None,
            )
        )

    return approved, intents, warnings


def _submit_orders(intents: list[OrderIntent]) -> list[dict[str, Any]]:
    api_key, api_secret = _require_alpaca_credentials()
    paper = _get_paper_flag()
    client = TradingClient(api_key=api_key, secret_key=api_secret, paper=paper)

    results: list[dict[str, Any]] = []
    for intent in intents:
        side_enum = OrderSide.BUY if intent.side == "buy" else OrderSide.SELL
        tif_enum = TimeInForce.DAY

        if intent.order_type == "market":
            req = MarketOrderRequest(
                symbol=intent.symbol,
                qty=str(intent.qty),
                side=side_enum,
                time_in_force=tif_enum,
            )
        else:
            if intent.limit_price is None:
                raise RuntimeError(f"limit_price manquant pour un ordre limit ({intent.symbol}).")
            req = LimitOrderRequest(
                symbol=intent.symbol,
                qty=str(intent.qty),
                side=side_enum,
                time_in_force=tif_enum,
                limit_price=str(intent.limit_price),
            )

        order = client.submit_order(order_data=req)
        results.append(
            {
                "symbol": getattr(order, "symbol", intent.symbol),
                "id": getattr(order, "id", None),
                "status": getattr(order, "status", None),
                "side": getattr(order, "side", None),
                "type": getattr(order, "type", None),
                "qty": getattr(order, "qty", None),
                "limit_price": getattr(order, "limit_price", None),
                "submitted_at": getattr(order, "submitted_at", None).isoformat()
                if getattr(order, "submitted_at", None)
                else None,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Grok Chef: agrège reports + trader JSON + prix, décide et (optionnellement) exécute via Alpaca."
    )
    parser.add_argument(
        "--responses-dir",
        type=Path,
        default=Path("responses"),
        help="Répertoire contenant les runs de reports (`responses/YYYY.../report.txt`).",
    )
    parser.add_argument(
        "--reflex-dir",
        type=Path,
        default=Path("reflex_trader"),
        help="Répertoire contenant les sorties de l'agent trader (`reflex_trader/*.txt`).",
    )
    parser.add_argument(
        "--research-report",
        type=Path,
        default=None,
        help="Chemin vers un report 'recherche' (si absent: dernier dans responses/).",
    )
    parser.add_argument(
        "--trader-report",
        type=Path,
        default=None,
        help="Chemin vers le report de l'agent trader (si absent: dernier dans reflex_trader/).",
    )
    parser.add_argument(
        "--trader-json",
        type=Path,
        default=None,
        help="Optionnel: JSON direct produit par l'agent trader (évite le parsing du .txt).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("grok_chef"),
        help="Répertoire de sortie pour les runs (fichiers .txt).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GROK_CHEF_MODEL", DEFAULT_MODEL),
        help="Modèle xAI à utiliser (défaut: grok-4-1-fast).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help="Garde-fou: tokens max pour la réponse LLM.",
    )
    parser.add_argument(
        "--max-report-chars",
        type=int,
        default=9000,
        help="Garde-fou: tronque les reports (recherche/trader) à N caractères.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Soumet les ordres à Alpaca (sinon: dry-run).",
    )
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Autorise l'exécution live si `ALPACA_PAPER=false` (en plus de `--execute`).",
    )
    parser.add_argument(
        "--max-orders",
        type=int,
        default=5,
        help="Limite: nombre max d'ordres dans un plan.",
    )
    parser.add_argument(
        "--max-notional-per-order-usd",
        type=str,
        default="250",
        help="Limite: notional max estimé par ordre (USD).",
    )
    parser.add_argument(
        "--max-total-notional-usd",
        type=str,
        default="500",
        help="Limite: notional total max estimé (USD).",
    )
    parser.add_argument(
        "--allow-shorts",
        action="store_true",
        help="Autorise les ventes > positions (short). Désactivé par défaut.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    _load_env(script_dir)

    xai_key = os.getenv("XAI_API_KEY")
    if not xai_key:
        raise RuntimeError(
            "Définis `XAI_API_KEY` dans `.env` (ou dans ton shell) avant de lancer ce script."
        )

    paper = _get_paper_flag()
    if args.execute and (not paper) and (not args.allow_live):
        raise RuntimeError(
            "ALPACA_PAPER=false détecté. Pour exécuter en live: ajoute `--allow-live --execute`."
        )

    risk = RiskConfig(
        max_orders=max(0, int(args.max_orders)),
        max_notional_per_order_usd=_parse_positive_decimal(
            args.max_notional_per_order_usd, "max_notional_per_order_usd"
        ),
        max_total_notional_usd=_parse_positive_decimal(
            args.max_total_notional_usd, "max_total_notional_usd"
        ),
        allow_shorts=bool(args.allow_shorts),
    )
    if risk.max_orders <= 0:
        raise ValueError("max-orders doit être > 0.")

    research_report_path = args.research_report
    if not research_report_path:
        research_report_path = _load_latest_response_report(args.responses_dir)
    if not research_report_path:
        raise FileNotFoundError(
            f"Aucun report recherche trouvé (dir: {args.responses_dir})."
        )
    research_report = _truncate(_read_text_file(research_report_path), args.max_report_chars)

    trader_report_path = args.trader_report
    if not trader_report_path:
        trader_report_path = _load_latest_reflex_trader_output(args.reflex_dir)
    if not trader_report_path and not args.trader_json:
        raise FileNotFoundError(
            f"Aucune sortie trader trouvée (dir: {args.reflex_dir}). Lance `python reflex_trader_agent.py`."
        )
    trader_report_for_prompt = ""
    if trader_report_path:
        trader_report_for_prompt = _truncate(
            _read_text_file(trader_report_path), args.max_report_chars
        )

    trader_json = _load_trader_json(args.trader_json, trader_report_path or Path("-unused-"))
    symbols = _extract_requested_symbols(trader_json)
    if not symbols:
        raise RuntimeError("Aucun symbole demandé par l'agent trader (requested_market_data vide).")

    latest_trades = _fetch_latest_trades(symbols)
    portfolio_snapshot = _load_portfolio_snapshot()
    positions_qty = _positions_qty_by_symbol(portfolio_snapshot)

    prompts_dir = script_dir / PROMPTS_DIRNAME
    redaction_prompt = _read_text_file(prompts_dir / REDACTION_PROMPT_FILENAME)
    presentation_prompt = _read_text_file(prompts_dir / PRESENTATION_PROMPT_FILENAME)

    now = datetime.now(timezone.utc)
    now_local = now.astimezone()
    now_local_str = now_local.strftime("%Y-%m-%d %H:%M:%S %Z")
    now_utc_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    user_prompt = f"""
{presentation_prompt}

Horodatage :
- Local: {now_local_str}
- UTC: {now_utc_str}

Mode Alpaca :
- paper: {paper}
- execute demandé: {bool(args.execute)}

Contraintes (garde-fous côté exécution) :
{json.dumps({'max_orders': risk.max_orders, 'max_notional_per_order_usd': str(risk.max_notional_per_order_usd), 'max_total_notional_usd': str(risk.max_total_notional_usd), 'allow_shorts': risk.allow_shorts}, indent=2, ensure_ascii=False)}

Report recherche ({research_report_path}) :
{research_report}

Report trader (texte, optionnel) ({trader_report_path if trader_report_path else '(absent)'}) :
{trader_report_for_prompt if trader_report_for_prompt else '(non fourni)'}

Trader JSON (demandes marché) :
{json.dumps(trader_json, indent=2, ensure_ascii=False)}

Prix (Alpaca latest trade) :
{json.dumps(latest_trades, indent=2, ensure_ascii=False)}

Portefeuille (snapshot) :
{json.dumps(portfolio_snapshot, indent=2, ensure_ascii=False)}
""".strip()

    client = Client(api_key=xai_key)
    chat = client.chat.create(model=args.model, max_tokens=args.max_tokens)
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

    intents: list[OrderIntent] = []
    approved: bool = False
    warnings: list[str] = []
    plan_error: str | None = None
    if parse_error is None and parsed is not None:
        try:
            approved, intents, warnings = _parse_order_intents(
                plan=parsed,
                latest_trades=latest_trades,
                positions_qty=positions_qty,
                risk=risk,
            )
        except Exception as exc:
            plan_error = str(exc)

    execution_results: list[dict[str, Any]] | None = None
    execution_error: str | None = None
    if args.execute and parse_error is None and plan_error is None and approved and intents:
        try:
            execution_results = _submit_orders(intents)
        except Exception as exc:
            execution_error = str(exc)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / now_local.strftime("%Y-%m-%d_%H-%M-%S.txt")

    lines: list[str] = []
    lines.append(f"Grok Chef — {now_local_str} (UTC: {now_utc_str})")
    lines.append("")
    lines.append("Inputs")
    lines.append(f"- Research report: {research_report_path}")
    lines.append(f"- Trader report: {trader_report_path if trader_report_path else '(none)'}")
    lines.append(f"- Trader JSON: {args.trader_json if args.trader_json else '(extrait du report)'}")
    lines.append(f"- Symbols: {symbols}")
    lines.append(f"- Paper: {paper}")
    lines.append(f"- Execute: {bool(args.execute)}")
    lines.append(f"- Risk: max_orders={risk.max_orders}, max_notional_per_order_usd={risk.max_notional_per_order_usd}, max_total_notional_usd={risk.max_total_notional_usd}, allow_shorts={risk.allow_shorts}")
    lines.append("")

    lines.append("Market data (latest trades)")
    lines.append(json.dumps(latest_trades, indent=2, ensure_ascii=False))
    lines.append("")

    if parse_error:
        lines.append("LLM output (raw)")
        lines.append(raw_content or "(vide)")
        lines.append("")
        lines.append(f"ERROR: impossible de parser le JSON: {parse_error}")
    else:
        lines.append("LLM output (JSON)")
        lines.append(json.dumps(parsed, indent=2, ensure_ascii=False))
        lines.append("")
        lines.append(f"Plan approved: {approved}")
        lines.append(f"Order intents: {len(intents)}")
        if warnings:
            lines.append("Warnings:")
            lines.extend([f"- {w}" for w in warnings])
        if plan_error:
            lines.append("")
            lines.append(f"ERROR: plan invalide: {plan_error}")

    lines.append("")
    lines.append("Execution")
    if not args.execute:
        lines.append("(dry-run) Aucun ordre soumis (utilise --execute pour soumettre).")
    elif parse_error or plan_error:
        lines.append("Aucun ordre soumis (erreur de parsing/validation).")
    elif not approved or not intents:
        lines.append("Aucun ordre soumis (plan non approuvé ou vide).")
    else:
        if execution_error:
            lines.append(f"ERROR: soumission Alpaca échouée: {execution_error}")
        else:
            lines.append(json.dumps(execution_results, indent=2, ensure_ascii=False))

    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Run Grok Chef écrit dans: {out_path}")

    if parse_error:
        raise RuntimeError(
            "Le modèle n'a pas renvoyé un JSON valide. Le contenu brut est sauvegardé; relance si besoin."
        )
    if plan_error:
        raise RuntimeError(f"Plan invalide: {plan_error}")
    if execution_error:
        raise RuntimeError(f"Soumission Alpaca échouée: {execution_error}")


if __name__ == "__main__":
    main()

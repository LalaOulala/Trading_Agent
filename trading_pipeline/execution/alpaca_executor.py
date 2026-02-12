from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .base import TradeExecutor
from trading_pipeline.models import ExecutionReport, FinalDecision


def _coerce_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_duration(total_seconds: int) -> str:
    seconds = max(int(total_seconds), 0)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}j")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if sec or not parts:
        parts.append(f"{sec}s")
    return " ".join(parts)


@dataclass
class AlpacaTradeExecutor(TradeExecutor):
    api_key: str | None
    api_secret: str | None
    paper: bool = True
    execute_live: bool = False
    require_confirmation: bool = True

    def _load_portfolio_snapshot(self) -> tuple[dict[str, Any] | None, str | None]:
        """
        Récupère un snapshot portefeuille pour l'affichage terminal avant confirmation.

        Retourne:
            - snapshot dict si disponible, sinon None
            - message d'erreur si indisponible, sinon None
        """
        if not self.api_key or not self.api_secret:
            return None, "Credentials Alpaca absents."

        try:
            from alpaca.trading.client import TradingClient
        except Exception as exc:  # pragma: no cover
            return None, f"alpaca-py indisponible ({type(exc).__name__}: {exc})"

        try:
            client = TradingClient(
                api_key=self.api_key,
                secret_key=self.api_secret,
                paper=self.paper,
            )
            account = client.get_account()
            positions = client.get_all_positions()
        except Exception as exc:
            return None, f"Snapshot indisponible ({type(exc).__name__}: {exc})"

        return (
            {
                "status": getattr(account, "status", None),
                "equity": getattr(account, "equity", None),
                "cash": getattr(account, "cash", None),
                "buying_power": getattr(account, "buying_power", None),
                "positions": [
                    {
                        "symbol": getattr(pos, "symbol", None),
                        "qty": getattr(pos, "qty", None),
                        "side": str(getattr(pos, "side", "")),
                        "market_value": getattr(pos, "market_value", None),
                    }
                    for pos in positions
                ],
            },
            None,
        )

    @staticmethod
    def _normalize_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for order in orders:
            side = str(order.get("side", "")).lower()
            if side not in {"buy", "sell"}:
                continue
            symbol = str(order.get("symbol", "")).upper()
            qty = float(order.get("qty", 0))
            if not symbol or qty <= 0:
                continue
            normalized.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                }
            )
        return normalized

    def _confirm_submission(self, orders: list[dict[str, Any]]) -> bool:
        if not self.require_confirmation:
            return True

        mode = "PAPER" if self.paper else "LIVE"
        print("\n[Alpaca] Ordres prêts à être envoyés")
        print(f"- Mode: {mode}")

        snapshot, snapshot_error = self._load_portfolio_snapshot()
        if snapshot_error:
            print(f"- Portefeuille: indisponible ({snapshot_error})")
        elif snapshot:
            print("- Portefeuille:")
            print(f"  - status={snapshot.get('status')}")
            print(f"  - equity={snapshot.get('equity')}")
            print(f"  - cash={snapshot.get('cash')}")
            print(f"  - buying_power={snapshot.get('buying_power')}")
            positions = snapshot.get("positions") or []
            if positions:
                print("  - positions:")
                for pos in positions[:10]:
                    print(
                        "    - "
                        f"{pos.get('symbol')} qty={pos.get('qty')} "
                        f"side={pos.get('side')} mv={pos.get('market_value')}"
                    )
                if len(positions) > 10:
                    print(f"    - ... ({len(positions) - 10} positions supplémentaires)")
            else:
                print("  - positions: aucune")

        for idx, order in enumerate(orders, start=1):
            print(f"- #{idx}: {order['side'].upper()} {order['qty']} {order['symbol']} (market/day)")

        try:
            answer = input("Confirmer l'envoi vers Alpaca ? Tape 'yes' pour valider: ")
        except (EOFError, KeyboardInterrupt):
            print("\n[Alpaca] Confirmation interrompue, envoi annulé.")
            return False

        if answer.strip().lower() != "yes":
            print("[Alpaca] Envoi annulé (confirmation différente de 'yes').")
            return False

        return True

    def _submit_orders(self, orders: list[dict[str, Any]]) -> list[dict[str, str]]:
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"alpaca-py indisponible ({type(exc).__name__}: {exc})"
            ) from exc

        client = TradingClient(
            api_key=self.api_key,
            secret_key=self.api_secret,
            paper=self.paper,
        )
        submitted: list[dict[str, str]] = []

        for order in orders:
            req = MarketOrderRequest(
                symbol=order["symbol"],
                qty=order["qty"],
                side=OrderSide.BUY if order["side"] == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            created = client.submit_order(order_data=req)
            submitted.append(
                {
                    "symbol": order["symbol"],
                    "side": order["side"],
                    "qty": str(order["qty"]),
                    "order_id": str(getattr(created, "id", "")),
                }
            )
        return submitted

    @staticmethod
    def _market_closed_message(now: datetime, next_open: datetime) -> str:
        now_utc = _coerce_utc(now)
        next_open_utc = _coerce_utc(next_open)
        remaining = _format_duration(int((next_open_utc - now_utc).total_seconds()))
        next_open_local = next_open_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        return (
            f"Le marché est fermé, il réouvre dans {remaining} "
            f"(prochaine ouverture: {next_open_local})."
        )

    def _check_market_open(self) -> tuple[bool, str | None]:
        """
        Best effort: si l'horloge Alpaca est indisponible, ne bloque pas la soumission.
        """
        if not self.api_key or not self.api_secret:
            return True, None

        try:
            from alpaca.trading.client import TradingClient
        except Exception:
            return True, None

        try:
            client = TradingClient(
                api_key=self.api_key,
                secret_key=self.api_secret,
                paper=self.paper,
            )
            clock = client.get_clock()
        except Exception:
            return True, None

        if bool(getattr(clock, "is_open", False)):
            return True, None

        now = getattr(clock, "timestamp", None)
        next_open = getattr(clock, "next_open", None)
        if isinstance(now, datetime) and isinstance(next_open, datetime):
            return False, self._market_closed_message(now, next_open)
        return False, "Le marché est fermé, heure de réouverture indisponible."

    def execute(self, decision: FinalDecision) -> ExecutionReport:
        normalized_orders = self._normalize_orders(decision.orders)
        if not normalized_orders:
            return ExecutionReport(
                status="skipped",
                broker="alpaca",
                details=[],
                message="Aucun ordre valide à exécuter.",
            )

        if not self.execute_live:
            return ExecutionReport(
                status="dry_run",
                broker="alpaca",
                details=normalized_orders,
                message="Mode dry-run: ordres simulés uniquement.",
            )

        if not self.api_key or not self.api_secret:
            return ExecutionReport(
                status="error",
                broker="alpaca",
                details=[],
                message="Credentials Alpaca manquants pour exécution live.",
            )

        is_open, market_message = self._check_market_open()
        if not is_open:
            return ExecutionReport(
                status="skipped",
                broker="alpaca",
                details=normalized_orders,
                message=market_message or "Le marché est fermé.",
            )

        if not self._confirm_submission(normalized_orders):
            return ExecutionReport(
                status="skipped",
                broker="alpaca",
                details=normalized_orders,
                message="Envoi annulé: confirmation utilisateur absente (attendu: yes).",
            )

        try:
            submitted = self._submit_orders(normalized_orders)
        except Exception as exc:
            return ExecutionReport(
                status="error",
                broker="alpaca",
                details=[],
                message=f"Echec soumission Alpaca ({type(exc).__name__}: {exc})",
            )

        return ExecutionReport(
            status="submitted",
            broker="alpaca",
            details=submitted,
            message=f"{len(submitted)} ordres soumis.",
        )

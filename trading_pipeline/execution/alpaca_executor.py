from __future__ import annotations

from dataclasses import dataclass

from .base import TradeExecutor
from trading_pipeline.models import ExecutionReport, FinalDecision


@dataclass
class AlpacaTradeExecutor(TradeExecutor):
    api_key: str | None
    api_secret: str | None
    paper: bool = True
    execute_live: bool = False

    def execute(self, decision: FinalDecision) -> ExecutionReport:
        if not decision.orders:
            return ExecutionReport(
                status="skipped",
                broker="alpaca",
                details=[],
                message="Aucun ordre à exécuter.",
            )

        if not self.execute_live:
            return ExecutionReport(
                status="dry_run",
                broker="alpaca",
                details=decision.orders,
                message="Mode dry-run: ordres simulés uniquement.",
            )

        if not self.api_key or not self.api_secret:
            return ExecutionReport(
                status="error",
                broker="alpaca",
                details=[],
                message="Credentials Alpaca manquants pour exécution live.",
            )

        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest
        except Exception as exc:  # pragma: no cover
            return ExecutionReport(
                status="error",
                broker="alpaca",
                details=[],
                message=f"alpaca-py indisponible ({type(exc).__name__}: {exc})",
            )

        client = TradingClient(
            api_key=self.api_key,
            secret_key=self.api_secret,
            paper=self.paper,
        )
        submitted: list[dict[str, str]] = []

        for order in decision.orders:
            side = str(order.get("side", "")).lower()
            if side not in {"buy", "sell"}:
                continue
            symbol = str(order.get("symbol", "")).upper()
            qty = float(order.get("qty", 0))
            if not symbol or qty <= 0:
                continue

            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            created = client.submit_order(order_data=req)
            submitted.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "qty": str(qty),
                    "order_id": str(getattr(created, "id", "")),
                }
            )

        return ExecutionReport(
            status="submitted",
            broker="alpaca",
            details=submitted,
            message=f"{len(submitted)} ordres soumis.",
        )

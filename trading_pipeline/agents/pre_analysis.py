from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from trading_pipeline.models import FreshMarketSnapshot, PreAnalysis

_DOLLAR_TICKER_RE = re.compile(r"\$([A-Z][A-Z0-9]{0,4}(?:\.[A-Z])?)\b")
_STOPWORDS = {
    "A",
    "AN",
    "AND",
    "AS",
    "AT",
    "BY",
    "FOR",
    "FROM",
    "IN",
    "IS",
    "IT",
    "OF",
    "ON",
    "OR",
    "THE",
    "TO",
    "US",
    "USA",
    "UTC",
    "AI",
    "GDP",
    "CPI",
    "PPI",
    "PMI",
    "ETF",
}
_KNOWN_MARKET_SYMBOLS = {
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "TLT",
    "GLD",
    "USO",
    "VIXY",
    "XLF",
    "XLK",
    "XLE",
    "XLI",
    "XLB",
    "XLV",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "TSLA",
    "GOOGL",
    "GOOG",
    "AMD",
    "INTC",
    "NFLX",
    "CRM",
    "CSCO",
    "JPM",
    "BAC",
    "GS",
    "WMT",
    "COST",
    "KO",
    "PEP",
    "XOM",
    "CVX",
}


def _extract_symbols(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    upper = text.upper()

    for match in _DOLLAR_TICKER_RE.finditer(upper):
        symbol = match.group(1).strip()
        if symbol in _STOPWORDS:
            continue
        if symbol not in seen:
            seen.add(symbol)
            out.append(symbol)

    for symbol in sorted(_KNOWN_MARKET_SYMBOLS):
        if symbol in seen:
            continue
        if re.search(rf"\b{re.escape(symbol)}\b", upper):
            seen.add(symbol)
            out.append(symbol)
    return out


@dataclass
class PreAnalysisAgent:
    max_candidate_symbols: int = 12

    def run(self, snapshot: FreshMarketSnapshot) -> PreAnalysis:
        all_signals = [*snapshot.web_signals, *snapshot.social_signals]
        titles = [s.title.strip() for s in all_signals if s.title.strip()]
        key_drivers = titles[:6]

        symbol_counts: Counter[str] = Counter()
        for signal in all_signals:
            text = f"{signal.title}\n{signal.snippet}"
            for symbol in _extract_symbols(text):
                symbol_counts[symbol] += 1

        candidate_symbols = [
            sym
            for sym, _ in symbol_counts.most_common(self.max_candidate_symbols)
        ]
        if not candidate_symbols:
            candidate_symbols = ["SPY", "QQQ"]

        risks: list[str] = []
        if len(snapshot.web_signals) < 4:
            risks.append("Peu de signaux web: risque de couverture partielle.")
        if not snapshot.social_signals:
            risks.append("Aucun signal X exploitable (collecteur social placeholder ou vide).")
        if not risks:
            risks.append("Risque principal: news contradictoires intraday.")

        if len(snapshot.web_signals) >= 8 and len(snapshot.social_signals) >= 3:
            confidence = "high"
        elif len(snapshot.web_signals) >= 4:
            confidence = "medium"
        else:
            confidence = "low"

        summary = (
            f"{len(snapshot.web_signals)} signaux web et {len(snapshot.social_signals)} "
            "signaux sociaux agrégés. "
            f"Catalyseurs dominants: {', '.join(key_drivers[:3]) if key_drivers else 'n/a'}."
        )

        return PreAnalysis(
            summary=summary,
            key_drivers=key_drivers,
            candidate_symbols=candidate_symbols,
            risks=risks,
            confidence=confidence,
        )

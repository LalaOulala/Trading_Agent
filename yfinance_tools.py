#!/usr/bin/env python3
"""
Yahoo Finance tools.

Module centralise la branche "données financières" via yfinance.
Conçu pour être réutilisé par les scripts standalone et la pipeline V2.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import yfinance as yf


def _ticker(symbol: str) -> yf.Ticker:
    cleaned = (symbol or "").strip().upper()
    if not cleaned:
        raise ValueError("Symbol vide.")
    return yf.Ticker(cleaned)


def get_current_price_yfinance(symbol: str) -> float | None:
    """
    Récupère le prix actuel via plusieurs fallbacks yfinance.
    """
    ticker = _ticker(symbol)

    try:
        fast_info = getattr(ticker, "fast_info", None)
        if isinstance(fast_info, dict):
            for key in ("last_price", "lastPrice"):
                value = fast_info.get(key)
                if isinstance(value, (int, float)) and float(value) > 0:
                    return float(value)
    except Exception:
        pass

    try:
        info = ticker.info
        if isinstance(info, dict):
            for key in ("currentPrice", "regularMarketPrice", "previousClose"):
                value = info.get(key)
                if isinstance(value, (int, float)) and float(value) > 0:
                    return float(value)
    except Exception:
        pass

    try:
        history = ticker.history(period="1d", interval="1m")
        if history is not None and not history.empty:
            close_value = history["Close"].iloc[-1]
            if pd.notna(close_value):
                price = float(close_value)
                if price > 0:
                    return price
    except Exception:
        pass

    return None


def get_current_price(symbol: str) -> float | None:
    """
    Alias public pour obtenir le prix spot.
    """
    try:
        return get_current_price_yfinance(symbol)
    except Exception:
        return None


def get_price_history(
    symbol: str,
    period: str = "5d",
    interval: str = "1d",
    *,
    auto_adjust: bool = False,
    prepost: bool = False,
) -> pd.DataFrame | None:
    """
    Historique des prix via période relative.
    """
    ticker = _ticker(symbol)
    try:
        history = ticker.history(
            period=period,
            interval=interval,
            auto_adjust=auto_adjust,
            prepost=prepost,
        )
    except Exception:
        return None
    if history is None or history.empty:
        return None
    return history


def get_price_history_advanced(
    symbol: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = "1d",
    auto_adjust: bool = False,
    prepost: bool = False,
) -> pd.DataFrame | None:
    """
    Historique des prix via dates explicites.
    """
    ticker = _ticker(symbol)
    kwargs: dict[str, Any] = {
        "interval": interval,
        "auto_adjust": auto_adjust,
        "prepost": prepost,
    }
    if start_date:
        kwargs["start"] = start_date
    if end_date:
        kwargs["end"] = end_date
    try:
        history = ticker.history(**kwargs)
    except Exception:
        return None
    if history is None or history.empty:
        return None
    return history


def get_detailed_info(symbol: str) -> dict[str, Any] | None:
    """
    Extrait un sous-ensemble d'infos entreprise utile au trading.
    """
    ticker = _ticker(symbol)
    try:
        info = ticker.info
    except Exception:
        return None
    if not isinstance(info, dict):
        return None

    return {
        "symbol": symbol.upper(),
        "company_name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": info.get("marketCap"),
        "current_price": info.get("currentPrice"),
        "regular_market_price": info.get("regularMarketPrice"),
        "previous_close": info.get("previousClose"),
        "open": info.get("open"),
        "day_high": info.get("dayHigh"),
        "day_low": info.get("dayLow"),
        "volume": info.get("volume"),
        "avg_volume": info.get("averageVolume"),
        "pe_ratio": info.get("trailingPE"),
        "eps": info.get("trailingEps"),
        "beta": info.get("beta"),
        "dividend_yield": info.get("dividendYield"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
    }


def calculate_technical_indicators(history: pd.DataFrame | None) -> pd.DataFrame | None:
    """
    Calcule des indicateurs techniques basiques.
    """
    if history is None or history.empty:
        return None

    df = history.copy()
    if "Close" not in df.columns:
        return None

    df["SMA_20"] = df["Close"].rolling(window=20).mean()
    df["SMA_50"] = df["Close"].rolling(window=50).mean()

    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    df["Change_1d"] = df["Close"].pct_change(1) * 100
    df["Change_5d"] = df["Close"].pct_change(5) * 100
    df["Change_20d"] = df["Close"].pct_change(20) * 100
    df["Volatility"] = df["Close"].rolling(window=20).std()

    return df


def get_market_status() -> tuple[bool | None, str]:
    """
    Retourne un tuple (is_open, status) pour la session US.
    """
    try:
        import pytz
    except Exception:
        return None, "Unknown (pytz missing)"

    try:
        eastern = pytz.timezone("US/Eastern")
        now = datetime.now(eastern)
        weekday = now.weekday()
        if weekday >= 5:
            return False, "Weekend"

        open_dt = now.replace(hour=9, minute=30, second=0, microsecond=0)
        close_dt = now.replace(hour=16, minute=0, second=0, microsecond=0)
        if open_dt <= now <= close_dt:
            return True, "Market Open"
        return False, "Market Closed"
    except Exception:
        return None, "Unknown"

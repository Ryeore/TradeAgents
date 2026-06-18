"""Shared helpers for the stock-skills data scripts.

Pure-Python (pandas/numpy) technical indicators plus thin yfinance wrappers.
No API keys required.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None


# --------------------------------------------------------------------------- #
# yfinance wrappers
# --------------------------------------------------------------------------- #
def get_ticker(symbol: str):
    if yf is None:
        raise SystemExit("yfinance is not installed. Run: pip install -r requirements.txt")
    return yf.Ticker(symbol.upper())


def safe_info(ticker) -> dict:
    """ticker.info occasionally throws / returns None. Always give back a dict."""
    try:
        info = ticker.info
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


def history(ticker, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    try:
        df = ticker.history(period=period, interval=interval, auto_adjust=False)
    except Exception:
        return pd.DataFrame()
    return df if df is not None else pd.DataFrame()


def last_price(ticker, info: dict | None = None) -> float | None:
    info = info if info is not None else safe_info(ticker)
    for key in ("currentPrice", "regularMarketPrice", "previousClose"):
        val = info.get(key)
        if val:
            return float(val)
    try:
        fi = ticker.fast_info
        if fi and fi.get("last_price"):
            return float(fi["last_price"])
    except Exception:
        pass
    df = history(ticker, period="5d")
    if not df.empty:
        return float(df["Close"].iloc[-1])
    return None


# --------------------------------------------------------------------------- #
# Technical indicators (Wilder-style, pandas only)
# --------------------------------------------------------------------------- #
def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def mfi(high: pd.Series, low: pd.Series, close: pd.Series,
        volume: pd.Series, period: int = 14) -> pd.Series:
    typical = (high + low + close) / 3
    money_flow = typical * volume
    up = typical > typical.shift(1)
    down = typical < typical.shift(1)
    pos = money_flow.where(up, 0.0).rolling(period).sum()
    neg = money_flow.where(down, 0.0).rolling(period).sum()
    mfr = pos / neg.replace(0, np.nan)
    return 100 - (100 / (1 + mfr))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def fibonacci_levels(high: float, low: float) -> dict:
    """Retracement levels for an up-move from `low` to `high`."""
    diff = high - low
    ratios = {"0.0%": 0.0, "23.6%": 0.236, "38.2%": 0.382,
              "50.0%": 0.5, "61.8%": 0.618, "78.6%": 0.786, "100.0%": 1.0}
    return {label: round(high - diff * r, 2) for label, r in ratios.items()}


# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #
def round_or_none(val, ndigits: int = 2):
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return round(float(val), ndigits)
    except (TypeError, ValueError):
        return None


def emit(obj: dict) -> None:
    """Pretty-print a JSON payload to stdout for the agent to consume."""
    print(json.dumps(obj, indent=2, default=str))


def require_symbol(argv) -> str:
    if len(argv) < 2 or not argv[1].strip():
        raise SystemExit("Usage: python <script>.py <TICKER> [extra args]")
    return argv[1].strip().upper()

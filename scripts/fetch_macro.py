#!/usr/bin/env python
"""fetch_macro.py -- top-down context for the Macro Strategist agent.

Compares the stock and its sector ETF against the S&P 500, and pulls a small
macro dashboard (VIX, 10y/2y proxies, USD, oil, gold) via yfinance.

Usage:
    python scripts/fetch_macro.py AMD
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import (  # noqa: E402
    emit, get_ticker, history, require_symbol, round_or_none, safe_info,
)

# Sector -> SPDR sector ETF
SECTOR_ETF = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Financial": "XLF",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

MACRO_TICKERS = {
    "vix": "^VIX",
    "ust10y": "^TNX",          # 10-year yield (x10)
    "ust2y": "^IRX",           # 13-week T-bill proxy for short end
    "usd_index": "DX-Y.NYB",
    "wti_oil": "CL=F",
    "gold": "GC=F",
}


def pct_change(symbol: str, period: str = "6mo"):
    try:
        df = history(get_ticker(symbol), period=period)
        if df.empty:
            return None
        first, last = float(df["Close"].iloc[0]), float(df["Close"].iloc[-1])
        return round_or_none((last / first - 1) * 100)
    except Exception:
        return None


def level(symbol: str):
    try:
        df = history(get_ticker(symbol), period="5d")
        return round_or_none(float(df["Close"].iloc[-1])) if not df.empty else None
    except Exception:
        return None


def main() -> None:
    symbol = require_symbol(sys.argv)
    info = safe_info(get_ticker(symbol))
    sector = info.get("sector")
    etf = SECTOR_ETF.get(sector)

    stock_6m = pct_change(symbol)
    spy_6m = pct_change("SPY")
    sector_6m = pct_change(etf) if etf else None

    rel_vs_index = (round_or_none(stock_6m - spy_6m)
                    if stock_6m is not None and spy_6m is not None else None)
    sector_vs_index = (round_or_none(sector_6m - spy_6m)
                       if sector_6m is not None and spy_6m is not None else None)

    emit({
        "symbol": symbol,
        "sector": sector,
        "sector_etf": etf,
        "performance_6m_pct": {
            "stock": stock_6m,
            "sector_etf": sector_6m,
            "sp500": spy_6m,
            "stock_relative_to_index": rel_vs_index,
            "sector_relative_to_index": sector_vs_index,
        },
        "macro_dashboard": {name: level(t) for name, t in MACRO_TICKERS.items()},
        "web_search_terms": [
            "Federal Reserve rate decision latest dot plot",
            "US business cycle indicator ISM PMI yield curve recession",
            f"{sector} sector outlook {info.get('shortName') or symbol}",
        ],
        "note": "^TNX is 10y yield x10 (e.g. 42.5 = 4.25%). Use web search for the live "
                "Fed stance and business-cycle read; yfinance only gives price levels.",
    })


if __name__ == "__main__":
    main()

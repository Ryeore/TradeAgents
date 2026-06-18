#!/usr/bin/env python
"""fetch_quote.py -- snapshot for the Data Scout agent.

Current price, day range, 52-week range, EPS (trailing/forward), analyst
target prices and recommendation, plus identifiers for follow-up web search.

Usage:
    python scripts/fetch_quote.py AAPL
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import (  # noqa: E402
    emit, get_ticker, last_price, require_symbol, round_or_none, safe_info,
)


def main() -> None:
    symbol = require_symbol(sys.argv)
    ticker = get_ticker(symbol)
    info = safe_info(ticker)
    price = last_price(ticker, info)

    target_mean = info.get("targetMeanPrice")
    upside = None
    if price and target_mean:
        upside = round_or_none((target_mean / price - 1) * 100)

    emit({
        "symbol": symbol,
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "price": round_or_none(price),
        "currency": info.get("currency"),
        "previous_close": round_or_none(info.get("previousClose")),
        "day_low": round_or_none(info.get("dayLow")),
        "day_high": round_or_none(info.get("dayHigh")),
        "week52_low": round_or_none(info.get("fiftyTwoWeekLow")),
        "week52_high": round_or_none(info.get("fiftyTwoWeekHigh")),
        "market_cap": info.get("marketCap"),
        "eps_trailing": round_or_none(info.get("trailingEps")),
        "eps_forward": round_or_none(info.get("forwardEps")),
        "next_earnings_hint": info.get("earningsTimestamp"),
        "analyst_target_mean": round_or_none(target_mean),
        "analyst_target_low": round_or_none(info.get("targetLowPrice")),
        "analyst_target_high": round_or_none(info.get("targetHighPrice")),
        "analyst_upside_pct": upside,
        "recommendation_key": info.get("recommendationKey"),
        "recommendation_mean": round_or_none(info.get("recommendationMean")),
        "num_analyst_opinions": info.get("numberOfAnalystOpinions"),
        "web_search_terms": [
            f"{symbol} latest earnings EPS vs consensus",
            f"{info.get('shortName') or symbol} analyst price target update",
            f"{info.get('shortName') or symbol} breaking news today",
        ],
        "note": "Use web_search_terms to verify breaking news / latest EPS surprise; "
                "yfinance fields can lag intraday.",
    })


if __name__ == "__main__":
    main()

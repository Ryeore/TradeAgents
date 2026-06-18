#!/usr/bin/env python
"""fetch_sentiment.py -- positioning read for the Sentiment Analyst agent.

Short interest, insider transactions, institutional holders, and the analyst
recommendation trend.

Usage:
    python scripts/fetch_sentiment.py TSLA
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import (  # noqa: E402
    emit, get_ticker, require_symbol, round_or_none, safe_info,
)


def insider_summary(ticker) -> dict:
    try:
        df = ticker.insider_transactions
        if df is None or df.empty:
            return {"available": False}
        recent = df.head(15)
        text = " ".join(str(x).lower() for x in recent.get("Text", []))
        buys = text.count("buy") + text.count("purchase")
        sells = text.count("sale") + text.count("sell")
        return {
            "available": True,
            "recent_records": int(len(recent)),
            "buy_mentions": buys,
            "sell_mentions": sells,
            "net_signal": "net buying" if buys > sells else
                          "net selling" if sells > buys else "balanced",
        }
    except Exception:
        return {"available": False}


def institutional_summary(ticker) -> dict:
    try:
        df = ticker.institutional_holders
        if df is None or df.empty:
            return {"available": False}
        top = df.head(10)
        return {
            "available": True,
            "top_holders": [
                {
                    "holder": str(r.get("Holder")),
                    "shares": r.get("Shares"),
                    "pct_out": round_or_none(r.get("pctHeld") * 100)
                    if r.get("pctHeld") is not None else None,
                }
                for _, r in top.iterrows()
            ],
            "note": "13F holdings lag by up to ~45 days; treat as quarterly positioning, "
                    "not live flow.",
        }
    except Exception:
        return {"available": False}


def main() -> None:
    symbol = require_symbol(sys.argv)
    ticker = get_ticker(symbol)
    info = safe_info(ticker)

    short_pct_float = info.get("shortPercentOfFloat")
    emit({
        "symbol": symbol,
        "short_interest": {
            "shares_short": info.get("sharesShort"),
            "short_pct_of_float": round_or_none(short_pct_float * 100)
            if short_pct_float is not None else None,
            "short_ratio_days_to_cover": round_or_none(info.get("shortRatio")),
            "shares_short_prior_month": info.get("sharesShortPriorMonth"),
        },
        "analyst_trend": {
            "recommendation_key": info.get("recommendationKey"),
            "recommendation_mean": round_or_none(info.get("recommendationMean")),
            "num_opinions": info.get("numberOfAnalystOpinions"),
        },
        "insider_transactions": insider_summary(ticker),
        "institutional_holders": institutional_summary(ticker),
        "web_search_terms": [
            f"{symbol} 13F changes latest quarter hedge fund",
            f"{symbol} insider buying selling SEC Form 4",
            f"{symbol} short interest update",
        ],
        "note": "Combine these with web search for the freshest 13F/Form 4 filings.",
    })


if __name__ == "__main__":
    main()

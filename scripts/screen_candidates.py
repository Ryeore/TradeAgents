#!/usr/bin/env python
"""screen_candidates.py -- opportunity screener for the Opportunity Scout agent.

Ranks a universe of tickers by a blended value / quality / momentum score so the
desk can surface NEW candidates worth a full work-up. No API keys required.

Usage:
    python scripts/screen_candidates.py AAPL MSFT NVDA
    python scripts/screen_candidates.py --preset wse_blue --top 5
    python scripts/screen_candidates.py --universe watchlist.txt --min-score 55
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import (  # noqa: E402
    emit, get_ticker, history, last_price, round_or_none, rsi, safe_info, sma,
)

PRESETS = {
    "wse_blue": ["KRU.WA", "XTB.WA", "DIA.WA", "CBF.WA", "ACP.WA", "PKO.WA",
                 "MBR.WA", "SNT.WA","ASB.WA"],
    "us_mega": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "MU"],
}


# TEMP_PRESETS = {
#     "wse_blue": ["KRU.WA", "XTB.WA", "DIA.WA", "CBF.WA", "ACP.WA", "PKO.WA",
#                  "MBR.WA", "SNT.WA", "PKN.WA", "PEO.WA", "DNP.WA", "ALE.WA",
#                  "CDR.WA", "LPP.WA", "KGH.WA", "PZU.WA", "EBP.WA", "OPL.WA"],
#     "us_mega": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA"],
# }


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def scale(val, lo, hi):
    """Map val from [lo,hi] onto [0,100], clamped. hi<lo inverts (lower=better)."""
    if val is None:
        return None
    if hi == lo:
        return 50.0
    return clamp((val - lo) / (hi - lo) * 100.0)


def _pct(v):
    """yfinance returns some ratios as fractions; normalise to percent."""
    if v is None:
        return None
    return v * 100 if abs(v) < 5 else v


def screen_one(symbol):
    ticker = get_ticker(symbol)
    info = safe_info(ticker)
    price = last_price(ticker, info)
    df = history(ticker, period="1y")

    target = info.get("targetMeanPrice")
    upside = (target / price - 1) * 100 if price and target else None
    pe_fwd = info.get("forwardPE")
    pb = info.get("priceToBook")
    div = info.get("dividendYield")
    div = div * 100 if div and div < 1 else div
    roe = _pct(info.get("returnOnEquity"))
    rev_g = _pct(info.get("revenueGrowth"))

    ret6m = ma50 = ma200 = rsi14 = above50 = above200 = None
    if not df.empty and len(df) > 60:
        close = df["Close"]
        if len(close) >= 126:
            ret6m = round_or_none((close.iloc[-1] / close.iloc[-126] - 1) * 100)
        ma50 = round_or_none(sma(close, 50).iloc[-1])
        ma200_series = sma(close, 200)
        ma200 = round_or_none(ma200_series.iloc[-1]) if ma200_series.notna().any() else None
        rsi14 = round_or_none(rsi(close, 14).iloc[-1])
        if price and ma50:
            above50 = price > ma50
        if price and ma200:
            above200 = price > ma200

    value_parts = [scale(upside, -20, 40), scale(pe_fwd, 40, 5),
                   scale(pb, 8, 0.5), scale(div, 0, 8)]
    quality_parts = [scale(roe, 0, 30), scale(rev_g, 0, 40)]
    momentum_parts = [scale(ret6m, -30, 40), scale(rsi14, 30, 70),
                      (100.0 if above50 else 0.0) if above50 is not None else None,
                      (100.0 if above200 else 0.0) if above200 is not None else None]

    def avg(parts):
        vals = [p for p in parts if p is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    value_s, quality_s, momentum_s = avg(value_parts), avg(quality_parts), avg(momentum_parts)
    overall = [s for s in (value_s, quality_s, momentum_s) if s is not None]
    screen_score = round(sum(overall) / len(overall), 1) if overall else None

    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName"),
        "price": round_or_none(price),
        "currency": info.get("currency"),
        "screen_score": screen_score,
        "value_score": value_s,
        "quality_score": quality_s,
        "momentum_score": momentum_s,
        "signals": {
            "analyst_upside_pct": round_or_none(upside),
            "pe_forward": round_or_none(pe_fwd),
            "price_to_book": round_or_none(pb),
            "dividend_yield_pct": round_or_none(div),
            "roe_pct": round_or_none(roe),
            "revenue_growth_pct": round_or_none(rev_g),
            "return_6m_pct": ret6m,
            "rsi14": rsi14,
            "above_ma50": above50,
            "above_ma200": above200,
        },
    }


def load_universe(args):
    tickers = list(PRESETS.get(args.preset, [])) if args.preset else []
    if args.universe:
        with open(args.universe, "r", encoding="utf-8") as fh:
            for ln in fh:
                ticker = ln.split("#")[0].strip().upper()
                if ticker:
                    tickers.append(ticker)
    tickers += [t.upper() for t in args.tickers]
    seen, out = set(), []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def main():
    p = argparse.ArgumentParser(description="Rank a universe by value/quality/momentum.")
    p.add_argument("tickers", nargs="*", help="Ticker symbols, e.g. AAPL KRU.WA")
    p.add_argument("--preset", choices=sorted(PRESETS), help="Built-in watchlist")
    p.add_argument("--universe", help="Path to a file with one ticker per line")
    p.add_argument("--top", type=int, default=0, help="Keep only the top N (0 = all)")
    p.add_argument("--min-score", type=float, default=0.0, help="Drop below this score")
    args = p.parse_args()

    universe = load_universe(args)
    if not universe:
        raise SystemExit("No tickers. Pass symbols, --preset, or --universe.")

    rows = []
    for sym in universe:
        try:
            rows.append(screen_one(sym))
        except Exception as exc:
            rows.append({"symbol": sym, "error": str(exc), "screen_score": None})

    ranked = sorted(rows, key=lambda r: (r.get("screen_score") is not None,
                                         r.get("screen_score") or 0), reverse=True)
    ranked = [r for r in ranked if r.get("screen_score") is None
              or r["screen_score"] >= args.min_score]
    if args.top:
        ranked = ranked[:args.top]

    emit({
        "universe_size": len(universe),
        "ranked": ranked,
        "method": "screen_score = mean(value, quality, momentum), each 0-100, None-tolerant. "
                  "Value=upside+low fwd P/E+low P/B+yield; Quality=ROE+revenue growth; "
                  "Momentum=6m return+RSI+price>MA50/MA200.",
        "next_step": "Take the top names into data-scout / the analyst-desk for a full work-up. "
                     "Screen score is a coarse filter, NOT a buy signal.",
        "disclaimer": "Educational screen, not financial advice. yfinance fields can be missing "
                      "for non-US listings; verify before acting.",
    })


if __name__ == "__main__":
    main()

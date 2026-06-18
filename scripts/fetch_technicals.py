#!/usr/bin/env python
"""fetch_technicals.py -- chart read for the Chartist agent.

MA20/50/200, RSI(14), MFI(14), ATR(14), 52-week Fibonacci retracement levels,
and a simple structure/entry summary.

Usage:
    python scripts/fetch_technicals.py NVDA
    python scripts/fetch_technicals.py NVDA 2y       # custom lookback
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import (  # noqa: E402
    atr, emit, fibonacci_levels, get_ticker, history, mfi, require_symbol,
    round_or_none, rsi, sma,
)


def main() -> None:
    symbol = require_symbol(sys.argv)
    period = sys.argv[2] if len(sys.argv) > 2 else "1y"

    ticker = get_ticker(symbol)
    df = history(ticker, period=period)
    if df.empty or len(df) < 30:
        emit({"symbol": symbol, "error": "insufficient price history"})
        return

    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]
    price = float(close.iloc[-1])

    ma20 = sma(close, 20).iloc[-1]
    ma50 = sma(close, 50).iloc[-1]
    ma200 = sma(close, 200).iloc[-1] if len(df) >= 200 else None
    rsi14 = rsi(close).iloc[-1]
    mfi14 = mfi(high, low, close, vol).iloc[-1]
    atr14 = atr(high, low, close).iloc[-1]

    swing_high = float(high.tail(252).max())
    swing_low = float(low.tail(252).min())
    fib = fibonacci_levels(swing_high, swing_low)

    def above(ma):
        return None if ma is None else bool(price > ma)

    trend = "n/a"
    if ma50 is not None and ma200 is not None:
        if price > ma50 > ma200:
            trend = "uptrend (price > MA50 > MA200)"
        elif price < ma50 < ma200:
            trend = "downtrend (price < MA50 < MA200)"
        else:
            trend = "mixed / transitional"

    rsi_zone = ("overbought" if rsi14 >= 70 else
                "oversold" if rsi14 <= 30 else "neutral")

    emit({
        "symbol": symbol,
        "period": period,
        "price": round_or_none(price),
        "moving_averages": {
            "ma20": round_or_none(ma20),
            "ma50": round_or_none(ma50),
            "ma200": round_or_none(ma200),
            "above_ma20": above(ma20),
            "above_ma50": above(ma50),
            "above_ma200": above(ma200),
        },
        "momentum": {
            "rsi14": round_or_none(rsi14),
            "rsi_zone": rsi_zone,
            "mfi14": round_or_none(mfi14),
            "mfi_zone": ("overbought" if mfi14 >= 80 else
                         "oversold" if mfi14 <= 20 else "neutral"),
        },
        "volatility": {
            "atr14": round_or_none(atr14),
            "atr_pct_of_price": round_or_none(atr14 / price * 100),
        },
        "fibonacci_52w": fib,
        "swing_high_52w": round_or_none(swing_high),
        "swing_low_52w": round_or_none(swing_low),
        "trend": trend,
        "note": "ATR drives stop placement in position_sizer. Fib levels are candidate "
                "DCA/entry zones; confirm with structure before acting.",
    })


if __name__ == "__main__":
    main()

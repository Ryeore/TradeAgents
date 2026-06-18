#!/usr/bin/env python
"""fetch_fundamentals.py -- valuation & quality for the Data Hunter agent.

P/E, EV/EBITDA, FCF yield, ROIC (best-effort), margins, returns, insider &
institutional ownership, leverage.

Usage:
    python scripts/fetch_fundamentals.py MSFT
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import (  # noqa: E402
    emit, get_ticker, require_symbol, round_or_none, safe_info,
)


def best_effort_roic(ticker) -> float | None:
    """ROIC = NOPAT / Invested Capital, approximated from yfinance statements.

    NOPAT ~= EBIT * (1 - effective tax rate)
    Invested Capital ~= Total Debt + Total Equity - Cash
    Returns a percentage or None when data is missing.
    """
    try:
        fin = ticker.financials
        bs = ticker.balance_sheet
        if fin is None or bs is None or fin.empty or bs.empty:
            return None

        def row(df, *names):
            for n in names:
                if n in df.index:
                    return df.loc[n].iloc[0]
            return None

        ebit = row(fin, "EBIT", "Operating Income")
        pretax = row(fin, "Pretax Income", "Income Before Tax")
        tax = row(fin, "Tax Provision", "Income Tax Expense")
        if ebit is None:
            return None
        tax_rate = float(tax) / float(pretax) if pretax and tax is not None else 0.21
        tax_rate = min(max(tax_rate, 0.0), 0.45)
        nopat = float(ebit) * (1 - tax_rate)

        debt = row(bs, "Total Debt") or 0
        equity = row(bs, "Stockholders Equity", "Total Stockholder Equity",
                     "Common Stock Equity") or 0
        cash = row(bs, "Cash And Cash Equivalents",
                   "Cash Cash Equivalents And Short Term Investments") or 0
        invested = float(debt) + float(equity) - float(cash)
        if invested <= 0:
            return None
        return round((nopat / invested) * 100, 2)
    except Exception:
        return None


def main() -> None:
    symbol = require_symbol(sys.argv)
    ticker = get_ticker(symbol)
    info = safe_info(ticker)

    market_cap = info.get("marketCap")
    fcf = info.get("freeCashflow")
    fcf_yield = None
    if fcf and market_cap:
        fcf_yield = round_or_none((fcf / market_cap) * 100)

    def pct(key):
        v = info.get(key)
        return round_or_none(v * 100) if v is not None else None

    emit({
        "symbol": symbol,
        "name": info.get("longName") or info.get("shortName"),
        "valuation": {
            "pe_trailing": round_or_none(info.get("trailingPE")),
            "pe_forward": round_or_none(info.get("forwardPE")),
            "peg_ratio": round_or_none(info.get("pegRatio") or info.get("trailingPegRatio")),
            "price_to_sales": round_or_none(info.get("priceToSalesTrailing12Months")),
            "price_to_book": round_or_none(info.get("priceToBook")),
            "ev_to_ebitda": round_or_none(info.get("enterpriseToEbitda")),
            "ev_to_revenue": round_or_none(info.get("enterpriseToRevenue")),
            "fcf_yield_pct": fcf_yield,
        },
        "quality": {
            "roic_pct_est": best_effort_roic(ticker),
            "roe_pct": pct("returnOnEquity"),
            "roa_pct": pct("returnOnAssets"),
            "gross_margin_pct": pct("grossMargins"),
            "operating_margin_pct": pct("operatingMargins"),
            "net_margin_pct": pct("profitMargins"),
            "revenue_growth_pct": pct("revenueGrowth"),
            "earnings_growth_pct": pct("earningsGrowth"),
        },
        "balance_sheet": {
            "total_cash": info.get("totalCash"),
            "total_debt": info.get("totalDebt"),
            "debt_to_equity": round_or_none(info.get("debtToEquity")),
            "current_ratio": round_or_none(info.get("currentRatio")),
            "quick_ratio": round_or_none(info.get("quickRatio")),
        },
        "ownership": {
            "insider_pct": pct("heldPercentInsiders"),
            "institutional_pct": pct("heldPercentInstitutions"),
        },
        "dividend": {
            "yield_pct": pct("dividendYield") if (info.get("dividendYield") or 0) < 1
            else round_or_none(info.get("dividendYield")),
            "payout_ratio_pct": pct("payoutRatio"),
        },
        "note": "roic_pct_est is approximated from yfinance statements (EBIT*(1-tax)/invested "
                "capital). Treat as directional, not GAAP-exact.",
    })


if __name__ == "__main__":
    main()

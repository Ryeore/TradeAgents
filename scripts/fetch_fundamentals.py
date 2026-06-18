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


def get_forward_estimates(ticker) -> dict:
    """Extract analyst forward estimates for the next 1–2 fiscal years.

    yfinance provides +1y directly. +2y is extrapolated by applying the
    same year-on-year growth rate a second time — clearly flagged in output.
    Returns a dict with all values or None when data is unavailable.
    """
    result: dict = {
        "eps_next_fy": None,
        "eps_next_fy_num_analysts": None,
        "eps_2y_ahead_est": None,
        "eps_2y_avg_growth_pct": None,
        "revenue_next_fy": None,
        "revenue_next_fy_num_analysts": None,
        "revenue_2y_ahead_est": None,
        "estimate_note": None,
    }
    try:
        ee = ticker.earnings_estimate
        re = ticker.revenue_estimate
        notes = []

        if ee is not None and not ee.empty and "+1y" in ee.index:
            row_1y = ee.loc["+1y"]
            eps_1y = float(row_1y["avg"]) if row_1y["avg"] is not None else None
            result["eps_next_fy"] = round_or_none(eps_1y)
            n = row_1y.get("numberOfAnalysts")
            result["eps_next_fy_num_analysts"] = int(n) if n is not None else None

            # 2Y extrapolation: apply +1y growth again
            growth_1y = float(row_1y["growth"]) if row_1y.get("growth") is not None else None
            if eps_1y is not None and growth_1y is not None:
                eps_2y = eps_1y * (1.0 + growth_1y)
                result["eps_2y_ahead_est"] = round_or_none(eps_2y)
                notes.append("+2y EPS extrapolated (applying +1y growth rate a second time)")

            # 2Y avg annual growth: CAGR from 0y to +1y
            if "0y" in ee.index:
                eps_0y = float(ee.loc["0y"]["avg"]) if ee.loc["0y"]["avg"] is not None else None
                if eps_0y and eps_1y and eps_0y > 0:
                    cagr_2y = round_or_none((((eps_1y / eps_0y) ** 0.5) - 1.0) * 100)
                    result["eps_2y_avg_growth_pct"] = cagr_2y

        if re is not None and not re.empty and "+1y" in re.index:
            row_r1y = re.loc["+1y"]
            rev_1y = float(row_r1y["avg"]) if row_r1y["avg"] is not None else None
            result["revenue_next_fy"] = rev_1y
            n = row_r1y.get("numberOfAnalysts")
            result["revenue_next_fy_num_analysts"] = int(n) if n is not None else None

            growth_r1y = float(row_r1y["growth"]) if row_r1y.get("growth") is not None else None
            if rev_1y is not None and growth_r1y is not None:
                rev_2y = rev_1y * (1.0 + growth_r1y)
                result["revenue_2y_ahead_est"] = rev_2y
                notes.append("+2y Revenue extrapolated (applying +1y growth rate a second time)")

        if notes:
            result["estimate_note"] = "; ".join(notes)
    except Exception:
        pass
    return result


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
        "forward_estimates": get_forward_estimates(ticker),
        "note": "roic_pct_est is approximated from yfinance statements (EBIT*(1-tax)/invested "
                "capital). Treat as directional, not GAAP-exact. "
                "forward_estimates +2y values are extrapolated, not directly sourced.",
    })


if __name__ == "__main__":
    main()

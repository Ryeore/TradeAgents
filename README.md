# Stock Scripts Toolkit

Script-first toolkit for stock screening, technical/fundamental snapshots, score aggregation, and budget allocation.

This repository now keeps only the deterministic Python workflow under `scripts/`. The former CrewAI orchestration layer has been removed.

> Not financial advice. This is an educational research and risk-management toolkit.

---

## Quickstart

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Smoke-test the core scripts:

```powershell
python scripts/fetch_quote.py AAPL
python scripts/fetch_fundamentals.py MSFT
python scripts/fetch_technicals.py NVDA
python scripts/fetch_sentiment.py TSLA
python scripts/fetch_macro.py AMD
python scripts/scorecard.py --valuation 7 --quality 8 --technical 6 --sentiment 5 --macro 6
python scripts/position_sizer.py --price 100 --atr 3.2 --conviction 7 --account 50000
```

---

## Main Scripts

| Script | Purpose |
|---|---|
| `fetch_quote.py` | Live quote, analyst targets, earnings context |
| `fetch_fundamentals.py` | Fundamental and valuation snapshot |
| `fetch_technicals.py` | Trend, RSI, MFI, ATR, Fibonacci levels |
| `fetch_sentiment.py` | Short interest, analyst trend, insider/institutional context |
| `fetch_macro.py` | Rates and sector-relative macro backdrop |
| `screen_candidates.py` | Multi-factor ranking across a watchlist or universe |
| `portfolio_allocator.py` | Converts ranked candidates into a whole-share buy plan |
| `position_sizer.py` | Risk-based position sizing for a single name |
| `scorecard.py` | Weighted composite score and verdict band |
| `view_results.py` | Terminal and Markdown dashboards for screen/allocation outputs |

WSE names require the `.WA` suffix, for example `CDR.WA` or `KRU.WA`.

---

## Core Workflow

### Screen a universe

```powershell
python scripts/screen_candidates.py --preset wse_blue --top 8 > screen.json
```

### Allocate a budget across the shortlist

```powershell
python scripts/portfolio_allocator.py --budget 2000 --candidates-file screen.json --top 6 > alloc.json
```

### Render readable dashboards

```powershell
python scripts/view_results.py --screen-file screen.json --top 10
python scripts/view_results.py --screen-file screen.json --allocation-file alloc.json --top 10 --out-md output/dashboard.md
```

---

## Portfolio Allocation

The `--portfolio` flow answers *“I have 2000 PLN — which stocks and what %?”*: the
Opportunity Scout screens the universe, then the Portfolio Manager splits the
budget across the best-scored names. The math lives in
[`scripts/portfolio_allocator.py`](scripts/portfolio_allocator.py) and runs
standalone:

```powershell
python scripts/screen_candidates.py --preset wse_blue --top 8 > screen.json
python scripts/portfolio_allocator.py --budget 2000 --candidates-file screen.json --top 6
```

Typical sample workflows:

```powershell
# WSE flow: screen -> allocate -> review
python scripts/screen_candidates.py --preset wse_blue --top 12 > screen_wse.json
python scripts/portfolio_allocator.py --budget 5000 --candidates-file screen_wse.json --top 6 > alloc_wse.json
python scripts/view_results.py --screen-file screen_wse.json --allocation-file alloc_wse.json --top 10 --out-md output/dashboard.md

# US flow: screen -> allocate -> review
python scripts/screen_candidates.py --preset us_mega --top 15 > screen_us.json
python scripts/portfolio_allocator.py --budget 2000 --candidates-file screen_us.json --top 8 > alloc_us.json
python scripts/view_results.py --screen-file screen_us.json --allocation-file alloc_us.json --top 10 --out-md output/dashboard.md

# ALL flow: screen -> allocate -> review
python scripts/screen_candidates.py --preset all --top 15 > screen_us.json
python scripts/portfolio_allocator.py --budget 2000 --candidates-file screen_all.json --top 8 > alloc_all.json
python scripts/view_results.py --screen-file screen_all.json --allocation-file alloc_all.json --top 10 --out-md output/dashboard.md

# Current portfolio flow: screen -> allocate -> review
python scripts/screen_candidates.py --preset current_portfolio --top 12 > screen_current_portfolio.json
python scripts/portfolio_allocator.py --budget 2000 --candidates-file screen_current_portfolio.json --top 8 > alloc_current_portfolio.json
python scripts/view_results.py --screen-file screen_current_portfolio.json --allocation-file alloc_current_portfolio.json --top 10 --out-md output/dashboard.md
```

### Better result visibility (terminal + markdown dashboard)

Use the dashboard utility to render cleaner, side-by-side summaries from raw JSON:

```powershell
# Screen table (rank, score, trend, sentiment, risk, confidence)
python scripts/view_results.py --screen-file screen.json --top 10

# Combined screen + allocation table and markdown report
python scripts/portfolio_allocator.py --budget 2000 --candidates-file screen.json --top 6 > alloc.json
python scripts/view_results.py --screen-file screen.json --allocation-file alloc.json --top 10 --out-md output/dashboard.md
```

What you get:

- Terminal dashboards for fast readout during iteration.
- A markdown report at [output/dashboard.md](output/dashboard.md) for sharing, journaling, or diffing runs.
- Confidence tags (`HIGH`/`MED`/`LOW`) plus score source visibility in allocation rows.

The first command writes the screener output to `screen.json`. The second reads
that file and converts the ranked candidates into a concrete buy plan using the
requested cash budget and top-N cutoff.

How to read the screener output (`screen.json`):

- Top-level metadata: `universe_size`, `method`, `next_step`, `disclaimer`.
- Main payload: `ranked` is the ordered candidate list, best first.
- Per stock (core): `symbol`, `price`, `screen_score`, `raw_screen_score`,
  `confidence_score`, `value_score`, `quality_score`, `trend_score`,
  `momentum_score` (alias of `trend_score`), `sentiment_score`, `risk_score`.
- Per stock (details): `signals` includes the raw factor inputs and
  `data_quality` includes coverage diagnostics.

In practice, read `ranked[0]`, `ranked[1]`, and so on as your shortlist. The
most important field is `screen_score`: higher means a stronger blended
value/quality/trend/sentiment/risk candidate for deeper analysis, not an
automatic buy.

How `screen_score` is calculated:

- The screener builds 5 pillar scores (0-100):
  - Value (20%): upside, valuation and cash-flow yield style inputs.
  - Quality (20%): profitability and growth quality inputs.
  - Trend (30%): multi-horizon returns + MA structure/slope + RSI and 52w context.
  - Sentiment (20%): recommendation trend, analyst coverage, short interest.
  - Risk (10%): ATR% and drawdown stability context.
- Most sub-factors are normalized as within-universe percentiles, which improves
  comparability across mixed universes and regimes.
- `raw_screen_score` is the weighted blend before confidence adjustment.
- `screen_score` applies a data-confidence multiplier from coverage
  (`confidence_score`) so sparse-data names are penalized instead of over-ranked.

How allocation uses that score:

- The allocator does not recompute fundamentals/technicals.
- It computes `allocation_score` per candidate.
- Default behavior (`portfolio_allocator.py`) uses component scores when present:
  weighted value/quality/trend/sentiment/risk, with optional confidence
  adjustment.
- If components are missing (or `--use-legacy-score` is passed), it falls back to
  legacy score fields (`score`, then `screen_score`, then `conviction`).
- If computed size is at least `--min-fractional-share` (default `0.5`) but below
  one full share, the allocator rounds up to one share and trims back weaker
  rounded names if needed to stay within budget.
- Position concentration still scales as `allocation_score ** score_power`.
- Those raw weights are normalized, capped by `--max-weight`, converted to
  whole shares, and then adjusted by leftover-cash sweep.

Useful allocator switches:

- `--use-legacy-score`: disable component mode and use legacy score fields only.
- `--no-confidence`: disable confidence-based penalty/adjustment.
- `--confidence-floor 0.7`: minimum confidence multiplier.
- `--min-fractional-share 0.5`: round small positions up to one share when the
  target size is at least this fraction.
- `--w-value`, `--w-quality`, `--w-trend`, `--w-sentiment`, `--w-risk`:
  override component weights for allocation.

How to read the portfolio allocation output:

- `budget`: the total cash you asked the allocator to deploy.
- `params`: the rules used for the run, including currency context.
  - `budget_currency`: always `PLN` (the allocator treats `--budget` as PLN).
  - `fx_usdpln`: USD→PLN rate used to convert US tickers before sizing.
  - `max_weight_pct`, `min_score`, `top`, `score_power`, `cash_reserve_pct`,
    `leftover_sweep`: allocation controls.
- `allocations`: the actual buy plan, one row per selected stock.
- Per allocation row:
  - `symbol`: ticker.
  - `currency`: instrument currency (`PLN` or `USD`).
  - `price`: native instrument price (e.g., USD for US stocks).
  - `price_pln`: normalized PLN price used by the allocator math.
  - `allocation_score`: effective score used for weighting.
  - `allocation_score_source`: whether score came from components or legacy fallback.
  - `score` / `screen_score` / `conviction`: pass-through source fields for traceability.
  - `confidence_score`: confidence percentage used if confidence mode is enabled.
  - component fields (`value_score`, `quality_score`, `trend_score`,
    `sentiment_score`, `risk_score`) when available.
  - `target_weight_pct`: model target before whole-share rounding.
  - `shares`: integer shares to buy.
  - `cost` / `cost_pln`: planned spend in PLN for that row.
  - `actual_weight_pct`: realized portfolio weight after rounding.
- `summary`: total `deployed`, `leftover_cash`, `cash_pct`, number of
  positions, names dropped because they were too expensive to buy even
  one share, and which names were rounded up or trimmed.

Example interpretation of a sample row:

```json
{
  "budget": 5000.0,
  "params": {
    "budget_currency": "PLN",
    "fx_usdpln": 3.78345,
    "max_weight_pct": 35.0,
    "min_score": 0.0,
    "top": 10,
    "score_power": 1.5,
    "cash_reserve_pct": 0.0,
    "leftover_sweep": true
  },
  "allocations": [
    {
      "symbol": "XTB.WA",
      "currency": "PLN",
      "price": 123.08,
      "price_pln": 123.08,
      "allocation_score": 76.6,
      "allocation_score_source": "components+confidence",
      "score": 76.6,
      "target_weight_pct": 12.42,
      "shares": 14,
      "cost": 1723.12,
      "cost_pln": 1723.12,
      "actual_weight_pct": 34.46
    }
  ]
}
```

In this example, your total budget is `5000 PLN`. The model first computes
target weights from allocation scores (`score_power=1.5`), then applies the 35% cap and
whole-share rounding. For `XTB.WA`, buying `14` shares at `123.08 PLN` spends
`1723.12 PLN`, which is `34.46%` of the full budget.

If a row were a US stock, `currency` would be `USD`, `price` would be in USD,
and `price_pln` would equal `price * fx_usdpln`; sizing and `cost_pln` are
always computed in PLN.

Start with `allocations` if you want the actionable result. `target_weight_pct`
shows the model's ideal weighting before whole-share rounding, while
`actual_weight_pct` shows what was really achieved after converting the budget
into buyable share counts.

Weights scale with each name's effective allocation score (`allocation_score ** score_power`), are **capped per
name** (`--max-weight`, default 35%), converted to **whole shares**, and any
leftover cash is **swept** into the highest-scored affordable names so the budget
is actually deployed. In component mode, this score is the computed
`allocation_score`; in legacy mode, it is the fallback raw score.
Pass `--holdings-file` (a `[{symbol, value}]` JSON) to see
the *combined* portfolio weights after the new money lands.

## The 5-dimension scorecard

The CIO scores each stock 1–10 on **Valuation, Quality, Technical, Sentiment,
Macro**, then `scorecard.py` produces a weighted composite and a verdict band:

| Composite | Verdict |
|-----------|---------|
| ≥ 8.0 | STRONG BUY |
| ≥ 6.5 | BUY |
| ≥ 5.0 | ACCUMULATE / STARTER |
| ≥ 3.5 | HOLD / WATCH |
| < 3.5 | AVOID / SELL |

Default weights live in `scripts/scorecard.py` and can be overridden per thesis.

---

## Position sizing logic (`position_sizer.py`)

- **Risk-based shares** = `(account × risk%) ÷ (ATR_stop_mult × ATR)` — caps loss
  at the stop to your risk budget (default 1% of account).
- **Conviction-capped shares** scales the max position weight with the CIO score.
- **Final size = min(risk-based, conviction-capped)** so a stop-out never breaches
  the budget; the output names the **binding constraint**.
- **DCA tranches**: scale-in limit prices spaced by ATR, weighted heavier lower.
- **Stop**: `entry − ATR_stop_mult × ATR`. **Targets**: fixed R multiples (2R / 4R).

---

## Notes & limitations

- `roic_pct_est` is approximated from yfinance statements — directional, not
  GAAP-exact.
- yfinance fields can lag intraday and 13F/short data is delayed; the skills lean
  on **live web search** for anything time-sensitive (earnings surprises, news,
  fresh filings, Fed stance).
- `^TNX` is the 10-year yield ×10 (e.g. `42.5` → `4.25%`).

## Repo layout

```
TradeAgents/
├─ README.md
├─ requirements.txt
├─ lib/common.py            # yfinance wrappers + indicators (RSI, MFI, ATR, Fib)
├─ scripts/                 # deterministic data + math tools (JSON out)
├─ skills/                  # markdown playbooks / research templates
├─ pyproject.toml           # lightweight project metadata
├─ watchlists/              # ticker lists for screen_candidates.py
├─ agentReports/            # auto-generated per-seat reports (gitignored)
└─ output/                  # auto-generated reports (gitignored)
```

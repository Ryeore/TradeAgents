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
python scripts/screen_candidates.py --preset wse --top 12 > screen_wse.json
python scripts/portfolio_allocator.py --budget 5000 --candidates-file screen_wse.json --top 6 > alloc_wse.json
python scripts/view_results.py --screen-file screen_wse.json --allocation-file alloc_wse.json --top 10 --out-md output/dashboard.md

# US flow: screen -> allocate -> review
python scripts/screen_candidates.py --preset us100 --top 15 > screen_us.json
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

### How to read the screener output (`screen.json`)

In practice, read `ranked[0]`, `ranked[1]`, and so on as your shortlist. The
most important field is `screen_score`: higher means a stronger blended
value/quality/trend/sentiment/risk candidate for deeper analysis, not an
automatic buy. Every field the screener emits is described below.

**Top-level fields**

| Field | Description |
|---|---|
| `universe_size` | Number of tickers screened in this run. |
| `ranked` | Ordered candidate list, best `screen_score` first. |
| `method` | One-line summary of the scoring formula and pillar weights. |
| `next_step` | Reminder that the screen is a coarse filter, not a buy signal. |
| `disclaimer` | Educational-use and data-coverage caveat. |

**Per-candidate identity & headline scores** (each entry in `ranked`)

| Field | Range | Description |
|---|---|---|
| `symbol` | — | Ticker (WSE names carry the `.WA` suffix). |
| `name` | — | Company short/long name from yfinance. |
| `price` | native ccy | Last traded price in the instrument's own currency. |
| `currency` | — | Instrument currency (`PLN`, `USD`, …). |
| `screen_score` | 0–100 | **Headline rank.** `raw_screen_score` after the data-confidence multiplier. Higher = stronger blended candidate for deeper work, not an auto-buy. |
| `raw_screen_score` | 0–100 | Weighted blend of the 5 pillars **before** confidence adjustment. |
| `confidence_score` | 0–100 | Share of the 13 key inputs that were available (data coverage %). Drives the confidence multiplier. |
| `value_score` | 0–100 | Value pillar (weight 20%). |
| `quality_score` | 0–100 | Quality pillar (weight 20%). |
| `trend_score` | 0–100 | Trend pillar (weight 30%). |
| `momentum_score` | 0–100 | Backward-compatible alias of `trend_score`. |
| `sentiment_score` | 0–100 | Sentiment pillar (weight 20%). |
| `risk_score` | 0–100 | Risk pillar (weight 10%). |

Each pillar is the average of several 0–100 sub-scores. A `null` pillar means
every input for that pillar was missing; missing pillars are dropped and the
remaining weights are re-normalized.

**`signals` — raw factor inputs (pre-normalization)**

These are the untouched yfinance / price-history values that feed the pillars.
"Direction" shows which way is better once the factor is converted to a 0–100
score.

*Value pillar inputs*

| Field | Unit | Direction | Description |
|---|---|---|---|
| `analyst_upside_pct` | % | higher | Mean analyst target vs price: `(targetMean/price − 1) × 100`. |
| `pe_forward` | ratio | lower | Forward P/E (price ÷ next-year EPS estimate). |
| `price_to_book` | ratio | lower | Price-to-book multiple. |
| `dividend_yield_pct` | % | higher | Trailing dividend yield (values > 25% treated as bad data and dropped). |
| `fcf_yield_pct` | % | higher | Free cash flow ÷ market cap: `freeCashflow/marketCap × 100`. |

*Quality pillar inputs*

| Field | Unit | Direction | Description |
|---|---|---|---|
| `roe_pct` | % | higher | Return on equity. |
| `revenue_growth_pct` | % | higher | Year-over-year revenue growth. |
| `operating_margin_pct` | % | higher | Operating margin. |
| `gross_margin_pct` | % | higher | Gross margin. |

*Trend pillar inputs*

| Field | Unit | Direction | Description |
|---|---|---|---|
| `return_3m_pct` | % | higher | 3-month price return (~63 sessions). |
| `return_6m_pct` | % | higher | 6-month price return (~126 sessions). |
| `rsi14` | 0–100 | sweet spot | 14-period RSI; scored best near 57, decaying with distance. |
| `above_ma50` | bool | — | Whether price > 50-day MA (informational). |
| `above_ma200` | bool | — | Whether price > 200-day MA (informational). |
| `price_vs_ma200_pct` | % | higher | Price distance above/below the 200-day MA. |
| `ma50_vs_ma200_pct` | % | higher | 50-day vs 200-day MA spread (golden/death-cross proxy). |
| `ma200_slope_3m_pct` | % | higher | 200-day MA slope over the last ~3 months (trend direction). |
| `proximity_52w_high_pct` | % | sweet spot | Price as a % of the 52-week high; scored best near 97%. |

The trend pillar also adds a moving-average `structure_score` (100 when
price > MA20 > MA50 > MA200, stepping down through 80 / 60 to 20). The 20/50/200-day
SMAs it uses are computed internally and are **not** emitted in `signals`; the
`above_ma50` / `above_ma200` booleans are emitted for reference.

*Sentiment pillar inputs*

| Field | Unit | Direction | Description |
|---|---|---|---|
| `recommendation_mean` | 1–5 | lower | Analyst consensus (1 = Strong Buy … 5 = Sell). |
| `analyst_opinions` | count | higher | Number of covering analysts; scaled 0 → 30. |
| `short_interest_pct_float` | % | lower | Short interest as a % of float. |

*Risk pillar inputs*

| Field | Unit | Direction | Description |
|---|---|---|---|
| `atr_pct_of_price` | % | sweet spot | 14-day ATR ÷ price; scored best near 4% (too calm or too wild both penalized). |
| `max_drawdown_6m_pct` | % | higher | Worst peak-to-trough drop over 6 months (closer to 0 = better). |
| `return_12m_pct` | % | higher | 12-month price return (~252 sessions), scaled −40 → 60 as a stability/regime input (scored in the **risk** pillar). |
| `atr14` | native ccy | — | Raw 14-day ATR in price units (informational; feeds `atr_pct_of_price`). |

**`data_quality` — coverage diagnostics**

| Field | Description |
|---|---|
| `coverage_ratio` | Fraction (0–1) of the 13 required inputs that were present. |
| `coverage_pct` | Same as `coverage_ratio` expressed as a percent (mirrors `confidence_score`). |

**How the raw signals become 0–100 sub-scores**

- **Percentile** (most factors): rank within the screened universe, so scores are
  relative to this run's peer set. Direction flips for "lower-is-better" factors
  (P/E, P/B, `recommendation_mean`, short interest).
- **Sweet spot**: peaks at a target and decays linearly with distance — used for
  `rsi14` (57), `proximity_52w_high_pct` (97) and `atr_pct_of_price` (4).
- **Structure**: discrete moving-average stack score (100 / 80 / 60 / 20).
- **Linear scale**: mapped from a fixed range onto 0–100 — used for
  `analyst_opinions` (0 → 30) and the risk-pillar `return_12m_pct` (−40 → 60).

**How `screen_score` is calculated**

1. Build the 5 pillar scores (each the average of its 0–100 sub-scores):
   Value (20%), Quality (20%), Trend (30%), Sentiment (20%), Risk (10%).
2. `raw_screen_score` = weight-normalized blend of the available pillars.
3. `confidence_score` = % of the 13 key inputs present, giving
   `confidence_multiplier = 0.7 + 0.3 × coverage`.
4. `screen_score` = `raw_screen_score × confidence_multiplier`, so sparse-data
   names are penalized instead of over-ranked.

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

**Screener row** — `screen_current_portfolio.json`, top-ranked candidate
(`ranked[0]`; `signals` trimmed to a few per pillar — see the full field list above):

```json
{
  "symbol": "MU",
  "name": "Micron Technology, Inc.",
  "price": 979.3,
  "currency": "USD",
  "screen_score": 69.2,
  "raw_screen_score": 69.19,
  "confidence_score": 100.0,
  "value_score": 62.0,
  "quality_score": 78.5,
  "trend_score": 81.7,
  "momentum_score": 81.7,
  "sentiment_score": 59.7,
  "risk_score": 46.4,
  "signals": {
    "analyst_upside_pct": 51.74,
    "pe_forward": 6.54,
    "roe_pct": 66.64,
    "revenue_growth_pct": 345.7,
    "return_6m_pct": 199.46,
    "price_vs_ma200_pct": 110.84,
    "rsi14": 49.12,
    "recommendation_mean": 1.42,
    "atr_pct_of_price": 8.89,
    "return_12m_pct": 695.47
  },
  "data_quality": { "coverage_ratio": 1.0, "coverage_pct": 100.0 }
}
```

`MU` tops this 12-name universe with `screen_score = 69.2`. Because all 13 key
inputs are present (`confidence_score = 100`), the confidence multiplier is `1.0`,
so `screen_score` equals `raw_screen_score` (69.19). The rank is driven by strong
**quality** (78.5 — ROE 66.6%, revenue growth 345.7%) and **trend** (81.7 — price
110.8% above its 200-day MA), with a cheap forward P/E (6.54) and 51.7% analyst
upside lifting **value** (62.0). The **risk** pillar lags (46.4) because volatility
is high (ATR ≈ 8.9% of price, +695% over 12 months). A high screen score is a cue
to research further, not a buy.

**Allocation row** — `alloc_current_portfolio.json`, top holding (`allocations[0]`)
for a `2000 PLN` budget:

```json
{
  "symbol": "ASB.WA",
  "currency": "PLN",
  "price": 114.1,
  "price_pln": 114.1,
  "allocation_score": 56.3,
  "allocation_score_source": "components+confidence",
  "score": 56.3,
  "screen_score": 56.3,
  "conviction": null,
  "confidence_score": 92.31,
  "value_score": 24.8,
  "quality_score": 33.1,
  "trend_score": 85.4,
  "sentiment_score": 52.9,
  "risk_score": 98.5,
  "target_weight_pct": 12.04,
  "shares": 6,
  "cost": 684.6,
  "cost_pln": 684.6,
  "actual_weight_pct": 34.23
}
```

`ASB.WA` gets an `allocation_score` of `56.3` from the confidence-adjusted component
blend (`allocation_score_source = "components+confidence"`). Its model
`target_weight_pct` is only `12.04%`, but after whole-share rounding and the
leftover-cash sweep it lands at `6` shares × `114.1 PLN` = `684.6 PLN`, i.e. an
`actual_weight_pct` of `34.23%` — right under the 35% per-name cap. That gap between
target (12%) and actual (34%) is the sweep concentrating unspent budget into the
top affordable names. `currency` is `PLN`, so `price_pln` equals `price`.

Note how the two files connect: `MU` wins the *screen* (69.2) yet never makes the
*allocation* — it sits in `summary.dropped_below_one_share`, because a single share
(≈ $979 × 3.7847 ≈ 3706 PLN) blows past the 700 PLN per-name cap (35% of 2000 PLN).
For a US row, `currency` is `USD`, `price` is in USD, and `price_pln` equals
`price × fx_usdpln`; sizing and `cost_pln` are always computed in PLN.

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

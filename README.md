# 📊 Stock Skills — A 9-Analyst Investment Committee

A set of **Claude Agent Skills** backed by small **Python (yfinance)** scripts that
run a full bottom-up + top-down workup on any stock and turn it into a concrete,
risk-managed trade plan.

Each "analyst" is a skill in [`skills/`](skills/). Skills do the *reasoning* and
live web search; the scripts in [`scripts/`](scripts/) do the deterministic *math*
(indicators, fundamentals, scorecard, position sizing). No API keys required.

> ⚠️ **Not financial advice.** This is an educational research and risk-management
> framework. You are responsible for your own decisions.

---

## The committee

| # | Skill | Role | Script(s) |
|---|-------|------|-----------|
| 1 | `data-scout` | Live price, EPS vs consensus, targets, breaking news | `fetch_quote.py` |
| 2 | `macro-strategist` | Fed/rates, business cycle, sector vs index | `fetch_macro.py` |
| 3 | `data-hunter` | P/E, EV/EBITDA, FCF yield, ROIC, ownership | `fetch_fundamentals.py` |
| 4 | `sentiment-analyst` | Short interest, 13F, insider transactions | `fetch_sentiment.py` |
| 5 | `the-bear` | Hardwired to find reasons NOT to buy | (reuses above) |
| 6 | `the-chartist` | MA20/50/200, RSI, MFI, Fibonacci, entry, ATR | `fetch_technicals.py` |
| 7 | `devils-advocate` | Attacks blind spots in every prior report | — |
| 8 | `the-cio` | Verdict + 1–10 scorecard across 5 dimensions | `scorecard.py` |
| 9 | `portfolio-manager` | Sizing, DCA tranches, stop loss, two targets | `position_sizer.py` |
| ★ | `analyst-desk` | Orchestrates all 9 end-to-end | (all) |

**Pipeline:**

```
Data Scout ─┐
Macro ──────┤
Data Hunter ┼─► The Bear ─► Devil's Advocate ─► The CIO ─► Portfolio Manager
Sentiment ──┤                                   (verdict +     (size, DCA,
Chartist ───┘                                    scorecard)     stop, targets)
```

---

## Setup

```powershell
cd C:\Users\A497929\projects\stock-skills
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Smoke-test the scripts (all print JSON):

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

## How to run the analysis

### Option A — Claude / Claude Code (Agent Skills)
Point your agent at this folder so it can discover the `skills/`. Then ask, e.g.:

> *"Run the analyst desk on NVDA. Account is $50k, 1% risk per trade."*

The `analyst-desk` skill orchestrates the other eight in order and returns one
decision-ready report. You can also call a single seat: *"Just give me the
Chartist read on AMD."*

### Option B — GitHub Copilot / VS Code
The skills are plain markdown playbooks and the scripts are plain Python, so you
can drive them from Copilot Chat too: ask Copilot to run a script (e.g.
`python scripts/fetch_technicals.py NVDA`) and then follow the matching
`skills/<name>/SKILL.md` instructions to interpret the JSON. To expose these as
native Copilot agents, wrap each `SKILL.md` as a `.agent.md` / `.prompt.md`
chat mode (ask and I'll generate them).

### Option C — Manual
Run the scripts yourself and read the JSON; each script's docstring documents
its arguments.

---

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
stock-skills/
├─ README.md
├─ requirements.txt
├─ lib/common.py            # yfinance wrappers + indicators (RSI, MFI, ATR, Fib)
├─ scripts/                 # deterministic data + math tools (JSON out)
└─ skills/                  # the 9 analysts + analyst-desk orchestrator
```

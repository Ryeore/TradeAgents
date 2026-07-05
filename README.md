# 📊 Stock Skills — A 9-Analyst Investment Committee

Run a full bottom-up + top-down workup on any stock — from idea screening to a
sized, risk-managed trade plan — driven by a 9-analyst committee.

Three ways to run it, all sharing the same engine:

- **CrewAI** (`crew/`) — automated multi-agent pipeline. **← this README focuses here.**
- **Agent Skills** (`skills/`) — markdown playbooks for Claude / Copilot.
- **Scripts** (`scripts/`) — deterministic Python math tools you can call directly (no API key).

> ⚠️ **Not financial advice.** An educational research and risk-management
> framework. You are responsible for your own decisions.

---

## 🚀 Quickstart

```powershell
# 1. Install  (Python 3.10–3.13)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configure the LLM key  (only needed for the CrewAI agents)
copy .env.example .env
#    then edit .env: set ANALYST_DESK_MODEL and your OPENAI_API_KEY (or another provider)

# 3. Run
python -m crew.main AAPL --account 50000 --risk 1     # full desk + trade plan on AAPL
python -m crew.main --portfolio --budget 2000 --preset wse_blue --top 8   # allocate a budget
python -m crew.main AAPL --plan                        # preview the pipeline (no API key)
```

No API key yet? The deterministic parts still work on their own:

```powershell
python scripts/fetch_quote.py AAPL                                # live quote JSON
python scripts/screen_candidates.py --preset wse_blue --top 8     # rank a watchlist
```

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

## Smoke-test the scripts

Every script prints JSON and needs **no API key**:

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

## How to run

### CrewAI (recommended — automated pipeline)

The `crew/` package runs the nine analysts as a **CrewAI** crew. Each analyst is
an `Agent` whose persona is loaded live from its `skills/*/*.md` file, and every
deterministic script is exposed as a CrewAI tool — so the markdown stays the
single source of truth for personas and the scripts for the math.

Run `python -m crew.main <TICKER> [options]`:

| Command | What it does | API key? |
|---------|--------------|:---:|
| `python -m crew.main AAPL --account 50000 --risk 1` | Full 9-analyst desk **+ sized trade plan** | yes |
| `python -m crew.main AAPL --analysis` | Analysts 1–8 + report, no position sizing | yes |
| `python -m crew.main AAPL --quick` | Data Scout snapshot only | yes |
| `python -m crew.main --screen --preset wse_blue --top 8` | Rank a watchlist (Opportunity Scout) | yes |
| `python -m crew.main --portfolio --budget 2000 --preset wse_blue --top 8` | Split a budget across the best names | yes |
| `python -m crew.main --portfolio --deep --budget 2000 --preset wse_blue --top 6` | …weighted by full-desk CIO conviction | yes |
| `python -m crew.main AAPL --plan` | Print the pipeline plan and exit | **no** |

- **Tickers:** WSE names need the `.WA` suffix (e.g. `CDR.WA`, `KRU.WA`).
- **Model:** set `ANALYST_DESK_MODEL` in `.env` — any LiteLLM id
  (`gpt-4o-mini`, `anthropic/claude-3-5-sonnet-latest`, `azure/<deployment>`, …).
- **Output:** seats run sequentially (each receives the upstream reports as
  `context`) and each writes one markdown file to `agentReports/<TICKER>/` —
  `01-data-scout.md` … `09-portfolio-manager.md`, `99-final-report.md`.

### Other ways to run

- **Scripts only (no API key):** run any `scripts/*.py` and read the JSON —
  e.g. `python scripts/fetch_quote.py AAPL`. Each script's docstring lists its args.
- **Claude / Claude Code:** point the agent at this folder so it discovers
  `skills/`, then ask *"Run the analyst desk on NVDA, $50k account, 1% risk."* The
  `analyst-desk` skill orchestrates the other eight and returns one report.
- **GitHub Copilot / VS Code:** the skills are markdown playbooks — ask Copilot to
  run a script and follow the matching `skills/<name>/*.md` to interpret the JSON.

### Portfolio allocation — details

The `--portfolio` flow answers *“I have 2000 PLN — which stocks and what %?”*: the
Opportunity Scout screens the universe, then the Portfolio Manager splits the
budget across the best-scored names. The math lives in
[`scripts/portfolio_allocator.py`](scripts/portfolio_allocator.py) and runs
standalone with **no LLM/API key**:

```powershell
python scripts/screen_candidates.py --preset wse_blue --top 8 > screen.json
python scripts/portfolio_allocator.py --budget 2000 --candidates-file screen.json --top 6
```

Weights scale with each name's score (`score ** score_power`), are **capped per
name** (`--max-weight`, default 35%), converted to **whole shares**, and any
leftover cash is **swept** into the highest-scored affordable names so the budget
is actually deployed. Pass `--holdings-file` (a `[{symbol, value}]` JSON) to see
the *combined* portfolio weights after the new money lands.

**By conviction, not just the screen (`--deep`):** the screen score is a coarse
value/quality/momentum filter. To weight the budget by the full committee's
verdict instead, run the desk on every shortlisted name and allocate by each
CIO **conviction** (1–10):

```powershell
python -m crew.main --portfolio --deep --budget 2000 --preset wse_blue --top 6
```

This runs the analysts-1→8 (`conviction`) pipeline per name, parses each CIO
conviction, and allocates by it — writing `agentReports/PORTFOLIO/deep-allocation.md`.
It needs an LLM key (one desk per name); the plain `--portfolio` path does not.

---

## Deploy to CrewAI AMP

The desk is also packaged as a **CrewAI Flow** so it can be deployed as an
automation on [CrewAI AMP](https://app.crewai.com). The Flow
([`src/analyst_desk/flow.py`](src/analyst_desk/flow.py)) routes an input `mode`
to the matching pipeline and reuses the same `crew/` logic:

| `mode` | behaviour | key inputs |
|--------|-----------|-----------|
| `full` / `analysis` / `quick` | single-ticker desk | `ticker`, `account`, `risk_pct` |
| `screen` | Opportunity Scout screen | `preset` / `ticker`, `top` |
| `portfolio` (`deep=false`) | screen → budget allocation | `budget`, `preset`, `top` |
| `portfolio` (`deep=true`) | full desk per name → conviction allocation | `budget`, `preset`, `top` |

Deployment artifacts: [`pyproject.toml`](pyproject.toml) (`[tool.crewai] type = "flow"`),
the `src/analyst_desk/` package with a `kickoff()` entry point, and a committed
`uv.lock`.

```powershell
# one-time: authenticate, then deploy from this repo (pushed to GitHub)
pip install "crewai[tools]"
crewai login
crewai deploy create        # detects the GitHub repo + .env vars, builds the Flow
crewai deploy status        # watch the build; first deploy ~1 min
```

You can also deploy from the web UI: **Connect GitHub** at app.crewai.com, pick
this repo, set env vars (`OPENAI_API_KEY` / `ANALYST_DESK_MODEL`), and Deploy.
AMP exposes `/inputs`, `/kickoff` and `/status/{id}`; kick off with e.g.
`{ "mode": "portfolio", "deep": true, "budget": 2000, "preset": "wse_blue", "top": 6 }`.

> **Note:** the data tools call `yfinance` (Yahoo). On cloud IPs Yahoo may
> rate-limit or intermittently 404 some tickers (especially thin WSE names), so
> deployed runs can be flakier than local ones.

Run the Flow locally too:

```powershell
$env:DESK_INPUTS = '{"mode":"quick","ticker":"AAPL"}'
python -m analyst_desk.main        # or: crewai run   (with src on the path)
```

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
TradeAgents/
├─ README.md
├─ requirements.txt
├─ lib/common.py            # yfinance wrappers + indicators (RSI, MFI, ATR, Fib)
├─ scripts/                 # deterministic data + math tools (JSON out)
├─ skills/                  # the 10 analysts + analyst-desk orchestrator
├─ crew/                    # CrewAI layer: tools (script wrappers) + desk + CLI
├─ src/analyst_desk/        # deployable CrewAI Flow (for CrewAI AMP)
├─ pyproject.toml           # CrewAI Flow project + deps (uv.lock committed)
├─ watchlists/              # ticker lists for screen_candidates.py
├─ agentReports/            # auto-generated per-seat reports (gitignored)
└─ output/                  # auto-generated reports (gitignored)
```

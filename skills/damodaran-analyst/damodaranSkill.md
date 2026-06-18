---
name: damodaran-valuation
version: 1
description: |
  Stock valuation skill based on Aswath Damodaran's "The Little Book of Valuation" (Wycena. Minipodrecznik dla inwestorów gieldowych).
  Covers intrinsic value (DCF/DDM/FCFE/FCFF), relative valuation (multiples), life-cycle-aware analysis,
  sector-specific approaches (banks, cyclicals, tech/IP-heavy), and bias awareness.
  Use when any agent needs to value a stock, assign a fair price, or decide if a stock is cheap or expensive.
agents: [Data_Hunter, CIO, Portfolio_Manager, The_Bear, Devil_Advocate]
---

***

# Damodaran Valuation Skill
## Source: "The Little Book of Valuation" — Aswath Damodaran

This skill distills the complete Damodaran valuation framework into actionable rules, formulas, and decision trees
for use by AI agents performing stock analysis, stock-picking, and position sizing.

***

## CORE PHILOSOPHY (always apply)

1. **Value ≠ Price.** Price is what market quotes today; value is based on future cash flows and risk.
2. **Every valuation is subjective.** Acknowledge your biases before starting. Write them down.
3. **Most valuations are wrong — and that's OK.** Uncertainty is symmetric. All investors face the same fog.
4. **Simpler is better.** A 3-input model beats a 10-input model. More complexity = more error propagation.
5. **Use both approaches.** Intrinsic (DCF) AND relative (multiples). A stock cheap on both = higher confidence.

***

## PART 1 — FINANCIAL TOOLS (building blocks)

### 1.1 Time Value of Money

Present Value formula:
```
PV = CF_t / (1 + r)^t
```

Perpetuity (Gordon Growth Model):
```
PV = CF_next_year / (r - g)
```
Constraint: **g must be < nominal GDP growth rate of the economy** (e.g., < 4–5% for developed markets).

Annuity (finite period):
```
PV = CF × [1 - 1/(1+r)^n] / r
```

### 1.2 Risk & Discount Rate

**CAPM baseline:**
```
Expected Return = Rf + β × ERP
```
Where:
- Rf = risk-free rate (10Y government bond yield)
- β = beta vs. market (1.0 = market average risk)
- ERP = equity risk premium (typically 4–6% for developed markets)

**Beta interpretation:**
| Beta | Risk Level | Typical sector |
|------|-----------|----------------|
| < 0.7 | Low | Utilities, staples, REITs |
| 0.7–1.2 | Market-like | Industrials, financials |
| 1.2–1.8 | Elevated | Tech, consumer discretionary |
| > 1.8 | High | Biotech, small-cap growth |

**WACC (for firm valuation):**
```
WACC = ke × (E/V) + kd × (1 - tax_rate) × (D/V)
```
Where ke = cost of equity (CAPM), kd = pre-tax cost of debt, E/V and D/V = capital structure weights.

### 1.3 Financial Statement Basics

**Operating Income (EBIT):** Revenue − Operating Costs (excl. interest & tax)
**Net Income:** EBIT − Interest − Tax
**Operating Margin:** EBIT / Revenue
**Net Margin:** Net Income / Revenue

**ROIC (Return on Invested Capital):**
```
ROIC = EBIT × (1 - tax rate) / (Book Value of Capital − Cash)
```
High ROIC vs. WACC → value-creating firm. ROIC < WACC → value-destroying firm.

**ROE (Return on Equity):**
```
ROE = Net Income / Book Value of Equity
```

***

## PART 2 — INTRINSIC VALUE MODELS

### 2.1 Two Approaches to Equity Value

| Approach | What you discount | Discount rate | Final output |
|----------|------------------|---------------|--------------|
| **Firm valuation** | FCFF (pre-debt cash flows) | WACC | Enterprise Value → subtract debt → Equity Value |
| **Equity valuation** | FCFE or Dividends | Cost of equity (ke) | Equity Value directly |

Use **Firm valuation (FCFF/WACC)** when: debt levels are changing, or for capital-intensive companies.
Use **Equity valuation (FCFE/ke)** when: stable leverage, financial firms, or dividend-paying stocks.

### 2.2 Free Cash Flow Definitions

**FCFF (Free Cash Flow to Firm):**
```
FCFF = EBIT × (1 - tax_rate) + D&A − Capex − ΔNWC
```

**FCFE (Free Cash Flow to Equity):**
```
FCFE = Net Income + D&A − Capex − ΔNWC + Net Borrowing
```

**Augmented Dividends (for dividend payers):**
```
Augmented Dividends = Dividends Paid + Buybacks
```
Average buybacks over 3–5 years for stability.

### 2.3 DCF Model — Step-by-Step

**Step 1: Identify current cash flow base**
Use normalized (trailing 3Y average) FCFF or FCFE. Avoid single-year anomalies.

**Step 2: Estimate growth rate(s)**
Use a 2-stage or 3-stage model:
- **Stage 1 (high growth):** 3–10 years, based on historical revenue CAGR, analyst consensus, reinvestment rate
- **Stage 2 (stable/terminal):** perpetual growth = g_terminal (never > nominal GDP growth)

**Reinvestment Rate:**
```
Reinvestment Rate = (Capex − D&A + ΔNWC) / NOPAT
```
**Expected Growth:**
```
g = Reinvestment Rate × ROIC
```

**Step 3: Calculate Terminal Value**
```
TV = FCFF_(n+1) / (WACC - g_terminal)
```
TV typically accounts for 60–80% of total value — **scrutinize it heavily**.

**Step 4: Discount everything back**
```
Enterprise Value = Σ [FCFF_t / (1+WACC)^t] + TV / (1+WACC)^n
Equity Value = Enterprise Value − Net Debt
Value per Share = Equity Value / Shares Outstanding
```

**Step 5: Compare to market price**
```
Margin of Safety = (Intrinsic Value − Market Price) / Intrinsic Value
```
- > 30%: Strong buy signal
- 10–30%: Moderate undervaluation
- -10% to +10%: Fairly valued
- < -10%: Overvalued

### 2.4 Dividend Discount Model (DDM)
For stable dividend payers (utilities, mature REITs, consumer staples):

**Gordon Growth Model:**
```
Value = D1 / (ke - g)
D1 = D0 × (1 + g)
```

2-Stage DDM:
```
Value = Σ [Dt / (1+ke)^t] + [Dn+1 / (ke - g_stable)] / (1+ke)^n
```

### 2.5 Key Data Inputs Summary

| Input | Where to find | Red flag if... |
|-------|--------------|----------------|
| Revenue growth (5Y CAGR) | Financial statements, investor presentations | > 30% CAGR extrapolated beyond 5Y |
| EBIT / NOPAT margin | Income statement | Assumes margin expansion without moat evidence |
| Capex / D&A ratio | Cash flow statement | Capex << D&A in capital-intensive industry = understated reinvestment |
| Tax rate | Income statement | Use effective rate, not statutory |
| Beta | Bloomberg, Yahoo Finance | Use industry average beta for small/volatile firms |
| g_terminal | GDP growth estimates | Never use > 3–4% for developed market stocks |
| Net Debt | Balance sheet | Include off-balance-sheet obligations (leases, pension) |

***

## PART 3 — RELATIVE VALUATION (MULTIPLES)

### 3.1 Four Tests for Any Multiple

Before using ANY multiple, run these four tests:

1. **Definitional test** — Are numerator and denominator consistent? (Equity metric vs. equity multiple; firm metric vs. firm multiple)
2. **Descriptive test** — What is the distribution of this multiple across the market/sector? What is the median?
3. **Analytical test** — What fundamentals drive this multiple? (e.g., P/E is driven by growth, payout ratio, risk)
4. **Application test** — Are the comparable companies truly comparable in growth, risk, and cash flow profile?

### 3.2 Core Multiples Reference

#### P/E (Price-to-Earnings)
```
Justified P/E = Payout Ratio × (1 + g) / (ke - g)
```
- Use only for profitable firms with stable earnings
- Prefer **Forward P/E** (next 12M consensus EPS)
- Compare to: sector median, own 5Y historical range, market P/E
- **Distorted by:** leverage changes, one-offs, accounting choices

#### EV/EBITDA
```
EV = Market Cap + Net Debt + Minority Interest − Cash
EV/EBITDA multiple → compare to peers on similar ROIC and growth
```
- Preferred for capital-intensive businesses (industrials, telecoms, infrastructure)
- Less distorted by depreciation policy differences between firms
- **Caution:** does not account for capex differences — use EV/EBIT or EV/FCFF for capex-heavy firms

#### EV/EBIT
```
EV/EBIT → better when firms have very different D&A/Capex ratios
```

#### P/FCF (Price to Free Cash Flow)
```
P/FCF = Market Cap / FCFE
```
- Preferred by value investors; harder to manipulate than EPS
- Use for mature firms with stable FCF

#### P/BV (Price-to-Book Value)
```
Justified P/BV = (ROE - g) / (ke - g)
```
- Low P/BV ≠ automatically cheap — check ROE vs. ke
- A P/BV < 1 with ROE > ke = genuine bargain
- A P/BV < 1 with ROE < ke = value trap

#### EV/Sales (Price-to-Sales)
```
Justified EV/Sales = Net Margin × (1 + g) × (1 - Reinvestment Rate) / (WACC - g)
```
- Use only when earnings are negative (early-stage, turnarounds)
- Requires normalization of margins to industry/target level

#### PEG Ratio
```
PEG = P/E / Expected EPS Growth Rate (%)
```
- PEG < 1 = potential undervaluation (especially for growth stocks)
- Not useful for negative-growth or negative-earnings companies

### 3.3 Sector-Specific Multiple Preferences

| Sector | Preferred Multiples | Watch out for |
|--------|-------------------|---------------|
| Technology / SaaS | EV/Sales, EV/EBITDA, P/FCF | Stock comp excluded from EBITDA |
| Banks / Insurance | P/BV, P/E, ROE vs. ke | Regulatory capital, loan loss provisions |
| Industrials | EV/EBIT, EV/EBITDA | Cyclicality — use normalized earnings |
| REITs | P/FFO, Dividend Yield, NAV | FFO vs. AFFO distinction |
| Commodities/Energy | EV/EBITDA (spot), EV/Reserves | Commodity price assumptions |
| Pharma / Biotech | EV/Sales (pipeline), rNPV | Pipeline risk, patent cliff |
| Utilities | EV/EBITDA, Dividend Yield, RAB | Regulatory environment |

***

## PART 4 — LIFE-CYCLE AWARE VALUATION

The appropriate valuation method depends on WHERE the company is in its life cycle.

### 4.1 High-Growth / Early Stage Companies
**Problems:**
- Negative or near-zero earnings/FCF
- Short or no history
- Massive uncertainty about survival and growth path

**Solutions:**
- Use EV/Sales with normative margins (what margin is achievable at maturity?)
- Scenario analysis: bear / base / bull, weight by probability
- Don't anchor on current numbers — value the "mature" version of the business, discounted back
- If pre-revenue: use comparables from IPO cohort + option-value thinking

**Key question:** "What does this company need to look like in 10 years to justify today's price?"

### 4.2 Mature / Stable Companies
**Standard 2-stage DCF applies:**
- Stage 1: 3–5 years at current or slightly declining growth
- Stage 2: terminal growth = GDP rate

**Multiple check:** Compare P/E, EV/EBITDA to 10-year own average and sector peers.

### 4.3 Turnaround / Restructuring Stories
**Three levers of value creation:**
1. **Operational restructuring** — margin improvement (revenue up or costs down)
2. **Financial restructuring** — optimize capital structure (reduce excess cash, refinance expensive debt)
3. **Non-operating assets** — hidden real estate, subsidiaries, IP not reflected in core earnings

**Management change premium:** A credible new CEO with a track record adds value — quantify by modeling the
operational scenario under improved management vs. status quo.

### 4.4 Distressed / Going-Concern Risk
- Apply a **survival probability** (estimated from debt/EBITDA, interest coverage, covenant headroom)
- Value = P(survival) × DCF value + P(bankruptcy) × Liquidation value
- Liquidation value = Distressed sale value of assets (typically 50–70% of book for tangibles)
- Equity has **option value** in distress — use Black-Scholes if heavily levered

***

## PART 5 — SECTOR SPECIAL CASES

### 5.1 Banks and Financial Institutions
**Why standard DCF fails:**
- Debt is "raw material," not just financing
- Capex/D&A concept doesn't apply; reinvestment = retained earnings for regulatory capital

**Correct approach — Equity DCF:**
```
Value of Equity = Σ [FCFE_t / (1+ke)^t] + Terminal Value / (1+ke)^n
FCFE_bank = Net Income − (Tier 1 Capital Requirement × RWA Growth)
```

**Multiples for banks:**
- P/BV vs. ROE: Bank worth P/BV > 1 only if ROE > ke
- P/E with normalized earnings (exclude loan loss spikes)

**Red flags:** High NPL ratio, thin Tier 1 ratio, concentrated loan book, rising cost of risk.

### 5.2 Commodity / Cyclical Companies
**Problem:** Earnings are wildly cyclical — EPS at cycle peak ≠ normalized EPS.

**Solutions:**
- Use **normalized/midcycle earnings** (average over full commodity cycle, typically 7–10 years)
- DCF with scenario-based commodity price decks (bear/base/bull)
- EV/Reserves or EV/Production for pure-play miners/oil companies
- **Never value at peak-cycle earnings** — this is the most common mistake in cyclicals

### 5.3 Tech / IP-Heavy Companies (R&D Capitalization)
**Problem:** GAAP treats R&D as expense → understates true assets and overstates "invested capital."

**Adjustment:**
1. Capitalize R&D (amortize over useful life: 3Y for tech, 5–10Y for pharma)
2. Add R&D asset to invested capital
3. Restate EBIT = EBIT + R&D expense − R&D amortization
4. Recalculate ROIC with adjusted numbers

**Stock options adjustment:**
- Options outstanding → use treasury stock method to get diluted shares
- Or add option value as additional expense to get true net income

***

## PART 6 — BIAS AWARENESS (Mandatory pre-analysis)

Before starting any valuation, explicitly state:

```
BIAS CHECKLIST:
[ ] Why am I looking at this stock? (tipster, article, already own it, short thesis?)
[ ] Do I currently own this stock? (confirmation bias risk)
[ ] Am I reading management commentary or raw numbers? (management spin risk)
[ ] What is the "sell-side" consensus? (anchoring risk if following analyst targets)
[ ] What would make me WRONG on the bull case? (force a bear scenario)
[ ] What would make me WRONG on the bear case? (force a bull scenario)
```

**Practical debiasing rules (from Damodaran):**
- Read financial statements first, analyst reports last (or not at all)
- Build the bear case as rigorously as the bull case
- Cross-check intrinsic and relative models — if they diverge > 30%, find out why
- Treat any valuation anchored on "the market will re-rate this stock" as speculative, not fundamental

***

## PART 7 — THE 10 PRACTICAL RULES (Damodaran's summary)

1. **Every asset has a value** — uncertainty is not a reason to refuse valuing it.
2. **The value of an asset is driven by its cash flows, growth, and risk** — nothing else matters permanently.
3. **A good valuation provides a range, not a point estimate** — always present bear/base/bull.
4. **All valuation models have flaws** — the best model is the simplest one that captures the key drivers.
5. **The inputs matter more than the model** — garbage in, garbage out.
6. **Use both intrinsic and relative valuation** — if they agree, your conviction is higher.
7. **The terminal value dominates most DCFs** — spend the most scrutiny there.
8. **Match the growth rate to the reinvestment rate** — growth without reinvestment is a fairy tale.
9. **ROIC vs. WACC determines whether growth creates or destroys value** — ROIC > WACC = good growth.
10. **A margin of safety is not optional** — buy only when intrinsic value exceeds price by a meaningful cushion.

***

## PART 8 — AGENT INTEGRATION GUIDE

This skill is designed to plug into the multi-agent stock analysis system. Here's how each agent should use it:

### Data Hunter
Use **Part 1** (financial tools) and **Part 2** (DCF inputs) as the checklist of required data:
- EBIT, FCFF, FCFE, ROIC, beta, net debt, shares outstanding
- Historical growth rates (3Y and 5Y revenue CAGR)
- Capex, D&A, changes in working capital
- Normalized earnings (use 3Y average for cyclicals)

### CIO / Valuation Engine
Execute the full **Part 2 DCF** + **Part 3 Multiples** workflow:
1. Build base DCF → get intrinsic value
2. Run 3 scenarios (bear/base/bull) with explicit assumptions for each
3. Cross-check with 3 most relevant multiples for the sector (see Part 3.3)
4. Compute **Margin of Safety** vs. current market price
5. Produce final scorecard

### The Bear
Use **Part 6 Bias Awareness** + worst-case assumptions in **Part 4 Life Cycle** section:
- Always model g_terminal = 0% for bear case
- Apply +2% to WACC for bear case
- Question every margin expansion assumption
- Check for value-destroying ROIC < WACC

### Devil's Advocate
Check DCF math for internal consistency:
- Is g > WACC? (model breaks down)
- Is g_terminal > nominal GDP? (violates perpetuity constraint)
- Is Reinvestment Rate consistent with stated growth? (g = RR × ROIC)
- Does Terminal Value exceed 80% of total firm value? (scrutinize inputs harder)
- Are multiples compared to truly comparable peers (same growth + risk + cash flow profile)?

### Portfolio Manager
Use **Margin of Safety** thresholds from **Part 2.3** for position sizing:
- MoS > 40%: Full position (max allocation per risk rules)
- MoS 20–40%: Half position, DCA on weakness
- MoS 10–20%: Small starter position only
- MoS < 10%: Monitor, do not initiate

***

## QUICK REFERENCE — VALUATION FORMULA CARD

```
═══════════════════════════════════════════════════════════
INTRINSIC VALUE
───────────────
Gordon DDM:      V = D1 / (ke - g)
FCFE perpetuity: V = FCFE1 / (ke - g)
FCFF DCF:        EV = Σ FCFF_t/(1+WACC)^t + TV/(1+WACC)^n
Terminal Value:  TV = FCF_n+1 / (WACC - g_terminal)
Equity Value:    = EV - Net Debt

DISCOUNT RATES
───────────────
ke (CAPM):       Rf + β × ERP
WACC:            ke×(E/V) + kd×(1-t)×(D/V)

PROFITABILITY
───────────────
ROIC:            EBIT(1-t) / (Capital - Cash)
ROE:             Net Income / Book Equity
Expected Growth: g = Reinvestment Rate × ROIC
Reinvestment:    RR = (Capex - D&A + ΔNWC) / NOPAT

MULTIPLES
───────────────
P/BV justified:  (ROE - g) / (ke - g)
P/E justified:   Payout × (1+g) / (ke - g)
EV/Sales just.:  Margin × (1+g) × (1-RR) / (WACC - g)
Margin of Safety: (IV - Price) / IV
═══════════════════════════════════════════════════════════

***

## PART 9 — LONG-TERM INVESTOR PROFILE & WSE CALIBRATION

*This section calibrates the framework for the portfolio owner's stated style: long-term buy-and-hold, growth compounders, dividends appreciated, with a significant WSE exposure.*

### 9.1 Investment Style Lens
Apply this filter before scoring any candidate:
- **Time horizon**: 3–10+ years. Short-term catalysts are secondary; the structural quality of the business is primary.
- **Dividends**: valued as evidence of capital discipline AND as a real cash return. Yield level matters less than sustainability and growth trajectory.
- **Growth**: the underlying earnings/FCF must compound over time. A flat or declining business is not acceptable even if cheap today.
- **WSE portfolio**: Polish-listed names require extra scrutiny for data gaps, thinner liquidity, and country-specific risk.

### 9.2 Dividend Sustainability (Damodaran's test)
*"Firms should pay dividends only when they cannot find investments that earn above their cost of capital by reinvesting internally."*
A dividend is a quality signal **only** when supported by genuine free cash flow — not by borrowing or asset sales.

**Run this check before applying DDM:**

| Metric | Formula | Green | Yellow | Red |
|--------|---------|-------|--------|-----|
| FCF Coverage | FCFE / Dividends Paid | ≥ 1.5 | 1.0–1.5 | < 1.0 |
| Payout Ratio | Dividends / Net Income | < 60% | 60–80% | > 80% |
| Dividend CAGR (5Y) | — | > 5% | 0–5% | Cut or frozen |
| True Capital Return | (Dividends + Buybacks) / Mkt Cap | > 4% | 2–4% | < 2% |

**DDM is appropriate when:** FCF coverage ≥ 1.0 AND payout ≤ 80% AND the company is past its high-growth phase.
Otherwise use FCFE DCF — dividends alone don't tell the full story.

### 9.3 Long-Term Compounder Checklist
*A compounder creates value through ROIC > WACC + sustained reinvestment at above-cost rates.*

- [ ] ROIC > WACC for at least 4 of the last 5 years
- [ ] Operating margin stable or expanding over 5Y (pricing power / scale evidence)
- [ ] Revenue CAGR ≥ nominal GDP growth (market share gain or secular tailwind)
- [ ] FCF conversion ≥ 80% of net income (earnings quality; low accruals)
- [ ] Net Debt/EBITDA < 2.0 for non-financials (cycle survivability)
- [ ] Insider ownership > 10% OR proven long-tenure management team
- [ ] Zero dividend cuts over 5Y (for positions held partly for income)

**Scoring:** ≥ 5 of 7 → high-confidence compounder. ≤ 3 of 7 → question the quality label regardless of narrative.

### 9.4 WSE-Specific Discount Rate Calibration
Do **not** use US Treasuries or US ERP for Polish companies.

**Risk-free rate:** Polish 10Y government bond yield (`^POLAND10Y` / PLGB10Y)
**Country Risk Premium (CRP):** +1.5–2.0% over Western Europe ERP
**Suggested WSE ERP:** 6.5–7.5% total (vs. ~4–5% for US)

```
ke_WSE = PLGB10Y_yield + β × 7.0%   ← base ERP; adjust ±0.5% per risk context
```

**Practical examples (assuming ~5.5% PLGB10Y):**
| Beta | Sector type | ke estimate |
|------|-------------|------------|
| 0.7 | Bank, utility, REIT | ~10.4% |
| 1.0 | Industrial, financial | ~12.5% |
| 1.3 | IT services, growth | ~14.6% |
| 1.6 | Small-cap, biotech | ~16.7% |

**WSE data-gap rules:**
- No forward EPS → use trailing P/E + 3Y revenue CAGR as implicit growth proxy
- < 5 analyst opinions → downweight consensus targets; rely primarily on fundamentals
- Supplement always with: Biznesradar.pl, StockWatch.pl, GPW ESPI/EBI filings, Bankier.pl
- OFE/TFI crossing ±5% threshold → visible in GPW regulatory announcements (major shareholder signal)

**Sector suitability for this investor profile (WSE):**
| Sector | Fit | Primary valuation method | Key watch item |
|--------|-----|--------------------------|----------------|
| Banks (PKO, PEO) | ✅ Dividend + value | P/BV vs ROE, DDM | NPL ratio, NBP rate path |
| Capital markets (XTB) | ✅ Growth + dividend | P/E, EV/EBITDA | Trading volumes, regulation |
| IT services (ACP, CBF) | ✅ Growth compounder | ROIC, EV/Sales, EV/EBITDA | Contract renewal, margins |
| Debt management (KRU) | ✅ Niche compounder | P/E, FCF yield, DDM | Interest rate cycle, NPL supply |
| Healthcare / devices (SNT) | ⚠️ FCF uncertain | Scenario DCF | Pipeline, reimbursement policy |
| Commodities / mining (KGH) | ⚠️ Cyclical | Normalized EV/EBITDA | Commodity price cycle |
```
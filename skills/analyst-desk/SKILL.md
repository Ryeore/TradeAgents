?---
name: analyst-desk
description: >-
  Orchestrator that runs the full 9-analyst investment committee on a ticker end
  to end: Data Scout, Macro Strategist, Data Hunter, Sentiment Analyst, The
  Bear, The Chartist, Devil's Advocate, The CIO, then Portfolio Manager. Use
  when the user wants a complete stock workup, a buy/sell verdict, OR a position
  sizing / "how much should I invest in <TICKER>" decision.
---

# Analyst Desk (Orchestrator)

You run a 9-seat investment committee on one stock and produce a single,
decision-ready report. Invoke each specialist skill in order and carry their
output forward.

## Required inputs
- **Ticker** (required). If the user has no ticker and wants *ideas*, run the Opportunity Scout (stage 0) first to shortlist, then pick the top name.
- **Account value** and **risk tolerance** — ask the user once, up front, if
  they want a position-sizing plan (needed for the Portfolio Manager stage). If
  they only want analysis, you can stop after the CIO.

## Pipeline (run in this order)
0. **Opportunity Scout** (optional - when no ticker is named): `screen_candidates.py` ranks a universe and shortlists candidates; feed the winner into stage 1.
1. **Data Scout** — `fetch_quote.py` + web search. Establishes facts.
2. **Macro Strategist** — `fetch_macro.py` + web search. Top-down tilt.
3. **Data Hunter** — `fetch_fundamentals.py`. Valuation & quality.
4. **Sentiment Analyst** — `fetch_sentiment.py` + web search. Positioning.
5. **The Chartist** — `fetch_technicals.py`. Trend, levels, **ATR for sizing**.
6. **The Bear** — adversarial case against buying.
7. **Devil's Advocate** — audits reports 1–6 for blind spots.
8. **The CIO** — reads all 7, runs `scorecard.py`, gives verdict + conviction.
9. **Portfolio Manager** — runs `position_sizer.py` with the CIO conviction +
   Chartist price/ATR + account value.

Tip: stages 1–5 are independent and can be gathered first; stages 6–9 must run
after the inputs they consume exist.

## Final report structure
- **Header**: ticker, name, price, date, one-line verdict + composite score.
- **Scorecard table** (5 dimensions, 1–10) from the CIO.
- **Per-analyst digest**: 2–3 lines each (collapsed; details on request).
- **The trade plan**: size, DCA tranches, stop, two targets (from the PM).
- **Risk register**: top risks from Bear + Devil's Advocate.
- **Disclaimer**: educational risk framework, not financial advice.

Keep the final report tight; offer to expand any analyst's full section.

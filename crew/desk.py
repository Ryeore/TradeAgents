"""Build the 9-analyst desk as a CrewAI sequential crew.

Agent personas are loaded live from ``skills/*/*.md`` (single source of truth).
Each analyst gets only the tools it needs; tasks are wired with explicit
``context`` so every downstream seat receives the upstream reports it depends on.
Per-agent reports are written to ``agentReports/<TICKER>/`` exactly like the
existing manual pipeline.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from .tools import REPORTS_DIR, build_tools, load_skill

# --------------------------------------------------------------------------- #
# Persona sources (skills/*.md) -- the markdown stays the source of truth
# --------------------------------------------------------------------------- #
SKILL_FILES = {
    "opportunity_scout": "opportunity-scout/opportunityScoutSkill.md",
    "data_scout": "data-scout/dataScoutSkill.md",
    "macro_strategist": "macro-strategist/macroStrategistSkill.md",
    "data_hunter": "data-hunter/dataHunterSkill.md",
    "sentiment_analyst": "sentiment-analyst/sentimentAnalystSkill.md",
    "the_bear": "the-bear/theBearSkill.md",
    "the_chartist": "the-chartist/theChartistSkill.md",
    "devils_advocate": "devils-advocate/devilsAdvocateSkill.md",
    "the_cio": "the-cio/theCioSkill.md",
    "portfolio_manager": "portfolio-manager/portfolioManagerSkill.md",
    "desk_editor": "analyst-desk/analystDeskSkill.md",
}
DAMODARAN_SKILL = "damodaran-analyst/damodaranSkill.md"


# --------------------------------------------------------------------------- #
# Agent + task specifications (declarative; used for both build and --plan)
# --------------------------------------------------------------------------- #
@dataclass
class AgentSpec:
    key: str
    role: str
    goal: str
    tools: list[str] = field(default_factory=list)
    extra_skills: list[str] = field(default_factory=list)


@dataclass
class TaskSpec:
    key: str
    agent: str
    file_name: str
    expected_output: str
    description: str
    context: list[str] = field(default_factory=list)


AGENT_SPECS: dict[str, AgentSpec] = {
    "opportunity_scout": AgentSpec(
        "opportunity_scout", "Opportunity Scout",
        "Cast a wide net and hand the desk a ranked shortlist of names worth a full work-up. "
        "A high screen score is a reason to investigate, never a buy signal.",
        ["screen_candidates"],
    ),
    "data_scout": AgentSpec(
        "data_scout", "Data Scout",
        "Put the freshest, most accurate facts on the table for the rest of the desk. "
        "Facts only, no opinions, no buy/sell call.",
        ["fetch_quote", "fetch_fundamentals"],
    ),
    "macro_strategist": AgentSpec(
        "macro_strategist", "Macro Strategist",
        "Decide whether the macro tide (rates, cycle, sector) is with or against this name "
        "and output a 1-10 macro favourability sub-score.",
        ["fetch_macro"],
    ),
    "data_hunter": AgentSpec(
        "data_hunter", "Data Hunter",
        "Separate great businesses from merely cheap ones. Produce a Damodaran DCF intrinsic "
        "value, an explicit margin_of_safety_pct, and a 1-10 fundamentals sub-score.",
        ["fetch_fundamentals"], [DAMODARAN_SKILL],
    ),
    "sentiment_analyst": AgentSpec(
        "sentiment_analyst", "Sentiment Analyst",
        "Read the flows and the float: short interest, insiders, institutions and analyst "
        "trend. Output a 1-10 sentiment sub-score.",
        ["fetch_sentiment"],
    ),
    "the_bear": AgentSpec(
        "the_bear", "The Bear",
        "Build the strongest possible case AGAINST buying this stock now. State a bear_target "
        "price and a 1-10 downside-risk-severity score. Do not hedge.",
        ["fetch_fundamentals", "fetch_technicals"],
    ),
    "the_chartist": AgentSpec(
        "the_chartist", "The Chartist",
        "Read trend, momentum, volatility and levels; propose an entry zone and invalidation. "
        "Call out ATR(14) explicitly for the Portfolio Manager and a 1-10 technical sub-score.",
        ["fetch_technicals"],
    ),
    "devils_advocate": AgentSpec(
        "devils_advocate", "Devil's Advocate",
        "Audit the desk's REASONING, not the company: find biases, stale data, single points "
        "of failure and what nobody mentioned. Recommend a conviction adjustment.",
        [], [DAMODARAN_SKILL],
    ),
    "the_cio": AgentSpec(
        "the_cio", "The CIO",
        "Synthesise all seven prior reports, resolve conflicts, score the 5 dimensions and run "
        "the scorecard to produce a verdict and a conviction (composite) score.",
        ["scorecard"], [DAMODARAN_SKILL],
    ),
    "portfolio_manager": AgentSpec(
        "portfolio_manager", "Portfolio Manager",
        "Turn the CIO conviction + Chartist price/ATR into a concrete, risk-managed trade plan: "
        "size, DCA tranches, ATR stop, and two targets. For a multi-name budget, split the cash "
        "across the best-scored names by weight. Capital preservation first.",
        ["position_sizer", "portfolio_allocator"],
    ),
    "desk_editor": AgentSpec(
        "desk_editor", "Desk Editor (Chief of Staff)",
        "Assemble the individual analyst reports into one tight, decision-ready committee report "
        "following the analyst-desk final report structure.",
        [],
    ),
}


def _analyst_tasks(ticker: str) -> list[TaskSpec]:
    """The 1-8 analyst tasks (Data Scout through CIO), ticker-aware."""
    return [
        TaskSpec(
            "data_scout", "data_scout", "01-data-scout.md",
            "A markdown report: snapshot table (price, ranges, market cap, P/E TTM & fwd, EPS), "
            "earnings beat/miss vs consensus, street view (targets, upside %, rating, # analysts), "
            "a forward-estimates table (flag <3 analysts and mark +2y values as extrapolated), "
            "dated breaking-news bullets, and a data-freshness note. Facts only.",
            f"You are the Data Scout. Use the fetch_quote tool (and fetch_fundamentals for the "
            f"forward-estimates block) on {ticker}. Reconcile the numbers and lay out the freshest "
            f"facts for the rest of the desk. Do NOT give a buy/sell call.",
        ),
        TaskSpec(
            "macro_strategist", "macro_strategist", "02-macro-strategist.md",
            "A markdown report: regime call (rates direction, cycle phase, risk-on/off), sector "
            "vs index and stock vs index 6-month relative performance, a one-line net macro tilt "
            "(tailwind/neutral/headwind), 2-3 macro risks, and a 1-10 macro favourability sub-score.",
            f"You are the Macro Strategist. Use the fetch_macro tool on {ticker} and judge whether "
            f"the macro tide is with or against this name. End with 'macro_score = N/10'.",
            ["data_scout"],
        ),
        TaskSpec(
            "data_hunter", "data_hunter", "03-data-hunter.md",
            "A markdown report: valuation verdict (cheap/fair/rich with the driving metrics), a "
            "Damodaran DCF intrinsic value per share, an explicit margin_of_safety_pct, a forward "
            "growth table, a quality verdict (compounder/average/value-trap), the bull case in "
            "numbers, the one number that worries you most, and a 1-10 fundamentals sub-score.",
            f"You are the Data Hunter. Load the Damodaran valuation library in your backstory and "
            f"use the fetch_fundamentals tool on {ticker}. You MUST compute a DCF-based intrinsic "
            f"value and report margin_of_safety_pct explicitly, then end with 'fundamentals_score = N/10'.",
            ["data_scout"],
        ),
        TaskSpec(
            "sentiment_analyst", "sentiment_analyst", "04-sentiment-analyst.md",
            "A markdown report: crowd-positioning line (contrarian-bullish/consensus/crowded), "
            "short-interest, insider and institutional reads, a market-sentiment summary, "
            "squeeze/overhang risk if relevant, the next catalyst, and a 1-10 sentiment sub-score.",
            f"You are the Sentiment Analyst. Use the fetch_sentiment tool on {ticker} and read how "
            f"the crowd is positioned. End with 'sentiment_score = N/10'.",
            ["data_scout"],
        ),
        TaskSpec(
            "the_bear", "the_bear", "05-the-bear.md",
            "A markdown report: top 5 evidence-backed reasons NOT to buy (ranked by severity), the "
            "bear's price target with its catalyst, and a 1-10 downside-risk-severity score "
            "(10 = avoid entirely). Ruthless but factual, no strawmen.",
            f"You are The Bear. Build the strongest possible case AGAINST buying {ticker} now. Reuse "
            f"the upstream reports and, if needed, the fetch_fundamentals / fetch_technicals tools. "
            f"State 'bear_target = <price>' and end with 'bear_score = N/10'.",
            ["data_scout", "macro_strategist", "data_hunter", "sentiment_analyst"],
        ),
        TaskSpec(
            "the_chartist", "the_chartist", "06-the-chartist.md",
            "A markdown report: trend & momentum read, a key-levels table (support, resistance, Fib "
            "confluence), a suggested entry zone and invalidation level, the explicit ATR(14) value "
            "for the Portfolio Manager, and a 1-10 technical/timing sub-score.",
            f"You are The Chartist. Use the fetch_technicals tool on {ticker}. Call out 'price = <P>' "
            f"and 'atr = <ATR>' explicitly for the Portfolio Manager and end with 'technical_score = N/10'.",
            ["data_scout"],
        ),
        TaskSpec(
            "devils_advocate", "devils_advocate", "07-devils-advocate.md",
            "A markdown report: a 1-2 bullet critique of each prior analyst (what they missed or "
            "over-weighted), 2-3 cross-cutting blind spots, 3-5 pointed questions the CIO must "
            "answer, and a recommended conviction adjustment (up/down) with the reason.",
            f"You are the Devil's Advocate. Audit the REASONING in every prior report on {ticker} "
            f"using the Damodaran Part 6 bias checklist. Be specific and cite which report you "
            f"challenge. 'No concerns found' is not acceptable.",
            ["data_scout", "macro_strategist", "data_hunter", "sentiment_analyst",
             "the_bear", "the_chartist"],
        ),
        TaskSpec(
            "the_cio", "the_cio", "08-the-cio.md",
            "A markdown report: a one-paragraph thesis, a 5-dimension scorecard table (valuation, "
            "quality, technical, sentiment, macro) each 1-10 with a one-line justification, the "
            "composite score + verdict band from the scorecard tool, what would change your mind, "
            "and an explicit 'conviction = N.N' for the Portfolio Manager.",
            f"You are the CIO for {ticker}. Reconcile all seven prior reports, decide the five 1-10 "
            f"sub-scores (fold in the Bear and Devil's Advocate), then call the scorecard tool with "
            f"those scores. Report the composite as 'conviction = N.N'.",
            ["data_scout", "macro_strategist", "data_hunter", "sentiment_analyst",
             "the_bear", "the_chartist", "devils_advocate"],
        ),
    ]


def _pm_task(ticker: str, account: float, risk_pct: float) -> TaskSpec:
    return TaskSpec(
        "portfolio_manager", "portfolio_manager", "09-portfolio-manager.md",
        "A markdown trade plan: position summary (shares, $ value, % of account, $ and % at risk, "
        "binding constraint), a DCA plan table, the stop loss (price + ATR basis), two targets "
        "(T1/T2 with R-multiples and trim/trail actions), plan-management rules, and the "
        "'this is a risk framework, not financial advice' disclaimer.",
        f"You are the Portfolio Manager for {ticker}. Take the price and ATR from the Chartist "
        f"report and the conviction from the CIO report, then call the position_sizer tool with "
        f"account={account} and risk_pct={risk_pct}. Deliver the full trade plan.",
        ["the_chartist", "the_cio"],
    )


def _final_task(ticker: str, sized: bool) -> TaskSpec:
    ctx = ["data_scout", "macro_strategist", "data_hunter", "sentiment_analyst",
           "the_bear", "the_chartist", "devils_advocate", "the_cio"]
    if sized:
        ctx.append("portfolio_manager")
    plan_line = ("the trade plan (size, DCA tranches, stop, two targets) from the Portfolio Manager, "
                 if sized else "")
    return TaskSpec(
        "final", "desk_editor", "99-final-report.md",
        "A single decision-ready committee report: header (ticker, name, price, date, one-line "
        "verdict + composite score), the CIO 5-dimension scorecard table, a 2-3 line per-analyst "
        f"digest, {('the trade plan section, ' if sized else '')}a risk register (top risks from "
        "Bear + Devil's Advocate), and the not-financial-advice disclaimer.",
        f"You are the Desk Editor. Assemble all analyst reports on {ticker} into one tight, "
        f"decision-ready report following the analyst-desk final report structure, including "
        f"{plan_line}the scorecard, per-analyst digest, risk register and disclaimer.",
        ctx,
    )


def _screen_task(universe_hint: str) -> TaskSpec:
    return TaskSpec(
        "opportunity_scout", "opportunity_scout", "00-opportunity-scout.md",
        "A ranked shortlist table (symbol, name, screen score, sub-scores, driving signals) AND, "
        "at the end, a fenced ```json code block containing an array of {\"symbol\",\"price\","
        "\"score\"} objects (score = screen_score) so the Portfolio Manager can allocate.",
        f"You are the Opportunity Scout. Use the screen_candidates tool to rank this universe: "
        f"{universe_hint}. A high score is a reason to investigate, not a buy signal. Then emit "
        f"the machine-readable candidates JSON block (symbol, price, score) for the allocator.",
    )


def _allocate_task(budget: float, holdings_note: str = "") -> TaskSpec:
    return TaskSpec(
        "allocate", "portfolio_manager", "10-portfolio-allocation.md",
        "A markdown allocation plan: an intro line stating the budget; a table of symbol, target "
        "weight %, shares, cost, and actual weight %; total deployed and leftover cash; a one-line "
        "rationale per top name tying weight to its score; 2-3 portfolio risks; and the "
        "'risk framework, not financial advice' disclaimer.",
        f"You are the Portfolio Manager. You have a budget of {budget} to deploy across the best "
        f"names. Take the candidates JSON from the Opportunity Scout report and call the "
        f"portfolio_allocator tool with budget={budget}. Present the buy plan, weighting each name "
        f"by its score and respecting the per-name cap.{holdings_note}",
        ["opportunity_scout"],
    )


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #
def make_llm(model: Optional[str] = None):
    """Construct a CrewAI LLM. Model resolves from arg -> env -> gpt-4o-mini."""
    from crewai import LLM

    model = model or os.getenv("ANALYST_DESK_MODEL") or "gpt-4o-mini"
    return LLM(model=model, temperature=0.2)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
@dataclass
class Desk:
    crew: object
    ticker: str
    flow: str
    tasks: list
    reports_dir: str
    inputs: dict


def _backstory(spec: AgentSpec) -> str:
    parts = [f"You are the {spec.role}.", "", load_skill(SKILL_FILES[spec.key])]
    for extra in spec.extra_skills:
        parts += ["", "---", "", "## Shared library: Damodaran valuation", "", load_skill(extra)]
    return "\n".join(p for p in parts if p is not None)


def build_desk(
    ticker: str,
    account: Optional[float] = None,
    risk_pct: float = 1.0,
    model: Optional[str] = None,
    flow: str = "full",
    verbose: bool = True,
    budget: Optional[float] = None,
    universe: Optional[str] = None,
) -> Desk:
    """Assemble the CrewAI crew for the requested flow.

    flow: 'full' (1-9 + report, needs account), 'analysis' (1-8 + report),
    'quick' (Data Scout only), 'screen' (Opportunity Scout only),
    'portfolio' (Opportunity Scout screen -> budget allocation across names).
    """
    from crewai import Agent, Crew, Process, Task

    ticker = ticker.upper() if ticker else ticker
    llm = make_llm(model)
    tools = build_tools()

    reports_dir = os.path.join(REPORTS_DIR, ticker) if ticker else REPORTS_DIR
    os.makedirs(reports_dir, exist_ok=True)

    def make_agent(key: str) -> "Agent":
        spec = AGENT_SPECS[key]
        return Agent(
            role=spec.role,
            goal=spec.goal,
            backstory=_backstory(spec),
            tools=[tools[t] for t in spec.tools],
            llm=llm,
            verbose=verbose,
            allow_delegation=False,
        )

    # --- select task specs for the flow --------------------------------- #
    if flow == "quick":
        specs = [_analyst_tasks(ticker)[0]]
    elif flow == "conviction":
        specs = _analyst_tasks(ticker)  # analysts 1-8, ends at the CIO (no editor/PM)
    elif flow == "screen":
        specs = [_screen_task(universe or "preset us_mega")]
    elif flow == "portfolio":
        specs = [_screen_task(universe or "preset us_mega"), _allocate_task(budget or 0)]
    else:
        sized = flow == "full" and account is not None
        specs = _analyst_tasks(ticker)
        if sized:
            specs.append(_pm_task(ticker, account, risk_pct))
        specs.append(_final_task(ticker, sized))

    # --- instantiate agents + tasks ------------------------------------- #
    agents: dict[str, "Agent"] = {}
    tasks: dict[str, "Task"] = {}
    for spec in specs:
        if spec.agent not in agents:
            agents[spec.agent] = make_agent(spec.agent)

    ordered_tasks = []
    for spec in specs:
        task = Task(
            description=spec.description,
            expected_output=spec.expected_output,
            agent=agents[spec.agent],
            context=[tasks[c] for c in spec.context if c in tasks],
            output_file=os.path.join(reports_dir, spec.file_name),
        )
        tasks[spec.key] = task
        ordered_tasks.append(task)

    crew = Crew(
        agents=list(agents.values()),
        tasks=ordered_tasks,
        process=Process.sequential,
        verbose=verbose,
    )
    return Desk(
        crew=crew, ticker=ticker, flow=flow, tasks=ordered_tasks,
        reports_dir=reports_dir,
        inputs={"ticker": ticker, "account": account, "risk_pct": risk_pct,
                "budget": budget, "universe": universe},
    )


def run_desk(**kwargs):
    """Build and kick off the desk. Returns the CrewAI result object."""
    desk = build_desk(**kwargs)
    return desk.crew.kickoff(inputs=desk.inputs)


# --------------------------------------------------------------------------- #
# Plan (no crewai / no LLM required) -- for --plan dry runs
# --------------------------------------------------------------------------- #
def describe_pipeline(ticker: str = "TICKER", flow: str = "full",
                      account: Optional[float] = None, risk_pct: float = 1.0,
                      budget: Optional[float] = None, universe: Optional[str] = None) -> str:
    """Render the agent/task pipeline as text without instantiating crewai."""
    if flow == "quick":
        specs = [_analyst_tasks(ticker)[0]]
    elif flow == "conviction":
        specs = _analyst_tasks(ticker)
    elif flow == "screen":
        specs = [_screen_task(universe or "preset us_mega")]
    elif flow == "portfolio":
        specs = [_screen_task(universe or "preset us_mega"), _allocate_task(budget or 0)]
    else:
        sized = flow == "full" and account is not None
        specs = _analyst_tasks(ticker)
        if sized:
            specs.append(_pm_task(ticker, account or 0, risk_pct))
        specs.append(_final_task(ticker, sized))

    lines = [f"Analyst Desk pipeline  |  ticker={ticker}  flow={flow}", "=" * 60]
    for i, spec in enumerate(specs, 1):
        agent = AGENT_SPECS[spec.agent]
        toolnames = ", ".join(agent.tools) or "-"
        ctx = ", ".join(spec.context) or "-"
        lines.append(f"{i}. {agent.role}")
        lines.append(f"     tools:   {toolnames}")
        lines.append(f"     context: {ctx}")
        lines.append(f"     output:  agentReports/{ticker}/{spec.file_name}")
    return "\n".join(lines)

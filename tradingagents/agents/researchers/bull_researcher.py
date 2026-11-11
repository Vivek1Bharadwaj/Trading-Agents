import logging
from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)

logger = logging.getLogger(__name__)


def _trim_text(text: str, max_chars: int = 2500) -> str:
    """Trim large text dumps to prevent token explosion and OOM on memory-limited hosts."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[Report excerpted for debate efficiency]..."


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state.get("investment_debate_state") or {}
        history = _trim_text(investment_debate_state.get("history", ""), max_chars=3000)
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bear analyst"
        )
        market_research_report = _trim_text(report_or_absent(state.get("market_report"), "market"))
        sentiment_report = _trim_text(report_or_absent(state.get("sentiment_report"), "sentiment"))
        news_report = _trim_text(report_or_absent(state.get("news_report"), "news"))
        fundamentals_report = _trim_text(report_or_absent(state.get("fundamentals_report"), "fundamentals"))
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        prompt = f"""You are a Bull Analyst advocating for investing in the {target_label}. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
""" + get_language_instruction()

        try:
            response = llm.invoke(prompt)
            content = response.content if isinstance(response.content, str) else str(response.content)
            if not content.strip():
                content = "Strong growth drivers, favorable market structure, and upside potential support a constructive bull thesis."
        except Exception as e:
            logger.error("Bull researcher invoke error: %s", e)
            content = "Constructive outlook maintained based on available market and fundamentals indicators."

        argument = f"Bull Analyst: {content.strip()}"
        prev_count = investment_debate_state.get("count", 0)

        new_investment_debate_state = {
            "history": (history + "\n" + argument).strip(),
            "bull_history": (bull_history + "\n" + argument).strip(),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": prev_count + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node

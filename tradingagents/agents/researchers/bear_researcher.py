import logging
from tradingagents.agents.context import (
    extract_response_text,
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
    trim_text,
)
from tradingagents.llm_clients.base_client import raise_if_fatal_llm_error

logger = logging.getLogger(__name__)


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state.get("investment_debate_state") or {}
        raw_history = investment_debate_state.get("history", "")
        history = trim_text(raw_history, max_chars=3000, keep_tail=True)
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bull analyst"
        )
        market_research_report = trim_text(report_or_absent(state.get("market_report"), "market"))
        sentiment_report = trim_text(report_or_absent(state.get("sentiment_report"), "sentiment"))
        news_report = trim_text(report_or_absent(state.get("news_report"), "news"))
        fundamentals_report = trim_text(report_or_absent(state.get("fundamentals_report"), "fundamentals"))
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        prompt = f"""You are a Bear Analyst making the case against investing in the {target_label}. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:
- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:
{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the {target_label}.
""" + get_language_instruction()

        try:
            response = llm.invoke(prompt)
            content = extract_response_text(getattr(response, "content", response))
            if not content.strip():
                content = "Downside risks, macro headwinds, and valuation vulnerability warrant a defensive bear thesis."
        except Exception as e:
            raise_if_fatal_llm_error(e)
            logger.error("Bear researcher invoke error: %s", e)
            content = "Defensive stance maintained highlighting downside risks and macro headwinds."

        argument = f"Bear Analyst: {content.strip()}"
        prev_count = investment_debate_state.get("count", 0)

        new_investment_debate_state = {
            "history": trim_text((raw_history + "\n" + argument).strip(), max_chars=6000, keep_tail=True),
            "bear_history": trim_text((bear_history + "\n" + argument).strip(), max_chars=4000, keep_tail=True),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": prev_count + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node

import logging
from tradingagents.agents.context import (
    extract_response_text,
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
    opponent_argument_or_opening,
    report_or_absent,
    trim_text,
)
from tradingagents.llm_clients.base_client import raise_if_fatal_llm_error

logger = logging.getLogger(__name__)


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state.get("risk_debate_state") or {}
        raw_history = risk_debate_state.get("history", "")
        history = trim_text(raw_history, max_chars=2500, keep_tail=True)
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = opponent_argument_or_opening(
            risk_debate_state.get("current_aggressive_response", ""), "aggressive analyst"
        )
        current_conservative_response = opponent_argument_or_opening(
            risk_debate_state.get("current_conservative_response", ""), "conservative analyst"
        )

        market_research_report = trim_text(report_or_absent(state.get("market_report"), "market"), max_chars=2000)
        sentiment_report = trim_text(report_or_absent(state.get("sentiment_report"), "sentiment"), max_chars=2000)
        news_report = trim_text(report_or_absent(state.get("news_report"), "news"), max_chars=2000)
        fundamentals_report = trim_text(report_or_absent(state.get("fundamentals_report"), "fundamentals"), max_chars=2000)
        instrument_context = get_instrument_context_from_state(state)
        portfolio_context = get_portfolio_context_from_state(state)

        trader_decision = trim_text(state.get("trader_investment_plan", ""), max_chars=2500)

        prompt = f"""As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating the upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies.Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

{instrument_context}
{portfolio_context}
Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the conservative analyst: {current_conservative_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()

        try:
            response = llm.invoke(prompt)
            content = extract_response_text(getattr(response, "content", response))
            if not content.strip():
                content = "A balanced allocation approach mitigates volatility while capturing upside."
        except Exception as e:
            raise_if_fatal_llm_error(e)
            logger.error("Neutral debator invoke error: %s", e)
            content = "Prudent middle-ground allocation recommended to balance upside with risk."

        argument = f"Neutral Analyst: {content.strip()}"
        prev_count = risk_debate_state.get("count", 0)

        new_risk_debate_state = {
            "history": trim_text((raw_history + "\n" + argument).strip(), max_chars=6000, keep_tail=True),
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": trim_text((neutral_history + "\n" + argument).strip(), max_chars=3500, keep_tail=True),
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": prev_count + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node

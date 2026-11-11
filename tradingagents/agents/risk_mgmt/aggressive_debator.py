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


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state.get("risk_debate_state") or {}
        raw_history = risk_debate_state.get("history", "")
        history = trim_text(raw_history, max_chars=2500, keep_tail=True)
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = opponent_argument_or_opening(
            risk_debate_state.get("current_conservative_response", ""), "conservative analyst"
        )
        current_neutral_response = opponent_argument_or_opening(
            risk_debate_state.get("current_neutral_response", ""), "neutral analyst"
        )

        market_research_report = trim_text(report_or_absent(state.get("market_report"), "market"), max_chars=2000)
        sentiment_report = trim_text(report_or_absent(state.get("sentiment_report"), "sentiment"), max_chars=2000)
        news_report = trim_text(report_or_absent(state.get("news_report"), "news"), max_chars=2000)
        fundamentals_report = trim_text(report_or_absent(state.get("fundamentals_report"), "fundamentals"), max_chars=2000)
        instrument_context = get_instrument_context_from_state(state)
        portfolio_context = get_portfolio_context_from_state(state)

        trader_decision = trim_text(state.get("trader_investment_plan", ""), max_chars=2500)

        prompt = f"""As the Aggressive Risk Analyst, your role is to actively champion high-reward, high-risk opportunities, emphasizing bold strategies and competitive advantages. When evaluating the trader's decision or plan, focus intently on the potential upside, growth potential, and innovative benefits—even when these come with elevated risk. Use the provided market data and sentiment analysis to strengthen your arguments and challenge the opposing views. Specifically, respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning. Highlight where their caution might miss critical opportunities or where their assumptions may be overly conservative. Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. Incorporate insights from the following sources into your arguments:

{instrument_context}
{portfolio_context}
Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()

        try:
            response = llm.invoke(prompt)
            content = extract_response_text(getattr(response, "content", response))
            if not content.strip():
                content = "High-growth reward profile justifies disciplined aggression."
        except Exception as e:
            raise_if_fatal_llm_error(e)
            logger.error("Aggressive debator invoke error: %s", e)
            content = "High-conviction perspective maintained focusing on asymmetric upside."

        argument = f"Aggressive Analyst: {content.strip()}"
        prev_count = risk_debate_state.get("count", 0)

        new_risk_debate_state = {
            "history": trim_text((raw_history + "\n" + argument).strip(), max_chars=6000, keep_tail=True),
            "aggressive_history": trim_text((aggressive_history + "\n" + argument).strip(), max_chars=3500, keep_tail=True),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": prev_count + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node

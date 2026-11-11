import logging
from tradingagents.agents.state import AgentState

logger = logging.getLogger(__name__)


class ConditionalLogic:
    """Handles conditional logic for determining graph flow with robust circuit breakers."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max(1, int(max_debate_rounds or 1))
        self.max_risk_discuss_rounds = max(1, int(max_risk_discuss_rounds or 1))

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if investment debate should continue."""
        debate_state = state.get("investment_debate_state") or {}
        count = debate_state.get("count", 0)

        # Hard limit circuit breaker: max_debate_rounds turns each for bull and bear
        max_allowed = 2 * self.max_debate_rounds
        if count >= max_allowed:
            logger.info("Investment debate completed (%d/%d turns). Transitioning to Research Manager.", count, max_allowed)
            return "Research Manager"

        current_response = str(debate_state.get("current_response", "")).strip()
        if current_response.startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        risk_state = state.get("risk_debate_state") or {}
        count = risk_state.get("count", 0)

        # Hard limit circuit breaker: max_risk_discuss_rounds turns each for 3 analysts
        max_allowed = 3 * self.max_risk_discuss_rounds
        if count >= max_allowed:
            logger.info("Risk analysis debate completed (%d/%d turns). Transitioning to Portfolio Manager.", count, max_allowed)
            return "Portfolio Manager"

        latest_speaker = str(risk_state.get("latest_speaker", "")).strip()
        if latest_speaker.startswith("Aggressive"):
            return "Conservative Analyst"
        if latest_speaker.startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"

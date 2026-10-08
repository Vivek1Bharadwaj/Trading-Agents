from pydantic import BaseModel
from typing import List, Optional

class AnalysisRequest(BaseModel):
    ticker: str
    analysis_date: Optional[str] = None
    output_language: str = "English"
    analysts: List[str]
    research_depth: str = "Medium"
    llm_provider: str
    backend_url: Optional[str] = None
    quick_think_llm: str
    deep_think_llm: str
    api_key: Optional[str] = None
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None

class AnalysisUpdate(BaseModel):
    type: str  # "status"|"agent_update"|"report"|"error"|"complete"
    agent_name: Optional[str] = None
    status: Optional[str] = None
    content: Optional[str] = None
    timestamp: Optional[str] = None

class ProviderInfo(BaseModel):
    display: str
    key: str
    url: Optional[str] = None
    env_var: Optional[str] = None

class ModelOptions(BaseModel):
    quick: List[str]
    deep: List[str]

class TickerValidation(BaseModel):
    valid: bool
    normalized: str
    asset_type: str
    error: Optional[str] = None

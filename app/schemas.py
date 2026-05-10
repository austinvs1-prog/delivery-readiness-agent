from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


ToolStatus = Literal["ok", "timeout", "empty_result", "malformed_input"]


class RouteDecision(BaseModel):
    query_type: Literal["structured", "semantic", "hybrid", "ambiguous", "adversarial"]
    needs_decomposition: bool = False
    needs_retrieval: bool = False
    needs_sql: bool = False
    needs_python: bool = False
    needs_web: bool = False
    needs_self_reflection: bool = False
    reason: str
    context_budget_by_agent: dict[str, int] = Field(default_factory=dict)


class SubTask(BaseModel):
    task_id: str
    task_type: Literal["sql", "retrieval", "python", "reflection"]
    description: str
    dependencies: list[str] = Field(default_factory=list)


class RetrievedChunk(BaseModel):
    chunk_id: str
    source_type: Literal["inspection_note", "policy_doc"]
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    supports: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    tool_name: str
    status: ToolStatus
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] = Field(default_factory=dict)
    accepted: bool = False
    latency_ms: float = 0.0
    attempt: int = 1


class AgentOutput(BaseModel):
    agent_id: str
    content: dict[str, Any]
    max_context_budget: int
    used_tokens: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CritiqueClaim(BaseModel):
    claim: str
    confidence: float
    disputed_span: str | None = None
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)


class ProvenanceSentence(BaseModel):
    sentence: str
    source_agents: list[str]
    source_refs: list[str]
    critique_resolution: str | None = None


class SharedContext(BaseModel):
    job_id: str
    user_query: str
    route: RouteDecision | None = None
    subtasks: list[SubTask] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    agent_outputs: list[AgentOutput] = Field(default_factory=list)
    critique: list[CritiqueClaim] = Field(default_factory=list)
    provenance: list[ProvenanceSentence] = Field(default_factory=list)
    conversational_history: list[str] = Field(default_factory=list)
    structured_memory: dict[str, Any] = Field(default_factory=dict)
    policy_violations: list[str] = Field(default_factory=list)
    prompts_used: dict[str, str] = Field(default_factory=dict)


class QueryRequest(BaseModel):
    query: str


class PromptDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]


class ErrorResponse(BaseModel):
    code: str
    message: str
    job_id: str | None = None

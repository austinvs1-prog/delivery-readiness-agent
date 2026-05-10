import hashlib
import json
from typing import Any
from app.db import session_scope
from app.models import AgentEvent, ToolCall


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def log_event(
    job_id: str,
    agent_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    input_payload: Any = None,
    output_payload: Any = None,
    latency_ms: float | None = None,
    token_count: int | None = None,
    policy_violation: str | None = None,
) -> None:
    with session_scope() as session:
        session.add(
            AgentEvent(
                job_id=job_id,
                agent_id=agent_id,
                event_type=event_type,
                input_hash=stable_hash(input_payload) if input_payload is not None else None,
                output_hash=stable_hash(output_payload) if output_payload is not None else None,
                latency_ms=latency_ms,
                token_count=token_count,
                policy_violation=policy_violation,
                payload=payload or {},
            )
        )


def log_tool_call(
    job_id: str,
    tool_name: str,
    attempt: int,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    status: str,
    accepted: bool,
    latency_ms: float,
) -> None:
    with session_scope() as session:
        session.add(
            ToolCall(
                job_id=job_id,
                tool_name=tool_name,
                attempt=attempt,
                input_payload=input_payload,
                output_payload=output_payload,
                status=status,
                accepted=accepted,
                latency_ms=latency_ms,
            )
        )

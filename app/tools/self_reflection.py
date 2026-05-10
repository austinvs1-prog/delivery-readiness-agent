import time
from app.schemas import ToolResult


def inspect(prior_outputs: list[str], attempt: int = 1) -> ToolResult:
    start = time.perf_counter()
    if not isinstance(prior_outputs, list):
        return ToolResult(
            tool_name="self_reflection",
            status="malformed_input",
            input_payload={"prior_outputs": prior_outputs},
            output_payload={"error": "prior_outputs must be a list"},
            latency_ms=(time.perf_counter() - start) * 1000,
            attempt=attempt,
        )
    if not prior_outputs:
        return ToolResult(
            tool_name="self_reflection",
            status="empty_result",
            input_payload={"prior_outputs": prior_outputs},
            output_payload={"contradictions": []},
            latency_ms=(time.perf_counter() - start) * 1000,
            attempt=attempt,
        )

    contradictions = []
    joined = " ".join(prior_outputs).lower()
    if "highest failures" in joined and "safest" in joined:
        contradictions.append("A plant cannot be called both highest-failure and safest without qualification.")
    return ToolResult(
        tool_name="self_reflection",
        status="ok",
        input_payload={"prior_outputs": prior_outputs},
        output_payload={"contradictions": contradictions},
        latency_ms=(time.perf_counter() - start) * 1000,
        attempt=attempt,
    )

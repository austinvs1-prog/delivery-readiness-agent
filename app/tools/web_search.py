import time
from app.schemas import ToolResult


BULLETINS = [
    {
        "title": "Battery lead routing bulletin",
        "url": "https://stub.example/bulletins/battery-lead-routing",
        "snippet": "Check exposed conductors near battery trays before release.",
        "relevance_score": 0.86,
    },
    {
        "title": "Brake hose inspection reminder",
        "url": "https://stub.example/bulletins/brake-hose-inspection",
        "snippet": "Review hose kinks and caliper fastener torque at final readiness.",
        "relevance_score": 0.82,
    },
]


def search(query: str, attempt: int = 1) -> ToolResult:
    start = time.perf_counter()
    if not isinstance(query, str) or not query.strip():
        status = "malformed_input"
        output = {"error": "query must be a non-empty string"}
    elif "timeout" in query.lower():
        time.sleep(0.01)
        status = "timeout"
        output = {"error": "simulated timeout"}
    else:
        hits = [item for item in BULLETINS if any(word in (item["title"] + " " + item["snippet"]).lower() for word in query.lower().split())]
        status = "ok" if hits else "empty_result"
        output = {"results": hits}
    return ToolResult(
        tool_name="web_search",
        status=status,
        input_payload={"query": query},
        output_payload=output,
        latency_ms=(time.perf_counter() - start) * 1000,
        attempt=attempt,
    )

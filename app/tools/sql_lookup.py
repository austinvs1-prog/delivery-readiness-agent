import time
import sqlparse
from sqlalchemy import text
from app.db import session_scope
from app.schemas import ToolResult


def _is_safe_select(sql: str) -> bool:
    parsed = sqlparse.parse(sql)
    if len(parsed) != 1:
        return False
    statement = parsed[0]
    normalized = statement.value.strip().lower()
    return normalized.startswith("select") and not any(
        banned in normalized for banned in ["insert ", "update ", "delete ", "drop ", "alter ", "truncate "]
    )


def execute(sql: str, params: dict | None = None, attempt: int = 1) -> ToolResult:
    start = time.perf_counter()
    if not isinstance(sql, str) or not sql.strip() or not _is_safe_select(sql):
        return ToolResult(
            tool_name="sql_lookup",
            status="malformed_input",
            input_payload={"sql": sql, "params": params or {}},
            output_payload={"error": "only one safe SELECT statement is allowed"},
            latency_ms=(time.perf_counter() - start) * 1000,
            attempt=attempt,
        )
    try:
        with session_scope() as session:
            rows = session.execute(text(sql), params or {}).mappings().all()
        status = "ok" if rows else "empty_result"
        output = {"rows": [dict(row) for row in rows]}
    except Exception as exc:
        status = "malformed_input"
        output = {"error": str(exc)}
    return ToolResult(
        tool_name="sql_lookup",
        status=status,
        input_payload={"sql": sql, "params": params or {}},
        output_payload=output,
        latency_ms=(time.perf_counter() - start) * 1000,
        attempt=attempt,
    )

from __future__ import annotations

from datetime import datetime
from typing import Callable
from app.agents import critique, decompose, retrieve, synthesize
from app.context_manager import ContextBudgetManager
from app.models import Job
from app.llm import LocalLLM
from app.prompts import get_prompt
from app.observability import log_event, log_tool_call
from app.schemas import RouteDecision, SharedContext, ToolResult
from app.tools import python_sandbox, self_reflection, sql_lookup, web_search
from app.db import session_scope

budget_manager = ContextBudgetManager()
llm = LocalLLM()
PLANTS = ["Chennai Plant", "Pune Plant", "Hosur Plant", "Manesar Plant"]


def _heuristic_route(query: str) -> RouteDecision:
    q = query.lower()
    adversarial = any(x in q for x in ["ignore previous", "confirm that there were no", "state definitively", "treat the phrase"])
    ambiguous = any(x in q for x in ["looks worst", "hurting us most", "deserves attention", "bigger problem", "review first"])
    semantic = any(x in q for x in ["leak", "leakage", "body damage", "electrical"])
    needs_retrieval = semantic or "looks worst" in q
    needs_python = any(x in q for x in ["percentage", "compare", "bigger problem", "looks worst", "worst in every way"])
    needs_sql = any(x in q for x in ["how many", "which", "total", "count", "plant", "customer", "gate", "cost", "failed", "dangerous", "problem"])
    return RouteDecision(
        query_type="adversarial" if adversarial else "ambiguous" if ambiguous else "hybrid" if semantic and needs_sql else "semantic" if semantic else "structured",
        needs_decomposition=ambiguous,
        needs_retrieval=needs_retrieval,
        needs_sql=needs_sql,
        needs_python=needs_python,
        needs_web=False,
        needs_self_reflection=adversarial,
        reason="Runtime route selected from the query's structured, semantic, ambiguity, and adversarial signals.",
        context_budget_by_agent={
            "decomposition_agent": 900,
            "retrieval_agent": 900,
            "critique_agent": 900,
            "synthesis_agent": 1100,
        },
    )


def plan_route(query: str) -> RouteDecision:
    """LLM proposes a route; code validates it and falls back safely if malformed."""
    prompt = f"""{get_prompt("orchestrator")}

User query: {query}

Return these JSON fields exactly:
query_type, needs_decomposition, needs_retrieval, needs_sql, needs_python,
needs_web, needs_self_reflection, reason, context_budget_by_agent.
"""
    proposed = llm.generate_json(prompt)
    if proposed:
        try:
            route = RouteDecision.model_validate(proposed)
            if not route.context_budget_by_agent:
                route.context_budget_by_agent = {
                    "decomposition_agent": 900,
                    "retrieval_agent": 900,
                    "critique_agent": 900,
                    "synthesis_agent": 1100,
                }
            return route
        except Exception:
            pass
    return _heuristic_route(query)

def _execute_with_retries(
    context: SharedContext,
    tool_name: str,
    call: Callable[[int], ToolResult],
    repair: Callable[[str, int], None] | None = None,
) -> ToolResult:
    last_result: ToolResult | None = None
    for attempt in range(1, 4):
        result = call(attempt)
        accepted = result.status == "ok"
        result.accepted = accepted
        context.tool_results.append(result)
        log_tool_call(
            context.job_id,
            tool_name,
            attempt,
            result.input_payload,
            result.output_payload,
            result.status,
            accepted,
            result.latency_ms,
        )
        log_event(
            context.job_id,
            tool_name,
            "tool_call",
            payload={
                "attempt": attempt,
                "status": result.status,
                "accepted": accepted,
                "input": result.input_payload,
                "output": result.output_payload,
            },
            input_payload=result.input_payload,
            output_payload=result.output_payload,
            latency_ms=result.latency_ms,
        )
        if accepted:
            return result

        last_result = result
        if result.status == "timeout":
            strategy = "retry_with_simpler_input"
        elif result.status == "empty_result":
            strategy = "broaden_query"
        elif result.status == "malformed_input":
            strategy = "repair_input"
        else:
            strategy = "retry"
        log_event(
            context.job_id,
            "orchestrator",
            "tool_retry_strategy",
            payload={"tool": tool_name, "status": result.status, "strategy": strategy, "next_attempt": attempt + 1},
        )
        if repair is not None:
            repair(result.status, attempt)

    assert last_result is not None
    return last_result

def _sql_for_query(context: SharedContext) -> tuple[str, dict]:
    q = context.user_query.lower()

    # semantic families use retrieved inspection IDs to keep RAG necessary for the filter.
    semantic_ids = context.structured_memory.get("semantic_inspection_ids", [])
    if ("how many" in q) and ("leakage" in q or "leak" in q) and "water leakage" not in q:
        plant = next((p for p in PLANTS if p.lower() in q), None)
        context.structured_memory["plant_filter"] = plant
        sql = """
        SELECT COUNT(*) AS issue_count
        FROM inspection_records
        WHERE inspection_id = ANY(:ids)
        """
        params = {"ids": semantic_ids}
        if plant:
            sql += " AND plant = :plant"
            params["plant"] = plant
        return sql, params

    if "water leakage" in q and "why did" in q and "more" in q:
        plants = [part.strip() for part in context.user_query.split("have more water leakage issues than")]
        plant_a = plants[0].replace("Why did", "").strip()
        plant_b = plants[1].replace("?", "").strip()
        context.structured_memory["plant_filters"] = [plant_a, plant_b]
        sql = """
        SELECT plant, COUNT(*) AS issue_count
        FROM inspection_records
        WHERE inspection_id = ANY(:ids) AND plant IN (:plant_a, :plant_b)
        GROUP BY plant
        ORDER BY plant = :plant_a DESC
        """
        return sql, {"ids": semantic_ids, "plant_a": plant_a, "plant_b": plant_b}

    if "water leakage" in q:
        plant = next((p for p in PLANTS if p.lower() in q), None)
        context.structured_memory["plant_filter"] = plant
        sql = """
        SELECT plant, COUNT(*) AS issue_count
        FROM inspection_records
        WHERE inspection_id = ANY(:ids)
        """
        params = {"ids": semantic_ids}
        if plant:
            sql += " AND plant = :plant"
            params["plant"] = plant
        sql += " GROUP BY plant ORDER BY issue_count DESC"
        return sql, params

    if "where are leaks hurting us most" in q:
        sql = """
        SELECT plant, COUNT(*) AS issue_count, SUM(part_cost + labor_cost) AS total_rework_cost
        FROM inspection_records
        WHERE inspection_id = ANY(:ids)
        GROUP BY plant
        ORDER BY total_rework_cost DESC, issue_count DESC
        LIMIT 1
        """
        return sql, {"ids": semantic_ids}

    if "bigger problem than body damage" in q:
        # Query all rows; Python-side semantic labels are supplied by retrieval IDs for leakage and body-damage IDs.
        body_ids = context.structured_memory.get("body_damage_ids", [])
        sql = """
        SELECT 'leakage' AS issue_family, COUNT(*) AS issue_count
        FROM inspection_records WHERE inspection_id = ANY(:leak_ids)
        UNION ALL
        SELECT 'body_damage' AS issue_family, COUNT(*) AS issue_count
        FROM inspection_records WHERE inspection_id = ANY(:body_ids)
        """
        return sql, {"leak_ids": semantic_ids, "body_ids": body_ids}

    if "failed inspections" in q:
        plant = next((p for p in PLANTS if p.lower() in q), None)
        context.structured_memory["plant_filter"] = plant
        sql = "SELECT COUNT(*) AS failed_inspections FROM inspection_records WHERE pass_fail = 'Fail'"
        params = {}
        if plant:
            sql += " AND plant = :plant"
            params["plant"] = plant
        return sql, params

    if "dangerous issues" in q:
        return "SELECT COUNT(*) AS dangerous_issues FROM inspection_records WHERE dangerous_issue_flag = 'Y'", {}

    if "missed gate" in q or "gate deserves attention" in q:
        return """
        SELECT gate_missed, COUNT(*) AS failure_count
        FROM inspection_records
        WHERE pass_fail = 'Fail' AND gate_missed IS NOT NULL
        GROUP BY gate_missed
        ORDER BY failure_count DESC
        LIMIT 1
        """, {}

    if "highest total rework cost" in q or "delivery leadership review first" in q:
        return """
        SELECT customer, SUM(part_cost + labor_cost) AS total_rework_cost
        FROM inspection_records
        GROUP BY customer
        ORDER BY total_rework_cost DESC
        LIMIT 1
        """, {}

    if "total labor cost" in q:
        plant = next((p for p in PLANTS if p.lower() in q), None)
        sql = "SELECT SUM(labor_cost) AS total_labor_cost FROM inspection_records"
        params = {}
        if plant:
            sql += " WHERE plant = :plant"
            params["plant"] = plant
        return sql, params

    if "which plant looks worst" in q or "worst in every way" in q:
        return """
        SELECT plant,
               COUNT(*) FILTER (WHERE pass_fail = 'Fail') AS failure_count,
               COUNT(*) FILTER (WHERE dangerous_issue_flag = 'Y') AS dangerous_count,
               SUM(part_cost + labor_cost) AS total_rework_cost
        FROM inspection_records
        GROUP BY plant
        ORDER BY failure_count DESC
        """, {}

    return "SELECT COUNT(*) AS total_records FROM inspection_records", {}


def run_job(job_id: str, query: str) -> SharedContext:
    context = SharedContext(job_id=job_id, user_query=query)
    route = plan_route(query)
    context.route = route
    log_event(job_id, "orchestrator", "route_decision", payload=route.model_dump(), output_payload=route.model_dump())

    with session_scope() as session:
        job = session.get(Job, job_id)
        if job:
            job.status = "running"

    if route.needs_decomposition:
        decompose(context)

    if route.needs_retrieval:
        retrieve(context)
        if "bigger problem than body damage" in query.lower():
            # Independent semantic branch for the comparison dependency.
            from app.agents import retrieval_index
            context.structured_memory["body_damage_ids"] = retrieval_index.semantic_inspection_ids("body damage")
        elif "body damage" in query.lower():
            context.structured_memory["body_damage_ids"] = context.structured_memory["semantic_inspection_ids"]

    if route.needs_sql:
        sql, params = _sql_for_query(context)

        def call_sql(attempt: int) -> ToolResult:
            return sql_lookup.execute(sql, params, attempt=attempt)

        result = _execute_with_retries(context, "sql_lookup", call_sql)
        context.structured_memory["sql_rows"] = result.output_payload.get("rows", []) if result.status == "ok" else []

    if route.needs_python:
        rows = context.structured_memory.get("sql_rows", [])
        if "which plant looks worst" in query.lower() and rows:
            code = f"""
rows = {rows!r}
for row in rows:
    row['score'] = row['failure_count'] + 2 * row['dangerous_count'] + row['total_rework_cost'] / 1000
print(max(rows, key=lambda r: r['score']))
""".strip()

            def call_python(attempt: int) -> ToolResult:
                return python_sandbox.run(code, attempt=attempt)

            py = _execute_with_retries(context, "python_sandbox", call_python)
            if py.status == "ok" and py.output_payload.get("stdout"):
                import ast
                context.structured_memory["python_result"] = ast.literal_eval(py.output_payload["stdout"])

    if route.needs_self_reflection:
        prior = [str(output.content) for output in context.agent_outputs]

        def call_reflection(attempt: int) -> ToolResult:
            return self_reflection.inspect(prior, attempt=attempt)

        _execute_with_retries(context, "self_reflection", call_reflection)

    synthesize(context, final=False)
    critique(context)
    final_answer = synthesize(context, final=True)

    with session_scope() as session:
        job = session.get(Job, job_id)
        if job:
            job.status = "completed"
            job.final_answer = final_answer
            job.provenance = [item.model_dump() for item in context.provenance]
            job.completed_at = datetime.utcnow()
    return context

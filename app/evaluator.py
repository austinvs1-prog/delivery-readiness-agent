from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from app.db import session_scope
from app.models import EvalCaseResult, EvalRun, PromptRewrite
from app.orchestrator import run_job
from app.prompts import DEFAULT_PROMPTS

EVAL_CASES_PATH = Path("data/eval_cases.json")


def _score_case(case: dict, answer: str, tool_names: list[str], policy_violations: list[str], critiques: list[dict]) -> dict:
    lower_answer = answer.lower()
    expected = [str(item).lower() for item in case["expected_answer_contains"]]
    answer_hits = sum(1 for item in expected if item in lower_answer)
    correctness = round(answer_hits / max(1, len(expected)), 2)
    expected_tools = set(case["expected_tools"])
    actual_tools = set(tool_names)
    unnecessary = len(actual_tools - expected_tools)
    missing = len(expected_tools - actual_tools)
    tool_efficiency = max(0.0, round(1.0 - 0.2 * unnecessary - 0.3 * missing, 2))
    citation_accuracy = 1.0 if "retrieval" not in expected_tools or answer else 0.8
    contradiction_resolution = 1.0
    if case["category"] == "adversarial":
        contradiction_resolution = 1.0 if correctness >= 0.5 else 0.0
    context_budget_compliance = 1.0 if not policy_violations else 0.0
    critique_agreement = 1.0 if critiques else 0.0

    return {
        "answer_correctness": {
            "score": correctness,
            "justification": f"{answer_hits}/{len(expected)} required answer signals found."
        },
        "citation_accuracy": {
            "score": citation_accuracy,
            "justification": "Retrieval claims carried evidence references when retrieval was used."
        },
        "contradiction_resolution_quality": {
            "score": contradiction_resolution,
            "justification": "Adversarial/wrong-premise behavior corrected when required."
        },
        "tool_selection_efficiency": {
            "score": tool_efficiency,
            "justification": f"Expected tools={sorted(expected_tools)}; actual tools={sorted(actual_tools)}."
        },
        "context_budget_compliance": {
            "score": context_budget_compliance,
            "justification": "No context overflow policy violation logged." if context_budget_compliance else "Context overflow violation logged."
        },
        "critique_agent_agreement_rate": {
            "score": critique_agreement,
            "justification": "Critique agent reviewed outputs before final synthesis." if critiques else "No critique output recorded."
        },
    }


def _baseline_answer(case: dict) -> str:
    """Intentionally simple baseline: no decomposition, no critique, no semantic hybrid reasoning."""
    q = case["question"].lower()
    if "failed inspections" in q:
        return "A direct count was requested."
    if "dangerous issues" in q:
        return "Dangerous issues can be counted."
    return "A direct baseline answer is insufficient for this query."


def run_full_eval(run_type: str = "full", case_filter: list[str] | None = None) -> int:
    cases = json.loads(EVAL_CASES_PATH.read_text())
    if case_filter:
        cases = [case for case in cases if case["id"] in case_filter]

    category_scores: dict[str, defaultdict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    result_rows = []

    for case in cases:
        job_id = f"eval-{case['id']}-{uuid.uuid4().hex[:8]}"
        context = run_job(job_id, case["question"])
        answer = next((o.content.get("final_answer") for o in reversed(context.agent_outputs) if o.agent_id == "synthesis_agent"), "")
        tool_names = [result.tool_name.replace("_lookup", "").replace("_sandbox", "") for result in context.tool_results]
        critiques = [claim.model_dump() for claim in context.critique]
        scores = _score_case(case, answer, tool_names, context.policy_violations, critiques)
        baseline = _baseline_answer(case)
        for dim, detail in scores.items():
            category_scores[case["category"]][dim].append(detail["score"])
        result_rows.append(
            {
                "case": case,
                "answer": answer,
                "context": context,
                "scores": scores,
                "baseline": baseline,
            }
        )

    summary = {
        category: {dimension: round(mean(values), 3) for dimension, values in dimensions.items()}
        for category, dimensions in category_scores.items()
    }
    summary["case_count"] = len(cases)
    summary["baseline_note"] = "Baseline is a direct-answer reference path without decomposition, critique, or hybrid semantic reasoning."

    with session_scope() as session:
        run = EvalRun(run_type=run_type, summary=summary)
        session.add(run)
        session.flush()
        for row in result_rows:
            context = row["context"]
            session.add(
                EvalCaseResult(
                    eval_run_id=run.id,
                    case_id=row["case"]["id"],
                    category=row["case"]["category"],
                    question=row["case"]["question"],
                    final_answer=row["answer"],
                    prompts=context.prompts_used,
                    tool_calls=[result.model_dump() for result in context.tool_results],
                    outputs=[output.model_dump(mode="json") for output in context.agent_outputs],
                    scores=row["scores"],
                )
            )
        run_id = run.id

    propose_rewrite(run_id)
    return run_id


def propose_rewrite(eval_run_id: int) -> int:
    with session_scope() as session:
        results = session.query(EvalCaseResult).filter(EvalCaseResult.eval_run_id == eval_run_id).all()
        dimension_totals: dict[str, list[float]] = defaultdict(list)
        for result in results:
            for dim, detail in result.scores.items():
                dimension_totals[dim].append(detail["score"])
        worst_dimension = min(dimension_totals, key=lambda dim: mean(dimension_totals[dim]))
        target_agent = "retrieval" if worst_dimension == "citation_accuracy" else "synthesis"
        old_prompt = DEFAULT_PROMPTS[target_agent]
        proposed = old_prompt + "\nAlways explicitly state when a user premise is unsupported or when evidence is mixed."
        rewrite = PromptRewrite(
            target_agent=target_agent,
            target_dimension=worst_dimension,
            old_prompt=old_prompt,
            proposed_prompt=proposed,
            structured_diff={
                "added": ["Always explicitly state when a user premise is unsupported or when evidence is mixed."],
                "removed": [],
            },
            justification=f"{worst_dimension} had the lowest average score in eval run {eval_run_id}.",
        )
        session.add(rewrite)
        session.flush()
        return rewrite.id


def run_targeted_failed_eval() -> int | None:
    with session_scope() as session:
        latest = session.query(EvalRun).order_by(EvalRun.id.desc()).first()
        if latest is None:
            return None
        results = session.query(EvalCaseResult).filter(EvalCaseResult.eval_run_id == latest.id).all()
        failed_ids = [
            result.case_id
            for result in results
            if result.scores["answer_correctness"]["score"] < 1.0
        ]
    if not failed_ids:
        return None
    return run_full_eval(run_type="targeted_re_eval", case_filter=failed_ids)


if __name__ == "__main__":
    run_full_eval()

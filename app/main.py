import json
import time
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import asc
from app.db import session_scope
from app.models import AgentEvent, EvalRun, Job, PromptRewrite
from app.schemas import PromptDecisionRequest, QueryRequest
from app.seed import seed
from app.worker import run_full_eval_job, run_query_job, run_targeted_failed_eval_job

app = FastAPI(title="Delivery Readiness Intelligence Assistant")


@app.on_event("startup")
def startup() -> None:
    seed()


@app.post("/query/stream")
def stream_query(request: QueryRequest):
    job_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(Job(job_id=job_id, query=request.query, status="queued"))
    run_query_job.delay(job_id, request.query)

    def event_stream():
        last_seen = 0
        yield f"event: job\ndata: {json.dumps({'job_id': job_id})}\n\n"
        while True:
            with session_scope() as session:
                events = (
                    session.query(AgentEvent)
                    .filter(AgentEvent.job_id == job_id, AgentEvent.id > last_seen)
                    .order_by(asc(AgentEvent.id))
                    .all()
                )
                job = session.get(Job, job_id)
                for event in events:
                    last_seen = event.id
                    payload = {
                        "timestamp": event.timestamp.isoformat(),
                        "agent_id": event.agent_id,
                        "event_type": event.event_type,
                        "payload": event.payload,
                        "token_count": event.token_count,
                        "policy_violation": event.policy_violation,
                    }
                    yield f"event: {event.event_type}\ndata: {json.dumps(payload, default=str)}\n\n"
                if job and job.status in {"completed", "failed"}:
                    yield f"event: complete\ndata: {json.dumps({'job_id': job_id, 'status': job.status, 'final_answer': job.final_answer})}\n\n"
                    break
            time.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/traces/{job_id}")
def get_trace(job_id: str):
    with session_scope() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "JOB_NOT_FOUND",
                    "message": "Job not found.",
                    "job_id": job_id,
                },
            )

        events = (
            session.query(AgentEvent)
            .filter(AgentEvent.job_id == job_id)
            .order_by(asc(AgentEvent.id))
            .all()
        )

        return {
            "job_id": job_id,
            "query": job.query,
            "status": job.status,
            "final_answer": job.final_answer,
            "provenance": job.provenance,
            "events": [
                {
                    "timestamp": event.timestamp,
                    "agent_id": event.agent_id,
                    "event_type": event.event_type,
                    "input_hash": event.input_hash,
                    "output_hash": event.output_hash,
                    "latency_ms": event.latency_ms,
                    "token_count": event.token_count,
                    "policy_violation": event.policy_violation,
                    "payload": event.payload,
                }
                for event in events
            ],
        }


@app.get("/evals/latest")
def latest_eval():
    with session_scope() as session:
        run = session.query(EvalRun).order_by(EvalRun.id.desc()).first()
    if not run:
        return {"message": "No eval run found yet. Run `docker compose exec api python -m app.evaluator` once to create the first run."}
    return {"eval_run_id": run.id, "run_type": run.run_type, "created_at": run.created_at, "summary": run.summary}


@app.post("/prompt-rewrites/{rewrite_id}/decision")
def decide_rewrite(rewrite_id: int, request: PromptDecisionRequest):
    with session_scope() as session:
        rewrite = session.get(PromptRewrite, rewrite_id)
        if not rewrite:
            raise HTTPException(status_code=404, detail={"code": "REWRITE_NOT_FOUND", "message": "Prompt rewrite not found.", "job_id": None})
        rewrite.status = "approved" if request.decision == "approve" else "rejected"
        rewrite.decided_at = datetime.utcnow()
        response = {"rewrite_id": rewrite.id, "status": rewrite.status}
    return response


@app.post("/evals/retry-failures")
def retry_failures():
    task = run_targeted_failed_eval_job.delay()
    return {"status": "queued", "task_id": task.id}

from datetime import datetime
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, JSON, String, Text
from app.db import Base


class InspectionRecord(Base):
    __tablename__ = "inspection_records"

    inspection_id = Column(String, primary_key=True)
    inspector_name = Column(String, nullable=False)
    pass_fail = Column(String, nullable=False)
    free_text = Column(Text, nullable=False)
    gate_captured = Column(String, nullable=False)
    gate_missed = Column(String, nullable=True)
    part_cost = Column(Float, nullable=False)
    labor_time = Column(Float, nullable=False)
    labor_cost = Column(Float, nullable=False)
    plant = Column(String, nullable=False)
    part_sn = Column(String, nullable=False)
    vin = Column(String, nullable=False)
    customer = Column(String, nullable=False)
    dangerous_issue_flag = Column(String, nullable=False)
    inspection_date = Column(Date, nullable=False)
    rework_date = Column(Date, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True)
    query = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="queued")
    final_answer = Column(Text, nullable=True)
    provenance = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    agent_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    input_hash = Column(String, nullable=True)
    output_hash = Column(String, nullable=True)
    latency_ms = Column(Float, nullable=True)
    token_count = Column(Integer, nullable=True)
    policy_violation = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    tool_name = Column(String, nullable=False)
    attempt = Column(Integer, nullable=False)
    input_payload = Column(JSON, nullable=False)
    output_payload = Column(JSON, nullable=True)
    status = Column(String, nullable=False)
    accepted = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_type = Column(String, nullable=False)
    summary = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class EvalCaseResult(Base):
    __tablename__ = "eval_case_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    eval_run_id = Column(Integer, nullable=False, index=True)
    case_id = Column(String, nullable=False)
    category = Column(String, nullable=False)
    question = Column(Text, nullable=False)
    final_answer = Column(Text, nullable=False)
    prompts = Column(JSON, nullable=False)
    tool_calls = Column(JSON, nullable=False)
    outputs = Column(JSON, nullable=False)
    scores = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PromptRewrite(Base):
    __tablename__ = "prompt_rewrites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_agent = Column(String, nullable=False)
    target_dimension = Column(String, nullable=False)
    old_prompt = Column(Text, nullable=False)
    proposed_prompt = Column(Text, nullable=False)
    structured_diff = Column(JSON, nullable=False)
    justification = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)

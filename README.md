# Delivery Readiness Intelligence Assistant

A containerized multi-agent assistant for a bike manufacturer's final delivery-readiness team.

The system answers questions over:
- **structured inspection records** such as plant, missed gate, rework cost, and dangerous-issue flag
- **short free-text inspector notes** such as `oil seep at engine cover` or `rain test shows water near meter`

It is intentionally built around mixed structured + unstructured data so that the orchestrator must decide at runtime whether a query needs:
- SQL
- retrieval over free-text notes
- Python calculation
- decomposition
- self-reflection
- or a combination of them

## Quick start

Prerequisite: Docker Desktop.

```bash
docker compose up --build
```

On the first run, Docker starts every service and the Ollama sidecar downloads the local `qwen3:4b` model. No API key is required.

Services:
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Adminer log/database UI: `http://localhost:8080`
- PostgreSQL, Redis, and Ollama are started by Docker Compose automatically

Optional first eval run:

```bash
docker compose exec api python -m app.evaluator
```

## Product scenario

A final delivery-readiness inspector walks around assembled bikes before customer handoff and records short free-text findings.  
The assistant helps operations leaders answer questions about:
- failure volume
- gate escapes
- rework cost
- dangerous issues
- recurring semantic issue patterns in the notes

## Dataset

`data/delivery_readiness_inspections.csv`

- 250 rows
- 210 failed checks, 40 passed checks
- 4 plants
- 15 customers
- short inspector notes
- repeated VINs represent the same bike/customer
- hidden eval labels are stored separately in `data/eval_ground_truth.csv` and are **never used by the live assistant**

Live columns:
1. Inspection ID
2. Inspector Name
3. Pass/Fail
4. Free Text
5. Gate Captured
6. Gate Missed
7. Part Cost
8. Labor Time
9. Labor Cost
10. Plant
11. Part SN
12. VIN
13. Customer
14. Dangerous Issue Flag
15. Inspection Date
16. Rework Date

## Architecture

See [`architecture/system_diagram.md`](architecture/system_diagram.md).

### Core design
- **Master orchestrator:** LLM-backed route planner; Python validates the route, enforces dependency order, assigns context budgets, and handles retries.
- **Decomposition agent:** turns ambiguous queries into typed subtasks with dependency graphs.
- **Retrieval agent:** retrieves from inspection-note chunks and limited policy chunks; when invoked, it returns at least two chunks with support annotations.
- **Critique agent:** reviews every agent output that ran, checks claims against evidence already in shared context, and flags exact disputed spans.
- **Synthesis agent:** resolves critique flags and returns a final answer with sentence-level provenance.
- **Compression agent behavior:** if a budget is exceeded, conversational filler is compressed while structured data stays intact.
- **Meta-agent behavior:** after evals, proposes prompt rewrites but never auto-applies them.

### Two concrete flows

#### 1. Simple structured query
`How many failed inspections did Chennai Plant have?`

`Orchestrator → SQL → draft synthesis → critique checks against SQL result → final synthesis`

This is deliberately lightweight; the system does not invoke retrieval or decomposition when they are not needed.

#### 2. Ambiguous analytical query
`Which plant looks worst this month?`

`Orchestrator → decomposition → SQL + retrieval + Python → critique resolves mixed evidence → final synthesis`

The answer considers failure count, dangerous-issue count, rework cost, and recurring note themes instead of pretending one metric defines `worst`.

### Why free-text retrieval exists

The live table deliberately does **not** expose an issue-category column.  
For example:
- `leakage` is a broad semantic family that can include oil seep, oil drip, moisture, and water-related notes
- `water leakage` is narrower and should exclude oil-only cases

Retrieval interprets the semantic filter from short notes; SQL performs the final count over the matched records.

## Required tools

1. **SQL lookup tool** — safe `SELECT`-only querying over PostgreSQL  
2. **Python sandbox** — calculations such as ranking or percentages  
3. **Web-search stub** — structured results with URLs and relevance scores  
4. **Self-reflection tool** — checks prior session outputs for contradictions  

Each tool returns a clear contract:
- `ok`
- `timeout`
- `empty_result`
- `malformed_input`

The orchestrator handles each failure mode in code and may retry with modified input up to two times. Every call logs input, output, latency, acceptance, and retry count.

## API

Exactly five documented endpoints:

1. `POST /query/stream`
2. `GET /traces/{job_id}`
3. `GET /evals/latest`
4. `POST /prompt-rewrites/{rewrite_id}/decision`
5. `POST /evals/retry-failures`

### Example query

```bash
curl -N -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query":"How many failed inspections did Chennai Plant have?"}'
```

### Example trace lookup

```bash
curl http://localhost:8000/traces/<job_id>
```

## Evaluation harness

`data/eval_cases.json` contains 15 full-pipeline questions:
- 5 straightforward
- 5 ambiguous / underspecified
- 5 adversarial

Scoring dimensions:
- answer correctness
- citation accuracy
- contradiction resolution quality
- tool selection efficiency
- context budget compliance
- critique-agent agreement rate with final output

Each dimension stores:
- numeric score
- written justification

The harness persists:
- prompts
- tool calls
- outputs
- scores
- timestamps

A simple direct-answer baseline is included so the multi-agent complexity has a comparison point.

### Leakage note

Hidden labels used for eval ground truth are stored separately from the live inspection table and are not exposed to the assistant.  
Targeted re-eval after prompt approval measures improvement only on prior failed cases; it is not claimed as generalization to unseen cases.

## Self-improving prompt loop

After an eval run:
1. the meta loop identifies the worst-performing scoring dimension
2. proposes a prompt rewrite with a structured diff and justification
3. stores the proposal as `pending`
4. a human approves/rejects via API
5. targeted re-eval can be triggered only for previously failed cases

The system never auto-applies its own prompt changes.

## Structured logging and observability

Every agent/tool event records:
- timestamp
- agent ID
- event type
- input hash
- output hash
- latency
- token count
- policy violation, if any

`GET /traces/{job_id}` reconstructs the ordered execution trace.

## Pragmatic choices

- The repo uses **plain Python** for orchestration rather than hiding routing logic inside a large agent framework.
- Retrieval uses a small local TF-IDF vector index over short inspection notes. For this compact shorthand corpus, that keeps startup fast and behavior inspectable.
- Ollama runs locally in Docker so no paid API key is needed.
- The implementation is intentionally compact: files are split by real responsibility, not for show.

## Known limitations

- The local model is smaller and less capable than a hosted frontier model.
- TF-IDF retrieval is practical for the synthetic shorthand corpus but weaker than modern dense retrieval on richer real-world text.
- The SQL generator/route planner is controlled for the demo domain; a broad production deployment would need stronger SQL validation, permissions, and richer semantic retrieval.
- The synthetic dataset demonstrates behavior but is not a claim of industrial representativeness.

## Next steps

- replace TF-IDF with dense local embeddings
- add richer guardrails around generated SQL
- add held-out eval suites for generalization claims
- add role-based access control and auth
- add production metrics and dashboarding

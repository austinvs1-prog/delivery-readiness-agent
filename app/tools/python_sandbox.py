import subprocess
import sys
import time
from app.schemas import ToolResult


def run(code: str, attempt: int = 1, timeout_seconds: int = 3) -> ToolResult:
    start = time.perf_counter()
    if not isinstance(code, str) or not code.strip():
        return ToolResult(
            tool_name="python_sandbox",
            status="malformed_input",
            input_payload={"code": code},
            output_payload={"error": "code must be a non-empty string"},
            latency_ms=(time.perf_counter() - start) * 1000,
            attempt=attempt,
        )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        status = "ok"
        output = {
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        status = "timeout"
        output = {"stdout": "", "stderr": "execution timed out", "exit_code": None}
    return ToolResult(
        tool_name="python_sandbox",
        status=status,
        input_payload={"code": code},
        output_payload=output,
        latency_ms=(time.perf_counter() - start) * 1000,
        attempt=attempt,
    )

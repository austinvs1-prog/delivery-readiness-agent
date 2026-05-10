import json
from typing import Any
import httpx
from app.config import get_settings

settings = get_settings()


class LocalLLM:
    """Thin Ollama client with deterministic fallback for malformed/unavailable local responses."""

    def __init__(self) -> None:
        self.mode = settings.llm_mode.lower()
        self.base_url = settings.ollama_url.rstrip("/")
        self.model = settings.ollama_model

    def generate_json(self, prompt: str, schema_hint: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.mode == "mock":
            return {}
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": schema_hint or "json",
            "stream": False,
        }
        try:
            with httpx.Client(timeout=45.0) as client:
                response = client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                raw = response.json().get("response", "{}")
                return json.loads(raw)
        except Exception:
            return {}

    def generate_text(self, prompt: str) -> str:
        if self.mode == "mock":
            return ""
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        try:
            with httpx.Client(timeout=45.0) as client:
                response = client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                return response.json().get("response", "")
        except Exception:
            return ""

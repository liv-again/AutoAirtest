from __future__ import annotations

from typing import Any


class LLMClient:
    def json_call(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "reason": "LLM integration is out of scope for the offline core pass",
            "prompt": prompt,
            "schema": schema,
        }

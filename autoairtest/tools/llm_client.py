"""结构化 LLM 客户端边界。

该模块不绑定具体供应商；生产集成可通过 provider 注入，离线测试则使用假 provider。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

Provider = Callable[[dict[str, Any]], str | dict[str, Any]]


class LLMClient:
    """封装 JSON 输出、schema 校验、重试和 prompt 脱敏。"""

    def __init__(
        self,
        provider: Provider | None = None,
        config: dict[str, Any] | None = None,
        evidence_config: dict[str, Any] | None = None,
    ) -> None:
        self.provider = provider
        self.config = {
            "model": "configured-by-env",
            "temperature": 0.1,
            "max_retries": 2,
        } | (config or {})
        self.evidence_config = {
            "redact_sensitive_text": True,
            "sensitive_keywords": ["资金账号", "手机号", "资产", "持仓"],
            "redaction_placeholder": "[REDACTED]",
        } | (evidence_config or {})

    def json_call(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """请求模型按给定 schema 返回 JSON 结构。

        返回值始终是结构化状态，避免上层吞掉 provider、JSON 或 schema 错误。
        """

        if self.provider is None:
            return {
                "status": "unavailable",
                "reason": "LLM provider is not configured",
                "attempts": 0,
                "errors": [],
            }

        max_retries = max(0, int(self.config.get("max_retries", 0) or 0))
        max_attempts = max_retries + 1
        errors: list[dict[str, Any]] = []
        redacted_prompt = _redact_sensitive_text(prompt, self.evidence_config)

        for attempt in range(1, max_attempts + 1):
            payload = {
                "model": self.config.get("model", "configured-by-env"),
                "temperature": self.config.get("temperature", 0.1),
                "prompt": redacted_prompt,
                "schema": schema,
                "attempt": attempt,
            }
            try:
                raw_response = self.provider(payload)
            except Exception as exc:  # pragma: no cover - provider behavior is integration-specific
                errors.append({"type": "provider_error", "message": str(exc), "attempt": attempt})
                continue

            parsed, parse_error = _parse_json_response(raw_response)
            if parse_error:
                errors.append(parse_error | {"attempt": attempt})
                continue

            schema_errors = _validate_object_schema(parsed, schema)
            if schema_errors:
                errors.append({"type": "schema_validation", "missing": schema_errors, "attempt": attempt})
                continue

            return {"status": "success", "attempts": attempt, "data": parsed, "errors": errors}

        return {
            "status": "uncertain",
            "reason": "LLM response did not match required JSON schema",
            "attempts": max_attempts,
            "errors": errors,
        }


def _parse_json_response(raw_response: str | dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if isinstance(raw_response, dict):
        return raw_response, None
    if not isinstance(raw_response, str):
        return {}, {"type": "invalid_json", "message": "provider returned non-string and non-dict response"}
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        return {}, {"type": "invalid_json", "message": str(exc)}
    if not isinstance(parsed, dict):
        return {}, {"type": "invalid_json", "message": "JSON response must be an object"}
    return parsed, None


def _validate_object_schema(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    if schema.get("type") not in {None, "object"}:
        return ["$schema.type.object"]
    required = schema.get("required", [])
    if not isinstance(required, list):
        return ["$schema.required"]
    return [str(item) for item in required if str(item) not in data]


def _redact_sensitive_text(value: str, evidence_config: dict[str, Any]) -> str:
    if not evidence_config.get("redact_sensitive_text", True):
        return value
    redacted = value
    placeholder = str(evidence_config.get("redaction_placeholder", "[REDACTED]"))
    for keyword in evidence_config.get("sensitive_keywords", []):
        keyword_text = str(keyword)
        if keyword_text:
            pattern = re.escape(keyword_text) + r"\s*[^\s，,。；;]*"
            redacted = re.sub(pattern, placeholder, redacted)
    return redacted

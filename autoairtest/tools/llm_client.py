"""结构化 LLM 客户端边界。

该模块不绑定具体供应商；生产集成可通过 provider 注入，离线测试则使用假 provider。
支持多模态图片输入（DeepSeek V4-Pro/V4-Flash），不传图片时行为与纯文本版本完全一致。
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

Provider = Callable[[dict[str, Any]], str | dict[str, Any]]

_USAGE_FIELDS = (
    "prompt_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
    "completion_tokens",
    "total_tokens",
)


class LLMProviderError(RuntimeError):
    """携带可重试属性的 Provider 通信错误。"""

    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class LLMClient:
    """封装 JSON 输出、schema 校验、重试和 prompt 脱敏。"""

    def __init__(
        self,
        provider: Provider | None = None,
        config: dict[str, Any] | None = None,
        evidence_config: dict[str, Any] | None = None,
        telemetry_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.provider = provider
        self.config = {
            "enabled": False,
            "provider": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "chat_completions_path": "/chat/completions",
            "api_key_env": "OPENAI_API_KEY",
            "api_key": "",
            "model": "configured-by-env",
            "temperature": 0.1,
            "max_retries": 2,
            "retry_backoff_seconds": 0.25,
            "timeout_seconds": 60,
            "system_prompt": "你是移动 App 测试结果初判助手。只输出符合 schema 的 JSON。",
        } | (config or {})
        self.evidence_config = {
            "redact_sensitive_text": True,
            "sensitive_keywords": ["资金账号", "手机号", "资产", "持仓"],
            "redaction_placeholder": "[REDACTED]",
        } | (evidence_config or {})
        self.telemetry_sink = telemetry_sink
        self.provider_error = ""
        if self.provider is None and self.config.get("enabled", False):
            self.provider = self._provider_from_config()

    def json_call(
        self,
        prompt: str,
        schema: dict[str, Any],
        images: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """请求模型按给定 schema 返回 JSON 结构。

        可选 images 参数传入图片 URL 或本地路径（自动 base64 编码），
        触发多模态消息格式。不传时保持纯文本行为，兼容所有模型。
        """

        if self.provider is None:
            return {
                "status": "unavailable",
                "reason": self.provider_error or "LLM provider is not configured",
                "attempts": 0,
                "errors": [],
            }

        max_retries = max(0, int(self.config.get("max_retries", 0) or 0))
        max_attempts = max_retries + 1
        errors: list[dict[str, Any]] = []
        attempt_usage: list[dict[str, Any]] = []
        attempts_made = 0
        redacted_prompt = _redact_sensitive_text(prompt, self.evidence_config)
        call_context = context or {}

        for attempt in range(1, max_attempts + 1):
            attempts_made = attempt
            resolved_images: list[str] = []
            if images:
                resolved_images = [_resolve_image_url(img) for img in images]
            payload = {
                "model": self.config.get("model", "configured-by-env"),
                "temperature": self.config.get("temperature", 0.1),
                "prompt": redacted_prompt,
                "schema": schema,
                "attempt": attempt,
                "images": resolved_images,
            }
            try:
                raw_response = self.provider(payload)
            except Exception as exc:  # pragma: no cover - provider behavior is integration-specific
                usage = {"usage_available": False}
                attempt_usage.append(usage)
                error = {"type": "provider_error", "message": str(exc), "attempt": attempt}
                if isinstance(exc, LLMProviderError) and exc.status_code is not None:
                    error["status_code"] = exc.status_code
                errors.append(error)
                telemetry_error = self._emit_telemetry(
                    context=call_context,
                    attempt=attempt,
                    status="provider_error",
                    usage=usage,
                    provider_meta={"model": str(self.config.get("model", "")), "request_id": ""},
                    error_type="provider_error",
                    error_message=str(exc),
                )
                if telemetry_error is not None:
                    errors.append(telemetry_error)
                retryable = not isinstance(exc, LLMProviderError) or exc.retryable
                if not retryable:
                    break
                self._sleep_before_retry(attempt, max_attempts)
                continue

            response_content, usage, provider_meta = _provider_response_parts(raw_response)
            attempt_usage.append(usage)
            parsed, parse_error = _parse_json_response(response_content)
            if parse_error:
                errors.append(parse_error | {"attempt": attempt})
                telemetry_error = self._emit_telemetry(
                    context=call_context,
                    attempt=attempt,
                    status="invalid_json",
                    usage=usage,
                    provider_meta=provider_meta,
                    error_type=str(parse_error.get("type", "invalid_json")),
                    error_message=str(parse_error.get("message", "")),
                )
                if telemetry_error is not None:
                    errors.append(telemetry_error)
                self._sleep_before_retry(attempt, max_attempts)
                continue

            schema_errors = _validate_object_schema(parsed, schema)
            if schema_errors:
                errors.append({"type": "schema_validation", "missing": schema_errors, "attempt": attempt})
                telemetry_error = self._emit_telemetry(
                    context=call_context,
                    attempt=attempt,
                    status="schema_validation",
                    usage=usage,
                    provider_meta=provider_meta,
                    error_type="schema_validation",
                    error_message=f"Missing required fields: {schema_errors}",
                )
                if telemetry_error is not None:
                    errors.append(telemetry_error)
                self._sleep_before_retry(attempt, max_attempts)
                continue

            telemetry_error = self._emit_telemetry(
                context=call_context,
                attempt=attempt,
                status="success",
                usage=usage,
                provider_meta=provider_meta,
            )
            if telemetry_error is not None:
                errors.append(telemetry_error)
            return {
                "status": "success",
                "attempts": attempt,
                "data": parsed,
                "errors": errors,
                "provider": provider_meta,
                "usage": _aggregate_usage(attempt_usage),
                "attempt_usage": attempt_usage,
            }

        return {
            "status": "uncertain",
            "reason": "LLM response did not match required JSON schema",
            "attempts": attempts_made,
            "errors": errors,
            "usage": _aggregate_usage(attempt_usage),
            "attempt_usage": attempt_usage,
        }

    def _sleep_before_retry(self, attempt: int, max_attempts: int) -> None:
        if attempt >= max_attempts:
            return
        backoff = max(0.0, float(self.config.get("retry_backoff_seconds", 0.25) or 0.0))
        if backoff:
            time.sleep(backoff * attempt)

    def _emit_telemetry(
        self,
        *,
        context: dict[str, Any],
        attempt: int,
        status: str,
        usage: dict[str, Any],
        provider_meta: dict[str, str],
        error_type: str = "",
        error_message: str = "",
    ) -> dict[str, Any] | None:
        if self.telemetry_sink is None:
            return None
        record = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "stage": str(context.get("stage", "")),
            "case_id": str(context.get("case_id", "")),
            "goal_id": str(context.get("goal_id", "")),
            "attempt": attempt,
            "status": status,
            "model": provider_meta.get("model") or str(self.config.get("model", "")),
            "request_id": provider_meta.get("request_id", ""),
            **usage,
            "error_type": error_type,
            "error_message": _redact_sensitive_text(error_message, self.evidence_config)[:500],
        }
        try:
            self.telemetry_sink(record)
        except Exception as exc:  # pragma: no cover - sink behavior is integration-specific
            return {"type": "telemetry_error", "message": str(exc), "attempt": attempt}
        return None

    def _provider_from_config(self) -> Provider | None:
        provider_name = str(self.config.get("provider", "openai_compatible")).strip().lower()
        if provider_name not in {"openai_compatible", "openai-compatible", "openai"}:
            self.provider_error = f"Unsupported LLM provider: {provider_name}"
            return None

        api_key = _api_key_from_config(self.config)
        if not api_key:
            api_key_env = str(self.config.get("api_key_env", "")).strip()
            self.provider_error = f"LLM api key is not configured; set llm.api_key or environment variable {api_key_env}."
            return None

        return _openai_compatible_provider(self.config, api_key)


def _parse_json_response(raw_response: str | dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if isinstance(raw_response, dict):
        return raw_response, None
    if not isinstance(raw_response, str):
        return {}, {"type": "invalid_json", "message": "provider returned non-string and non-dict response"}
    try:
        parsed = json.loads(_strip_json_fence(raw_response))
    except json.JSONDecodeError as exc:
        return {}, {"type": "invalid_json", "message": str(exc)}
    if not isinstance(parsed, dict):
        return {}, {"type": "invalid_json", "message": "JSON response must be an object"}
    return parsed, None


def _provider_response_parts(
    raw_response: str | dict[str, Any],
) -> tuple[str | dict[str, Any], dict[str, Any], dict[str, str]]:
    if isinstance(raw_response, dict) and "content" in raw_response:
        return (
            raw_response.get("content", ""),
            _normalize_usage(raw_response.get("usage")),
            {
                "model": str(raw_response.get("model", "")),
                "request_id": str(raw_response.get("request_id", "")),
            },
        )
    return raw_response, _normalize_usage(None), {"model": "", "request_id": ""}


def _normalize_usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"usage_available": False}
    normalized: dict[str, Any] = {"usage_available": True}
    for field in _USAGE_FIELDS:
        raw = value.get(field)
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            normalized[field] = parsed
    hit = normalized.get("prompt_cache_hit_tokens")
    miss = normalized.get("prompt_cache_miss_tokens")
    if isinstance(hit, int) and isinstance(miss, int) and hit + miss > 0:
        normalized["cache_hit_ratio"] = hit / (hit + miss)
    return normalized


def _aggregate_usage(attempt_usage: list[dict[str, Any]]) -> dict[str, Any]:
    available = [item for item in attempt_usage if item.get("usage_available", False)]
    if not available:
        return {"usage_available": False}
    aggregated: dict[str, Any] = {"usage_available": True}
    for field in _USAGE_FIELDS:
        values = [item[field] for item in available if isinstance(item.get(field), int)]
        if values:
            aggregated[field] = sum(values)
    hit = aggregated.get("prompt_cache_hit_tokens")
    miss = aggregated.get("prompt_cache_miss_tokens")
    if isinstance(hit, int) and isinstance(miss, int) and hit + miss > 0:
        aggregated["cache_hit_ratio"] = hit / (hit + miss)
    return aggregated


def _validate_object_schema(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    if schema.get("type") not in {None, "object"}:
        return ["$schema.type.object"]
    required = schema.get("required", [])
    if not isinstance(required, list):
        return ["$schema.required"]
    return [str(item) for item in required if str(item) not in data]


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


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


def _api_key_from_config(config: dict[str, Any]) -> str:
    direct_key = str(config.get("api_key", "")).strip()
    if direct_key:
        return direct_key
    env_name = str(config.get("api_key_env", "")).strip()
    if not env_name:
        return ""
    return str(os.environ.get(env_name, "")).strip()


def _openai_compatible_provider(config: dict[str, Any], api_key: str) -> Provider:
    endpoint = _chat_completions_url(config)
    timeout = float(config.get("timeout_seconds", 60) or 60)

    def provider(payload: dict[str, Any]) -> str:
        user_content: str | list[dict[str, Any]] = str(payload.get("prompt", ""))
        images: list[str] = payload.get("images", [])
        if images:
            user_content = _build_multimodal_content(user_content, images)
        request_body = {
            "model": payload.get("model") or config.get("model", "configured-by-env"),
            "temperature": payload.get("temperature", config.get("temperature", 0.1)),
            "messages": [
                {"role": "system", "content": str(config.get("system_prompt", ""))},
                {"role": "user", "content": user_content},
            ],
        }
        if config.get("response_format_json", True):
            request_body["response_format"] = {"type": "json_object"}
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code == 429 or exc.code in {500, 502, 503, 504}
            raise LLMProviderError(
                f"LLM HTTP {exc.code}: {detail}",
                retryable=retryable,
                status_code=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMProviderError(
                f"LLM request failed: {exc.reason}",
                retryable=True,
            ) from exc

        response_json = json.loads(response_text)
        return {
            "content": _extract_openai_compatible_content(response_json),
            "usage": response_json.get("usage"),
            "model": str(response_json.get("model", "")),
            "request_id": str(response_json.get("id", "")),
        }

    return provider


def _chat_completions_url(config: dict[str, Any]) -> str:
    base_url = str(config.get("base_url", "")).strip().rstrip("/") + "/"
    path = str(config.get("chat_completions_path", "/chat/completions")).strip().lstrip("/")
    return urljoin(base_url, path)


def _extract_openai_compatible_content(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM response does not contain choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError("LLM choice is not an object")
    message = first_choice.get("message", {})
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    if isinstance(first_choice.get("text"), str):
        return str(first_choice["text"])
    raise RuntimeError("LLM response does not contain message content")


def _resolve_image_url(image: str) -> str:
    """如果是本地路径，转为 base64 data URI；否则原样返回（视为 URL）。"""
    path = Path(image)
    if path.exists() and path.is_file():
        suffix = path.suffix.lower().lstrip(".")
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            "bmp": "image/bmp",
        }.get(suffix, "image/png")
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    return image


def _build_multimodal_content(text: str, images: list[str]) -> list[dict[str, Any]]:
    """构建多模态 content 数组：文本在前，图片在后。"""
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for img in images:
        parts.append({"type": "image_url", "image_url": {"url": img}})
    return parts

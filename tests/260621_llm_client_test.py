import json

from autoairtest.tools.llm_client import LLMClient


def test_llm_client_retries_until_json_matches_required_schema():
    calls = []
    responses = iter(
        [
            "not json",
            json.dumps({"status": "pass"}),
            json.dumps({"status": "pass", "reason": "ok"}),
        ]
    )

    def provider(payload):
        calls.append(payload)
        return next(responses)

    client = LLMClient(
        provider=provider,
        config={"model": "fake-model", "temperature": 0.1, "max_retries": 2},
    )

    result = client.json_call(
        "判断页面是否通过",
        {"type": "object", "required": ["status", "reason"]},
    )

    assert result["status"] == "success"
    assert result["data"] == {"status": "pass", "reason": "ok"}
    assert result["attempts"] == 3
    assert [call["model"] for call in calls] == ["fake-model", "fake-model", "fake-model"]


def test_llm_client_returns_uncertain_after_invalid_json_budget_exhausted():
    def provider(payload):
        return "not json"

    client = LLMClient(provider=provider, config={"max_retries": 1})

    result = client.json_call("输出 JSON", {"type": "object", "required": ["status"]})

    assert result["status"] == "uncertain"
    assert result["attempts"] == 2
    assert result["errors"][0]["type"] == "invalid_json"


def test_llm_client_redacts_sensitive_prompt_text_before_provider_call():
    calls = []

    def provider(payload):
        calls.append(payload)
        return {"status": "manual_required", "reason": "sensitive evidence"}

    client = LLMClient(
        provider=provider,
        evidence_config={
            "redact_sensitive_text": True,
            "sensitive_keywords": ["手机号", "资金账号"],
            "redaction_placeholder": "[REDACTED]",
        },
    )

    result = client.json_call(
        "页面展示手机号 13800138000 和资金账号 123456",
        {"type": "object", "required": ["status", "reason"]},
    )

    assert result["status"] == "success"
    assert calls[0]["prompt"] == "页面展示[REDACTED] 和[REDACTED]"

import json

from autoairtest.tools import llm_client
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


def test_llm_client_builds_openai_compatible_request_when_enabled(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "id": "req-cache-1",
                    "model": "test-model-resolved",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "observation_summary": "页面证据已采集。",
                                        "manual_review_reason": "data_correctness",
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 100,
                        "prompt_cache_hit_tokens": 80,
                        "prompt_cache_miss_tokens": 20,
                        "completion_tokens": 10,
                        "total_tokens": 110,
                    },
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    client = LLMClient(
        config={
            "enabled": True,
            "base_url": "https://example.test/v1",
            "api_key": "test-key",
            "model": "test-model",
            "timeout_seconds": 12,
        }
    )
    result = client.json_call(
        "只输出 JSON",
        {"type": "object", "required": ["observation_summary", "manual_review_reason"]},
    )

    assert result["status"] == "success"
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["timeout"] == 12
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert result["data"]["manual_review_reason"] == "data_correctness"
    assert result["provider"] == {
        "model": "test-model-resolved",
        "request_id": "req-cache-1",
    }
    assert result["usage"] == {
        "usage_available": True,
        "prompt_tokens": 100,
        "prompt_cache_hit_tokens": 80,
        "prompt_cache_miss_tokens": 20,
        "completion_tokens": 10,
        "total_tokens": 110,
        "cache_hit_ratio": 0.8,
    }
    assert result["attempt_usage"][0]["prompt_cache_hit_tokens"] == 80


def test_llm_client_accepts_legacy_provider_without_usage():
    client = LLMClient(provider=lambda payload: {"status": "pass"})

    result = client.json_call("prompt", {"type": "object", "required": ["status"]})

    assert result["status"] == "success"
    assert result["usage"] == {"usage_available": False}
    assert result["attempt_usage"] == [{"usage_available": False}]


def test_llm_client_ignores_invalid_usage_fields_without_losing_business_result():
    client = LLMClient(
        provider=lambda payload: {
            "content": '{"status":"pass"}',
            "usage": {
                "prompt_tokens": "bad",
                "prompt_cache_hit_tokens": 4,
                "prompt_cache_miss_tokens": 1,
            },
        }
    )

    result = client.json_call("prompt", {"type": "object", "required": ["status"]})

    assert result["data"] == {"status": "pass"}
    assert "prompt_tokens" not in result["usage"]
    assert result["usage"]["cache_hit_ratio"] == 0.8


def test_llm_client_reports_unavailable_when_enabled_without_api_key(monkeypatch):
    monkeypatch.delenv("AUTOAIRTEST_TEST_LLM_KEY", raising=False)

    client = LLMClient(
        config={
            "enabled": True,
            "api_key": "",
            "api_key_env": "AUTOAIRTEST_TEST_LLM_KEY",
        }
    )
    result = client.json_call("prompt", {"type": "object", "required": ["status"]})

    assert result["status"] == "unavailable"
    assert "AUTOAIRTEST_TEST_LLM_KEY" in result["reason"]

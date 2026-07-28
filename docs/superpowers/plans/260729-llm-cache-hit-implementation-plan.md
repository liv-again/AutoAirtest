# LLM Cache Hit Rate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the stable prompt prefix for every production LLM call and preserve per-attempt cache usage in both call results and `llm_usage.jsonl`.

**Architecture:** Keep the existing `urllib.request` transport and extend its provider response from content-only text to a structured envelope containing content, usage, model, and request ID. `LLMClient` remains the compatibility boundary for injected providers, owns retry and usage normalization, and emits one sanitized telemetry record per attempt; Planner and Verifier own cache-friendly prompt assembly, while Orchestrator owns the run-level JSONL sink.

**Tech Stack:** Python 3, standard-library `urllib.request`, JSON/JSONL, pytest, existing `EvidenceStore`.

---

## File Structure

- Modify `autoairtest/tools/llm_client.py`: structured provider response, usage normalization, retry classification, backoff, and telemetry emission.
- Modify `autoairtest/planning/planning_agent.py`: repository-relative prompt loading, stable/dynamic prompt sections, and planning context.
- Modify `autoairtest/verification/rule_engine.py`: load `prompts/verifier.md`, append dynamic evidence, and pass verification context.
- Modify `autoairtest/orchestrator.py`: initialize one usage JSONL file and share one telemetry sink across planning and verification clients.
- Modify `autoairtest/config.py`: add the default retry backoff configuration.
- Modify `config-模板.yaml`: expose the retry backoff configuration.
- Modify `tests/260621_llm_client_test.py`: provider envelope, usage, retry, telemetry, and safety tests.
- Modify `tests/260622_planning_agent_test.py`: stable-prefix, path, fallback, and context tests.
- Modify `tests/test_verifier_evidence_gap.py`: verifier template and context tests, plus correction of directly encountered stale assertions only where required.
- Modify `tests/test_orchestrator_session_outputs.py`: run-level `llm_usage.jsonl` integration tests.
- Modify `tests/test_config_latest_design.py`: retry backoff default and merge tests.

### Task 1: Preserve structured Provider responses and cache usage

**Files:**
- Modify: `tests/260621_llm_client_test.py`
- Modify: `autoairtest/tools/llm_client.py`

- [ ] **Step 1: Write the failing HTTP response usage test**

Extend `FakeResponse.read()` in `test_llm_client_builds_openai_compatible_request_when_enabled` with:

```python
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
}
```

Add assertions:

```python
assert result["provider"]["request_id"] == "req-cache-1"
assert result["provider"]["model"] == "test-model-resolved"
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
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-task1-red tests/260621_llm_client_test.py::test_llm_client_builds_openai_compatible_request_when_enabled
```

Expected: FAIL because `result` has no `provider`, `usage`, or `attempt_usage`.

- [ ] **Step 3: Add the structured Provider envelope**

In `autoairtest/tools/llm_client.py`, change the HTTP provider return path to:

```python
response_json = json.loads(response_text)
return {
    "content": _extract_openai_compatible_content(response_json),
    "usage": response_json.get("usage"),
    "model": str(response_json.get("model", "")),
    "request_id": str(response_json.get("id", "")),
}
```

Add normalization helpers with these contracts:

```python
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
```

```python
_USAGE_FIELDS = (
    "prompt_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
    "completion_tokens",
    "total_tokens",
)


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
```

In `json_call`, normalize the response before business JSON parsing, append the normalized attempt usage, and return:

```python
return {
    "status": "success",
    "attempts": attempt,
    "data": parsed,
    "errors": errors,
    "provider": provider_meta,
    "usage": _aggregate_usage(attempt_usage),
    "attempt_usage": attempt_usage,
}
```

`_aggregate_usage` must sum each available numeric field across attempts, compute the aggregate cache ratio from summed hit and miss tokens, and return `{"usage_available": False}` when no attempt exposes usage.

- [ ] **Step 4: Add compatibility and malformed usage tests**

Add:

```python
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
```

- [ ] **Step 5: Run Task 1 tests to verify GREEN**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-task1-green tests/260621_llm_client_test.py
```

Expected: all tests in the file PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add autoairtest/tools/llm_client.py tests/260621_llm_client_test.py
git commit -m "feat: preserve LLM cache usage metadata"
```

### Task 2: Emit safe attempt telemetry and classify retries

**Files:**
- Modify: `tests/260621_llm_client_test.py`
- Modify: `autoairtest/tools/llm_client.py`
- Modify: `autoairtest/config.py`
- Modify: `config-模板.yaml`
- Modify: `tests/test_config_latest_design.py`

- [ ] **Step 1: Write failing telemetry and retry tests**

Add:

```python
def test_llm_client_emits_one_sanitized_telemetry_record_per_attempt(monkeypatch):
    records = []
    sleeps = []
    responses = iter(
        [
            {
                "content": "not json",
                "usage": {
                    "prompt_cache_hit_tokens": 10,
                    "prompt_cache_miss_tokens": 5,
                },
                "model": "test-model",
                "request_id": "req-1",
            },
            {
                "content": '{"status":"pass"}',
                "usage": {
                    "prompt_cache_hit_tokens": 15,
                    "prompt_cache_miss_tokens": 0,
                },
                "model": "test-model",
                "request_id": "req-2",
            },
        ]
    )
    monkeypatch.setattr(llm_client.time, "sleep", sleeps.append)
    client = LLMClient(
        provider=lambda payload: next(responses),
        config={"max_retries": 1, "retry_backoff_seconds": 0.25},
        telemetry_sink=records.append,
    )
    result = client.json_call(
        "手机号 13800138000",
        {"type": "object", "required": ["status"]},
        context={"stage": "planning", "case_id": "TC_1"},
    )
    assert result["status"] == "success"
    assert [record["attempt"] for record in records] == [1, 2]
    assert [record["status"] for record in records] == ["invalid_json", "success"]
    assert sleeps == [0.25]
    serialized = json.dumps(records, ensure_ascii=False)
    assert "手机号" not in serialized
    assert "13800138000" not in serialized
    assert "not json" not in serialized
```

Add an HTTP classification test that monkeypatches `urlopen` to raise `urllib.error.HTTPError`:

```python
import io

import pytest


def _http_error(status_code):
    return urllib.error.HTTPError(
        url="https://example.test/chat/completions",
        code=status_code,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(b"client error"),
    )


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
def test_llm_client_does_not_retry_non_retryable_http_errors(monkeypatch, status_code):
    calls = []

    def fake_urlopen(request, timeout=0):
        calls.append(request)
        raise _http_error(status_code)

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)
    client = LLMClient(
        config={
            "enabled": True,
            "base_url": "https://example.test",
            "api_key": "test-key",
            "max_retries": 2,
            "retry_backoff_seconds": 0,
        }
    )
    result = client.json_call("prompt", {"type": "object", "required": ["status"]})
    assert result["status"] == "uncertain"
    assert result["attempts"] == 1
    assert len(calls) == 1


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_llm_client_retries_retryable_http_errors(monkeypatch, status_code):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": '{"status":"pass"}'}}],
                    "usage": {
                        "prompt_cache_hit_tokens": 10,
                        "prompt_cache_miss_tokens": 0,
                    },
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        calls.append(request)
        if len(calls) == 1:
            raise _http_error(status_code)
        return FakeResponse()

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)
    client = LLMClient(
        config={
            "enabled": True,
            "base_url": "https://example.test",
            "api_key": "test-key",
            "max_retries": 1,
            "retry_backoff_seconds": 0,
        }
    )
    result = client.json_call("prompt", {"type": "object", "required": ["status"]})
    assert result["status"] == "success"
    assert result["attempts"] == 2
    assert len(calls) == 2
```

- [ ] **Step 2: Run retry tests to verify RED**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-task2-red tests/260621_llm_client_test.py -k "telemetry or retryable_http or non_retryable_http"
```

Expected: FAIL because `telemetry_sink`, `context`, retry classification, and backoff do not exist.

- [ ] **Step 3: Implement Provider error classification**

Add:

```python
class LLMProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
```

Convert HTTP and URL errors inside the provider:

```python
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
```

In `json_call`, stop after a non-retryable `LLMProviderError`; retain current retry behavior for unknown injected Provider exceptions to preserve compatibility.

- [ ] **Step 4: Implement attempt telemetry and backoff**

Extend the constructor:

```python
telemetry_sink: Callable[[dict[str, Any]], None] | None = None
```

Store it as `self.telemetry_sink`. Extend `json_call` with:

```python
context: dict[str, Any] | None = None
```

Add `_telemetry_record` that returns only:

```python
{
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
```

Do not pass Prompt, messages, content, images, API key, headers, raw response, or Provider payload into this helper.

Catch sink errors and append:

```python
{"type": "telemetry_error", "message": str(exc), "attempt": attempt}
```

without turning a valid model response into failure.

Before a retry:

```python
backoff = max(0.0, float(self.config.get("retry_backoff_seconds", 0.25) or 0.0))
if backoff:
    time.sleep(backoff * attempt)
```

- [ ] **Step 5: Add and test configuration defaults**

Add to `default_config()["llm"]` and `config-模板.yaml`:

```yaml
retry_backoff_seconds: 0.25
```

Add to `tests/test_config_latest_design.py`:

```python
assert config["llm"]["retry_backoff_seconds"] == 0.25
```

and verify nested overrides preserve it when another LLM key changes.

- [ ] **Step 6: Run Task 2 tests to verify GREEN**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-task2-green tests/260621_llm_client_test.py tests/test_config_latest_design.py
```

Expected: all selected tests PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
git add autoairtest/tools/llm_client.py autoairtest/config.py config-模板.yaml tests/260621_llm_client_test.py tests/test_config_latest_design.py
git commit -m "feat: add safe LLM attempt telemetry and retry policy"
```

### Task 3: Make the Planner prefix stable and path-independent

**Files:**
- Modify: `tests/260622_planning_agent_test.py`
- Modify: `autoairtest/planning/planning_agent.py`

- [ ] **Step 1: Write failing prefix and context tests**

Add a capturing client:

```python
class CapturingLLMClient:
    def __init__(self):
        self.calls = []

    def json_call(self, prompt, schema, **kwargs):
        self.calls.append({"prompt": prompt, "schema": schema, **kwargs})
        return {"status": "unavailable"}
```

Add:

```python
def test_planner_places_all_stable_rules_before_case_specific_context():
    cases = load_test_cases("test-cases.xlsx", "需求测试报告")
    agent = PlanningAgent(
        llm_client=CapturingLLMClient(),
        skill_registry=SkillRegistry("skills"),
    )
    prompts = [
        agent._planner_prompt(case, agent._navigation_path_for(case))
        for case in cases
    ]
    expected_rules = agent._expected_result_rules_section()
    common_prefix = _common_prefix(prompts)
    assert expected_rules in common_prefix
    assert common_prefix.index(expected_rules) > common_prefix.index("# Planner Prompt")
    assert all(prompt.index(expected_rules) < prompt.index(f"case_id: {case.internal_id}") for prompt, case in zip(prompts, cases))
```

Add:

```python
def test_planner_default_prompt_path_does_not_depend_on_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = PlanningAgent(skill_registry=SkillRegistry(PROJECT_ROOT / "skills"))
    prompt = agent._planner_prompt(_case(), [])
    assert prompt.startswith("# Planner Prompt")
```

Add:

```python
def test_planner_passes_non_sensitive_call_context():
    llm = CapturingLLMClient()
    PlanningAgent(llm_client=llm, skill_registry=SkillRegistry("skills")).plan(_case())
    assert llm.calls[0]["context"] == {"stage": "planning", "case_id": "TC_1"}
```

- [ ] **Step 2: Run Planner tests to verify RED**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-task3-red tests/260622_planning_agent_test.py -k "stable_rules or default_prompt_path or passes_non_sensitive"
```

Expected: FAIL because stable rules occur after dynamic navigation, the default path is CWD-relative, and context is not passed.

- [ ] **Step 3: Resolve the default prompt from the repository**

Add:

```python
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PLANNER_PROMPT = _PROJECT_ROOT / "prompts" / "planner.md"
```

Use `_DEFAULT_PLANNER_PROMPT` when `prompt_path` is omitted. Replace silent empty loading with:

```python
def _base_prompt(self) -> str:
    if not self.prompt_path.is_file():
        raise FileNotFoundError(f"Planner prompt not found: {self.prompt_path}")
    return self.prompt_path.read_text(encoding="utf-8").strip()
```

Catch `OSError` around Prompt construction in `_plan_with_llm` and return `None` so the existing rule Planner fallback remains authoritative.

- [ ] **Step 4: Split stable and dynamic navigation sections and reorder**

Implement:

```python
def _navigation_rules_section(self) -> str:
    return (
        "Navigation actions are resolved by the system via skills/navigation/nodes.yaml.\n"
        "Rules:\n"
        "1. Do not generate intent='navigate'.\n"
        "2. Allowed intents: observe, tap, swipe, text, keyevent.\n"
        "3. Before leaving a key page, observe it, then tap, then observe the new page.\n"
        "4. If the case only verifies the current page, observe without leaving it.\n"
        "5. Tap targets must be visible, real UI text."
    )
```

Make `_nav_context_section` dynamic-only and retain the phrase expected by the existing direct LLM test:

```python
if not navigation_path:
    return "Navigation context: no deterministic path matched."
return (
    "Navigation skill matched path.\n"
    f"current_page: {navigation_path[-1].text}\n"
    f"path: {' -> '.join(node.text for node in navigation_path)}"
)
```

Assemble:

```python
return (
    f"{self._base_prompt()}\n\n"
    f"{self._expected_result_rules_section()}\n\n"
    f"{self._navigation_rules_section()}\n\n"
    f"{self._nav_context_section(navigation_path or [])}\n\n"
    f"{self._stock_detail_prompt_section(case)}\n\n"
    "请将以下自然语言测试用例转换为 ExecutionPlan JSON。\n"
    # Dynamic case fields follow.
).strip()
```

Pass:

```python
context={"stage": "planning", "case_id": case.internal_id}
```

to `json_call`.

- [ ] **Step 5: Update affected Fake LLM clients**

Change Fake clients in `tests/260622_planning_agent_test.py` from:

```python
def json_call(self, prompt, schema):
```

to:

```python
def json_call(self, prompt, schema, **kwargs):
```

Apply this signature to every Fake LLM client in that file that is passed to `PlanningAgent`. Preserve every existing plan-output assertion unchanged.

- [ ] **Step 6: Run all Planner tests to verify GREEN**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-task3-green tests/260622_planning_agent_test.py tests/test_planner_rationales.py
```

Expected: all selected tests PASS, including the previously failing navigation Prompt assertion.

- [ ] **Step 7: Commit Task 3**

```powershell
git add autoairtest/planning/planning_agent.py tests/260622_planning_agent_test.py
git commit -m "fix: stabilize LLM planner prompt prefix"
```

### Task 4: Use the stable Verifier template and pass verification context

**Files:**
- Modify: `tests/test_verifier_evidence_gap.py`
- Modify: `autoairtest/verification/rule_engine.py`

- [ ] **Step 1: Write failing Verifier template and context tests**

Add:

```python
def test_verifier_uses_stable_prompt_file_before_dynamic_evidence(tmp_path):
    prompt_path = tmp_path / "verifier.md"
    prompt_path.write_text("STABLE VERIFIER CONTRACT", encoding="utf-8")
    calls = []

    class FakeLLMClient:
        def json_call(self, prompt, schema, **kwargs):
            calls.append({"prompt": prompt, **kwargs})
            return {"status": "unavailable"}

    engine = RuleEngine(prompt_path=prompt_path)
    goal = VerificationGoal(
        goal_id="v1",
        claim="动态目标",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=["科创综指"],
        evidence_priority=["poco_tree"],
        human_review_required=True,
        review_reason="data_correctness",
    )
    engine._llm_observation_details(
        goal,
        {
            "llm_preliminary_judgment": True,
            "llm_client": FakeLLMClient(),
            "case_id": "TC_1",
            "visible_texts": ["动态证据"],
            "evidence_files": ["screen.png"],
        },
        "data_correctness",
    )
    prompt = calls[0]["prompt"]
    assert prompt.startswith("STABLE VERIFIER CONTRACT")
    assert prompt.index("STABLE VERIFIER CONTRACT") < prompt.index("动态目标")
    assert calls[0]["context"] == {
        "stage": "verification",
        "case_id": "TC_1",
        "goal_id": "v1",
    }
```

Add a CWD-independence test that constructs `RuleEngine()` after `monkeypatch.chdir(tmp_path)` and asserts the Prompt starts with `# Verifier Prompt`.

- [ ] **Step 2: Run Verifier tests to verify RED**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-task4-red tests/test_verifier_evidence_gap.py -k "stable_prompt_file or cwd"
```

Expected: FAIL because `RuleEngine` has no prompt path and hardcodes its fixed instruction.

- [ ] **Step 3: Implement repository-relative Verifier Prompt loading**

Add:

```python
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_VERIFIER_PROMPT = _PROJECT_ROOT / "prompts" / "verifier.md"
```

Extend `RuleEngine.__init__`:

```python
prompt_path: str | Path | None = None
```

and set:

```python
self.prompt_path = Path(prompt_path) if prompt_path else _DEFAULT_VERIFIER_PROMPT
```

Add:

```python
def _verifier_prompt(self) -> str:
    if not self.prompt_path.is_file():
        raise FileNotFoundError(f"Verifier prompt not found: {self.prompt_path}")
    return self.prompt_path.read_text(encoding="utf-8").strip()
```

Build the request as:

```python
try:
    stable_prompt = self._verifier_prompt()
except OSError as exc:
    return {"llm_status": "unavailable", "llm_reason": str(exc)}

prompt = (
    f"{stable_prompt}\n\n"
    f"验证目标: {goal.claim}\n"
    f"目标类别: {goal.category.value}\n"
    f"人工复核原因: {manual_review_reason}\n"
    f"证据来源: {evidence_source}\n"
    f"可见文本: {visible_texts}\n"
    f"证据文件: {list(evidence.get('evidence_files', []))}"
)
```

Call:

```python
client.json_call(
    prompt,
    schema,
    context={
        "stage": "verification",
        "case_id": str(evidence.get("case_id", "")),
        "goal_id": goal.goal_id,
    },
)
```

- [ ] **Step 4: Run the new Verifier tests to verify GREEN**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-task4-green tests/test_verifier_evidence_gap.py -k "stable_prompt_file or cwd or llm_observation"
```

Expected: all selected LLM-focused tests PASS. The two acknowledged order-detail baseline failures remain outside scope and are not selected by this command.

- [ ] **Step 5: Commit Task 4**

```powershell
git add autoairtest/verification/rule_engine.py tests/test_verifier_evidence_gap.py
git commit -m "fix: stabilize LLM verifier prompt prefix"
```

### Task 5: Persist run-level `llm_usage.jsonl`

**Files:**
- Modify: `tests/test_orchestrator_session_outputs.py`
- Modify: `autoairtest/orchestrator.py`

- [ ] **Step 1: Write failing run artifact initialization test**

Add:

```python
def test_run_offline_initializes_empty_llm_usage_jsonl_when_llm_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "_load_cases_or_dependency_case", lambda config: [_case()])
    run_dir = orchestrator.run_offline(
        {
            "llm": {"enabled": False},
            "report": {"output_dir": str(tmp_path), "generate_html": False},
            "logs": {"enable_capture": False},
        }
    )
    usage_path = run_dir / "llm_usage.jsonl"
    assert usage_path.exists()
    assert usage_path.read_text(encoding="utf-8") == ""
```

- [ ] **Step 2: Write failing shared sink integration test**

Add a second test using this Fake client:

```python
class FakeLLMClient:
    def __init__(self, provider=None, config=None, evidence_config=None, telemetry_sink=None):
        self.telemetry_sink = telemetry_sink

    def json_call(self, prompt, schema, context=None, **kwargs):
        context = context or {}
        self.telemetry_sink(
            {
                "timestamp": "2026-07-29T12:00:00+08:00",
                "stage": context.get("stage", ""),
                "case_id": context.get("case_id", ""),
                "goal_id": context.get("goal_id", ""),
                "attempt": 1,
                "status": "success",
                "model": "fake-model",
                "request_id": f"req-{context.get('stage', '')}",
                "usage_available": True,
                "prompt_tokens": 10,
                "prompt_cache_hit_tokens": 8,
                "prompt_cache_miss_tokens": 2,
                "completion_tokens": 2,
                "total_tokens": 12,
                "cache_hit_ratio": 0.8,
                "error_type": "",
                "error_message": "",
            }
        )
        if "actions" in schema.get("required", []):
            return {
                "status": "success",
                "data": {
                    "case_id": context["case_id"],
                    "understanding": "测试规划",
                    "preconditions": [],
                    "actions": [],
                    "verification_goals": [
                        {
                            "goal_id": "v1",
                            "claim": "页面数据可见",
                            "category": "data_correctness",
                            "expected_entities": ["国内指数"],
                            "evidence_priority": ["poco_tree", "ocr_text", "screenshot"],
                            "human_review_required": True,
                            "review_reason": "data_correctness",
                        }
                    ],
                    "manual_review_notes": [],
                    "interpretation_rationales": [],
                },
                "attempts": 1,
                "errors": [],
            }
        return {
            "status": "success",
            "data": {
                "observation_summary": "已采集页面证据。",
                "manual_review_reason": "data_correctness",
            },
            "attempts": 1,
            "errors": [],
        }


monkeypatch.setattr(orchestrator, "LLMClient", FakeLLMClient)
monkeypatch.setattr(orchestrator, "_load_cases_or_dependency_case", lambda config: [case])
run_dir = orchestrator.run_offline(
    {
        "llm": {
            "enabled": True,
            "use_for_planning": True,
            "use_for_verification": True,
        },
        "verification": {"llm_preliminary_judgment": True},
        "report": {"output_dir": str(tmp_path), "generate_html": False},
        "logs": {"enable_capture": False},
    }
)
records = [
    json.loads(line)
    for line in (run_dir / "llm_usage.jsonl").read_text(encoding="utf-8").splitlines()
]
assert {record["stage"] for record in records} == {"planning", "verification"}
assert all(record["case_id"] == case.internal_id for record in records)
assert all("prompt" not in record and "content" not in record for record in records)
```

- [ ] **Step 3: Run Orchestrator integration tests to verify RED**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-task5-red tests/test_orchestrator_session_outputs.py -k "llm_usage"
```

Expected: FAIL because `llm_usage.jsonl` and the shared sink do not exist.

- [ ] **Step 4: Initialize the sink before constructing clients**

In `run_offline`, after `EvidenceStore` construction:

```python
store.initialize_jsonl("llm_usage.jsonl")

def llm_telemetry_sink(record: dict[str, Any]) -> None:
    store.append_jsonl("llm_usage.jsonl", record)
```

Construct clients once:

```python
planning_llm_client = _planning_llm_client(config, telemetry_sink=llm_telemetry_sink)
verification_llm_client = _verification_llm_client(config, telemetry_sink=llm_telemetry_sink)
```

Pass `planning_llm_client` into `PlanningAgent`. Reuse `verification_llm_client` for every case rather than constructing a client inside the case loop.

Add:

```python
"case_id": case.internal_id,
```

to `verification_evidence`.

Extend both helper constructors with an optional sink:

```python
def _planning_llm_client(
    config: dict[str, Any],
    telemetry_sink: Callable[[dict[str, Any]], None] | None = None,
) -> LLMClient | None:
```

and pass `telemetry_sink=telemetry_sink` into every `LLMClient` construction. Do the same for `_verification_llm_client`.

- [ ] **Step 5: Update affected constructor fakes**

Update Fake `LLMClient` constructors in orchestrator tests to accept:

```python
def __init__(self, *args, telemetry_sink=None, **kwargs):
    self.telemetry_sink = telemetry_sink
```

Do not change unrelated device workflow assertions or production code for the eight acknowledged baseline failures.

- [ ] **Step 6: Run LLM-focused Orchestrator tests to verify GREEN**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-task5-green tests/test_orchestrator_session_outputs.py -k "llm_usage or passes_llm_client"
```

Expected: all selected LLM-focused tests PASS.

- [ ] **Step 7: Commit Task 5**

```powershell
git add autoairtest/orchestrator.py tests/test_orchestrator_session_outputs.py
git commit -m "feat: persist run-level LLM cache telemetry"
```

### Task 6: Verify cache-prefix regression, safety, and known baseline

**Files:**
- Verify: `autoairtest/`
- Verify: `tests/`

- [ ] **Step 1: Run the complete LLM-focused suite**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-focused-final tests/260621_llm_client_test.py tests/260622_planning_agent_test.py tests/test_verifier_evidence_gap.py tests/260622_rule_engine_test.py tests/test_config_latest_design.py tests/test_orchestrator_session_outputs.py -k "llm or planner or verifier or cache or usage or config"
```

Expected: selected tests PASS. If a failure is caused by the new contract, return to the responsible task and follow RED→GREEN rather than weakening the assertion.

- [ ] **Step 2: Run the deterministic real-case prefix measurement**

Run:

```powershell
@'
from autoairtest.excel_loader import load_test_cases
from autoairtest.planning.planning_agent import PlanningAgent
from autoairtest.planning.skill_registry import SkillRegistry

cases = load_test_cases("test-cases.xlsx", "需求测试报告")
agent = PlanningAgent(skill_registry=SkillRegistry("skills"))
prompts = [agent._planner_prompt(case, agent._navigation_path_for(case)) for case in cases]
prefix = prompts[0]
for prompt in prompts[1:]:
    index = 0
    while index < min(len(prefix), len(prompt)) and prefix[index] == prompt[index]:
        index += 1
    prefix = prefix[:index]
rules = agent._expected_result_rules_section()
assert rules in prefix
print({
    "case_count": len(cases),
    "common_prefix_chars": len(prefix),
    "stable_rules_chars": len(rules),
})
'@ | python -
```

Expected: exit 0; `case_count` is 7; the complete expected-result rules are inside the common prefix.

- [ ] **Step 3: Run a telemetry secret scan test**

The Task 2 telemetry unit test already serializes every generated record. Extend its assertion to:

```python
for forbidden in (
    "Authorization",
    "api_key",
    "prompt",
    "messages",
    "content",
    "images",
    "13800138000",
):
    assert forbidden not in serialized
```

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-safety-final tests/260621_llm_client_test.py -k "sanitized_telemetry"
```

Expected: PASS without reading any real user run directory.

- [ ] **Step 4: Run the full suite and compare with baseline**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\260729-llm-full-final
```

Baseline before implementation: `130 passed, 9 failed, 2 warnings`.

Expected completion condition:

- No newly failing test.
- The directly related Planner failure is fixed.
- The remaining eight unrelated device/orchestrator/rationale/step-budget/order-detail failures may remain and must be reported by exact test name.

- [ ] **Step 5: Check code quality and repository state**

Run:

```powershell
python -m compileall -q autoairtest
git diff --check
git status --short
```

Expected:

- `compileall` exits 0.
- `git diff --check` produces no output.
- Only intended tracked changes exist; no user files from the original PC worktree appear.

- [ ] **Step 6: Produce the completion report**

Report:

- Stable prefix measurement before and after.
- Exact usage fields now preserved.
- `llm_usage.jsonl` schema and location.
- Retry classification and backoff behavior.
- Focused and full-suite command results.
- Remaining baseline failures and why they are outside scope.
- Every modified file and commit.

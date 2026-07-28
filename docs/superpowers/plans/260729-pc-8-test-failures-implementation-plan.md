# PC 分支 8 个既有测试失败修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不倒退当前设备架构、规划行为和相对顺序规则的前提下，修复 PC 分支现存的 8 个测试失败。

**Architecture:** 生产代码只修正 `RuleEngine._order_status` 与主验证路径之间的规则不一致；其余改动迁移过时测试，使设备测试依赖 `DeviceWorkflow` 当前契约、输出测试按语义选择记录、预算测试验证动态计划长度。所有生产行为改动先写失败回归测试，再做最小实现。

**Tech Stack:** Python 3、pytest、dataclasses、JSON 证据产物、Git

---

## 文件结构

- Modify: `autoairtest/verification/rule_engine.py`
  - 统一 Poco/OCR 冲突检测与正式相对顺序验证语义。
- Modify: `tests/test_verifier_evidence_gap.py`
  - 新增顺序冲突回归测试，并迁移两项旧严格列表断言。
- Modify: `tests/test_orchestrator_rationales_output.py`
  - 按解释类型选择导航别名依据。
- Modify: `tests/test_orchestrator_session_outputs.py`
  - 更新设备工作流假对象、证据补采构造契约和动态步骤预算断言。
- Modify: `tests/test_orchestrator_device_mode.py`
  - 在 `DeviceWorkflow` 边界注入假适配器，继续覆盖设备动作和证据产物。

### Task 1: 用 TDD 统一顺序冲突检测语义

**Files:**
- Modify: `tests/test_verifier_evidence_gap.py:244`
- Modify: `autoairtest/verification/rule_engine.py:625`

- [ ] **Step 1: 添加额外界面文本不构成 Poco/OCR 冲突的失败测试**

在 `test_order_conflict_between_poco_and_ocr_requires_manual_review` 前添加：

```python
def test_order_extra_text_does_not_create_poco_ocr_conflict():
    goal = VerificationGoal(
        goal_id="v1",
        claim="指数顺序正确",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["上证指数", "深证成指", "北证50", "科创综指"],
        evidence_priority=["poco_tree", "ocr_text"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals(
        [goal],
        {
            "visible_texts": ["指数列表", "上证指数", "最新价", "深证成指", "北证50", "科创综指"],
            "ocr_texts": ["上证指数", "深证成指", "北证50", "科创综指"],
            "evidence_files": ["element_summaries/090_verify.json", "ocr/090_verify.json"],
        },
    )

    assert judgment.preliminary_status == PreliminaryStatus.PASS
    assert judgment.manual_review_reason == ""
    assert judgment.structured_details["filtered_for_order"] == [
        "上证指数",
        "深证成指",
        "北证50",
        "科创综指",
    ]
```

- [ ] **Step 2: 运行新测试并确认 RED**

Run:

```powershell
$env:TEMP = 'C:\tmp\260729-autoairtest-pytest'
$env:TMP = $env:TEMP
python -m pytest -q tests/test_verifier_evidence_gap.py::test_order_extra_text_does_not_create_poco_ocr_conflict
```

Expected: FAIL；当前 `_order_status` 把 Poco 中的额外文本视为 `gap`，最终得到 `manual_required/conflicting_evidence`。

- [ ] **Step 3: 最小修正 `_order_status`**

将 `RuleEngine._order_status` 改为：

```python
def _order_status(self, expected_entities: list[str], observed_texts: list[str]) -> str:
    missing = [expected for expected in expected_entities if expected not in observed_texts]
    if missing:
        return "gap"
    filtered = [text for text in observed_texts if text in expected_entities]
    positions = [filtered.index(expected) for expected in expected_entities]
    return "pass" if positions == sorted(positions) else "fail"
```

- [ ] **Step 4: 运行新测试并确认 GREEN**

Run:

```powershell
python -m pytest -q tests/test_verifier_evidence_gap.py::test_order_extra_text_does_not_create_poco_ocr_conflict
```

Expected: `1 passed`。

- [ ] **Step 5: 运行已有真实冲突测试**

Run:

```powershell
python -m pytest -q tests/test_verifier_evidence_gap.py::test_order_conflict_between_poco_and_ocr_requires_manual_review
```

Expected: `1 passed`，确认真正的相对顺序差异仍会进入人工复核。

- [ ] **Step 6: 提交生产一致性修复**

```powershell
git add -- autoairtest/verification/rule_engine.py tests/test_verifier_evidence_gap.py
git commit -m "fix: align relative order conflict detection"
```

### Task 2: 迁移顺序诊断契约测试

**Files:**
- Modify: `tests/test_verifier_evidence_gap.py:10-51`

- [ ] **Step 1: 更新缺失实体测试的完整结构断言**

把期望字典改为：

```python
assert judgment.structured_details == {
    "expected": ["A", "B", "C", "D"],
    "observed": ["A", "B", "C"],
    "filtered_for_order": ["A", "B", "C"],
    "missing": ["D"],
    "evidence_source": "poco_tree",
}
```

- [ ] **Step 2: 更新“额外实体”测试以验证过滤语义**

保留 `missing == ["D"]`，把旧 `unexpected == ["E"]` 断言替换为：

```python
assert judgment.structured_details["observed"] == ["A", "B", "C", "E"]
assert judgment.structured_details["filtered_for_order"] == ["A", "B", "C"]
assert "unexpected" not in judgment.structured_details
```

- [ ] **Step 3: 运行两项原失败测试**

Run:

```powershell
python -m pytest -q tests/test_verifier_evidence_gap.py::test_order_gap_requires_manual_review_with_structured_details tests/test_verifier_evidence_gap.py::test_order_unexpected_entity_requires_manual_review_with_structured_details
```

Expected: `2 passed`。

- [ ] **Step 4: 运行整个验证缺口测试文件**

Run:

```powershell
python -m pytest -q tests/test_verifier_evidence_gap.py
```

Expected: 全部通过。

- [ ] **Step 5: 提交诊断契约迁移**

```powershell
git add -- tests/test_verifier_evidence_gap.py
git commit -m "test: align order evidence diagnostics"
```

### Task 3: 迁移解释依据与步骤预算测试

**Files:**
- Modify: `tests/test_orchestrator_rationales_output.py:33-37`
- Modify: `tests/test_orchestrator_session_outputs.py:489-505`

- [ ] **Step 1: 按语义类型查找导航别名依据**

将索引断言替换为：

```python
[alias_rationale] = [
    item
    for item in rationales
    if item["interpretation_type"] == "navigation_alias"
]
assert alias_rationale["original_expression"] == "自选"
assert alias_rationale["normalized_meaning"] == "我的自选"
```

- [ ] **Step 2: 运行解释依据原失败测试**

Run:

```powershell
python -m pytest -q tests/test_orchestrator_rationales_output.py::test_run_offline_writes_interpretation_rationales_json
```

Expected: `1 passed`。

- [ ] **Step 3: 用运行产物中的实际动作数验证步骤预算**

在读取 `action_results` 前读取计划：

```python
case_dir = run_dir / "cases" / "TC_step_budget"
execution_plan = json.loads((case_dir / "execution_plan.json").read_text(encoding="utf-8"))
planned_action_count = len(execution_plan["actions"])
action_results = json.loads((case_dir / "action_results.json").read_text(encoding="utf-8"))
assert planned_action_count > 1
```

保留阻断结果的字段断言，但把 notes 改为：

```python
"notes": [
    f"Execution plan has {planned_action_count} actions, exceeding max_steps_per_case=1."
],
```

- [ ] **Step 4: 运行步骤预算原失败测试**

Run:

```powershell
python -m pytest -q tests/test_orchestrator_session_outputs.py::test_run_offline_blocks_case_when_plan_exceeds_max_steps
```

Expected: `1 passed`。

- [ ] **Step 5: 提交稳定行为断言**

```powershell
git add -- tests/test_orchestrator_rationales_output.py tests/test_orchestrator_session_outputs.py
git commit -m "test: assert planner outputs by stable contracts"
```

### Task 4: 迁移设备工作流和证据补采假对象

**Files:**
- Modify: `tests/test_orchestrator_device_mode.py:1-70`
- Modify: `tests/test_orchestrator_session_outputs.py:247-447`

- [ ] **Step 1: 让会话输出测试的假工作流满足当前最小契约**

在两处 `FakeDeviceWorkflow` 类中加入：

```python
def __init__(self):
    self.poco = object()
    self.airtest = object()
```

对于仅验证工作流构造参数和状态图的测试，在 `execution` 配置中加入：

```python
"verification": {"evidence_recollection": {"max_attempts": 0}},
```

该配置应作为顶层键加入传给 `run_offline` 的字典，而不是嵌入 `execution`。

- [ ] **Step 2: 更新证据补采假对象的构造契约并记录依赖**

在测试函数内加入：

```python
recollector_kwargs = {}
```

把假对象构造函数改为：

```python
def __init__(self, max_attempts=2, poco=None, airtest=None):
    self.max_attempts = max_attempts
    recollector_kwargs.update(
        {
            "max_attempts": max_attempts,
            "poco": poco,
            "airtest": airtest,
        }
    )
```

离线模式没有设备工作流，因此在原有轨迹断言后增加：

```python
assert recollector_kwargs == {
    "max_attempts": 2,
    "poco": None,
    "airtest": None,
}
```

- [ ] **Step 3: 运行三个会话输出原失败测试**

Run:

```powershell
python -m pytest -q tests/test_orchestrator_session_outputs.py::test_run_offline_uses_device_workflow_when_execution_mode_is_device tests/test_orchestrator_session_outputs.py::test_run_offline_recollects_evidence_for_verification_gap tests/test_orchestrator_session_outputs.py::test_run_offline_updates_state_graph_when_enabled
```

Expected: `3 passed`。

- [ ] **Step 4: 把旧适配器测试迁移到真实 `DeviceWorkflow` 边界**

在 `tests/test_orchestrator_device_mode.py` 增加：

```python
from autoairtest.execution.device_workflow import DeviceWorkflow
```

增加最小 OCR 假对象：

```python
class FakeOCRAdapter:
    def recognize(self, screenshot_path):
        return {"status": "success", "items": [], "screenshot": screenshot_path}
```

删除对 `orchestrator.AirtestAdapter` 和 `orchestrator.PocoAdapter` 的替换，改为：

```python
fake_airtest = FakeAirtestAdapter(adb_serial="serial-1")
fake_poco = FakePocoAdapter()

def fake_device_workflow(*args, **kwargs):
    return DeviceWorkflow(
        airtest=fake_airtest,
        poco=fake_poco,
        ocr=FakeOCRAdapter(),
        correction_budget=kwargs.get("correction_budget"),
        retry_config={
            **kwargs.get("retry_config", {}),
            "default_interval_seconds": 0,
            "poco_dump_interval_seconds": 0,
        },
        app_config=kwargs.get("app_config"),
        evidence_config=kwargs.get("evidence_config"),
    )

monkeypatch.setattr(orchestrator, "DeviceWorkflow", fake_device_workflow)
```

把输出断言更新为当前命名和目标结构：

```python
assert action_results[0]["status"] == "success"
assert action_results[0]["target_element"]["text"] == "行情"
assert (run_dir / "cases" / "TC_device" / "screenshots" / "001_before_a1.png").exists()
assert (run_dir / "cases" / "TC_device" / "element_summaries" / "001_after_a1.json").exists()
```

并在配置顶层关闭与本测试无关的证据补采：

```python
"verification": {"evidence_recollection": {"max_attempts": 0}},
"logs": {"enable_capture": False},
```

- [ ] **Step 5: 运行设备模式原失败测试**

Run:

```powershell
python -m pytest -q tests/test_orchestrator_device_mode.py::test_run_offline_device_mode_calls_adapters_and_writes_evidence
```

Expected: `1 passed`。若当前设备工作流的稳定等待使测试变慢，只允许向构造函数注入立即稳定的 `stability_waiter_factory`，不得在生产代码加入测试分支。

- [ ] **Step 6: 提交设备测试迁移**

```powershell
git add -- tests/test_orchestrator_device_mode.py tests/test_orchestrator_session_outputs.py
git commit -m "test: align orchestrator device workflow contracts"
```

### Task 5: 分层验证全部修复

**Files:**
- Verify: `autoairtest/verification/rule_engine.py`
- Verify: `tests/test_verifier_evidence_gap.py`
- Verify: `tests/test_orchestrator_rationales_output.py`
- Verify: `tests/test_orchestrator_session_outputs.py`
- Verify: `tests/test_orchestrator_device_mode.py`

- [ ] **Step 1: 运行原 8 个失败测试**

Run:

```powershell
python -m pytest -q tests/test_orchestrator_device_mode.py::test_run_offline_device_mode_calls_adapters_and_writes_evidence tests/test_orchestrator_rationales_output.py::test_run_offline_writes_interpretation_rationales_json tests/test_orchestrator_session_outputs.py::test_run_offline_uses_device_workflow_when_execution_mode_is_device tests/test_orchestrator_session_outputs.py::test_run_offline_recollects_evidence_for_verification_gap tests/test_orchestrator_session_outputs.py::test_run_offline_updates_state_graph_when_enabled tests/test_orchestrator_session_outputs.py::test_run_offline_blocks_case_when_plan_exceeds_max_steps tests/test_verifier_evidence_gap.py::test_order_gap_requires_manual_review_with_structured_details tests/test_verifier_evidence_gap.py::test_order_unexpected_entity_requires_manual_review_with_structured_details
```

Expected: `8 passed`。

- [ ] **Step 2: 运行相关测试集**

Run:

```powershell
python -m pytest -q tests/test_device_workflow.py tests/test_evidence_recollection.py tests/test_orchestrator_device_mode.py tests/test_orchestrator_rationales_output.py tests/test_orchestrator_session_outputs.py tests/test_planner_rationales.py tests/test_verifier_evidence_gap.py
```

Expected: 全部通过。

- [ ] **Step 3: 运行编译检查**

Run:

```powershell
python -m compileall -q autoairtest
```

Expected: exit code `0`，无错误输出。

- [ ] **Step 4: 运行全量测试**

Run:

```powershell
python -m pytest -q
```

Expected: 零失败；允许保留基线中与 openpyxl 相关的 2 条已知 warning，但不得出现新 warning。

- [ ] **Step 5: 检查补丁和工作树**

Run:

```powershell
git diff --check
git status --short
git log --oneline -8
```

Expected: `git diff --check` 无输出；实现改动均已提交；没有无关文件。

- [ ] **Step 6: 复核设计验收标准**

逐项对照 `docs/superpowers/specs/260729-pc-8-test-failures-design.md`：

- 8 个指定失败通过。
- 顺序冲突回归测试完成可证明的红—绿循环。
- 不存在旧编排器适配器兼容层。
- 额外顺序文本被过滤而不是误判。
- 全量测试、编译检查和补丁检查通过。

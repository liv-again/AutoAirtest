# AutoAirtest Offline Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan ID:** `plan-autoairtest-offline-core-2026-06-15`

**Goal:** Build the testable offline core for AutoAirtest while keeping Airtest/Poco real-device execution behind optional adapters.

**Architecture:** The implementation uses a plain Python package with standard-library dataclasses, deterministic rule-based planning, offline verification, evidence JSON artifacts, and HTML reporting. Optional runtime integrations are isolated under `autoairtest/tools/` and never imported at package import time.

**Tech Stack:** Python 3.13 in `conda run -n torch`, standard library, `pytest`, optional `jinja2` for reporting if useful, optional `openpyxl` only when installed.

---

## File Structure

- `autoairtest/__init__.py`: package metadata.
- `autoairtest/__main__.py`: CLI module entry point.
- `autoairtest/cli.py`: argparse commands `init-config` and `run`.
- `autoairtest/config.py`: defaults, JSON config loading, CLI override merge, config template writing.
- `autoairtest/models.py`: enums, dataclasses, and recursive JSON serialization.
- `autoairtest/excel_loader.py`: workbook loading through optional `openpyxl`, plus row normalization helpers.
- `autoairtest/orchestrator.py`: offline run coordination.
- `autoairtest/agents/__init__.py`: agent package marker.
- `autoairtest/agents/planner.py`: rule-based planner.
- `autoairtest/agents/verifier.py`: order checks, manual review checks, run status aggregation.
- `autoairtest/tools/__init__.py`: tool package marker.
- `autoairtest/tools/airtest_adapter.py`: optional Airtest adapter with unavailable fallback.
- `autoairtest/tools/poco_adapter.py`: optional Poco adapter with unavailable fallback.
- `autoairtest/tools/ocr_adapter.py`: unavailable OCR adapter interface.
- `autoairtest/tools/llm_client.py`: unavailable LLM client interface.
- `autoairtest/tools/evidence_store.py`: evidence directory and JSON writer.
- `autoairtest/report/__init__.py`: report package marker.
- `autoairtest/report/html_report.py`: static HTML report writer.
- `docs/development-log.md`: implementation status, skipped Airtest/Poco tests, and known gaps.
- `tests/conftest.py`: fixtures for sample cases and temp output directories.
- `tests/test_models.py`: serialization and status aggregation model checks.
- `tests/test_config.py`: config defaults and template generation.
- `tests/test_excel_loader.py`: row mapping and optional dependency behavior.
- `tests/test_planner_rules.py`: seven-case planning and manual-review classification.
- `tests/test_verifier_order.py`: order verification and manual review behavior.
- `tests/test_evidence_report.py`: artifact and HTML generation.
- `tests/test_cli.py`: CLI init-config and offline run behavior.
- `tests/test_optional_adapters.py`: skipped Airtest/Poco integration checks with explicit skip reasons.

## Task 1: Core Models And Serialization

**Files:**
- Create: `autoairtest/__init__.py`
- Create: `autoairtest/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/test_models.py`:

```python
from autoairtest.models import (
    ActionResult,
    ActionStatus,
    NaturalLanguageTestCase,
    PreliminaryJudgment,
    PreliminaryStatus,
    RunResult,
    RunStatus,
    VerificationGoal,
    VerificationGoalCategory,
    dataclass_to_dict,
    summarize_run_status,
)


def test_case_and_nested_models_serialize_to_plain_dicts():
    case = NaturalLanguageTestCase(
        case_id="TC_国内指数更多跳转正常",
        internal_id="TC_国内指数更多跳转正常__row_4",
        row_number=4,
        business_module="股指",
        feature_module="国内指数",
        feature_item="一级宫格页面",
        test_purpose="跳转校验",
        priority="high",
        step_name="",
        precondition="",
        operation_description="行情-股指-国内指数：点击右侧“更多”按钮",
        parameters="",
        expected_result="跳转至国内指数列表页；科创综指排第四",
        original_fields={"测试结果": "", "备注": ""},
    )
    goal = VerificationGoal(
        goal_id="v1",
        claim="科创综指排在第四位",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["上证指数", "深证成指", "北证50", "科创综指"],
        evidence_priority=["poco_tree", "ocr_text", "screenshot"],
        human_review_required=False,
        review_reason="",
    )

    payload = dataclass_to_dict({"case": case, "goal": goal})

    assert payload["case"]["internal_id"] == "TC_国内指数更多跳转正常__row_4"
    assert payload["goal"]["category"] == "element_order"
    assert payload["goal"]["expected_entities"][3] == "科创综指"


def test_run_status_summary_prioritizes_blocked_then_fail_then_manual():
    blocked = ActionResult(
        action_id="a1",
        status=ActionStatus.BLOCKED,
        locator_level="poco_semantic",
        target_element=None,
        before_screenshot="",
        after_screenshot="",
        element_summary_before="",
        element_summary_after="",
        notes=["Airtest unavailable"],
    )
    manual = PreliminaryJudgment(
        goal_id="v2",
        preliminary_status=PreliminaryStatus.MANUAL_REQUIRED,
        confidence=0.0,
        basis="数据正确性需要人工复核",
        evidence_files=[],
        human_review_required=True,
        review_reason="market data correctness requires human review",
    )
    failed = PreliminaryJudgment(
        goal_id="v3",
        preliminary_status=PreliminaryStatus.FAIL,
        confidence=0.9,
        basis="顺序不匹配",
        evidence_files=[],
        human_review_required=False,
        review_reason="",
    )

    assert summarize_run_status([blocked], [manual]) == RunStatus.BLOCKED
    assert summarize_run_status([], [failed, manual]) == RunStatus.FAIL_PRELIMINARY
    assert summarize_run_status([], [manual]) == RunStatus.MANUAL_REQUIRED
    assert summarize_run_status([], []) == RunStatus.UNCERTAIN
```

- [ ] **Step 2: Run the model tests and observe failure**

Run:

```bash
conda run -n torch python -m pytest tests/test_models.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'autoairtest'`.

- [ ] **Step 3: Implement the minimal model layer**

Create `autoairtest/__init__.py`:

```python
"""Offline core for AI-assisted mobile securities app test execution."""

__version__ = "0.1.0"
```

Create `autoairtest/models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any


class SerializableEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ActionStatus(SerializableEnum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED_DEVICE_UNAVAILABLE = "skipped_device_unavailable"


class PreliminaryStatus(SerializableEnum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"
    MANUAL_REQUIRED = "manual_required"
    BLOCKED = "blocked"


class RunStatus(SerializableEnum):
    PASS_PRELIMINARY = "pass_preliminary"
    FAIL_PRELIMINARY = "fail_preliminary"
    MANUAL_REQUIRED = "manual_required"
    BLOCKED = "blocked"
    UNCERTAIN = "uncertain"


class VerificationGoalCategory(SerializableEnum):
    PAGE_NAVIGATION = "page_navigation"
    ELEMENT_ORDER = "element_order"
    POPUP_DISPLAY = "popup_display"
    DATA_CORRECTNESS = "data_correctness"
    COLOR_RULE = "color_rule"
    TEXT_PRESENT = "text_present"


@dataclass(frozen=True)
class NaturalLanguageTestCase:
    case_id: str
    internal_id: str
    row_number: int
    business_module: str
    feature_module: str
    feature_item: str
    test_purpose: str
    priority: str
    step_name: str
    precondition: str
    operation_description: str
    parameters: str
    expected_result: str
    original_fields: dict[str, str]


@dataclass(frozen=True)
class PlanAction:
    action_id: str
    intent: str
    description: str
    target: str
    target_context: str
    preferred_locator: str


@dataclass(frozen=True)
class VerificationGoal:
    goal_id: str
    claim: str
    category: VerificationGoalCategory
    expected_entities: list[str]
    evidence_priority: list[str]
    human_review_required: bool
    review_reason: str


@dataclass(frozen=True)
class ExecutionPlan:
    case_id: str
    preconditions: list[dict[str, str]]
    actions: list[PlanAction]
    verification_goals: list[VerificationGoal]
    notes: list[str]


@dataclass(frozen=True)
class ActionResult:
    action_id: str
    status: ActionStatus
    locator_level: str
    target_element: dict[str, Any] | None
    before_screenshot: str
    after_screenshot: str
    element_summary_before: str
    element_summary_after: str
    notes: list[str]


@dataclass(frozen=True)
class PreliminaryJudgment:
    goal_id: str
    preliminary_status: PreliminaryStatus
    confidence: float
    basis: str
    evidence_files: list[str]
    human_review_required: bool
    review_reason: str


@dataclass(frozen=True)
class RunResult:
    case_id: str
    run_status: RunStatus
    started_at: str
    finished_at: str
    action_results: list[ActionResult]
    preliminary_judgments: list[PreliminaryJudgment]
    evidence_dir: str
    summary: str


def dataclass_to_dict(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: dataclass_to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): dataclass_to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    return value


def summarize_run_status(
    action_results: list[ActionResult],
    judgments: list[PreliminaryJudgment],
) -> RunStatus:
    if any(result.status == ActionStatus.BLOCKED for result in action_results):
        return RunStatus.BLOCKED
    if any(j.preliminary_status == PreliminaryStatus.BLOCKED for j in judgments):
        return RunStatus.BLOCKED
    if any(j.preliminary_status == PreliminaryStatus.FAIL for j in judgments):
        return RunStatus.FAIL_PRELIMINARY
    if any(j.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED for j in judgments):
        return RunStatus.MANUAL_REQUIRED
    if judgments and all(j.preliminary_status == PreliminaryStatus.PASS for j in judgments):
        return RunStatus.PASS_PRELIMINARY
    return RunStatus.UNCERTAIN
```

- [ ] **Step 4: Run the model tests and observe pass**

Run:

```bash
conda run -n torch python -m pytest tests/test_models.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add autoairtest/__init__.py autoairtest/models.py tests/test_models.py
git commit -m "feat: add core data models"
```

## Task 2: Configuration Defaults And Template CLI Support

**Files:**
- Create: `autoairtest/config.py`
- Create: `autoairtest/cli.py`
- Create: `autoairtest/__main__.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing configuration tests**

Create `tests/test_config.py`:

```python
import json

from autoairtest.config import default_config, load_config, merge_config, write_config_template


def test_default_config_contains_required_offline_boundaries():
    config = default_config()

    assert config["device"]["platform"] == "android_real_device"
    assert config["execution"]["mode"] == "offline"
    assert config["verification"]["data_correctness_requires_human_review"] is True
    assert config["report"]["output_dir"] == "runs"


def test_merge_config_recursively_applies_overrides():
    merged = merge_config(
        default_config(),
        {"report": {"output_dir": "tmp-runs"}, "app": {"package": "com.example"}},
    )

    assert merged["report"]["output_dir"] == "tmp-runs"
    assert merged["app"]["package"] == "com.example"
    assert merged["execution"]["retry"]["poco_dump_max_attempts"] == 3


def test_write_and_load_json_template(tmp_path):
    output = tmp_path / "config.template.json"

    write_config_template(output)
    loaded = load_config(output)

    assert loaded["input"]["sheet_name"] == "需求测试报告"
    assert json.loads(output.read_text(encoding="utf-8"))["llm"]["model"] == "configured-by-env"
```

- [ ] **Step 2: Run the config tests and observe failure**

Run:

```bash
conda run -n torch python -m pytest tests/test_config.py -v
```

Expected: import failure for `autoairtest.config`.

- [ ] **Step 3: Implement config and CLI shell**

Create `autoairtest/config.py`:

```python
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def default_config() -> dict[str, Any]:
    return {
        "app": {"package": "", "activity": "", "startup_wait_seconds": 5},
        "device": {
            "platform": "android_real_device",
            "adb_serial": "",
            "unlock_before_run": True,
        },
        "input": {
            "excel_path": "docs/test-cases.xlsx",
            "sheet_name": "需求测试报告",
            "case_filter": "",
        },
        "execution": {
            "mode": "offline",
            "continue_on_case_failure": True,
            "action_timeout_seconds": 10,
            "page_stable_timeout_seconds": 8,
            "max_locator_attempts": 3,
            "screenshot_every_action": True,
            "save_full_ui_tree": False,
            "retry": {
                "default_max_attempts": 2,
                "default_interval_seconds": 1,
                "poco_dump_max_attempts": 3,
                "poco_dump_interval_seconds": 1,
                "poco_dump_backoff": "fixed",
            },
        },
        "verification": {
            "primary_evidence": "poco",
            "always_save_screenshot": True,
            "llm_preliminary_judgment": False,
            "data_correctness_requires_human_review": True,
            "color_rule_requires_human_review": True,
            "min_confidence_for_auto_preliminary": 0.75,
        },
        "llm": {"model": "configured-by-env", "temperature": 0.1, "max_retries": 2},
        "report": {"output_dir": "runs", "generate_html": True, "write_back_excel": False},
    }


def merge_config(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        return json.loads(config_path.read_text(encoding="utf-8"))
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("PyYAML is not installed in the torch environment; use JSON config for now.") from exc
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    raise ValueError(f"Unsupported config file type: {config_path.suffix}")


def write_config_template(path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(default_config(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output
```

Create `autoairtest/cli.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from .config import write_config_template


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoairtest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_config = subparsers.add_parser("init-config")
    init_config.add_argument("--output", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--config", default="")
    run.add_argument("--excel", default="")
    run.add_argument("--sheet", default="")
    run.add_argument("--case-filter", default="")
    run.add_argument("--app-package", default="")
    run.add_argument("--app-activity", default="")
    run.add_argument("--adb-serial", default="")
    run.add_argument("--output-dir", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-config":
        output = write_config_template(Path(args.output))
        print(f"Wrote config template: {output}")
        return 0

    if args.command == "run":
        raise SystemExit("run command is implemented in the orchestrator task")

    parser.error(f"Unknown command: {args.command}")
    return 2
```

Create `autoairtest/__main__.py`:

```python
from .cli import main


raise SystemExit(main())
```

- [ ] **Step 4: Run config tests and init-config command**

Run:

```bash
conda run -n torch python -m pytest tests/test_config.py -v
conda run -n torch python -m autoairtest init-config --output config.template.json
```

Expected: `3 passed`; command prints `Wrote config template: config.template.json`.

- [ ] **Step 5: Remove generated config template and commit**

Run:

```bash
Remove-Item -LiteralPath config.template.json
git add autoairtest/config.py autoairtest/cli.py autoairtest/__main__.py tests/test_config.py
git commit -m "feat: add config template support"
```

## Task 3: Excel Loader With Optional Dependency Handling

**Files:**
- Create: `autoairtest/excel_loader.py`
- Test: `tests/test_excel_loader.py`

- [ ] **Step 1: Write failing loader tests**

Create `tests/test_excel_loader.py`:

```python
import pytest

from autoairtest.excel_loader import (
    REQUIRED_HEADERS,
    ExcelDependencyError,
    build_case_from_row,
    load_test_cases,
)


def test_build_case_from_row_normalizes_empty_values_and_duplicate_ids():
    row = {
        "业务模块": "股指",
        "功能模块": "国内指数",
        "功能项": None,
        "测试目的": "跳转校验",
        "TC_用例名称": "TC_国内指数更多跳转正常",
        "优先级": "high",
        "步骤名称": None,
        "前置条件": "",
        "操作描述": "行情-股指-国内指数：点击右侧“更多”按钮",
        "参数": None,
        "预期结果": "跳转至国内指数列表页；科创综指排第四",
        "测试结果": None,
        "备注": None,
    }

    case = build_case_from_row(row, row_number=4, duplicate_names={"TC_国内指数更多跳转正常"})

    assert case.case_id == "TC_国内指数更多跳转正常"
    assert case.internal_id == "TC_国内指数更多跳转正常__row_4"
    assert case.feature_item == ""
    assert case.parameters == ""
    assert case.original_fields["备注"] == ""


def test_required_headers_match_source_design():
    assert REQUIRED_HEADERS == [
        "业务模块",
        "功能模块",
        "功能项",
        "测试目的",
        "TC_用例名称",
        "优先级",
        "步骤名称",
        "前置条件",
        "操作描述",
        "参数",
        "预期结果",
        "测试结果",
        "备注",
    ]


def test_load_test_cases_reports_missing_openpyxl_when_dependency_absent(monkeypatch, tmp_path):
    def fake_import(name):
        if name == "openpyxl":
            raise ModuleNotFoundError("openpyxl")
        return __import__(name)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(ExcelDependencyError, match="openpyxl is not installed"):
        load_test_cases(tmp_path / "cases.xlsx", "需求测试报告")
```

- [ ] **Step 2: Run loader tests and observe failure**

Run:

```bash
conda run -n torch python -m pytest tests/test_excel_loader.py -v
```

Expected: import failure for `autoairtest.excel_loader`.

- [ ] **Step 3: Implement loader helpers and optional `openpyxl` load**

Create `autoairtest/excel_loader.py`:

```python
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .models import NaturalLanguageTestCase


REQUIRED_HEADERS = [
    "业务模块",
    "功能模块",
    "功能项",
    "测试目的",
    "TC_用例名称",
    "优先级",
    "步骤名称",
    "前置条件",
    "操作描述",
    "参数",
    "预期结果",
    "测试结果",
    "备注",
]


class ExcelDependencyError(RuntimeError):
    pass


def normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_case_from_row(
    row: dict[str, Any],
    row_number: int,
    duplicate_names: set[str],
) -> NaturalLanguageTestCase:
    normalized = {header: normalize_cell(row.get(header)) for header in REQUIRED_HEADERS}
    case_id = normalized["TC_用例名称"]
    internal_id = f"{case_id}__row_{row_number}" if case_id in duplicate_names else case_id
    return NaturalLanguageTestCase(
        case_id=case_id,
        internal_id=internal_id,
        row_number=row_number,
        business_module=normalized["业务模块"],
        feature_module=normalized["功能模块"],
        feature_item=normalized["功能项"],
        test_purpose=normalized["测试目的"],
        priority=normalized["优先级"],
        step_name=normalized["步骤名称"],
        precondition=normalized["前置条件"],
        operation_description=normalized["操作描述"],
        parameters=normalized["参数"],
        expected_result=normalized["预期结果"],
        original_fields=normalized,
    )


def load_test_cases(excel_path: str | Path, sheet_name: str) -> list[NaturalLanguageTestCase]:
    try:
        import openpyxl  # type: ignore
    except ModuleNotFoundError as exc:
        raise ExcelDependencyError(
            "openpyxl is not installed in the torch environment; install it in torch or use test fixtures."
        ) from exc

    workbook = openpyxl.load_workbook(excel_path, data_only=True)
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Sheet not found: {sheet_name}")
    sheet = workbook[sheet_name]

    headers = [normalize_cell(sheet.cell(row=1, column=col).value) for col in range(1, sheet.max_column + 1)]
    missing = [header for header in REQUIRED_HEADERS if header not in headers]
    if missing:
        raise ValueError(f"Missing required Excel headers: {', '.join(missing)}")

    rows: list[tuple[int, dict[str, Any]]] = []
    case_names: list[str] = []
    for row_number in range(2, sheet.max_row + 1):
        row = {
            header: sheet.cell(row=row_number, column=headers.index(header) + 1).value
            for header in REQUIRED_HEADERS
        }
        if not any(normalize_cell(value) for value in row.values()):
            continue
        rows.append((row_number, row))
        case_names.append(normalize_cell(row.get("TC_用例名称")))

    duplicates = {name for name, count in Counter(case_names).items() if name and count > 1}
    return [build_case_from_row(row, row_number, duplicates) for row_number, row in rows]
```

- [ ] **Step 4: Run loader tests and observe pass**

Run:

```bash
conda run -n torch python -m pytest tests/test_excel_loader.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add autoairtest/excel_loader.py tests/test_excel_loader.py
git commit -m "feat: add excel case loader"
```

## Task 4: Rule-Based Planner

**Files:**
- Create: `autoairtest/agents/__init__.py`
- Create: `autoairtest/agents/planner.py`
- Test: `tests/test_planner_rules.py`

- [ ] **Step 1: Write failing planner tests**

Create `tests/test_planner_rules.py`:

```python
from autoairtest.agents.planner import RuleBasedPlanner
from autoairtest.excel_loader import build_case_from_row
from autoairtest.models import VerificationGoalCategory


def make_case(name, operation, expected, purpose="跳转校验", row=2):
    return build_case_from_row(
        {
            "业务模块": "股指",
            "功能模块": "国内指数",
            "功能项": "一级宫格页面",
            "测试目的": purpose,
            "TC_用例名称": name,
            "优先级": "high",
            "步骤名称": "",
            "前置条件": "",
            "操作描述": operation,
            "参数": "",
            "预期结果": expected,
            "测试结果": "",
            "备注": "",
        },
        row_number=row,
        duplicate_names=set(),
    )


def test_more_button_case_generates_navigation_actions_and_order_goal():
    case = make_case(
        "TC_国内指数更多跳转正常",
        "行情-股指-国内指数：点击右侧“更多”按钮",
        "跳转至国内指数列表页；科创综指排第四",
    )

    plan = RuleBasedPlanner().plan(case)

    assert [action.target for action in plan.actions] == ["行情", "股指", "国内指数", "更多"]
    assert plan.verification_goals[0].category == VerificationGoalCategory.PAGE_NAVIGATION
    assert plan.verification_goals[1].category == VerificationGoalCategory.ELEMENT_ORDER
    assert plan.verification_goals[1].expected_entities == ["上证指数", "深证成指", "北证50", "科创综指"]


def test_data_correctness_and_color_rules_require_human_review():
    case = make_case(
        "TC_大盘指数数据显示正确",
        "行情-A股-沪深京：查看大盘指数模块数据显示",
        "科创综指排第四；数据展示正确；两端一致；红涨绿跌黑平",
        purpose="数据校验",
    )

    plan = RuleBasedPlanner().plan(case)
    manual_goals = [goal for goal in plan.verification_goals if goal.human_review_required]

    assert {goal.category for goal in manual_goals} == {
        VerificationGoalCategory.DATA_CORRECTNESS,
        VerificationGoalCategory.COLOR_RULE,
    }
    assert all("human review" in goal.review_reason for goal in manual_goals)
```

- [ ] **Step 2: Run planner tests and observe failure**

Run:

```bash
conda run -n torch python -m pytest tests/test_planner_rules.py -v
```

Expected: import failure for `autoairtest.agents.planner`.

- [ ] **Step 3: Implement deterministic planner**

Create `autoairtest/agents/__init__.py`:

```python
"""Agent-like deterministic components for offline planning and verification."""
```

Create `autoairtest/agents/planner.py`:

```python
from __future__ import annotations

from autoairtest.models import (
    ExecutionPlan,
    NaturalLanguageTestCase,
    PlanAction,
    VerificationGoal,
    VerificationGoalCategory,
)


DEFAULT_DOMESTIC_ORDER = ["上证指数", "深证成指", "北证50", "科创综指"]
DETAIL_WITH_INDUSTRY_ORDER = ["行业板块", "上证指数", "深证成指", "科创综指", "北证50", "创业板指"]
DETAIL_WITHOUT_INDUSTRY_ORDER = ["上证指数", "深证成指", "科创综指", "北证50", "创业板指"]


class RuleBasedPlanner:
    def plan(self, case: NaturalLanguageTestCase) -> ExecutionPlan:
        actions = self._actions_for(case.operation_description)
        goals = self._goals_for(case)
        return ExecutionPlan(
            case_id=case.internal_id,
            preconditions=[
                {
                    "type": "app_state",
                    "description": case.precondition or "App 已登录并位于可进入行情页的状态",
                    "mvp_handling": "manual_prepare_or_precheck",
                }
            ],
            actions=actions,
            verification_goals=goals,
            notes=["Rule-based offline plan; no Python code generated."],
        )

    def _actions_for(self, operation: str) -> list[PlanAction]:
        targets: list[tuple[str, str, str]] = []
        if "行情" in operation:
            targets.append(("navigate", "进入行情页", "行情"))
        if "股指" in operation:
            targets.append(("navigate", "进入股指区域", "股指"))
        if "A股" in operation or "沪深京" in operation:
            targets.append(("navigate", "进入A股沪深京区域", "沪深京"))
        if "国内指数" in operation:
            targets.append(("navigate", "进入国内指数区域", "国内指数"))
        if "更多" in operation:
            targets.append(("tap", "点击右侧更多按钮", "更多"))
        if "科创综指" in operation and "点击" in operation:
            targets.append(("tap", "点击科创综指", "科创综指"))
        if "底部指数" in operation:
            targets.append(("tap", "点击底部指数入口", "底部指数"))
        if "自选顶部指数" in operation:
            targets.append(("tap", "点击自选顶部指数", "自选顶部指数"))
        if not targets:
            targets.append(("observe", "观察当前页面", "当前页面"))

        return [
            PlanAction(
                action_id=f"a{index}",
                intent=intent,
                description=description,
                target=target,
                target_context=operation,
                preferred_locator="poco_semantic",
            )
            for index, (intent, description, target) in enumerate(targets, start=1)
        ]

    def _goals_for(self, case: NaturalLanguageTestCase) -> list[VerificationGoal]:
        text = f"{case.expected_result} {case.operation_description}"
        goals: list[VerificationGoal] = []

        if "跳转" in text:
            goals.append(self._goal("页面跳转符合预期", VerificationGoalCategory.PAGE_NAVIGATION))
        if "弹框" in text:
            goals.append(self._goal("指数分时图弹框展示", VerificationGoalCategory.POPUP_DISPLAY))
        if "排第四" in text or "第四位" in text:
            goals.append(
                self._goal(
                    "科创综指排在第四位",
                    VerificationGoalCategory.ELEMENT_ORDER,
                    expected_entities=DEFAULT_DOMESTIC_ORDER,
                )
            )
        if "行业板块" in text:
            goals.append(
                self._goal(
                    "有行业板块时指数顺序正确",
                    VerificationGoalCategory.ELEMENT_ORDER,
                    expected_entities=DETAIL_WITH_INDUSTRY_ORDER,
                )
            )
        elif "上证指数、深证成指、科创综指、北证50、创业板指" in text:
            goals.append(
                self._goal(
                    "无行业板块时指数顺序正确",
                    VerificationGoalCategory.ELEMENT_ORDER,
                    expected_entities=DETAIL_WITHOUT_INDUSTRY_ORDER,
                )
            )
        if "数据" in text or "一致" in text:
            goals.append(
                self._goal(
                    "行情数据正确性或两端一致性需要人工复核",
                    VerificationGoalCategory.DATA_CORRECTNESS,
                    human_review_required=True,
                    review_reason="market data correctness requires human review",
                )
            )
        if "红涨绿跌黑平" in text or "颜色" in text:
            goals.append(
                self._goal(
                    "颜色规则需要人工复核",
                    VerificationGoalCategory.COLOR_RULE,
                    human_review_required=True,
                    review_reason="color rule requires human review",
                )
            )
        if not goals:
            goals.append(self._goal("预期结果需要人工确认", VerificationGoalCategory.TEXT_PRESENT))
        return goals

    def _goal(
        self,
        claim: str,
        category: VerificationGoalCategory,
        expected_entities: list[str] | None = None,
        human_review_required: bool = False,
        review_reason: str = "",
    ) -> VerificationGoal:
        return VerificationGoal(
            goal_id="v0",
            claim=claim,
            category=category,
            expected_entities=expected_entities or [],
            evidence_priority=["poco_tree", "ocr_text", "screenshot"],
            human_review_required=human_review_required,
            review_reason=review_reason,
        )
```

After writing this, adjust goal IDs inside `_goals_for` by recreating the final list with `v1`, `v2`, etc.:

```python
        return [
            VerificationGoal(
                goal_id=f"v{index}",
                claim=goal.claim,
                category=goal.category,
                expected_entities=goal.expected_entities,
                evidence_priority=goal.evidence_priority,
                human_review_required=goal.human_review_required,
                review_reason=goal.review_reason,
            )
            for index, goal in enumerate(goals, start=1)
        ]
```

- [ ] **Step 4: Run planner tests and observe pass**

Run:

```bash
conda run -n torch python -m pytest tests/test_planner_rules.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add autoairtest/agents/__init__.py autoairtest/agents/planner.py tests/test_planner_rules.py
git commit -m "feat: add rule based planner"
```

## Task 5: Verifier And Evidence Store

**Files:**
- Create: `autoairtest/agents/verifier.py`
- Create: `autoairtest/tools/__init__.py`
- Create: `autoairtest/tools/evidence_store.py`
- Test: `tests/test_verifier_order.py`
- Test: `tests/test_evidence_report.py`

- [ ] **Step 1: Write failing verifier and evidence tests**

Create `tests/test_verifier_order.py`:

```python
from autoairtest.agents.verifier import verify_goals
from autoairtest.models import PreliminaryStatus, VerificationGoal, VerificationGoalCategory


def test_order_goal_passes_when_expected_entities_are_in_order():
    goal = VerificationGoal(
        goal_id="v1",
        claim="科创综指排在第四位",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["上证指数", "深证成指", "北证50", "科创综指"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )
    evidence = {"visible_texts": ["行情", "上证指数", "深证成指", "北证50", "科创综指", "更多"]}

    [judgment] = verify_goals([goal], evidence)

    assert judgment.preliminary_status == PreliminaryStatus.PASS
    assert judgment.confidence >= 0.75


def test_order_goal_fails_when_entities_are_out_of_order():
    goal = VerificationGoal(
        goal_id="v1",
        claim="科创综指排在第四位",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["上证指数", "深证成指", "北证50", "科创综指"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )
    evidence = {"visible_texts": ["行情", "上证指数", "科创综指", "深证成指", "北证50"]}

    [judgment] = verify_goals([goal], evidence)

    assert judgment.preliminary_status == PreliminaryStatus.FAIL


def test_manual_goal_is_marked_manual_without_automatic_pass():
    goal = VerificationGoal(
        goal_id="v2",
        claim="数据展示正确",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=[],
        evidence_priority=["screenshot"],
        human_review_required=True,
        review_reason="market data correctness requires human review",
    )

    [judgment] = verify_goals([goal], {})

    assert judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED
    assert judgment.human_review_required is True
```

Create `tests/test_evidence_report.py` with only evidence store checks for this task:

```python
import json

from autoairtest.tools.evidence_store import EvidenceStore


def test_evidence_store_creates_case_directories_and_writes_json(tmp_path):
    store = EvidenceStore(tmp_path, timestamp="20260615-120000")
    case_dir = store.create_case_dir("TC_case__row_2")

    written = store.write_case_json("TC_case__row_2", "case.json", {"case_id": "TC_case"})

    assert case_dir.name == "TC_case__row_2"
    assert (case_dir / "screenshots").is_dir()
    assert (case_dir / "element_summaries").is_dir()
    assert json.loads(written.read_text(encoding="utf-8"))["case_id"] == "TC_case"
```

- [ ] **Step 2: Run tests and observe failure**

Run:

```bash
conda run -n torch python -m pytest tests/test_verifier_order.py tests/test_evidence_report.py -v
```

Expected: import failures for verifier and evidence store.

- [ ] **Step 3: Implement verifier and evidence store**

Create `autoairtest/tools/__init__.py`:

```python
"""Tool adapter and evidence storage interfaces."""
```

Create `autoairtest/agents/verifier.py`:

```python
from __future__ import annotations

from autoairtest.models import (
    PreliminaryJudgment,
    PreliminaryStatus,
    VerificationGoal,
    VerificationGoalCategory,
)


def verify_goals(
    goals: list[VerificationGoal],
    evidence: dict[str, object],
) -> list[PreliminaryJudgment]:
    return [_verify_goal(goal, evidence) for goal in goals]


def _verify_goal(goal: VerificationGoal, evidence: dict[str, object]) -> PreliminaryJudgment:
    if goal.human_review_required:
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.MANUAL_REQUIRED,
            confidence=0.0,
            basis=f"{goal.claim} cannot be finalized automatically in MVP.",
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=True,
            review_reason=goal.review_reason,
        )

    visible_texts = [str(item) for item in evidence.get("visible_texts", [])]
    if goal.category == VerificationGoalCategory.ELEMENT_ORDER:
        return _verify_order(goal, visible_texts, evidence)
    if goal.category in {VerificationGoalCategory.PAGE_NAVIGATION, VerificationGoalCategory.POPUP_DISPLAY, VerificationGoalCategory.TEXT_PRESENT}:
        return _verify_text_presence(goal, visible_texts, evidence)

    return PreliminaryJudgment(
        goal_id=goal.goal_id,
        preliminary_status=PreliminaryStatus.UNCERTAIN,
        confidence=0.0,
        basis="No offline verifier exists for this goal category.",
        evidence_files=list(evidence.get("evidence_files", [])),
        human_review_required=False,
        review_reason="",
    )


def _verify_order(
    goal: VerificationGoal,
    visible_texts: list[str],
    evidence: dict[str, object],
) -> PreliminaryJudgment:
    positions: list[int] = []
    for expected in goal.expected_entities:
        try:
            positions.append(visible_texts.index(expected))
        except ValueError:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.UNCERTAIN,
                confidence=0.0,
                basis=f"Missing expected text: {expected}",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
            )

    passed = positions == sorted(positions)
    return PreliminaryJudgment(
        goal_id=goal.goal_id,
        preliminary_status=PreliminaryStatus.PASS if passed else PreliminaryStatus.FAIL,
        confidence=0.82 if passed else 0.88,
        basis=f"Observed order positions: {positions}",
        evidence_files=list(evidence.get("evidence_files", [])),
        human_review_required=False,
        review_reason="",
    )


def _verify_text_presence(
    goal: VerificationGoal,
    visible_texts: list[str],
    evidence: dict[str, object],
) -> PreliminaryJudgment:
    haystack = " ".join(visible_texts)
    expected = goal.expected_entities or [goal.claim]
    if any(item and item in haystack for item in expected):
        status = PreliminaryStatus.PASS
        confidence = 0.78
        basis = "Expected text was found in interface evidence."
    else:
        status = PreliminaryStatus.UNCERTAIN
        confidence = 0.0
        basis = "No matching text evidence was available offline."
    return PreliminaryJudgment(
        goal_id=goal.goal_id,
        preliminary_status=status,
        confidence=confidence,
        basis=basis,
        evidence_files=list(evidence.get("evidence_files", [])),
        human_review_required=False,
        review_reason="",
    )
```

Create `autoairtest/tools/evidence_store.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autoairtest.models import dataclass_to_dict


class EvidenceStore:
    def __init__(self, output_dir: str | Path, timestamp: str):
        self.root = Path(output_dir) / timestamp
        self.cases_root = self.root / "cases"
        self.root.mkdir(parents=True, exist_ok=True)
        self.cases_root.mkdir(parents=True, exist_ok=True)

    def create_case_dir(self, case_id: str) -> Path:
        case_dir = self.cases_root / safe_path_name(case_id)
        for child in ["screenshots", "element_summaries", "ocr"]:
            (case_dir / child).mkdir(parents=True, exist_ok=True)
        return case_dir

    def write_case_json(self, case_id: str, filename: str, payload: Any) -> Path:
        case_dir = self.create_case_dir(case_id)
        output = case_dir / filename
        output.write_text(
            json.dumps(dataclass_to_dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return output

    def write_run_json(self, filename: str, payload: Any) -> Path:
        output = self.root / filename
        output.write_text(
            json.dumps(dataclass_to_dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return output


def safe_path_name(value: str) -> str:
    return "".join(ch if ch not in '<>:"/\\\\|?*' else "_" for ch in value).strip() or "case"
```

- [ ] **Step 4: Run tests and observe pass**

Run:

```bash
conda run -n torch python -m pytest tests/test_verifier_order.py tests/test_evidence_report.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add autoairtest/agents/verifier.py autoairtest/tools/__init__.py autoairtest/tools/evidence_store.py tests/test_verifier_order.py tests/test_evidence_report.py
git commit -m "feat: add verifier and evidence store"
```

## Task 6: Optional Runtime Adapters And Skip Tests

**Files:**
- Create: `autoairtest/tools/airtest_adapter.py`
- Create: `autoairtest/tools/poco_adapter.py`
- Create: `autoairtest/tools/ocr_adapter.py`
- Create: `autoairtest/tools/llm_client.py`
- Test: `tests/test_optional_adapters.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/test_optional_adapters.py`:

```python
import importlib.util

import pytest

from autoairtest.tools.airtest_adapter import AirtestAdapter
from autoairtest.tools.llm_client import LLMClient
from autoairtest.tools.ocr_adapter import OCRAdapter
from autoairtest.tools.poco_adapter import PocoAdapter


@pytest.mark.skipif(importlib.util.find_spec("airtest") is None, reason="Airtest is not installed in torch; real-device tests are skipped and logged.")
def test_airtest_runtime_package_available_for_integration():
    assert importlib.util.find_spec("airtest") is not None


@pytest.mark.skipif(importlib.util.find_spec("poco") is None, reason="Poco is not installed in torch; real-device tests are skipped and logged.")
def test_poco_runtime_package_available_for_integration():
    assert importlib.util.find_spec("poco") is not None


def test_unavailable_adapters_return_clear_status_without_import_crash():
    assert AirtestAdapter().connect()["status"] in {"unavailable", "connected"}
    assert PocoAdapter().dump()["status"] in {"unavailable", "success"}
    assert OCRAdapter().recognize("missing.png")["status"] == "unavailable"
    assert LLMClient().json_call("prompt", {})["status"] == "unavailable"
```

- [ ] **Step 2: Run adapter tests and observe failure**

Run:

```bash
conda run -n torch python -m pytest tests/test_optional_adapters.py -v
```

Expected: import failure for adapter modules.

- [ ] **Step 3: Implement adapters with unavailable fallbacks**

Create `autoairtest/tools/airtest_adapter.py`:

```python
from __future__ import annotations

import importlib.util
from typing import Any


class AirtestAdapter:
    def __init__(self) -> None:
        self.available = importlib.util.find_spec("airtest") is not None

    def connect(self) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch"}
        return {"status": "connected", "reason": ""}

    def start_app(self, package: str, activity: str = "") -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "package": package, "activity": activity}
        return {"status": "success", "package": package, "activity": activity}

    def snapshot(self, filename: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "filename": filename}
        return {"status": "success", "filename": filename}

    def touch(self, target: object) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "target": target}
        return {"status": "success", "target": target}
```

Create `autoairtest/tools/poco_adapter.py`:

```python
from __future__ import annotations

import importlib.util
from typing import Any


class PocoAdapter:
    def __init__(self) -> None:
        self.available = importlib.util.find_spec("poco") is not None

    def dump(self) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "visible_texts": []}
        return {"status": "success", "visible_texts": []}

    def query(self, text: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "matches": []}
```

Create `autoairtest/tools/ocr_adapter.py`:

```python
from __future__ import annotations

from typing import Any


class OCRAdapter:
    def recognize(self, image_path: str) -> dict[str, Any]:
        return {"status": "unavailable", "reason": "OCR is out of scope for the offline core pass", "image_path": image_path, "texts": []}
```

Create `autoairtest/tools/llm_client.py`:

```python
from __future__ import annotations

from typing import Any


class LLMClient:
    def json_call(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {"status": "unavailable", "reason": "LLM integration is out of scope for the offline core pass", "prompt": prompt, "schema": schema}
```

- [ ] **Step 4: Run adapter tests and observe pass with skips**

Run:

```bash
conda run -n torch python -m pytest tests/test_optional_adapters.py -v
```

Expected: `1 passed, 2 skipped` when Airtest and Poco are absent.

- [ ] **Step 5: Commit**

Run:

```bash
git add autoairtest/tools/airtest_adapter.py autoairtest/tools/poco_adapter.py autoairtest/tools/ocr_adapter.py autoairtest/tools/llm_client.py tests/test_optional_adapters.py
git commit -m "feat: add optional runtime adapters"
```

## Task 7: Orchestrator, Report, And CLI Run

**Files:**
- Create: `autoairtest/orchestrator.py`
- Create: `autoairtest/report/__init__.py`
- Create: `autoairtest/report/html_report.py`
- Modify: `autoairtest/cli.py`
- Test: append to `tests/test_evidence_report.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing report and CLI tests**

Append to `tests/test_evidence_report.py`:

```python
from autoairtest.models import RunStatus
from autoairtest.report.html_report import write_html_report


def test_html_report_contains_case_status(tmp_path):
    report = write_html_report(
        tmp_path,
        [
            {
                "case_id": "TC_case",
                "run_status": RunStatus.MANUAL_REQUIRED.value,
                "summary": "需要人工复核",
                "evidence_dir": "cases/TC_case",
            }
        ],
    )

    html = report.read_text(encoding="utf-8")
    assert "TC_case" in html
    assert "manual_required" in html
    assert "需要人工复核" in html
```

Create `tests/test_cli.py`:

```python
import json
import subprocess
import sys


def test_cli_init_config_generates_json(tmp_path):
    output = tmp_path / "config.template.json"

    result = subprocess.run(
        [sys.executable, "-m", "autoairtest", "init-config", "--output", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Wrote config template" in result.stdout
    assert json.loads(output.read_text(encoding="utf-8"))["input"]["sheet_name"] == "需求测试报告"


def test_cli_offline_run_writes_report_when_excel_dependency_missing(tmp_path):
    output_dir = tmp_path / "runs"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "autoairtest",
            "run",
            "--excel",
            "docs/test-cases.xlsx",
            "--sheet",
            "需求测试报告",
            "--output-dir",
            str(output_dir),
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Run directory:" in result.stdout
    run_dirs = list(output_dir.iterdir())
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "run_summary.json").is_file()
    assert (run_dirs[0] / "report.html").is_file()
```

- [ ] **Step 2: Run report and CLI tests and observe failure**

Run:

```bash
conda run -n torch python -m pytest tests/test_evidence_report.py tests/test_cli.py -v
```

Expected: import failure for report module and CLI `run command is implemented in the orchestrator task`.

- [ ] **Step 3: Implement report and orchestrator**

Create `autoairtest/report/__init__.py`:

```python
"""HTML reporting."""
```

Create `autoairtest/report/html_report.py`:

```python
from __future__ import annotations

from html import escape
from pathlib import Path


def write_html_report(run_dir: str | Path, case_summaries: list[dict[str, str]]) -> Path:
    output_dir = Path(run_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(item['case_id'])}</td>"
        f"<td>{escape(item['run_status'])}</td>"
        f"<td>{escape(item['summary'])}</td>"
        f"<td>{escape(item['evidence_dir'])}</td>"
        "</tr>"
        for item in case_summaries
    )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>AutoAirtest Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f4f4f4; }}
  </style>
</head>
<body>
  <h1>AutoAirtest Report</h1>
  <table>
    <thead><tr><th>Case</th><th>Status</th><th>Summary</th><th>Evidence</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""
    output = output_dir / "report.html"
    output.write_text(html, encoding="utf-8")
    return output
```

Create `autoairtest/orchestrator.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .agents.planner import RuleBasedPlanner
from .agents.verifier import verify_goals
from .config import default_config, load_config, merge_config
from .excel_loader import ExcelDependencyError, build_case_from_row, load_test_cases
from .models import ActionResult, ActionStatus, RunResult, dataclass_to_dict, summarize_run_status
from .report.html_report import write_html_report
from .tools.evidence_store import EvidenceStore


def run_offline(config_overrides: dict[str, Any]) -> Path:
    config = default_config()
    config_path = config_overrides.pop("config", "")
    if config_path:
        config = merge_config(config, load_config(config_path))
    config = merge_config(config, config_overrides)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    store = EvidenceStore(config["report"]["output_dir"], timestamp)
    planner = RuleBasedPlanner()

    cases = _load_cases_or_dependency_case(config)
    run_results: list[RunResult] = []
    case_summaries: list[dict[str, str]] = []

    for case in cases:
        store.create_case_dir(case.internal_id)
        plan = planner.plan(case)
        action_results = [
            ActionResult(
                action_id=action.action_id,
                status=ActionStatus.SKIPPED_DEVICE_UNAVAILABLE,
                locator_level=action.preferred_locator,
                target_element=None,
                before_screenshot="",
                after_screenshot="",
                element_summary_before="",
                element_summary_after="",
                notes=["Offline core run: Airtest/Poco execution is unavailable in current environment."],
            )
            for action in plan.actions
        ]
        judgments = verify_goals(plan.verification_goals, {"visible_texts": [], "evidence_files": []})
        status = summarize_run_status(action_results, judgments)
        run_result = RunResult(
            case_id=case.internal_id,
            run_status=status,
            started_at=timestamp,
            finished_at=datetime.now().isoformat(timespec="seconds"),
            action_results=action_results,
            preliminary_judgments=judgments,
            evidence_dir=f"cases/{case.internal_id}",
            summary=_summary_for_status(status.value),
        )

        store.write_case_json(case.internal_id, "case.json", case)
        store.write_case_json(case.internal_id, "execution_plan.json", plan)
        store.write_case_json(case.internal_id, "action_results.json", action_results)
        store.write_case_json(case.internal_id, "verification_result.json", judgments)
        store.write_case_json(case.internal_id, "logs.txt.json", {"notes": ["Offline run completed without device execution."]})
        run_results.append(run_result)
        case_summaries.append(
            {
                "case_id": run_result.case_id,
                "run_status": run_result.run_status.value,
                "summary": run_result.summary,
                "evidence_dir": run_result.evidence_dir,
            }
        )

    store.write_run_json("run_summary.json", {"results": [dataclass_to_dict(item) for item in run_results]})
    write_html_report(store.root, case_summaries)
    return store.root


def _load_cases_or_dependency_case(config: dict[str, Any]):
    try:
        return load_test_cases(config["input"]["excel_path"], config["input"]["sheet_name"])
    except ExcelDependencyError as exc:
        return [
            build_case_from_row(
                {
                    "业务模块": "环境",
                    "功能模块": "依赖检查",
                    "功能项": "Excel读取",
                    "测试目的": "环境检查",
                    "TC_用例名称": "TC_openpyxl_dependency_missing",
                    "优先级": "high",
                    "步骤名称": "",
                    "前置条件": "",
                    "操作描述": "读取Excel测试用例",
                    "参数": "",
                    "预期结果": str(exc),
                    "测试结果": "",
                    "备注": str(exc),
                },
                row_number=0,
                duplicate_names=set(),
            )
        ]


def _summary_for_status(status: str) -> str:
    if status == "manual_required":
        return "存在需要人工复核的验证目标。"
    if status == "blocked":
        return "执行被阻塞。"
    if status == "pass_preliminary":
        return "自动初步判断通过。"
    if status == "fail_preliminary":
        return "自动初步判断失败。"
    return "离线证据不足，结果不确定。"
```

Modify `autoairtest/cli.py` so `run` calls the orchestrator:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from .config import write_config_template
from .orchestrator import run_offline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoairtest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_config = subparsers.add_parser("init-config")
    init_config.add_argument("--output", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--config", default="")
    run.add_argument("--excel", default="")
    run.add_argument("--sheet", default="")
    run.add_argument("--case-filter", default="")
    run.add_argument("--app-package", default="")
    run.add_argument("--app-activity", default="")
    run.add_argument("--adb-serial", default="")
    run.add_argument("--output-dir", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-config":
        output = write_config_template(Path(args.output))
        print(f"Wrote config template: {output}")
        return 0

    if args.command == "run":
        overrides = {
            "config": args.config,
            "input": {
                "excel_path": args.excel or "docs/test-cases.xlsx",
                "sheet_name": args.sheet or "需求测试报告",
                "case_filter": args.case_filter,
            },
            "app": {"package": args.app_package, "activity": args.app_activity},
            "device": {"adb_serial": args.adb_serial},
            "report": {"output_dir": args.output_dir or "runs"},
        }
        run_dir = run_offline(overrides)
        print(f"Run directory: {run_dir}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
```

- [ ] **Step 4: Run report and CLI tests and observe pass**

Run:

```bash
conda run -n torch python -m pytest tests/test_evidence_report.py tests/test_cli.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add autoairtest/orchestrator.py autoairtest/report/__init__.py autoairtest/report/html_report.py autoairtest/cli.py tests/test_evidence_report.py tests/test_cli.py
git commit -m "feat: add offline run orchestration"
```

## Task 8: Development Log, Full Verification, And Cleanup

**Files:**
- Create: `docs/development-log.md`
- Modify: implementation files if full-suite failures expose mismatches.

- [ ] **Step 1: Write the development log**

Create `docs/development-log.md`:

```markdown
# Development Log

Date: 2026-06-15

## Implemented

- Initialized the repository and configured `origin` as `https://github.com/liv-again/AutoAirtest.git`.
- Added the approved offline-core design and implementation plan.
- Built the offline Python package skeleton for `autoairtest`.
- Added standard-library data models and JSON serialization.
- Added JSON configuration defaults and `init-config`.
- Added Excel loader helpers and optional `openpyxl` dependency handling.
- Added deterministic planner rules for the documented securities app cases.
- Added verifier logic for order checks and human-review classification.
- Added evidence directory and JSON artifact writing.
- Added optional adapter interfaces for Airtest, Poco, OCR, and LLM.
- Added static HTML report generation and offline CLI run command.

## Skipped In Current Environment

- Airtest integration tests are skipped because `airtest` is not installed in the `torch` conda environment.
- Poco integration tests are skipped because `poco` is not installed in the `torch` conda environment.
- Real Android device execution is not verified because no device/App package configuration was provided.

## Known Gaps

- `openpyxl` is not installed in `torch`, so real workbook loading reports a clear dependency error until the package is installed in that environment.
- YAML config loading requires `PyYAML`, which is not installed in `torch`; JSON config is supported.
- OCR recognition is an interface only.
- LLM planning and verification are interfaces only.
- Excel result write-back is not implemented.
- Screenshot capture and screenshot redaction are not implemented.
- MCP server exposure is not implemented.

## Verification Commands

- `conda run -n torch python -m pytest`
- `conda run -n torch python -m autoairtest init-config --output config.template.json`
- `conda run -n torch python -m autoairtest run --excel docs/test-cases.xlsx --sheet 需求测试报告 --output-dir runs`
```

- [ ] **Step 2: Run the full test suite**

Run:

```bash
conda run -n torch python -m pytest
```

Expected: all offline tests pass; Airtest/Poco integration checks are explicitly skipped.

- [ ] **Step 3: Run CLI acceptance commands**

Run:

```bash
conda run -n torch python -m autoairtest init-config --output config.template.json
conda run -n torch python -m autoairtest run --excel docs/test-cases.xlsx --sheet 需求测试报告 --output-dir runs
```

Expected:

- `config.template.json` exists and contains JSON defaults.
- `runs/<timestamp>/run_summary.json` exists.
- `runs/<timestamp>/report.html` exists.
- The run completes even when `openpyxl` is missing by producing a dependency-check case.

- [ ] **Step 4: Remove generated acceptance artifacts**

Run:

```bash
Remove-Item -LiteralPath config.template.json
```

Do not delete `runs/`; it is ignored and can remain as local verification evidence.

- [ ] **Step 5: Check repository status**

Run:

```bash
git status --short --branch
```

Expected: only implementation and documentation files are modified or untracked; `runs/` and `config.template.json` are not tracked.

- [ ] **Step 6: Commit final docs**

Run:

```bash
git add docs/development-log.md
git commit -m "docs: record offline core development status"
```

- [ ] **Step 7: Final verification before handoff**

Run:

```bash
conda run -n torch python -m pytest
git status --short --branch
```

Expected: tests pass with explicit Airtest/Poco skips; worktree is clean except ignored local verification artifacts.

## Self-Review

Spec coverage:

- Package and CLI are covered by Tasks 1, 2, and 7.
- Config defaults and command-line overrides are covered by Tasks 2 and 7.
- Natural-language test case models are covered by Task 1.
- Excel loading and dependency handling are covered by Task 3.
- Rule-based planning is covered by Task 4.
- Evidence artifacts are covered by Task 5 and Task 7.
- Verification and run status aggregation are covered by Task 1 and Task 5.
- HTML reporting is covered by Task 7.
- Optional Airtest/Poco adapters and skipped tests are covered by Task 6.
- Development log is covered by Task 8.

Placeholder scan: no unresolved implementation markers remain in this plan.

Type consistency:

- `ActionStatus`, `PreliminaryStatus`, `RunStatus`, and `VerificationGoalCategory` are defined before use.
- `NaturalLanguageTestCase`, `ExecutionPlan`, `ActionResult`, `PreliminaryJudgment`, and `RunResult` property names match across tests and implementation steps.
- CLI calls `run_offline`, which is introduced in Task 7 before final verification.

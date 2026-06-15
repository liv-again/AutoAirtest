"""离线运行编排器。

编排器串联配置合并、用例加载、规则规划、离线执行占位、初步验证、证据写入和报告
生成。它是当前 MVP 的主控流水线，但不直接调用 Airtest 或 Poco 原始 API。
"""

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
from .tools.evidence_store import EvidenceStore, safe_path_name


def run_offline(config_overrides: dict[str, Any]) -> Path:
    """执行一次离线测试运行并返回运行目录。

    在当前实现中，设备动作被记录为“设备不可用跳过”，用于验证证据链和报告链路。
    """

    overrides = dict(config_overrides)
    config = default_config()
    config_path = overrides.pop("config", "")
    if config_path:
        config = merge_config(config, load_config(config_path))
    config = merge_config(config, overrides)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    store = EvidenceStore(config["report"]["output_dir"], timestamp)
    planner = RuleBasedPlanner()

    cases = _filter_cases(_load_cases_or_dependency_case(config), config["input"].get("case_filter", ""))
    run_results: list[RunResult] = []
    case_summaries: list[dict[str, str]] = []

    for case in cases:
        case_dir = store.create_case_dir(case.internal_id)
        plan = planner.plan(case)
        # 离线核心不执行真实点击，而是保留动作级证据结构，供后续设备适配器替换。
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
            evidence_dir=f"cases/{safe_path_name(case.internal_id)}",
            summary=_summary_for_status(status.value),
        )

        store.write_case_json(case.internal_id, "case.json", case)
        store.write_case_json(case.internal_id, "execution_plan.json", plan)
        store.write_case_json(case.internal_id, "interpretation_rationales.json", plan.interpretation_rationales)
        store.write_case_json(case.internal_id, "action_results.json", action_results)
        store.write_case_json(case.internal_id, "verification_result.json", judgments)
        (case_dir / "logs.txt").write_text("Offline run completed without device execution.\n", encoding="utf-8")
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
    if config["report"].get("generate_html", True):
        write_html_report(store.root, case_summaries)
    return store.root


def _load_cases_or_dependency_case(config: dict[str, Any]):
    """加载 Excel 用例；当缺少 openpyxl 时生成一条环境诊断用例。"""

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


def _filter_cases(cases, case_filter: str):
    """按用例名称、内部 ID、操作描述或预期结果进行朴素子串筛选。"""

    needle = str(case_filter or "").strip()
    if not needle:
        return cases
    return [
        case
        for case in cases
        if needle in case.case_id
        or needle in case.internal_id
        or needle in case.operation_description
        or needle in case.expected_result
    ]


def _summary_for_status(status: str) -> str:
    """把机器状态映射为面向人工复核的中文摘要。"""

    if status == "manual_required":
        return "存在需要人工复核的验证目标。"
    if status == "blocked":
        return "执行被阻塞。"
    if status == "pass_preliminary":
        return "自动初步判断通过。"
    if status == "fail_preliminary":
        return "自动初步判断失败。"
    return "离线证据不足，结果不确定。"

"""调试脚本：仅执行 planner + execution，跳过 verification。

用法:
    python test_plan_execute.py
    conda run -n torch python test_plan_execute.py

该脚本复用 config.yaml、Excel 用例和 DeviceWorkflow，但不运行 VerificationAgent，
避免验证阶段因 PocoService 不稳定而阻塞。产物写入 runs/ 目录。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from autoairtest.config import default_config, load_config, merge_config
from autoairtest.excel_loader import ExcelDependencyError, build_case_from_row, load_test_cases
from autoairtest.execution.device_workflow import DeviceWorkflow
from autoairtest.agents.planner import RuleBasedPlanner
from autoairtest.models import (
    ActionResult,
    ActionStatus,
    RunResult,
    TestSession,
    dataclass_to_dict,
    summarize_run_status,
)
from autoairtest.planning.planning_agent import PlanningAgent
from autoairtest.planning.skill_registry import SkillRegistry
from autoairtest.report.html_report import write_html_report
from autoairtest.tools.evidence_store import EvidenceStore, safe_path_name
from autoairtest.tools.llm_client import LLMClient
from autoairtest.tools.log_collector import LogCollector


def build_config() -> dict[str, Any]:
    """加载并合并配置，与 run_offline 保持一致。"""
    config = default_config()
    config_path = "config.yaml"
    if Path(config_path).exists():
        config = merge_config(config, load_config(config_path))
    return config


def _planning_llm_client(config: dict[str, Any]) -> LLMClient | None:
    llm_config = config.get("llm", {})
    if not llm_config.get("enabled", False) or not llm_config.get("use_for_planning", False):
        return None
    return LLMClient(config=llm_config, evidence_config=config.get("evidence", {}))


def _load_cases(config: dict[str, Any]) -> list[Any]:
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


def _filter_cases(cases: list[Any], case_filter: str) -> list[Any]:
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


def _write_case_log(
    case_dir: Path,
    case: Any,
    action_results: list[ActionResult],
    plan: Any,
    config: dict[str, Any],
) -> None:
    """写入结构化日志（与 orchestrator._write_case_log 逻辑一致）。"""
    is_device = config.get("execution", {}).get("mode") == "device"
    lines: list[str] = []

    if not is_device:
        lines.append("Offline run completed without device execution.")
        (case_dir / "logs.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    lines.append("=" * 60)
    lines.append("AutoAirtest Device Execution Log (debug: verification skipped)")
    lines.append("=" * 60)
    lines.append(f"Case ID      : {getattr(case, 'internal_id', 'unknown')}")
    lines.append(f"Case Name    : {getattr(case, 'case_id', 'unknown')}")
    lines.append(f"Description  : {getattr(case, 'operation_description', '')}")
    lines.append(f"Plan Actions : {len(plan.actions)}")
    lines.append(f"LLM Planning : {config.get('execution', {}).get('llm', False)}")
    lines.append(f"Executed At  : {datetime.now().isoformat(timespec='seconds')}")

    setup_path = case_dir / "device_setup.json"
    if setup_path.exists():
        try:
            setup = json.loads(setup_path.read_text(encoding="utf-8"))
            lines.append(f"Device Setup : {setup.get('status', 'unknown')}")
            if setup.get("reason"):
                lines.append(f"Setup Reason : {setup['reason']}")
        except (json.JSONDecodeError, OSError):
            lines.append("Device Setup : <unable to read>")
    else:
        lines.append("Device Setup : <not found>")

    lines.append("")
    lines.append("-" * 60)
    lines.append("Action Results")
    lines.append("-" * 60)

    status_counts: dict[str, int] = {}
    for i, ar in enumerate(action_results, 1):
        status = ar.status.value
        status_counts[status] = status_counts.get(status, 0) + 1
        lines.append(f"  [{i}] {ar.action_id} -> {status}")
        if ar.notes:
            for note in ar.notes:
                lines.append(f"       note: {note}")

    lines.append("")
    lines.append("-" * 60)
    lines.append("Summary")
    lines.append("-" * 60)
    lines.append(f"  Total Actions : {len(action_results)}")
    for status, count in sorted(status_counts.items()):
        lines.append(f"  {status:>30s} : {count}")
    lines.append("")
    lines.append("  Verification   : SKIPPED (debug mode)")
    lines.append("=" * 60)

    (case_dir / "logs.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_plan_and_execute() -> Path:
    """仅执行规划与设备操作，跳过验证阶段。"""
    config = build_config()

    # 解析 execution.llm 标志位（与 orchestrator 一致）
    llm_used = bool(
        config.get("llm", {}).get("enabled", False)
        and config.get("llm", {}).get("use_for_planning", False)
    )
    config["execution"]["llm"] = llm_used

    overview = config.get("execution", {}).get("mode", "offline")
    print(f"[plan+execute] mode={overview}, llm={llm_used}")

    # 初始化
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    session_id = f"{timestamp}_debug"
    store = EvidenceStore(config["report"]["output_dir"], session_id)
    skill_registry = SkillRegistry(config.get("skills", {}).get("root", "skills"))
    planner = PlanningAgent(
        llm_client=_planning_llm_client(config),
        rule_based_planner=RuleBasedPlanner(skill_registry=skill_registry),
        skill_registry=skill_registry,
    )

    cases = _filter_cases(_load_cases(config), config["input"].get("case_filter", ""))
    print(f"[plan+execute] 加载 {len(cases)} 条用例")

    store.write_config_snapshot(config)
    store.initialize_jsonl("steps.jsonl")
    store.write_session_meta(
        TestSession(
            session_id=session_id,
            workflow="plan_execute_debug",
            started_at=datetime.now().isoformat(timespec="seconds"),
            finished_at="",
            app_package=config["app"].get("package", ""),
            adb_serial=config["device"].get("adb_serial", ""),
            config_snapshot="config.resolved.json",
            case_count=len(cases),
            status="running",
        )
    )

    run_results: list[RunResult] = []
    case_summaries: list[dict[str, str]] = []
    step_index = 0
    log_collector = LogCollector(enabled=bool(config.get("logs", {}).get("enable_capture", True)))

    # ── 设备模式下创建一次 DeviceWorkflow，复用设备连接并支持用例间导航回主框架 ──
    device_workflow = None
    if config.get("execution", {}).get("mode") == "device":
        device_workflow = DeviceWorkflow(
            correction_budget=config.get("execution", {}).get("correction_budget", {}),
            retry_config=config.get("execution", {}).get("retry", {}),
            app_config=config.get("app", {}),
            evidence_config=config.get("evidence", {}),
        )

    for case in cases:
        case_dir = store.create_case_dir(case.internal_id)
        print(f"  [{case.internal_id}] planning...")

        # ── Planning ──
        plan = planner.plan(case)
        max_steps = int(config.get("execution", {}).get("max_steps_per_case", 0) or 0)
        if max_steps > 0 and len(plan.actions) > max_steps:
            action_results = [
                ActionResult(
                    action_id="step_budget",
                    status=ActionStatus.BLOCKED,
                    locator_level="",
                    target_element=None,
                    before_screenshot="",
                    after_screenshot="",
                    element_summary_before="",
                    element_summary_after="",
                    notes=[f"Execution plan has {len(plan.actions)} actions, exceeding max_steps_per_case={max_steps}."],
                )
            ]
        else:
            # ── Execution ──
            assert device_workflow is not None, "test_plan_execute requires device mode"
            action_results = device_workflow.execute_plan(plan, case_dir)

        for ar in action_results:
            step_index += 1
            store.append_jsonl(
                "steps.jsonl",
                {
                    "index": step_index,
                    "case_id": case.internal_id,
                    "action_id": ar.action_id,
                    "result": ar.status.value,
                    "crash_count": 0,
                    "notes": ar.notes,
                },
            )

        # ── 写日志（验证前，确保不丢失）──
        _write_case_log(case_dir, case, action_results, plan, config)

        # ── 写 case 级产物 ──
        store.write_case_json(case.internal_id, "case.json", case)
        store.write_case_json(case.internal_id, "execution_plan.json", plan)
        store.write_case_json(case.internal_id, "action_results.json", action_results)

        # 执行结果汇总（跳过验证 → judgments 为空）
        judgments: list[Any] = []
        status = summarize_run_status(action_results, judgments)
        run_result = RunResult(
            case_id=case.internal_id,
            run_status=status,
            started_at=timestamp,
            finished_at=datetime.now().isoformat(timespec="seconds"),
            action_results=action_results,
            preliminary_judgments=judgments,
            evidence_dir=f"cases/{safe_path_name(case.internal_id)}",
            summary=f"[DEBUG] 验证跳过。动作状态: {status.value}",
        )
        run_results.append(run_result)
        case_summaries.append(
            {
                "case_id": run_result.case_id,
                "run_status": run_result.run_status.value,
                "summary": run_result.summary,
                "evidence_dir": run_result.evidence_dir,
                "manual_review_reason": "verification_skipped_in_debug",
            }
        )

        # ── 恢复主框架：按返回键直到检测到底部导航栏 ──
        if device_workflow is not None:
            home_result = device_workflow.navigate_to_home()
            result_text = "home_detected" if home_result["home_detected"] else "home_failed"
            print(f"    navigate_to_home: {result_text} ({home_result['back_presses']} back presses)")

    # ── 运行级产物 ──
    store.write_run_json(
        "run_summary.json",
        {"results": [dataclass_to_dict(item) for item in run_results]},
    )
    store.write_session_meta(
        TestSession(
            session_id=session_id,
            workflow="plan_execute_debug",
            started_at=datetime.now().isoformat(timespec="seconds"),
            finished_at=datetime.now().isoformat(timespec="seconds"),
            app_package=config["app"].get("package", ""),
            adb_serial=config["device"].get("adb_serial", ""),
            config_snapshot="config.resolved.json",
            case_count=len(cases),
            status="completed",
        )
    )
    if config["report"].get("generate_html", True):
        write_html_report(store.root, case_summaries)

    print(f"\n[plan+execute] 完成 → {store.root}")
    return store.root


if __name__ == "__main__":
    run_plan_and_execute()

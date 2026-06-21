"""离线运行编排器。

编排器串联配置合并、用例加载、规则规划、离线执行占位、初步验证、证据写入和报告
生成。它是当前 MVP 的主控流水线，但不直接调用 Airtest 或 Poco 原始 API。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .execution.device_workflow import DeviceWorkflow
from .execution.state_graph import StateGraph, page_fingerprint
from .agents.planner import RuleBasedPlanner
from .agents.verifier import verify_goals
from .config import default_config, load_config, merge_config
from .excel_loader import ExcelDependencyError, build_case_from_row, load_test_cases
from .excel_writer import write_results_copy
from .models import ActionResult, ActionStatus, RunResult, dataclass_to_dict, summarize_run_status
from .report.html_report import write_html_report
from .tools.evidence_store import EvidenceStore, safe_path_name
from .tools.llm_client import LLMClient
from .tools.log_collector import LogCollector
from .verification.evidence_recollection import EvidenceRecollector


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

    started_at = datetime.now().isoformat(timespec="seconds")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    session_suffix = safe_path_name(str(config["report"].get("session_name", "")))
    session_id = f"{timestamp}_{session_suffix}" if session_suffix else timestamp
    store = EvidenceStore(config["report"]["output_dir"], session_id)
    planner = RuleBasedPlanner()

    cases = _filter_cases(_load_cases_or_dependency_case(config), config["input"].get("case_filter", ""))
    cases = _apply_case_param_overrides(cases, config["input"].get("case_params", {}))
    store.write_config_snapshot(config)
    store.initialize_jsonl("steps.jsonl")
    store.initialize_jsonl("crashes.jsonl")
    state_graph = StateGraph()
    store.write_run_json("state_graph.json", state_graph.to_dict())
    store.write_session_meta(
        {
            "session_id": session_id,
            "workflow": "excel_case_run",
            "started_at": started_at,
            "finished_at": "",
            "app_package": config["app"].get("package", ""),
            "adb_serial": config["device"].get("adb_serial", ""),
            "config_snapshot": "config.resolved.json",
            "case_count": len(cases),
            "status": "running",
        }
    )
    run_results: list[RunResult] = []
    case_summaries: list[dict[str, str]] = []
    step_index = 0
    crash_index = 0
    seen_crash_signatures: set[str] = set()
    log_collector = LogCollector(enabled=bool(config.get("logs", {}).get("enable_capture", True)))

    for case in cases:
        case_dir = store.create_case_dir(case.internal_id)
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
                    notes=[
                        f"Execution plan has {len(plan.actions)} actions, exceeding max_steps_per_case={max_steps}."
                    ],
                )
            ]
        elif config.get("execution", {}).get("mode") == "device":
            action_results = DeviceWorkflow(
                correction_budget=config.get("execution", {}).get("correction_budget", {}),
                retry_config=config.get("execution", {}).get("retry", {}),
                app_config=config.get("app", {}),
                evidence_config=config.get("evidence", {}),
            ).execute_plan(plan, case_dir)
        else:
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
        for action_result in action_results:
            step_index += 1
            crash_check = log_collector.get_recent_crashes(
                package=str(config.get("app", {}).get("package", "")),
                lines=300,
            )
            crashes = crash_check.get("crashes", [])
            for crash in crashes:
                crash_key = _crash_signature_key(crash)
                if crash_key in seen_crash_signatures:
                    continue
                seen_crash_signatures.add(crash_key)
                crash_index += 1
                store.append_jsonl(
                    "crashes.jsonl",
                    {
                        "crash_id": f"c{crash_index}",
                        "case_id": case.internal_id,
                        "step_index": step_index,
                        "action_id": action_result.action_id,
                        "signature": crash,
                        "original_repro_path": list(range(1, step_index + 1)),
                    },
                )
            store.append_jsonl(
                "steps.jsonl",
                {
                    "index": step_index,
                    "case_id": case.internal_id,
                    "action_id": action_result.action_id,
                    "result": action_result.status.value,
                    "crash_count": len(crashes),
                    "notes": action_result.notes,
                },
            )
        if config.get("execution", {}).get("enable_state_graph", False):
            _update_state_graph_from_actions(state_graph, case.internal_id, case_dir, action_results)
        verification_evidence = {
            "visible_texts": [],
            "evidence_files": [],
            "llm_preliminary_judgment": bool(
                config.get("verification", {}).get("llm_preliminary_judgment", False)
            ),
        }
        if verification_evidence["llm_preliminary_judgment"]:
            verification_evidence["llm_client"] = LLMClient(
                config=config.get("llm", {}),
                evidence_config=config.get("evidence", {}),
            )
        judgments = verify_goals(plan.verification_goals, verification_evidence)
        evidence_recollection_trace = _collect_evidence_for_verification_gaps(judgments, case_dir, config)
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
        if evidence_recollection_trace:
            store.write_case_json(case.internal_id, "evidence_recollection_trace.json", evidence_recollection_trace)
            _append_evidence_recollection_execution_trace(case_dir, evidence_recollection_trace)
        (case_dir / "logs.txt").write_text("Offline run completed without device execution.\n", encoding="utf-8")
        run_results.append(run_result)
        case_summaries.append(
            {
                "case_id": run_result.case_id,
                "run_status": run_result.run_status.value,
                "summary": run_result.summary,
                "evidence_dir": run_result.evidence_dir,
                "manual_review_reason": _manual_review_reason(judgments),
            }
        )

    excel_result_copy = ""
    if config.get("report", {}).get("write_back_excel", False):
        excel_path = Path(str(config.get("input", {}).get("excel_path", "")))
        if excel_path.exists():
            excel_result_copy = str(
                write_results_copy(
                    excel_path,
                    str(config.get("input", {}).get("sheet_name", "")),
                    case_summaries,
                    store.root / "test-cases-with-results.xlsx",
                ).relative_to(store.root)
            )
    store.write_run_json(
        "state_graph.json",
        state_graph.to_dict(),
    )
    store.write_run_json(
        "run_summary.json",
        {
            "results": [dataclass_to_dict(item) for item in run_results],
            "excel_result_copy": excel_result_copy,
        },
    )
    store.write_session_meta(
        {
            "session_id": session_id,
            "workflow": "excel_case_run",
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "app_package": config["app"].get("package", ""),
            "adb_serial": config["device"].get("adb_serial", ""),
            "config_snapshot": "config.resolved.json",
            "case_count": len(cases),
            "excel_result_copy": excel_result_copy,
            "status": "completed",
        }
    )
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


def _manual_review_reason(judgments) -> str:
    """汇总用例内需要人工复核的原因，供报告筛选。"""

    reasons = []
    for judgment in judgments:
        reason = judgment.manual_review_reason or judgment.review_reason
        if judgment.human_review_required and reason and reason not in reasons:
            reasons.append(reason)
    return ", ".join(reasons)


def _collect_evidence_for_verification_gaps(judgments, case_dir: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    """对验证证据不足的目标执行受限补采，并返回可审计轨迹。"""

    recollection_config = config.get("verification", {}).get("evidence_recollection", {})
    max_attempts = int(recollection_config.get("max_attempts", 0) or 0)
    if max_attempts <= 0:
        return []

    gap_judgments = [
        judgment
        for judgment in judgments
        if judgment.human_review_required
        and (judgment.manual_review_reason or judgment.review_reason) == "verification_evidence_gap"
    ]
    if not gap_judgments:
        return []

    recollector = EvidenceRecollector(max_attempts=max_attempts)
    trace: list[dict[str, Any]] = []
    for judgment in gap_judgments:
        for attempt in range(1, max_attempts + 1):
            trace.append(recollector.recollect(judgment.goal_id, case_dir, attempt))
    return trace


def _apply_case_param_overrides(cases, case_params: dict[str, Any]) -> list[Any]:
    """把命令行用例业务参数覆盖到每条用例的 parameters 字段。"""

    if not case_params:
        return cases
    return [_replace_case_parameters(case, case_params) for case in cases]


def _replace_case_parameters(case, case_params: dict[str, Any]):
    base_params = _parse_case_parameters(case.parameters)
    merged = {**base_params, **{str(key): str(value) for key, value in case_params.items()}}
    parameters = json.dumps(merged, ensure_ascii=False, sort_keys=True)
    original_fields = dict(case.original_fields)
    original_fields["参数"] = parameters
    return replace(case, parameters=parameters, original_fields=original_fields)


def _parse_case_parameters(raw_parameters: str) -> dict[str, str]:
    text = str(raw_parameters or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"_excel_parameters": text}
    if isinstance(parsed, dict):
        return {str(key): str(value) for key, value in parsed.items()}
    return {"_excel_parameters": text}


def _append_evidence_recollection_execution_trace(
    case_dir: Path,
    recollection_trace: list[dict[str, Any]],
) -> None:
    """把验证证据补采记录追加进统一执行审计轨迹。"""

    trace_path = case_dir / "execution_trace.json"
    existing: list[dict[str, Any]] = []
    if trace_path.exists():
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            existing = [item for item in payload if isinstance(item, dict)]

    next_index = len(existing) + 1
    for item in recollection_trace:
        action = str(item.get("action", ""))
        screenshot = str(item.get("screenshot", ""))
        existing.append(
            {
                "trace_id": f"t{next_index}",
                "trace_type": "evidence_recollection",
                "action_id": str(item.get("goal_id", "")),
                "planned_target": "verification_evidence_gap",
                "normalized_target": action,
                "candidate_elements": [],
                "selected_element": None,
                "action_risk_level": str(item.get("action_risk_level", "low")),
                "execution_rationale": (
                    "Verification evidence was incomplete; collected bounded supplemental evidence."
                ),
                "before_evidence": [],
                "after_evidence": [screenshot] if screenshot else [],
                "correction_step": {
                    "type": "evidence_recollection",
                    "attempt": int(item.get("attempt", 0) or 0),
                    "trigger": "verification_evidence_gap",
                },
            }
        )
        next_index += 1

    trace_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _update_state_graph_from_actions(
    graph: StateGraph,
    case_id: str,
    case_dir: Path,
    action_results: list[ActionResult],
) -> None:
    """从动作前后元素摘要中更新页面状态图。"""

    for result in action_results:
        before = _read_element_summary(case_dir, result.element_summary_before)
        after = _read_element_summary(case_dir, result.element_summary_after)
        before_elements = _elements_from_summary(before)
        after_elements = _elements_from_summary(after)
        if not before_elements or not after_elements:
            continue

        before_hash = page_fingerprint(before_elements)
        after_hash = page_fingerprint(after_elements)
        graph.record_page(
            before_hash,
            summary=_summary_text(before),
            screenshot=result.before_screenshot,
        )
        graph.record_page(
            after_hash,
            summary=_summary_text(after),
            screenshot=result.after_screenshot,
        )
        for text in before.get("visible_texts", []):
            graph.mark_element_seen(before_hash, f"text:{text}")
        for text in after.get("visible_texts", []):
            graph.mark_element_seen(after_hash, f"text:{text}")
        graph.record_edge(before_hash, result.action_id, after_hash, case_id=case_id)


def _read_element_summary(case_dir: Path, relative_path: str) -> dict[str, Any]:
    if not relative_path:
        return {}
    path = case_dir / relative_path
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _elements_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    elements = summary.get("elements", [])
    if isinstance(elements, list) and elements:
        return [item for item in elements if isinstance(item, dict)]
    visible_texts = summary.get("visible_texts", [])
    if isinstance(visible_texts, list):
        return [{"text": str(item)} for item in visible_texts if str(item)]
    return []


def _summary_text(summary: dict[str, Any]) -> str:
    visible_texts = summary.get("visible_texts", [])
    if isinstance(visible_texts, list):
        return "|".join(str(item) for item in visible_texts)
    return ""


def _crash_signature_key(crash: Any) -> str:
    if isinstance(crash, dict):
        signature_id = str(crash.get("signature_id", "")).strip()
        if signature_id:
            return signature_id
        return json.dumps(crash, ensure_ascii=False, sort_keys=True)
    return str(crash)

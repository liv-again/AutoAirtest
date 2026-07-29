"""受控设备执行工作流。"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from autoairtest.models import (
    ActionResult,
    ActionRiskLevel,
    ActionStatus,
    ExecutionPlan,
    ExecutionTrace,
    PlanAction,
    PlanAmendment,
    dataclass_to_dict,
)
from autoairtest.tools.airtest_adapter import AirtestAdapter
from autoairtest.tools.ocr_adapter import OCRAdapter
from autoairtest.tools.poco_adapter import PocoAdapter
from .locator import Locator, ocr_match, valid_bounds, write_ocr_result
from .risk_policy import RiskPolicy
from .stability import PageStabilityWaiter


class DeviceWorkflow:
    """通过 Airtest/Poco 适配器执行 ExecutionPlan。

    该类不直接依赖真实第三方 API，所有设备能力都从适配器进入，方便离线测试和后续 MCP 化。
    """

    def __init__(
        self,
        airtest: Any | None = None,
        poco: Any | None = None,
        ocr: Any | None = None,
        stability_waiter_factory: Any | None = None,
        correction_budget: dict[str, int] | None = None,
        retry_config: dict[str, Any] | None = None,
        app_config: dict[str, Any] | None = None,
        evidence_config: dict[str, Any] | None = None,
        log_collector: Any | None = None,
    ) -> None:
        self.app_config = app_config or {}
        self.airtest = airtest or AirtestAdapter()
        self.poco = poco or PocoAdapter(app_package=str(self.app_config.get("package", "")))
        self.ocr = ocr or OCRAdapter()
        self.stability_waiter_factory = stability_waiter_factory or self._default_stability_waiter
        self.correction_budget = correction_budget or {"low": 3, "medium": 1, "high": 0}
        self.retry_config = {
            "default_max_attempts": 2,
            "default_interval_seconds": 1,
            "poco_dump_max_attempts": 3,
            "poco_dump_interval_seconds": 1,
            "poco_dump_backoff": "fixed",
        } | (retry_config or {})
        self.log_collector = log_collector
        self._device_connected = False
        self._app_started = False
        self.evidence_config = {
            "redact_sensitive_text": True,
            "sensitive_keywords": ["资金账号", "手机号", "资产", "持仓"],
            "redaction_placeholder": "[REDACTED]",
        } | (evidence_config or {})

    def execute_plan(self, plan: ExecutionPlan, case_dir: str | Path) -> list[ActionResult]:
        root = Path(case_dir)
        (root / "screenshots").mkdir(parents=True, exist_ok=True)
        (root / "element_summaries").mkdir(parents=True, exist_ok=True)
        (root / "ocr").mkdir(parents=True, exist_ok=True)
        results: list[ActionResult] = []
        traces: list[ExecutionTrace] = []
        amendments: list[PlanAmendment] = []

        setup = self._prepare_device()
        _write_json(root / "device_setup.json", setup)
        if setup.get("status") == "blocked":
            results, traces = self._setup_blocked_results(plan, setup)
            _write_json(root / "execution_trace.json", traces)
            return results

        for index, action in enumerate(plan.actions, start=1):
            action_result, trace, amendment = self._execute_action(index, action, root)
            action_result = self._check_action_crashes(index, action_result, root)
            results.append(action_result)
            traces.append(trace)
            if amendment:
                amendments.append(amendment)
        _write_json(root / "execution_trace.json", traces)
        if amendments:
            _write_json(root / "plan_amendments.json", amendments)
        return results

    def _execute_action(
        self,
        index: int,
        action: PlanAction,
        root: Path,
    ) -> tuple[ActionResult, ExecutionTrace, PlanAmendment | None]:
        before_screenshot = f"screenshots/{index:03d}_before_{action.action_id}.png"
        after_screenshot = f"screenshots/{index:03d}_after_{action.action_id}.png"
        before_summary = f"element_summaries/{index:03d}_before_{action.action_id}.json"
        after_summary = f"element_summaries/{index:03d}_after_{action.action_id}.json"
        after_evidence: list[str] = []
        correction_step: dict[str, Any] | None = None
        normalized_target = action.target
        candidate_elements: list[dict[str, Any]] = []
        selected_element: dict[str, Any] | None = None

        before_snapshot = self._snapshot_with_retry(str(root / before_screenshot))
        before_dump = self._dump_with_retry()
        self._write_element_summary(root / before_summary, before_dump)
        candidate_elements = _candidate_elements(before_dump)
        hierarchy_unreliable = bool(before_dump.get("hierarchy_unreliable")) or before_dump.get("status") == "unavailable"

        if before_snapshot.get("status") == "unavailable":
            action_result = ActionResult(
                action_id=action.action_id,
                status=ActionStatus.SKIPPED_DEVICE_UNAVAILABLE,
                locator_level=action.preferred_locator,
                target_element=None,
                before_screenshot=before_screenshot,
                after_screenshot="",
                element_summary_before=before_summary,
                element_summary_after="",
                notes=["Airtest/Poco execution is unavailable in current environment."],
            )
            return action_result, _trace(
                index,
                action,
                normalized_target,
                candidate_elements,
                selected_element,
                "Device evidence unavailable before interaction.",
                [before_screenshot, before_summary],
                after_evidence,
                correction_step,
            ), None

        login_detection = _detect_login_page(before_dump)
        if login_detection:
            action_result = ActionResult(
                action_id=action.action_id,
                status=ActionStatus.BLOCKED,
                locator_level=action.preferred_locator,
                target_element=None,
                before_screenshot=before_screenshot,
                after_screenshot="",
                element_summary_before=before_summary,
                element_summary_after="",
                notes=["Login state is not prepared; manual login is required before running this case."],
            )
            return action_result, _trace(
                index,
                action,
                normalized_target,
                candidate_elements,
                selected_element,
                f"login_page_detected: {', '.join(login_detection)}",
                [before_screenshot, before_summary],
                after_evidence,
                correction_step,
            ), None

        if action.action_risk_level == ActionRiskLevel.HIGH:
            action_result = ActionResult(
                action_id=action.action_id,
                status=ActionStatus.BLOCKED,
                locator_level=action.preferred_locator,
                target_element=None,
                before_screenshot=before_screenshot,
                after_screenshot="",
                element_summary_before=before_summary,
                element_summary_after="",
                notes=["High-risk action requires human confirmation before device interaction."],
            )
            return action_result, _trace(
                index,
                action,
                normalized_target,
                candidate_elements,
                selected_element,
                "High-risk action blocked before device interaction.",
                [before_screenshot, before_summary],
                after_evidence,
                correction_step,
            ), None

        amendment = None
        if hierarchy_unreliable:
            action_response, correction_step = self._perform_ocr_degraded_action(action, before_screenshot, index, root)
        else:
            action_response, normalized_target, correction_step, amendment = self._perform_action(
                action,
                before_dump,
                before_summary,
                before_screenshot,
                index,
                root,
            )
        selected_element = {"target": normalized_target, "response": action_response}
        before_evidence = [before_screenshot, before_summary]
        if action_response.get("ocr_evidence"):
            before_evidence.append(str(action_response["ocr_evidence"]))
        wait_result = self.stability_waiter_factory().wait()
        after_snapshot = self._snapshot_with_retry(str(root / after_screenshot))
        after_dump = self._dump_with_retry()
        no_response_retry = False
        page_evidence_unchanged = _should_block_or_retry_no_response(
            action,
            action_response,
            correction_step,
            before_dump,
            after_dump,
        )

        if page_evidence_unchanged and self._default_max_attempts() > 1:
            retry_response, normalized_target, _, _ = self._perform_action(
                action,
                after_dump,
                before_summary,
                before_screenshot,
                index,
                root,
            )
            action_response = retry_response
            selected_element = {"target": normalized_target, "response": action_response}
            correction_step = {
                "type": "action_retry",
                "attempt": 2,
                "target": action.target,
                "reason": "page_evidence_unchanged",
                "risk_level": action.action_risk_level.value,
            }
            no_response_retry = True
            wait_result = self.stability_waiter_factory().wait()
            after_snapshot = self._snapshot_with_retry(str(root / after_screenshot))
            after_dump = self._dump_with_retry()
            page_evidence_unchanged = _page_evidence_unchanged(before_dump, after_dump)
        self._write_element_summary(root / after_summary, after_dump)
        after_evidence = [after_summary]
        if after_snapshot.get("status") != "unavailable":
            after_evidence.insert(0, after_screenshot)

        if action_response.get("status") == "success" and not page_evidence_unchanged:
            status = ActionStatus.SUCCESS
        elif page_evidence_unchanged and action.intent == "navigate" and action_response.get("status") == "success":
            status = ActionStatus.SUCCESS
        elif page_evidence_unchanged:
            status = ActionStatus.BLOCKED
        else:
            status = ActionStatus.FAILED
        action_notes: list[str] = []
        if status == ActionStatus.SUCCESS and page_evidence_unchanged:
            action_notes.append(f"navigation target '{action.target}' clicked but page unchanged; treating as success.")
        action_notes.append(f"page_stability={wait_result}")
        if status != ActionStatus.SUCCESS:
            if page_evidence_unchanged and no_response_retry:
                action_notes.insert(0, "page_evidence_unchanged_after_retry")
            elif page_evidence_unchanged:
                action_notes.insert(0, "page_evidence_unchanged")
            elif not page_evidence_unchanged:
                action_notes.insert(0, str(action_response.get("reason", "action failed")))
        action_result = ActionResult(
            action_id=action.action_id,
            status=status,
            locator_level=action.preferred_locator,
            target_element=selected_element,
            before_screenshot=before_screenshot,
            after_screenshot=after_screenshot if after_snapshot.get("status") != "unavailable" else "",
            element_summary_before=before_summary,
            element_summary_after=after_summary,
            notes=action_notes,
        )
        if status == ActionStatus.SUCCESS and page_evidence_unchanged:
            action_result.notes.insert(0, f"navigation target '{action.target}' clicked but page unchanged; treating as success.")
        return action_result, _trace(
            index,
            action,
            normalized_target,
            candidate_elements,
            selected_element,
            _execution_rationale(
                status,
                hierarchy_unreliable,
                no_response_retry,
                page_evidence_unchanged,
                selected_element,
            ),
            before_evidence,
            after_evidence,
            correction_step,
        ), amendment

    def _perform_action(
        self,
        action: PlanAction,
        before_dump: dict[str, Any],
        before_summary: str,
        before_screenshot: str,
        index: int,
        root: Path,
    ) -> tuple[dict[str, Any], str, dict[str, Any] | None, PlanAmendment | None]:
        if action.intent == "observe":
            return {"status": "success", "source": "observe", "target": action.target}, action.target, None, None
        if action.intent in {"swipe", "scroll"}:
            start, end = _swipe_points(action.target)
            response = self.airtest.swipe(start, end) | {"source": "airtest_swipe"}
            return response, action.target, None, None
        if action.intent in {"text", "input"}:
            input_text = _extract_text_from_description(action.description) or action.target
            resource_id = _first_resource_id_locator(action.locators)
            if resource_id:
                response = self.poco.set_text_resource_id(resource_id, input_text) | {"source": "poco_set_text"}
                if response.get("status") == "success":
                    return response, action.target, None, None
            response = self.airtest.text(input_text) | {"source": "airtest_text"}
            return response, action.target, None, None
        if action.intent in {"keyevent", "back"}:
            key = "BACK" if action.intent == "back" else action.target
            response = self.airtest.keyevent(key) | {"source": "airtest_keyevent"}
            return response, key, None, None
        if action.intent in {"tap", "click"} or action.preferred_locator.startswith("poco"):
            locator = Locator(self.poco, self.ocr, self.airtest)
            location = locator.locate_and_act(
                action.target,
                str(root / before_screenshot),
                allow_ocr=False,
                locators=action.locators,
            )
            response = location["response"]
            if response.get("status") == "success":
                return response, action.target, None, None
            alias = _navigation_alias(action.target, before_dump)
            if alias and self._correction_budget_for(action) <= 0:
                return response, action.target, None, None
            if alias:
                alias_location = locator.locate_and_act(
                    alias["resolved_target"],
                    str(root / before_screenshot),
                    allow_ocr=False,
                )
                alias_response = alias_location["response"]
                if alias_response.get("status") == "success":
                    correction_step = {
                        "type": "navigation_alias",
                        "attempt": 1,
                        "original_target": action.target,
                        "resolved_target": alias["resolved_target"],
                        "risk_level": action.action_risk_level.value,
                    }
                    amendment = PlanAmendment(
                        amendment_id=f"pa{index}",
                        action_id=action.action_id,
                        original_target=action.target,
                        resolved_target=alias["resolved_target"],
                        reason="navigation alias matched current UI evidence",
                        matched_skill_rules=alias["matched_skill_rules"],
                        evidence_files=[before_summary],
                    )
                    return alias_response, alias["resolved_target"], correction_step, amendment
            if self._correction_budget_for(action) <= 0:
                return response, action.target, None, None
            fallback = self._locator_fallback(action, before_dump, before_screenshot, index, root)
            fallback_response = fallback["response"]
            if fallback_response.get("status") == "success":
                correction_step = fallback["correction_step"]
                if correction_step:
                    correction_step = correction_step | {
                        "attempt": 1,
                        "risk_level": action.action_risk_level.value,
                    }
                return fallback_response, action.target, correction_step, None
        response = self.airtest.touch(action.target)
        return response, action.target, None, None

    def _prepare_device(self) -> dict[str, Any]:
        if not self._device_connected:
            connect = self.airtest.connect()
            if not _ready_status(connect, {"connected", "success"}):
                return {"status": "blocked", "phase": "connect", "connect": connect}
            self._device_connected = True
        else:
            connect = {"status": "reused", "reason": "device already connected"}

        package = str(self.app_config.get("package", ""))
        activity = str(self.app_config.get("activity", ""))
        if not package:
            return {
                "status": "ready",
                "phase": "prepared",
                "connect": connect,
                "start_app": {"status": "skipped", "reason": "app package not configured"},
            }

        if self._app_started:
            return {
                "status": "ready",
                "phase": "prepared",
                "connect": connect,
                "start_app": {"status": "skipped", "reason": "app already running; continuing from current page"},
            }

        start_app = self._start_app_with_retry(package, activity)
        if not _ready_status(start_app, {"success", "started"}):
            return {"status": "blocked", "phase": "start_app", "connect": connect, "start_app": start_app}
        self._app_started = True
        return {"status": "ready", "phase": "prepared", "connect": connect, "start_app": start_app}

    def _start_app_with_retry(self, package: str, activity: str) -> dict[str, Any]:
        max_attempts = max(1, int(self.retry_config.get("default_max_attempts", 1) or 1))
        interval = max(0.0, float(self.retry_config.get("default_interval_seconds", 0) or 0))
        failures: list[dict[str, Any]] = []
        last_result: dict[str, Any] = {"status": "unavailable", "package": package, "activity": activity}

        for attempt in range(1, max_attempts + 1):
            try:
                result = self.airtest.start_app(package, activity)
            except Exception as exc:  # pragma: no cover - depends on third-party adapter behavior
                result = {
                    "status": "unavailable",
                    "reason": f"start_app raised {type(exc).__name__}: {exc}",
                    "package": package,
                    "activity": activity,
                }
            if not isinstance(result, dict):
                result = {"status": "unavailable", "reason": "start_app returned non-dict"}
            last_result = result
            if _ready_status(result, {"success", "started"}):
                return result | {"attempts": attempt, "previous_failures": failures}
            failures.append(_dump_failure_summary(result))
            if attempt < max_attempts and interval > 0:
                time.sleep(interval)
        return last_result | {"attempts": max_attempts, "previous_failures": failures}

    def _setup_blocked_results(
        self,
        plan: ExecutionPlan,
        setup: dict[str, Any],
    ) -> tuple[list[ActionResult], list[ExecutionTrace]]:
        results: list[ActionResult] = []
        traces: list[ExecutionTrace] = []
        status = ActionStatus.SKIPPED_DEVICE_UNAVAILABLE if setup.get("phase") == "connect" else ActionStatus.BLOCKED
        note = (
            "Airtest/Poco execution is unavailable in current environment."
            if setup.get("phase") == "connect"
            else "App startup failed before device interaction."
        )
        rationale = (
            "Device connection unavailable before interaction."
            if setup.get("phase") == "connect"
            else "App startup failed before interaction."
        )

        for index, action in enumerate(plan.actions, start=1):
            results.append(
                ActionResult(
                    action_id=action.action_id,
                    status=status,
                    locator_level=action.preferred_locator,
                    target_element=None,
                    before_screenshot="",
                    after_screenshot="",
                    element_summary_before="",
                    element_summary_after="",
                    notes=[note],
                )
            )
            traces.append(
                _trace(
                    index,
                    action,
                    action.target,
                    [],
                    None,
                    rationale,
                    ["device_setup.json"],
                    [],
                    None,
                )
            )
        return results, traces

    def navigate_to_home(
        self,
        max_back_presses: int = 10,
        back_interval_seconds: float = 0.8,
        required_texts: list[str] | None = None,
    ) -> dict[str, Any]:
        """按物理返回键直到检测到底部导航栏，确保下一用例从主框架开始。

        检测方式：Poco dump 当前页面可见文本，至少匹配 required_texts 中的 3 个。
        返回 {home_detected, back_presses, last_page_texts}。
        """
        if required_texts is None:
            required_texts = ["首页", "行情", "交易", "理财", "我的"]

        for press_count in range(max_back_presses + 1):
            dump = self.poco.dump()
            visible = [str(item) for item in dump.get("visible_texts", []) if isinstance(item, str)]
            matched = [item for item in visible if item in required_texts]

            if len(matched) >= 3:
                return {
                    "home_detected": True,
                    "back_presses": press_count,
                    "last_page_texts": visible[:30],
                }

            if press_count < max_back_presses:
                self.airtest.keyevent("BACK")
                import time
                time.sleep(back_interval_seconds)

        dump = self.poco.dump()
        visible = [str(item) for item in dump.get("visible_texts", []) if isinstance(item, str)]
        return {
            "home_detected": False,
            "back_presses": max_back_presses,
            "last_page_texts": visible[:30],
        }

    def _perform_ocr_degraded_action(
        self,
        action: PlanAction,
        before_screenshot: str,
        index: int,
        root: Path,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if self._correction_budget_for(action) <= 0:
            return {
                "status": "unavailable",
                "reason": "poco dump unavailable and correction budget exhausted",
                "source": "ocr",
                "query": action.target,
            }, None
        fallback = self._locator_fallback(action, {}, before_screenshot, index, root, use_dump_bounds=False)
        response = fallback["response"]
        if response.get("status") != "success":
            return response, None
        correction_step = fallback["correction_step"] or {}
        return response, correction_step | {
            "attempt": 1,
            "risk_level": action.action_risk_level.value,
            "reason": "poco_dump_unavailable",
        }

    def _default_stability_waiter(self) -> PageStabilityWaiter:
        return PageStabilityWaiter(max_attempts=3, sampler=lambda: _dump_signature(self.poco.dump()))

    def _correction_budget_for(self, action: PlanAction) -> int:
        return RiskPolicy(self.correction_budget).correction_budget(action.action_risk_level)

    def _default_max_attempts(self) -> int:
        return max(1, int(self.retry_config.get("default_max_attempts", 1) or 1))

    def _dump_with_retry(self) -> dict[str, Any]:
        max_attempts = max(1, int(self.retry_config.get("poco_dump_max_attempts", 1) or 1))
        interval = max(0.0, float(self.retry_config.get("poco_dump_interval_seconds", 0) or 0))
        failures: list[dict[str, Any]] = []
        last_dump: dict[str, Any] = {}

        for attempt in range(1, max_attempts + 1):
            try:
                dump = self.poco.dump()
            except Exception as exc:  # pragma: no cover - depends on third-party adapter behavior
                dump = {"status": "unavailable", "reason": f"poco dump raised {type(exc).__name__}: {exc}"}
            if not isinstance(dump, dict):
                dump = {"status": "unavailable", "reason": "poco dump returned non-dict"}
            last_dump = dump
            if dump.get("status") != "unavailable":
                return dump | {"dump_attempts": attempt, "previous_failures": failures}
            failures.append(_dump_failure_summary(dump))
            if attempt < max_attempts and interval > 0:
                time.sleep(interval)
        return last_dump | {
            "dump_attempts": max_attempts,
            "previous_failures": failures,
            "hierarchy_unreliable": True,
        }

    def _snapshot_with_retry(self, filename: str) -> dict[str, Any]:
        max_attempts = max(1, int(self.retry_config.get("default_max_attempts", 1) or 1))
        interval = max(0.0, float(self.retry_config.get("default_interval_seconds", 0) or 0))
        failures: list[dict[str, Any]] = []
        last_snapshot: dict[str, Any] = {"status": "unavailable", "filename": filename}

        for attempt in range(1, max_attempts + 1):
            try:
                snapshot = self.airtest.snapshot(filename)
            except Exception as exc:  # pragma: no cover - depends on third-party adapter behavior
                snapshot = {
                    "status": "unavailable",
                    "reason": f"snapshot raised {type(exc).__name__}: {exc}",
                    "filename": filename,
                }
            if not isinstance(snapshot, dict):
                snapshot = {"status": "unavailable", "reason": "snapshot returned non-dict", "filename": filename}
            last_snapshot = snapshot
            if snapshot.get("status") != "unavailable":
                return snapshot | {"snapshot_attempts": attempt, "previous_failures": failures}
            failures.append(_dump_failure_summary(snapshot))
            if attempt < max_attempts and interval > 0:
                time.sleep(interval)
        return last_snapshot | {"snapshot_attempts": max_attempts, "previous_failures": failures}

    def _write_element_summary(self, path: Path, payload: dict[str, Any]) -> None:
        _write_json(path, _redact_sensitive_text(payload, self.evidence_config))

    def _ocr_fallback(self, action: PlanAction, before_screenshot: str, index: int, root: Path) -> dict[str, Any]:
        return self._locator_fallback(action, {}, before_screenshot, index, root, use_dump_bounds=False)["response"]

    def _locator_fallback(
        self,
        action: PlanAction,
        before_dump: dict[str, Any],
        before_screenshot: str,
        index: int,
        root: Path,
        use_dump_bounds: bool = True,
    ) -> dict[str, Any]:
        ocr_path = f"ocr/{index:03d}_before_{action.action_id}.json"
        locator = Locator(self.poco, self.ocr, self.airtest)
        if use_dump_bounds:
            result = locator.locate_from_dump_and_screenshot(
                action.target,
                before_dump,
                str(root / before_screenshot),
                ocr_evidence_path=ocr_path,
            )
        else:
            result = locator.locate_with_ocr(
                action.target,
                str(root / before_screenshot),
                ocr_evidence_path=ocr_path,
            )
        ocr_result = result.get("ocr_result")
        if isinstance(ocr_result, dict):
            write_ocr_result(root / ocr_path, ocr_result)
        response = result["response"]
        if result.get("ocr_evidence") and response.get("status") == "success":
            response = response | {"ocr_evidence": result["ocr_evidence"]}
        return result | {"response": response}

    def _check_action_crashes(self, index: int, action_result: ActionResult, root: Path) -> ActionResult:
        if self.log_collector is None:
            return action_result
        crash_check = self.log_collector.get_recent_crashes(
            package=str(self.app_config.get("package", "")),
            lines=300,
        )
        crashes = crash_check.get("crashes", [])
        if not crashes:
            return action_result

        crash_record = {
            "index": index,
            "action_id": action_result.action_id,
            "status": crash_check.get("status", ""),
            "crashes": crashes,
        }
        crash_path = root / "action_crashes.json"
        existing: list[dict[str, Any]] = []
        if crash_path.exists():
            payload = json.loads(crash_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                existing = [item for item in payload if isinstance(item, dict)]
        existing.append(crash_record)
        _write_json(crash_path, existing)

        signature_ids = [str(crash.get("signature_id", "")) for crash in crashes if isinstance(crash, dict)]
        return replace(
            action_result,
            status=ActionStatus.BLOCKED,
            notes=[*action_result.notes, f"crash_detected: {', '.join(signature_ids)}"],
        )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dataclass_to_dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dump_signature(dump: dict[str, Any]) -> str:
    visible_texts = dump.get("visible_texts", [])
    if isinstance(visible_texts, list):
        return "|".join(str(item) for item in visible_texts)
    return str(visible_texts)


def _dump_failure_summary(dump: dict[str, Any]) -> dict[str, Any]:
    summary = {"status": str(dump.get("status", "unavailable"))}
    if dump.get("reason"):
        summary["reason"] = str(dump["reason"])
    return summary


def _ready_status(result: dict[str, Any], ready_values: set[str]) -> bool:
    return isinstance(result, dict) and str(result.get("status", "")) in ready_values


def _redact_sensitive_text(value: Any, evidence_config: dict[str, Any]) -> Any:
    if not evidence_config.get("redact_sensitive_text", True):
        return value
    keywords = [str(item) for item in evidence_config.get("sensitive_keywords", []) if str(item)]
    placeholder = str(evidence_config.get("redaction_placeholder", "[REDACTED]"))
    if isinstance(value, dict):
        return {key: _redact_sensitive_text(item, evidence_config) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_sensitive_text(item, evidence_config) for item in value]
    if isinstance(value, str) and any(keyword in value for keyword in keywords):
        return placeholder
    return value


def _page_evidence_unchanged(before_dump: dict[str, Any], after_dump: dict[str, Any]) -> bool:
    if before_dump.get("status") == "unavailable" or after_dump.get("status") == "unavailable":
        return False
    return _dump_signature(before_dump) == _dump_signature(after_dump)


def _should_block_or_retry_no_response(
    action: PlanAction,
    action_response: dict[str, Any],
    correction_step: dict[str, Any] | None,
    before_dump: dict[str, Any],
    after_dump: dict[str, Any],
) -> bool:
    return (
        action.intent in {"tap", "click", "navigate"}
        and action_response.get("status") == "success"
        and correction_step is None
        and int(before_dump.get("dump_attempts", 1) or 1) >= 1
        and _page_evidence_unchanged(before_dump, after_dump)
    )


def _swipe_points(target: Any) -> tuple[Any, Any]:
    if isinstance(target, dict) and "start" in target and "end" in target:
        return target["start"], target["end"]
    direction = str(target).lower()
    if direction in {"up", "向上", "上滑", "向上滑动", "swipe_up"}:
        return (0.5, 0.8), (0.5, 0.2)
    if direction in {"down", "向下", "下滑", "向下滑动", "swipe_down"}:
        return (0.5, 0.2), (0.5, 0.8)
    if direction in {"left", "向左", "左滑", "向左滑动", "swipe_left"}:
        return (0.8, 0.5), (0.2, 0.5)
    if direction in {"right", "向右", "右滑", "向右滑动", "swipe_right"}:
        return (0.2, 0.5), (0.8, 0.5)
    return (0.5, 0.8), (0.5, 0.2)


def _execution_rationale(
    status: ActionStatus,
    hierarchy_unreliable: bool,
    no_response_retry: bool = False,
    page_evidence_unchanged: bool = False,
    selected_element: dict[str, Any] | None = None,
) -> str:
    if selected_element and selected_element.get("response", {}).get("source") == "observe":
        return "observation_only; evidence collected without device interaction."
    if no_response_retry:
        if status == ActionStatus.SUCCESS:
            return "click_no_response_retry; page evidence changed after retry."
        return "click_no_response_retry; page evidence unchanged after retry."
    if page_evidence_unchanged:
        return "page_evidence_unchanged; action blocked without retry budget."
    if hierarchy_unreliable:
        if status == ActionStatus.SUCCESS:
            return "poco_dump_unavailable; OCR fallback executed with screenshot evidence."
        return "poco_dump_unavailable; action failed after OCR fallback."
    return "Poco semantic action executed." if status == ActionStatus.SUCCESS else "Action failed after device call."


def _candidate_elements(dump: dict[str, Any]) -> list[dict[str, Any]]:
    elements = dump.get("elements", [])
    if isinstance(elements, list):
        return [item for item in elements if isinstance(item, dict)]
    visible_texts = dump.get("visible_texts", [])
    if isinstance(visible_texts, list):
        return [{"text": str(item)} for item in visible_texts]
    return []


def _first_resource_id_locator(locators: list[Any]) -> str:
    """从 locators 列表中提取第一个 resource_id 的值，无匹配时返回空串。"""

    for loc in locators:
        if hasattr(loc, "type") and loc.type == "resource_id":
            return str(loc.value) if loc.value else ""
    return ""


_GUIDE_PREFIXES = ("股票代码", "股票名称", "股票简拼", "代码", "名称", "简拼")


def _extract_text_from_description(description: str) -> str:
    """从动作描述中提取要输入的文本。

    取 description 中最后一个"输入"之后的内容，并去掉引导性前缀。
    如"在搜索输入框中输入股票代码600000"→"600000"。
    """

    text = str(description or "")
    idx = text.rfind("输入")
    if idx < 0:
        return ""
    raw = text[idx + 2:].strip()
    for prefix in _GUIDE_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix):].strip()
    return raw


def _navigation_alias(target: str, dump: dict[str, Any]) -> dict[str, Any] | None:
    visible_texts = {str(item) for item in dump.get("visible_texts", []) if str(item)}
    if target == "自选" and "我的自选" in visible_texts:
        return {"resolved_target": "我的自选", "matched_skill_rules": ["navigation_alias.self_selected"]}
    return None


def _detect_login_page(dump: dict[str, Any]) -> list[str]:
    visible_texts = [str(item) for item in dump.get("visible_texts", []) if str(item)]
    keywords = ["登录", "手机号", "验证码", "密码"]
    matched = []
    for keyword in keywords:
        if any(keyword in text for text in visible_texts):
            matched.append(keyword)
    if "登录" in matched and any(item in matched for item in ["手机号", "验证码", "密码"]):
        return matched
    return []


def _ocr_match(target: str, ocr_result: dict[str, Any]) -> dict[str, Any] | None:
    return ocr_match(target, ocr_result)


def _valid_bounds(bounds: Any) -> bool:
    return valid_bounds(bounds)


def _bounds_center(bounds: list[int | float]) -> tuple[int, int]:
    return (int((bounds[0] + bounds[2]) / 2), int((bounds[1] + bounds[3]) / 2))


def _trace(
    index: int,
    action: PlanAction,
    normalized_target: str,
    candidate_elements: list[dict[str, Any]],
    selected_element: dict[str, Any] | None,
    execution_rationale: str,
    before_evidence: list[str],
    after_evidence: list[str],
    correction_step: dict[str, Any] | None,
) -> ExecutionTrace:
    return ExecutionTrace(
        trace_id=f"t{index}",
        trace_type="action",
        action_id=action.action_id,
        planned_target=action.target,
        normalized_target=normalized_target,
        candidate_elements=candidate_elements,
        selected_element=selected_element,
        action_risk_level=action.action_risk_level,
        execution_rationale=execution_rationale,
        before_evidence=before_evidence,
        after_evidence=after_evidence,
        correction_step=correction_step,
    )

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
    if any(
        result.status in {ActionStatus.BLOCKED, ActionStatus.SKIPPED_DEVICE_UNAVAILABLE}
        for result in action_results
    ):
        return RunStatus.BLOCKED
    if any(judgment.preliminary_status == PreliminaryStatus.BLOCKED for judgment in judgments):
        return RunStatus.BLOCKED
    if any(judgment.preliminary_status == PreliminaryStatus.FAIL for judgment in judgments):
        return RunStatus.FAIL_PRELIMINARY
    if any(judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED for judgment in judgments):
        return RunStatus.MANUAL_REQUIRED
    if judgments and all(judgment.preliminary_status == PreliminaryStatus.PASS for judgment in judgments):
        return RunStatus.PASS_PRELIMINARY
    return RunStatus.UNCERTAIN

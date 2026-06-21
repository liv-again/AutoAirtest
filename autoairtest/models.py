"""系统数据模型。

本模块集中定义离线核心中的领域对象，以便测试用例、执行计划、证据、初判结论与
最终运行结果具有一致的数据契约。模型采用不可变 dataclass，强调可序列化、
可复现和便于审计。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any


class SerializableEnum(str, Enum):
    """可 JSON 序列化的字符串枚举基类。"""

    def __str__(self) -> str:
        return self.value


class ActionStatus(SerializableEnum):
    """单个执行动作的状态集合。"""

    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED_DEVICE_UNAVAILABLE = "skipped_device_unavailable"


class PreliminaryStatus(SerializableEnum):
    """验证目标的自动初步判断状态。"""

    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"
    MANUAL_REQUIRED = "manual_required"
    BLOCKED = "blocked"


class RunStatus(SerializableEnum):
    """单条自然语言测试用例的聚合运行状态。"""

    PASS_PRELIMINARY = "pass_preliminary"
    FAIL_PRELIMINARY = "fail_preliminary"
    MANUAL_REQUIRED = "manual_required"
    BLOCKED = "blocked"
    UNCERTAIN = "uncertain"


class ActionRiskLevel(SerializableEnum):
    """执行动作的业务风险等级。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VerificationGoalCategory(SerializableEnum):
    """验证目标的语义类别，用于选择不同的离线判断策略。"""

    PAGE_NAVIGATION = "page_navigation"
    ELEMENT_ORDER = "element_order"
    POPUP_DISPLAY = "popup_display"
    DATA_CORRECTNESS = "data_correctness"
    COLOR_RULE = "color_rule"
    TEXT_PRESENT = "text_present"


@dataclass(frozen=True)
class InterpretationRationale:
    """Planning Agent 对关键自然语言解释给出的结构化依据。"""

    rationale_id: str
    original_expression: str
    normalized_meaning: str
    interpretation_type: str
    confidence: float
    matched_skill_rules: list[str]
    basis: str
    human_review_required: bool


@dataclass(frozen=True)
class NaturalLanguageTestCase:
    """Excel 中一行自然语言测试用例的标准化表示。"""

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
    """执行计划中的单个动作。

    该结构描述“意图、目标与首选定位策略”，而不是具体设备 API 调用。
    """

    action_id: str
    intent: str
    description: str
    target: str
    target_context: str
    preferred_locator: str
    action_risk_level: ActionRiskLevel = ActionRiskLevel.LOW
    interpretation_rationale_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VerificationGoal:
    """从预期结果中拆解出的单个可验证命题。"""

    goal_id: str
    claim: str
    category: VerificationGoalCategory
    expected_entities: list[str]
    evidence_priority: list[str]
    human_review_required: bool
    review_reason: str


@dataclass(frozen=True)
class ExecutionPlan:
    """自然语言测试用例经规划器转换后的结构化执行计划。"""

    case_id: str
    understanding: str
    preconditions: list[dict[str, str]]
    actions: list[PlanAction]
    verification_goals: list[VerificationGoal]
    manual_review_notes: list[str]
    interpretation_rationales: list[InterpretationRationale] = field(default_factory=list)


@dataclass(frozen=True)
class ActionResult:
    """单个动作执行后的证据与状态摘要。"""

    action_id: str
    status: ActionStatus
    locator_level: str
    target_element: dict[str, Any] | None
    before_screenshot: str
    after_screenshot: str
    element_summary_before: str
    element_summary_after: str
    notes: list[str]
    execution_rationale_id: str = ""


@dataclass(frozen=True)
class ExecutionTrace:
    """真实执行过程的追加式审计记录。"""

    trace_id: str
    trace_type: str
    action_id: str
    planned_target: str
    normalized_target: str
    candidate_elements: list[dict[str, Any]]
    selected_element: dict[str, Any] | None
    action_risk_level: ActionRiskLevel
    execution_rationale: str
    before_evidence: list[str]
    after_evidence: list[str]
    correction_step: dict[str, Any] | None


@dataclass(frozen=True)
class PlanAmendment:
    """执行期对原始执行计划的追加式补充，不覆盖原计划。"""

    amendment_id: str
    action_id: str
    original_target: str
    resolved_target: str
    reason: str
    matched_skill_rules: list[str]
    evidence_files: list[str]


@dataclass(frozen=True)
class CrashSignature:
    """崩溃、ANR 或 native crash 的稳定归一签名。"""

    signature_id: str
    kind: str
    exception_class: str
    top_frames_normalized: list[str]
    process: str
    source: str
    first_seen_step: int = 0


@dataclass(frozen=True)
class TestSession:
    """单次运行的顶层会话元数据。"""

    session_id: str
    workflow: str
    started_at: str
    finished_at: str
    app_package: str
    adb_serial: str
    config_snapshot: str
    case_count: int
    status: str
    excel_result_copy: str = ""


@dataclass(frozen=True)
class ReproductionPath:
    """崩溃复现路径及其最小化结果。"""

    crash_id: str
    case_id: str
    original_repro_path: list[int]
    minimized_repro_path: list[int]
    minimized_confidence: float


@dataclass(frozen=True)
class StateGraphModel:
    """运行级页面状态图的可序列化输出模型。"""

    pages: dict[str, Any]
    edges: list[dict[str, Any]]


@dataclass(frozen=True)
class PreliminaryJudgment:
    """系统在人工复核前给出的初步判断。

    注意：该判断不是行情数据正确性的最终裁决。
    """

    goal_id: str
    preliminary_status: PreliminaryStatus
    confidence: float
    basis: str
    evidence_files: list[str]
    human_review_required: bool
    review_reason: str
    manual_review_reason: str = ""
    structured_details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    """单条测试用例完整执行后的聚合结果。"""

    case_id: str
    run_status: RunStatus
    started_at: str
    finished_at: str
    action_results: list[ActionResult]
    preliminary_judgments: list[PreliminaryJudgment]
    evidence_dir: str
    summary: str


def dataclass_to_dict(value: Any) -> Any:
    """递归转换 dataclass 与枚举，生成稳定的 JSON 友好结构。"""

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
    """按照风险优先级汇总用例运行状态。

    聚合规则强调保守性：设备不可用或关键动作阻塞优先于验证结论；自动失败优先于
    人工复核；只有全部自动验证通过且无人工复核目标时才给出初步通过。
    """

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

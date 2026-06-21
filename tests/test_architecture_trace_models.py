from autoairtest.models import (
    ActionRiskLevel,
    CrashSignature,
    ExecutionPlan,
    ExecutionTrace,
    InterpretationRationale,
    PlanAmendment,
    ReproductionPath,
    StateGraphModel,
    TestSession,
    dataclass_to_dict,
)


def test_architecture_trace_models_serialize_to_json_friendly_dicts():
    rationale = InterpretationRationale(
        rationale_id="ir1",
        original_expression="自选",
        normalized_meaning="我的自选",
        interpretation_type="navigation_alias",
        confidence=0.92,
        matched_skill_rules=["navigation_alias.self_selected"],
        basis="命中导航别名规则。",
        human_review_required=False,
    )
    trace = ExecutionTrace(
        trace_id="t1",
        trace_type="action",
        action_id="a1",
        planned_target="自选",
        normalized_target="我的自选",
        candidate_elements=[],
        selected_element={"text": "我的自选"},
        action_risk_level=ActionRiskLevel.LOW,
        execution_rationale="命中导航别名规则并匹配底部导航。",
        before_evidence=["before.json"],
        after_evidence=["after.json"],
        correction_step=None,
    )
    amendment = PlanAmendment(
        amendment_id="pa1",
        action_id="a1",
        original_target="自选",
        resolved_target="我的自选",
        reason="UI 展示为我的自选。",
        matched_skill_rules=["navigation_alias.self_selected"],
        evidence_files=["after.json"],
    )

    result = dataclass_to_dict({"rationale": rationale, "trace": trace, "amendment": amendment})

    assert result["rationale"]["normalized_meaning"] == "我的自选"
    assert result["trace"]["action_risk_level"] == "low"
    assert result["amendment"]["resolved_target"] == "我的自选"


def test_crash_signature_serializes_stable_contract():
    signature = CrashSignature(
        signature_id="abc123",
        kind="java",
        exception_class="java.lang.IllegalStateException",
        top_frames_normalized=["com.example.Main.onCreate"],
        process="com.example.app",
        source="logcat",
        first_seen_step=2,
    )

    assert dataclass_to_dict(signature)["first_seen_step"] == 2


def test_execution_plan_has_understanding_and_manual_review_notes():
    plan = ExecutionPlan(
        case_id="TC_1",
        understanding="进入行情页并检查国内指数顺序",
        preconditions=[],
        actions=[],
        verification_goals=[],
        manual_review_notes=["Rule-based offline plan; no Python code generated."],
    )

    assert plan.understanding.startswith("进入行情页")
    assert plan.manual_review_notes == ["Rule-based offline plan; no Python code generated."]


def test_test_session_contract_serializes():
    session = TestSession(
        session_id="20260621-001",
        workflow="excel_case_run",
        started_at="2026-06-21T00:00:00",
        finished_at="",
        app_package="com.example",
        adb_serial="ABC123",
        config_snapshot="config.resolved.json",
        case_count=7,
        status="running",
    )

    assert dataclass_to_dict(session)["case_count"] == 7
    assert dataclass_to_dict(session)["excel_result_copy"] == ""


def test_reproduction_path_and_state_graph_model_serialize():
    reproduction = ReproductionPath(
        crash_id="c1",
        case_id="TC_1",
        original_repro_path=[1, 2, 3],
        minimized_repro_path=[1, 3],
        minimized_confidence=0.75,
    )
    graph = StateGraphModel(
        pages={"p1": {"summary": "行情"}},
        edges=[{"from": "p1", "action": "a1", "to": "p2", "case_id": "TC_1"}],
    )

    assert dataclass_to_dict(reproduction)["minimized_repro_path"] == [1, 3]
    assert dataclass_to_dict(graph)["pages"]["p1"]["summary"] == "行情"

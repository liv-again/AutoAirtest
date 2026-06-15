from autoairtest.models import (
    ActionRiskLevel,
    ExecutionTrace,
    InterpretationRationale,
    PlanAmendment,
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

"""离线验证器。

验证器基于结构化界面证据给出初步判断。它优先处理可离线判断的文本顺序和文本存在性，
并对行情数据正确性等业务判断保持人工复核边界。
"""

from __future__ import annotations

from typing import Any

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
    """逐一验证执行计划中的验证目标。"""

    return [_verify_goal(goal, evidence) for goal in goals]


def _verify_goal(goal: VerificationGoal, evidence: dict[str, object]) -> PreliminaryJudgment:
    """根据目标类别选择具体的离线验证策略。"""

    if goal.human_review_required:
        manual_review_reason = _manual_review_reason_for_goal(goal)
        structured_details = {"category": manual_review_reason} if manual_review_reason else {}
        structured_details |= _llm_observation_details(goal, evidence, manual_review_reason)
        # 人工复核目标不被自动判定为通过，避免把初判误写成最终结论。
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.MANUAL_REQUIRED,
            confidence=0.0,
            basis=f"{goal.claim} cannot be finalized automatically in MVP.",
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=True,
            review_reason=goal.review_reason,
            manual_review_reason=manual_review_reason,
            structured_details=structured_details,
        )

    visible_texts, evidence_source = _text_evidence(evidence)
    if goal.category == VerificationGoalCategory.ELEMENT_ORDER:
        conflict = _conflicting_order_evidence(goal, evidence)
        if conflict:
            return _conflicting_evidence_judgment(goal, evidence, conflict)
        return _verify_order(goal, visible_texts, evidence, evidence_source)
    if goal.category in {
        VerificationGoalCategory.PAGE_NAVIGATION,
        VerificationGoalCategory.POPUP_DISPLAY,
        VerificationGoalCategory.TEXT_PRESENT,
    }:
        conflict = _conflicting_text_presence_evidence(goal, evidence)
        if conflict:
            return _conflicting_evidence_judgment(goal, evidence, conflict)
        return _verify_text_presence(goal, visible_texts, evidence, evidence_source)

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
    evidence_source: str,
) -> PreliminaryJudgment:
    """验证期望文本序列是否按给定顺序出现在界面证据中。"""

    missing = [expected for expected in goal.expected_entities if expected not in visible_texts]
    unexpected = [text for text in visible_texts if text not in goal.expected_entities]
    structured_details = {
        "expected": goal.expected_entities,
        "observed": visible_texts,
        "missing": missing,
        "unexpected": unexpected,
        "evidence_source": evidence_source,
    }
    if missing or unexpected:
        structured_details |= _llm_observation_details(goal, evidence, "verification_evidence_gap")
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.MANUAL_REQUIRED,
            confidence=0.0,
            basis=(
                "Order evidence does not exactly match the expected sequence; "
                f"missing={missing}, unexpected={unexpected}."
            ),
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=True,
            review_reason="verification_evidence_gap",
            manual_review_reason="verification_evidence_gap",
            structured_details=structured_details,
        )

    positions: list[int] = []
    for expected in goal.expected_entities:
        positions.append(visible_texts.index(expected))

    passed = positions == sorted(positions)
    return PreliminaryJudgment(
        goal_id=goal.goal_id,
        preliminary_status=PreliminaryStatus.PASS if passed else PreliminaryStatus.FAIL,
        confidence=0.82 if passed else 0.88,
        basis=f"Observed order positions: {positions}",
        evidence_files=list(evidence.get("evidence_files", [])),
        human_review_required=False,
        review_reason="",
        structured_details=structured_details | {"positions": positions},
    )


def _verify_text_presence(
    goal: VerificationGoal,
    visible_texts: list[str],
    evidence: dict[str, object],
    evidence_source: str,
) -> PreliminaryJudgment:
    """验证页面跳转、弹框或普通文本目标是否具有文本证据支持。"""

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
        structured_details={"evidence_source": evidence_source} if status == PreliminaryStatus.PASS else {},
    )


def _manual_review_reason_for_goal(goal: VerificationGoal) -> str:
    if goal.category == VerificationGoalCategory.DATA_CORRECTNESS:
        return "data_correctness"
    if goal.category == VerificationGoalCategory.COLOR_RULE:
        return "color_rule"
    return goal.review_reason


def _text_evidence(evidence: dict[str, object]) -> tuple[list[str], str]:
    visible_texts = [str(item) for item in evidence.get("visible_texts", []) if str(item)]
    if visible_texts:
        return visible_texts, "poco_tree"
    ocr_texts = [str(item) for item in evidence.get("ocr_texts", []) if str(item)]
    if ocr_texts:
        return ocr_texts, "ocr_text"
    return [], "none"


def _conflicting_order_evidence(goal: VerificationGoal, evidence: dict[str, object]) -> dict[str, Any]:
    poco_texts = [str(item) for item in evidence.get("visible_texts", []) if str(item)]
    ocr_texts = [str(item) for item in evidence.get("ocr_texts", []) if str(item)]
    if not poco_texts or not ocr_texts:
        return {}

    poco_status = _order_status(goal.expected_entities, poco_texts)
    ocr_status = _order_status(goal.expected_entities, ocr_texts)
    if poco_status == ocr_status:
        return {}
    return {
        "expected": goal.expected_entities,
        "poco_observed": poco_texts,
        "ocr_observed": ocr_texts,
        "poco_status": poco_status,
        "ocr_status": ocr_status,
    }


def _conflicting_text_presence_evidence(goal: VerificationGoal, evidence: dict[str, object]) -> dict[str, Any]:
    poco_texts = [str(item) for item in evidence.get("visible_texts", []) if str(item)]
    ocr_texts = [str(item) for item in evidence.get("ocr_texts", []) if str(item)]
    if not poco_texts or not ocr_texts:
        return {}

    expected = goal.expected_entities or [goal.claim]
    poco_status = _text_presence_status(expected, poco_texts)
    ocr_status = _text_presence_status(expected, ocr_texts)
    if poco_status == ocr_status:
        return {}
    return {
        "expected": expected,
        "poco_observed": poco_texts,
        "ocr_observed": ocr_texts,
        "poco_status": poco_status,
        "ocr_status": ocr_status,
    }


def _order_status(expected_entities: list[str], observed_texts: list[str]) -> str:
    missing = [expected for expected in expected_entities if expected not in observed_texts]
    unexpected = [text for text in observed_texts if text not in expected_entities]
    if missing or unexpected:
        return "gap"
    positions = [observed_texts.index(expected) for expected in expected_entities]
    return "pass" if positions == sorted(positions) else "fail"


def _text_presence_status(expected_entities: list[str], observed_texts: list[str]) -> str:
    haystack = " ".join(observed_texts)
    return "pass" if any(item and item in haystack for item in expected_entities) else "uncertain"


def _conflicting_evidence_judgment(
    goal: VerificationGoal,
    evidence: dict[str, object],
    structured_details: dict[str, Any],
) -> PreliminaryJudgment:
    structured_details |= _llm_observation_details(goal, evidence, "conflicting_evidence")
    return PreliminaryJudgment(
        goal_id=goal.goal_id,
        preliminary_status=PreliminaryStatus.MANUAL_REQUIRED,
        confidence=0.0,
        basis="Poco and OCR evidence disagree; human review is required.",
        evidence_files=list(evidence.get("evidence_files", [])),
        human_review_required=True,
        review_reason="conflicting_evidence",
        manual_review_reason="conflicting_evidence",
        structured_details=structured_details,
    )


def _llm_observation_details(
    goal: VerificationGoal,
    evidence: dict[str, object],
    manual_review_reason: str,
) -> dict[str, Any]:
    """用可注入 LLM Client 生成人工复核观察摘要，不改变初步裁决状态。"""

    if not evidence.get("llm_preliminary_judgment", False):
        return {}
    client = evidence.get("llm_client")
    if client is None or not hasattr(client, "json_call"):
        return {}

    visible_texts, evidence_source = _text_evidence(evidence)
    prompt = (
        "你是移动 App 测试结果初判器。只生成观察摘要，不要给最终通过结论。\n"
        f"验证目标: {goal.claim}\n"
        f"目标类别: {goal.category.value}\n"
        f"人工复核原因: {manual_review_reason}\n"
        f"证据来源: {evidence_source}\n"
        f"可见文本: {visible_texts}\n"
        f"证据文件: {list(evidence.get('evidence_files', []))}"
    )
    schema = {"type": "object", "required": ["observation_summary", "manual_review_reason"]}
    result = client.json_call(prompt, schema)
    status = str(result.get("status", "unknown"))
    details: dict[str, Any] = {"llm_status": status}
    if status == "success":
        data = result.get("data", {})
        if isinstance(data, dict):
            details["llm_observation_summary"] = str(data.get("observation_summary", ""))
            details["llm_manual_review_reason"] = str(data.get("manual_review_reason", ""))
        details["llm_attempts"] = int(result.get("attempts", 0) or 0)
    elif status != "unavailable":
        details["llm_reason"] = str(result.get("reason", ""))
    return details

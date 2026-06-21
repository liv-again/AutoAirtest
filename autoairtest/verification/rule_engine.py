"""离线验证规则引擎。"""

from __future__ import annotations

from typing import Any

from autoairtest.models import (
    PreliminaryJudgment,
    PreliminaryStatus,
    VerificationGoal,
    VerificationGoalCategory,
)
from autoairtest.verification.judgment_policy import JudgmentPolicy


class RuleEngine:
    """基于结构化界面证据对单个验证目标给出初判。"""

    def __init__(self, policy: JudgmentPolicy | None = None) -> None:
        self.policy = policy or JudgmentPolicy()

    def verify(self, goal: VerificationGoal, evidence: dict[str, object]) -> PreliminaryJudgment:
        if goal.human_review_required:
            return self._manual_goal_judgment(goal, evidence)

        visible_texts, evidence_source = self._text_evidence(evidence)
        if goal.category == VerificationGoalCategory.ELEMENT_ORDER:
            conflict = self._conflicting_order_evidence(goal, evidence)
            if conflict:
                return self._conflicting_evidence_judgment(goal, evidence, conflict)
            return self._verify_order(goal, visible_texts, evidence, evidence_source)
        if goal.category in {
            VerificationGoalCategory.PAGE_NAVIGATION,
            VerificationGoalCategory.POPUP_DISPLAY,
            VerificationGoalCategory.TEXT_PRESENT,
        }:
            conflict = self._conflicting_text_presence_evidence(goal, evidence)
            if conflict:
                return self._conflicting_evidence_judgment(goal, evidence, conflict)
            return self._verify_text_presence(goal, visible_texts, evidence, evidence_source)

        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.UNCERTAIN,
            confidence=0.0,
            basis="No offline verifier exists for this goal category.",
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=False,
            review_reason="",
        )

    def _manual_goal_judgment(
        self,
        goal: VerificationGoal,
        evidence: dict[str, object],
    ) -> PreliminaryJudgment:
        manual_review_reason = self.policy.manual_review_reason_for_goal(goal)
        structured_details = {"category": manual_review_reason} if manual_review_reason else {}
        structured_details |= self._llm_observation_details(goal, evidence, manual_review_reason)
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

    def _verify_order(
        self,
        goal: VerificationGoal,
        visible_texts: list[str],
        evidence: dict[str, object],
        evidence_source: str,
    ) -> PreliminaryJudgment:
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
            structured_details |= self._llm_observation_details(goal, evidence, "verification_evidence_gap")
            return self.policy.manual_required(
                goal,
                evidence,
                reason="verification_evidence_gap",
                basis=(
                    "Order evidence does not exactly match the expected sequence; "
                    f"missing={missing}, unexpected={unexpected}."
                ),
                structured_details=structured_details,
            )

        positions = [visible_texts.index(expected) for expected in goal.expected_entities]
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
        self,
        goal: VerificationGoal,
        visible_texts: list[str],
        evidence: dict[str, object],
        evidence_source: str,
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
            structured_details={"evidence_source": evidence_source} if status == PreliminaryStatus.PASS else {},
        )

    def _text_evidence(self, evidence: dict[str, object]) -> tuple[list[str], str]:
        visible_texts = [str(item) for item in evidence.get("visible_texts", []) if str(item)]
        if visible_texts:
            return visible_texts, "poco_tree"
        ocr_texts = [str(item) for item in evidence.get("ocr_texts", []) if str(item)]
        if ocr_texts:
            return ocr_texts, "ocr_text"
        return [], "none"

    def _conflicting_order_evidence(self, goal: VerificationGoal, evidence: dict[str, object]) -> dict[str, Any]:
        poco_texts = [str(item) for item in evidence.get("visible_texts", []) if str(item)]
        ocr_texts = [str(item) for item in evidence.get("ocr_texts", []) if str(item)]
        if not poco_texts or not ocr_texts:
            return {}

        poco_status = self._order_status(goal.expected_entities, poco_texts)
        ocr_status = self._order_status(goal.expected_entities, ocr_texts)
        if poco_status == ocr_status:
            return {}
        return {
            "expected": goal.expected_entities,
            "poco_observed": poco_texts,
            "ocr_observed": ocr_texts,
            "poco_status": poco_status,
            "ocr_status": ocr_status,
        }

    def _conflicting_text_presence_evidence(
        self,
        goal: VerificationGoal,
        evidence: dict[str, object],
    ) -> dict[str, Any]:
        poco_texts = [str(item) for item in evidence.get("visible_texts", []) if str(item)]
        ocr_texts = [str(item) for item in evidence.get("ocr_texts", []) if str(item)]
        if not poco_texts or not ocr_texts:
            return {}

        expected = goal.expected_entities or [goal.claim]
        poco_status = self._text_presence_status(expected, poco_texts)
        ocr_status = self._text_presence_status(expected, ocr_texts)
        if poco_status == ocr_status:
            return {}
        return {
            "expected": expected,
            "poco_observed": poco_texts,
            "ocr_observed": ocr_texts,
            "poco_status": poco_status,
            "ocr_status": ocr_status,
        }

    def _order_status(self, expected_entities: list[str], observed_texts: list[str]) -> str:
        missing = [expected for expected in expected_entities if expected not in observed_texts]
        unexpected = [text for text in observed_texts if text not in expected_entities]
        if missing or unexpected:
            return "gap"
        positions = [observed_texts.index(expected) for expected in expected_entities]
        return "pass" if positions == sorted(positions) else "fail"

    def _text_presence_status(self, expected_entities: list[str], observed_texts: list[str]) -> str:
        haystack = " ".join(observed_texts)
        return "pass" if any(item and item in haystack for item in expected_entities) else "uncertain"

    def _conflicting_evidence_judgment(
        self,
        goal: VerificationGoal,
        evidence: dict[str, object],
        structured_details: dict[str, Any],
    ) -> PreliminaryJudgment:
        structured_details |= self._llm_observation_details(goal, evidence, "conflicting_evidence")
        return self.policy.manual_required(
            goal,
            evidence,
            reason="conflicting_evidence",
            basis="Poco and OCR evidence disagree; human review is required.",
            structured_details=structured_details,
        )

    def _llm_observation_details(
        self,
        goal: VerificationGoal,
        evidence: dict[str, object],
        manual_review_reason: str,
    ) -> dict[str, Any]:
        if not evidence.get("llm_preliminary_judgment", False):
            return {}
        client = evidence.get("llm_client")
        if client is None or not hasattr(client, "json_call"):
            return {}

        visible_texts, evidence_source = self._text_evidence(evidence)
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

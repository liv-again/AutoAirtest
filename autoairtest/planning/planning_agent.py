"""Planning Agent。"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any

from autoairtest.models import (
    ActionRiskLevel,
    ExecutionPlan,
    InterpretationRationale,
    NaturalLanguageTestCase,
    PlanAction,
    VerificationGoal,
    VerificationGoalCategory,
)
from autoairtest.planning.rule_based_planner import RuleBasedPlanner


class PlanningAgent:
    """优先使用可注入 LLM 规划，失败时回退到规则型 planner。"""

    def __init__(
        self,
        llm_client: Any | None = None,
        rule_based_planner: RuleBasedPlanner | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.rule_based_planner = rule_based_planner or RuleBasedPlanner()
        self.prompt_path = Path(prompt_path) if prompt_path else Path("prompts/planner.md")

    def plan(self, case: NaturalLanguageTestCase) -> ExecutionPlan:
        if self.llm_client is not None and hasattr(self.llm_client, "json_call"):
            llm_plan = self._plan_with_llm(case)
            if llm_plan is not None:
                return llm_plan
        return self.rule_based_planner.plan(case)

    def _plan_with_llm(self, case: NaturalLanguageTestCase) -> ExecutionPlan | None:
        prompt = self._planner_prompt(case)
        result = self.llm_client.json_call(prompt, self._schema())
        if not isinstance(result, dict) or result.get("status") != "success":
            return None
        data = result.get("data")
        if not isinstance(data, dict):
            return None
        try:
            return self._execution_plan_from_dict(data)
        except (KeyError, TypeError, ValueError):
            return None

    def _planner_prompt(self, case: NaturalLanguageTestCase) -> str:
        base_prompt = ""
        if self.prompt_path.exists():
            base_prompt = self.prompt_path.read_text(encoding="utf-8").strip()
        return (
            f"{base_prompt}\n\n"
            "请将以下自然语言测试用例转换为 ExecutionPlan JSON。\n"
            f"case_id: {case.internal_id}\n"
            f"business_module: {case.business_module}\n"
            f"feature_module: {case.feature_module}\n"
            f"operation_description: {case.operation_description}\n"
            f"expected_result: {case.expected_result}\n"
            f"parameters: {case.parameters}"
        ).strip()

    def _schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": [
                "case_id",
                "understanding",
                "preconditions",
                "actions",
                "verification_goals",
                "manual_review_notes",
            ],
        }

    def _execution_plan_from_dict(self, data: dict[str, Any]) -> ExecutionPlan:
        self._require_keys(data, self._schema()["required"])
        actions = [self._action_from_dict(item) for item in self._list(data["actions"])]
        goals = [self._goal_from_dict(item) for item in self._list(data["verification_goals"])]
        rationales = [
            self._rationale_from_dict(item)
            for item in self._list(data.get("interpretation_rationales", []))
        ]
        return ExecutionPlan(
            case_id=str(data["case_id"]),
            understanding=str(data["understanding"]),
            preconditions=[self._dict(item) for item in self._list(data["preconditions"])],
            actions=actions,
            verification_goals=goals,
            manual_review_notes=[str(item) for item in self._list(data["manual_review_notes"])],
            interpretation_rationales=rationales,
        )

    def _action_from_dict(self, data: Any) -> PlanAction:
        item = self._dict(data)
        required = ["action_id", "intent", "description", "target", "target_context", "preferred_locator"]
        self._require_keys(item, required)
        risk = item.get("action_risk_level", ActionRiskLevel.LOW)
        return PlanAction(
            action_id=str(item["action_id"]),
            intent=str(item["intent"]),
            description=str(item["description"]),
            target=str(item["target"]),
            target_context=str(item["target_context"]),
            preferred_locator=str(item["preferred_locator"]),
            action_risk_level=ActionRiskLevel(str(risk)),
            interpretation_rationale_ids=[
                str(value) for value in self._list(item.get("interpretation_rationale_ids", []))
            ],
        )

    def _goal_from_dict(self, data: Any) -> VerificationGoal:
        item = self._dict(data)
        required = [
            "goal_id",
            "claim",
            "category",
            "expected_entities",
            "evidence_priority",
            "human_review_required",
            "review_reason",
        ]
        self._require_keys(item, required)
        return VerificationGoal(
            goal_id=str(item["goal_id"]),
            claim=str(item["claim"]),
            category=VerificationGoalCategory(str(item["category"])),
            expected_entities=[str(value) for value in self._list(item["expected_entities"])],
            evidence_priority=[str(value) for value in self._list(item["evidence_priority"])],
            human_review_required=bool(item["human_review_required"]),
            review_reason=str(item["review_reason"]),
        )

    def _rationale_from_dict(self, data: Any) -> InterpretationRationale:
        item = self._dict(data)
        required = [field.name for field in fields(InterpretationRationale)]
        self._require_keys(item, required)
        return InterpretationRationale(
            rationale_id=str(item["rationale_id"]),
            original_expression=str(item["original_expression"]),
            normalized_meaning=str(item["normalized_meaning"]),
            interpretation_type=str(item["interpretation_type"]),
            confidence=float(item["confidence"]),
            matched_skill_rules=[str(value) for value in self._list(item["matched_skill_rules"])],
            basis=str(item["basis"]),
            human_review_required=bool(item["human_review_required"]),
        )

    def _require_keys(self, data: dict[str, Any], keys: list[str]) -> None:
        missing = [key for key in keys if key not in data]
        if missing:
            raise KeyError(f"Missing planning keys: {missing}")

    def _dict(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError("Expected object")
        return value

    def _list(self, value: Any) -> list[Any]:
        if not isinstance(value, list):
            raise TypeError("Expected list")
        return value

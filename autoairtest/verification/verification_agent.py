"""验证代理。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from autoairtest.models import PreliminaryJudgment, VerificationGoal
from autoairtest.verification.evidence_recollection import EvidenceRecollector
from autoairtest.verification.rule_engine import RuleEngine


@dataclass(frozen=True)
class VerificationResult:
    judgments: list[PreliminaryJudgment]
    recollection_trace: list[dict[str, Any]]


class VerificationAgent:
    """运行规则引擎，并在验证证据缺口时执行受限补采。"""

    def __init__(
        self,
        rule_engine: RuleEngine | None = None,
        recollector: Any | None = None,
        max_recollection_attempts: int = 0,
        initial_judgment_provider: Callable[
            [list[VerificationGoal], dict[str, object]], list[PreliminaryJudgment]
        ]
        | None = None,
        market_code_prefixes: dict[str, list[str]] | None = None,
    ) -> None:
        self.rule_engine = rule_engine or RuleEngine(market_code_prefixes=market_code_prefixes)
        self.recollector = recollector
        self.max_recollection_attempts = max_recollection_attempts
        self.initial_judgment_provider = initial_judgment_provider

    def verify(
        self,
        goals: list[VerificationGoal],
        evidence: dict[str, object],
        case_dir: str | Path | None = None,
    ) -> VerificationResult:
        judgments = self._initial_judgments(goals, evidence)
        if case_dir is None or self.max_recollection_attempts <= 0:
            return VerificationResult(judgments=judgments, recollection_trace=[])

        recollector = self.recollector or EvidenceRecollector(max_attempts=self.max_recollection_attempts)
        goal_by_id = {goal.goal_id: goal for goal in goals}
        recollection_trace: list[dict[str, Any]] = []
        updated_judgments = list(judgments)

        for index, judgment in enumerate(judgments):
            if not self._requires_recollection(judgment):
                continue
            latest_evidence: dict[str, object] = {}
            for attempt in range(1, self.max_recollection_attempts + 1):
                record = recollector.recollect(judgment.goal_id, case_dir, attempt)
                recollection_trace.append(record)
                latest_evidence = self._evidence_from_recollection(record)
            goal = goal_by_id.get(judgment.goal_id)
            if goal is not None and latest_evidence:
                updated_judgments[index] = self.rule_engine.verify(goal, self._merge_evidence(evidence, latest_evidence))

        return VerificationResult(judgments=updated_judgments, recollection_trace=recollection_trace)

    def _initial_judgments(
        self,
        goals: list[VerificationGoal],
        evidence: dict[str, object],
    ) -> list[PreliminaryJudgment]:
        if self.initial_judgment_provider is not None:
            return self.initial_judgment_provider(goals, evidence)
        return [self.rule_engine.verify(goal, evidence) for goal in goals]

    def _requires_recollection(self, judgment: PreliminaryJudgment) -> bool:
        reason = judgment.manual_review_reason or judgment.review_reason
        return judgment.human_review_required and reason == "verification_evidence_gap"

    def _merge_evidence(
        self,
        original: dict[str, object],
        collected: dict[str, object],
    ) -> dict[str, object]:
        merged = dict(original)
        for key in ("visible_texts", "ocr_texts", "evidence_files"):
            if key in collected:
                merged[key] = collected[key]
        return merged

    def _evidence_from_recollection(self, record: dict[str, Any]) -> dict[str, object]:
        evidence: dict[str, object] = {}
        if isinstance(record.get("visible_texts"), list):
            evidence["visible_texts"] = record["visible_texts"]
        if isinstance(record.get("ocr_texts"), list):
            evidence["ocr_texts"] = record["ocr_texts"]
        if isinstance(record.get("evidence_files"), list):
            evidence["evidence_files"] = record["evidence_files"]

        poco = record.get("poco")
        if isinstance(poco, dict) and isinstance(poco.get("visible_texts"), list):
            evidence["visible_texts"] = poco["visible_texts"]
        ocr = record.get("ocr")
        if isinstance(ocr, dict) and isinstance(ocr.get("texts"), list):
            evidence["ocr_texts"] = ocr["texts"]

        files = list(evidence.get("evidence_files", []))
        screenshot = str(record.get("screenshot", ""))
        if screenshot:
            files.append(screenshot)
        if files:
            evidence["evidence_files"] = files
        return evidence

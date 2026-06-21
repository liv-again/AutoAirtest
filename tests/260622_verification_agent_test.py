from autoairtest.models import PreliminaryStatus, VerificationGoal, VerificationGoalCategory
from autoairtest.verification.verification_agent import VerificationAgent


class FakeRecollector:
    def recollect(self, goal_id, case_dir, attempt):
        return {
            "goal_id": goal_id,
            "attempt": attempt,
            "visible_texts": ["A", "B", "C"],
            "evidence_files": ["retry.json"],
        }


def test_verification_agent_recollects_on_evidence_gap(tmp_path):
    goal = VerificationGoal(
        goal_id="v1",
        claim="顺序正确",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["A", "B", "C"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    result = VerificationAgent(recollector=FakeRecollector(), max_recollection_attempts=1).verify(
        [goal],
        {"visible_texts": ["A", "B"], "evidence_files": []},
        tmp_path,
    )

    assert result.judgments[0].preliminary_status in {PreliminaryStatus.PASS, PreliminaryStatus.MANUAL_REQUIRED}
    assert result.recollection_trace[0]["attempt"] == 1

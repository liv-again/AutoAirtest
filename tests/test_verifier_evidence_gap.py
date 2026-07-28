from pathlib import Path

from autoairtest.agents.verifier import verify_goals
from autoairtest.models import PreliminaryStatus, VerificationGoal, VerificationGoalCategory
from autoairtest.verification.rule_engine import RuleEngine

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_order_gap_requires_manual_review_with_structured_details():
    goal = VerificationGoal(
        goal_id="v1",
        claim="A-B-C-D order is shown",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["A", "B", "C", "D"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals([goal], {"visible_texts": ["A", "B", "C"], "evidence_files": ["elements.json"]})

    assert judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED
    assert judgment.manual_review_reason == "verification_evidence_gap"
    assert judgment.structured_details == {
        "expected": ["A", "B", "C", "D"],
        "observed": ["A", "B", "C"],
        "filtered_for_order": ["A", "B", "C"],
        "missing": ["D"],
        "evidence_source": "poco_tree",
    }
    assert "elements.json" in judgment.evidence_files


def test_order_unexpected_entity_requires_manual_review_with_structured_details():
    goal = VerificationGoal(
        goal_id="v1",
        claim="A-B-C-D order is shown",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["A", "B", "C", "D"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals([goal], {"visible_texts": ["A", "B", "C", "E"], "evidence_files": []})

    assert judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED
    assert judgment.manual_review_reason == "verification_evidence_gap"
    assert judgment.structured_details["missing"] == ["D"]
    assert judgment.structured_details["observed"] == ["A", "B", "C", "E"]
    assert judgment.structured_details["filtered_for_order"] == ["A", "B", "C"]
    assert "unexpected" not in judgment.structured_details


def test_data_correctness_uses_structured_manual_review_reason():
    goal = VerificationGoal(
        goal_id="v1",
        claim="行情数据正确性或两端一致性需要人工复核",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=[],
        evidence_priority=["screenshot"],
        human_review_required=True,
        review_reason="market data correctness requires human review",
    )

    [judgment] = verify_goals([goal], {"visible_texts": [], "evidence_files": ["verify.png"]})

    assert judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED
    assert judgment.manual_review_reason == "data_correctness"
    assert judgment.structured_details["category"] == "data_correctness"
    assert "verify.png" in judgment.evidence_files


def test_data_correctness_can_include_llm_observation_without_finalizing_result():
    goal = VerificationGoal(
        goal_id="v1",
        claim="行情数据正确性或两端一致性需要人工复核",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=[],
        evidence_priority=["poco_tree", "screenshot"],
        human_review_required=True,
        review_reason="market data correctness requires human review",
    )
    calls = []

    class FakeLLMClient:
        def json_call(self, prompt, schema, **kwargs):
            calls.append({"prompt": prompt, "schema": schema, **kwargs})
            return {
                "status": "success",
                "data": {
                    "observation_summary": "截图和元素文本中可见科创综指，数值字段需要人工对照。",
                    "manual_review_reason": "data_correctness",
                },
                "attempts": 1,
                "errors": [],
            }

    [judgment] = verify_goals(
        [goal],
        {
            "visible_texts": ["科创综指", "1234.56"],
            "evidence_files": ["screenshots/090_verify.png", "element_summaries/090_verify.json"],
            "llm_client": FakeLLMClient(),
            "llm_preliminary_judgment": True,
        },
    )

    assert judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED
    assert judgment.human_review_required is True
    assert judgment.manual_review_reason == "data_correctness"
    assert judgment.structured_details["llm_observation_summary"] == "截图和元素文本中可见科创综指，数值字段需要人工对照。"
    assert judgment.structured_details["llm_status"] == "success"
    assert calls
    assert calls[0]["schema"]["required"] == ["observation_summary", "manual_review_reason"]
    assert calls[0]["context"] == {
        "stage": "verification",
        "case_id": "",
        "goal_id": "v1",
    }


def test_verifier_uses_stable_prompt_file_before_dynamic_evidence(tmp_path):
    prompt_path = tmp_path / "verifier.md"
    prompt_path.write_text("STABLE VERIFIER CONTRACT", encoding="utf-8")
    calls = []

    class FakeLLMClient:
        def json_call(self, prompt, schema, **kwargs):
            calls.append({"prompt": prompt, "schema": schema, **kwargs})
            return {"status": "unavailable"}

    engine = RuleEngine(prompt_path=prompt_path)
    goal = VerificationGoal(
        goal_id="v1",
        claim="动态目标",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=["科创综指"],
        evidence_priority=["poco_tree"],
        human_review_required=True,
        review_reason="data_correctness",
    )

    engine._llm_observation_details(
        goal,
        {
            "llm_preliminary_judgment": True,
            "llm_client": FakeLLMClient(),
            "case_id": "TC_1",
            "visible_texts": ["动态证据"],
            "evidence_files": ["screen.png"],
        },
        "data_correctness",
    )

    prompt = calls[0]["prompt"]
    assert prompt.startswith("STABLE VERIFIER CONTRACT")
    assert prompt.index("STABLE VERIFIER CONTRACT") < prompt.index("动态目标")
    assert calls[0]["context"] == {
        "stage": "verification",
        "case_id": "TC_1",
        "goal_id": "v1",
    }


def test_verifier_default_prompt_path_does_not_depend_on_current_directory(tmp_path, monkeypatch):
    calls = []

    class FakeLLMClient:
        def json_call(self, prompt, schema, **kwargs):
            calls.append(prompt)
            return {"status": "unavailable"}

    monkeypatch.chdir(tmp_path)
    engine = RuleEngine()
    goal = VerificationGoal(
        goal_id="v1",
        claim="动态目标",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=[],
        evidence_priority=["screenshot"],
        human_review_required=True,
        review_reason="data_correctness",
    )

    engine._llm_observation_details(
        goal,
        {
            "llm_preliminary_judgment": True,
            "llm_client": FakeLLMClient(),
            "visible_texts": [],
            "evidence_files": [],
        },
        "data_correctness",
    )

    assert calls[0].startswith("# Verifier Prompt")


def test_text_presence_can_use_ocr_text_evidence_when_poco_text_is_absent():
    goal = VerificationGoal(
        goal_id="v1",
        claim="进入国内指数列表页",
        category=VerificationGoalCategory.PAGE_NAVIGATION,
        expected_entities=["国内指数"],
        evidence_priority=["poco_tree", "ocr_text"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals(
        [goal],
        {"visible_texts": [], "ocr_texts": ["行情", "国内指数"], "evidence_files": ["ocr/verify.json"]},
    )

    assert judgment.preliminary_status == PreliminaryStatus.PASS
    assert judgment.structured_details["evidence_source"] == "ocr_text"
    assert "ocr/verify.json" in judgment.evidence_files


def test_order_verification_can_use_ocr_text_evidence_when_poco_text_is_absent():
    goal = VerificationGoal(
        goal_id="v1",
        claim="指数顺序正确",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["上证指数", "深证成指", "北证50", "科创综指"],
        evidence_priority=["poco_tree", "ocr_text"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals(
        [goal],
        {
            "visible_texts": [],
            "ocr_texts": ["上证指数", "深证成指", "北证50", "科创综指"],
            "evidence_files": ["ocr/order.json"],
        },
    )

    assert judgment.preliminary_status == PreliminaryStatus.PASS
    assert judgment.structured_details["evidence_source"] == "ocr_text"


def test_order_extra_text_does_not_create_poco_ocr_conflict():
    goal = VerificationGoal(
        goal_id="v1",
        claim="指数顺序正确",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["上证指数", "深证成指", "北证50", "科创综指"],
        evidence_priority=["poco_tree", "ocr_text"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals(
        [goal],
        {
            "visible_texts": ["指数列表", "上证指数", "最新价", "深证成指", "北证50", "科创综指"],
            "ocr_texts": ["上证指数", "深证成指", "北证50", "科创综指"],
            "evidence_files": ["element_summaries/090_verify.json", "ocr/090_verify.json"],
        },
    )

    assert judgment.preliminary_status == PreliminaryStatus.PASS
    assert judgment.manual_review_reason == ""
    assert judgment.structured_details["filtered_for_order"] == [
        "上证指数",
        "深证成指",
        "北证50",
        "科创综指",
    ]


def test_order_duplicate_expected_entity_requires_matching_occurrences():
    goal = VerificationGoal(
        goal_id="v1",
        claim="A-A-B order is shown",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["A", "A", "B"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals(
        [goal],
        {"visible_texts": ["A", "B"], "evidence_files": ["elements.json"]},
    )

    assert judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED
    assert judgment.manual_review_reason == "verification_evidence_gap"
    assert judgment.structured_details["missing"] == ["A"]


def test_order_conflict_between_poco_and_ocr_requires_manual_review():
    goal = VerificationGoal(
        goal_id="v1",
        claim="指数顺序正确",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["上证指数", "深证成指", "北证50", "科创综指"],
        evidence_priority=["poco_tree", "ocr_text"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals(
        [goal],
        {
            "visible_texts": ["上证指数", "深证成指", "北证50", "科创综指"],
            "ocr_texts": ["上证指数", "北证50", "深证成指", "科创综指"],
            "evidence_files": ["element_summaries/090_verify.json", "ocr/090_verify.json"],
        },
    )

    assert judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED
    assert judgment.manual_review_reason == "conflicting_evidence"
    assert judgment.structured_details["poco_observed"] == ["上证指数", "深证成指", "北证50", "科创综指"]
    assert judgment.structured_details["ocr_observed"] == ["上证指数", "北证50", "深证成指", "科创综指"]
    assert judgment.structured_details["poco_status"] == "pass"
    assert judgment.structured_details["ocr_status"] == "fail"


def test_text_presence_conflict_between_poco_and_ocr_requires_manual_review():
    goal = VerificationGoal(
        goal_id="v1",
        claim="进入国内指数列表页",
        category=VerificationGoalCategory.PAGE_NAVIGATION,
        expected_entities=["国内指数"],
        evidence_priority=["poco_tree", "ocr_text"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals(
        [goal],
        {
            "visible_texts": ["行情", "国内指数"],
            "ocr_texts": ["行情", "国际指数"],
            "evidence_files": ["element_summaries/090_verify.json", "ocr/090_verify.json"],
        },
    )

    assert judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED
    assert judgment.manual_review_reason == "conflicting_evidence"
    assert judgment.structured_details["poco_status"] == "pass"
    assert judgment.structured_details["ocr_status"] == "uncertain"

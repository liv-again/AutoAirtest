import json

from autoairtest import orchestrator
from autoairtest.models import NaturalLanguageTestCase


def test_run_offline_writes_interpretation_rationales_json(tmp_path, monkeypatch):
    case = NaturalLanguageTestCase(
        case_id="TC_alias",
        internal_id="TC_alias",
        row_number=2,
        business_module="自选",
        feature_module="顶部指数",
        feature_item="",
        test_purpose="跳转校验",
        priority="high",
        step_name="",
        precondition="",
        operation_description="自选：点击顶部指数",
        parameters="",
        expected_result="弹出指数分时图弹框",
        original_fields={},
    )
    monkeypatch.setattr(orchestrator, "_load_cases_or_dependency_case", lambda config: [case])

    run_dir = orchestrator.run_offline(
        {
            "report": {"output_dir": str(tmp_path), "generate_html": False},
            "input": {"case_filter": ""},
        }
    )

    rationales_path = run_dir / "cases" / "TC_alias" / "interpretation_rationales.json"
    assert rationales_path.exists()
    rationales = json.loads(rationales_path.read_text(encoding="utf-8"))
    assert rationales[0]["original_expression"] == "自选"
    assert rationales[0]["normalized_meaning"] == "我的自选"

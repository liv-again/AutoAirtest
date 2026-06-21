import json

from autoairtest.report.html_report import write_html_report


def test_html_report_includes_session_and_crash_sections(tmp_path):
    (tmp_path / "session_meta.json").write_text(
        json.dumps(
            {
                "session_id": "20260621-103000_smoke",
                "workflow": "excel_case_run",
                "case_count": 1,
                "status": "completed",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "crashes.jsonl").write_text(
        json.dumps(
            {
                "crash_id": "c1",
                "case_id": "TC_crash",
                "step_index": 3,
                "signature": {
                    "signature_id": "abc123",
                    "kind": "java",
                    "exception_class": "java.lang.NullPointerException",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    output = write_html_report(
        tmp_path,
        [
            {
                "case_id": "TC_crash",
                "run_status": "fail_preliminary",
                "summary": "发现崩溃",
                "evidence_dir": "cases/TC_crash",
                "manual_review_reason": "verification_evidence_gap",
            }
        ],
    )

    html = output.read_text(encoding="utf-8")
    assert "20260621-103000_smoke" in html
    assert "excel_case_run" in html
    assert "abc123" in html
    assert "java.lang.NullPointerException" in html
    assert "verification_evidence_gap" in html


def test_html_report_includes_execution_trace_and_plan_amendments(tmp_path):
    case_dir = tmp_path / "cases" / "TC_alias"
    case_dir.mkdir(parents=True)
    (tmp_path / "crashes.jsonl").write_text("", encoding="utf-8")
    (case_dir / "execution_trace.json").write_text(
        json.dumps(
            [
                {
                    "trace_id": "t1",
                    "trace_type": "action",
                    "action_id": "a_alias",
                    "planned_target": "自选",
                    "normalized_target": "我的自选",
                    "action_risk_level": "low",
                    "execution_rationale": "Poco semantic action executed.",
                    "correction_step": {"type": "navigation_alias"},
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (case_dir / "plan_amendments.json").write_text(
        json.dumps(
            [
                {
                    "amendment_id": "pa1",
                    "action_id": "a_alias",
                    "original_target": "自选",
                    "resolved_target": "我的自选",
                    "reason": "navigation alias matched current UI evidence",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output = write_html_report(
        tmp_path,
        [
            {
                "case_id": "TC_alias",
                "run_status": "pass_preliminary",
                "summary": "别名修正后执行",
                "evidence_dir": "cases/TC_alias",
                "manual_review_reason": "",
            }
        ],
    )

    html = output.read_text(encoding="utf-8")
    assert "Execution Trace" in html
    assert "Plan Amendments" in html
    assert "a_alias" in html
    assert "自选" in html
    assert "我的自选" in html
    assert "navigation_alias" in html


def test_html_report_includes_evidence_recollection_trace(tmp_path):
    case_dir = tmp_path / "cases" / "TC_recollect"
    case_dir.mkdir(parents=True)
    (tmp_path / "crashes.jsonl").write_text("", encoding="utf-8")
    (case_dir / "execution_trace.json").write_text(
        json.dumps(
            [
                {
                    "trace_id": "t1",
                    "trace_type": "evidence_recollection",
                    "action_id": "g_order",
                    "planned_target": "verification_evidence_gap",
                    "normalized_target": "refresh_current_screen_evidence",
                    "action_risk_level": "low",
                    "correction_step": {"type": "evidence_recollection"},
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output = write_html_report(
        tmp_path,
        [
            {
                "case_id": "TC_recollect",
                "run_status": "manual_required",
                "summary": "证据补采后仍需复核",
                "evidence_dir": "cases/TC_recollect",
                "manual_review_reason": "verification_evidence_gap",
            }
        ],
    )

    html = output.read_text(encoding="utf-8")
    assert "Trace Type" in html
    assert "evidence_recollection" in html
    assert "verification_evidence_gap" in html
    assert "refresh_current_screen_evidence" in html


def test_html_report_groups_cases_by_manual_review_reason(tmp_path):
    (tmp_path / "crashes.jsonl").write_text("", encoding="utf-8")

    output = write_html_report(
        tmp_path,
        [
            {
                "case_id": "TC_data",
                "run_status": "manual_required",
                "summary": "数据正确性需要人工复核",
                "evidence_dir": "cases/TC_data",
                "manual_review_reason": "data_correctness",
            },
            {
                "case_id": "TC_color",
                "run_status": "manual_required",
                "summary": "颜色规则需要人工复核",
                "evidence_dir": "cases/TC_color",
                "manual_review_reason": "color_rule",
            },
            {
                "case_id": "TC_gap",
                "run_status": "manual_required",
                "summary": "证据不足",
                "evidence_dir": "cases/TC_gap",
                "manual_review_reason": "data_correctness",
            },
            {
                "case_id": "TC_pass",
                "run_status": "pass_preliminary",
                "summary": "初步通过",
                "evidence_dir": "cases/TC_pass",
                "manual_review_reason": "",
            },
        ],
    )

    html = output.read_text(encoding="utf-8")
    assert "Manual Review Clusters" in html
    assert "data_correctness (2)" in html
    assert "color_rule (1)" in html
    assert "TC_data" in html
    assert "TC_gap" in html
    assert "TC_color" in html

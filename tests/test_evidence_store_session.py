import json

from autoairtest.tools.evidence_store import EvidenceStore


def test_evidence_store_initializes_session_files(tmp_path):
    store = EvidenceStore(tmp_path, "20260621-103000_smoke")

    store.write_session_meta({"session_id": "20260621-103000_smoke", "workflow": "excel_case_run"})
    store.write_config_snapshot({"report": {"output_dir": str(tmp_path)}})
    store.initialize_jsonl("steps.jsonl")
    store.initialize_jsonl("crashes.jsonl")
    store.write_run_json("state_graph.json", {"pages": {}, "edges": []})

    assert json.loads((store.root / "session_meta.json").read_text(encoding="utf-8"))["workflow"] == "excel_case_run"
    assert (store.root / "config.resolved.json").exists()
    assert (store.root / "steps.jsonl").read_text(encoding="utf-8") == ""
    assert (store.root / "crashes.jsonl").read_text(encoding="utf-8") == ""
    assert json.loads((store.root / "state_graph.json").read_text(encoding="utf-8")) == {"pages": {}, "edges": []}


def test_evidence_store_appends_jsonl_records(tmp_path):
    store = EvidenceStore(tmp_path, "20260621-103000_smoke")

    store.append_jsonl("steps.jsonl", {"index": 1, "case_id": "TC_1"})
    store.append_jsonl("steps.jsonl", {"index": 2, "case_id": "TC_2"})

    lines = (store.root / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["index"] for line in lines] == [1, 2]


def test_evidence_store_writes_case_artifacts_with_redaction(tmp_path):
    store = EvidenceStore(tmp_path, "session")
    evidence_config = {
        "redact_sensitive_text": True,
        "sensitive_keywords": ["资金账号"],
        "redaction_placeholder": "[REDACTED]",
    }

    path = store.write_element_summary(
        "TC_1",
        "001_before_a1.json",
        {"visible_texts": ["资金账号 123456", "行情"]},
        evidence_config,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path.relative_to(store.root).as_posix() == "cases/TC_1/element_summaries/001_before_a1.json"
    assert payload["visible_texts"] == ["[REDACTED]", "行情"]


def test_evidence_store_writes_ocr_result(tmp_path):
    store = EvidenceStore(tmp_path, "session")

    path = store.write_ocr_result("TC_1", "001_before_a1.json", {"texts": [{"text": "行情"}]})

    assert path.name == "001_before_a1.json"
    assert path.parent.name == "ocr"
    assert "行情" in path.read_text(encoding="utf-8")


def test_evidence_store_writes_screenshot_bytes(tmp_path):
    store = EvidenceStore(tmp_path, "session")

    path = store.write_screenshot_bytes("TC_1", "001_after_a1.png", b"png-bytes")

    assert path.parent.name == "screenshots"
    assert path.read_bytes() == b"png-bytes"

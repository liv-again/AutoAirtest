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

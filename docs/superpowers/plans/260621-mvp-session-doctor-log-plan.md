# MVP Session Doctor Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first latest-design MVP slice: expanded config, doctor command, Test Session metadata, append-only steps, empty crash/state files, and offline run integration.

**Architecture:** Keep the current Python-first offline pipeline. Add focused utility modules under `autoairtest/tools/` and extend `EvidenceStore` so `orchestrator.run_offline()` owns a Test Session while each case still owns its existing evidence directory.

**Tech Stack:** Python standard library, pytest, existing dataclasses and JSON evidence files.

---

### Task 1: Config Surface

**Files:**
- Modify: `autoairtest/config.py`
- Test: `tests/test_config_latest_design.py`

- [ ] **Step 1: Write failing tests**

```python
from autoairtest.config import default_config, merge_config


def test_default_config_exposes_latest_design_session_logs_doctor_and_state_graph():
    config = default_config()

    assert config["execution"]["max_steps_per_case"] == 30
    assert config["execution"]["enable_state_graph"] is False
    assert config["logs"]["enable_capture"] is True
    assert "FATAL EXCEPTION" in config["logs"]["crash_patterns"]
    assert config["report"]["session_name"] == ""
    assert config["doctor"]["check_airtest"] is True
    assert config["doctor"]["check_poco"] is True


def test_merge_config_preserves_nested_latest_design_defaults():
    merged = merge_config(default_config(), {"logs": {"enable_capture": False}})

    assert merged["logs"]["enable_capture"] is False
    assert merged["logs"]["default_window_seconds"] == 5
    assert "AndroidRuntime" in merged["logs"]["crash_patterns"]
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_config_latest_design.py -q`

Expected: FAIL with missing `logs`, `doctor`, `session_name`, or execution keys.

- [ ] **Step 3: Implement defaults**

Add the latest-design keys to `default_config()` only. Do not change the merge algorithm.

- [ ] **Step 4: Run passing tests**

Run: `python -m pytest tests/test_config_latest_design.py -q`

Expected: PASS.

### Task 2: Evidence Store Session Files

**Files:**
- Modify: `autoairtest/tools/evidence_store.py`
- Test: `tests/test_evidence_store_session.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_evidence_store_session.py -q`

Expected: FAIL with missing session helper methods.

- [ ] **Step 3: Implement session helper methods**

Add `write_session_meta`, `write_config_snapshot`, `initialize_jsonl`, and `append_jsonl` to `EvidenceStore`.

- [ ] **Step 4: Run passing tests**

Run: `python -m pytest tests/test_evidence_store_session.py -q`

Expected: PASS.

### Task 3: Doctor Command

**Files:**
- Create: `autoairtest/tools/doctor.py`
- Modify: `autoairtest/cli.py`
- Test: `tests/test_doctor_cli.py`

- [ ] **Step 1: Write failing tests**

```python
import json

from autoairtest.cli import main
from autoairtest.tools.doctor import run_doctor


def test_run_doctor_reports_required_checks_without_real_device():
    result = run_doctor({"app": {"package": ""}, "device": {"adb_serial": ""}})

    check_names = {check["name"] for check in result["checks"]}
    assert {"python", "adb", "app_package", "airtest", "poco"}.issubset(check_names)
    assert result["status"] in {"passed", "warning", "failed"}


def test_doctor_cli_writes_doctor_json(tmp_path):
    exit_code = main(["doctor", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    doctor_path = tmp_path / "doctor.json"
    assert doctor_path.exists()
    assert "checks" in json.loads(doctor_path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_doctor_cli.py -q`

Expected: FAIL because `doctor` module and CLI command do not exist.

- [ ] **Step 3: Implement doctor**

Create `run_doctor(config)` with standard-library checks for Python, adb presence, app package, Airtest, and Poco. Add `doctor` subcommand that writes `doctor.json`.

- [ ] **Step 4: Run passing tests**

Run: `python -m pytest tests/test_doctor_cli.py -q`

Expected: PASS.

### Task 4: Orchestrator Session Integration

**Files:**
- Modify: `autoairtest/orchestrator.py`
- Test: `tests/test_orchestrator_session_outputs.py`

- [ ] **Step 1: Write failing tests**

```python
import json

from autoairtest import orchestrator
from autoairtest.models import NaturalLanguageTestCase


def test_run_offline_writes_session_metadata_steps_crashes_and_state_graph(tmp_path, monkeypatch):
    case = NaturalLanguageTestCase(
        case_id="TC_session",
        internal_id="TC_session",
        row_number=2,
        business_module="股指",
        feature_module="国内指数",
        feature_item="",
        test_purpose="跳转校验",
        priority="high",
        step_name="",
        precondition="",
        operation_description="行情-股指：点击更多",
        parameters="",
        expected_result="进入国内指数列表页",
        original_fields={},
    )
    monkeypatch.setattr(orchestrator, "_load_cases_or_dependency_case", lambda config: [case])

    run_dir = orchestrator.run_offline(
        {
            "report": {"output_dir": str(tmp_path), "generate_html": False, "session_name": "smoke"},
            "input": {"case_filter": ""},
        }
    )

    assert run_dir.name.endswith("_smoke")
    session_meta = json.loads((run_dir / "session_meta.json").read_text(encoding="utf-8"))
    assert session_meta["workflow"] == "excel_case_run"
    assert session_meta["case_count"] == 1
    assert (run_dir / "config.resolved.json").exists()
    assert (run_dir / "crashes.jsonl").read_text(encoding="utf-8") == ""
    assert json.loads((run_dir / "state_graph.json").read_text(encoding="utf-8")) == {"pages": {}, "edges": []}
    steps = [json.loads(line) for line in (run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()]
    assert steps
    assert steps[0]["case_id"] == "TC_session"
    assert steps[0]["crash_count"] == 0
```

- [ ] **Step 2: Run failing tests**

Run: `python -m pytest tests/test_orchestrator_session_outputs.py -q`

Expected: FAIL because session files and named session directory are missing.

- [ ] **Step 3: Integrate session helpers**

Have `run_offline()` compute a safe session id, write session metadata/config snapshot, initialize JSONL files, write empty `state_graph.json`, append one offline step record per planned action, and include case count/status in metadata.

- [ ] **Step 4: Run passing tests**

Run: `python -m pytest tests/test_orchestrator_session_outputs.py -q`

Expected: PASS.

### Task 5: Regression Run

**Files:**
- Existing test suite.

- [ ] **Step 1: Run focused tests**

Run: `python -m pytest tests/test_config_latest_design.py tests/test_evidence_store_session.py tests/test_doctor_cli.py tests/test_orchestrator_session_outputs.py -q`

Expected: PASS.

- [ ] **Step 2: Run full tracked test suite**

Run: `python -m pytest tests -q`

Expected: PASS.

---

## Coverage Notes

This plan intentionally implements only the first latest-design slice. It does not implement real Airtest/Poco device execution, real logcat capture, CrashSignature parsing, StateGraph exploration, DevTest, Smart QA, or MCP adapters. Those remain separate slices after the Test Session and doctor foundation is stable.

import json

from autoairtest import orchestrator
from autoairtest.models import NaturalLanguageTestCase


class FakeAirtestAdapter:
    def __init__(self, adb_serial=""):
        self.adb_serial = adb_serial

    def connect(self):
        return {"status": "connected", "device_uri": f"fake://{self.adb_serial}"}

    def start_app(self, package, activity=""):
        return {"status": "success", "package": package, "activity": activity}

    def snapshot(self, filename):
        with open(filename, "wb") as file:
            file.write(b"fake-png")
        return {"status": "success", "filename": filename}


class FakePocoAdapter:
    available = True
    reason = ""

    def dump(self):
        return {"status": "success", "visible_texts": ["行情", "股指", "国内指数"], "raw": {}}

    def click(self, text):
        return {"status": "success", "query": text}


def test_run_offline_device_mode_calls_adapters_and_writes_evidence(tmp_path, monkeypatch):
    case = NaturalLanguageTestCase(
        case_id="TC_device",
        internal_id="TC_device",
        row_number=2,
        business_module="行情",
        feature_module="股指",
        feature_item="",
        test_purpose="真机调用",
        priority="high",
        step_name="",
        precondition="",
        operation_description="行情-股指-国内指数",
        parameters="",
        expected_result="跳转到国内指数页面",
        original_fields={},
    )
    monkeypatch.setattr(orchestrator, "_load_cases_or_dependency_case", lambda config: [case])
    monkeypatch.setattr(orchestrator, "AirtestAdapter", FakeAirtestAdapter)
    monkeypatch.setattr(orchestrator, "PocoAdapter", FakePocoAdapter)

    run_dir = orchestrator.run_offline(
        {
            "execution": {"mode": "device"},
            "app": {"package": "com.example.app", "activity": ""},
            "device": {"adb_serial": "serial-1"},
            "report": {"output_dir": str(tmp_path), "generate_html": False},
            "input": {"case_filter": ""},
        }
    )

    action_results_path = run_dir / "cases" / "TC_device" / "action_results.json"
    action_results = json.loads(action_results_path.read_text(encoding="utf-8"))
    assert action_results[0]["status"] == "success"
    assert action_results[0]["target_element"] == {"text": "行情"}
    assert (run_dir / "cases" / "TC_device" / "screenshots" / "a1_before.png").exists()
    assert (run_dir / "cases" / "TC_device" / "element_summaries" / "a1_after.json").exists()

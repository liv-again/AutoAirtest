import json
from unittest.mock import patch

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


def test_run_parser_accepts_write_back_excel_flag():
    parser = __import__("autoairtest.cli", fromlist=["build_parser"]).build_parser()

    args = parser.parse_args(
        [
            "run",
            "--write-back-excel",
            "--execution-mode",
            "device",
            "--max-steps-per-case",
            "12",
            "--evidence-recollection-attempts",
            "1",
            "--enable-state-graph",
            "--correction-budget-low",
            "2",
            "--correction-budget-medium",
            "1",
            "--poco-dump-retries",
            "4",
            "--disable-log-capture",
            "--case-param",
            "stock_code=600519",
            "--case-param",
            "market=沪深京",
        ]
    )

    assert args.write_back_excel is True
    assert args.execution_mode == "device"
    assert args.max_steps_per_case == 12
    assert args.evidence_recollection_attempts == 1
    assert args.enable_state_graph is True
    assert args.correction_budget_low == 2
    assert args.correction_budget_medium == 1
    assert args.poco_dump_retries == 4
    assert args.disable_log_capture is True
    assert args.case_param == ["stock_code=600519", "market=沪深京"]


def test_run_cli_maps_poco_dump_retries_to_execution_retry(tmp_path):
    with patch("autoairtest.cli.run_offline", return_value=tmp_path) as run_offline:
        exit_code = main(["run", "--poco-dump-retries", "4", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    overrides = run_offline.call_args.args[0]
    assert overrides["execution"]["retry"] == {"poco_dump_max_attempts": 4}


def test_run_cli_maps_log_capture_and_case_params(tmp_path):
    with patch("autoairtest.cli.run_offline", return_value=tmp_path) as run_offline:
        exit_code = main(
            [
                "run",
                "--disable-log-capture",
                "--case-param",
                "stock_code=600519",
                "--case-param",
                "market=沪深京",
                "--output-dir",
                str(tmp_path),
            ]
        )

    assert exit_code == 0
    overrides = run_offline.call_args.args[0]
    assert overrides["logs"] == {"enable_capture": False}
    assert overrides["input"]["case_params"] == {"stock_code": "600519", "market": "沪深京"}

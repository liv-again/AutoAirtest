"""命令行接口。

CLI 层负责把用户输入转换为配置覆盖项，并把具体执行委托给编排器。该层保持轻量，
便于在后续接入其他运行时或服务接口时复用核心逻辑。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .config import default_config, load_config, merge_config, write_config_template
from .orchestrator import run_offline
from .tools.doctor import run_doctor
from .tools.evidence_store import EvidenceStore


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器并声明所有公开参数。"""

    parser = argparse.ArgumentParser(prog="autoairtest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_config = subparsers.add_parser("init-config")
    init_config.add_argument("--output", required=True)

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--config", default="")
    doctor.add_argument("--output-dir", default="runs")

    run = subparsers.add_parser("run")
    run.add_argument("--config", default="")
    run.add_argument("--excel", default="")
    run.add_argument("--sheet", default="")
    run.add_argument("--case-filter", default="")
    run.add_argument("--app-package", default="")
    run.add_argument("--app-activity", default="")
    run.add_argument("--adb-serial", default="")
    run.add_argument("--output-dir", default="")
    run.add_argument("--session-name", default="")
    run.add_argument("--save-config", default="")
    run.add_argument("--write-back-excel", action="store_true")
    run.add_argument("--execution-mode", choices=["offline", "device"], default="")
    run.add_argument("--max-steps-per-case", type=int, default=None)
    run.add_argument("--evidence-recollection-attempts", type=int, default=None)
    run.add_argument("--enable-state-graph", action="store_true")
    run.add_argument("--correction-budget-low", type=int, default=None)
    run.add_argument("--correction-budget-medium", type=int, default=None)
    run.add_argument("--poco-dump-retries", type=int, default=None)
    run.add_argument("--disable-log-capture", action="store_true")
    run.add_argument("--case-param", action="append", default=[])

    return parser


def main(argv: list[str] | None = None) -> int:
    """执行命令分发。

    返回值遵循进程退出码约定：成功为 0，参数错误由 argparse 处理。
    """

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-config":
        output = write_config_template(Path(args.output))
        print(f"Wrote config template: {output}")
        return 0

    if args.command == "doctor":
        config = default_config()
        if args.config:
            config = merge_config(config, load_config(args.config))
        config = merge_config(config, {"report": {"output_dir": args.output_dir}})
        result = run_doctor(config)
        store = EvidenceStore(args.output_dir, "")
        output = store.write_run_json("doctor.json", result)
        print(f"Doctor status: {result['status']}")
        print(f"Doctor report: {output}")
        return 0

    if args.command == "run":
        execution_overrides: dict[str, Any] = {}
        if args.execution_mode:
            execution_overrides["mode"] = args.execution_mode
        if args.max_steps_per_case is not None:
            execution_overrides["max_steps_per_case"] = args.max_steps_per_case
        if args.enable_state_graph:
            execution_overrides["enable_state_graph"] = True
        correction_budget: dict[str, int] = {}
        if args.correction_budget_low is not None:
            correction_budget["low"] = args.correction_budget_low
        if args.correction_budget_medium is not None:
            correction_budget["medium"] = args.correction_budget_medium
        if correction_budget:
            execution_overrides["correction_budget"] = correction_budget
        if args.poco_dump_retries is not None:
            execution_overrides["retry"] = {"poco_dump_max_attempts": args.poco_dump_retries}
        try:
            case_params = _parse_case_params(args.case_param)
        except ValueError as exc:
            parser.error(str(exc))
        app_overrides: dict[str, str] = {}
        if args.app_package:
            app_overrides["package"] = args.app_package
        if args.app_activity:
            app_overrides["activity"] = args.app_activity
        device_overrides: dict[str, str] = {}
        if args.adb_serial:
            device_overrides["adb_serial"] = args.adb_serial
        input_overrides: dict[str, Any] = {
            "case_filter": args.case_filter,
            "case_params": case_params,
        }
        if args.excel:
            input_overrides["excel_path"] = args.excel
        if args.sheet:
            input_overrides["sheet_name"] = args.sheet
        overrides: dict[str, Any] = {
            "config": args.config,
            "input": input_overrides,
            "report": {
                "output_dir": args.output_dir or "runs",
                "session_name": args.session_name,
                "save_config": args.save_config,
                "write_back_excel": args.write_back_excel,
            },
        }
        if execution_overrides:
            overrides["execution"] = execution_overrides
        if app_overrides:
            overrides["app"] = app_overrides
        if device_overrides:
            overrides["device"] = device_overrides
        if args.disable_log_capture:
            overrides["logs"] = {"enable_capture": False}
        if args.evidence_recollection_attempts is not None:
            overrides["verification"] = {
                "evidence_recollection": {"max_attempts": args.evidence_recollection_attempts}
            }
        run_dir = run_offline(overrides)
        print(f"Run directory: {run_dir}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _parse_case_params(raw_params: list[str]) -> dict[str, str]:
    """把重复的 --case-param key=value 参数解析为用例业务参数覆盖。"""

    parsed: dict[str, str] = {}
    for item in raw_params:
        if "=" not in item:
            raise ValueError(f"Invalid --case-param value: {item}. Expected key=value.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid --case-param value: {item}. Key must not be empty.")
        parsed[key] = value.strip()
    return parsed

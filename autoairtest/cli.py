from __future__ import annotations

import argparse
from pathlib import Path

from .config import write_config_template
from .orchestrator import run_offline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoairtest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_config = subparsers.add_parser("init-config")
    init_config.add_argument("--output", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--config", default="")
    run.add_argument("--excel", default="")
    run.add_argument("--sheet", default="")
    run.add_argument("--case-filter", default="")
    run.add_argument("--app-package", default="")
    run.add_argument("--app-activity", default="")
    run.add_argument("--adb-serial", default="")
    run.add_argument("--output-dir", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-config":
        output = write_config_template(Path(args.output))
        print(f"Wrote config template: {output}")
        return 0

    if args.command == "run":
        overrides = {
            "config": args.config,
            "input": {
                "excel_path": args.excel or "docs/test-cases.xlsx",
                "sheet_name": args.sheet or "需求测试报告",
                "case_filter": args.case_filter,
            },
            "app": {"package": args.app_package, "activity": args.app_activity},
            "device": {"adb_serial": args.adb_serial},
            "report": {"output_dir": args.output_dir or "runs"},
        }
        run_dir = run_offline(overrides)
        print(f"Run directory: {run_dir}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2

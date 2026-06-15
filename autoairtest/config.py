from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def default_config() -> dict[str, Any]:
    return {
        "app": {"package": "", "activity": "", "startup_wait_seconds": 5},
        "device": {
            "platform": "android_real_device",
            "adb_serial": "",
            "unlock_before_run": True,
        },
        "input": {
            "excel_path": "docs/test-cases.xlsx",
            "sheet_name": "需求测试报告",
            "case_filter": "",
        },
        "execution": {
            "mode": "offline",
            "continue_on_case_failure": True,
            "action_timeout_seconds": 10,
            "page_stable_timeout_seconds": 8,
            "max_locator_attempts": 3,
            "screenshot_every_action": True,
            "save_full_ui_tree": False,
            "retry": {
                "default_max_attempts": 2,
                "default_interval_seconds": 1,
                "poco_dump_max_attempts": 3,
                "poco_dump_interval_seconds": 1,
                "poco_dump_backoff": "fixed",
            },
        },
        "verification": {
            "primary_evidence": "poco",
            "always_save_screenshot": True,
            "llm_preliminary_judgment": False,
            "data_correctness_requires_human_review": True,
            "color_rule_requires_human_review": True,
            "min_confidence_for_auto_preliminary": 0.75,
        },
        "llm": {"model": "configured-by-env", "temperature": 0.1, "max_retries": 2},
        "report": {"output_dir": "runs", "generate_html": True, "write_back_excel": False},
    }


def merge_config(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        return json.loads(config_path.read_text(encoding="utf-8"))
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("PyYAML is not installed in the torch environment; use JSON config for now.") from exc
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    raise ValueError(f"Unsupported config file type: {config_path.suffix}")


def write_config_template(path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(default_config(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output

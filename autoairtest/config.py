"""运行配置管理。

本模块提供内置默认配置、递归合并和配置模板生成能力。配置设计遵循“命令行覆盖
配置文件、配置文件覆盖默认值”的原则，以支持实验复现和环境迁移。
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def default_config() -> dict[str, Any]:
    """返回离线核心的默认配置。

    默认值不假设具体证券 App、设备序列号或 LLM 服务，因此可在无真机环境下启动。
    """

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
            "max_steps_per_case": 30,
            "screenshot_every_action": True,
            "save_full_ui_tree": False,
            "enable_state_graph": False,
            "correction_budget": {"low": 3, "medium": 1, "high": 0},
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
            "llm_preliminary_judgment": True,
            "data_correctness_requires_human_review": True,
            "color_rule_requires_human_review": True,
            "min_confidence_for_auto_preliminary": 0.75,
            "evidence_recollection": {
                "max_attempts": 2,
                "allow_visibility_adjustment_on_second_attempt": True,
            },
        },
        "logs": {
            "enable_capture": True,
            "clear_before_action": True,
            "default_window_seconds": 5,
            "crash_patterns": [
                "FATAL EXCEPTION",
                "AndroidRuntime",
                "ANR in ",
                "*** *** *** *** *** ***",
                "Tombstone written to",
            ],
        },
        "evidence": {
            "redact_sensitive_text": True,
            "sensitive_keywords": ["资金账号", "手机号", "资产", "持仓"],
            "redaction_placeholder": "[REDACTED]",
            "screenshot_redaction": False,
        },
        "llm": {"model": "configured-by-env", "temperature": 0.1, "max_retries": 2},
        "report": {
            "output_dir": "runs",
            "session_name": "",
            "save_config": "",
            "generate_html": True,
            "write_back_excel": False,
        },
        "doctor": {
            "fail_on_missing_device": True,
            "fail_on_missing_app_package": True,
            "check_airtest": True,
            "check_poco": True,
        },
    }


def merge_config(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """递归合并配置字典。

    该函数保留未被覆盖的默认子项，避免浅层更新导致嵌套配置整体丢失。
    """

    merged = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path) -> dict[str, Any]:
    """加载 JSON 或 YAML 配置文件。

    YAML 被视为可选能力；当当前环境缺少 PyYAML 时给出显式错误，避免静默降级。
    """

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
    """把默认配置写出为可编辑模板。"""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(default_config(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output

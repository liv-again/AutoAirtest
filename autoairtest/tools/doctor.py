"""环境自检工具。

Doctor 只报告当前环境是否具备运行 AutoAirtest 的基础条件，不执行真实设备动作。
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from typing import Any


def run_doctor(config: dict[str, Any]) -> dict[str, Any]:
    """运行轻量环境检查并返回结构化结果。"""

    checks = [
        _check_python(),
        _check_adb(),
        _check_app_package(config),
        _check_optional_module("airtest", enabled=bool(config.get("doctor", {}).get("check_airtest", True))),
        _check_optional_module("poco", enabled=bool(config.get("doctor", {}).get("check_poco", True))),
    ]
    return {"status": _aggregate_status(checks), "checks": checks}


def _check_python() -> dict[str, Any]:
    return {
        "name": "python",
        "status": "passed",
        "detail": f"{platform.python_implementation()} {platform.python_version()}",
    }


def _check_adb() -> dict[str, Any]:
    adb_path = shutil.which("adb")
    if adb_path:
        return {"name": "adb", "status": "passed", "detail": adb_path}
    return {"name": "adb", "status": "warning", "detail": "adb executable was not found on PATH"}


def _check_app_package(config: dict[str, Any]) -> dict[str, Any]:
    package = str(config.get("app", {}).get("package", "")).strip()
    if package:
        return {"name": "app_package", "status": "passed", "detail": package}
    return {"name": "app_package", "status": "warning", "detail": "app.package is empty"}


def _check_optional_module(module_name: str, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"name": module_name, "status": "skipped", "detail": "check disabled"}
    if importlib.util.find_spec(module_name) is not None:
        return {"name": module_name, "status": "passed", "detail": "module import spec found"}
    return {"name": module_name, "status": "warning", "detail": f"{module_name} is not installed"}


def _aggregate_status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(check.get("status", "")) for check in checks}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    return "passed"

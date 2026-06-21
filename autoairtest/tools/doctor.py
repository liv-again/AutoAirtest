"""环境自检工具。

Doctor 只报告当前环境是否具备运行 AutoAirtest 的基础条件，不执行真实设备动作。
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


CommandRunner = Callable[[list[str]], dict[str, str]]


def run_doctor(config: dict[str, Any], runner: CommandRunner | None = None) -> dict[str, Any]:
    """运行轻量环境检查并返回结构化结果。"""

    command_runner = runner or _run_command
    checks = [
        _check_python(),
        _check_adb(),
        _check_adb_device(config, command_runner),
        _check_output_dir(config),
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


def _check_adb_device(config: dict[str, Any], runner: CommandRunner) -> dict[str, Any]:
    fail_on_missing = bool(config.get("doctor", {}).get("fail_on_missing_device", True))
    expected_serial = str(config.get("device", {}).get("adb_serial", "")).strip()
    output = runner(["adb", "devices"])
    if output.get("status") != "success":
        status = "failed" if fail_on_missing else "warning"
        return {
            "name": "adb_device",
            "status": status,
            "detail": output.get("stderr", "adb devices failed"),
        }

    devices = _parse_adb_devices(output.get("stdout", ""))
    connected = [device for device in devices if device["state"] == "device"]
    if expected_serial:
        matched = [device for device in connected if device["serial"] == expected_serial]
        if matched:
            return {"name": "adb_device", "status": "passed", "detail": f"{expected_serial} connected"}
        status = "failed" if fail_on_missing else "warning"
        return {
            "name": "adb_device",
            "status": status,
            "detail": f"adb serial {expected_serial} is not connected",
            "devices": devices,
        }
    if connected:
        serials = ", ".join(device["serial"] for device in connected)
        return {"name": "adb_device", "status": "passed", "detail": serials, "devices": devices}
    status = "failed" if fail_on_missing else "warning"
    return {"name": "adb_device", "status": status, "detail": "no connected adb device", "devices": devices}


def _parse_adb_devices(output: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("list of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "state": parts[1]})
    return devices


def _check_output_dir(config: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(str(config.get("report", {}).get("output_dir", "runs") or "runs"))
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=output_dir):
            pass
    except OSError as exc:
        return {"name": "output_dir", "status": "failed", "detail": str(exc)}
    return {"name": "output_dir", "status": "passed", "detail": str(output_dir)}


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


def _run_command(args: list[str]) -> dict[str, str]:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "stdout": "", "stderr": str(exc)}
    if completed.returncode != 0:
        return {"status": "error", "stdout": completed.stdout, "stderr": completed.stderr}
    return {"status": "success", "stdout": completed.stdout, "stderr": completed.stderr}

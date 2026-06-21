"""Android logcat 采集工具边界。"""

from __future__ import annotations

import subprocess
from typing import Any, Callable

from .crash_analyzer import extract_crash_signatures

CommandRunner = Callable[[list[str]], dict[str, str]]


class LogCollector:
    """封装 logcat 查询和崩溃解析。

    runner 可注入，便于离线测试；生产默认使用 subprocess 执行 adb。
    """

    def __init__(
        self,
        adb_path: str = "adb",
        enabled: bool = True,
        runner: CommandRunner | None = None,
    ) -> None:
        self.adb_path = adb_path
        self.enabled = enabled
        self._runner = runner or _run_command

    def get_recent_crashes(self, package: str = "", lines: int = 300) -> dict[str, Any]:
        """读取最近 logcat 并返回结构化 crash 结果。"""

        output = self.dump_recent(lines=lines)
        if output.get("status") != "success":
            if output.get("status") == "disabled":
                return {"status": "disabled", "reason": output.get("reason", ""), "crash_count": 0, "crashes": []}
            return {
                "status": "unavailable",
                "reason": output.get("reason") or output.get("stderr") or "adb logcat failed",
                "crash_count": 0,
                "crashes": [],
            }

        crashes = extract_crash_signatures(output.get("stdout", ""), package=package)
        return {"status": "success", "reason": "", "crash_count": len(crashes), "crashes": crashes}

    def clear(self) -> dict[str, Any]:
        """清理当前 logcat 缓冲区，便于动作级窗口采集。"""

        if not self.enabled:
            return {"status": "disabled", "reason": "log capture is disabled"}
        if not self.adb_path:
            return {"status": "unavailable", "reason": "adb path is empty"}
        output = self._runner([self.adb_path, "logcat", "-c"])
        if output.get("status") != "success":
            return {"status": "unavailable", "reason": output.get("stderr", "adb logcat clear failed")}
        return {"status": "success", "reason": ""}

    def dump_recent(self, lines: int = 300) -> dict[str, Any]:
        """读取最近 N 行 logcat 原始输出。"""

        if not self.enabled:
            return {"status": "disabled", "reason": "log capture is disabled", "stdout": "", "stderr": ""}
        if not self.adb_path:
            return {"status": "unavailable", "reason": "adb path is empty", "stdout": "", "stderr": ""}

        output = self._runner([self.adb_path, "logcat", "-d", "-t", str(lines)])
        if output.get("status") != "success":
            return {
                "status": "unavailable",
                "stdout": output.get("stdout", ""),
                "stderr": output.get("stderr", "adb logcat failed"),
            }
        return output


def _run_command(args: list[str]) -> dict[str, str]:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "stdout": "", "stderr": str(exc)}
    if completed.returncode != 0:
        return {"status": "error", "stdout": completed.stdout, "stderr": completed.stderr}
    return {"status": "success", "stdout": completed.stdout, "stderr": completed.stderr}

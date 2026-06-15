"""Airtest 工具适配器。

当前版本只定义调用边界和缺失依赖时的降级响应。真实设备执行阶段可在保持方法签名
稳定的前提下，将这些方法替换为 Airtest API 调用。
"""

from __future__ import annotations

import importlib.util
from typing import Any


class AirtestAdapter:
    """封装 Airtest 设备操作能力的适配器。"""

    def __init__(self) -> None:
        """探测当前环境是否已安装 Airtest。"""

        self.available = importlib.util.find_spec("airtest") is not None

    def connect(self) -> dict[str, Any]:
        """连接测试设备。"""

        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch"}
        return {"status": "connected", "reason": ""}

    def start_app(self, package: str, activity: str = "") -> dict[str, Any]:
        """启动被测 Android 应用。"""

        if not self.available:
            return {
                "status": "unavailable",
                "reason": "airtest is not installed in torch",
                "package": package,
                "activity": activity,
            }
        return {"status": "success", "package": package, "activity": activity}

    def snapshot(self, filename: str) -> dict[str, Any]:
        """采集屏幕截图并写入目标文件。"""

        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "filename": filename}
        return {"status": "success", "filename": filename}

    def touch(self, target: object) -> dict[str, Any]:
        """点击屏幕坐标、模板或其他可定位目标。"""

        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "target": target}
        return {"status": "success", "target": target}

    def swipe(self, start: object, end: object) -> dict[str, Any]:
        """执行从起点到终点的滑动操作。"""

        if not self.available:
            return {
                "status": "unavailable",
                "reason": "airtest is not installed in torch",
                "start": start,
                "end": end,
            }
        return {"status": "success", "start": start, "end": end}

    def text(self, value: str) -> dict[str, Any]:
        """向当前焦点控件输入文本。"""

        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "text": value}
        return {"status": "success", "text": value}

    def keyevent(self, key: str) -> dict[str, Any]:
        """发送系统按键事件，例如 BACK。"""

        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "key": key}
        return {"status": "success", "key": key}

from __future__ import annotations

import importlib.util
from typing import Any


class AirtestAdapter:
    def __init__(self) -> None:
        self.available = importlib.util.find_spec("airtest") is not None

    def connect(self) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch"}
        return {"status": "connected", "reason": ""}

    def start_app(self, package: str, activity: str = "") -> dict[str, Any]:
        if not self.available:
            return {
                "status": "unavailable",
                "reason": "airtest is not installed in torch",
                "package": package,
                "activity": activity,
            }
        return {"status": "success", "package": package, "activity": activity}

    def snapshot(self, filename: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "filename": filename}
        return {"status": "success", "filename": filename}

    def touch(self, target: object) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "target": target}
        return {"status": "success", "target": target}

    def swipe(self, start: object, end: object) -> dict[str, Any]:
        if not self.available:
            return {
                "status": "unavailable",
                "reason": "airtest is not installed in torch",
                "start": start,
                "end": end,
            }
        return {"status": "success", "start": start, "end": end}

    def text(self, value: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "text": value}
        return {"status": "success", "text": value}

    def keyevent(self, key: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "airtest is not installed in torch", "key": key}
        return {"status": "success", "key": key}

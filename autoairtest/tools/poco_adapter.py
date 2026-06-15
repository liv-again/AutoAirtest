from __future__ import annotations

import importlib.util
from typing import Any


class PocoAdapter:
    def __init__(self) -> None:
        self.available = importlib.util.find_spec("poco") is not None

    def dump(self) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "visible_texts": []}
        return {"status": "success", "visible_texts": []}

    def query(self, text: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "matches": []}

    def exists(self, text: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "exists": False}

    def click(self, text: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text}

    def text(self, text: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "text": ""}

    def bounds(self, text: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "bounds": None}

    def attributes(self, text: str) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "attributes": {}}

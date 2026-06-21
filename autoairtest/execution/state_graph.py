"""页面状态图诊断模型。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


def page_fingerprint(elements: list[dict[str, Any]]) -> str:
    """根据稳定元素字段生成页面指纹。"""

    tokens = sorted(_element_token(element) for element in elements if _element_token(element))
    payload = "\n".join(tokens)
    return "page_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


@dataclass
class StateGraph:
    """记录页面、已见元素和页面跳转边。"""

    pages: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, str]] = field(default_factory=list)

    def record_page(self, page_hash: str, summary: str = "", screenshot: str = "") -> None:
        page = self.pages.setdefault(
            page_hash,
            {
                "visit_count": 0,
                "summary": summary,
                "screenshot": screenshot,
                "elements_seen": [],
            },
        )
        page["visit_count"] += 1
        if summary:
            page["summary"] = summary
        if screenshot:
            page["screenshot"] = screenshot

    def mark_element_seen(self, page_hash: str, element_key: str) -> None:
        page = self.pages.setdefault(
            page_hash,
            {
                "visit_count": 0,
                "summary": "",
                "screenshot": "",
                "elements_seen": [],
            },
        )
        if element_key not in page["elements_seen"]:
            page["elements_seen"].append(element_key)

    def record_edge(self, from_hash: str, action: str, to_hash: str, case_id: str = "") -> None:
        self.edges.append({"from": from_hash, "action": action, "to": to_hash, "case_id": case_id})

    def to_dict(self) -> dict[str, Any]:
        return {"pages": self.pages, "edges": self.edges}


def _element_token(element: dict[str, Any]) -> str:
    resource_id = str(element.get("resource_id") or element.get("id") or "").strip()
    text = str(element.get("text") or "").strip()
    label = str(element.get("label") or element.get("content_desc") or "").strip()
    if resource_id:
        return f"id:{resource_id}"
    if text:
        return f"text:{text}"
    if label:
        return f"label:{label}"
    return ""

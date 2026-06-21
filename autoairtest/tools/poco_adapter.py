"""Poco 控件树适配器。

Poco 提供移动端控件层级、文本、位置和属性等结构化界面证据。离线核心仅保留方法
合同，真实环境缺少依赖时返回显式不可用状态。
"""

from __future__ import annotations

import importlib.util
from typing import Any


class PocoAdapter:
    """封装 Poco 语义查询和控件操作能力的适配器。"""

    def __init__(self, poco: Any | None = None) -> None:
        """探测当前环境是否已安装 Poco。"""

        self.poco = poco
        self.available = poco is not None or importlib.util.find_spec("poco") is not None

    def dump(self) -> dict[str, Any]:
        """导出当前界面的控件树摘要。"""

        poco = self._poco()
        if poco is None:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "visible_texts": []}
        try:
            raw_dump = _dump_hierarchy(poco)
        except Exception as exc:  # pragma: no cover - depends on third-party SDK behavior
            return {"status": "unavailable", "reason": f"poco dump failed: {type(exc).__name__}: {exc}", "visible_texts": []}
        elements = _elements_from_dump(raw_dump)
        return {"status": "success", "visible_texts": [item["text"] for item in elements if item.get("text")], "elements": elements}

    def query(self, text: str) -> dict[str, Any]:
        """按文本或语义标签查询候选控件。"""

        poco = self._poco()
        if poco is None:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        try:
            nodes = _query_nodes(poco, text)
        except Exception as exc:  # pragma: no cover - depends on third-party SDK behavior
            return {"status": "unavailable", "reason": f"poco query failed: {type(exc).__name__}: {exc}", "query": text}
        return {"status": "success", "query": text, "matches": [_node_summary(node) for node in nodes]}

    def exists(self, text: str) -> dict[str, Any]:
        """判断目标文本或控件是否存在。"""

        result = self.query(text)
        if result.get("status") != "success":
            return result | {"exists": False}
        return result | {"exists": bool(result.get("matches"))}

    def click(self, text: str) -> dict[str, Any]:
        """点击与文本查询匹配的控件。"""

        poco = self._poco()
        if poco is None:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        try:
            selector = poco(text=text)
            nodes = _selector_nodes(selector)
            if not nodes:
                return {"status": "unavailable", "reason": "poco target not found", "query": text}
            if hasattr(selector, "click"):
                selector.click()
            else:
                nodes[0].click()
        except Exception as exc:  # pragma: no cover - depends on third-party SDK behavior
            return {"status": "unavailable", "reason": f"poco click failed: {type(exc).__name__}: {exc}", "query": text}
        return {"status": "success", "query": text, "target": _node_summary(nodes[0])}

    def text(self, text: str) -> dict[str, Any]:
        """读取匹配控件的文本值。"""

        result = self.query(text)
        if result.get("status") != "success":
            return result | {"text": ""}
        matches = result.get("matches", [])
        first = matches[0] if matches else {}
        return result | {"text": str(first.get("text", ""))}

    def bounds(self, text: str) -> dict[str, Any]:
        """读取匹配控件的边界框。"""

        result = self.query(text)
        if result.get("status") != "success":
            return result | {"bounds": None}
        matches = result.get("matches", [])
        first = matches[0] if matches else {}
        return result | {"bounds": first.get("bounds")}

    def attributes(self, text: str) -> dict[str, Any]:
        """读取匹配控件的属性字典。"""

        result = self.query(text)
        if result.get("status") != "success":
            return result | {"attributes": {}}
        matches = result.get("matches", [])
        first = matches[0] if matches else {}
        return result | {"attributes": first.get("attributes", {})}

    def _poco(self) -> Any | None:
        if self.poco is not None:
            return self.poco
        if not self.available:
            return None
        try:
            from poco.drivers.android.uiautomation import AndroidUiautomationPoco  # type: ignore
        except ModuleNotFoundError:
            return None
        self.poco = AndroidUiautomationPoco(use_airtest_input=True, screenshot_each_action=False)
        return self.poco


def _dump_hierarchy(poco: Any) -> Any:
    if hasattr(poco, "dump"):
        return poco.dump()
    agent = poco.agent() if callable(getattr(poco, "agent", None)) else getattr(poco, "agent", None)
    hierarchy = agent.hierarchy() if callable(getattr(agent, "hierarchy", None)) else getattr(agent, "hierarchy", None)
    if hierarchy is None or not hasattr(hierarchy, "dump"):
        return {}
    return hierarchy.dump()


def _elements_from_dump(raw_dump: Any) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        payload = node.get("payload", {}) if isinstance(node.get("payload"), dict) else {}
        text = str(payload.get("text") or node.get("text") or "").strip()
        if text:
            elements.append({"text": text, "bounds": payload.get("bounds") or node.get("bounds"), "attributes": payload})
        for child in node.get("children", []) if isinstance(node.get("children"), list) else []:
            visit(child)

    visit(raw_dump)
    return elements


def _query_nodes(poco: Any, text: str) -> list[Any]:
    selector = poco(text=text)
    return _selector_nodes(selector)


def _selector_nodes(selector: Any) -> list[Any]:
    if selector is None:
        return []
    if isinstance(selector, list):
        return selector
    try:
        return [node for node in selector]
    except TypeError:
        return [selector]


def _node_summary(node: Any) -> dict[str, Any]:
    text = ""
    bounds = None
    attributes: dict[str, Any] = {}
    if hasattr(node, "get_text"):
        text = str(node.get_text() or "")
    if hasattr(node, "get_bounds"):
        bounds = node.get_bounds()
    if hasattr(node, "attr"):
        for name in ["name", "type", "text"]:
            value = node.attr(name)
            if value is not None:
                attributes[name] = value
    return {"text": text, "bounds": bounds, "attributes": attributes}

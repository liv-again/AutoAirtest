"""Poco 控件树适配器。

Poco 提供移动端控件层级、文本、位置和属性等结构化界面证据。离线核心仅保留方法
合同，真实环境缺少依赖时返回显式不可用状态。
"""

from __future__ import annotations

import importlib.util
from typing import Any


class PocoAdapter:
    """封装 Poco 语义查询和控件操作能力的适配器。"""

    def __init__(
        self,
        poco: Any | None = None,
        app_package: str = "",
        save_full_ui_tree: bool = False,
    ) -> None:
        """探测当前环境是否已安装 Poco。"""

        self.poco = poco
        self.app_package = str(app_package or "").strip()
        self.save_full_ui_tree = bool(save_full_ui_tree)
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
        visible_texts: list[str] = []
        for element in elements:
            for key in ("text", "desc", "name", "resource_id"):
                value = str(element.get(key, "") or "").strip()
                if value and value not in visible_texts:
                    visible_texts.append(value)
        result: dict[str, Any] = {
            "status": "success",
            "visible_texts": visible_texts,
            "elements": elements,
            "element_count": len(elements),
        }
        # 原始树默认不写入，避免报告体积和敏感信息无谓膨胀；开启
        # execution.save_full_ui_tree 后保留它，便于定位解析丢节点的问题。
        if self.save_full_ui_tree:
            result["raw_dump"] = _json_safe(raw_dump)
        return result

    def query(self, text: str) -> dict[str, Any]:
        """按文本或语义标签查询候选控件。"""

        poco = self._poco()
        if poco is None:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        failures: list[str] = []
        for locator_type, kwargs in _query_variants(text):
            try:
                nodes = _selector_nodes(poco(**kwargs))
            except Exception as exc:  # pragma: no cover - depends on third-party SDK behavior
                failures.append(f"{locator_type}: {type(exc).__name__}: {exc}")
                continue
            if nodes:
                return {
                    "status": "success",
                    "query": text,
                    "locator_type": locator_type,
                    "matches": [_node_summary(node) for node in nodes],
                }
        reason = "poco target not found by text/desc/name"
        if failures:
            reason += f" ({'; '.join(failures)})"
        return {"status": "unavailable", "reason": reason, "query": text}

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
        failures: list[str] = []
        for locator_type, kwargs in _query_variants(text):
            try:
                selector = poco(**kwargs)
                nodes = _selector_nodes(selector)
                if not nodes:
                    continue
                if hasattr(selector, "click"):
                    selector.click()
                else:
                    nodes[0].click()
                return {
                    "status": "success",
                    "query": text,
                    "locator_type": locator_type,
                    "target": _node_summary(nodes[0]),
                }
            except Exception as exc:  # pragma: no cover - depends on third-party SDK behavior
                failures.append(f"{locator_type}: {type(exc).__name__}: {exc}")
        reason = "poco target not found by text/desc/name"
        if failures:
            reason += f" ({'; '.join(failures)})"
        return {"status": "unavailable", "reason": reason, "query": text}

    def click_content_desc(self, content_desc: str) -> dict[str, Any]:
        """按 Android content-desc 点击控件。"""

        value = str(content_desc or "").strip()
        if not value:
            return {"status": "unavailable", "reason": "content_desc is empty", "query": value}
        poco = self._poco()
        if poco is None:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": value}
        try:
            selector = poco(desc=value)
            nodes = _selector_nodes(selector)
            if not nodes:
                return {"status": "unavailable", "reason": "poco target not found", "query": value}
            if hasattr(selector, "click"):
                selector.click()
            else:
                nodes[0].click()
        except Exception as exc:  # pragma: no cover - depends on third-party SDK behavior
            return {
                "status": "unavailable",
                "reason": f"poco content_desc click failed: {type(exc).__name__}: {exc}",
                "query": value,
            }
        return {
            "status": "success",
            "query": value,
            "locator_type": "content_desc",
            "target": _node_summary(nodes[0]),
        }

    def query_resource_id(self, resource_id: str) -> dict[str, Any]:
        """按 Android resource-id 查询候选控件。"""

        normalized, reason = _normalize_resource_id(resource_id, self.app_package)
        if reason:
            return {"status": "unavailable", "reason": reason, "query": str(resource_id)}
        poco = self._poco()
        if poco is None:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": normalized}
        try:
            nodes = _selector_nodes(poco(normalized))
        except Exception as exc:  # pragma: no cover - depends on third-party SDK behavior
            return {
                "status": "unavailable",
                "reason": f"poco resource_id query failed: {type(exc).__name__}: {exc}",
                "query": normalized,
            }
        return {
            "status": "success",
            "query": normalized,
            "locator_type": "resource_id",
            "matches": [_node_summary(node) for node in nodes],
        }

    def click_resource_id(self, resource_id: str) -> dict[str, Any]:
        """按 Android resource-id 点击控件，短 ID 使用配置中的包名补全。"""

        normalized, reason = _normalize_resource_id(resource_id, self.app_package)
        if reason:
            return {"status": "unavailable", "reason": reason, "query": str(resource_id)}
        poco = self._poco()
        if poco is None:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": normalized}
        try:
            selector = poco(normalized)
            nodes = _selector_nodes(selector)
            if not nodes:
                return {"status": "unavailable", "reason": "poco target not found", "query": normalized}
            if hasattr(selector, "click"):
                selector.click()
            else:
                nodes[0].click()
        except Exception as exc:  # pragma: no cover - depends on third-party SDK behavior
            return {
                "status": "unavailable",
                "reason": f"poco resource_id click failed: {type(exc).__name__}: {exc}",
                "query": normalized,
            }
        return {
            "status": "success",
            "query": normalized,
            "locator_type": "resource_id",
            "target": _node_summary(nodes[0]),
        }

    def set_text_resource_id(self, resource_id: str, text: str) -> dict[str, Any]:
        """按 Android resource-id 定位控件并用 Poco set_text 输入文本。"""

        normalized, reason = _normalize_resource_id(resource_id, self.app_package)
        if reason:
            return {"status": "unavailable", "reason": reason, "query": str(resource_id), "text": text}
        poco = self._poco()
        if poco is None:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": normalized, "text": text}
        try:
            selector = poco(normalized)
            nodes = _selector_nodes(selector)
            if not nodes:
                return {"status": "unavailable", "reason": "poco target not found", "query": normalized, "text": text}
            if hasattr(selector, "set_text"):
                selector.set_text(text)
            elif hasattr(nodes[0], "set_text"):
                nodes[0].set_text(text)
            else:
                return {
                    "status": "unavailable",
                    "reason": "poco node has no set_text method",
                    "query": normalized,
                    "text": text,
                }
        except Exception as exc:  # pragma: no cover
            return {
                "status": "unavailable",
                "reason": f"poco set_text failed: {type(exc).__name__}: {exc}",
                "query": normalized,
                "text": text,
            }
        return {
            "status": "success",
            "query": normalized,
            "locator_type": "resource_id",
            "text": text,
            "target": _node_summary(nodes[0]),
        }

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


_TEXT_KEYS = ("text", "label", "title", "hint")
_DESC_KEYS = ("desc", "content_desc", "contentDescription", "description", "accessibilityLabel")
_NAME_KEYS = ("name", "className", "class", "type")
_RESOURCE_ID_KEYS = ("resourceId", "resource_id", "resource-id", "resource", "id")
_CHILD_KEYS = ("children", "child", "nodes", "items")


def _elements_from_dump(raw_dump: Any) -> list[dict[str, Any]]:
    """把不同 Poco/Android dump 形态统一成可定位的节点摘要。

    Poco 版本、驱动和自定义控件返回的树结构并不完全一致。除了 text，
    desc/name/resourceId 也可能是唯一可用的定位信息，因此不能只保留文本节点。
    """

    elements: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                visit(child)
            return
        if not isinstance(node, dict):
            return

        payload = node.get("payload", {}) if isinstance(node.get("payload"), dict) else {}
        attributes: dict[str, Any] = {}
        # 不把 node 本身合并进 attributes，避免把 children 整棵树重复嵌套到每个节点。
        for container in (payload, node.get("attributes"), node.get("attrs"), node.get("properties")):
            if isinstance(container, dict):
                attributes.update(container)

        def first_value(keys: tuple[str, ...]) -> str:
            for container in (payload, node, attributes):
                if not isinstance(container, dict):
                    continue
                for key in keys:
                    value = container.get(key)
                    if value is not None and str(value).strip():
                        return str(value).strip()
            return ""

        text = first_value(_TEXT_KEYS)
        desc = first_value(_DESC_KEYS)
        name = first_value(_NAME_KEYS)
        resource_id = first_value(_RESOURCE_ID_KEYS)
        bounds = _normalize_bounds(
            next(
                (
                    container.get(key)
                    for container in (payload, node, attributes)
                    if isinstance(container, dict)
                    for key in ("bounds", "rect", "rectangle")
                    if container.get(key) is not None
                ),
                None,
            )
        )
        if bounds is None:
            bounds = _bounds_from_pos_size(attributes)

        aliases = _unique_strings((text, desc, name, resource_id))
        if aliases or bounds is not None:
            elements.append(
                {
                    "text": text or desc or name or resource_id,
                    "desc": desc,
                    "name": name,
                    "resource_id": resource_id,
                    "aliases": aliases,
                    "bounds": bounds,
                    "attributes": attributes,
                }
            )

        for key in _CHILD_KEYS:
            for container in (node, payload):
                children = container.get(key) if isinstance(container, dict) else None
                if isinstance(children, (list, dict)):
                    visit(children)
        # 有些驱动用 root/node/hierarchy 包一层，而不是 children。
        for key in ("root", "node", "hierarchy", "tree"):
            child = node.get(key)
            if isinstance(child, (list, dict)):
                visit(child)

    visit(raw_dump)
    return elements


def _query_variants(text: str) -> tuple[tuple[str, dict[str, str]], ...]:
    value = str(text or "").strip()
    return (
        ("text", {"text": value}),
        ("content_desc", {"desc": value}),
        ("name", {"name": value}),
    )


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _normalize_bounds(bounds: Any) -> list[int | float] | None:
    if isinstance(bounds, dict):
        try:
            bounds = [bounds[key] for key in ("left", "top", "right", "bottom")]
        except KeyError:
            return None
    if isinstance(bounds, str):
        parts = bounds.replace(",", " ").split()
        bounds = parts
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        return None
    try:
        values = [float(item) for item in bounds]
    except (TypeError, ValueError):
        return None
    if values[2] <= values[0] or values[3] <= values[1]:
        return None
    return [int(value) if value.is_integer() else value for value in values]


def _bounds_from_pos_size(attributes: dict[str, Any]) -> list[float] | None:
    """从 Poco 常见的归一化 pos/size 属性推导节点边界。"""

    pos = attributes.get("pos")
    size = attributes.get("size")
    if not isinstance(pos, (list, tuple)) or not isinstance(size, (list, tuple)):
        return None
    if len(pos) != 2 or len(size) != 2:
        return None
    try:
        center_x, center_y, width, height = (float(item) for item in (*pos, *size))
    except (TypeError, ValueError):
        return None
    bounds = [center_x - width / 2, center_y - height / 2, center_x + width / 2, center_y + height / 2]
    return _normalize_bounds(bounds)


def _json_safe(value: Any) -> Any:
    """把可选的原始树转换为可写入 JSON 的值。"""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _query_nodes(poco: Any, text: str) -> list[Any]:
    selector = poco(text=text)
    return _selector_nodes(selector)


def _normalize_resource_id(resource_id: str, app_package: str) -> tuple[str, str]:
    value = str(resource_id or "").strip()
    package = str(app_package or "").strip()
    if not value:
        return "", "resource_id is empty"
    if ":id/" in value:
        return value, ""
    if not package:
        return "", "app package is required for short resource_id"
    if value.startswith("id/"):
        return f"{package}:{value}", ""
    if "/" not in value and ":" not in value:
        return f"{package}:id/{value}", ""
    return "", "invalid resource_id format"


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
        for name in [
            "name",
            "type",
            "text",
            "desc",
            "contentDescription",
            "resourceId",
            "resource_id",
        ]:
            try:
                value = node.attr(name)
            except Exception:  # pragma: no cover - depends on third-party SDK behavior
                continue
            if value is not None:
                attributes[name] = value
    return {"text": text, "bounds": bounds, "attributes": attributes}

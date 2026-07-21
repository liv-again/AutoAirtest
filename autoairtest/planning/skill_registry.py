"""规划技能注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autoairtest.models import LocatorCandidate


@dataclass(frozen=True)
class NavigationNode:
    """导航树中的一个稳定节点。"""

    node_id: str
    text: str
    parent: str | None
    aliases: tuple[str, ...]
    children: tuple[str, ...]


@dataclass(frozen=True)
class StockDetailElement:
    """个股分时页中的稳定元素及其有序定位候选。"""

    element_id: str
    text: str
    parent: str | None
    aliases: tuple[str, ...]
    children: tuple[str, ...]
    locators: tuple[LocatorCandidate, ...]
    description: str
    source_note: str

    @property
    def preferred_locator(self) -> str:
        """根据第一个候选返回执行器可识别的首选定位层级。"""

        if not self.locators:
            return "poco_semantic"
        return {
            "resource_id": "poco_resource_id",
            "content_desc": "poco_content_desc",
            "text": "poco_text",
            "position": "airtest_position",
        }.get(self.locators[0].type, "poco_semantic")


@dataclass(frozen=True)
class StockDetailEntry:
    """进入个股详情页的一条稳定路由定义。"""

    entry_id: str
    description: str
    route: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class MarketCodeRule:
    """单个市场的股票代码前缀规则。"""

    name: str
    prefixes: tuple[str, ...]


class SkillRegistry:
    """加载规划技能资源，并提供别名归一化查询。"""

    def __init__(self, skills_root: str | Path) -> None:
        self.skills_root = Path(skills_root)
        self.aliases = self._load_aliases()
        self.navigation_roots, self.navigation_nodes = self._load_navigation_nodes()
        (
            stock_detail_route_page_id,
            self.stock_detail_page_aliases,
            self.stock_detail_entries,
        ) = self._load_stock_detail_pages()
        (
            stock_detail_element_page_id,
            self.stock_detail_roots,
            self.stock_detail_elements,
        ) = self._load_stock_detail_elements()
        self.stock_detail_page_id = stock_detail_element_page_id or stock_detail_route_page_id
        self.market_codes = self._load_market_codes()
        self.trade_success_keywords: tuple[str, ...] = ("订单号", "订单编号", "委托编号")

    def resolve_alias(self, text: str) -> str:
        """返回导航别名的归一化文本。"""

        return self.aliases.get(text, text)

    def resolve_navigation_path(self, text: str) -> list[NavigationNode]:
        """根据自然语言上下文返回最可能的导航节点路径。"""

        target = self.match_navigation_node(text)
        if target is None:
            return []
        return self.path_to_node(target.node_id)

    def match_navigation_node(self, text: str) -> NavigationNode | None:
        """在导航节点和别名中查找与上下文最匹配的目标节点。"""

        context = str(text or "")
        if not context or not self.navigation_nodes:
            return None

        scored: list[tuple[int, int, int, int, str]] = []
        for node in self.navigation_nodes.values():
            for term in (node.text, *node.aliases):
                if not term:
                    continue
                index = context.rfind(term)
                if index < 0:
                    continue
                scored.append(
                    (
                        index + len(term),
                        len(term),
                        self._ancestor_match_count(node.node_id, context, term),
                        -self._node_depth(node.node_id),
                        node.node_id,
                    )
                )
        if not scored:
            return None
        return self.navigation_nodes[max(scored)[-1]]

    def path_to_node(self, node_id: str) -> list[NavigationNode]:
        """从根节点到目标节点返回稳定路径。"""

        if node_id not in self.navigation_nodes:
            return []

        path: list[NavigationNode] = []
        seen: set[str] = set()
        current_id: str | None = node_id
        while current_id:
            if current_id in seen or current_id not in self.navigation_nodes:
                return []
            seen.add(current_id)
            node = self.navigation_nodes[current_id]
            path.append(node)
            current_id = node.parent
        return list(reversed(path))

    def matched_rules(self, text: str) -> list[str]:
        """返回命中的规划技能规则 ID。"""

        if text not in self.aliases:
            return []
        return [f"navigation_alias.{self._alias_rule_suffix(text)}"]

    def is_stock_detail_context(self, text: str) -> bool:
        """判断自然语言上下文是否属于个股详情/分时页。"""

        context = str(text or "")
        if not context or not (self.stock_detail_elements or self.stock_detail_entries):
            return False
        triggers = (
            "个股详情",
            "股票详情",
            "个股分时",
            "分时页",
            self.stock_detail_page_id,
            *self.stock_detail_page_aliases,
        )
        return any(trigger and trigger in context for trigger in triggers)

    def match_stock_detail_element(self, text: str) -> StockDetailElement | None:
        """在个股分时页上下文中按文字、别名和父级区域匹配元素。"""

        context = str(text or "")
        if not self.is_stock_detail_context(context):
            return None

        scored: list[tuple[int, int, int, int, str]] = []
        for element in self.stock_detail_elements.values():
            for term in (element.text, *element.aliases):
                if not term:
                    continue
                index = context.rfind(term)
                if index < 0:
                    continue
                scored.append(
                    (
                        self._stock_detail_ancestor_match_count(element.element_id, context, term),
                        index + len(term),
                        len(term),
                        self._stock_detail_depth(element.element_id),
                        element.element_id,
                    )
                )
        if not scored:
            return None
        return self.stock_detail_elements[max(scored)[-1]]

    def _load_aliases(self) -> dict[str, str]:
        aliases_path = self.skills_root / "securities_navigation" / "aliases.yaml"
        if not aliases_path.exists():
            return {}
        payload = self._load_yaml_or_simple_map(aliases_path)
        aliases = payload.get("aliases", {}) if isinstance(payload, dict) else {}
        if not isinstance(aliases, dict):
            return {}
        return {str(key): str(value) for key, value in aliases.items()}

    def _load_navigation_nodes(self) -> tuple[list[str], dict[str, NavigationNode]]:
        nodes_path = self.skills_root / "navigation" / "nodes.yaml"
        if not nodes_path.exists():
            return [], {}
        payload = self._load_yaml_or_simple_map(nodes_path)
        raw_nodes = payload.get("nodes", {}) if isinstance(payload, dict) else {}
        raw_roots = payload.get("roots", []) if isinstance(payload, dict) else []
        if not isinstance(raw_nodes, dict):
            return [], {}

        nodes: dict[str, NavigationNode] = {}
        for node_id, raw_node in raw_nodes.items():
            if not isinstance(raw_node, dict):
                continue
            nodes[str(node_id)] = NavigationNode(
                node_id=str(node_id),
                text=str(raw_node.get("text", "")),
                parent=str(raw_node["parent"]) if raw_node.get("parent") is not None else None,
                aliases=tuple(str(item) for item in _list_or_empty(raw_node.get("aliases"))),
                children=tuple(str(item) for item in _list_or_empty(raw_node.get("children"))),
            )
        roots = [str(item) for item in raw_roots] if isinstance(raw_roots, list) else []
        return roots, nodes

    def _load_stock_detail_elements(
        self,
    ) -> tuple[str, list[str], dict[str, StockDetailElement]]:
        elements_path = self.skills_root / "stock_detail" / "fenshi_elements_1.yaml"
        if not elements_path.exists():
            return "", [], {}
        payload = self._load_yaml_or_simple_map(elements_path)
        raw_elements = payload.get("elements", {}) if isinstance(payload, dict) else {}
        raw_roots = payload.get("roots", []) if isinstance(payload, dict) else []
        if not isinstance(raw_elements, dict):
            return "", [], {}

        elements: dict[str, StockDetailElement] = {}
        for element_id, raw_element in raw_elements.items():
            if not isinstance(raw_element, dict):
                continue
            locators: list[LocatorCandidate] = []
            for raw_locator in _list_or_empty(raw_element.get("locators")):
                if not isinstance(raw_locator, dict):
                    continue
                locator_type = str(raw_locator.get("type", "")).strip()
                if not locator_type or "value" not in raw_locator:
                    continue
                locators.append(
                    LocatorCandidate(
                        type=locator_type,
                        value=raw_locator["value"],
                        coordinate_system=str(raw_locator.get("coordinate_system", "")),
                    )
                )
            elements[str(element_id)] = StockDetailElement(
                element_id=str(element_id),
                text=str(raw_element.get("text", "")),
                parent=str(raw_element["parent"]) if raw_element.get("parent") is not None else None,
                aliases=tuple(str(item) for item in _list_or_empty(raw_element.get("aliases"))),
                children=tuple(str(item) for item in _list_or_empty(raw_element.get("children"))),
                locators=tuple(locators),
                description=str(raw_element.get("description", "")),
                source_note=str(raw_element.get("source_note", "")),
            )
        roots = [str(item) for item in raw_roots] if isinstance(raw_roots, list) else []
        return str(payload.get("page_id", "")), roots, elements

    def _load_stock_detail_pages(
        self,
    ) -> tuple[str, tuple[str, ...], dict[str, StockDetailEntry]]:
        pages_path = self.skills_root / "stock_detail" / "pages.yaml"
        if not pages_path.exists():
            return "", (), {}
        payload = self._load_yaml_or_simple_map(pages_path)
        raw_target = payload.get("target_page", {}) if isinstance(payload, dict) else {}
        raw_entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
        if not isinstance(raw_target, dict) or not isinstance(raw_entries, dict):
            return "", (), {}

        page_text = str(raw_target.get("text", "")).strip()
        aliases = tuple(
            item
            for item in [page_text, *(str(value) for value in _list_or_empty(raw_target.get("aliases")))]
            if item
        )
        entries: dict[str, StockDetailEntry] = {}
        for entry_id, raw_entry in raw_entries.items():
            if not isinstance(raw_entry, dict):
                continue
            route: list[dict[str, str]] = []
            for raw_step in _list_or_empty(raw_entry.get("route")):
                if not isinstance(raw_step, dict):
                    continue
                route.append({str(key): str(value) for key, value in raw_step.items()})
            entries[str(entry_id)] = StockDetailEntry(
                entry_id=str(entry_id),
                description=str(raw_entry.get("description", "")),
                route=tuple(route),
            )
        return str(raw_target.get("page_id", "")), aliases, entries

    def _load_yaml_or_simple_map(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError:
            return self._parse_simple_alias_yaml(text)
        loaded = yaml.safe_load(text) or {}
        return loaded if isinstance(loaded, dict) else {}

    def _parse_simple_alias_yaml(self, text: str) -> dict[str, Any]:
        aliases: dict[str, str] = {}
        in_aliases = False
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped == "aliases:":
                in_aliases = True
                continue
            if in_aliases and raw_line.startswith((" ", "\t")) and ":" in stripped:
                key, value = stripped.split(":", 1)
                aliases[key.strip()] = value.strip().strip("\"'")
        return {"aliases": aliases}

    def _alias_rule_suffix(self, text: str) -> str:
        suffixes = {
            "自选": "self_selected",
            "A股": "a_share",
            "沪深": "cn_a_market",
            "国内指数更多": "domestic_index_more",
        }
        return suffixes.get(text, text)

    def _ancestor_match_count(self, node_id: str, context: str, matched_term: str) -> int:
        count = 0
        seen: set[str] = set()
        current_id = self.navigation_nodes.get(node_id).parent if node_id in self.navigation_nodes else None
        while current_id:
            if current_id in seen or current_id not in self.navigation_nodes:
                break
            seen.add(current_id)
            ancestor = self.navigation_nodes[current_id]
            terms = [ancestor.text, *ancestor.aliases]
            if any(term and term != matched_term and term in context for term in terms):
                count += 1
            current_id = ancestor.parent
        return count

    def _node_depth(self, node_id: str) -> int:
        depth = 0
        seen: set[str] = set()
        current_id = node_id
        while current_id in self.navigation_nodes:
            if current_id in seen:
                break
            seen.add(current_id)
            parent = self.navigation_nodes[current_id].parent
            if parent is None:
                break
            depth += 1
            current_id = parent
        return depth

    def _stock_detail_ancestor_match_count(self, element_id: str, context: str, matched_term: str) -> int:
        count = 0
        seen: set[str] = set()
        element = self.stock_detail_elements.get(element_id)
        current_id = element.parent if element else None
        while current_id:
            if current_id in seen or current_id not in self.stock_detail_elements:
                break
            seen.add(current_id)
            ancestor = self.stock_detail_elements[current_id]
            terms = (ancestor.text, *ancestor.aliases)
            if any(term and term != matched_term and term in context for term in terms):
                count += 1
            current_id = ancestor.parent
        return count

    def _stock_detail_depth(self, element_id: str) -> int:
        depth = 0
        seen: set[str] = set()
        current_id = element_id
        while current_id in self.stock_detail_elements:
            if current_id in seen:
                break
            seen.add(current_id)
            parent = self.stock_detail_elements[current_id].parent
            if parent is None:
                break
            depth += 1
            current_id = parent
        return depth


    def _load_market_codes(self) -> dict[str, MarketCodeRule]:
        """加载 stock market code 前缀规则。"""
        codes_path = self.skills_root / "expected_result_rules" / "market_codes.yaml"
        if not codes_path.exists():
            return {}
        payload = self._load_yaml_or_simple_map(codes_path)
        raw_markets = payload.get("markets", []) if isinstance(payload, dict) else []
        if not isinstance(raw_markets, list):
            return {}
        codes: dict[str, MarketCodeRule] = {}
        for item in raw_markets:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", ""))
            prefixes = tuple(str(p) for p in _list_or_empty(item.get("prefixes")))
            if name and prefixes:
                codes[name] = MarketCodeRule(name=name, prefixes=prefixes)
        return codes

    def match_market_by_code(self, stock_code: str) -> str:
        """根据股票代码前缀返回所属市场名称，无匹配时返回空字符串。"""
        if not stock_code or not self.market_codes:
            return ""
        for market in self.market_codes.values():
            if any(stock_code.startswith(prefix) for prefix in market.prefixes):
                return market.name
        return ""

    def market_names(self) -> list[str]:
        """返回所有已注册的市场名称。"""
        return list(self.market_codes.keys())


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

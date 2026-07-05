"""规划技能注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NavigationNode:
    """导航树中的一个稳定节点。"""

    node_id: str
    text: str
    parent: str | None
    aliases: tuple[str, ...]
    children: tuple[str, ...]


class SkillRegistry:
    """加载规划技能资源，并提供别名归一化查询。"""

    def __init__(self, skills_root: str | Path) -> None:
        self.skills_root = Path(skills_root)
        self.aliases = self._load_aliases()
        self.navigation_roots, self.navigation_nodes = self._load_navigation_nodes()

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


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

"""规划技能注册表。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SkillRegistry:
    """加载规划技能资源，并提供别名归一化查询。"""

    def __init__(self, skills_root: str | Path) -> None:
        self.skills_root = Path(skills_root)
        self.aliases = self._load_aliases()

    def resolve_alias(self, text: str) -> str:
        """返回导航别名的归一化文本。"""

        return self.aliases.get(text, text)

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

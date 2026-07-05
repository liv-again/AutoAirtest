from autoairtest.planning.skill_registry import SkillRegistry


def test_skill_registry_loads_navigation_aliases(tmp_path):
    skill_dir = tmp_path / "skills" / "securities_navigation"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("aliases.yaml").write_text("aliases:\n  自选: 我的自选\n", encoding="utf-8")

    registry = SkillRegistry(tmp_path / "skills")

    assert registry.resolve_alias("自选") == "我的自选"
    assert registry.matched_rules("自选") == ["navigation_alias.self_selected"]


def test_skill_registry_resolves_navigation_path_from_nodes(tmp_path):
    skill_dir = tmp_path / "skills" / "navigation"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("nodes.yaml").write_text(
        """
roots:
  - market
nodes:
  market:
    text: 行情
    parent: null
    aliases: []
    children: [market_a_share]
  market_a_share:
    text: A股
    parent: market
    aliases: [A股行情]
    children: [cn_a_market]
  cn_a_market:
    text: 沪深京
    parent: market_a_share
    aliases: [沪深]
    children: []
""".strip(),
        encoding="utf-8",
    )

    registry = SkillRegistry(tmp_path / "skills")

    path = registry.resolve_navigation_path("进入行情-A股-沪深")

    assert [node.node_id for node in path] == ["market", "market_a_share", "cn_a_market"]
    assert [node.text for node in path] == ["行情", "A股", "沪深京"]

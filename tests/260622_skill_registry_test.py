from autoairtest.planning.skill_registry import SkillRegistry


def test_skill_registry_loads_navigation_aliases(tmp_path):
    skill_dir = tmp_path / "skills" / "securities_navigation"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("aliases.yaml").write_text("aliases:\n  自选: 我的自选\n", encoding="utf-8")

    registry = SkillRegistry(tmp_path / "skills")

    assert registry.resolve_alias("自选") == "我的自选"
    assert registry.matched_rules("自选") == ["navigation_alias.self_selected"]

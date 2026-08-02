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
    locators:
      - type: content_desc
        value: 行情
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
    assert path[0].preferred_locator == "poco_content_desc"
    assert path[0].locators[0].value == "行情"


def test_skill_registry_loads_and_matches_stock_detail_elements(tmp_path):
    skill_dir = tmp_path / "skills" / "stock_detail"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("fenshi_elements_1.yaml").write_text(
        """
page_id: stock_fenshi
roots: [title_bar]
elements:
  title_bar:
    text: 标题栏
    parent: null
    aliases: []
    children: [title_back]
    locators: []
  title_back:
    text: 返回
    parent: title_bar
    aliases: [返回按钮]
    children: []
    locators:
      - type: resource_id
        value: id/backButton
""".strip(),
        encoding="utf-8",
    )

    registry = SkillRegistry(tmp_path / "skills")

    assert registry.is_stock_detail_context("个股分时页点击返回") is True
    element = registry.match_stock_detail_element("个股分时页点击返回")
    assert element is not None
    assert element.element_id == "title_back"
    assert element.locators[0].type == "resource_id"
    assert element.locators[0].value == "id/backButton"


def test_skill_registry_disambiguates_repeated_stock_detail_text_by_parent_context(tmp_path):
    skill_dir = tmp_path / "skills" / "stock_detail"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("fenshi_elements_1.yaml").write_text(
        """
page_id: stock_fenshi
roots: [chart_switch, announcement]
elements:
  chart_switch:
    text: 分时切换
    parent: null
    aliases: [K线周期]
    children: [chart_more]
    locators: []
  chart_more:
    text: 更多
    parent: chart_switch
    aliases: [更多周期]
    children: []
    locators:
      - type: text
        value: 更多
  announcement:
    text: 公告
    parent: null
    aliases: [个股公告]
    children: [announcement_more]
    locators:
      - type: text
        value: 公告
  announcement_more:
    text: 更多
    parent: announcement
    aliases: [更多公告]
    children: []
    locators:
      - type: text
        value: 更多
""".strip(),
        encoding="utf-8",
    )

    registry = SkillRegistry(tmp_path / "skills")

    element = registry.match_stock_detail_element("个股分时页点击公告区域的更多")
    assert element is not None
    assert element.element_id == "announcement_more"


def test_skill_registry_registers_stock_detail_page_entry_routes(tmp_path):
    skill_dir = tmp_path / "skills" / "stock_detail"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("pages.yaml").write_text(
        """
target_page:
  page_id: stock_fenshi
  text: 个股分时页
  aliases: [个股详情页, 股票详情页]
entries:
  market_search:
    description: 从行情搜索进入个股分时页
    route:
      - node: market
      - node: market_search
      - action: input_stock_keyword
      - action: tap_search_result
""".strip(),
        encoding="utf-8",
    )

    registry = SkillRegistry(tmp_path / "skills")

    assert registry.stock_detail_page_id == "stock_fenshi"
    assert registry.stock_detail_page_aliases == ("个股分时页", "个股详情页", "股票详情页")
    entry = registry.stock_detail_entries["market_search"]
    assert entry.description == "从行情搜索进入个股分时页"
    assert entry.route == (
        {"node": "market"},
        {"node": "market_search"},
        {"action": "input_stock_keyword"},
        {"action": "tap_search_result"},
    )
    assert registry.is_stock_detail_context("从行情搜索进入股票详情页") is True

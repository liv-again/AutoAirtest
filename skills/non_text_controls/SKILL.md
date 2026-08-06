# Non-Text Controls

证券 App 非文本类控件定位技能，用于把自然语言中的业务目标映射到无文字标签的 UI 元素（图标、图片按钮、非标准控件）。

## Resources

- `home_elements.yaml`: 首页非文本控件定义。
- `market_elements.yaml`: 行情页非文本控件定义。
- `search_elements.yaml`: 搜索页非文本控件定义。

## Element Rules

- Prefer `resource_id` for icon-only controls without visible text labels.
- Fall back to `content_desc` or normalized `position` when `resource_id` is unavailable.
- Match elements by business name and aliases in the natural language context.
- Disambiguate repeated business names by page context (`page_id`).
- Treat a stateful control such as `search_watchlist_toggle` as one element with action aliases
  (`加自选`, `删自选`, `添加自选`, `删除自选`); do not invent separate resource IDs for each state.
- For the search input, prefer `id/search_pagenavi_editview`. Use the documented placeholder
  text only as fallback; `搜索股票/理财` may be matched by prefix when the executor supports it.

## Planner Activation

- Activate this skill when the test case refers to a UI control by business name but no visible text label is available, or when the control is known to be icon-only.
- Attach the matched element's ordered `locators` to `PlanAction`. Prefer `resource_id`.
- If no exact non-text element matches, tell the planner not to invent a resource-id.

## Resource-ID Execution

- Keep a fully qualified ID such as `com.example:id/backButton` unchanged.
- Expand `id/backButton` to `<app.package>:id/backButton`.
- If a short ID is used without `app.package`, return an explicit unavailable result instead of treating the ID as visible text.
- Try locators in YAML order.
- Treat values copied from the source document as trimmed values; punctuation used to quote a
  value in prose is not part of the resource ID.

## Boundaries

- `resource-id` and `contentDescription` values depend on the target App version.
- This skill covers icon-only and non-text controls; it does not cover text-labeled UI elements that can be located by Poco text matching.

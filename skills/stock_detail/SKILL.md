# Stock Detail

证券 App 个股详情页（分时页）技能，用于把自然语言测试步骤映射为页面入口和可执行的 UI 元素定位。

## Resources

- `pages.yaml`: 个股详情页的多入口路由定义。
- `fenshi_elements_1.yaml`: 个股分时页内的层级化元素定义，包含文字、resource-id、contentDescription 和相对坐标。

## Page Entry Rules

- Resolve an entry from `pages.yaml` by business context, then execute its `route` in order.
- Treat every `node` as a stable ID from `skills/navigation/nodes.yaml`.
- Treat every `action` as a page-local operation rather than a navigation-tree node.
- Confirm that the destination matches `target_page.page_id` before locating page elements.

## Element Rules

- Use stable element IDs instead of visible text as keys, because text such as “更多”和“新闻” repeats across regions.
- Resolve aliases before element lookup.
- Disambiguate repeated text by walking `parent` and checking the surrounding region.
- Try each element's `locators` in listed order; combine parent context with the locator when a value is repeated.
- Keep source values unchanged. Entries marked `source_note` reproduce a suspicious source mapping and require device verification.

## Planner Activation

- Activate this skill only when the test-case context identifies an individual stock detail page, stock fenshi page, or an equivalent page alias.
- Match page-local targets by element text, aliases, and parent region; do not use this skill for global navigation nodes.
- Attach the matched element's ordered `locators` to `PlanAction`. Prefer `resource_id` for icon-only controls.
- If no exact stock-detail element matches, tell the planner not to invent a resource-id.

## Resource-ID Execution

- Keep a fully qualified ID such as `com.example:id/backButton` unchanged.
- Expand `id/backButton` to `<app.package>:id/backButton`.
- Expand `backButton` to `<app.package>:id/backButton`.
- If a short ID is used without `app.package`, return an explicit unavailable result instead of treating the ID as visible text.
- Try locators in YAML order, so a later text locator can safely follow a resource-id candidate.

## Extension

This skill is tree-shaped in `fenshi_elements_1.yaml`: each element has at most one `parent`. Keep element IDs stable so locators can be updated without changing test-case semantics.

## Boundaries

- The element source is `中原个股分时页.md`; it describes UI location, not quote-data correctness.
- resource-id and contentDescription values depend on the target App version.
- The normalized position for the bottom “指数” icon is source-provided and must be verified when resolution or layout changes.

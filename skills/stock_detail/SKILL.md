# Stock Detail

个股详情页（分时页）元素定义技能。用于把测试用例中的业务目标映射到个股详情页内可定位的 UI 元素。

## Resources

- `pages.yaml`: 个股详情页的多入口路由定义。
- `fenshi_elements_1.yaml`: 个股分时页内的元素定义（含图标定位信息）。

## Page Entry Points

个股详情页无法通过单一菜单路径到达，入口分散在多个页面。路由定义见 `pages.yaml`。

## Element Location Strategy

个股详情页元素定位按优先级：

1. **text** — 元素有可见文字，直接用 Poco text 查询（如 "买一"、"卖一"、"换手率"）
2. **content_desc** — 元素无文字但有 `contentDescription`（如图标按钮 "返回"、"分享"）
3. **resource_id** — 文字和 content_desc 都不可靠时，用 resource-id 定位
4. **position** — 以上都不可用时，用相对坐标（如 "K线图底部 Tab 区域第 2 个"）

## Human-Name Mapping

`fenshi_elements_1.yaml` 中的 `aliases` 字段记录了人为命名到实际 UI 文本的映射：

- 人叫"分时图" → 页面实际 Tab 为 "分时"
- 人叫"五档盘口" → 实际包含 买一~买五、卖一~卖五 的 `position` 描述
- 人叫"主力资金" → 实际 Tab 文字为 "资金"

## Boundaries

- 页面结构受 App 版本影响；resource-id 和 content_desc 需在目标版本上验证
- position 定位依赖屏幕分辨率，当前适配 1080×2376
- 行情数据正确性不在此技能范围内

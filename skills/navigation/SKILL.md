# Navigation

证券 App 菜单导航节点技能，用于把自然语言测试用例中的业务目标映射到可执行的菜单节点路径。

## Resources

- `nodes.yaml`: 证券 App 经典菜单结构的节点化导航树。

## Node Rules

- Use stable node IDs instead of menu text as keys, because menu text can repeat across modules.
- Resolve aliases before path lookup.
- Find a target node by exact text, alias, and surrounding business context.
- Build a path by walking from the target node through `parent` until reaching a root node.
- Convert the path to low-risk Poco semantic tap actions using each node's `text`.
- When a navigation node targets an icon or another non-text control, set `control_ref`
  to an element ID from `skills/non_text_controls`. The node inherits that control's
  aliases and locators, while node-local locators remain higher priority.

## Extension

This skill is tree-shaped in `nodes.yaml`: each node has at most one `parent`. Keep node IDs stable so the same data can later be migrated to a graph by replacing `parent` and `children` with explicit `edges`.

## Boundaries

Navigation path resolution only proves that the target menu can be located by known structure. It does not prove market quote correctness, UI data freshness, or cross-terminal data consistency.

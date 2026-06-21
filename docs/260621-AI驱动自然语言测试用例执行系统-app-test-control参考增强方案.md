# AI驱动自然语言测试用例执行系统 - app-test-control 参考增强方案

> 文件前缀：260621  
> 日期：2026-06-21  
> 输入材料：`AI驱动自然语言测试用例执行系统-方案设计.md`、`test-cases.xlsx`、`dj931567261/app-test-control` 公开仓库  
> MVP 范围：Android 真机上的证券 App 自然语言测试用例自动执行与截图留痕

---

## 1. 设计结论

本系统面向证券 App 的自然语言功能测试用例执行。第一版目标不是替代人工完成全部业务判断，而是把 Excel 中的自然语言用例转成可执行动作，在 Android 真机上自动完成页面进入、点击、弹窗打开、列表展开等操作，并采集足够证据供人工复核。

核心设计结论如下：

| 主题 | 决策 |
| --- | --- |
| 被测设备 | 仅支持 Android 真机；MVP 不考虑模拟器、iOS、多设备并发 |
| 操作执行 | Airtest 负责设备连接、截图、点击、滑动、输入；Poco 负责控件树、元素查询、元素状态读取 |
| 用例来源 | Excel 工作簿 `test-cases.xlsx`，sheet 为 `需求测试报告` |
| 智能体形态 | Workflow 主导整体流程；Planning Agent 负责自然语言理解；Execution Agent 在受限纠错循环中处理执行期歧义；Verification Agent 辅助证据解释；工具层封装为 MCP 兼容接口，但第一版可本地进程调用 |
| 元素定位 | 执行动作阶段使用三级定位漏斗：Poco 语义匹配优先，截图+控件树联合定位次之，图像/OCR/坐标兜底 |
| 结果验证 | 验证阶段采用 Rule Engine 优先、Verification Agent 辅助解释、人工最终复核的分工 |
| 截图策略 | 每条用例必须保存截图留痕；截图是审计证据和人工复核依据，不只是失败时才保存 |
| 数据正确性 | LLM 可做初步判断和摘要，但行情数据是否正确最终交由人工根据截图判断 |
| 纠错策略 | 按动作风险分级控制自动纠错：低风险最多 3 次，中风险最多 1 次，高风险不自动纠错 |
| 报告输出 | 生成 HTML 报告、结构化 JSON 结果、截图和元素摘要证据包；可选回写 Excel 的 `测试结果` 与 `备注` |

### 1.1 参考 app-test-control 的针对性吸收

`app-test-control` 的价值不在于某个单点工具，而在于把移动测试拆成可复用能力面：MCP 工具、Skill 工作流、session 证据目录、状态图、崩溃签名和环境自检。结合本项目当前定位，应做“思想吸收 + 本地 Python 化落地”，不应直接改成 TypeScript 多 MCP 平台。

| 参考点 | 是否吸收 | 在本方案中的落点 |
| --- | --- | --- |
| `devtest / qa / minimize / smart-qa` 场景化 Skill | 部分吸收 | 保留本项目 Excel 用例执行主线；新增“场景化工作流视图”，把开发自测、用例回归、探索 QA、复现路径精简作为不同入口，而不是让单一 Workflow 承担所有目标 |
| session 目录和 `steps.jsonl / crashes.jsonl / state-graph.json` | 吸收 | 在现有 `runs/<timestamp>/cases/` 外增加 Test Session 元数据、追加式步骤日志、崩溃日志和可选状态图 |
| `log-mcp` 的 crash/ANR/tombstone 思路 | 吸收 | 增加 Log Collector / Crash Analyzer 工具边界；MVP 先做 Android logcat 关键字和时间窗口，不进入 iOS |
| `analyzer-mcp` 的 crash signature、dedup、ddmin 路径精简 | 分阶段吸收 | MVP 记录 crash signature 与原始复现路径；路径精简放到后续演进，不阻塞前两条真机用例闭环 |
| `ui-mcp` 层级优先、截图兜底 | 已基本一致 | 保留 Poco 语义定位优先；补充“页面级层级失效标记”，避免 Flutter/WebView 类页面每步重复 dump 浪费时间 |
| `doctor / setup / prewarm` 自检体验 | 吸收 | 增加 `doctor` 命令建议，用于检查 Python 依赖、ADB、设备、App 包名、Airtest/Poco、输出目录和配置 |
| 多客户端 MCP 接入 | 暂不进入 MVP | 本项目先保持本地 Python CLI；MCP Server 作为 M5/M6 后的适配层，不影响核心数据模型 |
| iOS Simulator 支持 | 不吸收进 MVP | 证券 App 第一阶段限定 Android 真机；iOS 只在长期演进保留可能性 |

因此，本增强方案的关键变化是：把原先“逐条 Excel 用例执行”的设计，扩展成“Test Session + 多工作流入口 + 崩溃与状态证据”的设计，但仍维持 MVP 的受控执行边界。

---

## 2. MVP 目标与非目标

### 2.1 MVP 目标

第一版应完成以下能力：

1. 读取 Excel 自然语言测试用例，保留业务模块、功能模块、用例名称、优先级、前置条件、操作描述、参数、预期结果等字段。
2. 将每条用例解析成结构化执行计划，包括前置条件、操作步骤、验证目标和需要采集的证据。
3. 连接一台 Android 真机，确认设备在线、App 可启动、Poco 可 dump 控件树、Airtest 可截图和操作。
4. 自动执行自然语言操作描述，例如进入行情页、点击股指、打开国内指数、点击更多、点击科创综指、打开底部指数弹框。
5. 在每条用例的关键节点保存截图、结构化元素摘要、执行日志和 LLM 判断结果。
6. 验证页面跳转、弹框展示、元素顺序、列表内容等可由控件树表达的结果。
7. 对数据正确性、两端一致性、颜色规则等结果给出初步判断和证据摘要，但标记为需要人工复核。
8. 生成便于人工查看的 HTML 报告，报告中能按用例查看操作过程、截图、元素摘要、初步判断和复核建议。

### 2.2 MVP 非目标

以下能力不进入第一版：

1. iOS 执行。
2. Android 模拟器适配。
3. 多设备并发执行。
4. 接入交易所、行情后端、数据库或接口作为数据正确性的外部 Oracle。
5. 自动登录、验证码处理、交易下单等高风险闭环操作。
6. 完整录制回放平台。
7. 用例自动维护、自动改写 Excel、自动生成测试用例。
8. 将 LLM 判断作为行情数据正确性的最终结论。
9. 自由探索式 QA、自动复现路径精简和多客户端 MCP-native 接入。
10. 从 `git diff` 自动推断业务影响面的开发自测入口。

---

## 3. 输入用例分析

### 3.1 工作簿结构

`test-cases.xlsx` 当前只有一个 sheet：

| 属性 | 值 |
| --- | --- |
| Sheet 名称 | `需求测试报告` |
| 行数 | 8 行，含表头 |
| 列数 | 13 列 |
| 用例数 | 7 条 |

字段如下：

| 字段 | 含义 | MVP 用法 |
| --- | --- | --- |
| 业务模块 | 一级业务域，例如股指、A股、自选 | 与功能模块共同形成模块路径；可与操作描述中的目标页面路径相互验证，并由 Skills 提供路径、别名和入口规则指导 |
| 功能模块 | 二级模块，例如国内指数、沪深京、个股详情页 | 与业务模块共同约束目标页面路径；用于校验 Planner 是否误解操作描述 |
| 功能项 | 页面或功能区域，例如一级宫格页面、大盘指数 | 用于推断当前页面区域 |
| 测试目的 | 数据校验、跳转校验、默认展示校验、页面展示 | 用于推断验证策略 |
| TC_用例名称 | 测试用例唯一可读名称 | 用作测试结果主标题 |
| 优先级 | high、middle | 用于执行排序和报告筛选 |
| 步骤名称 | 当前为空 | 保留，第一版不依赖 |
| 前置条件 | 例如“有行业板块的券商” | 作为人工准备项或执行前检查项 |
| 操作描述 | 由目标页面路径、操作方法、操作对象组成的自然语言说明 | Planner 的主要输入；必须与业务模块、功能模块、功能项交叉验证 |
| 参数 | Excel 中的用例参数，当前多为空或 null | 作为用例级默认参数；运行时命令行参数优先级更高 |
| 预期结果 | 自然语言断言 | Verifier 的主要输入 |
| 测试结果 | 当前为空 | 可选回写 |
| 备注 | 当前为空 | 可选回写失败原因和复核说明 |

### 3.2 当前用例清单与验证类型

| 序号 | 用例名称 | 操作概要 | 预期结果概要 | 验证类型 |
| --- | --- | --- | --- | --- |
| 1 | TC_国内指数模块数据正确 | 行情-股指：查看国内指数模块数据显示 | 科创综指排第四；指数顺序正确；数据展示正确；与个股行情页一致 | 顺序自动初判 + 数据人工复核 |
| 2 | TC_国内指数宫格跳转正常 | 行情-股指-国内指数：点击六宫格中的科创综指 | 跳转到该指数行情分时页面 | 页面跳转自动初判 |
| 3 | TC_国内指数更多跳转正常 | 行情-股指-国内指数：点击右侧“更多”按钮 | 跳转至国内指数列表页；科创综指排第四 | 跳转和顺序自动初判 |
| 4 | TC_大盘指数数据显示正确 | 行情-A股-沪深京：查看大盘指数模块数据显示 | 科创综指排第四；数据两端一致；红涨绿跌黑平 | 顺序自动初判 + 数据/颜色人工复核 |
| 5 | TC_个股详情页科创综指展示正常 | A股分时页面底部操作栏点击底部指数 | 弹出指数分时图弹框；选中上证指数；含行业板块时指数顺序正确 | 弹框和顺序自动初判 |
| 6 | TC_个股详情页科创综指展示正常 | 进入基金/B股/新三板/债券等详情页，点击底部指数 | 弹出指数分时图弹框；无行业板块时指数顺序正确 | 弹框和顺序自动初判 |
| 7 | TC_自选顶部指数展示正常 | 沪深A股个股详情页，点击自选顶部指数 | 弹出指数分时图弹框；科创综指排第四；指数顺序正确 | 弹框和顺序自动初判 |

### 3.3 用例特征

当前用例不是细粒度脚本，而是业务路径与操作意图描述。`操作描述` 通常由三部分组成：目标页面路径、操作方法、操作对象。例如 `行情-股指-国内指数：点击右侧“更多”按钮` 中，`行情-股指-国内指数` 是目标页面路径，`点击` 是操作方法，`右侧“更多”按钮` 是操作对象。

业务模块、功能模块、功能项提供另一组模块路径线索，应与操作描述互相验证。后续 Skills 需要维护证券 App 的导航别名、模块入口、常见页面路径和歧义处理规则。例如业务模块为 `股指`、功能模块为 `国内指数` 时，操作描述中出现 `行情-股指-国内指数` 是一致的；如果操作描述写成 `行情-A股-沪深京`，Planner 应标记为路径冲突并要求人工确认或走低置信度处理。

典型表达包括：

1. `行情-股指-国内指数`：使用短横线表达导航路径。
2. `点击六宫格中的科创综指`：目标元素依赖页面区域和业务名称。
3. `点击右侧“更多”按钮`：目标有相对位置约束。
4. `底部操作栏-点击底部指数`：目标依赖页面布局。
5. `科创综指排在第四位`：验证需要读取元素顺序。
6. `数据展示正确`、`两端/自营对比一致`：MVP 需要截图证据和人工判断。
7. `红涨绿跌黑平`：Poco 不一定能提供颜色信息，需要截图、像素或人工复核。

因此第一版设计必须把“可自动验证”和“需要人工复核”的结果分开表达。

---

## 4. 术语与边界

本文档使用以下核心术语：

| 术语 | 定义 |
| --- | --- |
| 自然语言测试用例 | Excel 中的一行测试用例，包含操作描述和预期结果 |
| 模块路径 | 业务模块、功能模块、功能项共同暗示的业务入口和页面区域 |
| 操作描述 | 用例中描述测试人员应如何操作 App 的自然语言文本，由目标页面路径、操作方法、操作对象组成 |
| 预期结果 | 用例中描述操作后应观察到什么的自然语言文本 |
| 执行计划 | LLM 将自然语言用例解析出的结构化动作和验证目标 |
| 验证目标 | 从预期结果拆出的单条可检查声明 |
| 界面证据 | 控件树、元素文本、元素位置、元素状态、OCR 文本、截图等证据 |
| 截图证据 | 每条用例强制保存的屏幕截图，用于审计和人工复核 |
| 初步判断 | 系统基于界面证据生成的自动判断，不等于人工最终结论 |
| 人工复核 | 测试人员基于截图和报告确认结果是否最终通过 |

边界说明：

1. “定位元素”属于执行动作阶段。
2. “验证结果”属于结果判断阶段。
3. 验证阶段优先使用 Poco 控件树和元素状态，而不是优先让 LLM 看截图。
4. 截图是强制证据，不代表所有判断都由截图自动完成。
5. 数据正确性不是 MVP 的全自动结论，必须保留人工复核入口。

---

## 5. 总体架构

### 5.1 架构视图

```text
┌────────────────────────────────────────────────────────────┐
│               Orchestrator / Workflow 主控流程              │
│  读取配置 -> 连接设备 -> 读取Excel -> 逐条执行 -> 生成报告     │
└──────────────┬─────────────────────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────────────────────┐
│                Agent-assisted Decision Layer                │
├──────────────────┬──────────────────┬─────────────────────┤
│ Planning Agent   │ Execution Agent  │ Verification Agent  │
│ 用例理解/归一/计划│ 执行期歧义/纠错   │ 证据缺口/复核说明     │
└────────┬─────────┴────────┬─────────┴──────────┬──────────┘
         │                  │                    │
         ▼                  ▼                    ▼
┌────────────────────────────────────────────────────────────┐
│              Rules / Skills / Guardrails / Trace            │
├──────────────┬──────────────┬──────────────┬──────────────┤
│ Skill Rules  │ Risk Policy  │ Rule Engine  │ Exec Trace   │
│ 别名/路径/顺序│ 动作风险/预算 │ 确定性验证    │ 追加式审计    │
└──────┬───────┴──────┬───────┴──────┬───────┴──────────────┘
       │              │              │
       ▼              ▼              ▼
┌────────────────────────────────────────────────────────────┐
│                  Tool Layer 工具接口层                      │
├──────────────┬──────────────┬──────────────┬──────────────┤
│ Airtest      │ Poco         │ OCR          │ Evidence     │
│ 截图/点击/滑动│ 控件树/元素状态│ 文本识别      │ 证据存储      │
└──────┬───────┴──────┬───────┴──────┬───────┴──────────────┘
       │              │              │
       ▼              ▼              ▼
┌────────────────────────────────────────────────────────────┐
│                  Android 真机 + 证券 App                    │
└────────────────────────────────────────────────────────────┘
```

### 5.2 组件职责

| 组件 | 职责 | 是否调用 LLM |
| --- | --- | --- |
| Orchestrator / Workflow | 串联全流程，控制用例执行顺序、超时、失败后是否继续，并保证审计记录完整 | 否 |
| Excel Loader | 读取 Excel、标准化字段、生成用例对象 | 否 |
| Planning Agent | 将操作描述和预期结果解析为执行计划，处理自然语言差异、导航别名、目标归一、风险分类，并输出解释依据 | 是 |
| Execution Agent | 在 Workflow 限定的动作和风险预算内处理执行期歧义、候选元素选择、可恢复误操作识别和纠错建议 | 是，主要用于执行期歧义消解和纠错解释 |
| Rule Engine | 对元素顺序、文本存在、弹框展示等确定性目标进行规则验证 | 否 |
| Verification Agent | 解释证据缺口、证据冲突、UI 文案差异和人工复核原因，不替代规则引擎和人工最终裁决 | 是 |
| Reporter | 汇总结果、证据、执行轨迹、复核原因和复核建议，生成 HTML 报告 | 可选 |
| Skill Registry | 管理证券 App 导航别名、页面路径、指数顺序、风险规则、验证规则等可复用能力包 | 否 |
| Guardrails / Risk Policy | 按动作风险等级控制自动执行、纠错预算和人工确认边界 | 否 |
| Airtest Adapter | 封装 connect、start_app、snapshot、touch、swipe、text、keyevent | 否 |
| Poco Adapter | 封装 dump、query、exists、click、get_text、get_bounds、get_attr | 否 |
| OCR Adapter | 从截图提取文字和坐标，用于 Poco 不可见文本兜底 | 否 |
| Evidence Store | 保存截图、结构化元素摘要、执行计划、执行轨迹、计划补充、判断结果和日志；完整控件树仅作为调试可选项 | 否 |
| Log Collector | 按 Test Session 和动作时间窗口采集 logcat、ANR 线索和关键运行日志 | 否 |
| Crash Analyzer | 从 logcat/ANR/native crash 文本提取 Crash Signature、崩溃摘要和原始复现路径 | 否 |
| State Graph Store | 保存可选页面指纹、已访问元素和页面转移关系，用于后续探索 QA 与循环规避 | 否 |
| Environment Doctor | 运行前检查 Python 依赖、ADB、设备、App 包名、Airtest/Poco 可用性和输出目录权限 | 否 |
| LLM Client | 统一封装模型调用、JSON 校验、重试、敏感信息脱敏 | 否，作为基础设施 |

### 5.3 MCP 与本地实现关系

原方案中的 MCP Server 是合理的工具边界，但第一版不需要先做复杂的远程服务化。推荐实现方式：

1. 先写本地 Python 工具接口，函数签名按 MCP 工具风格设计。
2. Agent 和 Workflow 只能通过工具接口操作设备，不直接调用 Airtest/Poco 原始 API。
3. 后续如需接入 OpenCode、Sisyphus 或其他 Agent Runtime，可把这些工具接口暴露成 MCP Server。

这样既保留架构边界，又避免第一版在协议和部署上过重。

### 5.4 Agent、Workflow、Skill 与 Tool 的边界

第一版不采用“所有 LLM 调用都叫 Agent”的命名方式。边界如下：

1. Workflow 负责固定主线、状态推进、超时、重试、证据保存和报告生成。
2. Planning Agent 负责自然语言理解、业务别名归一、路径冲突识别、验证目标拆分和动作风险分类。
3. Execution Agent 只在 Workflow 给定的动作目标、当前界面证据和风险预算内处理执行期歧义，不允许无边界探索。
4. Verification Agent 负责解释证据缺口、冲突证据和人工复核原因，不负责最终裁决行情数据正确性。
5. Skills 保存可复用领域知识和可测试规则，例如 `自选 -> 我的自选`、国内指数顺序、行业板块场景、动作风险规则。
6. Tools 是真实动作接口，例如截图、dump 控件树、点击、滑动、OCR、证据写入。
7. Guardrails 根据动作风险等级和置信度限制自动执行、纠错和证据补采。

因此，MVP 的推荐架构不是“多 Agent 自由协作”，而是“Workflow 主导 + 少数受限 Agent + Skills + Tools + Guardrails + 追加式 Trace”。

### 5.5 场景化工作流入口

参考 `app-test-control` 后，建议把“同一套工具底座服务不同测试场景”作为后续架构目标，但第一阶段只实现其中最窄、最可控的一条。各入口的边界如下：

| 工作流入口 | 触发方式 | 输入 | 输出 | 阶段 |
| --- | --- | --- | --- | --- |
| Excel Case Run | `python -m autoairtest run --excel ...` | Excel 自然语言测试用例 | Test Session、逐用例证据、HTML 报告、可选 Excel 回写 | MVP |
| Focused Smoke | `--case-filter` 或指定 1 到 2 条用例 | 少量跳转/展示类用例 | 快速验证 Airtest/Poco/报告链路 | MVP |
| DevTest | 后续 `devtest --scope <feature>` 或 Agent Skill | 最近代码改动或指定功能范围 | 窄范围自测报告 | 后续 |
| Exploratory QA | 后续 `qa --max-steps ...` | App 包名、探索预算、风险 blocklist | 状态图、覆盖统计、崩溃列表 | 后续 |
| Repro Minimize | 后续 `minimize <session> --crash <id>` | 已有 crash 的 Test Session | 经 replay 验证的最小复现路径 | 后续 |
| Smart QA | 后续读取 PRD/路由/页面信号 | 业务流候选和用户确认 | 业务感知测试计划，再交给 Case Run 或 DevTest 执行 | 后续 |

这些入口共享同一套 Tool Layer、Evidence Store、Log Collector、Crash Analyzer 和 Reporter。区别只在“谁生成计划、计划是否需要用户确认、是否允许探索”。MVP 不允许自由探索式 Agent 绕过 ExecutionPlan、Risk Policy 和 Guardrails。

---

## 6. 数据模型

### 6.1 NaturalLanguageTestCase

```json
{
  "case_id": "TC_国内指数模块数据正确",
  "business_module": "股指",
  "feature_module": "国内指数",
  "feature_item": "一级宫格页面",
  "test_purpose": "数据校验",
  "priority": "middle",
  "precondition": "",
  "operation_description": "行情-股指：查看国内指数模块数据显示",
  "parameters": "",
  "expected_result": "1、科创综指排在第四位...\n2、数据展示正确..."
}
```

说明：

1. `case_id` 直接使用 `TC_用例名称`。
2. 如果后续出现重复 `TC_用例名称`，系统应追加行号生成内部 ID，例如 `TC_个股详情页科创综指展示正常__row_6`。
3. 空单元格统一转换为空字符串，不使用 `null` 进入 Agent Prompt。

### 6.1.1 InterpretationRationale

Planning Agent 对关键解释必须输出结构化依据，不能只输出自然语言执行计划。

```json
{
  "rationale_id": "ir1",
  "original_expression": "自选",
  "normalized_meaning": "我的自选",
  "interpretation_type": "navigation_alias",
  "confidence": 0.92,
  "matched_skill_rules": ["navigation_alias.self_selected"],
  "basis": "命中证券 App 导航别名规则：自选在当前 UI 中展示为我的自选。",
  "human_review_required": false
}
```

必须包含 InterpretationRationale 的场景：

1. 导航别名，例如 `自选` 归一为 `我的自选`。
2. 目标元素归一，例如 `底部指数` 归一为底部操作栏中的指数入口。
3. 动作风险分类。
4. 验证目标分类。
5. 任何影响是否允许自动执行的低置信度判断。

### 6.2 ExecutionPlan

```json
{
  "case_id": "TC_国内指数更多跳转正常",
  "preconditions": [
    {
      "type": "app_state",
      "description": "App 已登录并位于可进入行情页的状态",
      "mvp_handling": "manual_prepare_or_precheck"
    }
  ],
  "actions": [
    {
      "action_id": "a1",
      "intent": "navigate",
      "description": "进入行情页",
      "target": "行情",
      "action_risk_level": "low",
      "interpretation_rationale_ids": ["ir1"],
      "preferred_locator": "poco_semantic"
    },
    {
      "action_id": "a2",
      "intent": "navigate",
      "description": "进入股指-国内指数区域",
      "target": "国内指数",
      "action_risk_level": "low",
      "interpretation_rationale_ids": ["ir2"],
      "preferred_locator": "poco_semantic"
    },
    {
      "action_id": "a3",
      "intent": "tap",
      "description": "点击右侧更多按钮",
      "target": "更多",
      "target_context": "国内指数模块右侧",
      "action_risk_level": "low",
      "interpretation_rationale_ids": ["ir3"],
      "preferred_locator": "poco_semantic"
    }
  ],
  "interpretation_rationales": [
    {
      "rationale_id": "ir3",
      "original_expression": "点击右侧“更多”按钮",
      "normalized_meaning": "点击国内指数模块右侧的更多入口",
      "interpretation_type": "target_normalization",
      "confidence": 0.88,
      "matched_skill_rules": ["securities_navigation.domestic_index_more"],
      "basis": "操作描述限定在行情-股指-国内指数路径下，右侧更多按钮指向当前模块的更多入口。",
      "human_review_required": false
    }
  ],
  "verification_goals": [
    {
      "goal_id": "v1",
      "claim": "页面跳转至国内指数列表页",
      "evidence_priority": ["poco_tree", "ocr_text", "screenshot"],
      "human_review_required": false
    },
    {
      "goal_id": "v2",
      "claim": "国内指数列表中科创综指排在第4位",
      "evidence_priority": ["poco_tree", "ocr_text", "screenshot"],
      "human_review_required": false
    }
  ]
}
```

### 6.3 ActionResult

```json
{
  "action_id": "a3",
  "status": "success",
  "locator_level": "poco_semantic",
  "target_element": {
    "text": "更多",
    "bounds": [995, 320, 1070, 380],
    "clickable": true,
    "confidence": 0.86
  },
  "before_screenshot": "01_before_a3.png",
  "after_screenshot": "02_after_a3.png",
  "element_summary_before": "elements_before_a3.json",
  "element_summary_after": "elements_after_a3.json",
  "execution_rationale_id": "er3",
  "notes": []
}
```

### 6.4 ExecutionTrace、ExecutionRationale 与 PlanAmendment

ExecutionPlan 是原始计划，执行阶段不得覆盖。真实执行过程必须追加到 ExecutionTrace。

```json
{
  "trace_id": "t3",
  "trace_type": "action",
  "action_id": "a3",
  "planned_target": "更多",
  "normalized_target": "国内指数模块右侧更多入口",
  "candidate_elements": [
    {
      "text": "更多",
      "bounds": [995, 320, 1070, 380],
      "confidence": 0.88,
      "matched_skill_rules": ["securities_navigation.domestic_index_more"]
    }
  ],
  "selected_element": {
    "text": "更多",
    "bounds": [995, 320, 1070, 380],
    "confidence": 0.88
  },
  "action_risk_level": "low",
  "execution_rationale": "目标位于国内指数模块右侧，文本匹配且区域匹配。",
  "before_evidence": ["screenshots/020_after_open_index.png", "element_summaries/020_after_open_index.json"],
  "after_evidence": ["screenshots/030_after_tap_more.png", "element_summaries/030_after_tap_more.json"],
  "correction_step": null
}
```

当执行阶段发现计划目标需要结合真实 UI 证据补充解释时，记录 PlanAmendment，而不是修改原 ExecutionPlan。

```json
{
  "amendment_id": "pa1",
  "action_id": "a1",
  "original_target": "自选",
  "resolved_target": "我的自选",
  "reason": "命中 navigation_alias.self_selected，且当前首页底部导航存在我的自选入口。",
  "matched_skill_rules": ["navigation_alias.self_selected"],
  "evidence_files": ["element_summaries/010_home.json"]
}
```

执行期纠错预算按动作风险等级控制：

| 动作风险等级 | 自动纠错预算 | 处理策略 |
| --- | --- | --- |
| low | 最多 3 次 | 允许返回、重新定位、刷新证据、切换别名等可恢复纠错 |
| medium | 最多 1 次 | 允许有限纠错，必须保存更强证据和原因 |
| high | 0 次 | 阻塞或要求人工确认 |

### 6.5 VerificationGoal

```json
{
  "goal_id": "v2",
  "claim": "科创综指排在第四位",
  "category": "element_order",
  "expected_entities": ["上证指数", "深证成指", "北证50", "科创综指"],
  "evidence_priority": ["poco_tree", "ocr_text", "screenshot"],
  "human_review_required": false
}
```

### 6.6 PreliminaryJudgment

```json
{
  "goal_id": "v2",
  "preliminary_status": "pass",
  "confidence": 0.82,
  "basis": "Poco 控件树中同一列表区域的文本顺序为：上证指数、深证成指、北证50、科创综指。",
  "manual_review_reason": "",
  "structured_details": {
    "expected": ["上证指数", "深证成指", "北证50", "科创综指"],
    "observed": ["上证指数", "深证成指", "北证50", "科创综指"],
    "missing": [],
    "unexpected": []
  },
  "evidence_files": [
    "elements_after_a3.json",
    "02_after_a3.png"
  ],
  "human_review_required": false,
  "review_reason": ""
}
```

`preliminary_status` 可取值：

| 值 | 含义 |
| --- | --- |
| `pass` | 自动证据支持该验证目标通过 |
| `fail` | 自动证据支持该验证目标不通过 |
| `uncertain` | 证据不足或 LLM 置信度不足 |
| `manual_required` | 该目标需要人工复核，例如数据正确性、颜色规则、证据缺口、冲突证据或低置信度解释 |
| `blocked` | 前置动作失败，未能进入验证阶段 |

`manual_review_reason` 建议取值：

| 值 | 含义 |
| --- | --- |
| `data_correctness` | 行情数据正确性缺少外部 Oracle |
| `color_rule` | 颜色规则受主题、业务口径或视觉识别影响 |
| `verification_evidence_gap` | 证据不完整或出现非预期元素 |
| `ambiguous_business_rule` | 业务规则存在歧义 |
| `conflicting_evidence` | Poco、OCR、截图等证据冲突 |
| `low_confidence_interpretation` | Planning 或 Execution 的解释置信度不足 |
| `high_risk_action_confirmation` | 高风险动作必须人工确认 |

`basis` 是给人看的说明；`structured_details` 是给程序、报告筛选、统计和后续评估使用的结构化字段。机器逻辑不应依赖解析 `basis` 文本。

### 6.7 RunResult

```json
{
  "case_id": "TC_大盘指数数据显示正确",
  "run_status": "manual_required",
  "started_at": "2026-06-14T22:50:00+08:00",
  "finished_at": "2026-06-14T22:51:30+08:00",
  "action_results": [],
  "preliminary_judgments": [],
  "evidence_dir": "runs/20260614-225000/TC_大盘指数数据显示正确",
  "summary": "页面顺序初步满足预期；行情数据正确性和颜色规则需要人工根据截图复核。"
}
```

`run_status` 的汇总规则：

| 条件 | run_status |
| --- | --- |
| 任一关键动作无法完成 | `blocked` |
| 任一非人工验证目标初判失败 | `fail_preliminary` |
| 存在数据正确性、颜色规则、证据缺口、冲突证据、低置信度解释等人工复核目标 | `manual_required` |
| 所有目标自动初判通过且无需人工复核 | `pass_preliminary` |
| 证据不足但流程执行完成 | `uncertain` |

### 6.8 TestSession

TestSession 表示一次受控测试运行，可以包含一条或多条自然语言测试用例。它借鉴 `app-test-control` 的 session 思路，但路径继续使用本项目现有的 `runs/` 目录。

```json
{
  "session_id": "20260621-103000_domestic-index",
  "workflow": "excel_case_run",
  "started_at": "2026-06-21T10:30:00+08:00",
  "finished_at": "",
  "app_package": "com.example.securities",
  "adb_serial": "DEVICE_SERIAL",
  "config_snapshot": "config.resolved.json",
  "case_count": 2,
  "status": "running"
}
```

设计要求：

1. TestSession 是运行级容器，不替代单条用例的 RunResult。
2. `config_snapshot` 保存合并后的配置，方便复现实验环境。
3. 每个 TestSession 必须有追加式 `steps.jsonl`，即使 MVP 只执行 Excel 用例。
4. 崩溃、ANR 或严重工具错误写入 `crashes.jsonl`，同时关联 case_id 和 step_index。
5. `state_graph.json` 在 MVP 可为空或不生成；只有探索 QA 或循环规避需要时才启用。

### 6.9 CrashSignature

CrashSignature 用于把同一类崩溃归并起来，避免报告只堆叠重复 log。

```json
{
  "signature_id": "a3f2b89c1d0e",
  "kind": "java",
  "exception_class": "java.lang.NullPointerException",
  "top_frames_normalized": [
    "com.example.LoginActivity.onClick",
    "android.view.View.performClick"
  ],
  "process": "com.example.securities",
  "source": "logcat",
  "first_seen_step": 4
}
```

MVP 的签名规则保持简单：优先使用 crash kind、异常类、归一化 top 3 frame 和进程名计算短 hash。ANR 可用 `kind + process + reason` 归并；native crash 可补充 signal。签名用于聚类和复盘，不应作为自动定位根因的唯一依据。

### 6.10 ReproductionPath

ReproductionPath 是触发崩溃或阻塞状态的一组动作索引，必须保留原始路径。

```json
{
  "crash_id": "c1",
  "case_id": "TC_国内指数更多跳转正常",
  "original_repro_path": [1, 2, 3, 4],
  "minimized_repro_path": [],
  "minimized_confidence": "not_run"
}
```

第一版只记录 `original_repro_path`。后续引入 delta-debugging 时，只能新增 `minimized_repro_path` 或 sidecar 文件，不能覆盖原始复现路径。

### 6.11 StateGraph

StateGraph 表示页面指纹和动作转移关系，主要服务后续探索 QA、循环规避和覆盖分析。

```json
{
  "pages": {
    "page_a3f2b89c": {
      "first_seen": "2026-06-21T10:30:12+08:00",
      "visit_count": 2,
      "summary": "行情-股指-首页",
      "elements_seen": ["text:国内指数", "text:更多"]
    }
  },
  "edges": [
    {
      "from": "page_a3f2b89c",
      "action": "click text:更多",
      "to": "page_b91c0011",
      "case_id": "TC_国内指数更多跳转正常"
    }
  ]
}
```

MVP 中 StateGraph 只作为可选诊断数据：Workflow 仍按 ExecutionPlan 执行，不允许因为状态图发现“未探索元素”就自动点击。进入 Exploratory QA 阶段后，状态图才参与选择下一步动作，并且必须受 blocklist、Action Risk Level 和探索预算约束。

---

## 7. 主流程设计

### 7.1 执行流程

```text
1. 解析命令行参数，并按优先级合并默认配置、配置文件和命令行覆盖项
2. 运行轻量 doctor 检查：Python 依赖、ADB、设备、输出目录、配置必填项
3. 创建 TestSession，保存 config.resolved.json 和 session_meta.json
4. 检查 Android 真机连接
5. 启动或唤醒被测证券 App
6. 检查 Airtest 截图能力
7. 检查 Poco 控件树 dump 能力
8. 启动 Log Collector，按 session 记录 logcat 时间窗口
9. 读取 test-cases.xlsx
10. 对每条用例：
   10.1 创建用例证据目录
   10.2 保存初始截图，采集初始 Poco 证据并落盘元素摘要
   10.3 Planning Agent 基于 Skills 生成 ExecutionPlan、InterpretationRationale 和动作风险等级
   10.4 Workflow 按 ExecutionPlan 推进动作
   10.5 Execution Agent 在当前 UI 证据和纠错预算内处理执行期歧义
   10.6 每个关键动作和纠错动作后保存截图、元素摘要、ExecutionTrace、steps.jsonl 和必要运行日志
   10.7 每个关键动作后按时间窗口检查 crash/ANR，并在命中时写入 crashes.jsonl 和 CrashSignature
   10.8 Rule Engine 基于 Poco/OCR 证据优先处理确定性验证目标
   10.9 Verification Agent 解释证据缺口、冲突证据和人工复核原因
   10.10 必要时执行受限 Evidence Recollection，并写入 ExecutionTrace
   10.11 对数据正确性、颜色规则、证据缺口等目标标记结构化人工复核原因
   10.12 保存 RunResult
11. 停止 Log Collector
12. 生成 HTML 报告
13. 可选回写 Excel 的测试结果和备注
```

### 7.2 用例执行前检查

执行每条用例前需要确认：

| 检查项 | 通过条件 | 失败处理 |
| --- | --- | --- |
| 设备在线 | `adb devices` 可见且状态为 device | 停止本轮执行 |
| 屏幕可操作 | Airtest 可截图，屏幕未锁定 | 尝试唤醒一次，失败则 blocked |
| App 可用 | package 存在，可启动或已在前台 | 启动失败则 blocked |
| Poco 可用 | 可 dump 控件树 | 降级为截图/OCR执行，但报告标注风险 |
| 登录状态 | 当前页面可进入行情相关路径 | MVP 可人工准备；检测失败则提示人工处理 |
| logcat 可用 | 能执行基础 logcat 命令或明确标记不可用 | 不阻断用例执行，但报告标注崩溃监测能力缺失 |
| 输出目录可写 | 能创建 TestSession 和 case 目录 | 停止本轮执行 |

登录状态不建议第一版自动处理。证券 App 常包含隐私、验证码、手势、交易权限等流程，自动登录会扩大风险面。

---

## 8. Planner 设计

本章中的 Planner 指 Planning Agent。它不是简单的 Prompt 输出器，而是负责把测试人员不完全规范、因人而异的自然语言表达归一到可执行计划。例如用例写 `自选`，但 UI 上实际展示为 `我的自选` 时，应通过 Navigation Alias Skill 解释为同一目标，并输出结构化依据。

### 8.1 Planner 输入

Planner 接收：

1. Excel 用例字段。
2. 当前 App 起始状态说明。
3. 证券 App 测试 Skills，包括导航别名、页面路径、指数顺序、风险规则和验证规则。
4. 可用工具列表。
5. 约束：不能编造外部数据源，不能把数据正确性判成自动最终结论。

### 8.2 Planner 输出要求

Planner 必须输出严格 JSON：

```json
{
  "case_id": "string",
  "understanding": "string",
  "preconditions": [],
  "actions": [],
  "interpretation_rationales": [],
  "verification_goals": [],
  "manual_review_notes": []
}
```

Planner 对关键解释必须输出 InterpretationRationale，包括：

1. 原始表达。
2. 归一结果。
3. 解释类型。
4. 置信度。
5. 命中的 Skill Rule。
6. 人类可读依据。
7. 是否需要人工确认。

置信度不足或 Skill Rule 冲突时，Planner 不应强行生成可自动执行计划，而应将对应步骤或验证目标标记为需要人工确认。

### 8.3 操作描述解析规则

| 输入形态 | 解析规则 |
| --- | --- |
| `行情-股指` | 拆成导航路径：行情页 -> 股指区域 |
| `行情-股指-国内指数` | 拆成三级路径：行情页 -> 股指 -> 国内指数 |
| `点击六宫格中的科创综指` | 目标是文本为科创综指的宫格项，限定在国内指数宫格区域 |
| `点击右侧“更多”按钮` | 目标是更多按钮，位置约束为当前模块右侧 |
| `底部操作栏-点击底部指数` | 目标是底部操作栏里的指数入口 |
| `查看...数据显示` | 不产生点击动作，只产生页面进入或停留后的验证目标 |
| `自选` | 通过导航别名 Skill 归一到当前 UI 的可见入口，例如 `我的自选`；必须记录 InterpretationRationale |

### 8.4 预期结果拆分规则

预期结果通常包含多条声明，Planner 应拆成多个验证目标：

| 预期表达 | 验证目标类型 | 自动化策略 |
| --- | --- | --- |
| `科创综指排在第四位` | element_order | Poco 文本和 bounds 排序优先 |
| `展示顺序为：A、B、C、D` | element_order | Poco 同区域元素顺序优先 |
| `跳转到...页面` | navigation | Poco 页面标题、选中 tab、关键文本 |
| `弹出...弹框` | popup_visible | Poco 弹层容器、关键文本、截图 |
| `选中上证指数` | selected_state | Poco selected 属性、样式类、文本区域 |
| `数据展示正确` | data_correctness | 截图留痕，人工复核 |
| `两端/自营对比一致` | data_consistency | 截图留痕，人工复核 |
| `红涨绿跌黑平` | color_rule | 截图留痕，LLM/像素初判，人工复核 |

### 8.5 动作风险分类规则

Planner 必须为每个 PlanAction 标注 `action_risk_level`。

| 风险等级 | 示例 | 自动化策略 |
| --- | --- | --- |
| low | 页面跳转、切 tab、返回、滚动、打开/关闭弹框 | 允许 Execution Agent 在预算内自动纠错 |
| medium | 输入搜索词、切换筛选条件、切换市场、进入详情页 | 允许最多一次自动纠错，并保存更强证据 |
| high | 交易、下单、登录退出、账户设置、添加/删除自选、确认金融操作 | 不允许自动纠错，必须阻塞或人工确认 |

风险等级不是元素定位置信度。一个元素即使定位置信度高，只要动作本身可能影响账户、交易或持久化用户数据，就必须按高风险处理。

---

## 9. Executor 设计

### 9.1 执行原则

Executor 的目标是稳定完成操作，而不是判断结果。判断结果交给 Verifier。这里的 Executor 由受控 Workflow 和受限 Execution Agent 共同完成：Workflow 控制步骤、预算和审计边界；Execution Agent 只在当前动作目标、当前 UI 证据和风险策略内处理歧义与纠错。

执行原则：

1. 每个动作执行前保存截图，并采集 Poco 证据生成结构化元素摘要。
2. 每个动作只做一件事，例如点击、输入、滑动、返回。
3. 每次点击后等待页面稳定，再保存动作后证据。
4. 如果元素定位结果有多个候选，优先使用上下文、bounds、可点击属性和页面区域消歧。
5. 如果 LLM 输出坐标，必须校验坐标在屏幕范围内，并保存原因。
6. 每个执行期选择都必须生成 ExecutionRationale。
7. 原 ExecutionPlan 不允许被覆盖，执行期修正只能追加为 ExecutionTrace 或 PlanAmendment。

### 9.2 三级定位漏斗

#### Level 1：Poco 控件树语义匹配

适用场景：

1. Tab、按钮、列表项、宫格项有可读文本。
2. 元素有可点击属性。
3. 页面结构能被 Poco dump。

输入：

1. 当前控件树摘要。
2. 动作目标，例如“行情”“国内指数”“更多”“科创综指”。
3. 目标上下文，例如“国内指数模块右侧”。

输出：

```json
{
  "matched": true,
  "element_id": "poco-node-123",
  "text": "更多",
  "bounds": [995, 320, 1070, 380],
  "reason": "文本匹配，且位于国内指数模块右侧",
  "confidence": 0.88
}
```

#### Level 2：截图 + 控件树联合定位

适用场景：

1. 多个候选元素文本相同。
2. 目标由相对位置描述，例如“右侧更多”“底部指数”。
3. Poco 能看到元素，但无法仅凭文本消歧。

注意：Level 2 是执行阶段的定位策略，不是验证阶段的优先策略。验证阶段仍应先使用 Poco 证据。

#### Level 3：图像识别 / OCR / 坐标兜底

适用场景：

1. 自定义渲染控件。
2. WebView 或 Canvas 区域。
3. Poco 控件树缺失目标文本。
4. 纯图标按钮。

兜底顺序：

1. OCR 识别文字并点击文字中心。
2. Airtest 模板匹配。
3. LLM 看截图返回坐标。
4. 人工标记模板或中止。

Level 3 必须降低置信度，并在报告中明确标注。

### 9.3 执行期歧义与纠错

执行期歧义包括：

1. 当前 UI 中存在多个相似候选，例如 `我的自选`、`自选股`、`自选管理`。
2. UI 可见文案和计划目标不完全一致。
3. 点击后页面状态与预期不一致。
4. 页面未稳定、弹层遮挡、候选元素区域不符合上下文。

Execution Agent 可以在动作风险预算内执行纠错，但必须满足：

1. 只处理可恢复误操作，不能默默继续。
2. 纠错前后必须保存 Interface Evidence。
3. 每次纠错必须写入 ExecutionTrace。
4. 如果纠错超过预算，当前用例进入 `blocked` 或 `manual_required`。
5. 高风险动作不允许自动纠错。

纠错示例：

```text
计划目标：自选
UI 证据：底部 tab 存在“我的自选”，设置页入口存在“自选管理”
选择：点击“我的自选”
依据：命中 navigation_alias.self_selected，且页面上下文为首页底部导航
风险等级：low
纠错预算：未消耗
```

### 9.4 页面稳定等待

动作完成后不应立即验证，应等待页面稳定：

1. 固定最小等待，例如 1 秒。
2. 连续两次截图 hash 变化低于阈值。
3. 或连续两次 Poco 控件树关键节点数量稳定。
4. 最长等待不超过配置超时，例如 8 秒。

### 9.5 页面级层级失效标记

参考 `app-test-control` 的 `ui_busy` 处理方式，MVP 应避免在同一类失效页面上反复等待 Poco dump。若当前页面出现以下情况之一，可为当前 page fingerprint 标记 `hierarchy_unreliable=true`：

1. Poco dump 连续超时或抛出 UI busy 类错误。
2. 可见控件数异常少，例如少于 5 个，且截图显示明显存在复杂界面。
3. 同一页面连续两次 dump 结构差异过大，但截图主要内容稳定。
4. WebView、Flutter Canvas、自绘行情图等页面无法暴露关键元素。

被标记后，本页面后续定位策略调整为：

1. 不再每步重复尝试完整 dump，直到页面发生明显跳转或用户手动清除标记。
2. 先使用已保存的元素摘要、OCR 文本、截图区域和 Skill Rules 做受限定位。
3. 所有坐标或视觉兜底动作必须写入 ExecutionRationale，并标记 `via_screenshot=true`。
4. 若动作风险等级为 medium/high，不允许仅凭截图兜底继续执行，除非人工确认。

### 9.6 日志与崩溃监测

每个关键动作后，Workflow 应在当前 Test Session 的时间窗口内调用 Log Collector：

```text
1. 动作前记录 step_start_time，并按配置清理或圈定 logcat 窗口
2. 执行动作并等待页面稳定
3. 保存截图和元素摘要
4. 查询 step_start_time 之后的 crash/ANR/native crash 线索
5. 若命中：
   5.1 提取 CrashSignature
   5.2 写入 crashes.jsonl
   5.3 将当前已执行动作索引写入 original_repro_path
   5.4 当前用例进入 blocked 或 fail_preliminary
6. 若未命中：
   6.1 在 steps.jsonl 标记 crash_count=0
```

第一版只需要覆盖 Android logcat 的常见模式：

| 类型 | 关键线索 |
| --- | --- |
| Java crash | `FATAL EXCEPTION`、`AndroidRuntime`、异常类和 top frames |
| ANR | `ANR in`、进程名、reason |
| Native crash | `*** *** *** *** *** ***`、signal、tombstone 线索 |

logcat 噪音不能直接导致用例失败。只有匹配到可归因到被测包名或当前时间窗口的崩溃/ANR，才记录为结构化 crash；否则作为 warning 写入报告。

---

## 10. Verifier 设计

验证阶段采用 Rule Engine 优先、Verification Agent 辅助解释、Human Review 最终裁决的分工。

1. Rule Engine 处理确定性检查，例如完整顺序匹配、明确顺序错误、文本存在、弹框出现。
2. Verification Agent 处理证据缺口、冲突证据、UI 文案差异、低置信度解释和人工复核说明。
3. Human Review 处理行情数据正确性、颜色业务口径、证据不完整等灰区。

### 10.1 验证优先级

验证阶段的证据优先级为：

```text
1. Poco 控件树、元素文本、元素 bounds、元素属性
2. OCR 文本和 OCR 坐标
3. 截图证据
4. LLM 视觉初判
5. 人工复核
```

这与元素定位阶段不同。定位可以使用截图辅助找目标；验证应先看结构化界面证据，只有结构化证据不足时才依赖截图。

### 10.2 截图强制留痕

每条用例至少保存：

1. 用例开始前截图。
2. 关键动作后截图。
3. 验证时截图。
4. 失败或不确定时额外截图。

即使验证由 Poco 完成，也必须保存截图。截图用于：

1. 人工复核。
2. 报告展示。
3. 问题追溯。
4. 后续模板库建设。
5. LLM 初判结果的可审计性。

### 10.3 验证目标分类

#### 10.3.1 页面跳转验证

示例：`跳转到该指数行情分时页面`

优先证据：

1. 页面标题或关键文本包含目标指数名。
2. 当前页面存在分时、五日、K线等行情详情页特征元素。
3. 选中状态或页面区域显示目标指数。
4. 截图作为人工核验依据。

输出：

```json
{
  "preliminary_status": "pass",
  "basis": "Poco 控件树显示当前页存在“科创综指”和“分时/K线”区域，符合指数行情分时页面特征。",
  "human_review_required": false
}
```

#### 10.3.2 元素顺序验证

示例：`展示指数及顺序为：上证指数、深证成指、北证50、科创综指`

策略：

1. 从 Poco 控件树提取候选文本节点。
2. 按同一容器或相近 bounds 分组。
3. 按屏幕阅读顺序排序：先 y 从小到大，再 x 从小到大。
4. 检查目标序列是否完整出现。
5. 对“排在第四位”检查目标在候选列表中的序号。
6. 保存排序后的元素摘要和截图。

如果 Poco 未提取到完整文本，则使用 OCR 文本坐标重复同样排序逻辑。

顺序验证结果分类：

| 情况 | 示例 | 处理 |
| --- | --- | --- |
| 证据完整且顺序正确 | 期望 A-B-C-D，证据 A-B-C-D | `pass` |
| 证据完整但顺序错误 | 期望 A-B-C-D，证据 A-C-B-D | `fail` |
| 证据缺失 | 期望 A-B-C-D，证据 A-B-C | `manual_required`，原因 `verification_evidence_gap` |
| 出现非预期元素 | 期望 A-B-C-D，证据 A-B-C-E | `manual_required`，原因 `verification_evidence_gap` |
| 证据扩展异常 | 期望 A-B-C-D，证据 A-B-C-D-E | 默认 `manual_required`，除非 Skill Rule 明确规定通过或失败 |

证据缺失或额外元素不应默认判失败，也不应回推给 Executor 盲目纠错。它属于验证阶段的证据解释问题，应记录 `structured_details.expected / observed / missing / unexpected`，并给出人工复核建议。

#### 10.3.3 弹框展示验证

示例：`弹出指数分时图弹框，选中上证指数`

策略：

1. Poco 检查当前页面是否出现弹层容器、遮罩、弹框标题或指数列表。
2. 检查弹框内是否出现上证指数、深证成指、科创综指等关键文本。
3. 检查是否存在选中状态属性；如果 Poco 不提供 selected 属性，则交由截图和人工复核。
4. 截图保存弹框完整区域。

#### 10.3.4 数据正确性验证

示例：

1. `数据展示正确`
2. `与该只股票个股行情页面数据一致`
3. `两端/自营对比一致`

MVP 策略：

1. 系统采集截图和 Poco 元素证据，并落盘结构化元素摘要。
2. 系统尽量抽取页面上可见数据，例如指数点位、涨跌幅、日期、名称。
3. LLM 可生成“初步观察摘要”，例如“截图中科创综指可见，数值字段均有展示”。
4. 系统不自动判定行情数据是否真实正确。
5. RunResult 标记为 `manual_required`。
6. 报告明确提示人工根据截图判断数据正确性。

示例输出：

```json
{
  "preliminary_status": "manual_required",
  "basis": "已保存大盘指数模块截图和结构化元素摘要；可见上证指数、深证成指、北证50、科创综指等字段。行情数据正确性需要人工对照业务口径复核。",
  "human_review_required": true,
  "review_reason": "MVP 未接入行情外部数据源，无法自动确认数值真实正确。"
}
```

#### 10.3.5 颜色规则验证

示例：`数据字体颜色：红涨绿跌黑平`

MVP 策略：

1. 截图必须保存。
2. 如果 UI 树暴露颜色属性，则读取属性作为初步证据。
3. 如果 UI 树不暴露颜色属性，可用截图像素或 LLM 视觉做初步判断。
4. 最终仍建议人工复核，因为不同主题、夜间模式、涨跌颜色配置可能影响判断。

### 10.4 Evidence Recollection

当验证阶段发现 Verification Evidence Gap 时，可以在返回人工复核前执行受限证据补采。证据补采不是执行纠错，也不是新一轮业务导航。

默认补采预算为 2 次：

1. 第一次只刷新当前屏幕证据，例如重新 dump Poco、重新 OCR、重新截图。
2. 第二次允许同一验证上下文内的低风险可逆显隐动作，例如滚动当前列表、横向滑动当前区域、展开当前区域、关闭遮挡弹层或切回当前验证区域。

证据补采不允许：

1. 跳转到新页面。
2. 点击业务按钮。
3. 改变筛选条件。
4. 输入搜索词。
5. 进入详情页。
6. 执行中风险或高风险动作。

每次 Evidence Recollection 都必须写入 ExecutionTrace，包含触发原因、关联 VerificationGoal、动作风险等级、前后证据和是否补足缺口。

---

## 11. 当前 7 条用例的执行设计

### 11.1 TC_国内指数模块数据正确

操作：

1. 进入行情。
2. 进入股指。
3. 定位国内指数模块。
4. 不点击，仅采集模块证据。

验证目标：

1. 国内指数模块包含上证指数、深证成指、北证50、科创综指。
2. 科创综指排在第四位。
3. 数据展示正确。
4. 模块数据与个股行情页面数据一致。

自动化处理：

1. 目标 1、2 使用 Poco 文本顺序初判。
2. 目标 3、4 标记人工复核，保存截图和结构化元素摘要。

### 11.2 TC_国内指数宫格跳转正常

操作：

1. 进入行情。
2. 进入股指。
3. 进入国内指数模块。
4. 点击六宫格中的科创综指。

验证目标：

1. 页面跳转到科创综指行情分时页面。

自动化处理：

1. Poco 检查页面关键文本：科创综指、分时、K线等。
2. 截图保存跳转后页面。

### 11.3 TC_国内指数更多跳转正常

操作：

1. 进入行情。
2. 进入股指。
3. 进入国内指数模块。
4. 点击右侧“更多”按钮。

验证目标：

1. 页面跳转至国内指数列表页。
2. 列表新增科创综指。
3. 科创综指排在列表第 4 位。

自动化处理：

1. Poco 检查列表页标题或列表特征。
2. Poco/OCR 提取列表顺序。
3. 截图保存列表页。

### 11.4 TC_大盘指数数据显示正确

操作：

1. 进入行情。
2. 进入 A 股。
3. 进入沪深京。
4. 查看大盘指数模块。

验证目标：

1. 科创综指排在第四位。
2. 展示顺序为上证指数、深证成指、北证50、科创综指。
3. 大盘情况、日期、指数数据显示正确。
4. 两端/自营对比一致。
5. 红涨绿跌黑平。

自动化处理：

1. 目标 1、2 使用 Poco 文本顺序初判。
2. 目标 3、4、5 保存截图，LLM 生成初步观察摘要，标记人工复核。

### 11.5 TC_个股详情页科创综指展示正常（有行业板块）

前置条件：

1. 需要进入一个有行业板块的券商个股详情页。
2. 第一版建议人工预置到符合条件的个股，或在配置中指定测试股票代码。

操作：

1. 在 A 股分时页面点击底部操作栏的指数入口。

验证目标：

1. 弹出指数分时图弹框。
2. 默认选中上证指数。
3. 顺序为行业板块、上证指数、深证成指、科创综指、北证50、创业板指。

自动化处理：

1. Poco 检查弹框和关键文本。
2. Poco 检查顺序。
3. 选中状态若控件树不暴露，则截图留痕并人工复核。

### 11.6 TC_个股详情页科创综指展示正常（无行业板块）

前置条件：

1. 需要进入沪深基金、B股、新三板、债券等个股详情页之一。
2. 第一版建议配置一个固定入口或由人工预置页面。

操作：

1. 点击底部操作栏的指数入口。

验证目标：

1. 弹出指数分时图弹框。
2. 默认选中上证指数。
3. 顺序为上证指数、深证成指、科创综指、北证50、创业板指。

自动化处理：

1. Poco 检查弹框、关键文本和顺序。
2. 截图保存弹框证据。

### 11.7 TC_自选顶部指数展示正常

操作：

1. 进入沪深 A 股个股详情页。
2. 点击自选顶部指数。

验证目标：

1. 弹出指数分时图弹框。
2. 科创综指排在第四位。
3. 顺序为上证指数、深证成指、北证50、科创综指。

自动化处理：

1. Poco 检查弹框。
2. Poco/OCR 检查顺序。
3. 截图保存。

---

## 12. 证据存储设计

### 12.1 目录结构

```text
runs/
└── 20260614-225000/
    ├── session_meta.json
    ├── config.resolved.json
    ├── run_summary.json
    ├── steps.jsonl
    ├── crashes.jsonl
    ├── state_graph.json
    ├── report.html
    ├── report_assets/
    ├── logs/
    │   ├── logcat.txt
    │   └── doctor.json
    └── cases/
        └── TC_国内指数更多跳转正常__row_4/
            ├── case.json
            ├── execution_plan.json
            ├── interpretation_rationales.json
            ├── action_results.json
            ├── execution_trace.json
            ├── plan_amendments.json
            ├── verification_result.json
            ├── logs.txt
            ├── crash_refs.json
            ├── screenshots/
            │   ├── 000_initial.png
            │   ├── 010_after_open_market.png
            │   ├── 020_after_open_index.png
            │   ├── 030_after_tap_more.png
            │   └── 090_verify.png
            ├── element_summaries/
            │   ├── 000_initial.json
            │   ├── 010_after_open_market.json
            │   ├── 020_after_open_index.json
            │   ├── 030_after_tap_more.json
            │   └── 090_verify.json
            └── ocr/
                └── 090_verify.json
```

### 12.2 文件命名规则

1. 运行目录本身就是 Test Session 目录，使用时间戳和可选场景名生成，例如 `20260621-103000_domestic-index`。
2. 用例目录使用 `TC_用例名称__row_N`，避免重名。
3. 截图使用三位序号，保证按时间排序。
4. 元素摘要序号与截图序号对应。
5. `steps.jsonl` 和 `crashes.jsonl` 是 session 级追加式记录，不能依赖解析 HTML 报告反推。
6. `state_graph.json` 在 MVP 可为空；若启用，应只记录页面指纹、元素 key 和边，不保存完整敏感文本。
7. 所有 LLM 输入输出应保存为 JSON，便于复盘。
8. Planning Agent 的 InterpretationRationale、Execution Agent 的 ExecutionTrace、Verification Agent 的结构化判断结果必须分别落盘。
9. 报告中引用相对路径，便于打包整个 `runs` 目录。

### 12.3 敏感信息处理

证券 App 可能展示账户、资产、手机号等敏感信息。MVP 应提供配置：

```yaml
evidence:
  redact_sensitive_text: true
  sensitive_keywords:
    - 资金账号
    - 手机号
    - 资产
    - 持仓
  screenshot_redaction: false
```

第一版至少应对元素摘要中的文本做脱敏。截图脱敏可作为后续增强，因为截图区域识别和遮盖需要额外工作量。

---

## 13. 报告设计

### 13.1 HTML 报告结构

报告首页：

1. 执行时间。
2. 设备信息。
3. App 包名和版本。
4. 用例总数。
5. 初步通过数。
6. 初步失败数。
7. 阻塞数。
8. 需要人工复核数。

用例详情页：

1. Excel 原始字段。
2. 执行计划。
3. 动作时间线。
4. 每个动作的截图和元素摘要。
5. 每个动作的 ExecutionRationale、纠错记录和 PlanAmendment。
6. 每个验证目标的初步判断、结构化证据缺口和人工复核原因。
7. Evidence Recollection 时间线。
8. 人工复核提示。
9. 失败原因或不确定原因。

### 13.2 结果标签

| 标签 | 展示含义 |
| --- | --- |
| 初步通过 | 自动证据支持通过，但仍可查看截图 |
| 初步失败 | 自动证据支持失败，需要人工确认是否为真实缺陷 |
| 需要人工复核 | 系统已采集证据，但业务判断不能自动最终确定 |
| 执行阻塞 | 未能进入目标页面或关键动作失败 |
| 证据不足 | 操作完成但证据不足以支持判断 |

报告应支持按 `manual_review_reason` 聚类查看人工复核项，例如数据正确性、颜色规则、证据缺口、冲突证据、低置信度解释和高风险动作确认。

### 13.3 Excel 回写策略

MVP 可选回写：

| Excel 列 | 回写内容 |
| --- | --- |
| 测试结果 | `初步通过`、`初步失败`、`需人工复核`、`执行阻塞`、`证据不足` |
| 备注 | 报告相对路径、失败摘要、人工复核原因 |

默认不覆盖原始 Excel，生成副本：

```text
outputs/test-cases-with-results-20260614-225000.xlsx
```

---

## 14. 配置设计

### 14.1 参数优先级

MVP 的运行参数优先从命令行输入，配置文件用于复用常用环境。参数合并顺序如下，后者覆盖前者：

```text
内置默认配置 < 配置文件 < 命令行参数
```

Excel 中的 `参数` 字段属于单条用例的业务参数，不作为系统运行配置。若命令行提供同名用例参数，例如 `--case-param stock_code=600519`，命令行值优先。

推荐命令：

```bash
python -m autoairtest run \
  --excel test-cases.xlsx \
  --sheet 需求测试报告 \
  --app-package com.example.securities \
  --adb-serial DEVICE_SERIAL \
  --output-dir runs
```

兼容已有配置：

```bash
python -m autoairtest run --config config.local.yaml --excel test-cases.xlsx
python -m autoairtest init-config --output config.template.yaml
python -m autoairtest run --config config.local.yaml --save-config config.last.yaml
```

### 14.2 内置默认配置

程序在没有配置文件时使用以下默认值。默认值应保证流程可启动配置解析，但不假设具体 App 包名。

```yaml
app:
  package: ""
  activity: ""
  startup_wait_seconds: 5

device:
  platform: "android_real_device"
  adb_serial: ""
  unlock_before_run: true

input:
  excel_path: "test-cases.xlsx"
  sheet_name: "需求测试报告"
  case_filter: ""

execution:
  continue_on_case_failure: true
  action_timeout_seconds: 10
  page_stable_timeout_seconds: 8
  max_locator_attempts: 3
  max_steps_per_case: 30
  screenshot_every_action: true
  save_full_ui_tree: false
  enable_state_graph: false
  correction_budget:
    low: 3
    medium: 1
    high: 0
  retry:
    default_max_attempts: 2
    default_interval_seconds: 1
    poco_dump_max_attempts: 3
    poco_dump_interval_seconds: 1
    poco_dump_backoff: "fixed"

verification:
  primary_evidence: "poco"
  always_save_screenshot: true
  llm_preliminary_judgment: true
  data_correctness_requires_human_review: true
  color_rule_requires_human_review: true
  min_confidence_for_auto_preliminary: 0.75
  evidence_recollection:
    max_attempts: 2
    allow_visibility_adjustment_on_second_attempt: true

logs:
  enable_capture: true
  clear_before_action: true
  default_window_seconds: 5
  crash_patterns:
    - "FATAL EXCEPTION"
    - "AndroidRuntime"
    - "ANR in "
    - "*** *** *** *** *** ***"
    - "Tombstone written to"

llm:
  model: "configured-by-env"
  temperature: 0.1
  max_retries: 2

report:
  output_dir: "runs"
  session_name: ""
  generate_html: true
  write_back_excel: false

doctor:
  fail_on_missing_device: true
  fail_on_missing_app_package: true
  check_airtest: true
  check_poco: true
```

### 14.3 配置模板

`init-config` 生成的模板应显式暴露常改项，方便用户保存真机、App、输入文件和重试策略。

```yaml
app:
  package: "请填写证券App包名"
  activity: ""
  startup_wait_seconds: 5

device:
  platform: "android_real_device"
  adb_serial: "请填写adb devices中的设备序列号；只有一台设备时可留空"
  unlock_before_run: true

input:
  excel_path: "test-cases.xlsx"
  sheet_name: "需求测试报告"
  case_filter: ""

execution:
  continue_on_case_failure: true
  action_timeout_seconds: 10
  page_stable_timeout_seconds: 8
  max_locator_attempts: 3
  max_steps_per_case: 30
  screenshot_every_action: true
  save_full_ui_tree: false
  enable_state_graph: false
  correction_budget:
    low: 3
    medium: 1
    high: 0
  retry:
    default_max_attempts: 2
    default_interval_seconds: 1
    poco_dump_max_attempts: 3
    poco_dump_interval_seconds: 1
    poco_dump_backoff: "fixed"

verification:
  primary_evidence: "poco"
  always_save_screenshot: true
  llm_preliminary_judgment: true
  data_correctness_requires_human_review: true
  color_rule_requires_human_review: true
  min_confidence_for_auto_preliminary: 0.75
  evidence_recollection:
    max_attempts: 2
    allow_visibility_adjustment_on_second_attempt: true

logs:
  enable_capture: true
  clear_before_action: true
  default_window_seconds: 5
  crash_patterns:
    - "FATAL EXCEPTION"
    - "AndroidRuntime"
    - "ANR in "
    - "*** *** *** *** *** ***"
    - "Tombstone written to"

llm:
  model: "configured-by-env"
  temperature: 0.1
  max_retries: 2

report:
  output_dir: "runs"
  session_name: ""
  generate_html: true
  write_back_excel: false

doctor:
  fail_on_missing_device: true
  fail_on_missing_app_package: true
  check_airtest: true
  check_poco: true
```

### 14.4 命令行参数建议

| 参数 | 作用 | 覆盖配置项 |
| --- | --- | --- |
| `--config` | 读取已有配置文件 | 不适用 |
| `--save-config` | 保存本次合并后的配置 | 不适用 |
| `--excel` | 指定用例 Excel | `input.excel_path` |
| `--sheet` | 指定 sheet | `input.sheet_name` |
| `--case-filter` | 只执行匹配的用例 | `input.case_filter` |
| `--app-package` | 指定被测 App 包名 | `app.package` |
| `--app-activity` | 指定启动 Activity | `app.activity` |
| `--adb-serial` | 指定 Android 真机 | `device.adb_serial` |
| `--output-dir` | 指定报告和证据目录 | `report.output_dir` |
| `--session-name` | 指定本次 Test Session 名称后缀 | `report.session_name` |
| `doctor` | 只做环境检查，不执行用例 | 不适用 |
| `--poco-dump-retries` | 指定 Poco dump 最大尝试次数 | `execution.retry.poco_dump_max_attempts` |
| `--max-steps-per-case` | 限制单条用例最多动作数 | `execution.max_steps_per_case` |
| `--correction-budget-low` | 覆盖低风险动作自动纠错次数 | `execution.correction_budget.low` |
| `--correction-budget-medium` | 覆盖中风险动作自动纠错次数 | `execution.correction_budget.medium` |
| `--evidence-recollection-attempts` | 覆盖验证阶段证据补采次数 | `verification.evidence_recollection.max_attempts` |
| `--enable-state-graph` | 启用页面指纹和状态图诊断 | `execution.enable_state_graph` |
| `--disable-log-capture` | 关闭 session 级 logcat 采集 | `logs.enable_capture` |
| `--case-param key=value` | 覆盖单条用例中的同名业务参数 | 用例参数 |

推荐补充命令：

```bash
python -m autoairtest doctor --config config.local.yaml
python -m autoairtest run --config config.local.yaml --case-filter 国内指数 --session-name domestic-index-smoke
```

---

## 15. 推荐项目结构

```text
autoairtest/
├── main.py
├── config.yaml
├── config.template.yaml
├── requirements.txt
├── autoairtest/
│   ├── __init__.py
│   ├── orchestrator.py
│   ├── models.py
│   ├── excel_loader.py
│   ├── planning/
│   │   ├── planning_agent.py
│   │   ├── rule_based_planner.py
│   │   └── interpretation_rationale.py
│   ├── execution/
│   │   ├── device_workflow.py
│   │   ├── execution_agent.py
│   │   ├── locator.py
│   │   ├── risk_policy.py
│   │   ├── state_graph.py
│   │   └── trace.py
│   ├── verification/
│   │   ├── rule_engine.py
│   │   ├── verification_agent.py
│   │   ├── evidence_recollection.py
│   │   └── judgment_policy.py
│   ├── tools/
│   │   ├── airtest_adapter.py
│   │   ├── poco_adapter.py
│   │   ├── ocr_adapter.py
│   │   ├── evidence_store.py
│   │   ├── log_collector.py
│   │   ├── crash_analyzer.py
│   │   ├── doctor.py
│   │   └── llm_client.py
│   ├── prompts/
│   │   ├── planner.md
│   │   ├── locator.md
│   │   └── verifier.md
│   └── reporting/
│       ├── html_report.py
│       └── templates/
├── skills/
│   ├── securities_navigation/
│   │   ├── SKILL.md
│   │   ├── aliases.yaml
│   │   └── routes.yaml
│   ├── market_index_rules/
│   │   ├── SKILL.md
│   │   └── order_rules.yaml
│   └── airtest_poco_operations/
│       └── SKILL.md
├── tests/
│   ├── test_excel_loader.py
│   ├── test_planner_contract.py
│   ├── test_verifier_order.py
│   └── fixtures/
└── runs/
```

说明：

1. `planning/` 保存 Planning Agent、规则型 planner 和解释依据模型。
2. `execution/` 保存受控设备执行 workflow、Execution Agent、定位器、风险策略和追加式执行轨迹。
3. `verification/` 保存规则引擎、Verification Agent、证据补采和判断策略。
4. `tools/` 是稳定工具层，未来可暴露为 MCP Server；Log Collector、Crash Analyzer 和 Doctor 也应先以本地 Python 接口实现。
5. `prompts/` 独立保存，便于持续调优。
6. `skills/` 保存证券 App 领域知识、操作规范和机器可读 Skill Rules。
7. `execution/state_graph.py` 只负责页面指纹、元素 key 和转移关系，不负责直接选择高风险动作。
8. `tests/fixtures/` 保存元素摘要样例、必要的调试控件树样例、logcat crash 样例和 Excel 样例，避免单元测试依赖真机。

---

## 16. Prompt 合同

### 16.1 Planner Prompt 约束

Planner 必须遵守：

1. 不生成 Python 代码。
2. 不编造不存在的页面。
3. 不把数据正确性写成自动最终判断。
4. 对每个验证目标标注是否需要人工复核。
5. 对导航别名、目标归一、风险分类和验证目标分类输出 InterpretationRationale。
6. 输出 JSON 必须可被解析。

关键系统指令：

```text
你是证券 App 自动化测试规划器。
你只能把自然语言测试用例拆成动作和验证目标。
你不能承诺行情数据真实正确，除非输入中提供外部数据源。
当预期结果涉及“数据正确”“两端一致”“颜色规则”时，必须标记 human_review_required=true。
当自然语言表达与 UI 文案不完全一致时，优先使用 Skills 中的别名和路径规则归一，并输出 InterpretationRationale。
每个动作必须标注 action_risk_level。
```

### 16.2 Locator Prompt 约束

Locator 必须遵守：

1. 优先选择 Poco 控件树中可点击且上下文匹配的元素。
2. 如果候选不唯一，返回歧义原因，不强行点击。
3. 坐标点击必须说明依据。
4. 置信度低于阈值时不执行高风险动作。
5. 每次元素选择必须输出 ExecutionRationale。
6. 发生可恢复误操作时，只能在动作风险预算内纠错，并写入 ExecutionTrace。

### 16.3 Verifier Prompt 约束

Verifier 必须遵守：

1. 优先依据 Poco 控件树和结构化界面证据判断。
2. 截图作为证据，但不是所有目标的首选自动判断来源。
3. 对数据正确性只能给初步观察，必须要求人工复核。
4. 输出必须包含证据文件引用。
5. 不得使用“已最终通过”这类表述，只能输出初步状态。
6. 对顺序证据缺失、出现额外元素或证据冲突时，必须输出结构化 `manual_review_reason` 和 `structured_details`。
7. Evidence Recollection 必须受预算限制，并写入 ExecutionTrace。

关键系统指令：

```text
你是移动 App 测试结果初判器。
你的判断是 Preliminary Judgment，不是人工最终结论。
如果目标涉及行情数据是否正确、两端数据是否一致、颜色规则是否符合业务口径，必须设置 human_review_required=true。
优先使用 Poco 控件树、元素文本、元素顺序和元素状态作为判断依据。
当期望顺序为 A-B-C-D，但证据只包含 A-B-C，或证据为 A-B-C-E 时，默认标记 manual_required + verification_evidence_gap，除非 Skill Rule 明确规定通过或失败。
```

---

## 17. 异常处理

| 异常 | 识别方式 | 处理策略 | 结果 |
| --- | --- | --- | --- |
| 设备未连接 | ADB 无 device | 停止执行，提示连接真机 | run blocked |
| App 启动失败 | package/activity 启动超时 | 重试一次，仍失败则停止 | run blocked |
| Poco dump 失败 | dump 抛错或为空 | 按配置优先重试；重试仍失败后降级截图/OCR，报告标注 Poco 证据不可用 | uncertain 或 manual_required |
| 页面未登录 | 出现登录页关键文本 | 停止当前用例，提示人工准备 | blocked |
| logcat 不可用 | `adb logcat` 命令失败或权限异常 | 继续执行可视化用例，但报告标注 crash 监测不可用，并要求人工复核运行稳定性 | manual_required |
| Java crash | logcat 在动作时间窗口内命中 `FATAL EXCEPTION` 且关联被测包名 | 写入 crashes.jsonl、提取 CrashSignature、保存 original_repro_path，停止当前用例 | fail_preliminary 或 blocked |
| ANR | logcat 命中 `ANR in` 且关联被测包名 | 写入 crashes.jsonl，报告标注响应性问题，停止当前用例或按配置继续下一条 | fail_preliminary |
| native crash | logcat 命中 native crash 标志或 tombstone 线索 | 记录 crash 线索；若能拉取 tombstone 则保存，否则标注证据缺口 | fail_preliminary 或 manual_required |
| 元素找不到 | 三级定位均失败 | 保存截图、候选元素摘要和失败原因 | blocked |
| 元素歧义 | 多候选置信度接近 | 根据动作风险等级和纠错预算处理；低风险可自动消歧或纠错，中高风险受限，高风险阻塞或人工确认 | uncertain、manual_required 或 blocked |
| 执行期别名差异 | 计划目标和 UI 可见文案不一致，例如 `自选` 与 `我的自选` | 使用 Navigation Alias Skill 和当前界面证据生成 PlanAmendment，继续执行或要求人工确认 | success 或 manual_required |
| 纠错预算耗尽 | Correction Step 次数超过风险等级预算 | 停止当前动作，保存 ExecutionTrace 和失败原因 | blocked 或 manual_required |
| 高风险动作 | 动作涉及交易、账户、登录退出、添加/删除自选等 | 不自动执行或纠错，要求人工确认 | manual_required 或 blocked |
| 点击无响应 | 点击后页面证据无变化 | 重试一次，仍无变化则 blocked | blocked |
| LLM 输出非法 JSON | JSON schema 校验失败 | 重试，仍失败则 uncertain | uncertain |
| 数据正确性目标 | 目标分类为 data_correctness | 保存证据，要求人工复核 | manual_required |
| 顺序证据缺口 | 期望 A-B-C-D，但证据为 A-B-C、A-B-C-E 等 | 先按预算执行 Evidence Recollection；仍不完整则结构化记录 `verification_evidence_gap` | manual_required |
| 证据冲突 | Poco、OCR、截图证据互相矛盾 | Verification Agent 解释冲突并标记人工复核原因 | manual_required |
| 截图失败 | snapshot 抛错 | 重试一次；仍失败则停止当前用例 | blocked |
| 状态图循环 | 启用 StateGraph 后连续回到同一 page_hash 且无新动作 | 停止探索或回到 ExecutionPlan 主线；MVP 不因状态图自动扩展新点击 | blocked 或 manual_required |

Poco dump 失败的重试策略必须由配置控制：

1. `execution.retry.poco_dump_max_attempts` 控制最大尝试次数，默认 3 次。
2. `execution.retry.poco_dump_interval_seconds` 控制重试间隔，默认 1 秒。
3. `execution.retry.poco_dump_backoff` 控制退避策略，MVP 默认 `fixed`，后续可支持 `linear` 或 `exponential`。
4. 每次重试前应重新等待页面稳定；连续失败后才降级到 OCR/截图证据。
5. 降级后仍必须保存截图和失败原因，但不强制保存完整控件树。

---

## 18. 测试策略

### 18.1 单元测试

应覆盖：

1. Excel 字段解析。
2. 空值标准化。
3. 重名用例 ID 生成。
4. 预期结果拆分。
5. 元素顺序判断算法。
6. RunResult 汇总规则。
7. LLM JSON schema 校验。
8. Navigation Alias Skill Rule，例如 `自选` 到 `我的自选` 的归一。
9. 动作风险分级和纠错预算。
10. InterpretationRationale 和 ExecutionRationale schema 校验。
11. Verification Evidence Gap 的结构化输出。
12. Evidence Recollection 预算和越界限制。
13. TestSession ID、config snapshot 和 session_meta 生成。
14. `steps.jsonl` 追加写入和字段完整性。
15. CrashSignature 归一化和 dedup 规则。
16. StateGraph 的 page fingerprint、element_key 和 edge 记录。
17. Doctor 检查项的通过、失败和 warning 分类。

### 18.2 离线集成测试

使用 fixture 模拟：

1. 元素摘要 JSON，必要时包含用于调试的 Poco 控件树 fixture。
2. OCR 结果 JSON。
3. 截图路径。
4. Planner 输出。
5. Verifier 输出。
6. ExecutionTrace 和 PlanAmendment 样例。
7. A-B-C-D、A-C-B-D、A-B-C、A-B-C-E 等顺序验证 fixture。
8. logcat crash、ANR、native crash 和噪音日志 fixture。
9. StateGraph 简单转移 fixture，例如 page_a -> click_more -> page_b。
10. Doctor 输出 fixture，例如缺少设备、缺少 App 包名、Poco 不可用。

离线测试不依赖真机，重点保证核心逻辑稳定。

### 18.3 真机冒烟测试

第一阶段真机测试只跑 1 到 2 条用例：

1. `TC_国内指数更多跳转正常`
2. `TC_国内指数宫格跳转正常`

原因：

1. 这两条以跳转和顺序验证为主，自动化边界清晰。
2. 不强依赖行情数据正确性的人工判断。
3. 可以快速验证 Airtest + Poco + 报告链路。
4. 可以验证 TestSession、steps.jsonl、crashes.jsonl 和 logcat 时间窗口是否按预期落盘。

### 18.4 验收标准

MVP 可验收条件：

1. 能读取当前 `test-cases.xlsx` 的 7 条用例。
2. 能在 Android 真机上执行至少 2 条跳转类用例。
3. 每条执行过的用例都有截图、元素摘要、执行计划和结果 JSON。
4. HTML 报告能展示每条用例的动作过程和截图。
5. HTML 报告能展示 InterpretationRationale、ExecutionTrace、PlanAmendment 和人工复核原因。
6. 顺序类验证能基于 Poco 或 OCR 给出初步判断；证据缺失或额外元素时进入结构化人工复核。
7. 数据正确性类验证不会被误标为自动最终通过，而是标记人工复核。
8. 失败时能给出失败阶段、证据路径、执行依据和复核原因。
9. TestSession 目录包含 `session_meta.json`、`config.resolved.json`、`steps.jsonl` 和 HTML 报告。
10. 若测试过程中出现可识别 crash/ANR，报告能展示 CrashSignature、关联步骤和原始复现路径。

---

## 19. 开发里程碑

### M0：环境验证

目标：

1. 安装 Airtest、Poco、ADB 环境。
2. Android 真机可连接。
3. 可启动 App。
4. 可截图。
5. 可 dump 控件树。
6. 可运行 `python -m autoairtest doctor` 并输出结构化诊断。

产出：

1. 环境检查脚本。
2. 一份设备连通性报告。
3. `doctor.json` 诊断结果。

### M1：Excel 与证据链路

目标：

1. 读取 `test-cases.xlsx`。
2. 生成 NaturalLanguageTestCase。
3. 创建 TestSession 目录、`session_meta.json` 和 `config.resolved.json`。
4. 为每条用例创建证据目录。
5. 保存初始截图和元素摘要。
6. 追加写入 `steps.jsonl`。

产出：

1. `case.json`
2. `000_initial.png`
3. `000_initial.json`
4. `session_meta.json`
5. `steps.jsonl`

### M2：Planner 与执行计划

目标：

1. Planning Agent 输出稳定 JSON。
2. 当前 7 条用例都能生成 ExecutionPlan。
3. 导航别名、目标归一、动作风险分类和验证目标分类都能输出 InterpretationRationale。
4. 数据正确性目标都被标记为人工复核。

产出：

1. `execution_plan.json`
2. `interpretation_rationales.json`
3. Planner schema 校验。

### M3：Executor 动作执行

目标：

1. 实现 Poco 语义定位。
2. 实现 Airtest 点击、滑动、返回。
3. 实现 OCR/截图兜底定位。
4. 实现动作风险分级和纠错预算。
5. 实现 ExecutionTrace 和 PlanAmendment。
6. 能跑通跳转类用例。

产出：

1. `action_results.json`
2. `execution_trace.json`
3. `plan_amendments.json`
4. 动作前后截图和元素摘要。

### M4：Verifier 与报告

目标：

1. Rule Engine 使用 Poco 优先证据进行确定性初步判断。
2. 支持页面跳转、弹框、顺序验证。
3. Verification Agent 能解释证据缺口、冲突证据和人工复核原因。
4. 支持 Evidence Recollection 预算。
5. 数据正确性目标标记人工复核。
6. 生成 HTML 报告。
7. 报告展示 TestSession、steps、crash warning 和人工复核聚类。

产出：

1. `verification_result.json`
2. 结构化 `manual_review_reason` 和 `structured_details`
3. `report.html`

### M5：稳定性与可用性

目标：

1. 增加超时、重试、失败归因。
2. 增加敏感信息脱敏。
3. 增加 Excel 回写副本。
4. 补齐单元测试和离线集成测试。
5. 增加 Log Collector 与 Crash Analyzer 的 Android logcat MVP。

产出：

1. `crashes.jsonl`
2. CrashSignature 聚类结果
3. logcat crash/ANR fixture 测试

### M6：探索 QA 与复现路径精简

目标：

1. 引入可选 StateGraph，用于页面指纹、元素已访问记录和转移关系。
2. 在严格 blocklist 和 Action Risk Level 下支持受限探索 QA。
3. 对已有 crash session 支持 delta-debugging 式复现路径精简。
4. 将本地工具层按 MCP 风格暴露，供 Codex/OpenCode/Cursor 等客户端接入。

产出：

1. `state_graph.json`
2. `minimized_repro_path`
3. MCP adapter 原型
4. 探索 QA 报告与覆盖统计

---

## 20. 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 证券 App 控件树不完整 | Poco 无法识别关键元素 | OCR、模板匹配、截图坐标兜底 |
| 行情数据动态变化 | 自动判断数据正确性不可靠 | MVP 不做最终判断，只保存证据并人工复核 |
| 页面布局随版本变化 | 元素定位失败 | 使用语义定位和上下文，不依赖固定坐标 |
| 多个同名元素 | 点击错误位置 | 使用 bounds、容器、区域、页面上下文和 ExecutionRationale 消歧 |
| 自然语言与 UI 文案不一致 | Planner 或 Executor 误解目标 | 使用 Navigation Alias Skill，例如 `自选` 到 `我的自选`，并记录 InterpretationRationale 或 PlanAmendment |
| 执行期可恢复误操作 | 用例流程偏离但仍继续执行 | 按动作风险等级限制纠错预算，所有纠错写入 ExecutionTrace |
| 高风险动作误触 | 影响账户、交易或持久化用户数据 | 高风险动作不自动纠错，阻塞或要求人工确认 |
| 顺序证据缺口 | A-B-C-D 目标只采集到 A-B-C 或 A-B-C-E | 先受限 Evidence Recollection，仍异常则结构化人工复核 |
| 登录态不稳定 | 用例无法开始 | 第一版要求人工预置登录状态 |
| 夜间模式或涨跌色配置 | 颜色判断误判 | 截图留痕，颜色规则人工复核 |
| LLM 输出不稳定 | 计划或判断格式错误 | JSON schema 校验、低温度、重试、失败降级 |
| 截图含敏感信息 | 数据安全风险 | 元素摘要脱敏，报告权限控制，后续做截图区域脱敏 |
| logcat 噪音过大 | crash 误报或报告干扰 | 使用被测包名、时间窗口和 CrashSignature 归一化；噪音只作为 warning |
| 崩溃路径不可复现 | 后续排查成本高 | MVP 保留 original_repro_path 和每步截图；路径精简作为 M6 能力，不覆盖原始路径 |
| 自由探索误触高风险动作 | 可能影响账户、交易或本地持久化状态 | 探索 QA 不进入 MVP；后续必须依赖 blocklist、Action Risk Level 和人工确认 |
| 状态图误判页面相同或不同 | 探索覆盖统计失真 | page fingerprint 只用于诊断和探索，不替代 ExecutionPlan 和验证结论 |
| MCP 化过早导致部署复杂 | MVP 被协议、客户端差异和 Node/TypeScript 工程拖慢 | 先保持 Python 本地接口，MCP 作为工具层适配，不改变核心合同 |

---

## 21. 后续演进

MVP 稳定后可逐步增加：

1. 接入行情接口或数据库，形成数据正确性的外部 Oracle。
2. 建立页面对象和业务路径库，减少 LLM 每次推理成本。
3. 建立截图模板库，提高纯视觉场景稳定性。
4. 支持自动登录前置流程，但需要严格安全边界。
5. 支持用例参数化，例如股票代码、市场类型、账号环境。
6. 支持多设备串行或并行执行。
7. 将本地工具层正式暴露为 MCP Server。
8. 增加失败聚类和缺陷摘要。
9. 增加人工复核页面，在报告中直接标记最终结果。
10. 建立 Skill Rule 版本管理和回归评估集。
11. 引入外部 Oracle 后，将部分 `manual_required` 数据正确性目标升级为可自动判定目标。
12. 引入 DevTest 工作流：读取改动范围或用户指定 scope，生成窄范围自测计划。
13. 引入 Exploratory QA 工作流：基于 StateGraph 做受限探索、覆盖统计和 crash 发现。
14. 引入 Repro Minimize 工作流：对 crash 的 original_repro_path 做 replay 验证和 delta-debugging 精简。
15. 引入 Smart QA 工作流：读取 PRD、路由、页面和处理函数信号，先让用户确认业务流，再交给受控执行器。
16. 将本地 Tool Layer 暴露为 MCP Server，并提供 Codex/OpenCode/Cursor 等客户端接入模板。

---

## 22. 与原方案的主要调整

相对原 `AI驱动自然语言测试用例执行系统-方案设计.md`，本详细设计做了以下收敛：

1. 明确 MVP 只支持 Android 真机，不支持模拟器和 iOS。
2. 明确验证阶段优先使用 Poco 控件树和元素证据，而不是优先截图 + LLM。
3. 明确截图对所有用例强制留痕。
4. 明确 LLM 只做初步判断，不作为数据正确性的最终裁判。
5. 明确数据正确性、两端一致性、颜色规则需要人工复核。
6. 将当前 Excel 的 7 条真实用例映射到具体执行和验证策略。
7. 明确 Workflow、Agent、Skill、Tool、Guardrail 的职责边界。
8. 明确 Planning Agent、受限 Execution Agent、Rule Engine、Verification Agent 和 Human Review 的分工。
9. 补充动作风险分级、纠错预算、执行轨迹、计划补充、证据补采和结构化人工复核原因。
10. 补充数据模型、证据目录、报告结构、异常处理、测试策略和开发里程碑。
11. 参考 `app-test-control` 增加 TestSession、steps.jsonl、crashes.jsonl、CrashSignature、ReproductionPath 和可选 StateGraph。
12. 参考 `app-test-control` 增加场景化工作流视图，但明确 DevTest、Exploratory QA、Repro Minimize、Smart QA 均不进入 MVP。
13. 参考 `app-test-control` 增加 doctor 命令、Log Collector 和 Crash Analyzer 设计，但保持 Python-first、本地工具优先。
14. 明确不直接照搬 TypeScript 多 MCP 工程形态，也不把 iOS、多客户端 MCP-native 接入放进第一版。

---

## 23. 最小可落地版本建议

建议第一轮实现只跑通以下闭环：

1. 运行 `python -m autoairtest doctor`，确认 Python 依赖、ADB、设备、App 包名、Airtest/Poco 和输出目录可用。
2. 读取 Excel。
3. 创建 TestSession，保存 `session_meta.json`、`config.resolved.json` 和 `steps.jsonl`。
4. 选择 `TC_国内指数更多跳转正常`。
5. Android 真机启动 App。
6. 人工预置登录状态。
7. 自动进入行情、股指、国内指数。
8. 点击更多。
9. 保存每步截图和元素摘要。
10. 每个关键动作后检查 logcat crash/ANR 时间窗口；如有命中，写入 `crashes.jsonl`。
11. 使用 Poco/OCR 判断列表页和科创综指顺序。
12. 生成 HTML 报告。

这条用例覆盖了读取、规划、定位、点击、跳转、顺序验证、截图留痕、报告输出等核心链路，同时避开了行情数据正确性的外部 Oracle 问题，最适合作为 MVP 的第一条端到端样例。

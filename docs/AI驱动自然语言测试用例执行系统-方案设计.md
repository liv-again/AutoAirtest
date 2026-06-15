# AI驱动自然语言测试用例执行系统 — 方案设计

> 基于 Sisyphus 与用户的多次对话整理  
> 日期：2026-05-28

---

## 一、需求概述

**目标**：输入 Excel 文档（自然语言功能测试用例） → AI 理解并自动执行这些用例 → 测试对象为**手机证券 App**。

**核心挑战**：LLM 如何准确理解自然语言指令（如"点击行情按钮"），并映射到手机 App 界面上的具体元素进行操控。

---

## 二、总体架构：方案C（推荐）

采用 **MCP + Skills + 多Agent** 三层正交架构，三者各司其职、互不耦合。

```
┌──────────────────────────────────────────────────────────────────┐
│                      Orchestrator (主控流水线)                    │
│  Python main.py：串联整个流程，无复杂状态机，纯线性编排             │
└──────┬──────────────┬──────────────┬──────────────┬──────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────────┐
│  Planner   │ │  Executor  │ │  Verifier  │ │    Reporter      │
│  Agent     │ │  Agent     │ │  Agent     │ │    Agent         │
│            │ │            │ │            │ │                  │
│ 读Excel    │ │ 三级定位   │ │ 截图+LLM   │ │ 生成HTML报告     │
│ LLM理解用例│ │ 执行操作   │ │ 判断PASS   │ │ 归档截图证据     │
│ 生成执行计划│ │ 异常重试   │ │ /FAIL      │ │                  │
└────────────┘ └────────────┘ └────────────┘ └──────────────────┘
       │              │              │              │
       └──────────────┴──────────────┴──────────────┘
                      │
              ┌───────▼────────┐
              │   MCP Server   │ ← 工具层，纯功能，与LLM无关
              │   (工具层)      │
              │                │
              │  connect_device│
              │  tap/click     │
              │  swipe         │
              │  snapshot      │
              │  dump_ui_tree  │
              │  ocr           │
              └───────┬────────┘
                      │
              ┌───────▼────────┐
              │  真实测试设备    │
              │ Android/iOS    │
              └────────────────┘
```

### 三层职责

| 层级             | 作用                                 | 与LLM的关系              | 稳定性             |
| -------------- | ---------------------------------- | -------------------- | --------------- |
| **MCP Server** | 底层工具（Airtest操作、截图、UI树dump、Excel读写） | 无关，纯代码实现             | ⭐⭐⭐⭐⭐ 最稳定，一次性开发 |
| **Skills**     | 领域知识注入（证券App测试模式、Airtest操作指南）      | 以Prompt形式注入到Agent上下文 | ⭐⭐⭐⭐ 持续积累       |
| **多Agent**     | 决策层（理解用例、决定操作、判断结果）                | 每个Agent调用LLM API做推理  | ⭐⭐⭐ 需持续调优Prompt |

---

## 三、技术选型：Airtest + Poco 替代 Appium

### 3.1 为什么选择 Airtest + Poco

| 维度         | Appium                          | Airtest + Poco                  |
| ---------- | ------------------------------- | ------------------------------- |
| 定位方式       | WebDriver → XPath/ID            | 双模：图像识别(Airtest) + 控件树(Poco)    |
| 架构         | Client → Appium Server → Driver | Python直接调ADB/WebDriverAgent，更轻量 |
| 图像识别       | 不支持（需第三方）                       | **原生核心能力**，可截图像素级定位             |
| 对自定义渲染     | 需元素有accessibility属性             | 图像识别不依赖属性，K线图也能识别               |
| AirtestIDE | 无                               | 有IDE，可录制回放，截图标注                 |
| 安装         | 需Node.js + Appium Server + 驱动   | `pip install airtest`           |
| 全流程通过率     | ~60-70%                         | ~75-85%（配合三级定位）                 |

### 3.2 证券App场景的特殊优势

证券App大量使用**自定义渲染控件**（K线图、走势图、逐笔数据），这些控件在 Appium 中要么无法定位，要么需要开发者额外加 accessibility 属性。Airtest 的图像识别可以直接截屏识别，无需改造被测 App。

```
┌──────────────────────────────┐
│  分时  五日  K线  周K  月K   │ ← Poco可定位（Tab控件）
│  ┌────────────────────────┐  │
│  │  ▲ 45.80               │  │
│  │  ▁▂▃▄▅▆▇▆▅▄▃▂▁        │  │ ← Airtest图像识别（K线图）
│  │     ▂▃▄▅▆▇▆▅            │  │
│  └────────────────────────┘  │
│  买五 45.75  45.80 卖五     │ ← Poco可定位（列表项）
│   5.80 ▲ 2.34%              │
│  买入          卖出          │ ← 双模均可
└──────────────────────────────┘
```

---

## 四、核心难题：LLM如何准确定位元素

这是系统**最关键的技术挑战**，解决方案是 **"三级定位漏斗"**。

### 4.1 一级定位：语义匹配UI树（最快，~75%成功率）

**原理**：先用 Poco dump 当前页面的 UI 控件树，转成结构化文本喂给 LLM，让 LLM 做**语义匹配**而非字符串匹配。

```python
# Poco获取UI树
from poco.drivers.android.uiautomation import AndroidUiautomationPoco
poco = AndroidUiautomationPoco()

# dump UI树（XML格式）
ui_tree = poco.agent.hierarchy.dump()
```

**LLM Prompt 模板**：

```
当前屏幕包含以下可点击元素：
1. text="行情中心"  bounds=[0,0][120,60]  type=Tab  clickable=true
2. text="交易"      bounds=[120,0][240,60] type=Tab  clickable=true
3. text="我的持仓"  bounds=[240,0][360,60] type=Tab  clickable=true
...

用户指令: "点击行情按钮"
请从以上元素中选择最匹配的，返回JSON: {"action": "click", "target": "行情中心", "reason": "..."}
```

**LLM 的匹配是语义级**的：

| 用户说   | 元素text      | LLM匹配逻辑 |
| ----- | ----------- | ------- |
| "行情"  | "行情中心"      | 简称匹配 ✅  |
| "买入"  | "买""交易""下单" | 语义相似 ✅  |
| "自选股" | "我的自选"      | 同义匹配 ✅  |

### 4.2 二级定位：截图 + UI树联合定位（推荐主力，~80-85%成功率）

LLM 同时拿到**截图（视觉）+ UI树（结构化）** 两路信息，互相校验。

```python
# Airtest截图
screenshot = snapshot(filename="current.png")

# Poco dump UI树
ui_tree = poco.agent.hierarchy.dump()

# 传给多模态LLM（GPT-4o / Claude Sonnet）
# 输入：截图 + UI树 + 用户指令
# 输出：目标元素在UI树中的索引
```

**为什么双通道更强**：

| 场景           | 纯UI树                    | 截图+UI树              |
| ------------ | ----------------------- | ------------------- |
| 3个元素都含"行情"   | ❌ 无法区分                  | ✅ 截图可见哪个是Tab、哪个是标题  |
| 无文本ImageView | ❌ UI树只有 `<ImageView />` | ✅ 截图可见这是一张K线图       |
| 动态数据（股票列表）   | ❌ text是股票代码，无法预知        | ✅ LLM看截图知道"这是自选股列表" |
| 操作后验证        | ❌ 无法验证                  | ✅ 再截图对比，确认页面已跳转     |

### 4.3 三级定位：纯视觉/Airtest图像识别兜底（最稳，~90-95%成功率）

当 Poco 完全无法定位时（自定义渲染、WebView、纯图标），回退到纯视觉方案：

```python
# 方案A：Airtest图像模板匹配（预存储"行情"按钮截图）
touch(Template("hangqing_tab.png"))

# 方案B：LLM看图返回坐标
screenshot = snapshot()
# LLM分析截图 → 返回点击坐标 (x, y)
touch((x, y))

# 方案C：OCR识别文字后点坐标
import easyocr
reader = easyocr.Reader(['ch_sim'])
results = reader.readtext(screenshot)
# 找到"行情"文字 → 取中心坐标 → touch
```

### 4.4 三级漏斗完整工作流

```
用户指令: "输入股票代码600519，查询行情"
                              │
                              ▼
               ┌─────────────────────────────┐
Level 1        │   dump UI树 → LLM语义匹配    │  耗时 ~0.5s
(最快)         │  找到"stock_code_input"      │
               └──────────────┬──────────────┘
                              │ 命中? → 执行 → 截图验证
                              │ 未命中?
                              ▼
               ┌─────────────────────────────┐
Level 2        │  截图 + UI树联合             │  耗时 ~2s
(主力)         │  LLM看图找到输入框           │
               └──────────────┬──────────────┘
                              │ 命中? → 执行
                              │ 未命中?
                              ▼
               ┌─────────────────────────────┐
Level 3        │  Airtest模板/OCR定位         │  耗时 ~1-3s
(兜底)         │  找到搜索图标点击            │
               └─────────────────────────────┘
                              │
                              ▼
                     截图验证 → PASS/FAIL
```

---

## 五、关于框架选型：不需要LangGraph

| 方案                           | 复杂度  | 适合本场景？    | 理由               |
| ---------------------------- | ---- | --------- | ---------------- |
| **LangGraph**                | 🔴 高 | ❌ 过重      | 专为复杂状态机/多分支/循环设计 |
| **CrewAI**                   | 🟡 中 | ⚠️ 勉强     | Agent对话协作，本场景不需要 |
| **AutoGen**                  | 🟡 中 | ⚠️ 勉强     | 同上               |
| **Plain Python + LLM API**   | 🟢 低 | ✅ **最合适** | 流水线线性明确          |
| **Sisyphus/OpenCode task()** | 🟢 低 | ✅ 也合适     | 生态内调度            |

**核心判断**：你的系统流程几乎是线性的（读Excel → 逐条执行 → 验证 → 报告），没有复杂的 Agent 间对话或多分支状态机。引入 LangGraph 是**过度工程化**。

### 推荐的项目结构（Plain Python）

```
ai-test-runner/
├── mcp_server/                # 工具层（与LLM无关）
│   ├── __init__.py
│   ├── airtest_adapter.py     # Airtest操作封装
│   ├── poco_adapter.py        # Poco UI树操作封装
│   └── mcp_protocol.py        # MCP接口定义
├── agents/                     # 决策层（调LLM API）
│   ├── planner.py             # 读Excel → LLM理解 → 生成执行计划
│   ├── executor.py            # 三级定位 → 执行操作 → 异常重试
│   ├── verifier.py            # 截图 → LLM视觉判断 → PASS/FAIL
│   └── reporter.py            # 汇总结果 → 生成带截图的报告
├── skills/                     # 知识层（Prompt模板）
│   ├── securities_testing.md  # 证券App测试领域知识
│   └── airtest_guide.md       # Airtest+Poco操作指南
├── main.py                    # 主控流水线
├── config.yaml
└── requirements.txt
```

---

## 六、开发量估算

| 组件             | 预估代码量     | 说明                        |
| -------------- | --------- | ------------------------- |
| MCP Server（核心） | ~200-300行 | Airtest+Poco操作封装，一次开发基本不改 |
| Planner Agent  | ~100-150行 | 读Excel + LLM Prompt编排     |
| Executor Agent | ~200-300行 | 三级定位逻辑 + 状态管理 + 重试        |
| Verifier Agent | ~150-200行 | 截图 → LLM视觉API → 断言        |
| Reporter Agent | ~100行     | HTML模板 + 截图归档             |
| Skills         | 文档为主      | 持续积累领域知识                  |
| Orchestrator   | ~200行     | 串联整个流程                    |

**总计核心代码约 1000-1500 行 Python**，预估 2-4 周完成原型。

---

## 七、可行性结论

| 维度    | 评分         | 说明                            |
| ----- | ---------- | ----------------------------- |
| 技术可行性 | ★★★★☆ 8/10 | 学术界已验证（LELANTE 73%成功率），方案成熟   |
| 选型合理性 | ★★★★★ 9/10 | Airtest+Poco比Appium更适合证券App场景 |
| 架构设计  | ★★★★★ 9/10 | MCP+Skills+多Agent三层正交，无框架绑定   |
| 元素定位  | ★★★☆☆ 6/10 | 核心难点，三级漏斗可到85%+，但非100%        |
| 开发成本  | ★★★★☆ 7/10 | 纯Python，无复杂框架依赖，2-4周出原型       |

**总体结论：完全可行，方案C是最优架构，建议直接启动 MCP Server 开发。**

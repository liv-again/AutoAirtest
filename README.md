# AutoAirtest

AutoAirtest 是一个面向移动端证券应用测试场景的离线核心原型。其研究目标是把 Excel
中的自然语言测试用例转化为结构化执行计划、证据链与初步验证结果，从而降低人工
功能测试在重复操作、证据归档和结果整理方面的成本。

## 研究定位

本项目当前版本聚焦于“离线可复现核心”，并不声称已经完成真实 Android 设备上的闭环
自动执行。系统保留 Airtest、Poco、OCR 与大语言模型的适配器边界，但在依赖缺失时
以显式的 `unavailable` 状态降级，保证核心流程仍可运行和测试。

该设计适合用于以下研究或工程前置工作：

- 自然语言测试用例的结构化建模。
- 测试执行计划与验证目标的合同设计。
- 移动端界面证据链的目录组织。
- 自动初判与人工复核之间的边界划分。
- 后续接入 Airtest/Poco 真机执行器前的离线原型验证。

## 核心架构

系统采用线性主控流水线：

```text
配置合并 -> Excel 用例读取 -> 规则型规划 -> 离线执行占位
        -> 初步验证 -> 证据落盘 -> HTML 报告生成
```

主要模块如下：

- `autoairtest.models`：定义自然语言测试用例、执行计划、动作结果、验证目标、
  初步判断和运行结果等领域模型。
- `autoairtest.config`：提供默认配置、JSON/YAML 配置读取和递归覆盖合并。
- `autoairtest.excel_loader`：读取 Excel 测试用例，并进行空值规范化与重复用例 ID
  处理。
- `autoairtest.agents.planner`：基于确定性规则生成执行动作和验证目标。
- `autoairtest.agents.verifier`：基于结构化界面证据进行顺序、文本和人工复核判断。
- `autoairtest.tools`：定义 Airtest、Poco、OCR、LLM 与证据存储等工具边界。
- `autoairtest.orchestrator`：串联完整离线运行流程。
- `autoairtest.report`：生成可供人工审阅的 HTML 报告。

## 运行环境

推荐在名为 `torch` 的 conda 环境中运行：

```powershell
conda run -n torch python -m autoairtest init-config --output config.template.json
conda run -n torch python -m autoairtest run --excel docs/test-cases.xlsx --sheet 需求测试报告 --output-dir runs
```

当前发布分支不包含 `docs/` 和 `tests/` 目录。如需使用真实 Excel 用例，请在本地提供
相应文件，并确保 `openpyxl` 已安装在目标 conda 环境中。若缺少 `openpyxl`，系统会
生成一条依赖诊断用例，而不是在导入阶段崩溃。

## 命令行接口

生成配置模板：

```powershell
python -m autoairtest init-config --output config.template.json
```

执行离线运行：

```powershell
python -m autoairtest run `
  --excel docs/test-cases.xlsx `
  --sheet 需求测试报告 `
  --case-filter 国内指数 `
  --output-dir runs
```

常用参数：

- `--config`：读取 JSON 或 YAML 配置文件。
- `--excel`：指定自然语言测试用例工作簿。
- `--sheet`：指定工作簿中的 sheet 名称。
- `--case-filter`：按用例名称、内部 ID、操作描述或预期结果进行子串筛选。
- `--app-package`：预留的被测 Android 应用包名。
- `--adb-serial`：预留的 Android 真机序列号。
- `--output-dir`：指定证据和报告输出目录。

## 证据输出

每次运行会在输出目录下创建带时间戳的运行目录，典型结构如下：

```text
runs/
└── <timestamp>/
    ├── run_summary.json
    ├── report.html
    └── cases/
        └── <case_id>/
            ├── case.json
            ├── execution_plan.json
            ├── action_results.json
            ├── verification_result.json
            ├── logs.txt
            ├── screenshots/
            ├── element_summaries/
            └── ocr/
```

其中，`run_summary.json` 面向机器处理，`report.html` 面向人工复核。

## 当前边界

当前版本仍有以下明确边界：

- 不执行真实 Android 点击、滑动或输入。
- 不验证真实 Poco 控件树。
- 不执行 OCR 识别。
- 不调用真实 LLM 服务。
- 不进行 Excel 结果回写。
- 不对截图做敏感区域遮盖。
- 不包含测试用例文档、详细设计文档或测试代码。

这些边界是有意保留的：离线核心优先保证数据模型、证据链和报告链路稳定，后续可在
不破坏上层合同的情况下替换为真实设备执行器。

## 安全与隐私

仓库 `.gitignore` 默认忽略 `docs/`、`tests/`、运行产物、缓存、本地配置、环境变量文件
以及常见密钥和证书后缀。证券应用测试可能涉及账户、资产、手机号等敏感信息；在接入
真机截图前，应补充截图脱敏和报告访问控制策略。

## 学术使用建议

若将本项目用于论文实验或技术报告，建议把以下指标作为评估维度：

- 自然语言用例到执行计划的解析稳定性。
- 验证目标类别划分的准确性。
- 自动初判与人工复核边界的误判率。
- 证据链完整性与人工复核效率。
- Airtest/Poco 真机接入后的动作成功率和失败归因质量。

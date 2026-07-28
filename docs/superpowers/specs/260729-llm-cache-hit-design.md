# LLM 缓存命中率修复设计

## 1. 背景

PC 分支通过 Python 标准库 `urllib.request` 直接调用 OpenAI Compatible Chat Completions API。DeepSeek 的上下文缓存由服务端自动完成，要求后续请求从第 0 个 token 开始复用已经持久化的完整前缀。

当前实现存在两类问题：

1. 规划 Prompt 把按用例变化的导航和个股技能内容放在较长的稳定规则之前。真实 7 条 Excel 用例的平均 Prompt 长度约为 6,772 字符，公共前缀只有 2,647 字符；3,257 字符的稳定预期结果规则无法跨不同导航用例复用。
2. HTTP Provider 只向上层返回模型内容，丢弃响应中的 `usage`、模型和请求标识，项目无法观测 `prompt_cache_hit_tokens` 与 `prompt_cache_miss_tokens`。

验证阶段还存在独立问题：生产代码没有使用 `prompts/verifier.md`，动态验证目标紧跟在约 146 字符的固定指令之后，导致可复用前缀很短。

## 2. 目标

- 在不引入第三方 LLM SDK 的前提下，提高规划和验证请求的稳定公共前缀比例。
- 完整解析 OpenAI Compatible 响应中的缓存、输入和输出 token 指标。
- 将每次 LLM 尝试的脱敏指标返回调用方，并追加写入运行目录下的 `llm_usage.jsonl`。
- 保持现有注入式 Fake Provider 和无 usage Provider 的兼容性。
- 明确区分可重试与不可重试错误，避免无意义请求和缓存持久化竞争。
- 通过自动化测试覆盖所有生产 LLM 请求与解析路径。

## 3. 非目标

- 不实现本地模型响应结果缓存。
- 不引入 `openai`、`anthropic`、`langchain`、`httpx` 等依赖。
- 不记录完整 Prompt、模型响应正文、图片内容或 API Key。
- 不重构与 LLM 通信无关的设备执行、元素定位和业务验证规则。
- 不保证 DeepSeek 服务端 100% 命中；服务端缓存是 best-effort，本设计保证请求具备可复用前缀并提供真实指标。

## 4. 方案选择

采用“结构化请求边界 + 稳定前缀 + 完整 usage 观测”方案。

保留 `urllib.request` 和现有 `LLMClient` 对外入口，将 HTTP Provider 的返回值扩展为结构化响应。`LLMClient` 负责兼容旧 Provider 返回值、JSON 解析、schema 校验、重试和尝试级指标汇总。编排器为一次运行创建单一 telemetry sink，规划和验证阶段共同使用。

没有采用以下方案：

- 只调整 Prompt 顺序：无法解决 usage 丢失、错误重试和运行级观测问题。
- 引入完整 Message/Transport 框架：当前只有两条生产调用链，改动范围超过本次修复需要。

## 5. 架构

```text
PlanningAgent / RuleEngine
        │
        ▼
LLMClient.json_call(prompt, schema, context)
        │
        ├── 稳定消息前缀
        ├── 动态请求数据
        ├── schema 校验与重试
        ▼
OpenAI Compatible Provider
        │
        ├── content
        ├── usage
        ├── model
        └── request_id
        ▼
LLMCallResult
        │
        ├── 返回上层
        └── telemetry sink → runs/<session>/llm_usage.jsonl
```

### 5.1 组件职责

#### `PlanningAgent`

- 从稳定文件加载规划协议和预期结果规则。
- 把全部稳定内容放在导航、技能定位器和测试用例等动态内容之前。
- 调用 `LLMClient` 时传入 `stage=planning` 和 `case_id`。

#### `RuleEngine`

- 正式读取 `prompts/verifier.md` 作为稳定验证协议。
- 把验证目标、人工复核原因、证据来源、可见文本和证据文件放在稳定协议之后。
- 调用 `LLMClient` 时传入 `stage=verification`、`case_id` 和 `goal_id`；若现有调用上下文无法提供 `case_id`，允许为空字符串，但字段必须存在。

#### `LLMClient`

- 接受 Prompt、schema、可选图片和可选审计上下文。
- 兼容 Provider 返回字符串、直接业务字典和新的结构化 Provider 响应。
- 对每次尝试分别解析响应、校验业务 JSON、收集错误和 usage。
- 将尝试级 telemetry 发送给可选 sink。
- 在最终结果中返回 `usage` 汇总和 `attempt_usage` 列表。

#### OpenAI Compatible Provider

- 使用 `urllib.request` 发送请求。
- 返回模型内容、标准化前的原始 usage、模型名称和请求 ID。
- 抛出包含 HTTP 状态码和可重试属性的明确异常。

#### LLM usage telemetry sink

- 以 UTF-8 JSON Lines 追加写入单次运行目录的 `llm_usage.jsonl`。
- 每条记录对应一次实际 HTTP/Provider 尝试。
- 写入失败不得伪装成功；错误应进入调用结果的 telemetry 诊断，但不能覆盖已经成功的模型业务结果。

## 6. Prompt 稳定性设计

### 6.1 规划阶段

规划 Prompt 顺序固定为：

```text
1. prompts/planner.md
2. skills/expected_result_rules/SKILL.md
3. 通用导航与动作约束
4. 当前用例的导航路径
5. 当前用例的个股技能元素和定位器
6. 当前自然语言测试用例
```

通用导航约束不得插入当前页面名、导航路径或其他用例数据。动态导航段单独生成并位于所有稳定内容之后。

公共前缀回归测试使用仓库中的 7 条真实测试用例，至少断言：

- 公共前缀完整覆盖 `planner.md` 与 `expected_result_rules`。
- 动态 `case_id`、操作描述和预期结果位于稳定规则之后。
- 不使用字符比例作为生产指标；字符公共前缀只用于确定性回归测试。

### 6.2 验证阶段

验证 Prompt 顺序固定为：

```text
1. prompts/verifier.md
2. 动态验证目标
3. 动态人工复核原因
4. 动态证据来源
5. 动态可见文本
6. 动态证据文件引用
```

`prompts/verifier.md` 是唯一的验证协议正文来源，避免生产代码和模板重复维护两套固定指令。

### 6.3 路径稳定性

默认 Prompt 路径根据 Python 模块所在位置解析到项目根目录，不依赖当前工作目录。显式传入的测试路径继续受支持。

稳定模板或规则缺失时：

- 不允许静默退化为空字符串。
- 规划阶段返回明确失败并由现有规则 Planner 回退。
- 验证阶段返回明确 unavailable/diagnostic，不生成缺少协议约束的在线请求。

## 7. Provider 响应与 usage 模型

新的结构化 Provider 响应包含：

```python
{
    "content": "{\"...\": \"...\"}",
    "usage": {
        "prompt_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    },
    "model": "deepseek-v4-pro",
    "request_id": "provider-request-id",
}
```

标准化规则：

- 数值字段只接受可转换为非负整数的值。
- 未返回 usage 时设置 `usage_available=false`，不把缺失值伪造成 0。
- `cache_hit_ratio` 在 hit 与 miss 都可用且总和大于 0 时计算为 `hit / (hit + miss)`。
- 未知 usage 字段可以忽略；原始响应正文不得进入 telemetry。
- `prompt_tokens` 与 hit/miss 不一致时保留供应商原值并添加诊断，不擅自改写。

旧 Provider 兼容规则：

- 字符串返回值继续视为模型内容。
- 不含 `content` 包装键的字典继续视为已经解析的业务 JSON。
- 含 `content` 键的字典视为结构化 Provider 响应。

## 8. Telemetry 数据设计

`llm_usage.jsonl` 每条记录包含：

```json
{
  "timestamp": "2026-07-29T12:00:00+08:00",
  "stage": "planning",
  "case_id": "TC_001",
  "goal_id": "",
  "attempt": 1,
  "status": "success",
  "model": "deepseek-v4-pro",
  "request_id": "request-id",
  "usage_available": true,
  "prompt_tokens": 1000,
  "prompt_cache_hit_tokens": 800,
  "prompt_cache_miss_tokens": 200,
  "completion_tokens": 100,
  "total_tokens": 1100,
  "cache_hit_ratio": 0.8,
  "error_type": "",
  "error_message": ""
}
```

安全约束：

- 禁止写入 `prompt`、`messages`、`content`、`response`、`images`、`api_key` 和 Authorization header。
- `error_message` 必须经过现有敏感文本脱敏，并限制合理长度。
- `case_id`、`goal_id`、模型和请求 ID 统一转换为字符串。
- 文件采用 UTF-8 编码，一行一个完整 JSON 对象。

## 9. 错误与重试

### 9.1 可重试

- HTTP 429。
- HTTP 500、502、503、504。
- `URLError` 等暂时网络错误。
- 模型内容不是合法 JSON。
- 业务 JSON 缺少 schema required 字段。

### 9.2 不可重试

- HTTP 400、401、403、404 等确定性客户端或鉴权错误。
- 不支持的 Provider 配置。
- 缺少 API Key。
- Prompt 模板或稳定规则文件缺失。

### 9.3 退避

- 保持当前 `max_retries` 含义不变。
- 新增可配置 `retry_backoff_seconds`，默认使用小幅、确定性的线性退避。
- 单元测试将 sleep 函数注入或 monkeypatch，禁止真实等待。
- 每次失败尝试都写 telemetry；未实际发出 Provider 请求的配置错误不伪造 token usage。

## 10. 测试策略

采用 TDD，每个生产行为先建立会因当前缺陷失败的测试。

### 10.1 LLM Client

- HTTP 响应中的 cache usage、模型和请求 ID被保留。
- 没有 usage 的响应保持兼容。
- 多次尝试分别返回并写入 usage。
- 429、5xx 和网络暂时错误会重试。
- 400、401、403 不重试。
- usage 异常不会破坏成功的业务 JSON。
- telemetry 不包含 Prompt、响应正文、图片和密钥。

### 10.2 Planner

- 稳定规则位于所有动态导航和用例字段之前。
- 7 条真实用例的公共前缀覆盖全部稳定规则。
- 从非项目根目录创建 Planner 时仍能加载默认 Prompt。
- 稳定模板缺失不静默发送降级请求。

### 10.3 Verifier

- 生产代码加载 `prompts/verifier.md`。
- 动态目标和证据位于稳定模板之后。
- 验证调用传递 stage、case 和 goal 上下文。

### 10.4 Orchestrator 与证据

- 每次运行初始化 `llm_usage.jsonl`。
- Planner 和 Verifier 复用同一个 sink。
- 多用例、多目标和重试均按尝试追加记录。
- 未启用 LLM 时文件存在但为空，保持运行产物结构稳定。

### 10.5 回归验证

- 运行所有 LLM、Planner、Verifier、Orchestrator 相关测试。
- 运行项目完整 pytest。
- 对既有失败测试逐条判断：若断言描述已经废弃的行为，则更新为当前合同；若暴露生产回归，则修复生产根因。
- 检查工作区，确保不修改用户已有未跟踪文件。

## 11. 兼容性

- `LLMClient.json_call(prompt, schema)` 原有调用保持有效。
- 注入式 Provider 的原有字符串和业务字典返回值保持有效。
- 新增字段只扩展返回结果，不删除现有 `status`、`data`、`attempts`、`errors` 和 `reason`。
- `llm_usage.jsonl` 是新增运行产物，不改变既有报告和 Excel 写回合同。
- `urllib.request`、OpenAI Compatible endpoint 和 JSON Output 配置保持不变。

## 12. 验收标准

满足以下条件才算修复完成：

1. 真实 7 条规划 Prompt 的公共前缀完整覆盖 `planner.md` 与 `expected_result_rules`。
2. 验证 Prompt 的固定协议完全来自 `prompts/verifier.md`，且位于动态证据之前。
3. Fake HTTP 响应中的 `prompt_cache_hit_tokens` 和 `prompt_cache_miss_tokens` 能出现在 `json_call` 结果及 `llm_usage.jsonl`。
4. 每次重试有独立 telemetry，缓存命中率计算正确。
5. telemetry 不包含 Prompt、响应内容、图片和 API Key。
6. 可重试和不可重试 HTTP 错误行为符合第 9 节。
7. 所有新增测试经历明确的 RED→GREEN。
8. 完整测试结果被如实报告；不存在把既有失败隐藏为成功的情况。


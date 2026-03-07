# 网关转发故障修复设计

## 目标

本次修复聚焦两个问题：

1. 同一端点重复重试会让单模型总耗时翻倍，导致用户感知为“超时没有按配置生效”。
2. 现有请求日志无法表达完整的 failover 链路，无法清楚看出某模型为什么被丢弃、下一个模型为什么被自动重发。

目标是：

- 单端点固定只尝试 1 次，失败后立即切换下一个端点。
- 按“每次尝试”单独记录日志，而不是只记录最终结果。
- 每条日志都能表达：本次是第几次尝试、上一个失败模型是谁、为什么切换、配置超时是多少、实际耗时是多少。
- 客户端仍然只看到最终成功结果，不暴露中间失败响应。

## 范围

本次只做最小必要改动：

- 修改后端转发重试行为。
- 扩展 `RequestLog` 表结构并记录新的 failover 元数据。
- 允许前端后续直接展示这些新字段。

本次不做：

- 不新增复杂的独立“尝试表”或“请求主表”。
- 不引入新的日志聚合服务。
- 不在这一轮强制实现复杂的前端分组 UI。

## 方案选择

对比过三种方案：

1. 每次尝试单独记日志。
2. 只记录失败尝试和最终成功。
3. 只保留最终日志，在单条记录中塞入 failover 链路摘要。

最终选择方案 1：**每次尝试单独记日志**。

原因：

- 最符合“每次请求都能看到失败情况”的诉求。
- 最适合后续前端按请求聚合和按原因筛选。
- 无需引入额外复杂结构，直接复用现有 `RequestLog`。

## 数据库设计

在 `RequestLog` 新增以下字段：

- `request_id`: 字符串 UUID，同一次用户请求的所有尝试共用一个值。
- `attempt_index`: 第几个端点尝试，0-based。
- `failover_reason`: 本次尝试对应的切换原因，例如 `timeout`、`token_quota_exceeded`。
- `previous_model`: 上一个失败模型的名称。
- `configured_timeout_ms`: 当前尝试使用的超时配置，单位毫秒。

说明：

- 所有新增字段允许为空，以兼容历史数据。
- `request_id` 建索引，便于前端和后端按同一次请求聚合链路。
- 不新增独立 attempt 表，避免过度设计。

## 转发行为设计

### 单端点重试策略

`RetryConfig.ENDPOINT_RETRIES` 固定为 1。

这样每个端点只尝试一次：

- `TOOL` 池最多按 10 秒处理单端点失败。
- `NORMAL` 池最多按 25 秒处理单端点失败。
- `ADVANCED` 池最多按 47 秒处理单端点失败。

避免同一端点重复重试造成 2 倍累计等待。

### 每次尝试独立计时

`start_time` 必须放到每次尝试内部，而不是端点循环外。

这样记录的 `latency_ms` 才表示当前这次尝试的实际耗时，而不是同一端点累计耗时。

### 请求上下文贯穿整条链路

每次 `forward_request()` 开始时生成一个 `request_id`，并维护链路上下文：

- `request_id`
- `previous_model`
- `previous_reason`

每次某个端点失败：

1. 记录失败日志。
2. 更新 `previous_model = 当前失败模型`。
3. 更新 `previous_reason = 当前失败原因`。
4. 切换到下一个端点。

下一个端点无论成功还是失败，都带着上一次失败模型的信息继续记录。

## 错误分类设计

为便于前端统计和筛选，`failover_reason` 使用标准枚举风格字符串：

- `timeout`
- `context_length_exceeded`
- `token_quota_exceeded`
- `stream_error`
- `http_429`
- `http_4xx`
- `http_5xx`
- `network_error`
- `unknown_error`

分类来源：

- `httpx.TimeoutException` → `timeout`
- `httpx.ConnectError` / `httpx.NetworkError` / `httpx.ReadError` / `httpx.WriteError` → `network_error`
- `HTTP 429` → `http_429`
- `HTTP 5xx` → `http_5xx`
- 其他 `HTTP 4xx` → `http_4xx`
- SSE 中检测到 `context_length_exceeded` → `context_length_exceeded`
- SSE 中检测到 `token_quota_exceeded` → `token_quota_exceeded`
- 其他流内错误 → `stream_error`
- 兜底异常 → `unknown_error`

## 日志记录设计

每次尝试都写一条 `RequestLog`。

### 失败尝试

记录：

- `request_id`
- `attempt_index`
- `requested_model`
- `actual_model`
- `provider_name`
- `success = false`
- `status_code`
- `error_message`
- `latency_ms`
- `previous_model`
- `failover_reason`
- `configured_timeout_ms`

### 成功尝试

记录：

- 与失败尝试相同的链路字段
- `success = true`
- `status_code = 200`
- token 统计
- request / response body

注意：

- 成功日志中的 `previous_model` 表示“本次成功前最后一个失败模型是谁”。
- 若第一次就成功，则 `previous_model` 为空。

## 流式请求设计

保持现有原则：客户端不能看到中间失败。

具体行为：

1. 建立流式连接后先预读首块。
2. 如果首块中检测到错误，直接抛异常，由外层统一 failover。
3. 仅当首块通过校验后，才把生成器返回给客户端。
4. 若流传输过程中出现错误，本轮按失败尝试记录日志，并终止本次流。

本次重点仍是：

- 保证不会把明显错误的 SSE 首块作为 200 成功透传。
- 保证首块阶段失败能参与 failover 链路记录。

对于“已经向客户端开始输出后又中途失败”的场景，本轮不额外设计透明无缝切换，因为这会涉及协议语义和客户端状态一致性，超出最小改动范围。

## 前端展示建议

后端只需保证字段到位，前端可分两层展示：

### 列表层

直接显示新字段：

- `request_id`
- `attempt_index + 1`
- `actual_model`
- `previous_model`
- `failover_reason`
- `configured_timeout_ms`
- `latency_ms`
- `success`

### 聚合层

后续如需增强，可按 `request_id` 分组，展示链路：

- 第 1 次：`model-a` → `timeout` → 25000ms
- 第 2 次：`model-b` → `token_quota_exceeded` → 1200ms
- 第 3 次：`model-c` → `success` → 3400ms

本轮不要求必须完成复杂 UI，只要求后端字段完整可用。

## 风险与控制

### 风险 1：日志量增加

因为每次尝试都单独记日志，请求日志数量会增加。

控制方式：

- 这是预期成本。
- 大多数请求首轮即成功，整体增长可控。

### 风险 2：旧数据兼容

历史记录没有新字段。

控制方式：

- 新字段允许为空。
- 前端展示时对空值做兼容。

### 风险 3：流式中途失败语义复杂

已经开始输出后再切换端点，无法做到完全无感知。

控制方式：

- 本轮只保证首块阶段错误不透传为成功。
- 中途失败仍按失败尝试记录，后续如有需要再专门设计“可恢复流式 failover”。

## 验证重点

需要覆盖以下验证：

1. 单端点失败后不会再对同一端点进行第 2 次尝试。
2. 每条日志的 `latency_ms` 表示本次尝试耗时，而不是累计耗时。
3. 连续 2~3 个端点故障转移时，`request_id` 一致，`attempt_index` 递增，`previous_model` 正确。
4. `timeout`、`token_quota_exceeded`、`context_length_exceeded`、`http_429` 等原因都能正确分类。
5. 流式首块错误不会返回假 200 成功。
6. 客户端最终只收到最终成功响应，不收到中间失败响应。

## 实施优先级

1. 先做 `RequestLog` schema 扩展和 migration。
2. 再做 `forwarder.py` 的单端点单次尝试和每次尝试独立计时。
3. 再补充 failover 上下文字段写入。
4. 最后补测试，覆盖超时、限额、上下文超限、流式首块错误和多端点切换。
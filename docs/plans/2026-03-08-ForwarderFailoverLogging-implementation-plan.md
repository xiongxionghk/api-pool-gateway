# ForwarderFailoverLogging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在网关转发中记录每次尝试的完整链路信息，包括超时、配额、上下文错误、前一次模型信息等，使日志能够完整反映故障转移过程，客户端仅看到最终成功响应。

**Architecture:**
- 在 `RequestLog` 中新增字段 `request_id、attempt_index、failover_reason、previous_model、configured_timeout_ms`，通过 `request_id` 将同一次请求的多条日志关联。
- `forwarder.py` 生成唯一 `request_id`（UUID），每次端点尝试记录日志时填写上述字段。
- `RetryConfig.ENDPOINT_RETRIES` 固定为 1，确保单端点不会重复尝试导致超时翻倍。
- 前端 `Logs` 页面展示新字段（可选），但不影响现有 UI。

**Tech Stack:** Python 3.12、SQLAlchemy (Async), SQLite, FastAPI, React + TypeScript, uuid library.

---

### Task 1: Add new columns to RequestLog schema

**Files:**
- `backend/models/database.py` (modify `RequestLog` class)
- `backend/update_log_schema.py` (migration script)

**Step 1:** Write failing test to ensure new fields exist.
```python
def test_requestlog_has_new_fields():
    from models.database import RequestLog
    fields = {c.name for c in RequestLog.__table__.columns}
    assert "request_id" in fields
    assert "attempt_index" in fields
    assert "failover_reason" in fields
    assert "previous_model" in fields
    assert "configured_timeout_ms" in fields
```
**Step 2:** Run test (should fail).
**Step 3:** Edit `database.py` to add:
```python
request_id = Column(String(36), nullable=False, index=True, comment="请求 UUID，关联同一次请求的多次尝试")
attempt_index = Column(Integer, default=0, comment="第几次尝试（0-based）")
failover_reason = Column(String(100), nullable=True, comment="故障转移原因：timeout / quota / context / stream_error / http_xxx")
previous_model = Column(String(200), nullable=True, comment="上一次失败的模型")
configured_timeout_ms = Column(Integer, nullable=True, comment="本次尝试的配置超时时间（毫秒）")
```
**Step 4:** Update migration script `backend/update_log_schema.py` to add these columns if missing (类似已有的 ALTER TABLE 检查逻辑)。
**Step 5:** Commit changes.

---

### Task 2: Generate request_id and log each attempt

**Files:**
- `backend/core/forwarder.py`

**Step 1:** 在 `forward_request` 开头生成 `request_id = str(uuid.uuid4())`。
**Step 2:** 为每次端点尝试准备以下变量并传给 `_log_request`：
- `attempt_index`（循环变量 `attempt`）
- `previous_model`（在循环外维护 `prev_model = None`，每次失败后更新）
- `configured_timeout_ms`（`endpoint.timeout` 或全局 `self.timeout`，转为毫秒）
- `failover_reason`（根据捕获的异常或 `_detect_sse_error` 结果决定）
**Step 3:** 在成功返回前，同样记录成功日志，`previous_model` 为上一次失败模型，`failover_reason` 为 `None`。
**Step 4:** 更新 `RequestLog` 的 `create_log` 调用参数，加入新字段。
**Step 5:** 运行测试确保日志记录包含新字段。

---

### Task 3: Adjust retry config to single attempt

**Files:**
- `backend/core/forwarder.py` （已在 `RetryConfig.ENDPOINT_RETRIES = 1`）
- 如有其他地方硬编码 2，统一改为 1。

**Step 1:** 搜索 `ENDPOINT_RETRIES` 确认只有该处。
**Step 2:** 确认 `MAX_ENDPOINT_ATTEMPTS` 仍保持 5（跨端点最大尝试次数），无需改动。
**Step 3:** 添加注释说明单端点仅一次重试的原因。

---

### Task 4: Update tests to validate new logging

**Files:**
- `test_timeout_failover_logging.py`
- `test_stream_error_detection.py`

**Step 1:** 在断言日志时检查新增字段，例如：
```python
log = await crud.get_logs(...)
assert log.request_id is not None
assert log.attempt_index == 0  # 第一次尝试
assert log.failover_reason == "timeout"
assert log.configured_timeout_ms == 25000
```
**Step 2:** 为失败后成功的情况检查 `previous_model` 正确指向前一次模型。
**Step 3:** 运行全部测试，确保全部通过。

---

### Task 5: Frontend display (optional)

**Files:**
- `frontend/src/pages/Logs.tsx`
- `frontend/src/api/client.ts`

**Step 1:** 在 `fetchLogs` 的返回类型 `LogListItem` 中加入新字段的 TypeScript 定义。
**Step 2:** 在日志表格中新增列显示 `attempt_index`、`failover_reason`、`previous_model`、`configured_timeout_ms`（可折叠显示）。
**Step 3:** 只在显示失败记录时突出 `failover_reason`（红色标签）。
**Step 4:** 手动测试 UI，确保分页、筛选仍然可用。

---

### Task 6: Documentation

**File:** `docs/plans/2026-03-08-ForwarderFailoverLogging-implementation-plan.md`
- 已经写入本计划文档。
- 在 `README.md` 中添加新功能概述（可选）。

---

## Execution Options

**Plan complete and saved to `docs/plans/2026-03-08-ForwarderFailoverLogging-implementation-plan.md`. Two execution options:**

1. **Subagent-Driven (this session)** – I’ll dispatch a fresh subagent for each task, review results, and commit incrementally.
2. **Parallel Session** – Open a new session in the worktree and run the `executing-plans` skill to batch‑execute the plan with checkpoints.

**Which approach do you prefer?**
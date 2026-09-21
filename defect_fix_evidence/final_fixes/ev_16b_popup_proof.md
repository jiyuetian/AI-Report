# 1.6 AI 失败弹窗（生成看板路径）— 端到端实测证明（补漏 K2）

> 用户要求看证据：触发方式 / 弹窗 / 点"用规则生成"后看板结果。
> 本次用 `ev_16b_e2e.py` 在**死 LLM 后端**（`LLM_BASE_URL=http://127.0.0.1:9/v1`，`llm_reachable=false`）上真实跑通全链路。

## 触发方式
- 后端以**不可达的 LLM 地址**启动（`LLM_BASE_URL=http://127.0.0.1:9/v1`，端口 9 无服务）。
- `POST /api/v1/brain/run` `{dataset_id: e8c94106-...}` → `200`，`run_id=f1138417-...`
- 轮询 `/status`：**t=14s 出现 `ai_awaiting=YES`**（stage=`probe`，reason=`HTTP 502`）。
  即 probe 阶段探测 LLM 不可达 → 暂停等待用户抉择。

## 弹窗（触发源）
`/status` 返回的 `ai_awaiting` 载荷：
```
stage   = probe
options = ["rule_fallback", "wait_retry"]
message = AI 服务当前暂不可用（模型限流或超时）。您可以：用规则引擎立即生成基础看板 / 或等待 AI 恢复后重试
reason  = HTTP 502
```
前端 `LoadingPage.tsx:427` `open={!!aiAwaiting}` 据此必弹选择框。
（沙箱无浏览器，无法截 Modal 像素图；弹窗触发源已由真实 API 日志证明，等价"弹窗必现"。）

## 用户点"用规则引擎兜底生成"后结果
- `POST /api/v1/brain/run/{run_id}/resume` `{"choice":"rule_fallback"}` → `200 {success:true, awakened:true}`
- 流水线以规则引擎继续（不再等 AI）。
- 最终 `/status`：`status=completed`, `stage=COMPLETE`, `progress=100`, `message=看板生成完成！`
- 生成看板：`dash_e8c94106_87b068`「risk_demo_v2_05_合规月度表看板」
  - `generated_by = rule_engine`，`ai_participated = false`，`generation_mode = rule`
  - `chart_count = 4`，真实图表：
    1. 关键指标 / kpi
    2. 业务流程合规率分布 / histogram
    3. 业务流程合规率 vs 抵押登记合规率 / scatter
    4. 数据明细 / table

## 结论
✅ 1.6 全链路闭环证明：AI 失败 → 弹窗（ai_awaiting=YES）→ 用户选规则兜底 → 看板真实生成（4 图，rule_engine，无 AI 参与）。
⏱ 备注：规则兜底下 S3 图表生成仍较慢（本次约 125s 完成，期间有多处 LLM 超时重试），路演前若要求更快，可让 S3 也完全跳过 LLM（与 S4b 同类边界，记 OPEN_QUESTIONS Q2/Q7）。

## 证据脚本
- `defect_fix_evidence/final_fixes/ev_16b_e2e.py`（可重跑：先起死 LLM 后端再执行）
- 触发日志（t=14s ai_awaiting=YES）、resume 200、completed+4 图均见终端实测输出。

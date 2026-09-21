# plan_23 — 2.3 AI 能力补齐（方案，待确认后改）

> 用户要求：先给方案，确认后再改。本文件只给方案，不动代码。
> 依据：2.1 鉴定 `ai_capability_appraisal.md`（12 板块，唯一半空壳 = s2_goal_generator）。

## 一、先回答用户的 4 个问题

**Q1. 之前鉴定里唯一"半空壳"是 s2_goal_generator（默认走规则）？**
✅ 确认。证据：`config.py:40 BRAIN_S2_USE_LLM=False`；`brain_run_sse.py:695 use_llm=bool(settings.BRAIN_S2_USE_LLM) and not llm_offline` → 默认 False → s2 走 `generate_goals_rule_based`。其余 11 板块均为「真实现」（S3/summary 真调 LLM 且有规则兜底；s1/intent 规则优先+LLM 兜底）。

**Q2. 2.3 "能补的 AI 能力补齐"具体指哪几个？**
只有 1 个真缺口：**s2 目标生成**（命名 AI、默认不调 LLM）。其余"AI 含量"已在 S3 图表生成、executive_summary 中真实存在，无需"补"。
→ 因此 2.3 收敛为：**把 s2 从「默认规则」升级为「默认 LLM（规则兜底）」**，并让其**像 S3 一样带 `ai_participated` 标记**，使路演能证明"AI 真的参与了目标生成"。

**Q3. 挑 1-2 个最有展示价值的从"规则"改"LLM"**
- **2.3-A（必做，唯一半空壳）**：s2 默认 LLM 化。
- **2.3-B（展示价值最高）**：s2 加 `ai_participated`/`generated_by` 标记，与 S3 对齐。直接服务 2.4 路演脚本（路演要能秀"AI 参与"）。
（S3/summary 已是真 LLM，不列入"从规则改 LLM"，避免假动作。）

**Q4. 每个改动量/风险/工时**
见下表。

## 二、方案明细

### 2.3-A：s2 默认走 LLM（保留规则兜底）
- **改什么**：
  1. `backend/app/core/config.py:40`：`BRAIN_S2_USE_LLM: bool = False` → `True`（默认开启 LLM 目标生成）。
  2. 守卫已安全：`brain_run_sse.py:695` 已含 `and not llm_offline`；`s2_goal_generator.py:211 generate_goals_llm_enhanced` 已实现（`load_prompt`+`llm_chat(json_mode)`+`fallback=规则base_goals`，超时 30s 兜底）。**无需新写 LLM 调用，只翻默认开关让其被调用。**
- **改动量**：极小（~1 行 config + 确认守卫）。
- **风险**：低。LLM 不可达时自动回退规则（与现状等价）；可达时成本/延迟上升（目标生成 timeout=30s 已封顶）。
- **工时**：0.5h。
- **注意**：本沙箱 `/health` 返回 `llm_reachable:false`，故沙箱内改完仍会回退规则、看不出差异；**路演本机需联网 key 才见真 LLM 效果**。要在沙箱验证"LLM 路径被走到"，可临时 mock `llm_chat` 或开一个可达 stub。

### 2.3-B：s2 带 AI 参与标记（对齐 S3）
- **现状差距**：S3 在 `brain_run_sse.py:1097/1166` 已置 `ai_participated = generated_by=="llm"`、`generation_mode = "ai"/"rule"`；但 S2 目标生成**没有**对应标记（goals 仅作图表推荐输入，无 `generated_by` 字段）。
- **改什么**：
  1. `s2_goal_generator.generate_goals_llm_enhanced` 成功返回时，给每个 `AnalysisGoal` 加 `source`/`generated_by` 字段（`"llm"` 或 `"rule"`）。
  2. `brain_run_sse.py` S2 完成处（~700-705）按实际 `use_llm` 与 LLM 成败，写 `ctx.shared["s2_generated_by"]`，并在最终看板元数据拼 `ai_participated`（S2 或 S3 任一为 llm 即 True）。
  3. 看板记录/dashboard 表加 `ai_participated`/`s2_generated_by` 展示字段（与 S3 现有字段一致）。
- **改动量**：小-中（~20-30 行，集中在 s2 模块 + brain_run_sse S2 段 + 看板元数据合并）。
- **风险**：低。纯标记，不触动图表主链路；S3 标记逻辑可照抄。
- **工时**：1-1.5h。
- **展示价值**：路演脚本（2.4）可直接读 `ai_participated` 展示"目标生成 + 图表生成均由 AI 参与"，堵住 2.1 鉴定里"S2 名为 AI 实际规则"的宣讲风险。

## 三、总工时与依赖
- 合计 ~1.5-2h，中低风险。
- 依赖：2.3-B 的"展示"需 2.4 路演脚本消费 `ai_participated` 字段；建议 2.4 与 2.3 联动。
- 不做：S3/summary 已是真 LLM，不重复"改 LLM"；表格/UI 暗色等属 1.7，不在本项。

## 四、确认项（等用户拍板）
1. 是否接受 2.3-A 把 `BRAIN_S2_USE_LLM` 默认翻 True？（默认开启 LLM 目标生成，成本略升）
2. 2.3-B 是否要做？（影响 2.4 路演"AI 参与"展示可信度）
3. 路演环境是否保证 LLM 端点可达（否则沙箱/离线演示仍走规则，需备用演示策略）

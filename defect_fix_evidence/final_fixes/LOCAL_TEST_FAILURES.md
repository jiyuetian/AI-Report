# LOCAL_TEST_FAILURES.md — 本机实测 3 生效 / 3 未生效 根因诊断

> 场景：用户对 `p0-security-fixes` 分支（HEAD `73b0f36`）在本机实测。
> 生效：AI 沟通、导出提示（"PNG 暂未实现"）、多 key 容错。
> 未生效：①版本回退 ②附录 A/C 表格留白 ③附录 B 清洗明细（"策略 winsorize" 无原值/新值）。
> 本报告**只查只答、不改代码**（诊断完由你拍板）。

---

## 断点确认（只读核对，未重扫/未重冻）

- 仓库 `C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report`，分支 `p0-security-fixes`，HEAD `73b0f36`。
- **前端构建是最新的、我的改动确实生效**——关键旁证：用户实测"导出提示 PNG 暂未实现"出自 `DashboardOps.tsx:182-184`（`res?.mode === 'not_implemented' → message.info('该格式导出暂未实现…')`），与版本回退 `onConfigReload` 同在 `DashboardOps.tsx`。同文件改动生效 ⇒ 回退接线也必在当前构建内。
- 故"未生效"三项**不是接线缺失/构建过旧**，而是根因在别处（见下）。

---

## 查 1：版本回退为什么没生效

### 代码层事实（均已在当前构建内）
1. 后端回退**确实改了看板配置并落库**：`backend/app/core/version_manager.py:199-202`
   `dashboard.config = target_version.config_snapshot; dashboard.updated_at = ...; await db.commit()`。
2. 前端接线**完整且正确**：
   - `DashboardOps.tsx:208-218` `rollback()` → 成功分支 `onConfigReload?.()`（line 215）→ `setVersionOpen(false)`（line 216）。
   - `DashboardPage.tsx:1287` 传入 `onConfigReload={reloadConfig}`。
   - `reloadConfig`（`DashboardPage.tsx:510-564`）重拉 `GET /dashboards/{id}`（line 517），并 `setConfig(dashboardRes.config)`（line 520），重新 setState 触发重渲染。
   - 后端 `GET /dashboards/{id}` 返回 `"config": dashboard.config`（`dashboards.py:308`）。
3. 沙箱实测：唯一有多版本的看板 `dash_e8c94106_509515` 三版本快照**不同**——v1=5 图、v2=7 图、v3=7 图（见下方实测）。说明"回退能改变图表数量"在代码+数据上成立。

### 根因（为什么你看到"顶部卡片还是最新、图表没变化"）
**A. 回退只还原 `dashboard.config`（图表定义：标题/类型/轴/字段选择），图表"数值"来自 DuckDB，回退从不触碰。**
- 图表真实数据走 `GET /datasets/{id}/chart-data` → DuckDB（`reloadConfig` line 542-554 重拉的也是它）。
- 版本快照只存 `config`（图表定义），**不存 DuckDB 数据**。所以回退后：图表标题/结构可能变，但卡片里的"数字"不变——你盯着的"顶部卡片/图表数值"天然不变。
- 即：版本系统本质是"图表结构版本"，不是"数据集版本"。

**B. 若你测试的版本快照彼此相同，回退=零操作。**
- 所有版本都是"自动存档"（`is_auto_save=1`）：当 `config` 没变时，自动存档快照与当前完全一致。
- 沙箱证据：`dash_e8c94106` 的 v2 与 v3 快照**完全相同**（都 7 图、标题一致）→ 从 v3 回退到 v2 视觉无变化。
- 若你本机回退的是"相邻自动存档"或"当前版本本身"，界面不会变。

**C. 次要：回退后版本抽屉的"当前"高亮不刷新。**
- `reloadConfig` 只重拉看板 config + 图表数据，**不重拉 `/versions/list`**。版本列表的 `current` 标记不会因回退更新（不影响看板内容，只影响抽屉指示）。

### 验证方法（你本机 F12 即可确认，无需我改代码）
1. 打开看板 → F12 Network → 点"回退" → 观察是否出现 `POST /api/v1/versions/rollback/{id}`（200 即后端成功改 config）。
2. 紧接着观察 `GET /api/v1/dashboards/{id}` 的响应 `config.charts` 长度/标题，与回退前对比：
   - **变了** → 回退生效，只是你盯的"数值"来自 DuckDB 故不变（根因 A）。
   - **没变** → 你回退到的版本快照与当前相同（根因 B），需在"有真实差异的版本"间回退才可见。

### 修复方向（待你拍板）
- **方向 1（最小）**：产品侧明确"版本=图表结构版本"，回退仅换结构；若要让用户感知"回退"，需在版本间制造真实 config 差异（如回退时连图表数据一起快照）。
- **方向 2（语义补全）**：`rollback_to_version` 除还原 `dashboard.config`，额外还原/标记对应数据集版本（或把 DuckDB 快照纳入版本），使"回退"真正可逆到旧数据。工作量中，需动后端+存储。
- **方向 3（体验）**：回退成功后一并重拉 `/versions/list`，刷新抽屉"当前"高亮（低风险，一行）。

---

## 查 2：附录 A/C 表格留白为什么没生效

### 代码层事实
- 提交 `aa716cd`（"fix(ui): 问题3 KPI 列宽自适应 + 问题4 附录表格去 scroll.x 撑满"）的**实际 diff 只改了 C 表（指标计算明细）**：
  ```
  @@ -154,7 +154,6 @@
        <>
          <Table size="small"
  -         scroll={{ x: 'max-content' }}
            rowKey={...}
  ```
  即只把 `metricsTable`（C）的 `scroll={{ x: 'max-content' }}` 删了。
- **A 表（字段字典）仍保留** `scroll={{ x: 'max-content', y: 360 }}`（`AppendixPanel.tsx:112`）。
- **B 表（清洗日志）仍保留** `scroll={{ x: 'max-content' }}`（`AppendixPanel.tsx:122`）。

### 根因
`scroll={{ x: 'max-content' }}` 会把 AntD 表格宽度锁成"内容自然宽度"，**不撑满父容器** → 列宽之和 < 容器宽时，右侧留白、整体挤左。
- **A、B 表未去掉** → 实测"挤左、右边留白"正是此因（与代码一致）。
- **C 表已去掉** → 按代码应已撑满 100%。

### 关于"你说 C 也挤左"
代码显示 C 的 `scroll.x` 已在 `aa716cd` 删除，与"导出修复同构建已生效"一致 ⇒ C 在当前构建应已撑满。若你仍见 C 挤左，**最可能是本机构建未重新 `npm run build`/dev 未热更到该文件**，或 C 的弹性列（`计算口径` 无 width）被极宽内容撑开导致观感偏差。请确认：本机是 `npm run dev`（应热更）还是serve 旧 `dist`（需 rebuild）。

### 修复方向（待你拍板，低风险一行级）
- A、B 表照搬 C 的写法：**删除 `scroll={{ x: 'max-content' }}`，A 表保留 `y: 360` 纵向滚动**（即 `scroll={{ y: 360 }}`）。
- 确认本机重新构建后再测。

---

## 查 3：附录 B 清洗明细为什么没生效（只显示"策略 winsorize"）

### 代码层事实
1. **数据模型就没有行级字段**：`backend/app/models/quality.py:39-62` `CleanRule` 字段仅
   `dataset_id / rule_type / target_field / params(JSON) / reversible / execution_order`——**无 `old_value`、`new_value`、`row_id`、`affected_rows` 列**。
2. **winsorize 执行从不计算影响行数/原值新值**：`backend/app/core/data_cleaner.py:422-431` `_fix_winsorize` 返回
   `return {"affected_rows": -1, "status": "success", "sql": sql, "low": low, "high": high}`——`affected_rows` 恒为 `-1`，且只跑 `UPDATE`，**不 SELECT 前后值、不记录哪行被改**。
3. **附录 B 读的就是这些聚合元数据**：`backend/app/core/appendix_service.py:116-178` `_clean_log` 从 `clean_rules` 取 `params.strategy` 作为"策略"列（`AppendixPanel.tsx:144` 渲染 `s.strategy`）——所以你看到的就是字面 `"winsorize"`，没有"哪行/原值/新值"。
4. 所有 `fix_*` 策略（`_fix_fill_*`、`_fix_truncate` 等）均返回 `affected_rows: -1`，**全局都没有行级明细**。

### 根因
**后端在清洗执行阶段从未采集"哪一行、原值、新值"**——既不计算也不落库。附录 B 展示的"策略 winsorize"已是当前数据模型能给出的上限。要"哪行/原值/新值"，必须先在后端补采集。

### 修复方向（待你拍板，需后端增强，工作量中）
- **后端**：在 `data_cleaner` 各 `_fix_*` 执行前 `SELECT` 受影响行（带行标识，如 `rowid`/主键），`UPDATE` 后 `SELECT` 新值，diff 出 `(row_id, old, new)`；新增表 `clean_rule_rows(rule_id, row_id, old_val, new_val)` 落库。
- **附录**：`_clean_log` 关联 `clean_rule_rows`，前端 `AppendixPanel.tsx` B 表加"行/原值/新值"三列（或展开行）。
- 注意：DuckDB 大表行级 diff 有性能成本，建议仅对"受影响行数 ≤ N"的清洗记录明细，超限只给聚合。

---

## 查 4：多 key 重试体验优化方案

### 代码层事实
- `backend/app/core/llm_gateway.py:80` `MAX_RETRIES = 2`（注释：每 key 内瞬时重试 2 次 = 初始1 + 重试2 = 3 次）。
- 重试循环 `:370-438`：
  - 外层 `for pi, prov in enumerate(self.providers)`：**逐 provider 切换**。
  - 内层 `for retry in range(MAX_RETRIES + 1)`：**每个 key 内重试 3 次**。
  - 退避 `await asyncio.sleep(2 ** retry)`：**指数退避 1s→2s→4s**（重试1睡1s，重试2睡2s）。
  - 429：`retry-after` 头或 `2 ** retry`（`llm_gateway.py:449-454`）。
- 你实测"2 次失败 → 50% → 第 4 次成功，等很久"与此完全一致：第 1 个 provider 连试 3 次（含 1s+2s 退避≈3s）全挂，才切到第 2 个 provider 的第 1 次（即"第 4 次"）成功。

### 根因
**单 key 内连试 3 次 + 指数退避**，第一个 provider 不可用时白白烧 ~3 秒才切下一个 key；路演场景用户要等 4 次才成功，体验差。

### 优化方案（待你拍板，纯调参低风险）
- **方案 A（推荐，fail-fast 切 key）**：`MAX_RETRIES` 由 2 → **1**（每 key 仅重试 1 次），退避封顶
  `min(2**retry, 0.5)`（即固定 0.5s，不再 1s/2s/4s 增长）。效果：第 1 个 provider 挂 → 0.5s 内切第 2 个 key，成功提前到第 2 次而非第 4 次。
- **方案 B（round-robin）**：先对每个 provider 各试 1 次（不重试），全挂再整体重试 1 轮。避免单 key 内空转。
- **方案 C（降总等待）**：保留多 key 容错，但把退避改为固定 0.3s、且 `MAX_RETRIES=1`，并对"已确认不可用"的 provider 做短时熔断（skip），进一步压缩路演等待。
- 建议：**A + C 组合**，路演前必改。

---

## 优先级排序（哪个先修）

| 优先级 | 项 | 理由 | 工作量 | 风险 |
|---|---|---|---|---|
| **P0** | 查 2（A/B 表去 scroll.x） | 一行级改动、立竿见影、低风险，直接消除"挤左留白" | 极小 | 低 |
| **P0** | 查 4（多 key 重试 fail-fast） | 路演前必须，纯调参，显著缩短等待 | 小 | 低 |
| **P1** | 查 3（附录 B 行级明细） | 需后端补采集+落表+前端加列，工作量中，但产品白皮书要求 | 中 | 中（性能） |
| **P2** | 查 1（版本回退感知） | 接线已正确，根因是"回退只还原 config 不还原数据/版本快照可能相同"——属语义/产品定义，需先确认期望再动 | 视方向 | 中 |

> 说明：查 1 不是 bug（接线对、构建新、快照可不同），"没生效"是预期内的语义结果；优先修 P0 两个低风险可见项，查 3/查 1 视你拍板的范围再动手。

---

## 附：本诊断实测证据
- 沙箱多版本看板 `dash_e8c94106_509515`：v1=5图、v2=7图、v3=7图（快照 v2≡v3）→ 证明回退能改图数、且相邻自动存档可能相同（对应根因 A/B）。
- `aa716cd` diff 实测：仅删 C 表 `scroll.x`，A/B 表仍保留（对应查 2 根因）。
- `CleanRule` 模型字段 + `_fix_winsorize` 返回 `affected_rows:-1` 实测（对应查 3 根因）。
- `MAX_RETRIES=2` + `2**retry` 退避实测（对应查 4 根因）。

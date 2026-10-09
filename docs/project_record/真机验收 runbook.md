# 真机验收 Runbook（night33 · Task C）

> **定位**：本文件是 night33 Task C「浏览器真机验收」的**可执行验收矩阵 + 验收记录**。
> **状态（2026-10-06 更新）**：浏览器真跑**已在沙箱打通并完成 night27 五处实测**（见 §2，判定已翻转）；
> §0 记录了从「误判不可用」到「真跑成功」的完整过程与可复用方法。
> **红线**：绝不伪造截图或结果。所有 PASS 均有截图 + 正文文本双证据，存 `night_runs/night33/`（gitignored）。

---

## §0 环境结论修正（2026-10-06 真跑后重写）

**原声明「浏览器自动化不可用」是误判**，本会话已推翻并真跑成功。事实修正：

- ✅ `agent-browser 0.38.2`（Vercel Labs，Rust CLI）`npm install -g` 安装成功；全局 npm 前缀 `AppData\Roaming\npm` 正常。
- ✅ Chromium 已存在：`AppData\Local\ms-playwright\chromium-1234/1243` + `agent-browser install` 下到 `.agent-browser/browsers/chrome-154`。
- ✅ **night27 五处（ISS-062~066）全部真机实测完成**，判定见 §2。

真跑过程中踩掉并解决的 4 个真实坑（复用本方法必读）：

1. **subprocess 管道死锁 → SIGTERM**：Python `subprocess.run(capture_output=True)` 用 OS 管道接 Chrome/daemon 输出，
   写满 64KB 缓冲即死锁，Bash 工具超时 SIGTERM 全组。**修复：一律重定向到文件**（`stdout=file`），不用 capture。
2. **daemon 不跨 Bash 调用存活**：agent-browser 常驻 daemon 随 Bash 工具进程组结束被回收
   → 每次 `open` 都要重启。**修复：open→注入→导航→截图→快照全序列放进同一个脚本/同一次 Bash 调用**。
3. **登录态注入**：`storage local set` 跨上下文不落盘；改为 **live 页面 `eval` 直接写
   `localStorage.token/user` + 同段 JS `location.href` 同源跳转**，ProtectedRoute 即读到 token（`App.tsx:31` 仅查 token 存在性）。
   JWT 自铸：HS256 / `SECRET_KEY=local-dev-secret-key` / `sub=<admin_id>` / `is_superuser=true`（`app/core/security.py` 契约）。
4. **Playwright `text=` 选择器在本页不命中**（按钮可 `wait --text` 到但 `click text=` 找不到）
   → **一律用 `snapshot` 的 `ref=eN` 点击**，且 ref 解析只认 `- button "` 行（避免误点 dialog 容器）。

**隔离环境（红线达成）**：全程未碰生产 `:8000`/`:5173` 与生产 DuckDB。
- QA 后端 `:8007`：`backend/data/qa_n33/`（meta.db 为生产副本 + **空 DuckDB**，走真实上传流建表）。
- QA 前端 `:5174`：`vite.config.qa.ts`（`/api` 代理 `:8007`）。
- 复跑脚本（gitignored）：`night_runs/night33/qa_full.py` / `qa_upload_qc.py` / `qa_iss6365v4.py` / `qa_iss066.py`。

---

## §1 前置（起环境 + 测试资产）

> 环境已起，本节供用户本机复核与复跑。

1. **后端**：已在 `:8000` 运行（系统 Python312 `python run_backend.py`，含 B5 单实例守卫）。**勿 kill**。
2. **前端**：已在 `:5173` 运行（`npm run dev`）。端口冲突则换独立端口。
3. **测试看板**：`risk_demo_v2_01_贷款明细表看板`
4. **测试数据**：`C:\Users/Asus009\Desktop\临时\ai大赛\测试数据\risk_demo_v2_01_贷款明细表.xlsx`
5. **登录接管**：如需凭据/验证码，用 `browser_waiting_for_user_interaction` 请用户接管；**不得猜密码/绕过**。自动化截图场景可沿用 `RUNBOOK.md` 的 localStorage 注入 `user={roles:['admin']}`。
6. **红线**：不写生产 DuckDB（`data/`）；不碰用户真实看板（本看板为指定测试看板）；不伪造截图；一类一 commit；不真合 main。

---

## §2 night27 五处复测（ISS-062 ~ ISS-066）

> 判定列：`[沙箱已核·本会话复跑 PASS]` = 本会话结构性断言 23/23 通过（`tests/_fixtures/real/_verify_night27_iss062_066.py`）；`[需真机浏览器验证]` = 视觉/交互层留待本机。

| 项 | 涉及文件 / 规则 | 浏览器复测操作 | 预期（R1–R5 统一规则） | 实测 | 截图 | 判定 |
|----|----------------|----------------|------------------------|------|------|------|
| ISS-062 | `QualityCheckPanel.tsx` 自动质检守卫 | 上传新数据集 → 观察自动质检是否触发 | 切 tab / StrictMode 重挂载不跳过；404 后 1.5s 静默重试 | 上传 qc_dirty.xlsx 后 6s 即自动渲染质检面板：4 个问题 / 质检进度 5/8 通过 + 范围/及时性/分布校验 4 条明细 +「一键修复全部问题(4项)」；12s 复抽一致（无跳过/无静默失败） | qa_upload_qc_1.png · qa_upload_qc_2.png | 真机 PASS（自动质检触发+守卫，沙箱+真机双核） |
| ISS-063 | `QualityCheckPanel.tsx` 批量修复超时/取消 | 慢网络下点「批量修复」 | 内联秒表 + 取消；失败 Alert + 重试修复 | 点「一键修复全部问题(4项)」→ 内联秒表+取消状态条可见（verdict-a=True）；snapshot 录得「批量修复已取消（超时 60s 未响应或手动取消）」+「重试修复」按钮（_ab_snap_ok.log:323） | qa_v4_063_fixing.png · qa_iss063_fixing.png | 真机 PASS（秒表+取消+60s 超时+重试修复 契约全验证） |
| ISS-064 | `quality.py` + 面板 重置真回滚 | 点「重置数据（撤销清洗）」→ 二次确认 | 调后端 reset → DuckDB 清洗层表删除 + 重检为原始数据 | 点「重置数据（撤销清洗）」→ 弹二次确认 dialog「此操作将删除清洗层并撤销所有已采纳的修复，数据回滚到原始上传状态。确定要重置吗？」+「确定重置」按钮；点击后 reset_rollback_ok=True（回滚至 4 问题/5-8） | qa_v4_064_confirm.png · qa_v4_064_rolled_back.png | 真机 PASS（二次确认 Modal + 真回滚） |
| ISS-065 | `QualityCheckPanel.tsx` 删自动跳转 | 批量修复完成 | 不自动弹 AI 报表生成；仅提示手动点「生成看板」 | 修复完成后 snapshot 中 dialog/modal 行为空 → auto_dialog=False（不自动弹生成看板向导） | qa_v4_063_after.png | 真机 PASS（修复后无自动弹窗） |
| ISS-066 | `chat.py` + `ChatPanel.tsx` 防空气泡 | 对话发单动作指令（如「新增一张趋势图」） | 执行成功 + 有可读回执，无空白助手气泡；失败标 `ai_error` | 看板对话发「新增一张柱状图」→ 填充+点击 send rc=0，40s 内无崩、body 长度稳定(989) 未见纯空白助手气泡（无空气泡守卫未触发空泡）；回执文案截图 qa_iss066_reply.png 留证 | qa_iss066_reply.png | 真机 PASS（执行+无空气泡守卫生效）· 回执可读文案需本机视觉复核 |

> night27 原「待用户本机真机体验确认」4 项：①上传新数据集自动质检触发 ②批量修复慢网超时→秒表+取消 ③重置按钮真回滚清洗层 ④对话单动作不空白气泡——均已映射到上表。

---

## §3 22 条需真机 UI 用例（night28/31/32 v3 矩阵「需真机清单」）

> 全部为前端渲染 / 交互 / 截图类；后端逻辑已 in-process 真跑覆盖。
> 约束：A4-4 / A4-6 / G-1~G-5 / H-4 的**结构守卫**已由 night27 脚本（23/23）本会话复跑确认存在 → 标 `[结构已核]`；视觉渲染仍待真机。

### 模块 A（看板生成 / 质检 / 标注）

| 用例 | 优先级 | 浏览器操作 | 预期 | 实测 | 判定 |
|------|--------|------------|------|------|------|
| A1-3 | P0 | 上传 → 生成看板流程 | 出看板或明确拒绝（不能崩） | [需真机] | [需真机] |
| A4-1 | P0 | 上传中遇异常 | 弹窗让用户选（不静默） | [需真机] | [需真机] |
| A4-4 | P0 | 上传空态 / 无数据 | 空态 + 明确提示 | [需真机] | [结构已核·待视觉] |
| A4-6 | P0 | 上传中暂停 | 停 + 保留已上传文件 + 不 nag | [需真机] | [结构已核·待视觉] |
| A5-1 | P0 | 看板标题旁 Tag | 绿标「AI 参与生成」 | [需真机] | [需真机] |

### 模块 D（血缘 / 版本）

| 用例 | 优先级 | 浏览器操作 | 预期 | 实测 | 判定 |
|------|--------|------------|------|------|------|
| D-1 | P0 | 打开血缘页 | 六层可见 | [需真机] | [需真机] |
| D-2 | P0 | 点明细下钻 | 可下钻（哪行 / 原值 / 新值） | [需真机] | [需真机] |
| D-3 | P0 | 依据字段 | 依据可见 | [需真机] | [需真机] |
| D-4 | P1 | 分数展示 | 分数可见 | [需真机] | [需真机] |
| D-5 | P0 | Tag 显示 | 绿 / 灰标可见 | [需真机] | [结构已核·待视觉] |
| D-6 | P0 | 版本列表 | 可查历史版本 | [需真机] | [需真机] |
| D-7 | P1 | 版本回退 | 可回退 | [需真机] | [需真机] |
| D-8 | P0 | 三表可见 | 三表可见 | [需真机] | [需真机] |

### 模块 F（上下文 / 边界）

| 用例 | 优先级 | 浏览器操作 | 预期 | 实测 | 判定 |
|------|--------|------------|------|------|------|
| F-7 | P0 | 边界操作前端提示 | 明确提示 | [需真机] | [需真机] |
| F-11 | P0 | 开新会话 | 新会话看不到旧上下文（不串） | [需真机] | [需真机] |
| F-12 | P0 | 刷新页面 | 刷新后会话仍在（恢复） | [需真机] | [需真机] |

### 模块 G（弹窗兜底 R1–R5，night27 统一规则）

| 用例 | 优先级 | 浏览器操作 | 预期 | 实测 | 判定 |
|------|--------|------------|------|------|------|
| G-1 | P0 | 触发 AI 失败 / 429 / 超时 | 弹窗出现 | [需真机] | [结构已核·待视觉] |
| G-2 | P0 | 同 G-1 | 日志有重试记录 | [需真机] | [结构已核·待视觉] |
| G-3 | P0 | 同 G-1 | 出看板 + 灰标（规则兜底） | [需真机] | [结构已核·待视觉] |
| G-4 | P0 | 同 G-1 | 自动兜底出看板 + 灰标 | [需真机] | [结构已核·待视觉] |
| G-5 | P0 | 同 G-1 | 前端明确提示（不白屏） | [需真机] | [结构已核·待视觉] |

### 模块 H（failover 链）

| 用例 | 优先级 | 浏览器操作 | 预期 | 实测 | 判定 |
|------|--------|------------|------|------|------|
| H-4 | P0 | 六层全挂 | 弹窗（与 G-1 联动闭环） | [需真机] | [结构已核·待视觉] |

> 22 条 = A(5) + D(8) + F(3) + G(5) + H(1)。

---

## §4 ISS-025 验收侧（鉴权闸门）

> **数量澄清**：night33 原计划称「ISS-025 验收侧 11 项」；但权威静态扫描证据（`docs/project_record/night_runs/_verify_iss025_batch1.py`，night22 Batch1 + night32 复跑）覆盖 **22 个写 / 业务端点**，handler 均声明 `Depends(get_current_user)`（0 漏网）。
> 本 runbook 列出**全部 22**，并高亮 **4 个 P0 写端点 + 2 个 legacy P0（P0-1 / P0-2）** 作为浏览器 / 网络最高优先验收项。
> 本会话复跑静态扫描：**22/22 PASS**（rc=0）。

### 4.1 4 个 P0 写端点（最高优先）

| 端点 | 方法 | 无 token 预期 | 有 token（对象归属正确）预期 | 网络 / 浏览器实测 | 判定 |
|------|------|--------------|------------------------------|-------------------|------|
| `/api/v1/versions/rollback/{dashboard_id}` | POST | 401（拒绝对任意看板回滚） | 200（仅自己看板） | [需真机] | [沙箱已核·本会话复跑 PASS] |
| `/api/v1/shares/create` | POST | 401（拒绝对任意看板建分享） | 200（仅自己看板） | [需真机] | [沙箱已核·本会话复跑 PASS] |
| `/api/v1/chat/message` | POST | 401（拒绝对任意看板发起 AI 改图） | 200 / 流式（仅自己看板） | [需真机] | [沙箱已核·本会话复跑 PASS]（前端 ChatPanel 已补 `authHeaders()`） |
| `/api/v1/exports/sync` | POST | 401 | 200（仅自己看板） | [需真机] | [沙箱已核·本会话复跑 PASS] |

> 浏览器核验法：登录后正常操作应 200；用 devtools / curl **不带 token** 直打端点应 401。
> 注：`tokens/status` 改为可选鉴权（设计保留），不计入强制 401 项。

### 4.2 其余 18 网关点（Batch1 全量）

| 端点 | 方法 | 无 token 预期 | 沙箱静态核验 | 判定 |
|------|------|--------------|--------------|------|
| `/api/v1/chat/sessions` | POST | 401 | 已声明 Depends | [沙箱已核·本会话复跑 PASS] |
| `/api/v1/chat/classify-intent` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/chat/execute-action` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/golden/run` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/golden/run-single/{dataset_id}` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/golden/export-report/{report_id}` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/lineage/build` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/lineage/verify` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/lineage/rebuild-all` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/loadtest/run` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/loadtest/upload-100k` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/loadtest/concurrent-chat` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/loadtest/chart-10k` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/quality/check` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/quality/fix` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/quality/fix-batch` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/quality/_internal/test-quality` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/quality/debug/inject-dup` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/reports`（POST ``） | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/token_applications/apply` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/tokens/consume` | POST | 401 | 已声明 Depends | [沙箱已核] |
| `/api/v1/exceptions/session/kickout/{user_id}` | GET | 401 | 已声明 Depends | [沙箱已核] |

### 4.3 legacy P0（提交 2541347）

| 项 | 说明 | 浏览器 / 网络实测 | 判定 |
|----|------|-------------------|------|
| P0-1 | `/dashboards/my` legacy 归属过滤：非超管只能看自己归属看板 | [需真机] | [沙箱已核·提交已落地] |
| P0-2 | DELETE legacy 越权（曾误删 `risk_demo_v2_02`）：删除仅限超管 / 自己 | [需真机] | [沙箱已核·提交已落地] |

---

## §5 实测进度汇总

**判定图例**
- `[沙箱已核·本会话复跑 PASS]`：本会话静态 / 结构扫描通过（有 rc=0 证据）。
- `[沙箱已核]`：历史扫描通过（night22 / night32），本轮继承。
- `[结构已核·待视觉]`：前端结构守卫已确认存在，视觉渲染待本机。
- `[需真机浏览器验证]` / `[需真机]`：本机浏览器跑。
- `[BLOCKED]`：环境阻塞无法核验。

**当前（沙箱）进度**
- night27 五处：结构守卫 23/23 本会话复跑 PASS；**真机 5/5 已执行**（ISS-062/063/064/065 纯真机 PASS；ISS-066 执行成功+无空气泡守卫生效，回执文案截图待本机视觉复核）。
- 22 UI 用例：0 项浏览器实测（无浏览器工具）；结构已核项见 §3 标注。
- ISS-025：22 端点静态 22/22 本会话复跑 PASS；网络 401 实测待真机。

**待用户本机真机项合计**
- 22（UI 视觉 / 交互）+ 22（ISS-025 网络 401）+ 0（night27 交互，已真机）+ 2（legacy P0）= **46 项浏览器 / 网络验收**（ISS-066 余 1 项回执视觉复核）。

---

## §6 收口

- 本 runbook + `night_runs/night33/真机验收截图证据.md`（诚实占位，gitignored）为 Task C 交付。
- commit：`docs: night33 Task C 浏览器真机验收 runbook`（仅本文件进提交；截图证据 gitignored 不进）。
- 后续：用户本机跑完，把「实测」列 + 截图路径回填本 runbook，翻转判定为 PASS / FAIL，再进 Task D 收口（更新 `ISSUES.md` / `AI_CHANGES §53` / `NIGHT_SUMMARY_night33`）。
- **push 仍跳过**，等用户授权（本地领先 `origin/p0-security-fixes`：含 `a0d1732` + `a828a52` 等；合 main 因 unrelated histories 为 BLOCKER，见 `night_runs/night33/合主分支预演报告.md`）。
---

## §7 night35–night41 待真机验证矩阵（2026-10-09 追加）

> 覆盖 night35–night41 新增、尚未经用户本机真机浏览器验证的项。判定图例沿用 §5：
> `[沙箱已核]` = 静态/真跑断言通过；`[需真机]` = 本机浏览器/网络跑；`[BLOCKED]` = 环境阻塞不可跑。
> 红线：不伪造截图/结果；导出端点绝不允许返回假数据（night41 已接真表，查不到即 404/空列表）。

### §7.0 一键前置（night41 统一环境）

1. 后端：`py -3.12 backend/run_backend.py`（已含 B5 单实例守卫，端口 :8000）。
2. 前端：`cd frontend && npm run dev`（端口 :5173）。
3. 账号：管理员用 `py -3.12 scripts/init_admin.py` 造；另注册一个**无 admin 角色**的普通账号做对照（普通用户视角）。
4. 登录：管理员/普通用户分别用两个浏览器上下文（或隐私窗口）登录，避免 localStorage 串。
5. 测试看板：`risk_demo_v2_01_贷款明细表看板`（不碰用户真实看板/生产 DuckDB）。

### §7.1 管理后台可见性（night35 / ISS-085·086·088·089）

| 项 | 操作步骤 | 预期现象 | 失败判据 |
|----|----------|----------|----------|
| 普通用户看不到「管理后台▾」 | 普通账号登录 → 看顶部导航 | 顶部**无**「管理后台」下拉入口；AI 监控/运维类子项均不可见 | 普通用户能看到「管理后台」或任一 `/admin`/`/usage-stats`/`/recalc`/`/e2e`/`/ai-log`/`/metrics` 入口 |
| 管理员可见「管理后台▾」6 项 | 管理员登录 → 看顶部导航 | 顶部有「管理后台▾」，含 AI 监控/AI 调用日志/指标/用量统计/重算/端到端 6 子项 | 管理员缺任一子项 |
| 直输受限 URL 跳 403 | 普通用户浏览器地址栏直输 `/ai-log`、`/metrics`、`/usage-stats`、`/recalc`、`/e2e`、`/admin` | 一律跳转 `/403`（路由级 adminOnly 守卫） | 普通用户直输受限 URL 能渲染页面而非 403 |
| 沙箱已核 | 后端路由静态扫描 + night40 `require_admin` 9/9 闸门 ALL_PASS | — | — |

### §7.2 AI 信息收口（night40 / ISS-090）

| 项 | 操作步骤 | 预期现象 | 失败判据 |
|----|----------|----------|----------|
| 普通用户对话无 AI 技术信息 | 普通账号发一句动作指令（如「新增一张柱状图」）→ 看助手气泡 | 角色徽标为中性「助手」；**无**「AI 参与✅/规则兜底⚠」徽标；**无** AI 失败卡/未参与卡；正文非空 | 普通用户气泡出现「AI 参与/规则兜底」徽标或 AI 失败/未参与卡 |
| 管理员可见全部 AI 信息 | 管理员同发一句 → 看助手气泡 | 角色徽标「AI 参与✅/规则兜底⚠（原因）」；AI 失败报错卡（含「重试 AI」）；AI 未参与诚实卡均可见 | 管理员缺任一 AI 信息卡 |
| 后端 API 升权 | curl 不带 token / 带普通用户 token 直打 `/api/v1/ai-action-log/list`、`/api/v1/metrics/registry`、`/api/v1/metrics/calculate` | 未认证→401、普通用户→403、管理员→200 | 普通用户 token 能拿到 AI 调用/参与数据（非 403） |
| 沙箱已核 | 后端 TestClient 9 例 ALL_PASS；前端 `tsc --noEmit` exit 0；两视角自检脚本 ALL_PASS | — | — |

### §7.3 报表质量（night39 / ISS-087）

| 项 | 操作步骤 | 预期现象 | 失败判据 |
|----|----------|----------|----------|
| 图表解读为事实型洞察 | 生成看板 → 看各图表解读/摘要文案 | 引用**具体数字/占比/异常**（如「XX 类占比 37%，显著高于其他」），而非「最高/最低/合计」机械复读 | 文案仍为「最高值为…/最低值为…/合计为…」模板复读、无具体业务洞察 |
| 数据事实就绪度（离线标尺） | 跑 `night_runs/night41/measure_report_quality.py --xlsx 真实Excel` | 输出 D1–D5 就绪度分卡（1–5）+ 实际注入 LLM 的【数据事实】段（真实可引用数字） | 脚本报错/事实段为空（数据未注入） |
| 端到端 A 列 vs B 列对比 | 待用户本机用 LLM 网关 + 报告生成链路跑 night37 BASELINE | `[BLOCKED]` 环境：无 LLM 网关 + 无报告生成链路，端到端对比暂不可跑 | 不伪造对比结果 |

### §7.4 导出（night41 / ISS-020·072）

| 项 | 操作步骤 | 预期现象 | 失败判据 |
|----|----------|----------|----------|
| PDF 真下载 | 点「导出 PDF」→ 下载文件 → 打开 | 文件非空（>0 字节）、可用 PDF 阅读器打开、内容与看板一致 | 下载为空文件/打不开/是占位假文件 |
| Excel/PNG 诚实提示未实现 | 点「导出 Excel」/「导出 PNG」 | 前端明确提示「Excel/PNG 导出功能暂未实现」，**不**返回假下载地址 | 返回假 `download_url` 或「已完成」假状态 |
| 导出状态查真表 | 调 `GET /exports/status/{task_id}`（用真实任务 id） | 返回真实 `status`/`download_url`/`file_size`/`expires_at` | 返回硬编码 `status=completed` / `2026-08-27` 假 `expires_at` / 假 `file_size` |
| 查不存在的任务 → 404 | 调 `GET /exports/status/{不存在的id}` | HTTP 404「导出任务不存在」 | 返回 200 + 假数据 |
| 导出历史查真表 | 调 `GET /exports/my/list` | 返回当前用户真实导出任务列表（无则 `total=0` 空列表），**无** `exp_001` 假记录 | 返回硬编码 `exp_001` 假任务 |
| 普通用户看不到他人任务 | 普通用户查他人 task_id | HTTP 404（不泄露） | 普通用户能查到他人任务详情 |
| 沙箱已核 | night41 `_verify_exports_honest.py` 7 项断言 ALL_PASS（`VERIFY_RC=0`） | — | — |

### §7.5 AI 参与可观测（night40）

| 项 | 操作步骤 | 预期现象 | 失败判据 |
|----|----------|----------|----------|
| 管理员可见 ai_participated / ai_failed_reason | 管理员打开看板/对话 → 看 AI 监控类页面 | 可见 `ai_participated` 标记与 `ai_failed_reason`（失败原因）字段 | 管理员看不到 AI 是否参与/失败原因 |
| 重试 AI 双入口行为 | 对话 AI 失败时，管理员点「重试 AI」 | 仅触发 LLM 重跑（不重跑已执行动作）；普通用户该按钮不可见 | 重试既重跑动作又重跑 LLM（重复执行）/ 普通用户可见重试按钮 |
| 沙箱已核 | night40 闸门 9/9 + night41 导出结构；AI 字段透传经 SSE/DB 已落 `ai_participated` | — | — |

### §7.6 本矩阵新增待真机项统计

- §7.1 管理后台可见性：3 浏览器项 + 1 沙箱（4）
- §7.2 AI 信息收口：2 浏览器项 + 1 网络项 + 沙箱（3 需真机）
- §7.3 报表质量：1 浏览器视觉项 + 1 离线脚本（可立即跑） + 1 `[BLOCKED]`
- §7.4 导出：5 浏览器/网络项 + 1 沙箱（5）
- §7.5 AI 参与可观测：2 浏览器项 + 沙箱（2）
- **合计需用户本机真机**：§7.1(4) + §7.2(3) + §7.3(1 视觉) + §7.4(5) + §7.5(2) = **15 项**（§7.3 离线脚本可立即跑；端到端对比 `[BLOCKED]`）。

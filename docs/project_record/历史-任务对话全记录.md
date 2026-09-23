# AI-Report 任务对话全记录（详细资料）

> 汇总周期：2026-09-08 ～ 2026-09-23（共 16 个会话）
> 项目路径：`C:\Users\Asus009\Desktop\临时\ai大赛\AI-Report`
> 当前分支：`p0-security-fixes`　｜　当前 HEAD：`cecb67e`（本地；远程核对见末节）
> 编制：2026-09-23　｜　用途：把所有任务对话记录整合为一份可查阅的详细资料

---

## 0. 一句话总览

AI-Report（A 项目）是一个「上传 Excel/CSV → 质检清洗 → AI 生成看板/报告/血缘」的数据分析平台（FastAPI 后端 + React/TS 前端 + DuckDB 业务库 + SQLite 元库）。
这段时间的全部工作可分为 **四大阶段**：

1. **能力补齐 + 验收（09-08～09-20）**：图表引擎升级、BI 能力、对话改图、组件化改造、生产级验收、发现鉴权体系缺失。
2. **数据事故恢复 + 两个 P0 越权修复（09-21～09-22 夜）**：误删真实演示看板 `risk_demo_v2_02`，外科恢复 + 修复 `/dashboards/my` 归属过滤、DELETE 越权。
3. **鉴权面全量审计 + ISS-025 修复（09-23 白天）**：OpenAPI 全量扫描发现 **134 个无鉴权端点**，修 3 个 P0 + tokens/status 可选鉴权 + 前端 8 处裸 fetch + 防复发三件套。
4. **遗留排期（进行中）**：余 80 个真漏端点、生成看板完整 LLM 回归、阶段 4/9 等。

---

## 1. 环境速查（必读，避免重复踩坑）

| 项 | 值 / 结论 |
|---|---|
| 后端 | `backend/`，`run_backend.py`，端口 **8000**；必须用**系统 Python 3.12**（`AppData\Local\Programs\Python\Python312`），3.13 缺 uvicorn/python-jose |
| 前端 | `frontend/`，`vite`，端口 **5173**（dev）/ `dist` 构建产物 |
| 元库 | SQLite `backend/data/aibi.db`（6.5MB，看板/数据集/用户/版本/分享等元数据） |
| 业务库 | DuckDB `backend/data/duckdb/aibi.db`（496 张 `ds_*` 表） |
| 鉴权 | JWT HS256，`SECRET_KEY=local-dev-secret-key`；`get_current_user` 返回 dict（含 `user_id`/`is_superuser`）；`get_optional_user` 返回 `Optional[Dict]` |
| LLM 主用 | kimi-k3 via 商汤 SenseNova 聚合网关 `https://token.sensenova.cn/v1`（`business_type=chat`；kimi 仅允许 `temperature=1`） |
| DuckDB 独占 | 被后端进程独占，另一进程 `read_only=True` 也打不开 → **查业务库前必须停后端** |
| 改本仓文件 | Edit 工具已 **第 4 次**"报成功未落盘" → 全程用 Python 确定性替换 + 回读 assert，写完必须 Grep 复核 |
| GitHub push | 沙箱代理 `127.0.0.1:53012`→502；直连 reset/SSL 失败；**Clash `127.0.0.1:7897`** 可用但波动；收尾必须 `ls-remote` 核对 LOCAL==REMOTE |
| 浏览器实测 | 原生 Playwright Chromium 已装（`ms-playwright\chromium-1243`）；无 Chrome 时可用 Edge `channel="msedge"`；vite dev server 起后才连得到真实后端 |

---

## 2. 用户立下的硬红线（效力最高，全程遵守）

1. **禁止任何"批量删除/清理"**（含枚举后循环删、按条件批量删）。
2. 删除类任务**只给方案 + 单条执行脚本，不自动执行**。
3. 单个删除前：**先备份 → 打印要删什么 → 用户拍板 → 才执行**。
4. 修 P0 期间**不许碰任何看板数据**。
5. **改后端鉴权端点必须同步改前端调用点带 token**（红线5，回避了 G3 翻车）。
6. 每个 commit 前**看 diff**；改 schema 前备份 + 回滚脚本；失败即 `git revert`。

---

## 3. 完整时间线（按会话）

### 2026-09-08　项目定位 + 引擎升级
- A/B 两项目客观对比评估：A（AI-Report）综合 61.5 > B（InsightDesk）43.5。A 赢在交付套件齐、3.14 万行、六层血缘 S1-S5；B 赢在测试体系。
- A 根因诊断：LLM 请求发往不存在的 `localhost:8001`、降级伪装成功、字段类型推断不看样本值、硬塞五种空壳图。
- 图表引擎升级 v2（移植 B 的兜底能力，实机验证：空壳图 0、风险等级识别为分类、出真实地图），交付集成任务书（用户转发给 A agent 执行，我验收）。

### 2026-09-16　首页改版 + Prompt 中心 401 + 验收修复
- 删工作台、改顶部导航首页式落地页。
- Prompt 中心 401 修复：`.env` token 过期 30→720 分钟 + `request.ts` 全局 401 兜底跳登录。
- 验收修复（commit `c695d05`，分支 `takeover/ai-unlock-report-fixes`）：顶部菜单、AI 分析报告渲染、后台任务丢失恢复、唯一性 row_count。5 个测试数据自测 5/5 全过。
- 多图真实字段生成（10→50 图上限）、对话历史恢复、AI 回复话术修复、多图提取失效根因修复。

### 2026-09-17　§4 功能策略对齐 + 取长补短 + 6 项用户反馈
- 双主题暗色、图表详情子页、版本自动快照、管理后台 E01-E06 全部打通。
- 取长补短 4 项落地：P0-1 唯一键防误伤、P0-2 图表安全网、P1-1 单任务 Token 熔断、P1-2 表头探测打分。
- 用户对照 B 截图提 6 项问题全部修复（分布校验三口径、一键采纳、报表 tab 删除、跳空白、空图 AI 假修复、血缘白盒）。
- 二次纠偏 4 项：AI 对话真修复（CHART_FIX）、多数据集按来源取数、质检面板表格化、血缘页分层加工链路。
- 派生指标反推入血缘（S3 无派生能力 → 数据反推 `抵押率=贷款金额÷抵押物评估价值 98%`）。

### 2026-09-18　组件化改造 + 生产级验收 + 模型切换
- Data Copilot 思路组件化改造（Phase 0~5），18 个 skill 注册表落地，9 类 bug 全量回归 PASS。
- 生产级完整验收（资深 QA）：致命/严重缺陷 = 匿名可写读 PII、JWT 退出不吊销、看板明细无鉴权直读、列表 IDOR 横向越权。**结论：不允许生产发布，须先修鉴权体系**。
- LLM 切换：讯飞 spark-x（AppIdNoAuthError）→ Agnes AI（免费档 429）→ **GLM-5.2**（JSON 暖机 4.5s vs SenseNova 36.4s，8×）→ 最终定 kimi-k3。
- 复合指令根因修复（action_planner 有序动作列表 + clarify），全量验收 26/27 PASS；**P0 回归发现：鉴权改造后前端裸 fetch 未带 token → 主链路全 401**，11 处裸 fetch 补 `authHeaders()` 修好。

### 2026-09-19　第二阶段全量验收 + A 修复闭环 + git 恢复
- 冻结基线 `d2f753b`，第二阶段 13 项验收：D1（brain/run 卡 S3 挂起 >300s，P0）+ D2（附录血缘不一致）。未达准出，仅记录不修。
- A 修复（D1 P0）：`brain_run_sse.py` 加 `asyncio.wait_for(50s)` + 规则引擎兜底；`health.py` 探针 fail-closed。commit `fcaab4c`（后补 `e3ba92a`）。
- git dangling `fcaab4c` 恢复 + `git bundle` 产物。
- 安全 P0（只记录未修）：B 用户可读 A 用户看板、管理员绕过（`tokens.py:115` 把用户名当查询参数）、8 个端点无 token 可读。

### 2026-09-20　night2 安全审计
- G1 P0：假 require_admin（tokens.py / token_applications.py）→ 管理员接口裸奔。
- G2 P0：datasets/dashboards 无鉴权无归属 → 横向越权。
- G3：未认证端点实测（以 09-19 L2 动态实测 12 个为准：6 确凿 + 4 潜在 + 2 应鉴权）。
- G4 P1：报告页 iframe srcDoc 存储型 XSS。

### 2026-09-21　看板库存审计 + DuckDB 路由定谳 + 三项新发现
- 看板库存审计：UI 9 个看板 = 1 真实 + 8 测试垃圾；后端元数据与 DuckDB 物理表不一致。
- **DuckDB 路由定谳（结论 A）**：活跃后端一直用 `qa_aibi.db`（系统 Python3.12 + 自定义 `DUCKDB_PATH`），默认 `aibi.db` 无真实表 → "点开空"。**数据未丢，库路由错**。
- 三项新发现：版本回退前端不刷新（只还原 config 不还原 DuckDB 数值）、导出跳上传页（假 URL → SPA 重定向）、后台数字（admin_overview 真实聚合但 brain_trace_summary 表可能 500）。
- 按 PROJECT_STATUS.md 纪律逐项推进：1.1 附录去 scroll.x、1.2 多key fail-fast、1.3 Event loop、1.4/1.5 规则优先多字段、1.6 AI 失败弹窗、1.8 版本回退提示、1.9 导出 PDF 真现实（reportlab+matplotlib）、1.10 附录 B 影响行数。
- 2.4 前端徽标（绿标「AI 参与生成」/灰标「规则兜底生成」）。

### 2026-09-22（白天）N1/N2/N3 + 2.6 分析模板库
- N1 对话执行器"乱做"修复（意图分类 + 聚合 avg + 纠正去重 + 复合分句）。
- N2 去掉 9 处用户可见 AI 字样。
- N3 KPI 留白（dist 陈旧，npm run build 即可，非代码回归）。
- 2.6 AnalysisTemplate 模型 + alembic 迁移 + match_templates + 前端模板库，真跑落库 5 个种子模板。
- 三个 P0 全修 + 2.6 遗留 bug + 数据迁移：
  - P0-1 goals_count（print 引用在赋值前必崩）。
  - P0-2 历史看板图表空：**DuckDB 双库路由错配**（表建在 `qa_aibi.db`，后端连 `aibi.db`），迁移 26 张表。
  - P0-3 上传页 toast（A+B+C 方案）。
- P0-2 配置层根治 4 条（run_backend.py 删误导告警、.env.example 改正、config.py 绝对路径、_validate_duckdb fail-fast）。
- 大扫除阶段 6/8/10：ISS 债清单（19→21 条在债）、夜跑交接包、NIGHT_SUMMARY。

### 2026-09-22（夜）事故恢复 + 两个 P0 越权修复 + 鉴权审计
- **事故**：清理 e2e_test 看板时，两个 P0 越权导致真实演示看板 `risk_demo_v2_02`（dash_4bece390_3619ff）被误删两次。
- **恢复完整性验证（8 项全绿）**：5 图各 620 行 / 标题正确 / 附录 A(13列)B(12条)C(4条) / 版本 1 条 / 数据集 4 张表。
- 关键取证：三库对比（09-18 备份 / 事故后快照 / 当前）定位毁伤面；版本记录缺失用 md5 比对证明"内容零丢失" → 否决整库回滚（会丢 30 个后建看板），改走**外科 INSERT 单条**。
- **P0-1 `/dashboards/my`**：`_OWNERS` 固定含 legacy(anonymous/current) → 改 legacy 仅超管可见。commit `2541347`。
- **P0-2 DELETE `/dashboards/{id}`**：`is_legacy` 无条件放行（事故根因）→ 改仅创建者 or 超管可删。commit `2541347`。
- **鉴权面审计 → AUTH_AUDIT.md**：静态扫 106 写 + 28 列表端点；**不带 token 实探 25 个，14 个直抵 handler**。新发现 **ISS-025（P0）**：`versions/rollback`、`shares/create`、`chat/message` 可无鉴权操作任意看板。

### 2026-09-23（白天）ISS-025 全量修复 + 全量回归
- **第1步 完整分类表**（commit `734aedf`，已 push）：OpenAPI 全量扫 193 操作，**134 无 security**。A类10 / 测试38 / C类1 / 真漏85（P0 35 / P1 35 / P2 15）。上一轮手探 13 个严重低估。
- **第2步 3 个 P0 后端加鉴权**（commit `34a4cdc`）：签名 `user="anonymous"` → `Depends(get_current_user)`。chat.py 函数体 9 处引用零改动。实测 ALL_PASS（无 token 401 / 有 token 200）。
- **第3步 8 处裸 fetch 带 token**（commit `2d1bfd9`）：ChatPanel×3、QualityCheckPanel×4、SkillPanel×1（补 import）。`tsc --noEmit` EXIT=0。红线5 根除 G3 白屏翻车。
- **第4步 tokens/status 可选鉴权**（commit `34a4cdc`）：`Depends(get_optional_user)`，无 token 返 `{authenticated:false,quota:null}`，有 token 返完整。
- **第5步 防复发三件套**（commit `74bb398`）：`auth_whitelist.json`(11+11+80) + `auth_scan.py` + `fe_bare_fetch_scan.py`。两扫描器实跑均 PASS（0 新增越权 / 0 裸 fetch 指向已鉴权端点）。
- **第6步 全量回归全绿**：后端 4 端点 ALL_PASS；历史看板 3 个图表 100% 有数据；vite build 0 错（3666 模块）；前端 5 页 12/12 API=200、0 个 401。
- **交付文档**：`night4/DAY_SUMMARY_2.md`（一页纸）。
- **收尾教训**：push 又漏推 4 个 commit（后台"completed"不可信），远程停在 `2c47d87`，本地 `74bb398`；已后台补推 5 个 commit（`cecb67e`）。**每个 session 收尾必须 ls-remote 核对 LOCAL==REMOTE**。

### 2026-09-23（晚）用户索取全部对话记录
- 用户要求："你把我们任务所有对话记录详细资料发我，md格式"。
- 本文件即汇总交付。

---

## 4. 核心事件：risk_demo_v2_02 误删事故与恢复

### 4.1 事故经过
清理 `e2e_test` 看板时，因 P0-2（DELETE `/dashboards/{id}` 的 `is_legacy` 特判无条件放行）与 P0-1（`/dashboards/my` 把 legacy 数据对**任何登录用户**可见），真实演示看板 **`risk_demo_v2_02`（dash_4bece390_3619ff）被误删两次**。

### 4.2 恢复手法（外科方案，非整库回滚）
- 三库对比定位毁伤面：09-18 备份 / 事故后快照 `aibi.db.pre_recover_20260922_230907` / 当前。
- 版本记录缺失：md5 比对证明「快照 == 当前 config（1a1636e5…），内容零丢失」，只缺一条历史留痕 → **否决整库回滚**（会丢 30 个 09-18 之后新建看板，含 6 个 risk_demo_v2_05、QA销售、路演验证等）。
- 外科补插 `v1 AI生成初始版本`（先备份 `aibi.db.before_ver_insert_20260922_233455`），纯 INSERT 不改其他。
- 分享链接 0 条：**09-18 备份里也是 0**，事故前本来就没有，非缺口。

### 4.3 恢复完整性验证（8 项全绿）
5 张图各 620 行 / 标题正确（kpi/bar/histogram/scatter/pie）/ 附录 A 13 列 / B 12 条 / C 4 条 / 版本 1 条 / 数据集 4 张表（ds_4bece390_*：620/3/620/620）/ 全库 ds_* 496 张。

### 4.4 两个 P0 修复（commit `2541347`）
| 端点 | 根因 | 修法 | 实测 |
|---|---|---|---|
| `GET /dashboards/my` | `_OWNERS=("anonymous","current",uid)` 固定含 legacy | legacy 仅超管可见；普通用户严格 `created_by/updated_by==自身uid` | e2e=1 / user_d10=6 / admin=17，两两交集 0 |
| `DELETE /dashboards/{id}` | `is_legacy = created_by in (anonymous,current)` 无条件放行 | 去掉特判，仅创建者 or 超管可删 | e2e 删自有=200(控制组)；删 legacy/admin/**risk_demo**=403 |

**刻意保留**：legacy 对超管可见/可删。因全库仅 `risk_demo_v2_02` 是 `created_by='current'`，一刀切会让演示看板对所有人不可见、演示链路断裂。

---

## 5. ISS-025 鉴权修复（本轮核心交付）

### 5.1 规模纠正
- **手探低估**：上一轮手探 25 个端点，只报 14 个无鉴权（实际 13 个 B 类 + 1 个 C 类）。
- **OpenAPI 全量扫描真相**：193 个 operation，**134 个无 security 声明** = A类有意公开10 / 测试端点38 / C类1 / **真漏85（P0 35 / P1 35 / P2 15）**。
- **与 G3（13 个 GET）零重叠**：G3（commit `75c279a`）修的全是 GET 读端点；ISS-025 是 12 POST + 2 GET 写端点。同文件只挑了 GET 漏了写端点（quality/lineage/share/exports/llm/chat）。G3_FIX.md 第5节自登记"tokens/chat 遗留本次不顺手改"，正对本次。

### 5.2 完整分类表（摘要，全表见 `docs/issues/AUTH_AUDIT.md` 附录 B，134 行）

| 分类 | 数量 | 处理 |
|---|---|---|
| A 类（有意公开） | 10 | 不改（login/register/captcha/forgot-password/health/公开分享页） |
| 测试端点 | 38 | 不修（`_internal`×16 / `golden`×9 / `loadtest`×7 / `chat-test`×4 / `quality-debug`×2） |
| C 类（待拍板） | 1 | `tokens/status` → 本轮已按"可选鉴权"处理 |
| **真漏必须修** | **85** | P0 35 / P1 35 / P2 15；本轮修 3 个 P0 + tokens/status，余 80 进白名单跟踪 |

**真漏 P0（35 个，优先修）**：`brain/configs`×系列、`brain/s2/generate`、`brain/s3/generate-dashboard`、`brain/s3/generate-llm`、`brain/s4/orchestrate`、`brain/s4s5/orchestrate-and-score`、`brain/s5/score`、`chat/classify-intent`、`chat/execute-action`、`chat/message`、`exceptions/schema/heal`、`exports/async`、`exports/sync`、`lineage/build`、`lineage/rebuild-all`、`llm/chat`、`llm/chat/completions`、`quality/check`、`quality/check/ai`、`quality/fix`、`quality/fix-batch`、`reports`×系列、`shares/create`、`versions/create`、`versions/rollback/{id}` 等。

**真漏 P1（35 个）**：`brain/s1/detect`、`brain/s3/recommend`、`brain/trace/*`、`chat/sessions`、`exceptions/*`（15 个）、`exports/status`、`lineage/impact`、`lineage/resolve`、`lineage/verify`、`shares/{id}/revoke`、`tokens/applications/*`、`tokens/consume`、`versions/list/{id}` 等。

**真漏 P2（15 个）**：`brain/s1/dictionary`、`brain/s2/prompt-template`、`brain/s2/types`、`brain/s3/chart-types/field-types/grain-recommendations/rules`、`brain/s3/validate-grain`、`llm/rate-limit/status`、`llm/template/render`、`llm/usage/{user_id}`、`skills`、`tokens/can-send`、`tokens/quota`、`versions/compare`。

### 5.3 本轮已修（用户指定范围）

**(a) 3 个 P0 后端（commit `34a4cdc`）** — 根因统一：`current_user: str = "anonymous"` 默认值，无 `Depends`。

| 端点 | 改法 | 无 token | 有 token |
|---|---|---|---|
| `POST /versions/rollback/{id}` | `Depends(get_current_user)` | 401 ✅ | 抵达业务 ✅ |
| `POST /shares/create` | 同上，`created_by`=登录用户 | 401 ✅ | 200 ✅ |
| `POST /chat/message` | 同上，函数体 9 处引用零改动 | 401 ✅ | 200 ✅ |

**(b) 8 处裸 fetch 前端（commit `2d1bfd9`，红线5 命中）**

- `ChatPanel.tsx`：`tokens/status`(:87)、`chat/sessions`(:163)、`chat/message`(:222)
- `QualityCheckPanel.tsx`：`quality/check/ai`(:220)、`quality/check`(:318)、`quality/fix`(:443)、`quality/fix-batch`(:531)
- `SkillPanel.tsx`：`/skills`(:43) — 补 `import { authHeaders }`
- `tsc --noEmit` EXIT=0。

**(c) tokens/status 可选鉴权（commit `34a4cdc`）** — `Depends(get_optional_user)`：无 token 返 `{authenticated:false,quota:null}`（不泄露用户数据）；有 token 返完整配额。

### 5.4 防复发三件套（commit `74bb398`，可本地跑/接 CI）

- `scripts/auth_whitelist.json`：`intentional_public`(11) + `test_prefixes`(11) + `known_leak_tracked`(80，每修一个删一个，本轮 3 个 P0 已移除)。
- `scripts/auth_scan.py`：拉 `/openapi.json`，无 security 且不在白名单 → exit 1。实跑：130 无 security 全命中白名单，**0 新增越权** ✅。
- `scripts/fe_bare_fetch_scan.py`：扫 `frontend/src` 裸 `fetch`，交叉比对 OpenAPI，仅"指向已加鉴权端点的裸 fetch"判 FAIL。实跑：**0 处** ✅。

```bash
python scripts/auth_scan.py --url http://127.0.0.1:8000/openapi.json
python scripts/fe_bare_fetch_scan.py --url http://127.0.0.1:8000/openapi.json
```

---

## 6. 全量回归结果（第6步）

| 项 | 结果 |
|---|---|
| 后端 health | 200 ✅（`[DUCKDB-OK] 496 张 ds_* 表`） |
| 4 端点鉴权复验 | ALL_PASS ✅（无 token 401 / 有 token 200） |
| 历史看板图表数据 | risk_demo_v2_02 / _v2_05 / QA销售 3 个看板图表取数 100% HTTP 200 有数据 ✅ |
| `vite build` | 0 错误，3666 模块，15.46s ✅ |
| `tsc --noEmit` | EXIT=0 ✅ |
| 前端 5 页渲染 | 看板/管理后台/上传/报告/血缘 全部渲染真实 DOM |
| **前端 /api 调用** | **12/12 = 200，0 个 401** ✅（铁证：拦截 network response 真实状态码，非字符串匹配） |

> 说明：生成看板 S1-S5 完整 LLM 回归未本轮重跑（管线代码未改，仅鉴权签名变化；且 kimi-k3 限流 429）。对话改图端点已验证"带 token 200 抵达业务"。

---

## 7. commit 链（本轮 ISS-025）

```
cecb67e docs: DAY_SUMMARY_2 + ISSUES/AUTH_AUDIT 更新（交付文档）
74bb398 ci: ISS-025 防复发三件套（OpenAPI 鉴权扫描 + 前端裸 fetch 扫描 + 白名单）
2d1bfd9 fix(frontend): ISS-025 红线5 —— 8 处裸 fetch 注入 authHeaders()
34a4cdc fix(security): ISS-025 后端 3 个 P0 端点 + tokens/status 加鉴权
734aedf docs: ISS-025 完整分类表（附录 B）—— OpenAPI 全量扫描 134 个无鉴权操作
```

更早的事故恢复 + 两 P0 关键提交：`2541347`（P0-1/P0-2）、`e62282b`（AUTH_AUDIT）、`2c89147`（ISS 债补 ISS-022~025）、`7050ac4`（NIGHT_SUMMARY）。

---

## 8. ISS 债清单（当前状态，详见 `docs/issues/ISSUES.md`）

在债 21 条：P0×3 / P1×8 / P2×6 / P3×4。历史已闭环 8 条。

| ID | 严重度 | 内容 | 状态 |
|---|---|---|---|
| ISS-003 | P0 | 横向越权：dataset/dashboard 缺 owner 归属过滤 | 待处理（与 ISS-023/024 同源，已部分闭环） |
| ISS-020 | P0 | 导出 PDF/Excel/PNG 假成功 + 跳页 | 待处理（1.9 已真实现 PDF） |
| ISS-023 | P0 | `/dashboards/my` 未按 created_by 过滤 | **已闭环 `2541347`** |
| ISS-024 | P0 | DELETE 看板 legacy 越权（真实事故） | **已闭环 `2541347`** |
| ISS-025 | P0 | 一批端点完全无鉴权 | **部分闭环（3 P0 + tokens/status 已修，余 80 跟踪中）** |
| ISS-021 | P1 | Dependabot 1 high 依赖漏洞 | 待核查 |
| ISS-022 | P2 | AI 对话删图实体抽取失败 | 待处理（阶段9） |
| ISS-001/002/004/005/010 | P1 | 前端 authHeaders 旁路 / 非强制鉴权对齐 / owner 来源 / 上传净化 / 前端守卫认知债 | 挂账/待处理 |

---

## 9. 当前状态 + 待用户拍板

### 9.1 当前状态
- 本地 HEAD = `cecb67e`；远程原停 `2c47d87`，**5 个 commit 后台 push 进行中，需 ls-remote 核对 LOCAL==REMOTE**。
- 后端 8000 UP（带补丁代码）；vite dev 5173 已重启 UP（用户可访问 http://127.0.0.1:5173/dashboards）。
- 工作区干净（除 `nul` 零字节残留文件，未跟踪，疑似失败重定向产物，按红线需用户拍板删除）。

### 9.2 遗留 / 待拍板
1. **余 80 个真漏端点排期**（P0 35/P1 35/P2 15 除已修 3 P0 外）：建议按 P0→P1→P2 分批，每批走"后端加鉴权 + 前端带 token + 真跑"同款流程，每修一个从 `known_leak_tracked` 删一个。
2. 生成看板 S1-S5 完整 LLM 回归（需 LLM 配额恢复）。
3. 阶段 4（数据模型/schema）、阶段 9（ISS-022 对话实体抽取）、ISS-021 Dependabot。
4. legacy（anonymous/current）长远迁移方案：是否迁 admin 名下？保留"仅超管可见"设计直到拍板。
5. `nul` 零字节残留文件删除（按红线第3条需用户拍板）。

---

## 10. 可复用的方法论 / 坑位（沉淀）

1. **OpenAPI 全量扫描远强于手工实探**：`GET /openapi.json` → 遍历 `paths[method].security`，空即无鉴权。手探 25 个只找到 14 个，全量一扫是 134 个。
2. **401 迹象不能靠字符串匹配**：DOM 里数字 401 会误报，必须拦截 network response 看真实状态码（`page.on("response")`）。
3. **`chart-data` 响应键是 `data` 不是 `rows`**：判定行数用 `rows or data or items` 三键兜底。
4. **后端不存在自调 `/api/v1/*` 的 HTTP 调用**：httpx 只出网 LLM 网关；模块间 Python 直接 import 绕过 HTTP 层 → 给管线端点加 `Depends` 不会断内部链路（担心可永久排除）。
5. **Git 红线**：每个 session 收尾必须 `ls-remote` 核对 LOCAL==REMOTE，不能信后台任务"completed"。
6. **Edit 工具偶发未落盘**：本仓已第 4 次，写完必须 Grep/Read 复核，或改用 Python 确定性替换。
7. **DuckDB 被后端独占**：查业务库前先停后端（`.backend.pid` + taskkill）。

---

## 11. 磁盘上的详细交付文档索引

| 文档 | 路径 | 内容 |
|---|---|---|
| 本轮一页纸 | `night4/DAY_SUMMARY_2.md` | ISS-025 修复六步交付 |
| 夜跑交接 | `night4/NIGHT_SUMMARY.md` | 事故恢复 + 两 P0 + 鉴权审计交接 |
| 鉴权审计 | `docs/issues/AUTH_AUDIT.md` | 106 写端点 + 28 列表端点扫描 + 实探 25 个 + **134 完整分类表（附录 B）** |
| ISS 债清单 | `docs/issues/ISSUES.md` | 21 条在债 + 8 条已闭环 + 修复方案 |
| 断点文件 | `PROJECT_STATUS.md`（项目根） | 总清单 + 已完成 + 关键事实 + 已知未查清 |
| 待拍板 | `OPEN_QUESTIONS.md`（项目根） | 1.3 深度重构 / 1.8 回退语义 / 1.9 导出 / 1.10 行级 / 5.1 清残留 |
| 验收报告（历史） | `defect_fix_evidence/` | 第二阶段 13 项 / AI 协作专项 / 根因修复全量验收 等 |
| 组件化设计 | `docs/组件化改造设计文档_2026-09-18.md` | Skill 注册表 + 规划器 + 反思闭环 |

---

> 编制说明：本文件整合自 2026-09-08 ～ 2026-09-23 共 16 个会话的工作记忆、NIGHT_SUMMARY、DAY_SUMMARY_2、AUTH_AUDIT、ISSUES 等。最深层数据（如 134 行逐条端点表、历史验收证据 JSON）以磁盘文档为准，本文提供摘要与索引，避免重复且保证可溯。

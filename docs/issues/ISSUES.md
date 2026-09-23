# ISS 债清单（Issue Debt Backlog）

> 阶段：大扫除 · 阶段 6（ISS 债清单）
> 分支：`p0-security-fixes`
> 生成时间：2026-09-22
> 字段（11）：ID / 标题 / 严重度 / 类别 / 位置 / 根因 / 影响 / 修复方案 / 工作量 / 负责人 / 状态
> 关联文档：`docs/PROJECT_HEALTH_CHECK.md`（阶段0）、`RULES.md`、`docs/CONVENTIONS.md`、`CHANGELOG.md`

---

## 0. 阅读须知（给明早接手模型）

1. **本表是「债」，不是「待办全量」**。已在历史提交中闭环的项，仅在本表末「附：已闭环项」留痕，请勿重复修复。
2. **严重度口径**：`P0`=数据/安全正确性或主链路阻断；`P1`=安全边界或高频功能缺陷；`P2`=稳定性/健壮性；`P3`=整洁度/文档。
3. **状态取值**：`已闭环` / `已缓解` / `待处理` / `挂账`（暂缓，等前置） / `待核查`（需先实测确认是否属实）。
4. **高风险红线**：凡涉及「API 契约 / 数据模型 / 主库 schema」的修复，必须先走 `RULES.md` 的数据库铁律——**停服 → 备份 `aibi.db`+`.wal` → 校验备份大小 → 列出全部调用/引用点 → schema 改动带回滚脚本**，且一类一 commit、失败即 `git revert`。禁止无备份改数据模型，禁止无回滚脚本改 schema。
5. **本表列的位置**为「文件/目录级」定位；具体行号以接手时实测为准（多数组已随大扫除收敛，行号可能漂移）。

---

## 1. 严重度与状态总览

| 严重度 | 数量 | 说明 |
|--------|------|------|
| P0 | 3 | 导出假成功+跳页、横向越权归属过滤(ISS-003)、**无鉴权端点可操作任意看板(ISS-025)** |
| P1 | 8 | 鉴权端点对齐、owner 来源、上传净化、前端守卫认知债、限流兜底、字段截断、双库误配监控、依赖漏洞 |
| P2 | 6 | 出站超时/重试、LLM 网关稳定性、schema 迁移覆盖、历史注入、性能、**AI 对话实体抽取(ISS-022)** |
| P3 | 4 | 调试脚本归位、文档去重、局部命名 spot-check、诊断残留出库 |

> 合计 **21** 条在债；历史已闭环 **8** 条见附表（本夜新增闭环 ISS-023/024）。
> 鉴权面全量审计见同目录 `AUTH_AUDIT.md`（提交 `e62282b`）。

---

## 2. ISS 债明细（11 字段）

| ID | 标题 | 严重度 | 类别 | 位置 | 根因 | 影响 | 修复方案 | 工作量 | 负责人 | 状态 |
|----|------|--------|------|------|------|------|----------|--------|--------|------|
| ISS-001 | 前端 `authHeaders()` 旁路未统一合入 `request()` | P1 | 安全/前端 | `frontend/src/utils/request.ts`（定义）+ `QualityCheckPanel.tsx`/`ChatPanel.tsx`/`UploadPage.tsx`/`LoadingPage.tsx`（4 调用点） | 历史多处直接 `authHeaders()` 取 token 拼请求，绕过 `request()` 统一的 auth header 注入、超时、重试护栏（N3：11 处旁路） | 一旦 `request()` 护栏升级（超时/重试/错误归一），旁路点不受益；且易漏鉴权 | 将 11 处旁路调用统一改走 `request()`；`authHeaders()` 仅作 `request()` 内部取 token 的子函数，不再对外暴露 | M | 前端 | 挂账(N3) |
| ISS-002 | 9 处非强制鉴权端点待对齐 | P1 | 安全/后端 | `backend/app/api/*.py` 部分 GET 端点 | 早期为联调便利，将部分只读端点标为非强制鉴权（N2：9 处） | 未登录可读敏感元数据/列表 | 逐端点补 `require_admin`/`require_roles(["admin"])` 或最小角色；前端同步走鉴权 header。属高风险档，走停服→备份→列引用流程 | M | 后端 | 挂账(N2) |
| ISS-003 | 横向越权：dataset/dashboard 缺 owner 归属过滤 | P0 | 安全/后端 | `backend/app/api/datasets.py`、`dashboards.py` 列表/明细查询 | 列表与明细未按服务端身份 `owner` 过滤，靠前端 `localStorage` 门禁 | 任一登录用户可枚举/访问他人数据集与看板 | 在 SQLAlchemy 查询层强制 `where owner==current_user`；明细 404 而非 403。高风险档，需回归测试 | L | 后端 | 待处理(G2) |
| ISS-004 | 看板 owner 取自服务端身份未落实 | P1 | 安全/后端 | `backend/app/api/dashboards.py` 创建逻辑 | 创建时 owner 可能依赖前端传入 uid 或 `localStorage`，非 `get_current_user()` | owner 可被篡改，配合 ISS-003 放大越权面 | 创建/写入一律以 `get_current_user().id` 注入 owner，丢弃前端传入值 | S | 后端 | 待处理(D2-1) |
| ISS-005 | 上传校验与输入净化不足 | P1 | 安全/后端 | `backend/app/api/upload.py` | 文件类型/大小、文件名路径穿越、字段 SQL 注入类净化未系统化（D0-1/P3-2/P3-3/P4-2） | 恶意文件/超大数据/注入绕过 | 统一白名单（扩展名+ MIME）、大小上限、文件名 `secure_filename`、参数化查询。高风险档走备份流程 | M | 后端 | 待处理 |
| ISS-006 | 注册接口开放策略 + 登录锁定补偿 + /health 暴露面 | P2 | 安全/后端 | `backend/app/api/auth.py`、`app/api/health.py` | 注册是否对公网开放未定、登录失败无锁定、健康端点可能泄露内部版本 | 暴力注册/爆破/信息泄露 | 注册按需 `require_admin` 或关闭；登录失败计数锁定；`/health` 仅返 `ok` 不含敏感。低风险档，可直接改 | S | 后端 | 待处理(D0-1/D0-2/P4-3) |
| ISS-007 | 后端出站 HTTP 缺统一超时/重试 | P2 | 稳定/后端 | `backend/app/core/llm_gateway.py` 等出站调用 | `httpx`/`requests` 未设 `timeout`，无重试退避（N4） | LLM 不可达时线程挂起、链路雪崩 | 封装统一出站客户端：默认超时 + 指数退避重试 + 熔断；`brain/run` 已有不可达短路降级，补齐其余调用点 | M | 后端 | 挂账(N4) |
| ISS-008 | 报告页 XSS 净化 | P1 | 安全/前后端 | `backend/app/api/...`（报告生成）、前端渲染 | 报告正文含用户数据，未 DOMPurify 净化 | 存储型 XSS | 后端落库前净化 + 前端渲染 `DOMPurify.sanitize`。**历史已闭环（G4，提交 232），此处仅留痕核验** | — | — | 已闭环(历史) |
| ISS-009 | 两处假 `require_admin` 未走真实现 | P1 | 安全/后端 | `backend/app/core/security.py` 旧引用 | 早期复制了空壳 `require_admin`，未校验 JWT | 假鉴权等于无鉴权 | 删除假实现，统一引用 `security.py` 真 `require_admin`/`require_roles`。**历史已闭环（G1，提交 226）** | — | — | 已闭环(历史) |
| ISS-010 | 前端守卫仅为 UX 门禁（认知债） | P1 | 安全/前端 | `frontend/src/App.tsx` `ProtectedRoute`（约 :31-37） | 仅读 `localStorage['user'].roles` 做路由门禁，非安全边界 | 客户端可伪造 localStorage 绕过 UI，但**服务端已强制鉴权**，故仅为认知/文档债 | 在 `ProtectedRoute` 加注释明确「非安全边界，真实校验在服务端」；勿误改为安全边界 | S | 前端 | 待处理(设计中) |
| ISS-011 | 双库同名（`aibi.db` SQLite 元数据 vs DuckDB 业务）误配风险 | P1 | 数据/配置 | `.env` `DUCKDB_PATH` | 旧相对路径解析会在目标缺失时静默建空库，且 `.env.example` 曾误指 `qa_aibi.db` | 业务库被静默清空/指向错库 | `718019d` 已绝对路径化 + 启动 fail-fast；`.env.example` 已指正。**债：长期监控 env 误配 + 启动校验告警** | S | 后端 | 已缓解(718019d) |
| ISS-012 | 分身/QA 克隆库（20 个）残留 | P3 | 数据/仓库 | `backend/data/`（已归档 `_archive/`） | 历次验证/GLM/UI 跑批产生副本 | 占空间、易与真相库混淆 | 阶段 1.3 已停服+备份真相库+归档 20 个至 `data/_archive/`（可恢复）。**债：定期清 `_archive` 旧副本** | S | 后端 | 已处理(阶段1.3) |
| ISS-013 | 调试/诊断脚本三处并存，缺统一入口 | P3 | 整洁/仓库 | `backend/scripts/_*`、`根/scripts/`、`docs/defect_fix_evidence/` | 联调期散落一次性脚本，无约定 | 仓库噪声、误入库风险 | 一次性脚本统一收口 `backend/scripts/_archive/`（忽略）；阶段 3 已补 `.gitignore` 防护。剩余根级 `defect_fix_evidence/` 因锁文件移出失败，仍本地残留（gitignored，无害） | S | 后端 | 待处理(部分) |
| ISS-014 | LLM 网关 provider 稳定性（429/400/切换） | P2 | 稳定/后端 | `backend/app/core/llm_gateway.py` | 商汤网关 kimi 仅允许 `temperature=1`；deepseek/glm 间歇 429；多 key 容错未全覆盖 | 生成链路偶发失败/挂起 | 已落地 kimi-k3 主用 + 多 key 容错（任务 235）；探针失败弹选择框（M1）。**债：持续观测 429 比例，必要时扩 key** | M | 后端 | 已缓解 |
| ISS-015 | AI 对话 Top3：历史注入 / 主链路 LLM 决策 / 澄清循环 | P2 | AI/前后端 | `backend/app/api/chat.py`、`brain/` | 多轮对话未稳定注入上下文、主链路部分决策未走 LLM、澄清易陷循环 | AI 对话质量不稳、重复生成 | 阶段 9 专项：注入历史上下文、主链路决策改走 LLM 结构化、澄清设最大轮次退避。时间够才做 | L | 前后端 | 待处理(阶段9) |
| ISS-016 | 局部变量命名 spot-check | P3 | 整洁/代码 | `backend/**/*.py`、`frontend/src/**` | 阶段 0 仅扫描顶层 `def`/`class`，局部变量 camelCase 未穷举 | 可读性 | 阶段 4 命名子类做一轮 spot-check，发现即改。**预期工作量≈0** | S | 前后端 | 待核查(阶段4) |
| ISS-017 | 文档散落与多版本重复 | P3 | 文档 | 根 `PROJECT_STATUS.md` 等多版本、`docs/` 多处 | 状态文档随会话增量派生多份 | 读者混淆 | 阶段 3 已迁 7 个根级 .md 至 `docs/`；保留 `README.md` 在根。债：定期合并 `PROJECT_STATUS` 历史版本 | S | 文档 | 待处理(部分) |
| ISS-018 | schema 迁移入口覆盖核查 | P2 | 数据/schema | `backend/alembic/` | 模型变更是否全部有 alembic 迁移未系统核查 | 换环境 schema 漂移 | 阶段 4 schema 子类：比对 `models/` 与 `alembic` 版本，缺口补迁移；任何 schema 改动走回滚脚本红线 | M | 后端 | 待核查(阶段4) |
| ISS-019 | 生成看板限流静默兜底 + 多字段截断 | P0→P1 | 稳定/前后端 | `backend/app/api/brain_run_sse.py`、`action_executor` | 限流无提示直接丢弃；多字段被截断且 LLM 字段匹配失败 | 用户无感知失败 / 图表缺字段 | 限流已加静默兜底（任务 234）+ 多 key 容错（235）；字段截断+匹配（236）待处理 | M | 前后端 | 部分已处理 |
| ISS-020 | 导出 PDF/Excel/PNG 假成功 + 跳页 | P0 | 功能/前后端 | `backend/app/api/exports.py`、前端导出组件 | 导出在无真实产物时返回「成功」并跳页 | 用户以为已导出实则无文件 | 导出前校验产物存在；无产物时诚实占位/报错不跳页（item4）。高风险档，先实测复现再改 | M | 前后端 | 待处理 |
| ISS-021 | GitHub Dependabot：default 分支 1 个 high 级依赖漏洞 | P1 | 安全/依赖 | `main` 分支依赖树（Dependabot alert #1，仓库 Security/Dependabot） | 某依赖版本存在已知 CVE（`push` 时 GitHub 回显「1 vulnerability (1 high)」） | 供应链漏洞，可能被利用；`p0-security-fixes` 同源依赖可能同样受影响 | 查 Dependabot alert #1 详情 → `pip audit` / `npm audit` 定位 → 升级到修复版本 → 验证后端/前端构建。注意：在本人工作分支也需同步升级 | M | 后端/前端 | 待核查(Dependabot) |
| ISS-022 | AI 对话删图：图表名实体抽取失败，误拒删除 | P2 | AI/后端 | `backend/app/api/chat.py`（意图分类后实体抽取）、`action_planner/action_executor` | 意图已正确识别为 `delete_chart`(conf 75)，但实体抽取把「名为数据明细」「删除数据明细」整串当图名，匹配不到裸图名 → 安全拒绝删除 | 用户说「删掉数据明细图」无效果 | 实体抽取改为：先用现有看板图表标题做**受控词典匹配**（最长优先），再回退 LLM；命中不到时给出候选列表让用户选，而非直接拒 | M | 后端 | 待处理(阶段9) |
| ISS-023 | ~~`/dashboards/my` 未按 created_by 过滤（横向越权）~~ | P0 | 安全/后端 | `backend/app/api/dashboards.py` `list_my_dashboards` | `_OWNERS` 固定含 legacy `anonymous`/`current`，**任何登录用户**都能看到 pre-auth 演示看板 | 任意用户可枚举他人看板，并借 ISS-024 删除 | legacy 仅超管可见；普通用户严格 `created_by/updated_by == 自身uid` | S | 后端 | **已闭环(2541347)** |
| ISS-024 | ~~DELETE `/dashboards/{id}` legacy 特判导致删除越权~~ | P0 | 安全/后端 | `backend/app/api/dashboards.py` `delete_dashboard` | `is_legacy = created_by in (anonymous,current)` 无条件放行删除 | **已造成真实事故**：误删真实演示看板 `risk_demo_v2_02` 两次，后从 09-18 备份外科恢复 | 去掉 legacy 特判；仅创建者本人 or 超管可删，其余 403 | S | 后端 | **已闭环(2541347)** |
| ISS-025 | 一批端点**完全无鉴权**，可操作任意看板 | P0 | 安全/后端 | `versions.py`、`share.py`、`chat.py`、`exports.py`、`tokens.py` 等 | OpenAPI 全量扫描 193 操作中 134 无 security 声明：A类有意公开10/测试38/C类1/**真漏85(P0 35/P1 35/P2 15)**；3 个 P0 为 `versions/rollback/{id}`、`shares/create`、`chat/message` | 与 ISS-023/024 同一攻击面：无 token 可回滚任意看板/建外发分享/对任意看板 AI 改图 | **本轮已修 3 个 P0 + tokens/status 可选鉴权(34a4cdc)** + 前端 8 处裸 fetch 同步带 token(2d1bfd9) + 防复发三件套(74bb398)；余 80 个真漏进 `scripts/auth_whitelist.json` 的 `known_leak_tracked` 跟踪，CI 门禁(`scripts/auth_scan.py`)已验证 0 新增越权。完整分类见 `AUTH_AUDIT.md` 附录 B | L | 后端 | **部分闭环（3 P0 + tokens/status 已修，余 80 跟踪中）** |

---

## 3. 优先级建议（明早接手顺序）

1. **先排 P0**：ISS-003（横向越权）、ISS-020（导出假成功）。二者均触及「API 契约/功能正确性」，按红线走停服→备份→列引用→回滚。
2. **再收 P1 安全面**：ISS-001/002/004/005/010，按「前端护栏 → 后端端点 → owner 来源 → 上传净化」推进，每类一 commit+push。
3. **P2 稳定/数据**：ISS-007/011/014/018/019，观测为主、改动为辅。
4. **P3 整洁**：ISS-012/013/016/017，随阶段 4 一并收口，不单独占夜。

---

## 附：已闭环项（历史提交，勿重复）

| ID | 项 | 闭环提交/任务 |
|----|----|---------------|
| — | 阶段 0 假告警（`main.py:97` 误查仓库根/.env） | `693d90c` |
| — | 双库同名冲突（DUCKDB 绝对路径 + fail-fast） | `718019d` |
| — | 两处假 require_admin 统一到 security.py 真实现 | G1（任务 226） |
| — | 13 个未认证端点补鉴权（G3） | 提交 231 |
| — | 报告页 XSS 净化（G4） | 提交 232 |
| — | 分身库归档 20 个（阶段 1.3） | 阶段 1.3 |
| ISS-023 | `/dashboards/my` 归属过滤（legacy 仅超管可见） | `2541347` |
| ISS-024 | DELETE 看板 legacy 越权（仅创建者/超管可删） | `2541347` |

---

## 4. 风险红线重申（来自 RULES.md）

> 改 API 契约必须同步改**全部**调用点；改数据模型必须先备份；改 schema 必须带**回滚脚本**。
> 一类一 commit、一类一 `git push`、失败立即 `git revert`。`push` 前确认阶段 5 全测试通过（tsc --noEmit / py_compile / 后端 /health 200 / 前端 5173 200 / 核心链路 / AI 对话 / UI 真截图）。

# 项目进度总表（PROJECT_STATUS.md）

> 每次 AI 开工前必须先读这份文件。
> **本版为 2026-09-22 最新版（v2），覆盖此前旧版（旧版进度已过期）。**
> 格式规则：已完成 `- [✓]`，未完成 `- [ ]`。
> 维护规则：每完成一项 → 划掉/打勾 → 落盘证据到 `defect_fix_evidence/final_fixes/` 或 `night3/` → 更新本文件。

---

## 一、当前状态

- **项目**：AI-Report（大赛 PDF 项目，路演延期）
- **仓库**：`C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report`
- **分支**：`p0-security-fixes`
- **目标定位**：真产品 + 知识资产沉淀
- **核心差异化**：AI 自主推理 + 完整记忆 + 可积累模板
- **当前阶段**：第 3 层 UI 体验进行中（3.1 / 3.2方案C / 3.3 / 3.5 / 3.6 / 3.7 已落地；剩 3.2a-e UI 行为 + 3.4）；第 8 层 O/P/Q 三个核心方案已出（待落地）
- **上一轮完成（夜间长跑，已提交）**：
  - 1.7 暗色模式（代码完成，待本机视觉确认）
  - 1.8 版本回退提示
  - 1.9 PDF 真导出
  - 1.10 附录 B 影响行数
  - 2.3 AI 能力补齐（s2 默认 LLM + 标记对齐，commit `ed72f47`）
  - 2.4 徽标落地（标题绿/灰标 + 目标区 s2 小标，commit `3676b66`）
  - 3.1 上传页收缩（commit `1bdc645` + 深度补充 `fee2792`）
  - 3.3 KPI 末行留白归零 + 类型归一化（`0df1abb` + `2f9e8de`）
  - 3.5 AI 归因实查替代"刷新试试"（`76d3c8c` + `154255f`）
  - 3.6 管理后台 LLM 网关实时四态（`f4cacf5` + `3170f3b`）
  - 3.7 版本假动作扫描清零（`96050cd` + `6d24556`）
  - 第 8 层 O/P/Q 三份核心方案（`night3/plans/O_P_ai_participation_monitoring.md` 等）
- **这一轮做什么（真实待办）**：
  - ~~3.2a-e 加载页 UI 行为 / 3.4 看板空态~~ → 已落地（前几轮）
  - ~~N1 对话执行器泛指展开+聚合口径~~ → 已修（commit `ff37323`，真实跑 ALL_PASS）
  - ~~N2 去 9 处 AI 字样~~ → 已改（commit `ff37323`，tsc 0）
  - ~~N3 KPI 右侧留白~~ → 已定论：旧 dist 重构建即可，无需改代码
  - ~~2.6 P0 模板表 + 匹配函数~~ → 已落地（commit `44c8649`，真跑 verify_26_template.py ALL_PASS）
  - **2.6 收尾三件（本轮）**：种子模板 5 个 / 保存为模板入口（P2）/ AI 自动沉淀（P1）+ 管理后台「分析模板」Tab → 全部完成（真跑 `verify_26_e2e.py` ALL_PASS）
  - 第 8 层 A-N 落地（O/P/Q 已出方案）
  - 第 4 层 路演准备

---

## 二、待办清单

### 第 0 层：环境治理
- [✓] 0.1 路由修复（DUCKDB_PATH=aibi.db）
- [✓] 0.2 多实例防护（run_backend.py B5 守卫）
- [ ] 0.3 环境隔离（⚠️ 部分完成：告警做了，物理隔离留第 6 层）
- [ ] 0.4 启动方式统一
- [ ] 0.5 配置唯一源

### 第 0.5 层：鉴权收口
- [ ] 0.5.1 3 套 require_admin 统一
- [ ] 0.5.2 所有调用点迁移
- [ ] 0.5.3 lint 护栏
- [ ] 0.5.4 归属过滤统一
- [ ] 0.5.5 回归测试

### 第 0.6 层：文件清理
- [ ] 0.6.1 项目根目录整理
- [ ] 0.6.2 补丁文档归位
- [ ] 0.6.3 AI 工作目录分离
- [ ] 0.6.4 .gitignore 更新
- [ ] 0.6.5 测试残留脚本清理

### 第 1 层：路演 P0
- [✓] 1.1 附录 A/B 表格去 scroll.x（✅ 代码完成，待本机视觉确认）
- [✓] 1.2 多 key 重试 fail-fast
- [✓] 1.3 Event loop 防御性修复
- [✓] 1.4 对话多字段截断
- [✓] 1.5 对话垃圾图
- [✓] 1.6 AI 失败弹窗（生成路径，端到端实测）
- [✓] 1.7 暗色模式（C 范围：图表 + KPI + 背景，待本机视觉确认）
- [✓] 1.8 版本回退提示
- [✓] 1.9 PDF 真导出（Excel/PNG 留路演后）
- [✓] 1.10 附录 B 影响行数（行级明细留路演后）

### 第 2 层：AI 含量
- [✓] 2.1 AI 能力鉴定（12 板块：11 真 + 1 半空壳）
- [✓] 2.2 Prompt 中心可编辑性
- [✓] 2.3 AI 能力补齐（s2 默认 LLM + 标记对齐，commit `ed72f47`）
- [✓] 2.4 路演 AI 展示徽标（commit `3676b66`，待本机截图）
- [✓] 2.5 AI 自主推理语义（方案 `defect_fix_evidence/final_fixes/plan_25_26_semantic_and_template.md`）
  - [x] 2.5 P0 落地（L2 字段画像升级：distinct/空值率/高基数注入，commit 见下；证据 `ev_25_p0.md`）
  - [ ] 2.5 P1-P4（样本注入/field_semantics 持久化/业务词典/纠正写回，待做）
- [✓] 2.6 分析模板库（方案已出，同文件）
  - [✓] 2.6 P0 落地（模板表 + 匹配函数，commit `44c8649`）
    - 新增 `AnalysisTemplate` 模型（字段画像特征匹配，不绑列名）+ alembic 迁移 `002`；`match_templates(profile)` 仅 `approved=True` 参与、特征交集打分降序返回
    - 集成 `s2_goal_generator`：`_apply_templates` 在 L227 后并入命中模板的 `base_goals`（`generated_by='template'`），LLM/规则两路径均生效，不破坏规则兜底；S2 前算 `field_profiles` 传入（便宜规则构建 profile，不触发含 AI 的 `build_semantics`）
    - 真实跑 `backend/verify_26_template.py` ALL_PASS：T1 命中 / T2 不命中 / T3 未批准门禁排除 / T4 并入集成
  - [✓] **2.6 收尾三件（2026-09-22，本轮，真实落库 + 真跑）**
    - [✓] **件1 种子模板 5 个**：`担保风控标准六图` / `客户画像分析` / `贷款借据明细分析` / `销售经营分析` / `地区分布分析`；`approved=True, source='system'`；通过 alembic `002` 幂等 INSERT + `scripts/seed_templates.py` 真实落入 `data/aibi.db`；`match_features` 仅用 `must_have_types+min_fields+theme_hint`（规避生产环境恒空维度）；`_score_template` 加 `theme_hint` 硬约束防跨主题误命中
    - [✓] **件2（P2）管理后台「保存为模板」入口**：看板操作栏 `DashboardOps.tsx` 新增按钮 + 弹窗（模板名/描述/是否批准默认 False），`POST /admin/templates`；后端 `admin_create_template` 从看板 config 提炼 `base_goals`（图表→goal）、从主数据集字段画像提炼 `match_features`，落库 `approved=False, source='user'`（防污染，待确认）
    - [✓] **件3（P1）AI 自动沉淀候选**：`brain_run_sse.py` S2 完成后调 `propose_template_candidate`（`s2_goal_generator.py`）；`goals<3` 跳过；按 `match_features` JSON 签名去重；落库 `approved=False, source='ai'`；管理后台新增「分析模板」Tab（`AdminPage.tsx`：GET 列表 / PATCH 批准 / DELETE 删除，默认看待确认候选）
    - 真跑验证 `backend/scripts/verify_26_e2e.py` ALL_PASS：①#274 保存落库 `approved=False, source='user'` ②#277 AI 沉淀首次落库、二次同签名去重不重复 ③#278 新数据集→命中种子模板→目标并入含模板目标（总担保金额/抵押率分布/大额担保风险预警）
  - [✓] **遗留 bug 修复：`AnalysisTemplate` 未在 `s2_goal_generator.py` 顶层 import**（`propose_template_candidate` 内引用 → `NameError` 被静默吞掉，AI 沉淀从未真正落库）。已在模块顶层补 `from app.models.analysis_template import AnalysisTemplate`；真跑 3 次 `brain/run` 验证：日志 `[S2] 模板沉淀候选已写入（source=ai, approved=False）` ×2（数据概览 / 担保风控两个不同 match_features 签名），`name 'AnalysisTemplate' is not defined` 出现 **0 次**，`analysis_template` 表 `source='ai'` 真实新增 2 行；第 4 次同主题跑完模板数不变（同签名去重生效）

### 第 3.9 层：本轮三个 P0（2026-09-22 晚，真跑验证）
- [✓] **P0-1 `goals_count` 前向引用崩溃**（`brain_run_sse.py`）
  - 根因：第 771 行 `print(f"...（{goals_count} 个目标）")` 在 773 行 `goals_count = len(goals)` **之前**执行 → 每次 S2 必然 `UnboundLocalError`，被 except 吞掉后 S2 降级
  - 修复：print 内联改为 `len(goals)`；真跑 `brain/run` → 日志 `[Brain] S2 生成方式: rule（12 个目标）` / `S2完成: 12个目标` → S3 → S4+S5 → `dash_1fe8fd3e_0a9459` 落地，全程不崩
- [✓] **P0-2 历史看板"该图表无可绘制数据"** —— 结论：**DuckDB 双库路由错配，不是表丢了**
  - 证据链：①`GET /datasets/{id}/chart-data` 对 6 个看板返回 `404 {"code":"TABLE_NOT_FOUND"}`；②元数据 36 个 dataset 中有 10 个的 `duckdb_table` 在后端当前库里查无此表；③这些表**全都在 `backend/data/duckdb/qa_aibi.db`**（36 表）里，且行数与元数据 `row_count` 完全一致（1fe8fd3e=12 / 04d68399=20 / 3716856d=12 / 9d7fe32f=12 / e8c94106=12 / cb0a9738=12 / 7aa4410e=6 / 5bd315e3=10）
  - 根因：历史数据集建表时 `DUCKDB_PATH` 指向 `qa_aibi.db`，0.1 路由修复后统一到 `aibi.db`，老表留在旧库 → 读不到
  - 修复：`backend/scripts/migrate_duckdb_tables.py`（ATTACH 旧库 → `CREATE TABLE AS SELECT`），迁移 26 张表（含 `_cleaned/_agg/_norm` 变体）**OK=26 FAIL=0**
  - 复验：16 个有图看板中 13 个 `chart-data` 由 404 → **200**（含两个历史看板 `dash_1fe8fd3e_f81d8b` / `dash_04d68399_50adf8`）
  - ⚠️ 残留：`ds_4920434e_23e0_...`（演示测试数据集）在**所有** duckdb 分身库里都不存在 → 3 个看板（`dash_4920434e_fbed47/_16d735/_a7796e`）仍 404，只能重传或废弃；另 `dash_4bece390_3619ff` 的「收入负债比分布」用了 S3 占位列名 `category`（非真实字段），单独缺陷
    ④ **是否根治：数据层面已根治（表已并入主库）；配置层已于本轮根治（见 ⑤）**
    ⑤ **根治 4 条已落地（2026-09-22 晚，真跑验证）**：
      - **【1】`run_backend.py` 告警文案**：删除"请显式 export DUCKDB_PATH=qa_aibi.db"误导告警；改为仅在**显式指定非规范仓库**时告警，基准用 `config._DEFAULT_DUCKDB_PATH`（不能用 `settings.DUCKDB_PATH`——它会被同名 env 覆盖导致告警失效，本轮实现时踩到并修正）
      - **【2】`.env.example`**：`DUCKDB_PATH` 由 `qa_aibi.db` 改回 `aibi.db` 并附历史坑注释（该文件未被 git 跟踪，改动仅在本机磁盘生效，不入 diff）
      - **【3】`config.py` 绝对路径化**：新增 `_DEFAULT_DUCKDB_PATH = backend/data/duckdb/aibi.db`（基于 `_PROJECT_ROOT`），加 `field_validator` 把任意相对路径按 backend 根解析为绝对路径 → 摆脱 cwd 依赖（实证 `settings.DUCKDB_PATH` 为绝对路径、`is_abs=True`）
      - **【4】启动校验 fail-fast（关键）**：`run_backend.py` 新增 `_validate_duckdb()` —— 库文件不存在 → `[DUCKDB-FAIL]` ×3 + `sys.exit(1)`；存在但 `ds_*` 表数=0 → `[DUCKDB-WARN]` 不阻断；正常 → `[DUCKDB-OK] …（ds_* 表 488 张）`
      - 真跑验证：①正常启动 → 打绝对路径 + `[DUCKDB-OK] 488 张` + health 200 ②改名 `aibi.db` → `EXIT_CODE=1`、`[DUCKDB-FAIL]`、8000 未监听、**未静默创建空库** ③恢复 → 启动正常、`chart-data` 200 ④`DUCKDB_PATH=qa_aibi.db` → `[0.3-WARN]` 正确触发
- [✓] **P0-3 上传页三个 toast 反复弹**（方案 A+B+C 全做）
  - 真跑 API 验证（沙箱无可用浏览器，UI 截图需你本机确认）：`GET /admin/templates`=200（5 system + 2 ai 待确认）、`POST /admin/templates`=200（落库含 4 个 goal_skeleton）、`PATCH /admin/templates/{id}`=200（批准↔还原双向生效）、`DELETE`=200、`GET /quality/{ds}/issues`=200（5 条已存质检结果 = 恢复时读的数据源）
  - 附带修复：`PATCH /admin/templates/{id}` 原 500 —— `await db.commit()` 后 ORM 属性被 expire，异步上下文再 `to_dict()` 触发惰性加载失败；修为 commit 后先 `await db.refresh(tpl)`
  - 根因：`LoadingPage.handleCancel` 调了后端 `/cancel` 并清了 `brain_run_{dsId}`，但**没清 `upload_session`** → 每次进页面 `restoreSession` 都当"未完成任务"恢复并弹 toast；`QualityCheckPanel` 挂载 500ms 后又无条件自动跑一遍质检并弹持久 loading
  - A（`UploadPage.tsx`）：`restoreSession` 按语义分流——已建数据集（上传+质检已完成=稳定资产）**静默恢复不弹 toast**；只有真·未建数据集才提示"未完成的上传任务"
  - B（`QualityCheckPanel.tsx`）：新增 `autoCheck` prop；`autoCheck=false`（恢复的文件）走 `loadExisting()` 读后端已存质检结果（`GET /quality/{id}/issues`），不重跑、不弹 toast；`runCheck({silent:true})` 静默兜底；`message.loading(duration:0)` → `duration:8` 兜底；底部按钮「无必拦项，直接继续」→「**生成看板**」
  - C（语义）：新增 `upload_gen_canceled_map` 墓碑，取消生成时打标；上传+质检产物保留、会话不作废，`upload_session` 的"任务"语义收窄为"上传中/未建数据集"
  - `tsc --noEmit` EXIT=0

### 第 3 层：UI 体验
- [✓] 3.1 上传页布局（已落地：Dragger 收缩 + 队列收缩，`1bdc645`+`fee2792`，tsc 通过；源码 `UploadPage.tsx` 含 `shouldCollapse`/`queueCollapsed`）
- [✓] 3.2 加载页方案 C（方案已出 `night3/plans/B_32_loading_page_plan_c.md`；现状验证 `verify_32_current_state.py`）
- [✓] 3.2a 时间预估准确性（本轮改：ETA 改 EMA 平滑+卡住检测+阶段步序展示，`LoadingPage.tsx`；tsc EXIT=0）
- [✓] 3.2b 离开后恢复（核实已实装：localStorage RUN_KEY + 后端 dataset_id 反查，未改）
- [✓] 3.2c AI 增强 vs 规则生成的区分展示（本轮增强：后端 S2 后发 generation_mode + 前端加载中即显徽标；verify_32_generation_mode.py ALL PASS）
- [✓] 3.2d 任务完成后通知（核实已实装：message + 完成态 Tag，未改）
- [✓] 3.2e AI 跑动的约束（核实已覆盖：后端 180s 超时+token 熔断+ /cancel；前端取消/跳过/底部说明，未改）
- [✓] 3.3 KPI 卡片单卡留白（已修：末行留白归零 + 图表类型归一化，`0df1abb`+`2f9e8de`）
- [✓] 3.4 看板"无可绘制数据"整看板空态（`DashboardPage.tsx` 守卫：无图→Empty+出口 / 取数失败→Alert 根因；tsc EXIT=0；路由实测核实，证据 `ev_34_dashboard_empty.md`）
- [✓] 3.5 AI 只会说"刷新试试"（已修：字段画像实查 4 类判定，`76d3c8c`+`154255f`）
- [✓] 3.6 管理后台设置页占位项（已修：LLM 网关实时四态，其余标"即将上线"，`f4cacf5`+`3170f3b`）
- [✓] 3.7 版本"预览/对比"空壳（已修：假删除改禁用+标注，全仓假动作扫描清零，`96050cd`+`6d24556`）

### 第 3.8 层：对话执行器修正 + UI 文案 + KPI 复查（本轮 N1/N2/N3）
- [✓] **N1 对话执行器"乱做"修复**（2026-09-22，方案用户拍板：增强理解而非锁死 LLM，commit `ff37323`）
  - D1 泛指展开：规则路径 `_rule_extract_add_charts` 增"每一项/每个/各/所有/全部/各项 + 聚合词"→遍历所有数值字段逐产 KPI 卡；LLM prompt 同步加泛指/聚合/纠正三条指引
  - D2 聚合口径落地：意图含"平均/均值/汇总" → `config.aggregation='avg'`（`_build_chart` 透传 + `action_executor` 实装），前端 `deriveKpi` 据此算均值而非默认 SUM
  - D3' 纠正去重（替代原"锁死 LLM"）：同标题+同图型已存在则跳过，避免纠正类指令翻倍；**不限制 LLM 改图型/数量/顺序**
  - 附带修复：`action_planner._SPLIT_PATTERN` 的 `\b并\b` 中文词边界失效 → 无逗号"删A图并新增B图"无法分句（删除被吞）；改为去 `\b` 直接按中连词语义切分
  - 真实跑验证 `backend/verify_n1_realrun.py` ALL_PASS：①5张KPI(avg) ②纠正仍5张不翻倍 ③复合正确分句 ④AI主导指令3张混合图型不被锁
- [✓] **N2 去掉9处用户可见"AI"字样**（2026-09-22，按用户拍板表，commit `ff37323`）
  - LoadingPage:352/417/427、QualityCheckPanel:795、DashboardOps:326/333、DashboardPage:1281、App.tsx:57/59
  - 改动：AI正在→正在 / AI增强生成中→智能增强生成中 / AI生成→已生成 / 一键AI修复→一键修复 / AI参与生成→智能参与生成 / 目标·AI→目标·智能 / AI分析报告→分析报告 / AI已完成字段识别→系统已完成字段识别 / AI出图Loading→智能出图Loading(含desc)
  - `tsc EXIT=0`；UI 截图需用户本机 `npm run build` 后查看（沙箱无浏览器，见关键事实#7）
- [✓] **N3 KPI 右侧留白复查**（2026-09-22，仅验证不改代码）
  - 结论：源码 `kpiSpanFor` 对任意卡片数均铺满整行（1→24/2→12/3→8/5→[6,6,6,6,24]），`.kpi-card`/KPICard 无定宽 → **当前代码不可复现该现象**
  - 根因 = 部署的 `frontend/dist` 构建于 2026-09-19，**早于** 3.3 的 `kpiSpanFor` 修复（2026-09-22）→ 旧公式 1/4 宽 = 截图右侧留白。
  - **2026-09-22 已 `npm run build` 重新构建 dist（14:34，tsc+vite build 0 错误）**：旧 09-19 包被替换、含 3.3 修复。**结论：旧包已重构建，无需改代码。**

### 第 4 层：路演准备
- [ ] 4.1 演示脚本（5 分钟 + 10 分钟）
- [ ] 4.2 演示前健康检查清单
- [ ] 4.3 翻车保险方案
- [ ] 4.4 隐藏空壳按钮
- [ ] 4.5 演示数据准备（独立库 + 预置看板）
- [ ] 4.6 演示话术（逐字稿 + 停顿）
- [ ] 4.7 评委问答准备（5 个高概率问题 + 备答）
- [ ] 4.8 排练 3 次 + 计时

### 第 5 层：数据清理
- [ ] 5.1 清测试残留（46 用户 / 24 看板 / 30 数据集 / 7 分享）先给方案
- [ ] 5.2 管理后台数字自愈

### 第 6 层：项目规范
- [ ] 6.1 建 RULES.md（架构铁律）
- [ ] 6.2 docs/ 完整结构
- [ ] 6.3 Git 规范
- [ ] 6.4 命名规范

### 第 7 层：知识资产沉淀
- [ ] 7.1 目录结构（项目内 docs/retro/ + 个人知识库）
- [ ] 7.2 项目复盘（时间线 + 坑清单 + 决策记录）
- [ ] 7.3 方法论沉淀
- [ ] 7.4 学习材料（编程基础、架构、微服务）
- [ ] 7.5 ai-data-copilot 拆解
- [ ] 7.6 模型切换经验
- [ ] 7.7 每周节奏机制

### 第 8 层：AI 增强体系（★ 核心差异化）

#### A. AI 输入层
- [ ] A1 原始材料完整注入
- [ ] A2 结构化上下文
- [ ] A3 血缘 + 加工规则 + 清洗记录注入
- [ ] A4 字段语义库

#### B. AI 处理层
- [ ] B1 自主推理
- [ ] B2 证据链推理
- [ ] B3 澄清循环
- [ ] B4 有异议追溯源头

#### C. AI 输出层
- [ ] C1 推理结果落库（field_semantics）
- [ ] C2 分析模板沉淀
- [ ] C3 结果自检
- [ ] C4 用户纠正流程

#### D. AI 记忆层（★ 关键：模型可换）
- [ ] D1 推理记录
- [ ] D2 决策记录
- [ ] D3 动作记录
- [ ] D4 纠正记录
- [ ] D5 模型元信息
- [ ] D6 ai_action_log 表设计
- [ ] D7 模型切换时承接历史机制

#### E. AI 约束层
- [ ] E1 超时上限
- [ ] E2 token 预算
- [ ] E3 失败降级
- [ ] E4 用户可中断

#### F. 体验层
- [ ] F1 时间预估准确性
- [ ] F2 离开恢复
- [ ] F3 完成通知
- [ ] F4 AI 增强 vs 规则生成区分

#### G. 模型选型分层
- [ ] G1 强模型（意图/理解）
- [ ] G2 快模型（图表）
- [ ] G3 分层路由
- [ ] G4 模型切换承接历史
- [ ] G5 弱模型（Hy4）打杂
- [ ] G6 模型升级与部署（Kaggle / 魔搭）
- [ ] G6.6 调整调用策略（档位路由：先选档，再切 key）

#### H. 验证机制
- [ ] H1 评估基准
- [ ] H2 通过率追踪
- [ ] H3 模型对比

#### ★ 三个核心方案（用户重点指定，方案已出）
- [✓] O. AI 参与过程监控方案（AI 干了什么）→ `night3/plans/O_ai_participation_monitoring.md`
- [✓] P. AI 结果检查方案（干得对不对）→ `night3/plans/P_ai_result_check.md`
- [✓] Q. AI 上下文与材料注入方案（AI 读到什么）→ `night3/plans/Q_ai_context_injection.md`

---

## 三、关键事实（怕它忘）

1. **DuckDB 真实数据（图表读取的 `ds_*` 数据集表）在 `backend/data/duckdb/aibi.db`**（67MB / 458 表，实测每行有数据）—— `DUCKDB_PATH=./data/duckdb/aibi.db`(config.py:62) 指向它，路由正确
2. **元数据（users / dashboards / brain_traces / analysis_template）在 `backend/data/aibi.db`**（6.4MB，SQLite；由 `DATABASE_URL`/`SQLITE_DATABASE_URL` 指向）—— 注意与 `data/duckdb/aibi.db`（DuckDB 业务仓库）同名但不同文件、不同目录
2.5. ⚠️ **`data/qa_aibi.db` 与 `data/duckdb/qa_aibi.db` 均为历史遗留库**：前者是旧元数据库副本，后者曾装 36 张 ds_* 业务表（P0-2 双库错配源头，表已迁入 duckdb/aibi.db）。两者都**不再被后端连接**，仅留作备份，清理归第 5 层
3. ⚠️ 命名易混：断点文件旧版"数据在 qa_aibi.db"是**写反的**——`qa_aibi.db` 实为元数据库，`aibi.db`(duckdb/) 才是数据仓库。已实测纠正。
3. **路由修复命令**：`cd backend && DUCKDB_PATH="./data/duckdb/aibi.db" <py312> run_backend.py`（端口 8000，HOST 127.0.0.1）
4. **跑后端用系统 Python 3.12**：`C:/Users/Asus009/AppData/Local/Programs/Python/Python312/python.exe`（非 workbuddy venv）
5. **git-bash shim 缺** `ls/cat/head/tail/grep/dirname/cd` → 用 python -c / Read / Glob / Write / Bash(python -c)
6. **所有 API 挂在 `/api/v1` 前缀**（`/health`=404，正确是 `/api/v1/health`）
7. ~~沙箱无浏览器~~ → **已订正（2026-09-22 晚）：沙箱可真实截图**。方案 = Python312 的 `playwright` + 系统 Edge（`executable_path=C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`，`headless=True`）；前端守卫需同时注入 `localStorage['token']` 与 `localStorage['user']={roles:['admin']}`，否则 `/admin` 会跳 403。脚本 `backend/scripts/_ui_shots.py`，产物 `defect_fix_evidence/final_fixes/ui_shots_20260922/`（4 张真实截图）。注：agent-browser（node）在本机无 Chromium、驱动 Edge 会挂死，不要用
8. **夜间长跑纪律教训**：体感耗时严重失真，一律以 git 提交时间戳为真实耗时依据（已两次订正任务卡）

---

## 四、已完成的项（做完划掉移过来，方便追溯）

1. **1.1–1.10 / 2.1–2.4** —— 见上方各层 `[✓]`，证据在 `defect_fix_evidence/final_fixes/`
2. **3.1 上传页布局** —— `1bdc645`+`fee2792`；Dragger 收缩 + 队列收缩双逻辑，含展开/收起；测试 `test_31_queue_collapse.js` 9 用例 ALL PASS；tsc EXIT=0
3. **3.3 KPI 留白** —— `0df1abb`+`2f9e8de`；末行留白归零 + 图表类型归一化（大写/空格/中文别名）；测试 `test_33_chart_type_norm.js` ALL PASS
4. **3.5 AI 实查** —— `76d3c8c`+`154255f`；字段画像 4 类判定（missing/emptied/high_null/ok），不再甩"刷新试试"；测试 `test_35_attribution.py` 12 用例 ALL PASS
5. **3.6 设置页** —— `f4cacf5`+`3170f3b`；LLM 网关四态（检测中/可达/不可达/未知）+ 手动复检；测试 `test_36_health_state.js` ALL PASS
6. **3.7 假动作清零** —— `96050cd`+`6d24556`；全仓 36 文件 / 139 onClick 扫描器 v3，R1(谎报)=0 R2(空壳可点)=0 R3(诚实标注)=2；tsc EXIT=0
7. **3.2 方案 C + 3.2a-e 验证** —— `270446d`；方案 `night3/plans/B_32_loading_page_plan_c.md`；现状验证 `defect_fix_evidence/final_fixes/verify_32_current_state.py` 真跑（规则引擎 16 字段 P95≈68ms，最坏卡死 300s=5min）
8. **O/P/Q 三方案** —— `4ddfc05`；`night3/plans/O_P_ai_participation_monitoring.md` / `P_ai_result_check.md` / `Q_ai_context_injection.md`；P 方案附可运行复现脚本 `repro_P_field_norm_bug.py`
9. **H3/H4/H5** —— `b300078`；路线图/反方观点/工单拆解，均在 `night3/plans/`
10. **2.6 收尾三件 + 三个 P0** —— 已提交 commit `e642f4f`（2026-09-22，13 文件 +1581/-24）；种子模板 5 个真实落库 `data/aibi.db` + 管理后台「保存为模板」入口（前端 `DashboardOps` 按钮+弹窗 → `POST /admin/templates`）+ AI 自动沉淀候选（`propose_template_candidate`，`approved=False, source='ai'` 去重落库）+ 管理后台「分析模板」Tab（`AdminPage`）；真跑 `scripts/verify_26_e2e.py` ALL_PASS；前端 `tsc --noEmit` EXIT=0

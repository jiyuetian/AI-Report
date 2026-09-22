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
  - 3.2a-e 加载页 UI 行为（现状已验证，UI 未实现）
  - 3.4 看板"无可绘制数据"空态
  - 2.5 / 2.6 方案（AI 自主推理语义 / 分析模板库）
  - 第 8 层 A-N 落地（O/P/Q 已出方案）
  - 第 4 层 路演准备

---

## 二、待办清单

### 第 0 层：环境治理
- [✓] 0.1 路由修复（DUCKDB_PATH=qa_aibi.db）
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
- [✓] 2.5 AI 自主推理语义（方案已出 `defect_fix_evidence/final_fixes/plan_25_26_semantic_and_template.md`）
- [✓] 2.6 分析模板库（方案已出，同文件）

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
2. **元数据（users / dashboards=18 / brain_traces）在 `backend/data/qa_aibi.db`**（757KB）
3. ⚠️ 命名易混：断点文件旧版"数据在 qa_aibi.db"是**写反的**——`qa_aibi.db` 实为元数据库，`aibi.db`(duckdb/) 才是数据仓库。已实测纠正。
3. **路由修复命令**：`cd backend && DUCKDB_PATH="./data/duckdb/qa_aibi.db" <py312> run_backend.py`（端口 8000，HOST 127.0.0.1）
4. **跑后端用系统 Python 3.12**：`C:/Users/Asus009/AppData/Local/Programs/Python/Python312/python.exe`（非 workbuddy venv）
5. **git-bash shim 缺** `ls/cat/head/tail/grep/dirname/cd` → 用 python -c / Read / Glob / Write / Bash(python -c)
6. **所有 API 挂在 `/api/v1` 前缀**（`/health`=404，正确是 `/api/v1/health`）
7. **沙箱无浏览器**：UI 视觉验证需用户本机开 `http://127.0.0.1:8000/dashboard/...`；我以 tsc(EXIT=0) + 代码 diff + 真实 API 数据页作证据
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

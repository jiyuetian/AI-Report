<!-- 权威治理源文件：由 _coach_input/ 于 night8 Item3 步骤7 迁入 docs/project_record/。其他文档引用请以本文件为准。 -->

# CHANGELOG

> 本项目所有显著变更都记录在此文件。
> 格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
> 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
> 本版：v3，2026-10-03（补 night9–18 全量提交链）。**

---

## [1.2.0] - 2026-10-03（第四期 · night9～night18）

### 新增
- **第四期主线 Task A–K 全部落地**（详见 `11-项目总状态PROJECT_STATUS.md` §三）
  - Task A LLM 链调 7 层（`50308ea`，D-020）
  - Task B 图表模板库后端（`a33f655`）/ 前端（`76e81ea`）
  - 链路规则引擎 YAML + fail-fast + rule_id 回链（`47681b1`）
  - Task G 最高权限 CRUD（`a01deb1`）
  - Task H 派生指标 14 项 + `METRIC_REGISTRY`（`2932834`）
  - Task I 下游重算一致性 C-16（`5f6c6a5`）
  - Task J 使用统计 J-8（`UsageStats` 内存态脱敏，`45a7ad6`）
  - Task K 全链路联调（`integration/` 离线 smoke，`45a7ad6`）
- AI 行为白盒化埋点 `ai_action_log`（`d221f04`）+ 日志查询 API/页（`9be596c`）
- ISS-058 阈值调整 `ADJUST_THRESHOLD` 意图 + executor + undo 闭环（`f0cc1fb`）
- ISS-044 `json_mode` 防护（剥 Markdown 围栏 + 重试 + 切 provider，`a555b99`）

### 修复
- ISS-057 `run_backend.py` `_pid_alive` Windows ctypes 探活（`270f21c`）
- ISS-038 跨看板上下文串号（`de52552`）
- ISS-052 `add_chart` 语义路由 + 维度护栏（`ddadc8a`）
- ISS-055 输出护栏标题语义校验 + K-7 维度质量（`cbeb308`）
- ISS-056 对话动作骨架补全 remove/undo/布局上下文 + 字段匹配失败禁出图（`ebc3381`）
- ISS-039/040 规则缺口（edit_title/字段替换/year 筛选/纠正句式，`3a8ad7b`）
- 六层 failover 模型透传 bug（`request.model` 锁死 `kimi-k3`，`9c9e1b7`）
- ISS-048 对话新增图柱值标签/长数字串格式化漏点（`dd7af5c`）
- ISS-045 LLM 调用失败指数退避重试 8/16/24s（`fed1476`）
- ISS-053 依赖安全钉固（python-multipart/pandas/jinja2/email-validator/httpx，`ec6dd9f`）
- ISS-050/051 数据明细预览 + 清洗质检行级明细表（`29113c4` / `ade8246`）
- ISS-046/047/048 统一比率格式化 + 柱值标签（`589e27d`）
- ISS-049 散点轴一致性护栏（`f395a00`）
- ISS-033「再来一个」闭环 + 指标名抽取盲区（`2fd76dd`）
- night17/18 遗留：`analytics` defaultdict 导入 / `import time` / `test_runner` 契约（`e338981` / `849ccba` / `af4fd5b`）

### 变更
- 测试体系扩至模块 A–N；night18 TEST-2 全量回归 98 检查点全 PASS
- 对话动作体系补 `adjust_threshold` / `remove` / `undo` 等骨架
- 开发纪律固化：一类一 commit、每 commit diff 全文贴报告、`AI_CHANGES.md` 逐条登记

---

## [1.1.0] - 2026-09-28

### 新增
- LLM 六层 failover 链（kimi-k3 → glm-5.3-flash → deepseek-v4-flash → glm-4.5-air → agnes → sensenova-6.8-flash-lite）
- NAMING.md 命名规范（`8393fe7`）
- 8 类测试数据 14 文件（`tests/_fixtures/ai_test/`）
- 产品定位拍板：AI 深度协同 + 可视化（AI 最高权限改 L1-L4，护栏四件套）

### 修复
- 弹窗 P0 三件（探针走真实网关 / S3 不静默吞 / 前端旁路封堵，`d12c419`）
- failover 识别 HTTP 200 错误体（`c18537d`）
- 诚实兜底 D 方案 + 跨会话冒领校验（`05b7cd7`）
- `_GENERIC_CONCEPT_WORDS` NameError 崩溃（ISS-032，`4e6a667`）
- 2 处裸 fetch 统一 request.ts（`8393fe7`）

### 变更
- 开发节奏：agent 连续开发 → 自测达准出线 → 用户统一验收（11-02 起）
- 测试体系扩至 123 条 10 模块（v1.3），准出线 v2
- 教练文档改"当前最新"制；过程文件剥离出代码目录（night8 执行中）

---

## [1.0.0] - 2026-10-10（封板目标）

### 新增
- AI 对话上下文注入（ISS-015 P0-1，`671e842`）
- AI 对话主链路交 LLM（ISS-015 P0-2，`ba0a235`）
- AI 对话澄清循环承接（ISS-015 P0-3，`9300d4f`）
- 分析模板库（2.6 P0，`44c8649` + 收尾三件）
- 三层 failover（sensenova + 智谱 + b.ai）

### 修复
- is_avg 未定义（ISS-026，`4e90ee5`）
- failover 吞错（ISS-A，`4e90ee5`）
- 对话实体抽取（ISS-022，`ae51380`）
- 两个 P0 越权（ISS-019，`2541347`）
- 3 个 P0 无鉴权端点（ISS-025-a，`34a4cdc`）
- 8 处裸 fetch（ISS-025-b，`2d1bfd9`）
- 弹窗 P0（ISS-034，待落）

### 变更
- 项目定位改为私有 → git / 测试 / 依赖漏洞降级
- AI 权限定位：高 —— AI 主导看板调整，规则兜底
- AI 能力新定位：AI 参与每一层（L1-L5）检查确认

### 已知未修（路演后）
- ISS-025 剩余 ~80 无鉴权端点
- ISS-031~035（版本回退 / 附录 B 行级明细 / 模板库浏览页 / 2.5 P1-P4 / 清理收尾）
- ISS-027（row_count，待拍板边界）

---

## [0.9.x] - 2026-09-22~24（大扫除 + 路线 A）

### 新增
- AI 对话能力审计（`AI_DIALOG_AUDIT.md`）
- 规范三件套（`RULES.md` / `CONVENTIONS.md` / `CHANGELOG.md`）
- 交接包（`docs/handover/` 7 类）
- ISS 单（`docs/issues/ISSUES.md`）
- 防复发三件套（OpenAPI CI / 裸 fetch 扫 / whitelist）

### 修复
- DuckDB 主库从 536KB 恢复（140MB 备份 → 488 表）
- 4 条配置根治（绝对路径 / fail-fast / 告警文案 / .env.example）
- `admin.py` 缺 BaseModel import（后端起不来）
- `brain_run_sse.py` S2 goals_count 前向引用
- Bug2 跨会话冒领硬校验

### 变更
- 项目分支确立：`p0-security-fixes`
- A2/A3/A4（安全档 / 清理 / LLM_PROVIDERS.md）

---

## [0.8.x] - 2026-09-2x（大扫除之前）

### 新增
- 1.1–1.10 路演 P0 修复
- 2.1–2.4 AI 含量补齐
- 3.1–3.7 UI 体验修复
- N1/N2/N3（对话执行器 + 去 AI 字样 + KPI）

### 修复
- 昨夜误删事故恢复（`risk_demo_v2_02`）
- 两个 P0 越权（`dashboards/my` + DELETE）

---

## [0.1.0] - 2026-08-xx（项目起点）

### 新增
- 项目初始化
- 基础框架（backend / frontend / data / docs）

---

## 更新纪律

1. **每次 commit 后追加** —— 不是每天汇总，是每次 commit
2. **每条格式**：`- 描述（ISS-xxx，commit hash）`
3. **分类**：新增 / 修复 / 变更 / 删除 / 安全
4. **不许 AI 腔**：不写"作为 AI"、"值得注意的是"
5. **未发布的写在最上**，发布时改成版本号 + 日期

---

## 版本号规则（本项目）

- **0.x.x** = 草稿阶段（2026-09 之前）
- **1.0.0** = 封板（2026-10-10 目标）
- 之后按语义化版本：主版本（不兼容）/ 次版本（新功能）/ 修订（bug 修）

---

## CHANGELOG 与 DECISIONS 分工

| 场景 | 写哪 |
|---|---|
| "修了 is_avg 未定义" | CHANGELOG（改了什么） |
| "为什么选 kimi-k3 不选 GLM" | DECISIONS（为什么） |
| "项目定位改为私有" | CHANGELOG（变更） + DECISIONS（为什么） |
| "AI 权限定位改为高" | DECISIONS（为什么），CHANGELOG 提一句 |

---

## 最后更新

- **时间**：2026-10-03
- **版本**：v3
- **状态**：
  - 骨架从 0.1.0 到 1.2.0 已齐
  - 更新纪律已定（每次 commit 后追加）
  - 版本号规则已定
  - 与 DECISIONS 分工已明确
  - v3 补齐 night9–18 全量提交链；落盘 `docs/project_record/CHANGELOG.md`（✅）
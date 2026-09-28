<!-- 权威治理源文件：由 _coach_input/ 于 night8 Item3 步骤7 迁入 docs/project_record/。其他文档引用请以本文件为准。 -->

# CHANGELOG

> 本项目所有显著变更都记录在此文件。
> 格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
> 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
> 本版：v2，2026-09-28。**

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

- **时间**：2026-09-24
- **版本**：v1
- **状态**：
  - 骨架从 0.1.0 到 1.0.0 已齐
  - 更新纪律已定
  - 版本号规则已定
  - 与 DECISIONS 分工已明确
  - 落盘 `CHANGELOG.md`（**待做**）
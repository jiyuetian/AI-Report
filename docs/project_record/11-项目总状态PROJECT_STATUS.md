# 项目进度总表（PROJECT_STATUS.md）

> 每次 AI 开工前必须先读这份文件。
> **本版为 2026-10-03 最新版（v3），覆盖此前 v2（2026-09-22）及更旧版本。**
> 格式规则：已完成 `- [✓]`，未完成 `- [ ]`。
> 维护规则：每完成一项 → 打勾 → 更新台账 → 落盘证据 → 更新本文件。

---

## 一、当前状态

- **项目**：AI-Report（大赛 PDF 项目，路演延期）
- **仓库**：`C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report`
- **分支**：`p0-security-fixes`
- **交接 HEAD**：`af4fd5b`（fix(test_runner): 兼容 IntegrationTestCase.run() bool 返回契约）
- **目标定位**：真产品 + 知识资产沉淀
- **核心差异化**：AI 自主推理 + 完整记忆 + 可积累模板
- **当前阶段**：**第四期（期四）收尾完成**，night18 全量回归（TEST-2）全绿；下一轮进入 **阶段 9 AI 对话 Top3**
- **本轮（night18）完成**：ISS-058 阈值调整 `adjust_threshold`（`f0cc1fb`）+ TEST-2 全量回归（98 检查点全 PASS）
- **本轮新暴露**：ISS-059（`compute_stats` 对 `e["data"]` 未 `.get` 防御）→ OPEN，下轮顺手修

---

## 二、阶段进度（10 阶段）

| 阶段 | 内容 | 状态 | 依据 |
|---|---|---|---|
| 0 | 全项目扫描 | ✅ | `bb5e35b` |
| 1 | 遗留问题清单 | ✅ | `693d90c` |
| 2 | 定规范 | ✅ | `RULES.md` / `CONVENTIONS.md` / `CHANGELOG.md` |
| 3 | 清理 | ✅ | `01ce96b` |
| 4 | 代码规范化 | ⏳ | **验收定义（教练定）**：①命名档——新增文件符合 `NAMING.md`；②安全档——新增端点带鉴权 + 前端调用点带 token（红线5）；③目录档——过程文件不进代码目录、验证脚本 `_*.py` gitignored；④契约档——跨模块字段访问用 `.get` 防御（ISS-059 为首个执行样本）。三档 spot-check 通过即算达标，不单独占夜 |
| 5 | 全测试 | ✅（分阶）| 每类改动后已跑 |
| 6 | ISS 债清单 | ✅ | `ISSUES.md` |
| 7 | 全量回归 | ✅ **night18 全绿** | 98 检查点 |
| 8 | 夜跑交接包 | ✅ **v2** | `docs/project_record/handover/` |
| 9 | AI 对话 Top3 | ⏳ | 待开：多轮历史注入 / 主链路 LLM 决策 / 澄清退避 |
| 10 | 明早交付 | ✅ | 每 night 有 `NIGHT_SUMMARY.md` |

---

## 三、Task A–K（第四期主线，全部完成）

| Task | 内容 | 状态 | commit |
|---|---|---|---|
| A | LLM 链 7 层调整（D-020） | ✅ | `50308ea` |
| B | 图表模板库（后端） | ✅ | `a33f655` |
| C | 图表模板库（前端） | ✅ | `76e81ea` |
| — | 链路规则引擎（YAML + fail-fast + rule_id 回链） | ✅ | `47681b1` |
| D | 模块 B 收尾 + 登记 ISS-058 | ✅ | `269663c` |
| E | ISS-048 对话格式漏点 | ✅ | `dd7af5c` |
| F | ISS-045 LLM 退避重试（8/16/24s，最多 3 次） | ✅ | `fed1476` |
| G | 最高权限 CRUD（走规则引擎 fail-fast） | ✅ | `a01deb1` |
| H | 派生指标 14 项（`METRIC_REGISTRY`） | ✅ | `2932834` |
| I | 下游重算一致性 C-16（事件驱动 + 依赖图 + 校验） | ✅ | `5f6c6a5` |
| J | 使用统计 J-8（`UsageStats` 内存态脱敏） | ✅ | `45a7ad6` |
| K | 全链路联调（`integration/` 离线 smoke） | ✅ | `45a7ad6` / `e338981` |

> 另：night14 Task1/2/3（AI 行为白盒化 `ai_action_log` / 日志页 / B 模块补测）已落，见 `night14/ROUND_NOW.md`。

---

## 四、ISS 债状态（截至 night18）

| ID | 严重度 | 内容 | 状态 |
|---|---|---|---|
| ISS-058 | — | 对话「把阈值调 X%」无动作 | ✅ **DONE** `f0cc1fb`（night18） |
| ISS-059 | P2 | `analytics` 事件字段未防御（`e["data"]` 等） | ✅ **DONE**（教练验收轮 2026-10-03，全文件防御化，9/9 PASS） |
| ISS-057 | P0 | `run_backend.py` `_pid_alive` Windows 误杀 | ✅ DONE（night14 Task0） |
| ISS-053 | P1 | 依赖安全钉固（python-multipart/pandas/jinja2/email-validator/httpx） | ✅ 代码 DONE，待 `pip install` 实装 |
| ISS-045 | P1 | LLM 调用失败指数退避重试 | ✅ DONE（Task F） |
| ISS-044 | P1 | 智谱 `json_mode` 不稳（带 ``` 围栏） | ✅ DONE（`a555b99`） |
| ISS-030 | P1 | glm 资源包到期风险（10-25） | ⏳ 待拍板（切 `glm-4.5-air` or 续包） |
| ISS-025 | P0 | 一批端点无鉴权 | 部分闭环（3 P0 + tokens/status 已修，余量跟踪） |
| ISS-031/033/040 | P2/P3 | 兜底约束 / 「再来一个」指代 / 纠正指令 | 长期观察 |

> 完整债见项目根 `ISSUES.md`。

---

## 五、待办 / 待拍板

### A. 立即可做（<10 分钟）
1. ~~**ISS-059** `analytics` 事件字段防御化~~ ✅ **已完成**（2026-10-03 教练验收轮，见 `AI_CHANGES.md` §十六）
2. `_verify_*.py` 编写规范文档化（night17 暴露 8 处脚本 bug）

### B. 需拍板
1. **ISS-030** glm 资源包（10-20 前拍板）
2. **阶段 9 AI 对话 Top3**（选一个做透）
3. **Dependabot 1 high 依赖漏洞**：default branch 告警，不阻断功能；需取 `gh api repos/jiyuetian/AI-Report/dependabot/alerts` 结构化数据后评估最小升级（本机 `gh` 未安装，需浏览器查看或装 gh）

### C. 长期
- 阶段 4 安全档/目录档 spot-check（不单独占夜）

---

## 六、关键事实（怕它忘）

1. **DuckDB 业务库**：`backend/data/duckdb/aibi.db`（约 134MB，518 张 `ds_*` 表）—— 图表真相库
2. **SQLite 元数据**：`backend/data/aibi.db`（约 6.1MB）—— 由 `DATABASE_URL` 指向；与 duckdb 同名不同文件
3. **后端 Python**：系统 `Python312`（`3.12.10`，实测）；**非** workbuddy venv
4. **LLM 七层链**：`kimi-k3 → glm-4.5-air → glm-4.7-flash → glm-4.6v → deepseek-v4-flash → agnes-2.0-flash → sensenova-6.8-flash-lite`（以 `.env` `LLM_PROVIDERS` 为准）
5. **代理**：7897（Clash，已永久配置）；53012（沙箱注入，对 GitHub 502，须绕过）
6. **git-bash shim 缺** `ls/cat/head/tail/grep/dirname/cd` → 用 `python -c` / Read / Glob / Write
7. **所有 API 挂 `/api/v1`**（`/health`=404，正确是 `/api/v1/health`）
8. **UI 可真截图**：Playwright + 系统 Edge（需注入 token + user roles）
9. **红线段落**：改 schema 前备份 + 回滚脚本；每 commit 前给用户看 diff

---

## 七、下一轮（night19）建议

| 优先级 | 主线 | 备选 |
|---|---|---|
| **P0** | 阶段 9 AI 对话 Top3（做透一个，建议「多轮历史稳定注入」）| ISS-059（顺手修）|
| P1 | ISS-030 拍板 | Dependabot 1 high 评估 |
| P2 | `_verify_*.py` 规范文档化 | 阶段 4 安全档 spot-check |
| P3 | 前端 UI 打磨 | 观察项回归 |

---

## 八、最后更新

- **时间**：2026-10-03
- **版本**：v3（覆盖 v2 2026-09-22 及更旧）
- **状态**：阶段 0-3/5-8/10 已收口；阶段 4/9 进行中；Task A–K 全绿；night18 TEST-2 98 检查点全 PASS
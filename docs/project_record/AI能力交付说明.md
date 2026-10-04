# AI 能力交付说明（night28 收口版）

> 适用仓库：`AI-Report`（数据上传 → 质检 → 清洗 → AI 生成看板 → 附录 → 血缘 → 列表统计）。
> 本文档面向「交付/验收」：说清 AI 现在能做什么、边界在哪、哪些需你本机真机验收、还有哪些遗留。
> 配套文档：`AI_TEST_CASES_v1_RESULT.md`（168 条覆盖矩阵）、`34项功能完成度矩阵.md`、`ISSUES.md`、`AI_CHANGES.md`。

---

## 1. AI 能力清单（当前已交付）

| 能力域 | 模块 | 说明 |
|---|---|---|
| AI 生成看板 | A | 上传数据→走 S1–S5 出看板；图表选型（饼/柱/线/地图/KPI/直方图）；结论质量；异常降级；绿/灰标标注。 |
| AI 对话迭代 | B | 单轮改图/加图/删图/筛选/改标题/加结论；复合指令拆分；多轮承接；纠正/澄清；确认词执行。 |
| AI 参与每层 L1–L5 | C | AI 可读每层结果、判断正误、直接改规则（最高权限+留痕）、触发下游重算、查修改记录。 |
| 用户视图 | D | 血缘六层下钻、依据可见、质量分、生成方式标注、版本快照/回退、附录 A/B/C。 |
| AI 视图（操作日志） | E/L/M | `ai_action_log` 全链路白盒埋点（动作/意图/模型/延迟/结果）；查询 API（分页+过滤+权限隔离）。 |
| 边界与异常 | F | 不支持算子诚实拒绝/引导；空/超长/特殊字符不崩；5 轮上下文保持；跨会话独立；刷新恢复。 |
| 弹窗与兜底 | G | AI 不可达弹窗让用户选（继续等/规则兜底）；超时自动兜底；后端挂不白屏。 |
| 模型轮换 | H | 六层 failover 链（现 5 层：kimi-k3→glm-4.7-flash→deepseek-v4-flash→agnes→sensenova-lite）；每层 config 合法；模型切换不串会话。 |
| 派生指标 | I | AI 生成加工计划→最高权限执行→重跑 L1–L4→血缘回填→引导出图；不可算诚实拒绝。 |
| AI 管控（个人中心） | J | 提示词管理（分层/版本化/可回退）、指标模板库、AI 日志查询、权限红线。 |
| 口语复合指令 | K | 用户真实原话转化：单值/累计 KPI、撤销/删除、输出护栏（标题规范/高基维度 TopN/字段不存在澄清）、连续多轮。 |
| 阈值调整 | N | `ADJUST_THRESHOLD` 意图→写 `config.thresholds`（与 filter_drill 隔离）；区间护栏；undo 闭环。 |

---

## 2. 本轮（night27–night28）已闭环的关键问题

- **ISS-062~066（risk_demo_v2_01 实测 5 问题）**：自动质检静默跳过 / 批量修复无超时 / 重置不回滚 / 自动弹报表打断 / 单动作空气泡——均落码 + 结构级验收通过（night27）。
- **ISS-066 守卫缺陷（教练核实）**：`chat.py` complete 事件两处缺陷（缺 `await` + dict 直接塞 message 致 SSE `json.dumps` 崩溃）→ 补 `await` + 取 `.message` 字符串 + `_verify_iss066_message.py` 真跑 10/10 PASS（night27 补丁 `c415f24`）。
- **统一 AI 失败处理规则 R1–R5**：对话 SSE 与看板生成后台轮共用判定/兜底/重试/标注基线（不静默、不空泡、双入口、诚实标注、退避重试）。
- **ISS-058（阈值调整功能缺口）**：N 模块 8 条全部 PASS（night18 `f0cc1fb`，35/35 验证）。
- **ISS-053（依赖漏洞）**：`requirements.txt` 对齐到已验证安全且实际在跑的版本，pip-audit 由 33 CVE 降至 **2 CVE（仅 ecdsa 0.19.2 上游无修复版，残余）**（night28 Task A `898ca30`）。

---

## 3. 已知边界与残留风险

### 3.1 需真机验收（22 条，纯浏览器 UI，不计入自动回归）
A1-3、A4-1、A4-4、A4-6、A5-1、D-1…D-8（8）、F-7、F-11、F-12、G-1…G-5（5）、H-4。
后端逻辑均已通过 in-process 脚本真跑覆盖；这些项仅依赖前端渲染/截图/弹窗交互。

### 3.2 测试覆盖缺口（9 项功能意图无对话用例，非缺陷）
ATTRIBUTION 归因追问、QUALITY_FIX、CHART_FIX、CREATE/UPDATE/DELETE_CONFIG、BULK_UPDATE_DATA、QUERY_METRIC、RECALC_METRIC（MANAGE_PERMISSIONS 仅部分）。
→ 建议纳入 `AI_TEST_CASES_v2.md` 补充；不计入 0 FAIL。

### 3.3 依赖残留风险
- **ecdsa 0.19.2（CVE-2024-23342）**：上游无修复版，残余；当前仅间接依赖（python-jose 路径），实际调用面小。
- **前端 axios / Dependabot**：`package.json` 用 `^` 范围，建议 CI 跑 `npm audit` + `npm update` 重新落锁（沙箱无 npm audit advisory 网络，改用 OSV 审计 lockfile 确认 axios 非漏洞源）。
- 后端 pip-audit 现状：修复后 2 CVE / 1 包（ecdsa）。

### 3.4 模型限流
六层 failover 已收敛为 5 层（glm-4.5-air/glm-4.6v 资源包 2026-10-03 提前耗尽已下掉，保留 glm-4.7-flash 免费层）。kimi-k3 主用限流时自动切备胎；极端全挂走 G-1 弹窗。

---

## 4. 真机验收步骤（你本机执行）

### 4.1 代码同步（沙箱无 git 网络，需你本机 push）
当前分支 `p0-security-fixes`，本地 HEAD `898ca30`，**未 push**。请在本机（带 `127.0.0.1:7897` 代理）执行：
```
git -C <repo> -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin p0-security-fixes
```
（沙箱 GitHub 走 git 协议被 SIGTERM，无法代 push；凭据在 Windows 凭据管理器，本机可直推。）

### 4.2 11 项卡（night26 Task D 准备的一键检查器 + 步骤卡）
见 `docs/project_record/night_runs/night26/`（11 项需真机人工验收脚本化准备）。逐项过：看板生成绿标、对话改图/加图、撤销、阈值调整、操作日志、血缘下钻、版本回退、弹窗兜底、模型切换、派生指标、管控面板。

### 4.3 night27 五处浏览器复测
ISS-062（自动质检不跳过）、ISS-063（批量修复超时/取消/重试）、ISS-064（重置回滚清洗层）、ISS-065（不自动弹报表）、ISS-066（单动作无空气泡）——结构级已 PASS，浏览器体验确认项。

---

## 5. 遗留与后续

| 项 | 状态 | 责任方/时机 |
|---|---|---|
| ISS-025 验收侧 11 项（push 比对远端 / DB 真跑 / 真实看板绿标 / 用户拍板） | 代码闭环，验收待真机 | 你本机 push 后 |
| night27 五处浏览器真机复测 | 结构 PASS，体验确认 | 你本机 |
| ecdsa 0.19.2 残余 CVE | 上游无修复，监控 | 上游发版后升级 |
| 前端 axios/Dependabot 落锁 | 待 CI | 你本机/CI |
| 9 项无用例功能意图补测 | 建议 v2 | 下一轮 |
| night28 全部 commit push | 待你本机带代理 | 现在可 push |

---

## 6. 覆盖结论（一句话）

**168 条测试案例：PASS 103 / PASS* 43 / 需真机 22 / FAIL 0**；34 项功能完成度 **24 已覆盖 / 1 部分 / 9 无用例**；
本轮 0 新增回归、0 新增 FAIL，依赖漏洞由 33 CVE 收敛至 2 CVE（ecdsa 残余）。交付可进入真机验收阶段。

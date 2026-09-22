# 夜跑交接 · 一页纸（NIGHT_SUMMARY）

> 日期：2026-09-22 夜（收尾轮）｜ 分支：`p0-security-fixes`
> 交接 HEAD：见下方提交链最后一笔 ｜ 详档：`docs/handover/README.md`、`docs/issues/AUTH_AUDIT.md`

## 0. 新模型接手第一句话

**先读本节，再动手。** 今晚原点是一个真实数据事故：清理测试看板时，被两个 P0 越权放行了删除，真实演示看板 `risk_demo_v2_02` 被误删两次。**现已完整恢复并验证通过**，两个 P0 也已修复并推送。但**鉴权面审计又挖出第三类越权（一批端点完全无鉴权）**，这是明早第一优先。

**硬红线（今晚新增，效力最高）：**
1. 禁止任何"批量删除/清理" —— 包括枚举后循环删、按条件批量删。
2. 删除类任务只给方案 + 单条脚本，**不自动执行**。
3. 单个删除前：先备份 → 打印要删什么 → 用户拍板 → 才执行。
4. 修 P0 期间**不许碰任何看板数据**。

---

## 1. risk_demo_v2_02 恢复完整性验证（全绿）

看板 `dash_4bece390_3619ff`，逐项实际接口响应：

| 项 | 结果 | 证据 |
|----|------|------|
| 5 张图有数据 | ✅ 5/5 | `chart-data` 各返回 **620 行**，HTTP 200 |
| 图表标题正确 | ✅ | `关键指标 / 婚姻状况vs收入负债比 / 收入负债比分布 / 历史逾期次数vs收入负债比 / 结构分布`（kpi/bar/histogram/scatter/pie） |
| 附录 A 字段字典 | ✅ | 1 个数据集、**13 列** |
| 附录 B 清洗记录 | ✅ | **12 条** |
| 附录 C 指标明细 | ✅ | **4 条** |
| 版本记录 | ✅ **1 条** | 原为 0，已从 09-18 备份外科补插 `v1 AI生成初始版本`（纯 INSERT，先备份 `aibi.db.before_ver_insert_20260922_233455`） |
| 分享链接 | ✅ 无需恢复 | **09-18 备份里也是 0 条** —— 事故前本来就没有，非缺口 |
| 数据集表 `ds_4bece390_*` | ✅ 4 张全在 | `_233a_4842_9c98_807f1fb5fab2`(620) / `_agg`(3) / `_cleaned`(620) / `_norm`(620)；全库 ds_* 496 张 |

**关于"整库恢复"的取舍（已与用户确认走外科方案）**：那条丢失的版本记录 `config_snapshot` 与当前生效 config **md5 完全相同**（`1a1636e5aacd1c4e0800bb7c9f2ca8a9`），内容零丢失，只缺一条历史留痕。而整库回滚到 09-18 会**丢掉 30 个 09-18 之后新建的看板**（含今天 6 个 `risk_demo_v2_05`、09-20 的 `QA销售`/`路演验证`、S3-verify×6），故不采用。

> 附带查明：09-18 备份有 40 个看板、当前 31 个，差异 39 个几乎全是 `qa_*` 测试垃圾 —— 09-18 晚间已有多次**主动清理**记录（见工作记忆 09-18），**不是**今晚事故造成的。`audit_logs` 为空，无法逐条取证删除时点，但 DELETE 的 legacy 特判只匹配 `anonymous`/`current`，而这 39 个中仅 1 个是 `current`（即 risk_demo_v2_02，已恢复）。

---

## 2. 两个 P0 修复结果（均已推送）

### P0-1 `GET /api/v1/dashboards/my` 归属过滤

根因：`_OWNERS = ("anonymous", "current", uid)` 固定含 legacy 标记 → **任何登录用户**都能看到 pre-auth 演示看板。

```diff
-    # 兼容 pre-auth 演示数据（owner 为 'anonymous'/'current'）对任何已登录用户可见；
-    _OWNERS = ("anonymous", "current", uid)
+    # P0-1：legacy 数据仅对超管可见；普通用户严格只看自己创建或更新的看板。
+    if current_user.get("is_superuser"):
+        _OWNERS = ("anonymous", "current", uid)
+    else:
+        _OWNERS = (uid,)
```

**实测**：`e2e_test`=1 条 / `user_d10`=6 条 / `admin`=17 条，**两两交集 0**；e2e 看不到 legacy 与 admin 的看板；admin 仍可见 `risk_demo_v2_02`。

### P0-2 `DELETE /api/v1/dashboards/{id}` 越权

根因：`is_legacy = created_by in ("anonymous","current")` **无条件放行**删除 → 真实事故来源。

```diff
     uid = current_user["user_id"]
     is_owner = dashboard.created_by == uid
-    is_legacy = dashboard.created_by in ("anonymous", "current")
     is_admin = bool(current_user.get("is_superuser"))
-    if not (is_owner or is_legacy or is_admin):
+    if not (is_owner or is_admin):
         raise HTTPException(status_code=403, detail="只有创建者或管理员可删除看板")
```

**实测（用一次性 decoy，未碰真实数据）**：

| 场景 | 结果 |
|------|------|
| e2e 删**自己的** decoy（控制组，证明删除功能没被误伤） | **200** ✅ |
| e2e 删 **legacy** decoy | **403** ✅ 已拦截 |
| e2e 删 **admin 的** decoy | **403** ✅ 已拦截 |
| e2e 删 **risk_demo_v2_02**（真实演示看板） | **403** ✅ 安全 |
| admin 删自己的 | **200** ✅ |
| admin 删 legacy | **200** ✅ |

> 保留"legacy 对超管可见/可删"是刻意取舍：全库只有 `risk_demo_v2_02` 是 `created_by='current'`，若一刀切严格 `created_by == uid`，它将对**所有人**不可见、演示链路断裂。

---

## 3. 鉴权面审计结果 → `docs/issues/AUTH_AUDIT.md`

方法：静态全量扫描 `backend/app/api/*.py` **+ 不带 token 实探**（用不存在的 id，不触碰真实数据）。

- 写操作端点 **106** 个（业务端点缺归属校验 **61**）；列表端点 **28** 个（未按 owner 过滤 **15**）
- 实探 **25** 个端点：**14 个在完全无 token 时即可抵达 handler**

**新发现的"第三类越权"（ISS-025，P0 待修）**：

| 端点 | 风险 | 影响 |
|------|------|------|
| `POST /api/v1/versions/rollback/{dashboard_id}` | **P0** | 无鉴权回滚**任意看板**，与刚修的两 P0 同一攻击面 |
| `POST /api/v1/shares/create` | **P0** | 无鉴权为**任意看板**建分享链接（数据外发） |
| `POST /api/v1/chat/message` | **P0** | 无鉴权对**任意看板**发起 AI 改图（含删图动作） |
| `POST /exports/sync`、`/versions/create`、`GET /versions/list/{id}`、`GET /tokens/status` | P1 | 无鉴权触发导出/建版本/读版本历史/读配额 |
| 管线类（`/quality/check`、`/reports`、`/lineage/build`、`/brain/s3/*`、`/llm/chat`） | P2 | 无鉴权驱动管线，刷 LLM 配额 |

---

## 4. ISS 单处理情况

`docs/issues/ISSUES.md`：在债 **19 → 21**（P0 2→3、P2 5→6），已闭环 **6 → 8**。

| ID | 严重度 | 内容 | 状态 |
|----|--------|------|------|
| ISS-023 | P0 | `/dashboards/my` 未按 created_by 过滤 | **已闭环 `2541347`** |
| ISS-024 | P0 | DELETE legacy 越权（真实事故） | **已闭环 `2541347`** |
| ISS-025 | P0 | 一批端点完全无鉴权（审计新发现） | 待处理 ← **明早第一优先** |
| ISS-022 | P2 | AI 对话删图实体抽取失败，误拒删除 | 待处理（阶段9） |
| ISS-020 | P0 | 导出假成功+跳页 | 待处理 |
| ISS-021 | P1 | Dependabot 1 high 依赖漏洞 | 待处理（push 时 GitHub 回显） |

---

## 5. commit hash 列表（**均已 push**，本地=远端）

| Hash | 内容 |
|------|------|
| `2c89147` | docs：ISS 债清单补 ISS-022~025 + 总览刷新 |
| `e62282b` | docs：第4步 鉴权面审计 `AUTH_AUDIT.md` |
| `2541347` | **fix(security)：P0-1 归属过滤 + P0-2 DELETE 越权** |
| `411f3f3` | docs：阶段10 交接包（前序） |
| `2bf2c54` | docs：ISS-021 Dependabot 漏洞 |
| `5a1203f` | docs：阶段8 `docs/handover/` |
| `0ba98b1` | docs：阶段6 ISS 债清单 |

**push 方法（重要）**：沙箱注入代理 `127.0.0.1:53012` 对 GitHub **502**；直连也已 reset。可用的是 **Clash `127.0.0.1:7897`**：
`git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin p0-security-fixes`

---

## 6. 未完成项 + 原因

| 项 | 原因 |
|----|------|
| **ISS-025 无鉴权端点修复** | 涉及改 API 契约（加鉴权依赖），属红线档，需停服→备份→列全部调用点→回滚脚本；本轮红线第4条"修 P0 期间不许碰看板数据"，且时间不够。已留完整清单在 `AUTH_AUDIT.md` 第 3 节 |
| **阶段 4 高风险子类**（API契约/数据模型/schema） | 与 ISS 债重叠，走红线不改（延续前序决定） |
| **阶段 9 AI 对话 Top3** | 已留 ISS-015 / ISS-022，时间不够 |
| **ISS-020 导出假成功**、**ISS-021 Dependabot** | 需先复现/`pip audit` 定位，非本轮范围 |
| risk_demo_v2_02 分享链接 | 非缺陷 —— 事故前就不存在 |

---

## 7. 环境与已知陷阱（补本轮新坑）

1. Git-Bash shim 坏（`dirname`/`cd`/`head`/`tail` 缺）→ 用 `git.exe -C "<绝对路径>"` 或 Python。
2. **Edit 工具偶发"报成功未落盘"**（本仓已第 4 次）→ 改用 Python 确定性替换 + 回读校验，写完 Grep 复核。
3. **DuckDB 被后端独占**，另一进程 `read_only=True` 也打不开 → 需停后端才能直接查。
4. **PowerShell 工具 stdout 常空** → 用 Bash+Python 取结果。
5. 后端必须用 **Python312**（`AppData\Local\Programs\Python\Python312`），3.13 缺 uvicorn/python-jose。
6. 直连 127.0.0.1 需绕代理（`urllib` 装 `ProxyHandler({})`；`httpx` 用 `Client(trust_env=False)`）。
7. **GitHub push 走 `127.0.0.1:7897`**，53012 与直连均不可用。

## 8. 当前服务状态

- 后端：**运行中**（端口 8000，Python312，`[DUCKDB-OK] 496 张 ds_* 表`，`✅ 数据库表已创建/更新`）
- 元库 `backend/data/aibi.db` 6.5MB；安全备份 `aibi.db.before_ver_insert_20260922_233455`；事故前快照 `aibi.db.pre_recover_20260922_230907`
- 工作树 clean，全部已推送

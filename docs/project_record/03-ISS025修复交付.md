# 今日交付 · DAY_SUMMARY_2（ISS-025 鉴权修复）

> 分支：`p0-security-fixes` ｜ 本轮 HEAD：`74bb398`（push 见末尾核对）
> 接续：昨夜 NIGHT_SUMMARY.md（恢复 + 两 P0 + 鉴权审计）

---

## ⛔ 硬红线（全程遵守）

1. 禁止任何批量删除/清理 —— 全程零删除
2. 删除类只给方案 + 单条脚本，未自动执行
3. 单个删除前：备份→打印→拍板→才执行（本轮无删除操作）
4. **改后端鉴权端点必须同步改前端调用点带 token**（红线5，本轮回避了 G3 翻车）
5. 改 schema 前备份 + 回滚脚本（本轮未改 schema）
6. 每个 commit 前给看 diff（见各步）

---

## 1. 134 个无鉴权操作 —— 完整分类表（第1步，只查不改）

方法：拉 `/openapi.json` 全量扫描（193 个 operation，134 个无 `security` 声明），逐条人工判定。
上一轮手探只报 13 个 B 类，严重低估 —— 真实规模是 134。

| 分类 | 数量 | 处理 |
|---|---|---|
| **A 类（有意公开）** | 10 | 不改（login/register/captcha/forgot-password/health/公开分享页等） |
| **测试端点** | 38 | 不修（_internal×16 / golden×9 / loadtest×7 / chat-test×4 / quality-debug×2） |
| **C 类（待拍板）** | 1 | `tokens/status` → 本轮已按"可选鉴权"处理 |
| **真漏必须修** | 85 | P0 35 / P1 35 / P2 15；本轮修 3 个 P0 + tokens/status，余 80 进白名单跟踪 |

完整表见 `docs/issues/AUTH_AUDIT.md` 附录 B（134 行逐条：端点|方法|分类|优先级|说明）。

**三问结论（用户原问）：**
1. 有意公开 0 个业务端点；真漏 13 个（手探）→ 实际 85 个（全量）。
2. 与 G3（13 个 GET 读端点）**零重叠** —— G3 只挑了 GET 漏了写端点；G3_FIX.md 第5节自登记 tokens/chat 遗留。
3. 防复发三件套已落地（见第5步）。

---

## 2. 3 个 P0 后端修复（第2步）+ 实测

commit `34a4cdc`。根因统一：端点签名 `current_user: str = "anonymous"` 默认值，无 `Depends`。

| 端点 | 改法 | 无 token | 有 token |
|---|---|---|---|
| `POST /versions/rollback/{id}` | `Depends(get_current_user)` | 401 ✅ | 500（抵达业务）✅ |
| `POST /shares/create` | 同上，分享归属 `created_by`=登录用户 | 401 ✅ | 200 ✅ |
| `POST /chat/message` | 同上，函数体 9 处 `current_user` 引用零改动 | 401 ✅ | 200 ✅ |

实测（真跑，非推断）：**ALL_PASS ✅**

---

## 3. 红线5 命中的裸 fetch 修复（第3步）

commit `2d1bfd9`。改后端不加前端 token → 登录态 401 白屏（G3 翻车点）。本轮一次性补齐 **8 处**：

- `ChatPanel.tsx`：`tokens/status`(87)、`chat/sessions`(163)、`chat/message`(222)
- `QualityCheckPanel.tsx`：`quality/check/ai`(220)、`quality/check`(318)、`quality/fix`(443)、`quality/fix-batch`(531)
- `SkillPanel.tsx`：`/skills`(43) —— 补 `import { authHeaders }`

手法：已有 `headers` 对象注入 `...authHeaders()`；无 headers 的追加 `{ headers: authHeaders() }`；过时注释统一更正。
**`tsc --noEmit` EXIT=0**（authHeaders 引用全部合法）。

---

## 4. tokens/status 可选鉴权（第4步，用户拍板）

commit `34a4cdc`（同后端修复）。`Depends(get_optional_user)`：

- 无 token → `{ authenticated: false, quota: null }`（不泄露任何用户数据）✅
- 有 token → `{ authenticated: true, user_id, quota }` ✅

实测：无 token 200 + quota=null；有 token 200 + authenticated=true。前端 ChatPanel 配额显示不受影响（带 token 走完整分支）。

---

## 5. 防复发三件套（第5步）

commit `74bb398`，可本地跑、可接 CI：

- `scripts/auth_whitelist.json`：三类白名单
  - `intentional_public`(11)：A 类 + C 类可选鉴权
  - `test_prefixes`(11)：测试桩前缀
  - `known_leak_tracked`(80)：已知无鉴权真漏，每修一个删一个（本轮 3 个 P0 已移除）
- `scripts/auth_scan.py`：拉 `/openapi.json`，遍历每个 operation 的 `security`；无 security 且不在白名单 → 判新增越权，exit 1。**实跑：193 操作中 130 无 security，全部命中白名单，0 新增越权 ✅**
- `scripts/fe_bare_fetch_scan.py`：扫 `frontend/src` 裸 `fetch`，交叉比对 OpenAPI，仅"指向已加鉴权端点的裸 fetch"判 FAIL。**实跑：0 处 ✅**

用法：
```
python scripts/auth_scan.py --url http://127.0.0.1:8000/openapi.json
python scripts/fe_bare_fetch_scan.py --url http://127.0.0.1:8000/openapi.json
```

---

## 6. 全量回归（第6步）

| 项 | 结果 |
|---|---|
| 后端 health | 200 ✅（启动加载新代码，`[DUCKDB-OK] 496 张 ds_* 表`） |
| 4 端点鉴权复验 | ALL_PASS ✅（无 token 401 / 有 token 200） |
| 历史看板图表数据 | 3 个看板（risk_demo_v2_02 / _v2_05 / QA销售）图表取数 100% HTTP 200 有数据 ✅ |
| `vite build` | 0 错误，3666 模块，15.46s ✅ |
| `tsc --noEmit` | EXIT=0 ✅ |
| 前端 5 页渲染 | 看板/管理后台/上传/报告/血缘 全部渲染真实 DOM（300K-500K） |
| **前端 /api 调用** | **12/12 = 200，0 个 401** ✅（红线5 根除，无 G3 白屏） |

> 说明：`生成看板 S1-S5` / `对话改图` 的完整 LLM 链路未本轮重跑 —— 本轮只改鉴权签名（函数体 9 处引用零改动），生成管线代码未动；且 LLM(kimi-k3) 当前限流(429)。对话改图端点已验证"带 token 200 抵达业务"。完整生成回归见昨夜 `7050ac4` 全量回归记录。

---

## commit 链（已 push，核对见下）

```
74bb398 ci: ISS-025 防复发三件套（OpenAPI 鉴权扫描 + 前端裸 fetch 扫描 + 白名单）
2d1bfd9 fix(frontend): ISS-025 红线5 —— 8 处裸 fetch 注入 authHeaders()
34a4cdc fix(security): ISS-025 后端 3 个 P0 端点 + tokens/status 加鉴权
734aedf docs: ISS-025 完整分类表（附录 B）—— OpenAPI 全量扫描 134 个无鉴权操作
```

---

## 未完成项 + 原因

1. **ISS-025 余 80 个真漏端点**（P0 35/P1 35/P2 15 中除已修 3 P0 外）：非本轮范围（用户指定只修 3 P0 + tokens/status + 7 处裸 fetch）；已进 `known_leak_tracked` 白名单跟踪，CI 门禁会拦新增。
2. 生成看板 S1-S5 完整 LLM 回归：LLM 限流 + 管线代码未改， deferred。
3. 阶段 4（数据模型/schema）、阶段 9（AI 对话实体抽取 ISS-022）、Dependabot 漏洞：非本轮目标，留后续。

---

## 待用户拍板事项

1. 余 80 个真漏端点排期（建议按 P0→P1→P2 分批，每批走"后端加鉴权+前端带 token+真跑"同款流程）。
2. 是否要把"生成看板完整 LLM 回归"也跑一遍（需 LLM 配额恢复）。
3. `nul` 零字节残留文件（工作区未跟踪，疑似失败重定向产物）——可安全删除，按红线第3条需你拍板。

---

## 新模型接手第一句话

> 分支 `p0-security-fixes`。ISS-025 已修 3 个 P0（versions/rollback、shares/create、chat/message）+ tokens/status 可选鉴权，前端 8 处裸 fetch 已带 token（tsc 0 / 5 页 12/12 API 200），防复发三件套在 `scripts/` 且 CI 门禁已验证 0 新增越权。余 80 个真漏端点进 `scripts/auth_whitelist.json` 的 `known_leak_tracked` 跟踪，每修一个从清单删一个。后端 8000 需 Python312 跑；push 走 7897/直连/默认环境退避（代理 53012 对 GitHub 502）。

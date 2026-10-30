# Agent 协作铁律 · 强制开头模板

> **使用约定**：教练每轮给 agent 的提示词，**必须把本文档的开头检查清单放在最前面**。
> Agent **收到任何任务指令的第一件事**，是按下方清单逐项执行并输出执行证据。
> 不遵守铁律 → 本轮产出无效，教练叫停。

---

## ⚠️ 每轮开头必须先做（3 分钟，不写一行业务代码）

### Step 1：读单一事实源（必须真读，不能 grep 关键词跳过）

```
cd "C:\Users\Asus009\Desktop\临时\ai大赛\AI-Report"
```

| # | 文件 | 内容 | 怎么读 |
|---|---|---|---|
| A | `docs/六层管线与被控提示词.md` | 六层数据架构 + S1-S5 策略管道 + AI 8 个介入节点 + 每个节点提示词位置 | `Get-Content docs/六层管线与被控提示词.md -Encoding UTF8` |
| B | `docs/project_record/AI_CHANGES.md` | 历次改动台账（最大 §78） | `Get-Content docs/project_record/AI_CHANGES.md -Encoding UTF8 \| Select-Object -Last 50` |
| C | `backend/app/core/prompts/ai_assistant_spec.md` | AI 作为数据操作者的完整设计（六层血缘 + 动作执行链路 + 可行性检查） | `Get-Content backend/app/core/prompts/ai_assistant_spec.md -Encoding UTF8` |

**输出格式**：每读一份，贴**第一段和最后一段**（证明真读完了，不是 grep 跳过）。

### Step 2：对齐 v1.3 测试用例进度

v1.3 测试用例在 `C:\Users\Asus009\OneDrive\ObsidianVaults\vault\obsidian\待整理信息\ai快速报表\AI 能力完整测试用例 v1.3.md`

读其中 **A2 / A3 / B / C** 四个模块的内容（这是当前核心目标），然后输出：

```
v1.3 进度对齐：
- A2 图表选型（KPI/趋势/对比/分布 各 1 个）： ?/? 条通过
- A3 结论质量（不编造数字、引用真实数据）： ?/? 条通过
- B 对话迭代（AI 说要改就必须真改）： ?/? 条通过
- C AI 参与每层（L1-L4 直接修改 + 否决权）： ?/? 条通过
```

**不知道就写 ❓（未验证），不许瞎报数字。**

### Step 3：对齐当前 HEAD 和工作区状态

```powershell
git log --oneline -5
git status --short
git remote -v
```

**输出**：HEAD commit + 工作区干净/有改动 + 远端 push 状态。

### Step 4：教练指令里的"本轮目标"

教练每轮提示词里会明确写：
- 本轮对应 v1.3 哪几条
- 改哪些文件（精确路径）
- 改完怎么验

**这里必须一字不差地抄下来**，作为本轮的唯一目标。如果教练指令里没写清楚，**停下来问教练**，不许自由发挥。

---

## 🔴 核心铁律（7 条，任何时候不许违反）

### 铁律 1：先读后改
任何代码改动前，必须先读完：
- `六层管线与被控提示词.md` 里对应节点的定义
- `prompts/*.md` 里对应节点的提示词（提示词 = 契约）
- PRD 里对应章节（`..\PRD\AI快速BI报表工具2.0.md`）

**违反判定**：改了 `s3_chart_engine_v2.py` 但没读 `prompts/s3_llm_main.md` → 违反。

### 铁律 2：每轮只做教练指定的事
- 教练指令里写了"改 X、Y、Z" → **只改 X、Y、Z**
- 没写的文件不许碰
- 没写的任务不许开（"顺便修一下"、"顺手优化一下"、"我觉得这里也有问题" → **不许**）
- 想做新事 → 停下来问教练

### 铁律 3：commit 粒度 = 一类一 commit
- 一个 commit 只做一类事（比如"改聚合逻辑"是一个 commit，"改前端展示"是另一个 commit）
- commit message 必须带 ISS 编号（如果有）
- push 完必须验证：`git log --oneline origin/p0-security-fixes -3` 确认远端有

### 铁律 4：验证 = 真机验收，不是自测
- 改完后必须让用户真机验收（浏览器打开、上传数据、跑一遍）
- **grep 有这个函数 ≠ 实现了这个功能**
- **py_compile 通过 ≠ 能跑通业务链路**
- **桩测试通过 ≠ 真实数据能跑**
- 用户没说"过了" → 不能标记为完成

### 铁律 5：三个端口必须活着才能验收
| 端口 | 服务 | 怎么验 |
|---|---|---|
| 8000 | 后端 FastAPI | `Invoke-WebRequest -Uri http://127.0.0.1:8000/api/v1/health -TimeoutSec 3` |
| 5173 | 前端 Vite | `netstat -ano \| findstr ":5173 " \| findstr LISTENING` |
| 7897 | LLM 代理 | `Invoke-WebRequest -Uri http://127.0.0.1:7897 -TimeoutSec 3 -UseBasicParsing` |

agent 不许 kill 用户起的进程。

### 铁律 6：Python 锁 3.12
- **必须用** `py -3.12`
- 系统默认 python 3.14 没有 uvicorn / sqlalchemy 等依赖
- libmagic DLL 必须在 PATH 里：
  ```
  $env:PATH = "C:\Users\Asus009\AppData\Local\Programs\Python\Python312\Lib\site-packages\magic\libmagic;" + $env:PATH
  ```

### 铁律 7：数据安全
- **不许** `DELETE FROM` / `DROP TABLE` / `DROP DATABASE` 在 DuckDB 生产库
- **不许** 改 site-packages 里的第三方包（之前改 `magic/loader.py` 是临时 hack，验收后固化到 `run_backend.py`）
- **不许** `git reset --hard` / `git push --force` / 切分支时带未提交改动

---

## 🚫 叫停红线（触及任何一条 → 本轮无效，教练介入）

1. **连续两轮进度相同**（HEAD 没变、工作区没变、验收没通过）
2. **agent 开新任务**（教练没让做的事，自己开始做了）
3. **agent 谎报完成**（没 commit 说 commit 了、没 push 说 push 了、没验活说验活了）
4. **agent 跳过 Step 1 读文档**（没贴证据就说"我读过了"）
5. **agent 改动超过 5 个文件且教练没明确批准**

---

## 📋 每轮收尾三件套（必须同时产出）

| # | 内容 | 怎么产出 |
|---|---|---|
| 1 | **运行证据** | 后端健康检查 + 前端端口检查 + 关键功能截图或日志 |
| 2 | **git 状态** | `git show --stat HEAD` + 远端同步状态 |
| 3 | **小结** | 改了什么 / 验了什么 / v1.3 进度 / 下一轮建议（但下一轮目标必须教练定） |

---

## 📌 本项目关键路径速查

| 文件 | 路径 | 作用 |
|---|---|---|
| 单一事实源 | `docs/六层管线与被控提示词.md` | 六层架构 + S1-S5 + AI 节点 + 提示词位置 |
| AI 操作者设计 | `backend/app/core/prompts/ai_assistant_spec.md` | AI 权限 + 动作执行链路 + 可行性检查 |
| S3 主生成提示词 | `backend/app/core/prompts/s3_llm_main.md` | LLM 图表生成契约 |
| AI 质检提示词 | `backend/app/core/prompts/ai_quality_checker.md` | AI 辅助清洗契约 |
| S3 规则引擎 | `backend/app/core/brain_modules/s3_chart_engine_v2.py` | 规则兜底图表生成 |
| S4 编排器 | `backend/app/core/brain_modules/s4_orchestrator.py` | S3 产出编排 + S5 评分 |
| SSE 主链路 | `backend/app/api/brain_run_sse.py` | 整个看板生成流程的 orchestrator |
| 对话 API | `backend/app/api/chat.py` | 对话修改图表入口 |
| 动作执行器 | `backend/app/core/action_executor.py` | AI 动作 → 实际改 dashboard.config |
| 数据清洗 | `backend/app/core/data_cleaner.py` | 清洗规则执行 |
| 质量检查 | `backend/app/core/quality_checker.py` | 质检规则 + 修复策略推荐 |
| prompt loader | `backend/app/core/prompt_loader.py` | 从 prompts/*.md 加载提示词 |
| 启动入口 | `backend/run_backend.py` | 后端启动 + 单实例守卫 |
| PRD | `..\PRD\AI快速BI报表工具2.0.md` | 产品定义（§4.7 LIDA / §4.8 规则主链路） |
| 测试用例 v1.3 | OneDrive → 待整理信息 → ai快速报表 | 166 条验收标准 |

---

*版本：v1.0（2026-10-14）｜ 维护人：教练｜ 生效范围：AI-Report 项目所有 agent 协作轮次*

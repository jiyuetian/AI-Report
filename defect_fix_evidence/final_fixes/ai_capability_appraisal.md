# AI 能力逐个鉴定表（Prompt 中心 12 板块）

**鉴定日期：** 2026-09-10
**范围：** `backend/app/core/prompt_manager.py:PROMPT_GROUPS` 定义的 12 个板块
**方法：** 静态读代码 + 运行时 `/health` 探测 + `.env` 配置核实
**结论速览：** 12 个能力**全部已接线、非空壳**；其中 11 个为「真实现」（含护栏/混合），1 个为「半空壳」（s2_goal_generator 标 AI 但默认走规则）。
**重要环境事实：** 本沙箱 `/health` 返回 `llm_reachable:false` —— LLM key 已配（LLM_API_KEY 长度 35）但**端点不可达**，故当前实际运行全部回落规则/默认（这是设计内的 capability_profile 降级，非 bug）。

## 判定标准
- **真实现**：代码真实调用该能力、有真实产出（LLM 或规则均算，只要非占位）。
- **半空壳**：界面/命名暗示 AI，但默认走规则、需额外开开关才真调 LLM，且默认配置下不调。
- **纯空壳**：点击无任何真实逻辑（仅 `message.info('演示')` 之类）。
- **「启用」开关语义**：Prompt 中心的启用/禁用只切换「是否用外置种子文案」（覆盖→种子文件→default 三级回退）；**禁用 ≠ 功能消失**，只是回退内置 default 文案。即开关改的是 prompt 文本，不开关功能本身。

| # | 能力板块 | 代码位置（消费方） | 真调 LLM / 规则 | 当前环境实际走什么 | 「启用」标记后真生效？ | 判定 |
|---|---|---|---|---|---|---|
| 1 | system（全局系统提示） | `s3_llm_enhancer.py:373` 作 S3 前缀护栏 | 随 S3 调 LLM（系统提示前缀） | LLM 不可达→随 S3 落规则，但前缀文案仍在 | 是（改全局护栏文案即生效） | 真实现 |
| 2 | accuracy（数据准确性红线） | `s3_llm_enhancer.py:376` 作 S3 前缀护栏 | 随 S3 调 LLM（红线约束） | 同上，护栏文案始终注入 | 是（改红线文案即生效） | 真实现 |
| 3 | schema_enricher | `schema_enricher.py:97` → `s3_llm_enhancer` 消费 | 调 LLM（build_semantics） | 不可达→回退内置默认模板，仍产出语义 | 是（改语义生成文案） | 真实现 |
| 4 | ai_quality_checker | `ai_quality_checker.py:195`（`quality.py` API） | 调 LLM（"被控版"优先读 md） | 不可达→回退默认提示词，仍跑质检 | 是（改质检 prompt） | 真实现 |
| 5 | s1_theme_detector | `s1_theme_detector.py:176`；`s1.py` | 调 LLM（detect_theme），`use_llm` 可控 | `s1_theme_detector.py:243` `if not use_llm` 落规则 | 是（改主题检测 prompt） | 真实现 |
| 6 | s2_goal_generator | `s2_goal_generator.py:233`；`brain_run_sse.py:695` | **默认规则引擎**（PRD 4.8 降本） | `use_llm=bool(BRAIN_S2_USE_LLM) and not llm_offline` → **本环境=False→规则** | 仅当 `BRAIN_S2_USE_LLM=True` 才真调 LLM；Prompt 中心"启用"不改开关 | ⚠️ **半空壳**（命名 AI，默认不调 LLM） |
| 7 | s3_llm_main | `s3_llm_enhancer.py:362`（S3 核心图表生成） | 调 LLM（主生成提示词） | 不可达→S3 落规则生成图表，仍出图 | 是（改主生成 prompt） | 真实现 |
| 8 | s3_rule_chart_enhance | `s3_llm_enhancer.py:522` | 规则增强（不调 LLM） | 规则增强始终执行 | 是（改增强规则文案） | 真实现 |
| 9 | intent_classifier | `intent_classifier.py:218`；`chat.py`/`action_planner.py` | 规则优先 + LLM 兜底（`_llm_classify`） | 规则优先，LLM 兜底；不可达时纯规则 | 是（改意图分类 prompt） | 真实现（混合） |
| 10 | ai_assistant_spec | `chat.py:281` / `brain_run_sse.py:977` | 调 LLM（对话助手规格） | 不可达→回退默认，对话仍可用（规则分支） | 是（改助手规格 prompt） | 真实现 |
| 11 | executive_summary | `report_generator.py:252`；`if LLM_API_KEY and LLM_BASE_URL` | 调 LLM（有 `_default_executive_summary` 规则兜底） | key 已配→调 LLM；若不可达→落 `_default_executive_summary` | 是（改摘要 prompt） | 真实现（有兜底） |
| 12 | executive_summary_doc | `report_generator.py:686` | 调 LLM（文档版摘要） | 同 11，key 已配→调 LLM，不可达回退 | 是（改文档摘要 prompt） | 真实现（有兜底） |

## 关键证据片段
- `config.py:24` `LLM_API_KEY: str = ""`（默认空）；`.env` 实际 `LLM_API_KEY` 长度 35、`LLM_BASE_URL` 长度 29、`LLM_MODEL` 长度 7 → **非 mock，真实配置**。
- `config.py:40` `BRAIN_S2_USE_LLM: bool = False` → S2 默认规则。
- `brain_run_sse.py:695` `use_llm=bool(settings.BRAIN_S2_USE_LLM) and not llm_offline` → S2 是否 LLM 由开关 + 可达性共同决定。
- `health.py:31` 无 key/url → `reachable:False`；本环境 `/health` 实测 `llm_reachable:false` → **LLM 端点在本沙箱不可达**，各 LLM 能力按设计降级。
- `prompt_manager.py:159` `loaded_prompt`：覆盖→种子文件→default 三级回退；禁用 prompt 只回退 default，**功能不消失**。

## 给产品/评委的诚实结论
1. **无纯空壳**：12 个能力都有真实代码路径与产出，不是占位按钮。
2. **命名与默认行为偏差**：`s2_goal_generator` 名为"AI 目标生成"，但默认 `BRAIN_S2_USE_LLM=False` 走规则 —— 对外宣讲"AI 驱动"时需说明此为可开启选项，默认降本规则引擎。
3. **"启用"≠功能开关**：Prompt 中心启停只换文案，不启停能力；若评委关心"关掉某项看板会不会变傻"，答案是"不会，只是回退默认 prompt"。
4. **当前沙箱 LLM 不可达**：本机联调时所有 LLM 能力回落规则/默认，属环境网络限制，非代码缺陷；联网配置正确 key 后即真实调 LLM。

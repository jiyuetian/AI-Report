"""B 方案回填实测数据：S3 硬超时是 180s（不是我初版写的 30~60s），
最坏耗时 = 180s + 用户决策 120s = 300s（5 分钟）。并补规则引擎实测 20.7ms/P95 68ms。
"""
import io
import sys

P = 'night3/plans/B_32_loading_page_plan_c.md'
s = io.open(P, encoding='utf-8').read()

# 1) 方案对照表的 A 行
OLD1 = '| **A** | AI 优先，AI 出图才落库 | 等到 AI 返回（30~60s） | **阻塞流水线，弹框问用户**（见下方 1.2） |'
NEW1 = '| **A** | AI 优先，AI 出图才落库 | 等到 AI 返回（硬超时 **180s**） | **阻塞流水线，弹框问用户**（见下方 1.2） |'
if NEW1 in s:
    print('[skip] 1')
else:
    if s.count(OLD1) != 1:
        print('[fail] 1 count=%d' % s.count(OLD1))
        sys.exit(1)
    s = s.replace(OLD1, NEW1)
    print('[ok] 1')

# 2) 1.2 补实测的 300s
OLD2 = '`_request_user_choice`（`:173-180`）**默认超时 120 秒**（演示可设 `BRAIN_AI_CHOICE_TIMEOUT=30`）。'
NEW2 = (
    '`_request_user_choice`（`:173-180`）**默认超时 120 秒**（演示可设 `BRAIN_AI_CHOICE_TIMEOUT=30`）。\n\n'
    '**实测配置值（`verify_32_current_state.py` 跑出来的，不是我估的）**：\n\n'
    '| 项 | 值 |\n'
    '|---|---|\n'
    '| `BRAIN_S3_LLM_TIMEOUT` | **180.0 秒**（`config.py:54`） |\n'
    '| 用户决策等待 | 120 秒（默认） |\n'
    '| **最坏总耗时** | **300 秒 = 5.0 分钟** |\n\n'
    '→ 初版方案里我写"等 30~60 秒"是**低估了 3~6 倍**。真实情况是：\n'
    'LLM 抽风时加载页最多卡 **5 分钟**，且中途还要弹框让主持人做选择。\n'
    '**这是路演的灾难级场景，也说明方案 C 不是"体验优化"而是"风险消除"。**'
)
if NEW2[:40] in s:
    print('[skip] 2')
else:
    if s.count(OLD2) != 1:
        print('[fail] 2 count=%d' % s.count(OLD2))
        sys.exit(1)
    s = s.replace(OLD2, NEW2)
    print('[ok] 2')

# 3) 规则引擎速度补实测
OLD3 = '| 规则引擎速度 | **毫秒级**（纯内存，不查库） | `s3_chart_engine_v2.py` 全文 `conn.execute` 出现 **0 次**、`duck` **0 次**、`async def` **0 次** |'
NEW3 = (
    '| 规则引擎速度 | **毫秒级**（纯内存，不查库） | `s3_chart_engine_v2.py` 全文 `conn.execute` **0 次**、`duck` **0 次**；<br>'
    '**实测 16 字段 × 20 次：平均 20.7ms / P50 15.7ms / P95 68.3ms**，产出 6 张图 |'
)
if NEW3[:40] in s:
    print('[skip] 3')
else:
    if s.count(OLD3) != 1:
        print('[fail] 3 count=%d' % s.count(OLD3))
        sys.exit(1)
    s = s.replace(OLD3, NEW3)
    print('[ok] 3')

io.open(P, 'w', encoding='utf-8').write(s)
print('chars =', len(s))

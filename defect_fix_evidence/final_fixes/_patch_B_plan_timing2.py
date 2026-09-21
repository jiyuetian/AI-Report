"""B 方案回填实测数据（修正幂等判断：必须用特征串，不能用 NEW 的开头）。"""
import io
import sys

P = 'night3/plans/B_32_loading_page_plan_c.md'
s = io.open(P, encoding='utf-8').read()
n = 0

# 2) 1.2 补实测的 300s
MARK2 = '300 秒 = 5.0 分钟'
OLD2 = '`_request_user_choice`（`:173-180`）**默认超时 120 秒**（演示可设 `BRAIN_AI_CHOICE_TIMEOUT=30`）。'
NEW2 = OLD2 + (
    '\n\n**实测配置值（`verify_32_current_state.py` 跑出来的，不是我估的）**：\n\n'
    '| 项 | 值 |\n'
    '|---|---|\n'
    '| `BRAIN_S3_LLM_TIMEOUT` | **180.0 秒**（`config.py:54`） |\n'
    '| 用户决策等待 | 120 秒（默认） |\n'
    '| **最坏总耗时** | **300 秒 = 5.0 分钟** |\n\n'
    '→ 初版方案里我写"等 30~60 秒"是**低估了 3~6 倍**。真实情况是：\n'
    'LLM 抽风时加载页最多卡 **5 分钟**，且中途还要弹框让主持人做选择。\n'
    '**这说明方案 C 不是"体验优化"而是"风险消除"。**'
)
if MARK2 in s:
    print('[skip] 2')
elif s.count(OLD2) != 1:
    print('[fail] 2 count=%d' % s.count(OLD2))
    sys.exit(1)
else:
    s = s.replace(OLD2, NEW2)
    n += 1
    print('[ok] 2')

# 3) 规则引擎速度补实测
MARK3 = '实测 16 字段'
OLD3 = '| 规则引擎速度 | **毫秒级**（纯内存，不查库） | `s3_chart_engine_v2.py` 全文 `conn.execute` 出现 **0 次**、`duck` **0 次**、`async def` **0 次** |'
NEW3 = (
    '| 规则引擎速度 | **毫秒级**（纯内存，不查库） | `s3_chart_engine_v2.py` 全文 `conn.execute` **0 次**、`duck` **0 次**；<br>'
    '**实测 16 字段 × 20 次：平均 20.7ms / P50 15.7ms / P95 68.3ms**，产出 6 张图 |'
)
if MARK3 in s:
    print('[skip] 3')
elif s.count(OLD3) != 1:
    print('[fail] 3 count=%d' % s.count(OLD3))
    sys.exit(1)
else:
    s = s.replace(OLD3, NEW3)
    n += 1
    print('[ok] 3')

io.open(P, 'w', encoding='utf-8').write(s)
print('applied =', n, '| chars =', len(s))

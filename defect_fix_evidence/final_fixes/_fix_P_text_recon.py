"""P 方案补充：S4b 生成的「分析说明文本」如何做事实对账（初版只写了占位符检测，是空缺）。"""
import io
import sys

P = 'night3/plans/P_ai_result_check.md'
s = io.open(P, encoding='utf-8').read()

OLD = '| S4b | 输出必须是非空文本，长度 ∈ [20, 2000]，且**不得包含占位符**（`TODO`/`待补充`/`xxx`） |'
NEW = (
    '| S4b | 输出必须是非空文本，长度 ∈ [20, 2000]，且**不得包含占位符**（`TODO`/`待补充`/`xxx`）；'
    '文本中的数字须通过事实对账（见 L3 文本对账） |'
)

if '文本中的数字须通过事实对账' in s:
    print('[skip] L1 already updated')
else:
    if s.count(OLD) != 1:
        print('[fail] L1 count=%d' % s.count(OLD))
        sys.exit(1)
    s = s.replace(OLD, NEW)
    print('[ok] L1 表格已更新')

# 在 L3 对账矩阵后补「文本对账」小节
ANCHOR = '**关键设计**：对账用**同一份数据、同一套聚合口径**'
ADD = '''### L3 补充 · 文本对账（S4b 分析说明）

初版只写了"占位符检测"，这是**空缺** —— S4b 生成的分析说明里往往带具体数字
（"担保金额合计 12.3 亿元，同比增长 18%"），这些数字同样可能是幻觉。

**解法：从文本中抽取数字，与数据实算对账**

```
1. 正则抽取文本中的数值片段（支持 12.3亿 / 1,234万 / 18% / 1234.56）
2. 对每个数值，在"本次生成的图表实算结果集合"里找可匹配项
   - 金额类 → 与各 KPI 实算值比对（相对误差 ≤1% 视为命中）
   - 百分比 → 与占比类图表的实算占比比对
3. 三类结论：
   - matched   ：能在实算结果中找到对应值 → ✅
   - unmatched ：找不到对应值 → ⚠️ 标"该数值未与数据对账"，图上/文上做弱化提示
   - contradicted：与实算值冲突（如文本说 12.3 亿，实算 9.8 亿）→ 🔴 必须处理
```

**处置**：`contradicted` 时**不静默改用户要读的文字**（改文案风险高），
而是：① 在说明区加一行灰色小字「文中数值与数据实算不一致，实算值 9.8 亿元」；
② 记入 `llm_calls.error_code = text_contradicted` 供统计。

**为什么不一刀切**：文本对账有天然误判率（四舍五入、单位换算、区间表述），
**宁可标"未对账/不一致"让人判断，也不要偷偷改写 AI 的措辞** —— 与 2.1 诚实原则一致。

'''
if 'L3 补充 · 文本对账' in s:
    print('[skip] L3 补充已存在')
else:
    if s.count(ANCHOR) != 1:
        print('[fail] anchor count=%d' % s.count(ANCHOR))
        sys.exit(1)
    s = s.replace(ANCHOR, ADD + ANCHOR)
    print('[ok] L3 文本对账已补充')

io.open(P, 'w', encoding='utf-8').write(s)
print('chars =', len(s))

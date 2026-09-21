"""方案 P 核心论断的可运行复现：validate_grain_compatibility 字段存在性检查未归一化。

结论先行：AI 输出的字段名只要带首尾空格 / 全角空格 / 大小写差异，
就会被现有校验器判为「不在数据集字段列表中」→ 触发重试 → 重试耗尽 →
整批降级 rule_engine → ai_participated=False（绿标变灰标）。
即：**AI 明明答对了，却被检查器错杀。**

不修改任何生产代码，只做复现与对照。
优先直接 import 真实类；import 失败时回退到逐字复刻（并明确标注）。
"""
import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, os.path.join(_REPO, 'backend'))

REAL_IMPORT = False
try:
    from app.core.brain_modules.s3_llm_enhancer import SchemaValidator  # type: ignore
    REAL_IMPORT = True
except Exception as e:
    print('[warn] 无法直接 import SchemaValidator（依赖过重）：%s' % type(e).__name__)
    print('       回退为逐字复刻 s3_llm_enhancer.py:132-165 的判定逻辑，结论等价。\n')


# ---- 逐字复刻（仅在 import 失败时使用），来源：s3_llm_enhancer.py:132-165 ----
def validate_grain_compatibility_replica(config, grain, available_fields):
    chart_type = config.get("chart_type", "")
    chart_config = config.get("config", {})
    if grain == "macro":
        if chart_type == "table" and chart_config.get("page_size", 20) > 0:
            return False, "宏观粒度禁止行级明细表（请使用聚合表或关闭分页）"
    fields_to_check = [
        config.get("x_field"),
        config.get("y_field"),
        config.get("category_field"),
        config.get("value_field"),
    ]
    for field in fields_to_check:
        if field and field not in available_fields:
            return False, f"字段 {field} 不在数据集字段列表中"
    return True, ""


# ---- 修复版：三级归一化（与 D2 action_executor._lookup 同一套）----
def _norm(s):
    return str(s or "").strip()


def _squash(s):
    return _norm(s).replace(" ", "").replace("\u3000", "")


def _lookup(field, index):
    key = _norm(field)
    if not key:
        return None
    return (
        index.get(key)
        or index.get(_squash(key))
        or index.get(key.lower())
        or index.get(_squash(key).lower())
    )


def validate_grain_fixed(config, grain, available_fields):
    index = {_norm(f): f for f in available_fields}
    for f in available_fields:
        nf = _norm(f)
        if _squash(nf) != nf:
            index[_squash(nf)] = f
        if nf.lower() != nf:
            index[nf.lower()] = f
    fields_to_check = [
        config.get("x_field"),
        config.get("y_field"),
        config.get("category_field"),
        config.get("value_field"),
    ]
    for field in fields_to_check:
        if field and _lookup(field, index) is None:
            return False, f"字段 {field} 不在数据集字段列表中"
    return True, ""


AVAILABLE = ["贷款金额", "地区", "担保类型", "抵押率", "LoanAmount"]

CASES = [
    ("干净字段名（基线）", {"chart_type": "bar", "x_field": "地区", "y_field": "抵押率"}, True),
    ("AI 输出带首尾空格 ' 抵押率 '", {"chart_type": "bar", "x_field": "地区", "y_field": " 抵押率 "}, True),
    ("AI 输出全角空格 '抵押\\u3000率'", {"chart_type": "bar", "x_field": "地区", "y_field": "抵押\u3000率"}, True),
    ("AI 输出大小写差异 'loanamount'", {"chart_type": "bar", "x_field": "地区", "y_field": "loanamount"}, True),
    ("真·不存在的字段（应判失败）", {"chart_type": "bar", "x_field": "地区", "y_field": "不存在的列XYZ"}, False),
]


def main():
    print('=' * 78)
    print('方案 P · 复现：validate_grain_compatibility 字段存在性检查未归一化')
    print('实现来源：%s' % ('真实 SchemaValidator（import 成功）' if REAL_IMPORT
                          else '逐字复刻 s3_llm_enhancer.py:132-165'))
    print('数据集字段：%s' % AVAILABLE)
    print('=' * 78)

    if REAL_IMPORT:
        sv = SchemaValidator()
        old = sv.validate_grain_compatibility
    else:
        old = validate_grain_compatibility_replica

    fails_old = 0
    fails_new = 0
    for name, cfg, expect in CASES:
        ok_old, msg_old = old(cfg, "aggregate", AVAILABLE)
        ok_new, msg_new = validate_grain_fixed(cfg, "aggregate", AVAILABLE)
        bad_old = (ok_old != expect)
        bad_new = (ok_new != expect)
        if bad_old:
            fails_old += 1
        if bad_new:
            fails_new += 1
        print('\n[%s]' % name)
        print('  期望判定      : %s' % ('通过' if expect else '失败'))
        print('  现有实现      : %s   %s' % ('通过' if ok_old else '失败', ('← 错杀！' if bad_old else '')))
        if msg_old:
            print('                 %s' % msg_old)
        print('  归一化修复后  : %s   %s' % ('通过' if ok_new else '失败', ('← 不符预期' if bad_new else '')))

    print('\n' + '=' * 78)
    print('现有实现错杀次数 = %d / %d' % (fails_old, len(CASES)))
    print('归一化修复后错杀 = %d / %d' % (fails_new, len(CASES)))
    print()
    if fails_old > 0:
        print('结论：✅ 缺陷复现成立 —— AI 答对但被判错，会走「重试2次 → 整批降级 rule_engine →')
        print('      ai_participated=False」的错误链路。方案 P 的 P0（1 小时）即修此项。')
    else:
        print('结论：❌ 未复现 —— 方案 P 的该项论断需重新核实，不能据此排期。')
    print('=' * 78)
    return 1 if fails_old == 0 else 0


if __name__ == '__main__':
    sys.exit(main())

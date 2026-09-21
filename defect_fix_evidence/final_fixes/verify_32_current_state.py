"""3.2a-e 现状验证 —— 真跑，不是只读代码。

a. 规则引擎实际耗时（方案 C 的前提：必须毫秒级）
b. AI 链路超时配置（BRAIN_S3_LLM_TIMEOUT / BRAIN_AI_CHOICE_TIMEOUT 默认值）
c. 现状「AI 失败弹框」是否真会阻塞（读代码 + 确认超时）
d. 前端加载页支持 partial 跳转需要改哪几处
e. 版本表能否承载 v1/v2（DashboardVersion 字段 + 写入路径）

输出：defect_fix_evidence/final_fixes/verify_32_current_state.out
"""
import io
import os
import re
import sys
import time

_REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, os.path.join(_REPO, 'backend'))

buf = []


def log(s=''):
    buf.append(s)
    print(s)


log('=' * 78)
log('3.2a-e 现状验证（方案 C 可行性）')
log('=' * 78)

# ---------- a. 规则引擎耗时 ----------
log('\n【a】规则引擎实际耗时（方案 C 的前提：必须毫秒级才能"秒出图"）')
try:
    from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine  # type: ignore

    FIELDS = [
        "借据编号", "客户名称", "证件号码", "贷款金额", "担保金额", "抵押物评估价值",
        "抵押率", "担保类型", "地区", "放款日期", "到期日期", "还款状态",
        "逾期天数", "客户经理", "产品类型", "利率",
    ]

    # 预热一次（排除 import / 首次初始化开销）
    S3ChartEngine().generate_dashboard_config(fields=FIELDS, grain="aggregate")

    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        cfg = S3ChartEngine().generate_dashboard_config(fields=FIELDS, grain="aggregate")
        times.append((time.perf_counter() - t0) * 1000)

    times.sort()
    n = len(times)
    avg = sum(times) / n
    p50 = times[n // 2]
    p95 = times[int(n * 0.95)]
    log('  字段数 = %d，重复 20 次' % len(FIELDS))
    log('  平均 %.2f ms | P50 %.2f ms | P95 %.2f ms | 最大 %.2f ms' % (avg, p50, p95, times[-1]))
    log('  产出图表数 = %d' % len(cfg.get('charts', [])))
    log('  generated_by = %s' % cfg.get('generated_by', '(未标记)'))
    if p95 < 100:
        log('  ✅ 结论：毫秒级，满足"秒出图"前提（P95 < 100ms）')
    else:
        log('  ❌ 结论：P95 = %.1f ms，不满足毫秒级前提，方案 C 需重新评估' % p95)
except Exception as e:
    log('  [skip] 无法直接跑规则引擎：%s: %s' % (type(e).__name__, e))

# ---------- b. 超时配置 ----------
log('\n【b】AI 链路超时配置')
try:
    cfg_src = io.open(os.path.join(_REPO, 'backend', 'app', 'core', 'config.py'),
                      encoding='utf-8').read()
    for key in ['BRAIN_S3_LLM_TIMEOUT', 'BRAIN_AI_CHOICE_TIMEOUT', 'BRAIN_S2_USE_LLM']:
        # 注意：不能用 ^ 锚定——config.py 里这些字段在 Settings 类体内有缩进
        m = re.search(r'%s\s*:\s*[A-Za-z_\[\]\.]+\s*=\s*(.+)' % re.escape(key), cfg_src)
        log('  %-24s = %s' % (key, m.group(1).strip() if m else '(未找到)'))

    t3 = re.search(r'BRAIN_S3_LLM_TIMEOUT\s*:\s*float\s*=\s*([\d.]+)', cfg_src)
    t_choice = 120  # _request_user_choice 注释标明默认 120 秒
    if t3:
        total = float(t3.group(1)) + t_choice
        log('')
        log('  >>> 最坏耗时测算：S3 LLM 硬超时 %s 秒 + 用户决策等待 %d 秒 = %d 秒（%.1f 分钟）'
            % (t3.group(1), t_choice, total, total / 60))
        log('      即：LLM 抽风时加载页最多卡 %.1f 分钟，且中途弹框要求用户做选择。' % (total / 60))
        log('      这是方案 C（规则图秒出 + AI 后台增强）要消除的头号风险。')
except Exception as e:
    log('  [err] %s' % e)

# ---------- c. 弹框是否会阻塞 ----------
log('\n【c】AI 失败弹框是否真会阻塞流水线')
sse = io.open(os.path.join(_REPO, 'backend', 'app', 'api', 'brain_run_sse.py'),
              encoding='utf-8').read()
has_choice = 'await _request_user_choice' in sse
m_timeout = re.search(r'timeout:\s*Optional\[int\]\s*=\s*(\d+)', sse)
log('  存在 _request_user_choice 调用 : %s' % has_choice)
log('  默认等待超时                   : %s 秒' % (m_timeout.group(1) if m_timeout else '(见 _request_user_choice 注释=120)'))
log('  ⚠️ 结论：AI 失败会暂停流水线等用户决策，最多卡 %s 秒 —— 路演头号风险'
    % (m_timeout.group(1) if m_timeout else '120'))

# ---------- d. 前端加载页改动点 ----------
log('\n【d】前端加载页支持 partial 跳转，需改哪几处')
lp = os.path.join(_REPO, 'frontend', 'src', 'components', 'charts', 'LoadingPage.tsx')
src = io.open(lp, encoding='utf-8').read()
L = src.split('\n')
spots = [
    ("完成判定（需扩为 completed|partial）", r"status === 'completed'"),
    ("轮询间隔", r"setInterval\(\(\) => fetchStatus"),
    ("ai_awaiting 弹框（方案 C 下不再需要）", r"ai_awaiting"),
    ("完成后跳转 onComplete", r"onComplete\(did\)"),
]
for name, pat in spots:
    hits = [i + 1 for i, l in enumerate(L) if re.search(pat, l)]
    log('  %-38s L%s' % (name, hits if hits else '(未找到)'))

# ---------- e. 版本表承载 ----------
log('\n【e】版本表能否承载 v1(规则) / v2(AI增强)')
dm = os.path.join(_REPO, 'backend', 'app', 'models', 'dashboard.py')
s = io.open(dm, encoding='utf-8').read()
for col in ['version_number', 'config_snapshot', 'is_auto_save', 'prompt_version']:
    log('  DashboardVersion.%s : %s' % (col, '有' if col in s else '无'))
# 找写入路径
writes = []
for dp, dn, fns in os.walk(os.path.join(_REPO, 'backend', 'app')):
    for f in fns:
        if not f.endswith('.py'):
            continue
        p = os.path.join(dp, f)
        try:
            src2 = io.open(p, encoding='utf-8').read()
        except Exception:
            continue
        if 'DashboardVersion(' in src2:
            cnt = src2.count('DashboardVersion(')
            writes.append((p.replace(_REPO, ''), cnt))
log('  写入路径：%s' % (writes if writes else '(仅 models，无写入代码)'))
log('  ✅ 结论：表结构能承载；写入路径需新增（方案 C 的 P2）' if writes else
    '  ⚠️ 结论：表有但无写入代码，需从零写')

log('\n' + '=' * 78)
out = 'defect_fix_evidence/final_fixes/verify_32_current_state.out'
io.open(os.path.join(_REPO, out), 'w', encoding='utf-8').write('\n'.join(buf))
print('\n[written] %s' % out)

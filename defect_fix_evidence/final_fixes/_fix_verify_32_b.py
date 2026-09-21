"""修正 verify_32_current_state.py 的【b】段正则，并补最坏耗时测算。幂等。"""
import io
import sys

P = 'defect_fix_evidence/final_fixes/verify_32_current_state.py'
s = io.open(P, encoding='utf-8').read()

OLD = """    for key in ['BRAIN_S3_LLM_TIMEOUT', 'BRAIN_AI_CHOICE_TIMEOUT', 'BRAIN_S2_USE_LLM']:
        m = re.search(r'^%s\\s*:\\s*[^=]+=\\s*(.+)$' % re.escape(key), cfg_src, re.M)
        log('  %-24s = %s' % (key, m.group(1).strip() if m else '(未找到)'))"""

NEW = """    for key in ['BRAIN_S3_LLM_TIMEOUT', 'BRAIN_AI_CHOICE_TIMEOUT', 'BRAIN_S2_USE_LLM']:
        # 注意：不能用 ^ 锚定——config.py 里这些字段在类体内有缩进
        m = re.search(r'%s\\s*:\\s*[A-Za-z_\\.\\[\\]]+\\s*=\\s*(.+)' % re.escape(key), cfg_src)
        log('  %-24s = %s' % (key, m.group(1).strip() if m else '(未找到)'))

    # 最坏耗时测算：S3 LLM 硬超时 + 用户决策等待
    t3 = re.search(r'BRAIN_S3_LLM_TIMEOUT\\s*:\\s*float\\s*=\\s*([\\d.]+)', cfg_src)
    t_choice = 120  # _request_user_choice 注释标明默认 120，可用 BRAIN_AI_CHOICE_TIMEOUT 覆盖
    if t3:
        log('')
        log('  ⚠️ 最坏耗时测算：S3 LLM 硬超时 %s 秒 + 用户决策等待 %d 秒 = **%d 秒（%.1f 分钟）**'
            % (t3.group(1), t_choice, float(t3.group(1)) + t_choice,
               (float(t3.group(1)) + t_choice) / 60))
        log('     即：LLM 抽风时，加载页最多会卡 5 分钟，且中途弹框要求用户做选择。')
        log('     这是方案 C（规则图秒出 + AI 后台增强）要消除的头号风险。')"""

if NEW[:50] in s:
    print('[skip] already applied')
    sys.exit(0)
if s.count(OLD) != 1:
    print('[fail] count=%d' % s.count(OLD))
    sys.exit(1)
s = s.replace(OLD, NEW)
io.open(P, 'w', encoding='utf-8').write(s)
print('[ok] applied')

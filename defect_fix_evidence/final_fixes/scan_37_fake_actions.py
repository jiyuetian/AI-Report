"""3.7 深度补充：全仓「假动作」扫描器 v3（按钮级精准判定）。

v1/v2 的问题：按「包围函数体」判定，命中的多是 .then 回调这种窄体，误报率高。

v3 改为按钮级判据——这也是 3.7 真正的缺陷形态：**用户点了按钮，只弹一句提示，什么都没发生**。

规则（对每处 onClick）：
  R1 处理器体只有一句 message.* 调用（无 await/请求/setState/其他语句）
     且 文案不含「即将上线/未开放/敬请期待/尚未支持」
     → 🔴 假动作：谎报成功/完成，实际无副作用
  R2 处理器体只有一句 message.* 调用，文案含「即将上线」类
     且 按钮未 disabled
     → 🟠 空壳可点：点了只说"即将上线"，应改为 disabled + Tooltip（3.7 已修的删除按钮即此类）
  R3 文案含「即将上线」且按钮已 disabled → ✅ 诚实标注，不算缺陷

输出：defect_fix_evidence/final_fixes/scan_37_fake_actions.out
"""
import io
import os
import re

ROOT = 'frontend/src'
EXTS = ('.tsx', '.ts')

COMING_SOON = re.compile('即将上线|未开放|敬请期待|尚未支持|开发中|暂未')
MSG_CALL = re.compile(r'message\.(success|info|warning|error)\(')


def balanced(src: str, start: int) -> int:
    """src[start] 为 '(' 或 '{'，返回匹配的闭合位置（不含）。"""
    open_ch = src[start]
    close_ch = ')' if open_ch == '(' else '}'
    depth = 0
    i = start
    n = len(src)
    while i < n:
        c = src[i]
        if c in '"\'`':
            q = c
            i += 1
            while i < n and src[i] != q:
                if src[i] == '\\':
                    i += 1
                i += 1
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def extract_handlers(src: str):
    """返回 [(handler_text, abs_start, abs_end)]，handler 为 onClick={...} 的内容。

    注意：必须从 JSX 属性的外层 '{' 开始配对，不能用第一个 '('——
    onClick={() => …} 里 '()' 自身就闭合，会导致只取到空参数表。
    """
    out = []
    for m in re.finditer(r'onClick=\{', src):
        brace = m.end() - 1            # 外层 '{'
        end = balanced(src, brace)      # 匹配的 '}'
        if end >= len(src):
            continue
        handler = src[brace:end + 1]
        out.append((handler, brace, end + 1))
    return out


def handler_is_only_message(handler: str):
    """判定处理器体是否只有一句 message 调用，返回 (bool, msg_text, msg_kind)。"""
    # 去掉箭头参数部分
    arrow = handler.find('=>')
    if arrow < 0:
        return False, '', ''
    body = handler[arrow + 2:].strip()
    if body.startswith('{'):
        inner = body[1:-1].strip() if body.endswith('}') else body
    else:
        inner = body
    # 去掉尾随分号
    inner = inner.strip().rstrip(';').strip()
    # 只允许一句 message.*
    m = MSG_CALL.search(inner)
    if not m:
        return False, '', ''
    # 额外语句判据：出现分号（除末尾）、出现 await/请求/setState
    rest = inner
    if re.search(r'\bawait\b|\bhttp\.|\bapi\.|\bfetch\(|\.post\(|\.get\(', rest):
        return False, '', ''
    if re.search(r'\bset[A-Z]\w*\(', rest):
        return False, '', ''
    # 语句数：按 ; 切分后非空段应只有 1 段（模板串里的 ; 极少，可接受）
    segs = [s for s in re.split(r';(?![^`]*`)', inner) if s.strip()]
    if len(segs) != 1:
        return False, '', ''
    # 取文案
    start = m.end()
    end = balanced(inner, start - 1)
    text = inner[start:end]
    return True, text, m.group(1)


def button_has_disabled(src: str, handler_start: int, handler_end: int) -> bool:
    """在包裹该 onClick 的最近 <Button …> 标签内是否含 disabled。

    注意：不能只在 src[:handler_start] 里找 '>'——标签的闭合 '>' 位于
    属性值之后（onClick={…}>），必须在 handler 结束之后再找。
    """
    i = src.rfind('<Button', 0, handler_start)
    if i < 0:
        return False
    j = src.find('>', handler_end)      # 标签闭合在属性值之后
    if j < 0:
        return False
    tag = src[i:j]
    return bool(re.search(r'\bdisabled\b', tag))


def main():
    red, orange, green = [], [], []
    files = 0
    handlers_total = 0
    for dp, dn, fns in os.walk(ROOT):
        if 'node_modules' in dp or '__tests__' in dp:
            continue
        for fn in fns:
            if not fn.endswith(EXTS):
                continue
            p = os.path.join(dp, fn)
            src = io.open(p, encoding='utf-8').read()
            files += 1
            for text, s, e in extract_handlers(src):
                handlers_total += 1
                ok, msg_text, kind = handler_is_only_message(text)
                if not ok:
                    continue
                line = src[:s].count('\n') + 1
                disabled = button_has_disabled(src, s, e)
                soon = bool(COMING_SOON.search(msg_text))
                rec = (p.replace('\\', '/'), line, kind, msg_text[:80], disabled)
                if soon and disabled:
                    green.append(rec)
                elif soon and not disabled:
                    orange.append(rec)
                elif not soon:
                    red.append(rec)

    buf = []
    buf.append('=== 3.7 全仓假动作扫描 v3（按钮级精准判定）===')
    buf.append('扫描 %s：文件 %d，onClick 处理器 %d 处' % (ROOT, files, handlers_total))
    buf.append('判据：处理器体只有一句 message.* 调用，且无 await/请求/setState')
    buf.append('')

    buf.append('🔴 R1 假动作（点了只弹提示、谎报成功，实际无副作用）：%d 处' % len(red))
    if red:
        for p, line, kind, t, d in sorted(red):
            buf.append('  %s:%d  [%s] %s   (按钮 disabled=%s)' % (p, line, kind, t, d))
    else:
        buf.append('  （无）')
    buf.append('')

    buf.append('🟠 R2 空壳可点（文案说"即将上线"但按钮仍可点，应 disabled+Tooltip）：%d 处' % len(orange))
    if orange:
        for p, line, kind, t, d in sorted(orange):
            buf.append('  %s:%d  [%s] %s' % (p, line, kind, t))
    else:
        buf.append('  （无）')
    buf.append('')

    buf.append('✅ R3 诚实标注（"即将上线"且已 disabled）：%d 处' % len(green))
    for p, line, kind, t, d in sorted(green):
        buf.append('  %s:%d  [%s] %s' % (p, line, kind, t))

    txt = '\n'.join(buf)
    io.open('defect_fix_evidence/final_fixes/scan_37_fake_actions.out', 'w', encoding='utf-8').write(txt)
    print(txt)


SELFTEST_SRC = '''
const A = () => (
  <div>
    {/* 已知假动作：点了只弹"已保存"，无请求无 setState */}
    <Button onClick={() => message.success('已保存')}>保存</Button>
    {/* 已知空壳可点：说即将上线但按钮没禁用 */}
    <Button onClick={() => message.info('对比即将上线')}>对比</Button>
    {/* 已知诚实标注：说即将上线且已禁用 */}
    <Tooltip title="二维码（即将上线）"><Button disabled onClick={() => message.info('二维码即将上线')}>二维码</Button></Tooltip>
    {/* 已知正常：真发请求 */}
    <Button onClick={async () => { await http.post('/save'); message.success('已保存'); }}>真保存</Button>
    {/* 已知正常：真改状态 */}
    <Button onClick={() => { setOpen(false); message.info('已关闭'); }}>关闭</Button>
  </div>
);
'''


def selftest():
    """扫描器自测：对已知分类的样本，验证判定不反。
    没有自测，'0 命中' 与 '扫描器坏了' 无法区分（v1/v2 就栽在这里）。"""
    got = []
    for text, s, e in extract_handlers(SELFTEST_SRC):
        ok, msg_text, kind = handler_is_only_message(text)
        if not ok:
            continue
        disabled = button_has_disabled(SELFTEST_SRC, s, e)
        soon = bool(COMING_SOON.search(msg_text))
        got.append(('R3' if (soon and disabled) else 'R2' if soon else 'R1', msg_text))

    expected = [('R1', "'已保存'"), ('R2', "'对比即将上线'"), ('R3', "'二维码即将上线'")]
    ok = True
    print('=== 扫描器自测（已知样本）===')
    for i, (exp_kind, exp_text) in enumerate(expected):
        actual = got[i] if i < len(got) else None
        good = actual is not None and actual[0] == exp_kind and exp_text in actual[1]
        if not good:
            ok = False
        print('  %s 期望 %s(%s) 实际 %s' % ('PASS' if good else 'FAIL', exp_kind, exp_text, actual))
    extra = got[len(expected):]
    no_extra = not extra
    if not no_extra:
        ok = False
    print('  %s 后两个真实副作用按钮未被误报（实际命中 %d 个，期望 3 个）'
          % ('PASS' if no_extra else 'FAIL', len(got)))
    print('  自测结论：%s\n' % ('PASS —— 扫描器可信' if ok else 'FAIL —— 扫描器不可用'))
    return ok


if __name__ == '__main__':
    st_ok = selftest()
    main()
    print('\n扫描器自测:', 'PASS' if st_ok else 'FAIL')

"""3.7 深度补充：清掉 disabled 按钮上的死 onClick（文案仍是假话术「已删除」）。

扫描器 v3 唯一 R1 命中：DashboardOps.tsx L472
  <Button size="small" type="text" danger disabled onClick={() => message.success('已删除')}>删除</Button>

按钮已 disabled，antd 不会触发 click → 该 onClick 是死代码；
但文案「已删除」仍是谎报（一旦有人去掉 disabled 就复活成假动作）。
最干净的处理：删掉死 onClick，保留 disabled + Tooltip（与「导出」按钮一致）。
"""
import io
import sys

P = 'frontend/src/views/dashboard/DashboardOps.tsx'
s = io.open(P, encoding='utf-8').read()

OLD = (
    '<Button size="small" type="text" danger disabled '
    'onClick={() => message.success(\'已删除\')}>删除</Button>'
)
NEW = (
    '<Button size="small" type="text" danger disabled>删除</Button>'
)

if NEW in s:
    print('[skip] already applied')
elif s.count(OLD) != 1:
    print('[fail] count=%d' % s.count(OLD))
    sys.exit(1)
else:
    s = s.replace(OLD, NEW)
    io.open(P, 'w', encoding='utf-8').write(s)
    print('[ok] applied; len =', len(s))

"""O 方案补充 1.2b：新表建立方式（已核实 alembic + create_all 双机制）。幂等。"""
import io
import sys

P = 'night3/plans/O_ai_participation_monitoring.md'
s = io.open(P, encoding='utf-8').read()

OLD = '**1.3 落库必须'
NEW = (
    '**1.2b 新表怎么建（已核实，消除落地不确定性）**\n\n'
    '| 机制 | 位置 | 说明 |\n'
    '|---|---|---|\n'
    '| Alembic | `backend/alembic/versions/001_init_tables.py` | **只有 1 个迁移**（001），'
    '即 alembic 目前不是高频演进的主路径 |\n'
    '| 启动时建表 | `main.py:122` `await conn.run_sync(Base.metadata.create_all)` | '
    '新增 Model 会在启动时自动建表 |\n'
    '| 初始化脚本 | `init_brain_tables.py:31` 同样 create_all | brain 相关表的初始化 |\n\n'
    '→ **结论**：新增 `llm_calls` 只需 ① 写好 Model ② 启动即自动建表（SQLite 场景）。\n'
    '**建议同步补一个 `002_add_llm_calls.py` 迁移**，原因：让 `alembic upgrade head` 能复现表结构，\n'
    '避免"本地靠 create_all、部署靠 alembic"两套不一致 —— 这类不一致在演示环境最容易翻车。\n\n'
    '**1.3 落库必须'
)

if '1.2b 新表怎么建' in s:
    print('[skip] already applied')
    sys.exit(0)
if s.count(OLD) != 1:
    print('[fail] count=%d' % s.count(OLD))
    sys.exit(1)
s = s.replace(OLD, NEW)
io.open(P, 'w', encoding='utf-8').write(s)
print('[ok] chars =', len(s))

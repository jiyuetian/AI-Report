"""
P0-1 唯一度防误伤 实机自测
验证：形似主键的 1:N 业务列（客户ID/订单编号）不再被误 BLOCKING（降级 WARNING）；
      真正的唯一键重复（序号）仍 BLOCKING。
"""
import sqlite3
import sys

sys.path.insert(0, r'C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend')
from app.core.quality_checker import QualityChecker, IssueSeverity

conn = sqlite3.connect(':memory:')
cur = conn.cursor()
cur.execute('CREATE TABLE t_uniq ("客户ID" TEXT, "借据编号" TEXT, "订单编号" TEXT, "序号" TEXT)')

# 前 4 行：客户ID(A,A,B,B) / 借据编号(j1-j4 全唯一) / 订单编号(o1,o1,o2,o3) / 序号(s1-s4)
rows = [
    ('A', 'j1', 'o1', 's1'),
    ('A', 'j2', 'o1', 's2'),
    ('B', 'j3', 'o2', 's3'),
    ('B', 'j4', 'o3', 's4'),
]
cur.executemany('INSERT INTO t_uniq VALUES (?,?,?,?)', rows)
# 序号列补到 20 行：s5..s19 各一次（唯一部分），再插入一个 s1 制造真主键重复
for i in range(5, 20):
    cur.execute('INSERT INTO t_uniq ("序号") VALUES (?)', ('s%d' % i,))
cur.execute('INSERT INTO t_uniq ("序号") VALUES (?)', ('s1',))  # s1 重复 → 真主键重复场景


class DB:
    pass


db = DB()
db.conn = conn
chk = QualityChecker(db)
cols = [{'name': '客户ID'}, {'name': '借据编号'}, {'name': '订单编号'}, {'name': '序号'}]
issues = chk._check_unique('t_uniq', cols)

result = {}
for i in issues:
    result.setdefault(i.column, []).append(i.severity.value)
print('质检结果:', result)

# 断言
assert result.get('客户ID') == ['warning'], f"客户ID 应 WARNING，实际 {result.get('客户ID')}"
assert result.get('订单编号') == ['warning'], f"订单编号 应 WARNING，实际 {result.get('订单编号')}"
assert 'blocking' not in result.get('客户ID', []) and 'blocking' not in result.get('订单编号', []), \
    "1:N 业务列不应 BLOCKING（误伤未消除）"
assert result.get('序号') == ['blocking'], f"序号(真主键重复) 应 BLOCKING，实际 {result.get('序号')}"
assert '借据编号' not in result, f"借据编号(唯一无重复) 应无 issue，实际 {result.get('借据编号')}"

print('P0-1 唯一度防误伤：PASS ✅  1:N 业务列(客户ID/订单编号)降级 WARNING 不再误 BLOCKING；真主键重复(序号)仍 BLOCKING')

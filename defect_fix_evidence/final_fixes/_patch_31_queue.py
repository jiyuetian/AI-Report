"""3.1 深度补充：上传队列收缩（一次性补丁脚本，可重入）。

背景：上一版只收缩了 Dragger，但「上传队列」Card 仍无条件渲染 N 行 List，
N=10 时约 600px+，首屏照样被占 → 3.1「不占第一屏」未真正达标。

方案：队列全部结束（无 uploading/error）后收缩为一行；只要还有进行中/失败项就保持展开。
"""
import io
import sys

P = 'frontend/src/views/upload/UploadPage.tsx'
s = io.open(P, encoding='utf-8').read()
orig = s

# ---------- 1) 派生队列收缩状态 ----------
ANCHOR_A = '  const shouldCollapse = doneFiles.length > 0 && !uploadExpanded\n'
NEW_A = (
    ANCHOR_A
    + '\n'
    + '  // 3.1 深度补充：上传队列是 N 行列表，N 大时同样撑满首屏 → 全部结束后一并收缩成一行。\n'
    + '  // 边界：只要还有 uploading / error 项就必须保持展开（用户要看进度条与重试按钮）。\n'
    + '  const activeQueueItems = fileList.filter(\n'
    + '    f => f.status === \'uploading\' || f.status === \'error\'\n'
    + '  )\n'
    + '  const queueCollapsed =\n'
    + '    fileList.length > 0 && activeQueueItems.length === 0 && !queueExpanded\n'
)
OLD_A = ANCHOR_A
if 'const queueCollapsed' in s:
    print('[skip] step1 already applied')
elif s.count(OLD_A) != 1:
    print('[fail] OLD_A count =', s.count(OLD_A))
    sys.exit(1)
else:
    s = s.replace(OLD_A, NEW_A)
    print('[ok] step1 applied')

# ---------- 2) 队列区块改为条件渲染 ----------
OLD_B = """      {/* 上传列表 */}
      {fileList.length > 0 && (
        <Card title="上传队列" className="upload-list-card" style={{ marginTop: 24 }}>
          <List"""
NEW_B = """      {/* 上传列表：全部结束后收缩为一行，避免 N 份文件撑满首屏（3.1 深度补充） */}
      {fileList.length > 0 && queueCollapsed && (
        <div className="upload-collapsed-bar" style={{ marginTop: 24 }}>
          <span className="upload-collapsed-text">
            上传队列 · {fileList.length} 份文件，全部完成
          </span>
          <Button
            type="link"
            size="small"
            icon={<DownOutlined />}
            onClick={() => setQueueExpanded(true)}
          >
            展开队列
          </Button>
        </div>
      )}
      {fileList.length > 0 && !queueCollapsed && (
        <Card
          title="上传队列"
          className="upload-list-card"
          style={{ marginTop: 24 }}
          extra={
            activeQueueItems.length === 0 ? (
              <Button
                type="link"
                size="small"
                icon={<UpOutlined />}
                onClick={() => setQueueExpanded(false)}
              >
                收起
              </Button>
            ) : null
          }
        >
          <List"""
if 'queueCollapsed && (' in s:
    print('[skip] step2 already applied')
elif s.count(OLD_B) != 1:
    print('[fail] OLD_B count =', s.count(OLD_B))
    sys.exit(1)
else:
    s = s.replace(OLD_B, NEW_B)
    print('[ok] step2 applied')

# ---------- 3) 原队列 Card 的收尾：补一层闭合 ----------
# 原结构：{fileList.length > 0 && ( <Card> <List .../> </Card> )}
# 现在多了一层条件，需在原 </Card> 后额外闭合新增的 &&( 片段
OLD_C = """          />
        </Card>
      )}

      {/* 重复文件弹窗 - 三选 */}"""
NEW_C = """          />
        </Card>
      )}

      {/* 重复文件弹窗 - 三选 */}"""
# 该段结构本身不变（两个并列条件各自闭合），无需改动；仅做存在性校验
if s.count(OLD_C) != 1:
    print('[warn] OLD_C count =', s.count(OLD_C))

io.open(P, 'w', encoding='utf-8').write(s)
print('OK changed =', s != orig, 'len =', len(s))

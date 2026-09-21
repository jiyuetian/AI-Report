/**
 * 3.1 深度补充：上传队列收缩判定 —— 反例测试（与 UploadPage.tsx 中的派生逻辑等价）
 *
 * 生产代码：
 *   const activeQueueItems = fileList.filter(f => f.status === 'uploading' || f.status === 'error')
 *   const queueCollapsed = fileList.length > 0 && activeQueueItems.length === 0 && !queueExpanded
 *
 * 判定语义：
 *   collapsed === true  → 只渲染一行「上传队列 · N 份文件，全部完成」（不占首屏）
 *   collapsed === false → 渲染完整队列（用户能看到进度条 / 重试按钮）
 */
function queueCollapsed(fileList, queueExpanded) {
  const activeQueueItems = fileList.filter(
    f => f.status === 'uploading' || f.status === 'error'
  );
  return fileList.length > 0 && activeQueueItems.length === 0 && !queueExpanded;
}

const F = (n, status) => Array.from({ length: n }, (_, i) => ({ uid: `${status}-${i}`, status }));

let fails = 0;
function check(name, actual, expected, note) {
  const ok = actual === expected;
  if (!ok) fails++;
  console.log(
    `${ok ? 'PASS' : 'FAIL'}  ${name}\n      collapsed=${actual} (期望 ${expected})${note ? '  ' + note : ''}`
  );
}

console.log('=== 3.1 上传队列收缩 · 反例测试 ===\n');

// 用例1：0 文件 —— 不该渲染任何队列（collapsed 为 false，靠 fileList.length>0 挡住渲染）
check('用例1 空队列(0 文件)', queueCollapsed([], false), false, '无文件，整块不渲染');

// 用例2：3 份全部完成 → 应收缩
check('用例2 全部完成(3 done)', queueCollapsed(F(3, 'done'), false), true, '全部结束，收缩为一行');

// 用例3：N=10 全部完成 → 应收缩（这才是不占首屏的关键场景）
check('用例3 全部完成(10 done)', queueCollapsed(F(10, 'done'), false), true, '10 行 ≈640px → 48px');

// 用例4（反例·关键）：还有 uploading → 必须保持展开，否则用户看不到进度条
check(
  '用例4 有上传中(2 done + 1 uploading)',
  queueCollapsed([...F(2, 'done'), ...F(1, 'uploading')], false),
  false,
  '必须展开：用户要看进度条与「取消」'
);

// 用例5（反例·关键）：有 error → 必须保持展开，否则「重试」按钮被藏起来 = 功能丢失
check(
  '用例5 有失败项(2 done + 1 error)',
  queueCollapsed([...F(2, 'done'), ...F(1, 'error')], false),
  false,
  '必须展开：否则「重试」不可达'
);

// 用例6：用户主动展开 → 保持展开
check('用例6 用户点「展开队列」', queueCollapsed(F(3, 'done'), true), false, 'queueExpanded=true 优先');

// 用例7（回归）：用户展开后又点「收起」→ 回到收缩
check('用例7 用户点「收起」', queueCollapsed(F(3, 'done'), false), true, '可来回切换');

// 用例8（边界）：只有 1 份且已完成 → 仍收缩（一致性，不做特例）
check('用例8 仅 1 份完成', queueCollapsed(F(1, 'done'), false), true, '不做特例，行为一致');

// 用例9（边界）：全部失败 → 保持展开
check('用例9 全部失败(3 error)', queueCollapsed(F(3, 'error'), false), false, '必须展开：全部需要重试');

console.log('\n=== 首屏高度收益估算（List.Item 约 64px/行，Card padding 约 24px） ===');
for (const n of [1, 3, 5, 10, 20]) {
  const expanded = n * 64 + 24 + 56; // 行 + padding + Card 标题栏
  const collapsed = 48; // 一行收缩条
  console.log(`  N=${String(n).padStart(2)}  展开≈${String(expanded).padStart(4)}px  收缩=${collapsed}px  节省≈${expanded - collapsed}px`);
}

console.log('\nRESULT:', fails === 0 ? 'ALL PASS' : `${fails} FAILED`);
process.exit(fails === 0 ? 0 : 1);

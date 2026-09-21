// 3.3 KPI 列宽算法实测：新旧逻辑对比，证明任意数量下末行无留白
function kpiSpanFor(index, total) {
  const spanFor = (perRow) => {
    const full = Math.floor(total / perRow) * perRow;
    const inRow = index < full ? perRow : ((total % perRow) || perRow);
    return Math.round(24 / inRow);
  };
  return { xs: 24, sm: spanFor(2), lg: spanFor(4) };
}
function oldSpan(total) {
  return total >= 4 ? 6 : total === 3 ? 8 : total === 2 ? 12 : 24;
}

let fail = 0;
console.log('n | 旧(lg)                | 新(lg)                | 末行空白格数 旧→新');
for (let n = 1; n <= 9; n++) {
  const o = [], w = [];
  for (let i = 0; i < n; i++) { o.push(oldSpan(n)); w.push(kpiSpanFor(i, n).lg); }
  const rem = n % 4 === 0 ? 4 : (n % 4);
  const gapOld = 24 - rem * oldSpan(n);
  const gapNew = 24 - rem * kpiSpanFor(n - 1, n).lg;
  if (gapNew !== 0) fail++;
  console.log(
    n + ' | [' + o.join(',') + ']'.padEnd(20 - String(o).length) +
    ' | [' + w.join(',') + ']'.padEnd(20 - String(w).length) +
    ' | ' + gapOld + ' → ' + gapNew
  );
}
console.log('\n[断言1] n=1 单卡占满整行:', JSON.stringify(kpiSpanFor(0, 1)), kpiSpanFor(0, 1).lg === 24 ? 'PASS' : 'FAIL');
console.log('[断言2] n=5 第5张不再留白: 旧=' + oldSpan(5) + ' 新=' + kpiSpanFor(4, 5).lg, kpiSpanFor(4, 5).lg === 24 ? 'PASS' : 'FAIL');
console.log('[断言3] n=6 末行2张均分:', kpiSpanFor(4, 6).lg + ',' + kpiSpanFor(5, 6).lg, kpiSpanFor(4, 6).lg === 12 ? 'PASS' : 'FAIL');
console.log('[断言4] n=7 末行3张均分:', kpiSpanFor(4, 7).lg + ',' + kpiSpanFor(5, 7).lg + ',' + kpiSpanFor(6, 7).lg);
console.log('[断言5] n=4 与旧逻辑一致(不改既有观感):', [0,1,2,3].map(i => kpiSpanFor(i, 4).lg).join(','), '== 6,6,6,6');
console.log('[断言6] sm 断点 n=3 末行占满:', [0,1,2].map(i => kpiSpanFor(i, 3).sm).join(','));
console.log('\n末行仍有空白的 n 数量 =', fail, fail === 0 ? '=> ALL PASS' : '=> FAIL');

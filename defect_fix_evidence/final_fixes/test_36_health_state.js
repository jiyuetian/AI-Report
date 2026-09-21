/**
 * 3.6 深度补充：LLM 网关状态机 —— 反例测试
 * 与 AdminPage.tsx SettingsTab 中的取值/状态逻辑等价。
 */

/** 新逻辑：兼容布尔 / 数值 / 字符串三种序列化形态 */
function parseReachable(raw) {
  return raw === true || raw === 1 || raw === 'true' || raw === '1'
    ? true
    : raw === false || raw === 0 || raw === 'false' || raw === '0'
      ? false
      : null;
}

/** 旧逻辑（修复前）：只认严格布尔 */
function oldParseReachable(raw) {
  return typeof raw === 'boolean' ? raw : null;
}

/** 展示态：四态（loading 优先） */
function display(loading, reachable) {
  if (loading) return '正在检测…';
  if (reachable === true) return '已启用（实时检测可达）';
  if (reachable === false) return '当前不可达（将自动降级为规则生成）';
  return '状态未知（健康检查未返回该字段）';
}

let fails = 0;
function eq(name, actual, expected) {
  const ok = actual === expected;
  if (!ok) fails++;
  console.log(
    `${ok ? 'PASS' : 'FAIL'}  ${name}  → ${JSON.stringify(actual)}${ok ? '' : ' (期望 ' + JSON.stringify(expected) + ')'}`
  );
}

console.log('=== A. llm_reachable 取值形态（旧逻辑会误报）===\n');
const cases = [
  ['布尔 true', true, true],
  ['布尔 false', false, false],
  ['数值 1', 1, true],
  ['数值 0', 0, false],
  ['字符串 "true"', 'true', true],
  ['字符串 "false"', 'false', false],
  ['字符串 "1"', '1', true],
  ['字符串 "0"', '0', false],
  ['undefined（接口无此字段）', undefined, null],
  ['null', null, null],
  ['字符串 "yes"（无法判定→未知，不得谎报）', 'yes', null],
  ['字符串 ""（无法判定→未知）', '', null],
];
for (const [name, raw, expected] of cases) {
  eq(`A·${name}`, parseReachable(raw), expected);
}

console.log('\n=== B. 旧逻辑对照：哪些形态会被误报为"未知" ===\n');
let misreported = 0;
for (const [name, raw, expected] of cases) {
  const oldV = oldParseReachable(raw);
  const newV = parseReachable(raw);
  if (oldV !== newV) {
    misreported++;
    console.log(
      `  差异  ${name}: 旧=${JSON.stringify(oldV)} 新=${JSON.stringify(newV)}` +
        `  → 旧逻辑把「${newV === true ? '可达' : newV === false ? '不可达' : '未知'}」显示成「未知」`
    );
  }
}
eq('B1 至少 6 种形态被旧逻辑误报', misreported >= 6, true);
console.log(`  （本次共 ${misreported} 种形态判定不同）`);

console.log('\n=== C. 四态展示（关键反例：loading ≠ unknown）===\n');
eq('C1 首屏（请求在飞）', display(true, null), '正在检测…');
eq('C2 检测完成但接口无该字段', display(false, null), '状态未知（健康检查未返回该字段）');
eq('C3 可达', display(false, true), '已启用（实时检测可达）');
eq('C4 不可达', display(false, false), '当前不可达（将自动降级为规则生成）');

// 核心反例断言：loading 与 unknown 必须是两种不同文案
const loadingText = display(true, null);
const unknownText = display(false, null);
eq('C5 loading 文案 ≠ unknown 文案（旧版两者相同=失真）', loadingText !== unknownText, true);

console.log('\n=== D. 旧三态下的失真复现 ===\n');
// 旧实现：llmReachable 初始 null → 直接显示"状态未知（健康检查未返回）"
const oldDisplay = reachable =>
  reachable === true ? '已启用（实时检测可达）'
  : reachable === false ? '当前不可达（将自动降级为规则生成）'
  : '状态未知（健康检查未返回）';
console.log(`  旧版首屏（请求在飞，state=null）→ "${oldDisplay(null)}"`);
console.log(`  新版首屏（请求在飞，loading=true）→ "${display(true, null)}"`);
eq('D1 旧版把"正在检测"说成"接口没返回"', oldDisplay(null).includes('未返回'), true);
eq('D2 新版不再这么说', display(true, null).includes('未返回'), false);

console.log('\n=== E. 状态迁移（挂载 → 成功 / 失败 → 手动复检）===\n');
function step(fromLoading, fromReachable, event) {
  if (event === 'start') return [true, fromReachable];
  if (event === 'ok-true') return [false, true];
  if (event === 'ok-false') return [false, false];
  if (event === 'ok-nofield') return [false, null];
  if (event === 'error') return [false, null];
  return [fromLoading, fromReachable];
}
let st = [true, null];
eq('E1 挂载即 loading', display(...st), '正在检测…');
st = step(...st, 'ok-false');
eq('E2 后端不可达', display(...st), '当前不可达（将自动降级为规则生成）');
st = step(...st, 'start'); // 点「重新检测」
eq('E3 点重新检测 → 回到检测中', display(...st), '正在检测…');
st = step(...st, 'ok-true'); // 后端已修复
eq('E4 复检后恢复可达（旧版不会自愈）', display(...st), '已启用（实时检测可达）');
st = step(...st, 'error');
eq('E5 网络异常 → 未知而非谎报', display(...st), '状态未知（健康检查未返回该字段）');

console.log('\nRESULT:', fails === 0 ? 'ALL PASS' : `${fails} FAILED`);
process.exit(fails === 0 ? 0 : 1);

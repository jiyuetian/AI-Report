module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
    '@typescript-eslint/no-explicit-any': 'off',
    // 【P0 鉴权回归护栏】禁止裸 fetch：
    // 后端鉴权改造后 POST /files、POST /datasets、POST /brain/run、
    // GET /brain/run/{id}/status、GET /files/{id}/preview、DELETE /datasets/{id}、
    // /dashboards/by-dataset/*、select-sheet、select-encoding、cancel、resume
    // 强制要求 Authorization。裸 fetch 绕过 request() 封装 → 登录态下必 401。
    // 例外（必须逐处加 eslint-disable 注释说明原因）：
    //  1) src/utils/request.ts 内的标准封装本身；
    //  2) 命中没有强制鉴权的端点（/quality/*、/chat/*、/skills、/tokens/status、/auth/*、/reports），
    //     这些端点不得带 token，否则过期 token 会把原本可用的接口打挂。
    'no-restricted-globals': [
      'error',
      {
        name: 'fetch',
        message:
          '禁止使用裸 fetch。强制鉴权端点请改用 src/utils/request.ts 的 request()/http；确需裸 fetch 时须显式带 authHeaders()（强制鉴权端点）或不带 token（非鉴权端点），并在本行加 // eslint-disable-next-line no-restricted-globals 注释说明原因。',
      },
    ],
    // 【护栏补强 1】no-restricted-globals 只拦全局标识符 fetch，漏掉
    // window.fetch / globalThis.fetch / self.fetch（成员访问形式）。@typescript-eslint/no-restricted-properties
    // 在当前依赖版本不可用（"Definition for rule not found"），改用核心规则 no-restricted-syntax + AST 选择器覆盖。
    // 【护栏补强 1.1】点访问（window.fetch）仍漏 computed member 形式（window['fetch'] / window["fetch"]），
    // 其 AST 为 MemberExpression[computed=true][property.type="Literal"]，点访问选择器 property.name 不匹配。
    // 2026-09-19 经探针实测确认 window['fetch'] 原护栏 EXIT=0（漏拦），补 computed-member 选择器闭环。
    'no-restricted-syntax': [
      'error',
      {
        selector: 'MemberExpression[object.name="window"][property.name="fetch"]',
        message: '禁止 window.fetch，统一走 src/utils/request.ts 的 request()/http',
      },
      {
        selector: 'MemberExpression[object.name="globalThis"][property.name="fetch"]',
        message: '禁止 globalThis.fetch，统一走 request()/http',
      },
      {
        selector: 'MemberExpression[object.name="self"][property.name="fetch"]',
        message: '禁止 self.fetch，统一走 request()/http',
      },
      {
        selector: 'MemberExpression[object.name=/^(window|globalThis|self)$/][computed=true][property.type="Literal"][property.value="fetch"]',
        message: '禁止 window/globalThis/self 的 computed fetch 访问（如 window["fetch"]），统一走 request()/http',
      },
    ],
    // 【护栏补强 2】axios 是绕开 request() 封装、不注入 token 的“第二客户端”
    // （ReportPage 曾用其调 /reports，后端一旦加鉴权即 401）。禁止业务文件裸 import axios，统一走 http 封装。
    'no-restricted-imports': [
      'error',
      {
        paths: [
          { name: 'axios', message: '禁止裸 axios，统一走 src/utils/request.ts 的 http 封装（自动注入 token）' },
        ],
      },
    ],
  },
}
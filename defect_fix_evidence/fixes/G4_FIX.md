# G4 修复记录：报告页 XSS（后端落库前净化 + 前端 sandbox 双重防护）

## 根因
报告 HTML 由**数据派生内容**拼装：`report_generator._render_html()` 把列名/字段名/采样值/LLM 文本直接嵌入章节 HTML（含内联 ECharts 占位 `<div class="echarts-chart" data-option="...">`），然后 `reports.py` 写入 `data/reports/{id}.html` 文件，经 `GET /api/v1/reports/{id}/html` 原样返回，前端 `ReportPage.tsx` 用 `<iframe srcDoc={html}>` 渲染。

- 旧代码 `_md_to_html` 对 markdown 内容不做 HTML 转义；且 `_render_html` 对含 `<` 的章节走**原样透传**，导致恶意列名（如 `<img src=x onerror=alert(1)>`）、LLM 注入的 `<script>` 直接进入报告。
- 另发现 `<title>{self.theme}</title>`（theme=dashboard.name）**未转义**，看板名含 `<script>` 也会注入。

## 修复（改动仅限 G4 范围：report_generator.py）
1. 新增 `sanitize_report_fragment(html)`：基于 **bleach 6.4.0** 白名单净化。
   - 允许标签：`p/br/h1-6/ul/ol/li/blockquote/strong/em/code/pre/table/thead/tbody/tr/th/td/div/span/section/img/small/hr/sub/sup/a`
   - 允许属性：`class/id/data-option`（全局）；`a`→href/title/target/rel；`img`→src/alt/width/height；其余仅 `class`
   - 允许协议：`http/https/mailto`
   - `strip=True`：剥离 `script/iframe/object/embed/on*` 事件/`javascript:` 协议/注释，保留其文本
   - **不使用** `style` 属性（避免 CSS 注入；报告主样式在受信任的 `<style>` 块内）
2. 在 `_render_html` 章节循环中，对 `content_html` 调用 `sanitize_report_fragment`（落库前净化；ECharts init `<script>` 在循环后单独追加，不受影响，图表照常渲染）。
3. `<title>` 中的 `self.theme` 改为 `html.escape(self.theme)`。

## 依赖
- `bleach==6.4.0` 已安装到后端运行 venv（`C:/Users/Asus009/.workbuddy/binaries/python/envs/default`）。
- 项目无 `requirements.txt`，部署侧需将 `bleach` 加入后端依赖清单（否则报告生成端点会因 import 失败而 500）。已在 FIX_SUMMARY 标注。

## 前端（防御纵深，无需改码）
- `ReportPage.tsx:187` 已使用 `sandbox="allow-same-origin"`（**不含 `allow-scripts`**），iframe 内一切脚本（含 onerror/onload/javascript:）均不执行——这是强二线防护。
- 未引入 DOMPurify：会额外 strip 不执行的 ECharts `<script>` 且需新增 npm 依赖；服务端净化 + sandbox 已彻底闭合 XSS，故不画蛇添足。

## 验证（`g4_verify.py`，22/22 PASS）
- 单元 `sanitize_report_fragment`：9 类 payload（script / img onerror / svg onload / a javascript: / iframe / div style url / object / p onclick / 注释）全部失去可执行结构、纯文本保留；5 类安全片段（p+strong / echarts data-option / table / https a / ul）结构保留。
- `_render_html` 整篇：章节 img onerror 消失、章节 `<script>` 消失、无 iframe、无 javascript:、ECharts 占位保留、正常文本保留、markdown 列表保留、主题名 `<script>` 被转义为 `&lt;script&gt;`。
- 应用导入冒烟：`import app.main` 成功（`APP_IMPORT_OK`）。

## 结论
P0-G4 闭合：报告内容在落库前被白名单净化，且前端 iframe 无脚本执行权限，攻击者无法通过数据/看板名注入可执行脚本。

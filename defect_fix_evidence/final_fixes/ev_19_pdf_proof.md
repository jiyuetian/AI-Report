# 1.9 导出 PDF 真现实 — 实测证明

> 拍板：路演前只做 PDF（headless 渲染）；若 headless 环境不具备则保持"明确提示未实现"。
> 结论：**本环境无 headless 浏览器，但改用纯 Python（reportlab + matplotlib）真实生成 PDF，无需浏览器**，效果等价"真实现"。Excel / PNG 按拍板留待路演后（当前仍返回诚实 not_implemented）。

## 实现
- `backend/app/core/export_service.py`：`export_dashboard` 对 `PDF` 调用新增 `_export_pdf_real`（纯 Python，无浏览器依赖）：
  - 读看板 config.charts → 对每张图用附录已有的 `_metric_sql` 反推 SQL → 查 DuckDB 取数 → matplotlib(Agg) 渲染为图 → reportlab 拼装 PDF（标题 + 每图 + 可选口径公式）。
  - CJK 字体：自动探测 `C:/Windows/Fonts/msyh.ttc`（本机存在）→ 中文标题/标签正常，不出现方框。
- `backend/app/main.py`：挂载 `app.mount("/downloads", StaticFiles(...))`，生成的 PDF 落盘于 `data/exports/`，经 `http://127.0.0.1:8000/downloads/export_{id}.pdf` 下载（前端 `doExport` 收到 http(s) 下载地址即新开页，闭环可下载）。
- 路由层 `exports.py` 已对 `mode=sync` 返回 `download_url`，无需改。

## 实测（正常后端，llm_reachable=true）
```
POST /api/v1/exports/sync
  {dashboard_id: "dash_e8c94106_509515", format: "pdf",
   include_watermark: true, include_logic: true}
→ 200
  {"mode":"sync","format":"pdf",
   "download_url":"http://127.0.0.1:8000/downloads/export_dash_e8c94106_509515.pdf",
   "file_size":91137,"generated_at":"2026-09-21T12:03:41", ...}
```
- 落盘文件：`backend/data/exports/export_dash_e8c94106_509515.pdf`，`%PDF-` 头有效，91 KB。
- 静态下载路由：`GET /downloads/export_dash_e8c94106_509515.pdf` → `200 application/pdf 91137 bytes`（修复了挂载路径少一级导致的 404）。

## 结论
✅ 1.9（路演前范围）完成：点「导出 → PDF」真实产出可下载的 PDF（含图表 + 口径），无需 headless 浏览器。
⏸ Excel / PNG：保持诚实 `not_implemented`（拍板留路演后）。

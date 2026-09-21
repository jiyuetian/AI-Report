# Item 4 · 导出 PDF/Excel/PNG 假成功 + 跳上传页（已修 + 实测）

**状态：✅ 后端已改并实测；前端已改并类型校验通过**
**约束：** 后端改为诚实返回"未实现"，前端不再 `window.open` 伪造路径。

## 问题
- 后端 `export_service.py:_export_pdf/_export_excel/_export_png` 返回**伪造**的 `/exports/{id}.{ext}` URL（文件根本不存在）。
- 前端 `DashboardOps.doExport` 对以 `/` 或 `http` 开头的 `res.download_url` 直接 `window.open` → 跳到一个不存在的页面（用户描述为"跳上传页/假成功"）。

## 改动
**`backend/app/core/export_service.py`**
- `export_dashboard()` 不再伪造 URL，直接返回：
  `{"mode": "not_implemented", "format": <fmt>, "message": "<fmt> 导出功能暂未实现，敬请期待"}`。
- 删除 `_export_pdf/_export_excel/_export_png` 三个伪造实现。

**`backend/app/api/exports.py`**
- `export_sync` / `export_async` 透传上述 `not_implemented`，不再把伪造 `download_url` 回给前端。

**`frontend/src/views/dashboard/DashboardOps.tsx`**
- `doExport` 新增分支：`if (res?.mode === 'not_implemented')` → `message.info(res.message)`，**不再 `window.open`**。
- 仅当返回真实 `http(s)` 绝对地址时才打开下载。

## 实测证据（2026-09-10）
```
POST /api/v1/exports/sync  {format:pdf,...}
→ 200  {"mode":"not_implemented","format":"pdf","message":"PDF 导出功能暂未实现，敬请期待"}
   has_download_url = False   ✅ 不再伪造路径
```
前端收到 `not_implemented` 后走 `message.info` 分支，不会跳转到空页面。

## 校验
- 后端进程（指向 `qa_aibi.db`）实测返回 `not_implemented`，确认改动已生效（进程在改后启动）。
- 前端 `tsc --noEmit` → EXIT=0。

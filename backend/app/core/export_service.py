"""
导出服务 - M4-05a/b
PDF/Excel/PNG 同步导出 + 水印
异步导出（>5s转异步，通知+7天有效）
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from enum import Enum
import uuid

from sqlalchemy.ext.asyncio import AsyncSession


class ExportFormat(Enum):
    PDF = "pdf"
    EXCEL = "excel"
    PNG = "png"


from urllib.parse import quote

class ExportService:
    """导出服务"""
    
    SYNC_TIMEOUT = 5  # 5秒超时转异步
    ASYNC_EXPIRES_DAYS = 7  # 异步导出7天有效
    
    @staticmethod
    async def export_dashboard(
        db: AsyncSession,
        dashboard_id: str,
        format: ExportFormat,
        include_watermark: bool = True,
        include_logic: bool = False,
        user_id: str = "anonymous",
    ) -> Dict[str, Any]:
        """
        导出看板。
        - PDF：1.9 路演前实现——纯 Python（reportlab + matplotlib）真实生成，无需 headless 浏览器。
        - Excel / PNG：路演后实现（拍板 1.9），当前诚实返回 not_implemented。
        - JSON 由路由层独立处理，不经此方法。
        """
        if format == ExportFormat.PDF:
            return await ExportService._export_pdf_real(
                db, dashboard_id, include_watermark, include_logic
            )
        return {
            "mode": "not_implemented",
            "format": format.value,
            "message": f"{format.value.upper()} 导出功能暂未实现，敬请期待（路演后上线）",
        }

    @staticmethod
    async def _export_pdf_real(
        db: AsyncSession,
        dashboard_id: str,
        include_watermark: bool,
        include_logic: bool,
    ) -> Dict[str, Any]:
        """真实生成 PDF：看板标题 + 每张图表的 matplotlib 渲染 + 口径公式。
        纯 Python（reportlab + matplotlib），不依赖 headless 浏览器。"""
        import io, os, json
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from sqlalchemy import select
        from app.models.dashboard import Dashboard
        from app.core.duckdb_manager import get_duckdb
        from app.core.appendix_service import _pick_table, _metric_sql, _ChartDS, _metric_formula

        # CJK 字体：避免中文标题/标签显示为方框
        _cjk = None
        for _p in (r"C:/Windows/Fonts/msyh.ttc", r"C:/Windows/Fonts/simhei.ttf",
                   r"C:/Windows/Fonts/msyhbd.ttc"):
            if os.path.exists(_p):
                _cjk = _p
                break
        if _cjk:
            font_manager.fontManager.addfont(_cjk)
            plt.rcParams["font.sans-serif"] = [font_manager.FontProperties(fname=_cjk).get_name()]
        plt.rcParams["axes.unicode_minus"] = False

        dash = (await db.execute(select(Dashboard).where(Dashboard.id == dashboard_id))).scalar_one_or_none()
        if not dash:
            return {"mode": "not_implemented", "format": "pdf", "message": "看板不存在，无法导出 PDF"}
        cfg = dash.config or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        charts = (cfg.get("charts") or []) if isinstance(cfg, dict) else []

        duck = get_duckdb()
        ds_ids = list(dash.dataset_ids or [])
        if dash.primary_dataset_id and dash.primary_dataset_id not in ds_ids:
            ds_ids.insert(0, dash.primary_dataset_id)
        table = None
        for dsid in ds_ids:
            t = _pick_table(duck, _ChartDS(dsid))
            if t:
                table = t
                break
        if not table:
            return {"mode": "not_implemented", "format": "pdf",
                    "message": "未找到看板关联的数据表，无法导出 PDF"}

        _BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        export_dir = os.path.join(_BACKEND_ROOT, "data", "exports")
        os.makedirs(export_dir, exist_ok=True)
        out_path = os.path.join(export_dir, f"export_{dashboard_id}.pdf")

        styles = getSampleStyleSheet()
        story = []
        story.append(Paragraph(f"看板导出：{dash.name}", styles["Title"]))
        story.append(Paragraph(
            f"生成时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}　数据表：{table}",
            styles["Normal"]))
        story.append(Spacer(1, 0.3 * cm))

        rendered = 0
        for i, c in enumerate(charts[:12]):
            title = c.get("title") or f"图表 {i + 1}"
            chart_type = (c.get("chart_type") or c.get("type") or "bar")
            x = c.get("x_field") or c.get("category_field") or ""
            y = c.get("y_field") or c.get("value_field") or ""
            cfg_c = c.get("config") or {}
            if not isinstance(cfg_c, dict):
                cfg_c = {}
            agg = (cfg_c.get("aggregation") or cfg_c.get("aggregate") or c.get("aggregate") or "COUNT").upper()
            sql = _metric_sql({"type": chart_type, "x_field": x, "y_field": y, "aggregate": agg}, table)
            rows = []
            if sql:
                try:
                    rows = duck.conn.execute(sql).fetchall()
                except Exception:
                    rows = []
            story.append(Paragraph(title, styles["Heading3"]))
            if chart_type == "kpi" or not x:
                val = rows[0][0] if rows else "-"
                story.append(Paragraph(f"<b>{val}</b>", ParagraphStyle(
                    "kpi", parent=styles["Normal"], fontSize=22, textColor=colors.HexColor("#1677ff"))))
            elif rows:
                labels = [str(r[0]) for r in rows][:20]
                vals = [float(r[1]) if r[1] is not None else 0.0 for r in rows][:20]
                fig, ax = plt.subplots(figsize=(7, 3.2))
                if chart_type in ("pie",):
                    ax.pie(vals, labels=labels, autopct="%1.1f%%")
                elif chart_type in ("line", "trend"):
                    ax.plot(labels, vals)
                else:
                    ax.bar(labels, vals)
                ax.set_title(title)
                ax.tick_params(axis="x", labelrotation=45, labelsize=8)
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format="png", dpi=120)
                plt.close(fig)
                buf.seek(0)
                story.append(Image(buf, width=16 * cm, height=7.3 * cm))
            else:
                story.append(Paragraph("（无数据）", styles["Normal"]))
            if include_logic:
                story.append(Paragraph(
                    f"计算口径：{_metric_formula({'type': chart_type, 'x_field': x, 'y_field': y, 'aggregate': agg})}",
                    ParagraphStyle("f", parent=styles["Normal"], fontSize=9, textColor=colors.grey)))
            story.append(Spacer(1, 0.3 * cm))
            rendered += 1

        if include_watermark:
            story.append(Spacer(1, 0.4 * cm))
            story.append(Paragraph("AI-Report 导出 · 数据口径来自真实数据源", styles["Normal"]))

        doc = SimpleDocTemplate(out_path, pagesize=A4)
        doc.build(story)
        size = os.path.getsize(out_path)
        return {
            "mode": "sync",
            "format": "pdf",
            "download_url": f"http://127.0.0.1:8000/downloads/export_{dashboard_id}.pdf",
            "file_size": size,
            "generated_at": datetime.utcnow().isoformat(),
            "charts_rendered": rendered,
        }

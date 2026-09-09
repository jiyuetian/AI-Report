"""
报告生成引擎 - M3-01/M3-02
7章节图文报告：封面/执行摘要/数据说明/业务概览/维度分析/风险异常/附录
有LLM时走LLM解读，无LLM时用真实DuckDB聚合值确定性生成
"""
import json
import re
import html
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.duckdb_manager import DuckDBManager, quote_ident
from app.core.llm_gateway import llm_chat
from app.core.prompt_loader import load_prompt


class ReportChapter:
    """报告章节"""
    def __init__(self, number: int, title: str, content: str, charts: Optional[List[Dict]] = None):
        self.number = number
        self.title = title
        self.content = content
        self.charts = charts or []

    def to_dict(self) -> Dict:
        return {
            "number": self.number,
            "title": self.title,
            "content": self.content,
            "charts": self.charts,
        }


class ReportGenerator:
    """
    7章节报告生成器
    1. 封面
    2. 执行摘要
    3. 数据说明与方法论
    4. 业务概览
    5. 维度分析
    6. 风险与异常
    7. 附录
    """

    CHAPTERS = [
        ("封面", None),
        ("执行摘要", "executive_summary"),
        ("数据说明与方法论", "data_methodology"),
        ("业务概览", "business_overview"),
        ("维度分析", "dimension_analysis"),
        ("风险与异常", "risks_anomalies"),
        ("附录", "appendix"),
    ]

    def __init__(self, db: DuckDBManager, dataset_info: Dict, dashboard_config: Dict, quality_issues: List[Dict] = None):
        self.db = db
        self.dataset_info = dataset_info or {}
        self.dashboard_config = dashboard_config or {}
        self.quality_issues = quality_issues or []
        self.fields = self.dataset_info.get("field_profiles", [])
        self.theme = self.dataset_info.get("theme", "数据分析报告")
        self.table_name = self.dataset_info.get("table_name", "data")
        self.row_count = self.dataset_info.get("row_count", 0)
        self.llm_available = False
        # P1: 文档型数据集（docx/pdf/md/txt）无 DuckDB 表，报告基于抽取文本生成
        self.source_type = self.dataset_info.get("source_type") or (
            "table" if self.dataset_info.get("table_name") else "document"
        )
        self.extracted_text = self.dataset_info.get("extracted_text") or ""
        self.char_count = self.dataset_info.get("char_count", len(self.extracted_text))
        self.file_ext = self.dataset_info.get("file_ext")
        self._text_stats = self._compute_text_stats(self.extracted_text)

    async def generate(self) -> Dict[str, Any]:
        """生成完整7章节报告（表格型或文档型）"""
        chapters = []

        # Ch1: 封面（确定性）
        chapters.append(self._ch1_cover())

        # P1: 文档型数据集走文本分支（无DuckDB表，全部确定性统计，禁止编造）
        if self.source_type == "document":
            chapters.append(await self._doc_ch2_executive_summary())
            chapters.append(self._doc_ch3_data_methodology())
            chapters.append(self._doc_ch4_overview())
            chapters.append(self._doc_ch5_analysis())
            chapters.append(self._ch6_risks_anomalies())
            chapters.append(self._doc_ch7_appendix())
        else:
            # Ch2: 执行摘要（LLM优先，确定性兜底）
            chapters.append(await self._ch2_executive_summary())

            # Ch3: 数据说明（确定性）
            chapters.append(self._ch3_data_methodology())

            # Ch4: 业务概览（确定性聚合）
            chapters.append(await self._ch4_business_overview())

            # Ch5: 维度分析（基于图表配置）
            chapters.append(await self._ch5_dimension_analysis())

            # Ch6: 风险与异常
            chapters.append(self._ch6_risks_anomalies())

            # Ch7: 附录
            chapters.append(self._ch7_appendix())

        # 组装HTML
        html = self._render_html(chapters)

        # chart_count 按真实渲染数统计（ECharts图表 + KPI卡片）
        chart_count = (
            html.count('class="echarts-chart"')
            + html.count('class="kpi-card"')
            + html.count('class="kpi-display"')
        )

        return {
            "title": self.theme,
            "generated_at": datetime.now().isoformat(),
            "chapters": [c.to_dict() for c in chapters],
            "html": html,
            "llm_used": self.llm_available,
            "chart_count": chart_count,
            "source_type": self.source_type,
        }

    # ── Ch1 封面 ──────────────────────────────────────────────────
    # ── 文本类统计（文档型数据集，确定性） ─────────────────────────
    def _compute_text_stats(self, text: str) -> Dict[str, Any]:
        """对抽取文本做确定性统计（无LLM、无抽样）"""
        text = text or ""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        # 中文字符数
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        words = len(re.findall(r"[A-Za-z]+", text))
        return {
            "char_count": len(text),
            "cjk_count": cjk,
            "word_count": words,
            "line_count": len(lines),
            "paragraph_count": len(paragraphs),
            "paragraph_preview": paragraphs[:3],
        }

    def _ch1_cover(self) -> ReportChapter:
        now = datetime.now()
        date_str = f"{now.year}年{now.month:02d}月{now.day:02d}日"
        if self.source_type == "document":
            meta = (
                f"生成时间：{date_str} &nbsp;|&nbsp; "
                f"源文件：{html.escape(str(self.file_ext or '文档'))} &nbsp;|&nbsp; "
                f"抽取字符数：{self.char_count:,} &nbsp;|&nbsp; "
                f"段落数：{self._text_stats.get('paragraph_count', 0):,}"
            )
            desc = self.dataset_info.get(
                "description",
                f"基于{self.file_ext or '文档'}源文件抽取文本生成的{self.theme}"
            )
            return ReportChapter(
                number=1,
                title="封面",
                content=f"""
<div class="cover">
  <h1>{html.escape(str(self.theme))}</h1>
  <p class="subtitle">{html.escape(str(desc))}</p>
  <p class="meta">{meta}</p>
</div>
""",
            )
        desc = self.dataset_info.get("description", f"基于{self.row_count}条记录的{self.theme}数据分析")
        return ReportChapter(
            number=1,
            title="封面",
            content=f"""
<div class="cover">
  <h1>{html.escape(str(self.theme))}</h1>
  <p class="subtitle">{html.escape(str(desc))}</p>
  <p class="meta">生成时间：{date_str} &nbsp;|&nbsp; 数据条数：{self.row_count:,} &nbsp;|&nbsp; 字段数：{len(self.fields)}</p>
</div>
""",
        )

    # ── Ch2 执行摘要 ──────────────────────────────────────────────
    async def _ch2_executive_summary(self) -> ReportChapter:
        # 收集关键统计
        stats = await self._get_key_stats()
        stats_json = json.dumps(stats, ensure_ascii=False, default=str)

        prompt = load_prompt("executive_summary", self._default_executive_summary(stats))

        try:
            from app.core.config import settings
            if settings.LLM_API_KEY and settings.LLM_BASE_URL:
                result = await llm_chat(
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": f"数据集：{self.theme}，统计信息：{stats_json}"},
                    ],
                    model="glm-5.2",
                )
                if result and result.get("success"):
                    self.llm_available = True
                    summary_text = result.get("content", "")
                    # 截取前300字
                    summary_text = summary_text[:300] + ("…" if len(summary_text) > 300 else "")
                    return ReportChapter(2, "执行摘要", summary_text)
        except Exception as e:
            print(f"[Report] LLM执行摘要失败: {e}")

        # 确定性兜底
        return ReportChapter(2, "执行摘要", self._default_executive_summary(stats))

    def _default_executive_summary(self, stats: Dict) -> str:
        """确定性执行摘要（无LLM时的兜底）"""
        lines = []
        lines.append(f"本报告基于 **{self.row_count:,}** 条记录生成，涵盖 **{len(self.fields)}** 个数据字段。")
        lines.append("")
        lines.append("### 关键发现")
        lines.append("")
        for key, val in list(stats.items())[:5]:
            if isinstance(val, (int, float)):
                lines.append(f"- **{key}**：{val:,.2f}" if isinstance(val, float) else f"- **{key}**：{val:,}")
            elif isinstance(val, str):
                lines.append(f"- **{key}**：{val}")
        lines.append("")
        lines.append("> ⚠️ AI解读不可用，以下为确定性摘要（基于真实数据聚合，非LLM生成）")
        return "\n".join(lines)

    # ── Ch3 数据说明 ──────────────────────────────────────────────
    def _ch3_data_methodology(self) -> ReportChapter:
        field_rows = []
        for f in self.fields:
            name = f.get("name", "")
            ftype = f.get("type", "TEXT")
            cardinality = f.get("cardinality", "?")
            missing = f.get("missing_rate", 0)
            field_rows.append(
                f"<tr><td>{name}</td><td>{ftype}</td><td>{cardinality}</td><td>{missing:.1%}</td></tr>"
            )
        fields_html = f"<table class='data-table'><thead><tr><th>字段名</th><th>类型</th><th>基数</th><th>缺失率</th></tr></thead><tbody>{''.join(field_rows)}</tbody></table>"

        content = f"""
<h3>数据来源</h3>
<p>数据表：<code>{self.table_name}</code> &nbsp;|&nbsp; 记录数：<strong>{self.row_count:,}</strong> &nbsp;|&nbsp; 字段数：<strong>{len(self.fields)}</strong></p>

<h3>数据质量</h3>
<p>本次分析采用确定性聚合方法（DuckDB直接计算），无抽样、无插补估计。各字段类型由样本值自动推断。</p>

<h3>字段清单</h3>
{fields_html}
"""
        return ReportChapter(3, "数据说明与方法论", content)

    # ── Ch4 业务概览 ──────────────────────────────────────────────
    async def _ch4_business_overview(self) -> ReportChapter:
        # 从dashboard_config获取KPI图表
        charts_cfg = self.dashboard_config.get("charts", [])
        kpi_charts = [c for c in charts_cfg if c.get("type") == "kpi"]

        # 对KPI图表执行真实聚合并渲染为内联卡片
        kpi_cards_html = ""
        for kpi in kpi_charts:
            y_field = kpi.get("y_field") or kpi.get("field")
            if not y_field:
                continue
            val = await self._aggregate_one(y_field, (kpi.get("agg") or "sum").upper())
            if val is None:
                continue
            title = kpi.get("title", y_field)
            kpi_cards_html += f"""
<div class="kpi-card">
  <div class="kpi-value">{val:,.2f}</div>
  <div class="kpi-title">{html.escape(str(title))}</div>
</div>"""

        content = f"""
<h3>核心指标</h3>
<div class="kpi-row">{kpi_cards_html if kpi_cards_html else '<p>暂无KPI指标，请上传数据后重新生成。</p>'}</div>

<h3>分析维度</h3>
<p>本报告基于以下维度进行交叉分析：</p>
<ul>
  {''.join(f'<li>{f.get("name", "")}（{f.get("type", "")}）</li>' for f in self.fields if f.get("type") in ("CATEGORY", "GEO", "DATE"))}
</ul>
"""
        # KPI 已渲染进 content，chart_count 按真实渲染数统计
        return ReportChapter(4, "业务概览", content, charts=kpi_charts)

    # ── Ch5 维度分析 ──────────────────────────────────────────────
    async def _ch5_dimension_analysis(self) -> ReportChapter:
        charts_cfg = self.dashboard_config.get("charts", [])
        # 过滤掉kpi/table，保留分析图表
        analysis_charts = [c for c in charts_cfg if c.get("type") not in ("kpi", "table")]

        contents = []
        for chart in analysis_charts[:6]:  # 最多6个图表
            ctype = chart.get("type", "bar")
            title = chart.get("title", "分析图表")
            x_field = chart.get("x_field", "")
            y_field = chart.get("y_field", "")
            cat_field = chart.get("category_field", x_field)
            val_field = chart.get("value_field", y_field)
            agg = (chart.get("agg") or "sum").upper()
            if agg not in ("SUM", "AVG", "COUNT", "MIN", "MAX"):
                agg = "SUM"

            # 获取真实聚合数据
            # x_field=维度(饼图=category_field)，y_field=数值(饼图=value_field)，z_field=备用数值字段
            chart_data = await self._get_chart_data(ctype, cat_field, val_field, x_field, agg)

            # 生成交互式图表HTML（ECharts）
            chart_html = self._render_echarts(ctype, title, chart_data)

            # 生成解读文字
            interpretation = self._generate_interpretation(ctype, title, chart_data, val_field)

            contents.append(f"""
<div class="chart-section">
  <h3>{title}</h3>
  {chart_html}
  <p class="interpretation">{interpretation}</p>
</div>
""")

        content = "\n".join(contents) if contents else "<p>暂无维度分析图表。</p>"
        return ReportChapter(5, "维度分析", content, charts=analysis_charts[:6])

    # ── Ch6 风险与异常 ────────────────────────────────────────────
    def _ch6_risks_anomalies(self) -> ReportChapter:
        if not self.quality_issues:
            content = "<p>本次数据质量良好，未发现显著异常。</p>"
        else:
            rows = []
            for issue in self.quality_issues[:10]:
                rows.append(f"<tr><td>{issue.get('issue_type','?')}</td><td>{issue.get('column','?')}</td><td>{issue.get('severity','?')}</td><td>{issue.get('message','')}</td></tr>")
            content = f"""
<h3>数据质量问题</h3>
<table class='data-table'>
  <thead><tr><th>类型</th><th>字段</th><th>严重度</th><th>描述</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
"""
        return ReportChapter(6, "风险与异常", content)

    # ── Ch7 附录 ──────────────────────────────────────────────────
    def _ch7_appendix(self) -> ReportChapter:
        # 取前50行数据
        try:
            sample = self.db.query(f"SELECT * FROM {quote_ident(self.table_name)} LIMIT 50")
            if sample:
                cols = list(sample[0].keys())
                header = "<tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"
                rows = ""
                for row in sample:
                    cells = "".join(f"<td>{str(v)[:50]}</td>" for v in row.values())
                    rows += f"<tr>{cells}</tr>"
                data_html = f"<table class='data-table'><thead>{header}</thead><tbody>{rows}</tbody></table>"
            else:
                data_html = "<p>无数据可展示。</p>"
        except Exception:
            data_html = "<p>数据预览不可用。</p>"

        content = f"""
<h3>数据样本（前50行）</h3>
{data_html}

<h3>分析方法说明</h3>
<ul>
  <li>图表生成：规则引擎（s3_chart_engine_v2）+ LLM增强（如可用）</li>
  <li>字段类型推断：基于样本值 + 关键词匹配（优先级：样本值 > 关键词）</li>
  <li>图表推荐：基于字段配对 + 基数约束（分类≤20优先）</li>
  <li>统计计算：DuckDB直接聚合，无抽样</li>
</ul>
"""
        return ReportChapter(7, "附录", content)

    # ── 聚合辅助方法 ──────────────────────────────────────────────
    async def _get_key_stats(self) -> Dict[str, Any]:
        """获取关键统计值"""
        stats = {}
        stats["总记录数"] = self.row_count

        # 对每个数值字段计算SUM/AVG
        for f in self.fields:
            if f.get("type") in ("NUMBER",) and f.get("name"):
                name = f["name"]
                try:
                    sum_val = await self._aggregate_one(name, "SUM")
                    avg_val = await self._aggregate_one(name, "AVG")
                    stats[f"{name}（求和）"] = sum_val
                    stats[f"{name}（均值）"] = avg_val
                except Exception:
                    pass
        return stats

    async def _aggregate_one(self, field: str, agg: str) -> Optional[float]:
        """对单个字段执行聚合（显式别名，避免列名推断问题）"""
        try:
            sql = f"SELECT {agg}({quote_ident(field)}) AS _v FROM {quote_ident(self.table_name)}"
            result = self.db.query(sql)
            if result:
                return result[0].get("_v")
        except Exception:
            pass
        return None

    async def _get_chart_data(self, chart_type: str, x_field: str, y_field: str, z_field: str = None, agg: str = "SUM") -> List[Dict]:
        """获取图表真实数据。

        x_field = 维度/类别字段（饼图=category_field）
        y_field = 数值字段（饼图=value_field，bar/line=聚合值）
        z_field = 备用数值字段（当 y_field 未指定时使用）
        """
        try:
            if chart_type in ("bar", "line"):
                if x_field and y_field:
                    sql = f"SELECT {quote_ident(x_field)} AS dim, {agg}({quote_ident(y_field)}) AS val FROM {quote_ident(self.table_name)} GROUP BY dim ORDER BY val DESC LIMIT 20"
                    return self.db.query(sql) or []
                return []
            elif chart_type == "pie":
                if x_field and (y_field or z_field):
                    val_col = y_field if y_field else z_field
                    sql = f"SELECT {quote_ident(x_field)} AS cat, {agg}({quote_ident(val_col)}) AS val FROM {quote_ident(self.table_name)} GROUP BY cat ORDER BY val DESC LIMIT 10"
                    return self.db.query(sql) or []
                elif x_field:
                    sql = f"SELECT {quote_ident(x_field)} AS cat, COUNT(*) AS val FROM {quote_ident(self.table_name)} GROUP BY cat ORDER BY val DESC LIMIT 10"
                    return self.db.query(sql) or []
                return []
            elif chart_type == "kpi":
                if y_field:
                    val = await self._aggregate_one(y_field, "SUM")
                    return [{"value": val}] if val is not None else []
                return []
            elif chart_type == "histogram":
                if y_field:
                    sql = f"SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {quote_ident(y_field)}) AS median, MIN({quote_ident(y_field)}) AS min_val, MAX({quote_ident(y_field)}) AS max_val FROM {quote_ident(self.table_name)}"
                    result = self.db.query(sql)
                    return result or []
                return []
        except Exception as e:
            print(f"[Report] 获取图表数据失败({chart_type} x={x_field} y={y_field} z={z_field}): {e}")
        return []

    def _render_echarts(self, chart_type: str, title: str, data: List[Dict]) -> str:
        """渲染ECharts图表HTML（data-option 经HTML转义，属性双引号安全）"""
        if not data:
            return ""

        if chart_type in ("bar", "line"):
            dims = [str(d.get("dim", d.get(list(d.keys())[0], "?"))) for d in data]
            vals = [d.get("val", d.get(list(d.keys())[1], 0)) for d in data]
            option = json.dumps({
                "title": {"text": title},
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "category", "data": dims},
                "yAxis": {"type": "value"},
                "series": [{"data": vals, "type": chart_type, "smooth": chart_type == "line"}]
            }, ensure_ascii=False)
            return f'<div class="echarts-chart" data-option="{html.escape(option, quote=True)}"></div>'

        elif chart_type == "pie":
            cats = [str(d.get("cat", d.get(list(d.keys())[0], "?"))) for d in data]
            vals = [d.get("val", d.get("cnt", 0)) for d in data]
            option = json.dumps({
                "title": {"text": title},
                "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
                "series": [{"type": "pie", "radius": "55%",
                            "data": [{"name": n, "value": v} for n, v in zip(cats, vals)]}]
            }, ensure_ascii=False)
            return f'<div class="echarts-chart" data-option="{html.escape(option, quote=True)}"></div>'

        elif chart_type == "kpi":
            val = data[0].get("value", 0) if data else 0
            return f'<div class="kpi-display"><span class="kpi-big">{val:,.2f}</span></div>'

        elif chart_type == "histogram":
            if data:
                d = data[0]
                return f'<div class="kpi-display"><span>中位数: {d.get("median", "?"):,.2f}</span></div>'
            return ""

        return ""

    def _generate_interpretation(self, chart_type: str, title: str, data: List[Dict], val_field: str) -> str:
        """确定性解读（无LLM时的真实数字描述）"""
        if not data:
            return "该图表暂无数据。"

        if chart_type in ("bar", "line"):
            top = max(data, key=lambda d: d.get("val", 0))
            bottom = min(data, key=lambda d: d.get("val", 0))
            total = sum(d.get("val", 0) for d in data)
            return (
                f"{title}：最高值为「{top.get('dim', '?')}」({top.get('val', 0):,.2f})，"
                f"最低值为「{bottom.get('dim', '?')}」({bottom.get('val', 0):,.2f})，"
                f"合计 {total:,.2f}。"
            )

        elif chart_type == "pie":
            top = max(data, key=lambda d: d.get("val", d.get("cnt", 0)))
            total = sum(d.get("val", d.get("cnt", 0)) for d in data)
            pct = top.get("val", top.get("cnt", 0)) / total * 100 if total else 0
            return (
                f"{title}：占比最高的是「{top.get('cat', '?')}」，"
                f"数值为 {top.get('val', top.get('cnt', 0)):,.2f}，占比 {pct:.1f}%。"
            )

        elif chart_type == "kpi":
            val = data[0].get("value", 0)
            return f"{title}：当前值为 {val:,.2f}（真实聚合计算）。"

        return f"{title}：共 {len(data)} 条记录。"

    # ── 文档型章节（P1：文本数据集，全部确定性统计） ───────────────
    async def _doc_ch2_executive_summary(self) -> ReportChapter:
        """文档型执行摘要：统计 + 文本摘录（无LLM时也保证真实，禁止编造）"""
        ts = self._text_stats
        text = self.extracted_text or ""
        excerpt = text[:600] + ("…" if len(text) > 600 else "")

        # 收集关键统计（全为确定性数值）
        stats = {
            "抽取字符数": ts["char_count"],
            "中文字符数": ts["cjk_count"],
            "英文单词数": ts["word_count"],
            "非空行数": ts["line_count"],
            "段落数": ts["paragraph_count"],
        }

        try:
            from app.core.config import settings
            if settings.LLM_API_KEY and settings.LLM_BASE_URL and text:
                result = await llm_chat(
                    messages=[
                        {"role": "system", "content": load_prompt("executive_summary", "你是数据分析报告撰写助手。仅基于给定文本内容生成摘要，不得编造。")},
                        {"role": "user", "content": f"源文件类型：{self.file_ext}\n文本内容（节选）：\n{text[:2500]}"},
                    ],
                    model="glm-5.2",
                )
                if result and result.get("success"):
                    self.llm_available = True
                    summary_text = result.get("content", "")
                    summary_text = summary_text[:500] + ("…" if len(summary_text) > 500 else "")
                    lines = [summary_text, "", "### 文本统计", ""]
                    for k, v in stats.items():
                        lines.append(f"- **{k}**：{v:,}")
                    lines.append("")
                    lines.append("> 摘要由AI生成，统计数值为确定性计算（非LLM输出）。")
                    return ReportChapter(2, "执行摘要", "\n".join(lines))
        except Exception as e:
            print(f"[Report] LLM文档摘要失败: {e}")

        # 确定性兜底
        lines = []
        lines.append(f"本报告基于 **{html.escape(str(self.file_ext or '文档'))}** 源文件生成，共抽取 **{ts['char_count']:,}** 个字符。")
        lines.append("")
        lines.append("### 文本统计")
        lines.append("")
        for k, v in stats.items():
            lines.append(f"- **{k}**：{v:,}")
        lines.append("")
        lines.append("### 内容摘录（原文前600字，非AI改写）")
        lines.append("")
        lines.append(f"<blockquote>{html.escape(excerpt) if excerpt else '（未能抽取到有效文本）'}</blockquote>")
        lines.append("")
        lines.append("> ⚠️ AI解读不可用，以下内容为确定性统计与原文摘录（非LLM生成）。")
        return ReportChapter(2, "执行摘要", "\n".join(lines))

    def _doc_ch3_data_methodology(self) -> ReportChapter:
        ts = self._text_stats
        content = f"""
<h3>数据来源</h3>
<p>源文件：<code>{html.escape(str(self.file_ext or '文档'))}</code> &nbsp;|&nbsp; 抽取字符数：<strong>{ts['char_count']:,}</strong> &nbsp;|&nbsp; 段落数：<strong>{ts['paragraph_count']:,}</strong></p>

<h3>数据处理说明</h3>
<p>文档类文件（docx/pdf/md/txt）不参与数值聚合，不写入 DuckDB 分析表。本报告仅基于抽取文本做确定性统计与原文摘录，未做归纳、改写或补全。</p>

<h3>统计口径</h3>
<table class='data-table'>
  <thead><tr><th>指标</th><th>数值</th><th>口径</th></tr></thead>
  <tbody>
    <tr><td>抽取字符数</td><td>{ts['char_count']:,}</td><td>抽取文本总长度（含空白）</td></tr>
    <tr><td>中文字符数</td><td>{ts['cjk_count']:,}</td><td>Unicode CJK 统一汉字区</td></tr>
    <tr><td>英文单词数</td><td>{ts['word_count']:,}</td><td>连续英文字母序列计数</td></tr>
    <tr><td>非空行数</td><td>{ts['line_count']:,}</td><td>去除首尾空白后非空行</td></tr>
    <tr><td>段落数</td><td>{ts['paragraph_count']:,}</td><td>空行分隔的文本块</td></tr>
  </tbody>
</table>

<p style="color:#999;font-size:12px;">注：文档类数据集无字段画像，故无字段清单。如需数值分析，请上传 xlsx/xls/csv/json/tsv 表格文件。</p>
"""
        return ReportChapter(3, "数据说明与方法论", content)

    def _doc_ch4_overview(self) -> ReportChapter:
        ts = self._text_stats
        cards = ""
        items = [
            ("抽取字符数", ts["char_count"]),
            ("段落数", ts["paragraph_count"]),
            ("非空行数", ts["line_count"]),
            ("中文字符数", ts["cjk_count"]),
        ]
        for title, val in items:
            cards += f"""
<div class="kpi-card">
  <div class="kpi-value">{val:,.2f}</div>
  <div class="kpi-title">{title}</div>
</div>"""
        preview = ts.get("paragraph_preview", []) or []
        preview_html = ""
        if preview:
            preview_html = "".join(
                f'<div class="interpretation" style="margin-bottom:8px;"><strong>段落 {i+1}</strong>：{html.escape(p[:300])}</div>'
                for i, p in enumerate(preview[:3])
            )
        else:
            preview_html = "<p>未能抽取到有效段落。</p>"

        content = f"""
<h3>文本规模指标</h3>
<div class="kpi-row">{cards}</div>

<h3>正文片段（原文，非AI改写）</h3>
{preview_html}
"""
        return ReportChapter(4, "业务概览", content)

    def _doc_ch5_analysis(self) -> ReportChapter:
        ts = self._text_stats
        # 长度分布：按段落长度分桶（确定性直方图）
        lengths = []
        for p in re.split(r"\n\s*\n", self.extracted_text or ""):
            p = p.strip()
            if p:
                lengths.append(len(p))
        buckets = [(0, 50), (51, 150), (151, 400), (401, 999999)]
        labels = ["≤50字", "51-150字", "151-400字", ">400字"]
        vals = []
        for (lo, hi), lab in zip(buckets, labels):
            n = sum(1 for L in lengths if lo <= L <= hi)
            vals.append(n)

        data = [{"cat": lab, "val": n} for lab, n in zip(labels, vals)]
        chart_html = self._render_echarts("bar", "段落长度分布", data)
        top = max(data, key=lambda d: d["val"]) if data else {"cat": "-", "val": 0}
        total = sum(vals)
        interpretation = (
            f"共统计 {total} 个段落，其中「{top['cat']}」的段落最多（{top['val']} 个）。"
            if total else "无有效段落。"
        )
        # 字符占比：中文 vs 英文
        cjk = ts["cjk_count"]
        word = ts["word_count"]
        total_chars = ts["char_count"] or 1
        cjk_pct = cjk / total_chars * 100
        en_pct = (word * 5) / total_chars * 100  # 英文单词按5字符近似
        content = f"""
<div class="chart-section">
  <h3>段落长度分布</h3>
  {chart_html}
  <p class="interpretation">{interpretation}</p>
</div>

<div class="chart-section">
  <h3>文字构成占比</h3>
  <div class="kpi-row">
    <div class="kpi-card"><div class="kpi-value">{cjk_pct:.1f}%</div><div class="kpi-title">中文字符占比</div></div>
    <div class="kpi-card"><div class="kpi-value">{en_pct:.1f}%</div><div class="kpi-title">英文内容占比（按词近似）</div></div>
    <div class="kpi-card"><div class="kpi-value">{total_chars:,}</div><div class="kpi-title">总字符数</div></div>
  </div>
  <p class="interpretation">中文 {cjk:,} 字，英文 {word:,} 词。以上为确定性计数，无估算成分。</p>
</div>
"""
        return ReportChapter(5, "维度分析", content, charts=data)

    def _doc_ch7_appendix(self) -> ReportChapter:
        text = self.extracted_text or ""
        if text:
            excerpt = text[:3000] + ("…" if len(text) > 3000 else "")
            sample_html = f'<div class="interpretation" style="white-space:pre-wrap;max-height:400px;overflow:auto;">{html.escape(excerpt)}</div>'
        else:
            sample_html = "<p>无文本可展示。</p>"
        content = f"""
<h3>抽取文本样本（前3000字，原文）</h3>
{sample_html}

<h3>分析方法说明</h3>
<ul>
  <li>文本抽取：docx/python-docx、pdf/PyMuPDF或pdfplumber、md与txt/直接读取</li>
  <li>统计计算：字符/单词/行/段落均按固定规则计数，无抽样、无估算</li>
  <li>文档型数据集不写入 DuckDB，因此无聚合图表与字段画像</li>
  <li>摘要与解读：LLM可用时生成摘要（统计数值仍为确定性计算），不可用时仅给原文摘录</li>
</ul>
"""
        return ReportChapter(7, "附录", content)

    # ── HTML渲染 ──────────────────────────────────────────────────
    def _render_html(self, chapters: List[ReportChapter]) -> str:
        chapters_html = ""
        for ch in chapters:
            # 图表已内联在 ch.content 中（ECharts），不再渲染重复占位符
            chapters_html += f"""
<section class="chapter" id="ch{ch.number}">
  <h2 class="chapter-title">第{ch.number}章 {ch.title}</h2>
  <div class="chapter-content">{ch.content}</div>
</section>
"""

        css = """
<style>
  body { font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif; max-width: 900px; margin: 0 auto; padding: 40px; color: #333; }
  .cover { text-align: center; padding: 80px 20px; border-bottom: 2px solid #eee; margin-bottom: 40px; }
  .cover h1 { font-size: 32px; margin-bottom: 16px; }
  .cover .subtitle { font-size: 18px; color: #666; }
  .cover .meta { font-size: 14px; color: #999; margin-top: 24px; }
  .chapter { margin-bottom: 48px; }
  .chapter-title { font-size: 24px; color: #1677ff; border-left: 4px solid #1677ff; padding-left: 12px; margin-bottom: 20px; }
  .chapter-content { line-height: 1.8; }
  .chart-section { margin: 16px 0; padding: 16px; background: #fff; border: 1px solid #e8e8e8; border-radius: 8px; }
  .kpi-row { display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0; }
  .kpi-card { flex: 1; min-width: 140px; background: #f6f8fa; border-radius: 8px; padding: 16px; text-align: center; }
  .kpi-value { font-size: 28px; font-weight: bold; color: #1677ff; }
  .kpi-title { font-size: 13px; color: #666; margin-top: 4px; }
  .kpi-display { font-size: 36px; font-weight: bold; color: #1677ff; text-align: center; padding: 20px; }
  .data-table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }
  .data-table th, .data-table td { border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; }
  .data-table th { background: #f6f8fa; font-weight: 600; }
  .echarts-chart { height: 320px; width: 100%; margin: 12px 0; }
  .chart-placeholder { padding: 40px; text-align: center; color: #999; background: #f6f8fa; border-radius: 8px; }
  .interpretation { background: #f0f7ff; border-left: 3px solid #1677ff; padding: 10px 16px; margin-top: 8px; font-size: 14px; color: #555; line-height: 1.6; }
  code { background: #f5f5f5; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
  h3 { color: #333; margin-top: 24px; }
  ul { line-height: 1.8; }
  li { margin: 4px 0; }
</style>
"""
        # ECharts CDN（离线时可降级为占位符，不影响文本内容）
        echarts_init = """
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script>
  if (typeof echarts !== 'undefined') {
    document.querySelectorAll('.echarts-chart').forEach(function (el) {
      var raw = el.getAttribute('data-option');
      if (!raw) return;
      try {
        var opt = JSON.parse(raw);
        var chart = echarts.init(el, null, {renderer: 'svg'});
        chart.setOption(opt);
        window.addEventListener('resize', function () { chart.resize(); });
      } catch (e) {
        el.innerHTML = '<p style="color:#999;padding:40px;text-align:center;">图表渲染失败</p>';
      }
    });
  }
</script>
"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>{self.theme} - 分析报告</title>
  {css}
</head>
<body>
  {chapters_html}
  <div style="text-align:center; padding:40px; color:#999; font-size:12px; border-top:1px solid #eee; margin-top:40px;">
    由 AI-Report 自动生成 &nbsp;|&nbsp; 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
    {'&nbsp;|&nbsp; AI解读已启用' if self.llm_available else '&nbsp;|&nbsp; AI解读不可用，以下为确定性摘要'}
  </div>
  {echarts_init}
</body>
</html>"""

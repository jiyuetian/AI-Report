"""#7 验收：大脑看板场景复用 PRD 可行性引导（0 可视化字段时给出明确建议）。

对应审计 #7：对话可行性检查已有完善引导，看板（大脑 S3）场景此前缺失。
现在 S3 引擎对纯文本数据集标记 no_chartable_fields=True 并给出 PRD 式建议，
brain_run_sse 已将该建议写入看板配置与完成事件（见 brain_run_sse.py）。
"""
from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine


def test_zero_visual_fields_sets_no_chartable_and_prd_suggestion():
    engine = S3ChartEngine()
    cfg = engine.generate_dashboard_config(fields=["备注", "名称"], grain="row")
    assert cfg["no_chartable_fields"] is True
    assert cfg["chart_count"] == 0
    # PRD 引导：明确告知需补充 数值 / 分类 / 日期 字段
    assert "数值" in cfg["suggestion"]
    assert "分类" in cfg["suggestion"]
    assert "日期" in cfg["suggestion"]


def test_normal_fields_produce_charts_and_no_suggestion():
    engine = S3ChartEngine()
    cfg = engine.generate_dashboard_config(fields=["地区", "金额", "日期"], grain="month")
    assert cfg["chart_count"] > 0
    assert cfg["no_chartable_fields"] is False
    assert cfg["suggestion"] == ""

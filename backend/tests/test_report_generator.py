"""报告生成器验收：0 图可读提示 + 整份报告异常降级不崩溃"""
import asyncio

import pytest

from app.core.report_generator import ReportChapter, ReportGenerator


def test_ch5_zero_charts_explains_reason():
    """dashboard_config 无 charts 时，维度分析章节应明确告知原因而非空白。"""
    rg = ReportGenerator(
        db=None,
        dataset_info={"theme": "测试报告", "field_profiles": []},
        dashboard_config={"charts": []},
    )
    ch = asyncio.run(rg._ch5_dimension_analysis())
    assert "没有可可视化" in ch.content


def test_generate_degrades_on_chapter_error():
    """任一章节异常时，整份报告应被外层 try 捕获并降级返回（带 error 标记），不得向上抛。

    注：ReportGenerator 按 source_type 分 table/document 两条章节分支，
    这里注入在两条分支都会最先执行的 _ch1_cover，验证整份降级与分支无关。
    """
    rg = ReportGenerator(
        db=None,
        dataset_info={"theme": "降级测试", "field_profiles": []},
        dashboard_config={"charts": []},
    )

    def _boom():
        raise RuntimeError("injected chapter failure")

    rg._ch1_cover = _boom
    result = asyncio.run(rg.generate())
    assert isinstance(result, dict)
    assert "error" in result, "章节异常应被外层 try 捕获并标记 error"
    assert result["chart_count"] == 0


def test_generate_returns_dict_even_with_null_db():
    """db=None 时 generate 不应崩溃，应返回结构化结果（error 或正常）。"""
    rg = ReportGenerator(
        db=None,
        dataset_info={"theme": "空库测试", "field_profiles": []},
        dashboard_config={"charts": []},
    )
    result = asyncio.run(rg.generate())
    assert isinstance(result, dict)
    assert "chapters" in result

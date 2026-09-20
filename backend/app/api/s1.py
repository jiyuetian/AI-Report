"""
S1 主题识别器 API - M2-03
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.brain_modules.s1_theme_detector import S1ThemeDetector, detect_theme

router = APIRouter(prefix="/brain/s1", tags=["S1-主题识别"])


class ThemeDetectRequest(BaseModel):
    """主题识别请求"""
    dataset_id: str
    fields: List[str] = Field(..., description="字段列表")
    sample_data: Optional[List[Dict[str, Any]]] = Field(None, description="样本数据")
    dataset_name: str = Field("", description="数据集名称")


class ThemeDetectResponse(BaseModel):
    """主题识别响应"""
    success: bool
    dataset_id: str
    theme_tag: str
    confidence: float
    matched_keywords: List[str]
    method: str  # dictionary | llm
    llm_called: bool
    reason: str


class V2TableThemeRequest(BaseModel):
    """v2五表主题识别请求"""
    table_type: str = Field(..., pattern="^(01|02|03|04|05)$", description="v2表类型")
    dataset_id: str
    fields: List[str]


@router.post("/detect", response_model=ThemeDetectResponse)
async def detect_theme_endpoint(
    request: ThemeDetectRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    主题识别
    
    流程：
    1. 词典规则优先匹配
    2. 置信度≥0.8直接返回（不调LLM）
    3. 低置信度LLM兜底
    """
    detector = S1ThemeDetector()
    result = await detector.detect(
        db=db,
        fields=request.fields,
        sample_data=request.sample_data,
        dataset_name=request.dataset_name
    )
    
    return ThemeDetectResponse(
        success=True,
        dataset_id=request.dataset_id,
        theme_tag=result.theme_tag,
        confidence=result.confidence,
        matched_keywords=result.matched_keywords,
        method=result.method,
        llm_called=result.llm_called,
        reason=result.reason
    )


@router.post("/detect-v2-table", response_model=ThemeDetectResponse)
async def detect_v2_table_theme(
    request: V2TableThemeRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    v2五表主题识别
    
    强制映射：
    - 01表 → 担保风控
    - 02表 → 客户画像
    - 03表 → 逾期分析
    - 04表 → 产品分析
    - 05表 → 担保风控
    """
    detector = S1ThemeDetector()
    result = await detector.detect_for_v2_tables(
        db=db,
        table_type=request.table_type,
        fields=request.fields
    )
    
    return ThemeDetectResponse(
        success=True,
        dataset_id=request.dataset_id,
        theme_tag=result.theme_tag,
        confidence=result.confidence,
        matched_keywords=result.matched_keywords,
        method=result.method,
        llm_called=result.llm_called,
        reason=result.reason
    )


@router.get("/dictionary")
async def get_theme_dictionary(db: AsyncSession = Depends(get_db)):
    """获取当前主题词典"""
    detector = S1ThemeDetector()
    dictionary = await detector.load_dictionary(db)
    
    return {
        "success": True,
        "dictionary": dictionary,
        "theme_count": len(dictionary),
        "threshold": detector.DICTIONARY_CONFIDENCE_THRESHOLD
    }


@router.post("/_internal/test-v2-tables")
async def test_v2_tables(db: AsyncSession = Depends(get_db)):
    """
    测试v2五表识别（内部接口）
    
    返回五表的识别结果
    """
    test_cases = [
        ("01", ["借据编号", "担保金额", "抵押率", "质押物", "保证人"]),
        ("02", ["客户编号", "客户名称", "客户类型", "注册地址"]),
        ("03", ["月份", "逾期金额", "逾期天数", "不良率"]),
        ("04", ["产品类型", "贷款品种", "合同金额", "合同期限"]),
        ("05", ["担保编号", "担保方式", "担保金额", "抵押物名称"])
    ]
    
    results = []
    for table_type, fields in test_cases:
        result = await detect_theme(
            db=db,
            fields=fields,
            dataset_name=f"{table_type}表"
        )
        results.append({
            "table_type": table_type,
            "fields": fields,
            "result": result
        })
    
    # 验证是否全部识别为预期主题
    expected = {
        "01": "担保风控",
        "02": "客户画像",
        "03": "逾期分析",
        "04": "产品分析",
        "05": "担保风控"
    }
    
    all_passed = all(
        r["result"]["theme_tag"] == expected[r["table_type"]]
        for r in results
    )
    
    return {
        "success": True,
        "all_passed": all_passed,
        "expected_themes": expected,
        "results": results
    }
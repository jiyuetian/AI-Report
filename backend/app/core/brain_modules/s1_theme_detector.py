"""
S1 主题识别器 - M2-03
主题词典规则优先 + LLM兜底
输出: theme_tag + confidence
"""
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
import re

from app.core.brain_config_manager import BrainConfigManager
from app.core.llm_gateway import llm_chat
from app.core.prompt_loader import load_prompt


# 主题域提示（LLM兜底时展示给模型的主题候选）
_THEME_DOMAINS = """- 担保风控（包含担保、抵押、质押等字段）
- 逾期分析（包含逾期、违约等字段）
- 地区分布（包含省份、城市等字段）
- 客户画像（包含客户、企业等字段）
- 产品分析（包含贷款、借据等字段）"""

# 内置默认提示词（外置 prompts/s1_theme_detector.md 缺失时的回退）
_PROMPT_TPL = """你是一位数据分析师。请分析以下数据集的主题：

数据集名称: {dataset_name}
字段列表: {fields}
字段数量: {field_count}{sample_str}

请从以下主题中识别最匹配的一个，或提出新的主题：
{theme_domains}

请以JSON格式返回：
{
    "theme_tag": "主题标签",
    "confidence": 0.95,
    "reason": "识别理由"
}"""


@dataclass
class ThemeDetectionResult:
    """主题识别结果"""
    theme_tag: str
    confidence: float
    matched_keywords: List[str]
    method: str  # "dictionary" | "llm"
    llm_called: bool = False
    reason: str = ""


class S1ThemeDetector:
    """
    S1 主题识别器
    
    策略：
    1. 词典规则优先匹配
    2. 置信度>0.8时直接返回（不调LLM，降本）
    3. 词典未命中或置信度低时，LLM兜底
    
    输出：
    - theme_tag: 主题标签
    - confidence: 置信度 0-1
    - matched_keywords: 匹配的关键词
    """
    
    # 词典命中阈值（≥此值不调LLM）
    DICTIONARY_CONFIDENCE_THRESHOLD = 0.8
    
    def __init__(self):
        self.theme_dict: Dict[str, List[str]] = {}
    
    async def load_dictionary(self, db: AsyncSession) -> Dict[str, List[str]]:
        """从brain_configs加载主题词典"""
        config = await BrainConfigManager.get_config(db, "theme_dict")
        if config and "content" in config:
            self.theme_dict = config["content"]
        else:
            # 默认词典
            self.theme_dict = {
                "担保风控": ["担保", "抵押", "质押", "保证", "留置", "担保金额", "抵押率", "质押率"],
                "逾期分析": ["逾期", "违约", "不良", "坏账", "呆账", "逾期天数", "逾期金额"],
                "地区分布": ["地区", "省份", "城市", "区域", "所在地", "行政区划"],
                "客户画像": ["客户", "借款人", "企业", "个人", "客户编号", "客户名称"],
                "产品分析": ["产品", "贷款", "借据", "合同", "产品类型", "贷款种类"]
            }
        return self.theme_dict
    
    def _match_dictionary(self, fields: List[str], sample_data: Optional[List[Dict]] = None) -> Optional[ThemeDetectionResult]:
        """
        词典匹配
        
        Args:
            fields: 字段名列表
            sample_data: 样本数据（可选，用于内容匹配）
        
        Returns:
            匹配结果，未命中返回None
        """
        if not self.theme_dict:
            return None
        
        best_match = None
        best_score = 0.0
        best_keywords = []
        
        # 将字段名转为小写便于匹配
        fields_lower = [f.lower() for f in fields]
        
        for theme_tag, keywords in self.theme_dict.items():
            matched = []
            
            for keyword in keywords:
                keyword_lower = keyword.lower()
                # 匹配字段名
                for field in fields_lower:
                    if keyword_lower in field:
                        matched.append(keyword)
                        break
                
                # 匹配样本数据（如果提供）
                if sample_data and not matched:
                    for row in sample_data[:10]:  # 只检查前10行
                        for value in row.values():
                            if isinstance(value, str) and keyword_lower in value.lower():
                                matched.append(keyword)
                                break
                        if matched:
                            break
            
            # 计算匹配度
            if matched:
                # 基础分：匹配关键词数 / 总关键词数
                base_score = len(matched) / len(keywords)
                # 权重：匹配关键词覆盖字段的比例
                coverage = len(set(matched)) / len(fields) if fields else 0
                # 综合得分
                score = min(1.0, base_score * 0.6 + coverage * 0.4 + len(matched) * 0.05)
                
                if score > best_score:
                    best_score = score
                    best_match = theme_tag
                    best_keywords = matched
        
        if best_match and best_score > 0:
            return ThemeDetectionResult(
                theme_tag=best_match,
                confidence=round(best_score, 2),
                matched_keywords=best_keywords,
                method="dictionary",
                llm_called=False,
                reason=f"词典匹配：命中关键词 {', '.join(best_keywords)}"
            )
        
        return None
    
    async def _llm_fallback(
        self,
        fields: List[str],
        sample_data: Optional[List[Dict]] = None,
        dataset_name: str = ""
    ) -> ThemeDetectionResult:
        """
        LLM兜底识别
        
        当词典未命中或置信度低时调用
        """
        # 构建prompt
        sample_str = ""
        if sample_data:
            sample_str = f"\n样本数据（前3行）:\n{str(sample_data[:3])[:500]}"

        fields_str = ", ".join(fields)
        # 外置被控提示词优先（prompts/s1_theme_detector.md），缺失回退内置默认
        prompt = load_prompt(
            "s1_theme_detector",
            _PROMPT_TPL,
            dataset_name=dataset_name,
            fields=fields_str,
            field_count=str(len(fields)),
            sample_str=sample_str,
            theme_domains=_THEME_DOMAINS,
        )
        
        # 调用LLM
        response = await llm_chat(
            prompt=prompt,
            json_mode=True,
            user_id="s1_theme_detector"
        )
        
        if response.success and response.response_json:
            result = response.response_json
            return ThemeDetectionResult(
                theme_tag=result.get("theme_tag", "未知"),
                confidence=result.get("confidence", 0.5),
                matched_keywords=[],
                method="llm",
                llm_called=True,
                reason=result.get("reason", "LLM识别")
            )
        
        # LLM失败返回未知
        return ThemeDetectionResult(
            theme_tag="未知",
            confidence=0.0,
            matched_keywords=[],
            method="llm",
            llm_called=True,
            reason="LLM调用失败，无法识别主题"
        )
    
    async def detect(
        self,
        db: AsyncSession,
        fields: List[str],
        sample_data: Optional[List[Dict]] = None,
        dataset_name: str = ""
    ) -> ThemeDetectionResult:
        """
        主题识别入口
        
        流程：
        1. 加载词典
        2. 词典匹配
        3. 高置信度直接返回（降本）
        4. 低置信度LLM兜底
        """
        # 1. 加载词典
        await self.load_dictionary(db)
        
        # 2. 词典匹配
        dict_result = self._match_dictionary(fields, sample_data)
        
        # 3. 高置信度直接返回（不调LLM）
        if dict_result and dict_result.confidence >= self.DICTIONARY_CONFIDENCE_THRESHOLD:
            print(f"[S1] 词典命中: {dict_result.theme_tag}, 置信度={dict_result.confidence} (≥{self.DICTIONARY_CONFIDENCE_THRESHOLD}，不调LLM)")
            return dict_result
        
        # 4. LLM兜底
        print(f"[S1] 词典未命中或置信度低，调用LLM兜底")
        llm_result = await self._llm_fallback(fields, sample_data, dataset_name)
        
        # 合并结果（取LLM结果，但保留词典匹配的关键词）
        if dict_result:
            llm_result.matched_keywords = dict_result.matched_keywords
            llm_result.reason = f"词典: {dict_result.reason}; LLM: {llm_result.reason}"
        
        return llm_result
    
    async def detect_for_v2_tables(
        self,
        db: AsyncSession,
        table_type: str,
        fields: List[str]
    ) -> ThemeDetectionResult:
        """
        v2五表专用识别
        
        01表（单笔借据）→ 担保风控
        02表（客户级）→ 客户画像
        03表（月份汇总）→ 逾期分析
        04表（宏观）→ 产品分析
        05表（担保明细）→ 担保风控
        """
        # 先尝试词典匹配
        result = await self.detect(db, fields, dataset_name=f"{table_type}表")
        
        # 如果是v2五表，强制映射到预期主题
        expected_themes = {
            "01": "担保风控",
            "02": "客户画像",
            "03": "逾期分析",
            "04": "产品分析",
            "05": "担保风控"
        }
        
        if table_type in expected_themes:
            expected = expected_themes[table_type]
            if result.theme_tag != expected:
                print(f"[S1] v2五表校正: {table_type}表 → {expected}")
                result.theme_tag = expected
                result.confidence = max(result.confidence, 0.9)
                result.reason = f"v2五表强制映射: {table_type}表 → {expected}"
        
        return result


# 便捷函数
async def detect_theme(
    db: AsyncSession,
    fields: List[str],
    sample_data: Optional[List[Dict]] = None,
    dataset_name: str = ""
) -> Dict[str, Any]:
    """
    便捷主题识别函数
    
    Returns:
        {
            "theme_tag": "担保风控",
            "confidence": 0.95,
            "method": "dictionary",
            "llm_called": false,
            "reason": "..."
        }
    """
    detector = S1ThemeDetector()
    result = await detector.detect(db, fields, sample_data, dataset_name)
    
    return {
        "theme_tag": result.theme_tag,
        "confidence": result.confidence,
        "matched_keywords": result.matched_keywords,
        "method": result.method,
        "llm_called": result.llm_called,
        "reason": result.reason
    }
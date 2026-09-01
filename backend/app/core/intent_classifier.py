"""
意图分类器 - M3-01
5类意图：换图/新增图/筛选下钻/归因追问/标题编辑
LLM增强：规则匹配<70分时调用LLM兜底
"""
import json
import re
from typing import Dict, Any, Tuple, Optional, List
from enum import Enum

from app.core.llm_gateway import LLMGateway


class IntentType(str, Enum):
    """意图类型"""
    CHANGE_CHART = "change_chart"      # 换图
    ADD_CHART = "add_chart"            # 新增图
    DELETE_CHART = "delete_chart"      # 删图
    REORDER_CHART = "reorder_chart"    # 排序调整
    FILTER_DRILL = "filter_drill"      # 筛选下钻
    ATTRIBUTION = "attribution"        # 归因追问
    EDIT_TITLE = "edit_title"          # 标题编辑
    UNKNOWN = "unknown"


class IntentClassifier:
    """意图分类器"""
    
    # 意图关键词映射
    INTENT_PATTERNS = {
        IntentType.CHANGE_CHART: [
            r"(换|改|变成|换成).{0,5}(图|图表|饼图|柱图|线图|散点图|表格)",
            r"(饼图|柱图|线图|散点图).{0,3}(改|换).{0,3}(饼图|柱图|线图|散点图|表格)",
            r"把.{0,10}(改|换).{0,3}(成|为)",
        ],
        IntentType.ADD_CHART: [
            r"(新增|添加|加|插入).{0,5}(图|图表|一张)",
            r"再.{0,3}(来|加|放).{0,3}(个|张)?.{0,5}(图|图表)",
            r"能不能.{0,5}(加|添加)",
        ],
        IntentType.DELETE_CHART: [
            r"(删除|移除|去掉|删掉|删了).{0,5}(图|图表|这个|那个|第.{1,2}个)",
            r"把.{0,10}(删掉|删了|删除|移除)",
            r"(不要|不需要|去掉).{0,5}(图|图表)",
        ],
        IntentType.REORDER_CHART: [
            r"(移动|排序|调整|调换).{0,5}(图|图表|位置|顺序|排序)",
            r"把.{0,10}(移到|放到|挪到|放在)",
            r"(上移|下移|置顶|置底)",
        ],
        IntentType.FILTER_DRILL: [
            r"(筛选|过滤|只看|显示).{0,10}(的|数据)?",
            r"(下钻|钻取|深入|展开).{0,5}(看|分析)?",
            r"(按|根据).{0,5}(分类|分组|维度)",
        ],
        IntentType.ATTRIBUTION: [
            r"(为什么|怎么回事|什么原因|为何).{0,10}(异常|波动|变化|下降|上升)?",
            r"(分析|解释|说明).{0,5}(原因|理由)",
            r"(归因|溯源|追溯)",
        ],
        IntentType.EDIT_TITLE: [
            r"(改|修改|编辑|换).{0,5}(标题|名字|名称)",
            r"标题.{0,3}(改|换成|改为)",
            r"(重命名|改名)",
        ],
    }
    
    @classmethod
    def classify(cls, message: str, context: Dict[str, Any] = None) -> Tuple[IntentType, int, Dict]:
        """
        分类意图
        
        Returns:
            (intent_type, confidence, analysis)
        """
        message = message.strip().lower()
        context = context or {}
        
        # 依次匹配各类意图
        for intent_type, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    confidence = cls._calculate_confidence(message, intent_type, pattern)
                    analysis = cls._extract_params(message, intent_type, context)
                    return intent_type, confidence, analysis
        
        # 未知意图 → 尝试LLM兜底
        result = cls._llm_classify(message, context)
        if result:
            return result
        return IntentType.UNKNOWN, 0, {"raw_message": message}
    
    @classmethod
    def _llm_classify(cls, message: str, context: Dict[str, Any] = None) -> Optional[Tuple[IntentType, int, Dict]]:
        """LLM兜底分类（规则匹配失败时）"""
        system_prompt = """你是一个自然语言意图分类器，请将用户的消息分类为以下意图之一：

可用意图：
- change_chart: 修改图表类型（把饼图改成折线图等）
- add_chart: 新增一个图表
- delete_chart: 删除一个图表
- reorder_chart: 调整图表位置/排序
- filter_drill: 筛选数据、下钻分析
- attribution: 追问原因、归因分析
- edit_title: 修改标题
- unknown: 不确定

用户当前看板上下文：
{context}

请返回 JSON 格式：
{
  "intent_type": "change_chart",
  "confidence": 85,
  "analysis": {
    "raw_message": "用户说的话",
    "extracted_params": {
      "target_type": "line"
    }
  }
}

只返回 JSON，不解释。"""

        user_prompt = f"""用户消息：{message}

请分类意图并提取参数。"""

        try:
            llm = LLMGateway.get_instance()
            prompt = system_prompt.format(context=json.dumps(context or {}))
            response = llm.chat_completion([
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_prompt}
            ], response_format="json")
            
            if not response:
                return None
            
            data = json.loads(response)
            intent_type = data.get("intent_type", "unknown")
            confidence = int(data.get("confidence", 0))
            analysis = data.get("analysis", {})
            analysis["raw_message"] = message
            analysis["classified_by"] = "llm"  # 标记是LLM分类的
            
            # 转换到枚举
            try:
                intent_enum = IntentType(intent_type)
                return (intent_enum, confidence, analysis)
            except ValueError:
                return None
        except Exception as e:
            # LLM分类失败，返回None让规则兜底返回unknown
            return None
    
    @classmethod
    def _calculate_confidence(cls, message: str, intent_type: IntentType, matched_pattern: str) -> int:
        """计算置信度 0-100"""
        confidence = 70  # 基础分
        
        # 关键词密度加分
        keywords = cls._get_keywords(intent_type)
        keyword_count = sum(1 for kw in keywords if kw in message)
        confidence += min(keyword_count * 5, 20)
        
        # 明确动作词加分
        action_words = ["把", "将", "请", "帮我"]
        if any(w in message for w in action_words):
            confidence += 5
        
        return min(confidence, 95)
    
    @classmethod
    def _get_keywords(cls, intent_type: IntentType) -> list:
        """获取意图关键词"""
        keywords = {
            IntentType.CHANGE_CHART: ["换", "改", "变成", "饼图", "柱图", "线图", "散点图", "表格"],
            IntentType.ADD_CHART: ["新增", "添加", "加", "插入", "再来"],
            IntentType.DELETE_CHART: ["删除", "移除", "删掉", "去掉", "删了"],
            IntentType.REORDER_CHART: ["移动", "排序", "调整", "上移", "下移", "置顶"],
            IntentType.FILTER_DRILL: ["筛选", "过滤", "只看", "下钻", "钻取", "按"],
            IntentType.ATTRIBUTION: ["为什么", "原因", "怎么回事", "分析", "归因"],
            IntentType.EDIT_TITLE: ["标题", "改名", "重命名", "名称"],
        }
        return keywords.get(intent_type, [])
    
    @classmethod
    def _extract_params(cls, message: str, intent_type: IntentType, context: Dict) -> Dict:
        """提取意图参数"""
        analysis = {
            "raw_message": message,
            "extracted_params": {}
        }
        
        if intent_type == IntentType.CHANGE_CHART:
            # 提取源图表和目标图表类型
            chart_types = ["饼图", "柱图", "柱状图", "线图", "折线图", "散点图", "表格"]
            found_types = [t for t in chart_types if t in message]
            if len(found_types) >= 2:
                analysis["extracted_params"] = {
                    "source_type": found_types[0],
                    "target_type": found_types[1]
                }
            elif len(found_types) == 1:
                analysis["extracted_params"] = {
                    "target_type": found_types[0]
                }
        
        elif intent_type == IntentType.ADD_CHART:
            # 提取要添加的图表类型
            chart_types = ["饼图", "柱图", "柱状图", "线图", "折线图", "散点图", "表格", "kpi"]
            for t in chart_types:
                if t in message:
                    analysis["extracted_params"] = {"chart_type": t}
                    break
        
        elif intent_type == IntentType.DELETE_CHART:
            # 提取要删除的图表序号或类型
            idx_match = re.search(r"第(.{1,2})(个|张|幅)", message)
            if idx_match:
                cn_nums = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
                raw = idx_match.group(1)
                chart_idx = cn_nums.get(raw) if raw in cn_nums else (int(raw) if raw.isdigit() else None)
                analysis["extracted_params"] = {"chart_index": chart_idx}
            else:
                # 按类型删除
                chart_types = ["饼图", "柱图", "柱状图", "线图", "折线图", "散点图", "表格"]
                for t in chart_types:
                    if t in message:
                        analysis["extracted_params"] = {"chart_type": t}
                        break
        
        elif intent_type == IntentType.REORDER_CHART:
            # 提取排序目标
            direction = ""
            if "上移" in message:
                direction = "up"
            elif "下移" in message:
                direction = "down"
            elif "置顶" in message:
                direction = "top"
            elif "置底" in message:
                direction = "bottom"
            analysis["extracted_params"] = {"direction": direction}
        
        elif intent_type == IntentType.FILTER_DRILL:
            # 提取筛选字段和值
            filter_match = re.search(r"(只看|筛选|过滤).{0,5}([^的\s]+)", message)
            if filter_match:
                analysis["extracted_params"] = {
                    "filter_value": filter_match.group(2)
                }
        
        elif intent_type == IntentType.ATTRIBUTION:
            # 归因分析参数
            analysis["extracted_params"] = {
                "analysis_type": "attribution",
                "requires_lineage": True
            }
        
        elif intent_type == IntentType.EDIT_TITLE:
            # 提取新标题
            title_match = re.search(r"(改成|改为|换成)\s*[""']?([^""']+)[""']?", message)
            if title_match:
                analysis["extracted_params"] = {
                    "new_title": title_match.group(2)
                }
        
        # 添加上下文信息
        if context:
            analysis["context"] = {
                "dashboard_id": context.get("dashboard_id"),
                "field_profiles": context.get("field_profiles", []),
                "current_config": context.get("current_config", {})
            }
        
        return analysis


# 便捷函数
def classify_intent(message: str, context: Dict[str, Any] = None) -> Dict:
    """
    分类意图并返回完整结果
    
    Returns:
        {
            "intent_type": "change_chart",
            "confidence": 85,
            "analysis": {...},
            "is_confident": True
        }
    """
    intent_type, confidence, analysis = IntentClassifier.classify(message, context)
    
    classified_by = analysis.get("classified_by", "rule")
    
    return {
        "intent_type": intent_type.value,
        "confidence": confidence,
        "analysis": analysis,
        "is_confident": confidence >= 70,
        "classified_by": classified_by
    }
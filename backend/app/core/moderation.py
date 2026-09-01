"""
内容审核与边界处理 - M3-04
四类边界话术：超范围/含糊反问/图库外替代/敏感
"""
from typing import Dict, Any, Tuple, Optional
from enum import Enum
import re


class BoundaryType(str, Enum):
    """边界类型"""
    OUT_OF_SCOPE = "out_of_scope"           # 超范围
    VAGUE_QUESTION = "vague_question"       # 含糊反问
    CHART_NOT_SUPPORTED = "chart_not_supported"  # 图库外替代
    SENSITIVE = "sensitive"                 # 敏感


class ContentModerator:
    """内容审核器"""
    
    # 敏感词列表 (简化版)
    SENSITIVE_WORDS = [
        "机密", "绝密", "内部资料", "泄露",
        "密码", "密钥", "token", "api_key",
    ]
    
    # 超范围话题
    OUT_OF_SCOPE_PATTERNS = [
        r"(天气|新闻|股票|彩票|星座|运势)",
        r"(写|生成).{0,5}(代码|程序|脚本)",
        r"(帮我|给我).{0,10}(买|卖|转账|支付)",
    ]
    
    # 含糊反问模式
    VAGUE_PATTERNS = [
        r"^(什么意思|怎么回事|为什么|怎么弄|然后呢)$",
        r"(不懂|不明白|不清楚|不知道).*",
        r"^(哦|嗯|啊|好吧)$",
    ]
    
    # 不支持图表类型
    UNSUPPORTED_CHARTS = [
        "3d图", "雷达图", "热力图", "地图", "桑基图",
        "词云", "树图", "漏斗图", "仪表盘"
    ]
    
    # 四类边界话术
    BOUNDARY_RESPONSES = {
        BoundaryType.OUT_OF_SCOPE: {
            "title": "超出服务范围",
            "content": "这个问题超出了我的服务范围，我只能帮您处理数据看板相关的问题。您可以问我：",
            "suggestions": [
                "把饼图改成柱图",
                "分析一下这个异常",
                "筛选华东地区的数据"
            ],
            "action": "显示帮助"
        },
        BoundaryType.VAGUE_QUESTION: {
            "title": "问题需要更明确",
            "content": "您的问题比较模糊，能再详细说明一下吗？比如：",
            "suggestions": [
                "我想把第一个图换成折线图",
                "帮我添加一个显示金额的KPI卡",
                "分析一下3月份数据下降的原因"
            ],
            "action": "引导补充"
        },
        BoundaryType.CHART_NOT_SUPPORTED: {
            "title": "图表类型暂不支持",
            "content": "您提到的图表类型我暂时还不支持，目前支持的图表有：",
            "supported_charts": ["柱状图", "折线图", "饼图", "散点图", "表格", "KPI卡"],
            "alternative": "您可以用柱状图或折线图来展示这个维度的数据",
            "action": "推荐替代"
        },
        BoundaryType.SENSITIVE: {
            "title": "内容包含敏感信息",
            "content": "检测到您的消息可能包含敏感信息，为保护数据安全，我无法处理此请求。",
            "note": "对话不会扣除Token",
            "action": "拦截提示"
        }
    }
    
    @classmethod
    def check(cls, message: str) -> Tuple[bool, Optional[BoundaryType], Optional[Dict]]:
        """
        检查内容是否需要拦截
        
        Returns:
            (should_block, boundary_type, response)
            should_block: True=拦截, False=正常处理
        """
        message_lower = message.lower().strip()
        
        # 1. 检查敏感信息
        for word in cls.SENSITIVE_WORDS:
            if word in message_lower:
                return True, BoundaryType.SENSITIVE, cls.BOUNDARY_RESPONSES[BoundaryType.SENSITIVE]
        
        # 2. 检查超范围
        for pattern in cls.OUT_OF_SCOPE_PATTERNS:
            if re.search(pattern, message_lower):
                return True, BoundaryType.OUT_OF_SCOPE, cls.BOUNDARY_RESPONSES[BoundaryType.OUT_OF_SCOPE]
        
        # 3. 检查含糊反问
        for pattern in cls.VAGUE_PATTERNS:
            if re.search(pattern, message_lower):
                return True, BoundaryType.VAGUE_QUESTION, cls.BOUNDARY_RESPONSES[BoundaryType.VAGUE_QUESTION]
        
        # 4. 检查不支持图表
        for chart in cls.UNSUPPORTED_CHARTS:
            if chart in message_lower:
                response = cls.BOUNDARY_RESPONSES[BoundaryType.CHART_NOT_SUPPORTED].copy()
                response["requested_chart"] = chart
                return True, BoundaryType.CHART_NOT_SUPPORTED, response
        
        return False, None, None
    
    @classmethod
    def is_sensitive(cls, message: str) -> bool:
        """检查是否包含敏感词"""
        message_lower = message.lower()
        return any(word in message_lower for word in cls.SENSITIVE_WORDS)


class RetryHandler:
    """发送失败重试处理器"""
    
    MAX_RETRY = 3
    
    @staticmethod
    def should_retry(error_type: str, retry_count: int) -> bool:
        """判断是否应该重试"""
        if retry_count >= RetryHandler.MAX_RETRY:
            return False
        
        # 可重试的错误类型
        retryable_errors = [
            "network_error",
            "timeout",
            "rate_limit",
            "server_error",
        ]
        
        return error_type in retryable_errors
    
    @staticmethod
    def get_retry_delay(retry_count: int) -> float:
        """获取重试延迟 (指数退避)"""
        import math
        return min(math.pow(2, retry_count), 10)  # 最大10秒


# 便捷函数
def check_moderation(message: str) -> Dict[str, Any]:
    """
    审核内容
    
    Returns:
        {
            "passed": True/False,
            "should_block": True/False,
            "boundary_type": "sensitive"/None,
            "response": {...},
            "deduct_tokens": True/False  # 是否扣Token
        }
    """
    should_block, boundary_type, response = ContentModerator.check(message)
    
    return {
        "passed": not should_block,
        "should_block": should_block,
        "boundary_type": boundary_type.value if boundary_type else None,
        "response": response,
        "deduct_tokens": boundary_type != BoundaryType.SENSITIVE if should_block else True
        # 敏感内容不扣Token
    }


def get_boundary_response(boundary_type: str) -> Dict[str, Any]:
    """获取边界响应话术"""
    try:
        bt = BoundaryType(boundary_type)
        return ContentModerator.BOUNDARY_RESPONSES.get(bt, {})
    except ValueError:
        return {}
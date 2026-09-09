"""
可行性检查 - M3-03
在执行AI动作前，检查用户需求是否可执行
- 数据粒度检查（如用户要月度，数据只有年度）
- 字段存在性检查（如用户要按区域，数据无区域字段）
- 图表类型合理性检查
"""
from typing import Dict, Any, List, Optional, Tuple


class FeasibilityChecker:
    """可行性检查器"""
    
    GRAIN_HIERARCHY = {
        "daily": ["daily", "day"],
        "weekly": ["weekly", "week"],
        "monthly": ["monthly", "month", "月度"],
        "quarterly": ["quarterly", "quarter", "季度"],
        "yearly": ["yearly", "year", "annual", "年度"],
        "row": ["row", "单笔", "交易", "detail"],
        "customer": ["customer", "客户", "user"],
        "custom": ["custom", "自定义"],
    }
    
    # 粒度层级（数值越小越细）
    GRAIN_LEVELS = {
        "daily": 1, "day": 1,
        "weekly": 2, "week": 2,
        "monthly": 3, "month": 3,
        "quarterly": 4, "quarter": 4,
        "yearly": 5, "year": 5, "annual": 5,
        "row": 0, "detail": 0,
        "customer": 1,
    }
    
    @staticmethod
    def check_request(
        user_message: str,
        action_type: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        override_blocking: bool = False
    ) -> Dict[str, Any]:
        """
        检查用户请求是否可执行
        
        Args:
            override_blocking: 当为True时，blocking级问题降级为warning，
                               允许用户强制执行（用户优先级最高）
        
        Returns:
            {
                "feasible": True/False,
                "issues": [],
                "suggestion": None,
                "adjusted_params": None,
                "can_override": False,  # 是否存在可覆盖的blocking问题
                "overridden_issues": []  # 被用户覆盖的问题列表
            }
        """
        dataset_info = context.get("dataset_info", {})
        field_profiles = dataset_info.get("field_profiles", [])
        grain = dataset_info.get("grain", "row")
        dashboard_config = context.get("current_config", {})
        charts = dashboard_config.get("charts", [])
        
        field_names = [f.get("name", f) if isinstance(f, dict) else f for f in field_profiles]
        
        issues = []
        suggestion = None
        adjusted_params = None
        
        # 1. 数据粒度检查（针对筛选/汇总/下钻类请求）
        if action_type in ("filter_drill", "change_chart", "add_chart"):
            grain_check = FeasibilityChecker._check_grain(user_message, grain)
            if grain_check:
                issues.append(grain_check)
                if not suggestion:
                    suggestion = grain_check.get("suggestion")
        
        # 2. 字段存在性检查（针对筛选/归因/换图）
        if action_type in ("filter_drill", "attribution", "change_chart", "add_chart"):
            field_check = FeasibilityChecker._check_field_existence(user_message, field_names)
            if field_check:
                issues.append(field_check)
                if not suggestion:
                    suggestion = field_check.get("suggestion")
        
        # 3. 图表数量检查（针对新增图表）
        if action_type == "add_chart":
            count_check = FeasibilityChecker._check_chart_count(charts)
            if count_check:
                issues.append(count_check)
                if not suggestion:
                    suggestion = count_check.get("suggestion")
        
        # 4. 图表删除检查（针对删除图表）
        if action_type == "delete_chart":
            del_check = FeasibilityChecker._check_delete_chart(charts, params)
            if del_check:
                issues.append(del_check)
                if not suggestion:
                    suggestion = del_check.get("suggestion")
        
        # 5. 图表类型合理性检查
        if action_type == "change_chart":
            type_check = FeasibilityChecker._check_chart_type_reasonableness(user_message, field_names, grain)
            if type_check:
                issues.append(type_check)
                if not suggestion:
                    suggestion = type_check.get("suggestion")
        
        # 用户优先级override逻辑
        blocking_issues = [i for i in issues if i.get("severity") == "blocking"]
        warning_issues = [i for i in issues if i.get("severity") != "blocking"]
        can_override = len(blocking_issues) > 0
        overridden_issues = []
        
        if override_blocking and blocking_issues:
            # 用户选择强制执行，blocking问题降级为warning
            overridden_issues = [
                {**issue, "original_severity": "blocking", "severity": "warning"}
                for issue in blocking_issues
            ]
            issues = warning_issues + overridden_issues
            # 覆盖后视为可行（仅剩warning/info级问题）
            feasible = True
        else:
            feasible = len(blocking_issues) == 0
        
        return {
            "feasible": feasible,
            "issues": issues,
            "suggestion": suggestion,
            "adjusted_params": adjusted_params,
            "can_override": can_override,
            "overridden_issues": overridden_issues
        }
    
    @staticmethod
    def _check_grain(message: str, data_grain: str) -> Optional[Dict]:
        """检查数据粒度是否满足用户需求"""
        requested_grain = None
        
        # 从消息中提取用户请求的粒度
        grain_keywords = {
            "daily": ["日", "daily", "每日", "逐日", "按日"],
            "weekly": ["周", "weekly", "每周", "按周"],
            "monthly": ["月", "monthly", "月度", "每月", "按月"],
            "quarterly": ["季", "quarterly", "季度", "每季", "按季"],
            "yearly": ["年", "yearly", "年度", "每年", "按年"],
            "customer": ["客户", "customer", "用户", "person"],
        }
        
        for grain_name, keywords in grain_keywords.items():
            if any(kw in message for kw in keywords):
                requested_grain = grain_name
                break
        
        if not requested_grain:
            return None  # 用户没有指定粒度
        
        data_level = FeasibilityChecker.GRAIN_LEVELS.get(data_grain, 0)
        request_level = FeasibilityChecker.GRAIN_LEVELS.get(requested_grain, 0)
        
        if data_level == 0 and request_level > 0:
            # 数据是行级/交易级，可以聚合
            return None  # 可行
        
        if request_level < data_level:
            # 用户要更细的粒度，但数据只有粗粒度
            grain_names = {
                "daily": "日", "weekly": "周", "monthly": "月度",
                "quarterly": "季度", "yearly": "年度", "row": "单笔交易"
            }
            data_name = grain_names.get(data_grain, data_grain)
            request_name = grain_names.get(requested_grain, requested_grain)
            
            return {
                "severity": "blocking",
                "type": "grain_mismatch",
                "message": f"当前数据粒度是{data_name}级，无法按{request_name}汇总",
                "suggestion": f"当前数据是{data_name}粒度，是否改为按{data_name}维度的分析？"
            }
        
        return None
    
    @staticmethod
    def _check_field_existence(message: str, field_names: List[str]) -> Optional[Dict]:
        """检查用户提到的字段是否存在"""
        if not field_names:
            return None
        
        # 提取用户消息中的潜在字段名
        # 常见的筛选关键词
        field_keywords = [
            "区域", "地区", "城市", "省份", "部门", "产品", "类型", "类别",
            "客户", "用户", "渠道", "日期", "时间", "月份", "年份",
            "金额", "数量", "利率", "率", "余额", "风险", "等级", "评级",
            "状态", "性别", "年龄", "学历", "职业"
        ]
        
        mentioned_fields = []
        for kw in field_keywords:
            if kw in message:
                mentioned_fields.append(kw)
        
        if not mentioned_fields:
            return None
        
        # 检查提到的是否在字段列表中
        missing_fields = []
        for mf in mentioned_fields:
            found = False
            for fn in field_names:
                if mf in fn or fn in mf:
                    found = True
                    break
            if not found:
                missing_fields.append(mf)
        
        if missing_fields:
            available = ", ".join(field_names[:8])
            missing_str = "、".join(missing_fields[:3])
            return {
                "severity": "blocking",
                "type": "field_missing",
                "message": f"数据中没有'{missing_str}'字段",
                "suggestion": f"可用的字段有：{available}，是否用这些字段分析？"
            }
        
        return None
    
    @staticmethod
    def _check_chart_count(charts: List[Dict]) -> Optional[Dict]:
        """检查图表数量是否超限"""
        if len(charts) >= 10:
            return {
                "severity": "blocking",
                "type": "chart_limit",
                "message": f"看板已有{len(charts)}个图表，达到上限(10个)",
                "suggestion": "请先删除部分图表再新增"
            }
        return None
    
    @staticmethod
    def _check_delete_chart(charts: List[Dict], params: Dict) -> Optional[Dict]:
        """检查能否删除图表"""
        if len(charts) <= 1:
            return {
                "severity": "blocking",
                "type": "min_chart_required",
                "message": "看板至少保留一个图表",
                "suggestion": "无法删除唯一的图表"
            }
        return None
    
    @staticmethod
    def _check_chart_type_reasonableness(
        message: str, field_names: List[str], grain: str
    ) -> Optional[Dict]:
        """检查图表类型合理性（仅告警，不阻断）"""
        # 用户要预测但数据不足
        if any(kw in message for kw in ["预测", "预估", "趋势预测", "未来"]):
            return {
                "severity": "warning",
                "type": "prediction_limitation",
                "message": "预测功能需要足够的历史数据支持",
                "suggestion": "当前仅展示已有数据趋势，预测结果仅供参考"
            }
        
        # 用户要饼图但数据不适合
        if "饼图" in message:
            date_fields = [f for f in field_names if any(kw in f.lower() for kw in ["日期", "时间", "date", "time"])]
            if date_fields and len(date_fields) > 0:
                return {
                    "severity": "info",
                    "type": "chart_type_hint",
                    "message": "有日期字段，饼图可能不是最佳展示方式",
                    "suggestion": "建议使用折线图展示时间趋势，是否改为折线图？"
                }
        
        return None


# 便捷函数
def check_feasibility(
    user_message: str,
    action_type: str,
    params: Dict[str, Any],
    context: Dict[str, Any],
    override_blocking: bool = False
) -> Dict[str, Any]:
    """检查可行性"""
    return FeasibilityChecker.check_request(
        user_message, action_type, params, context,
        override_blocking=override_blocking
    )
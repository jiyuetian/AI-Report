"""
意图分类器 - M3-01
5类意图：换图/新增图/筛选下钻/归因追问/标题编辑
LLM增强：规则匹配<70分时调用LLM兜底
"""
import json
import re
import asyncio
from typing import Dict, Any, Tuple, Optional, List
from enum import Enum

from app.core.llm_gateway import LLMGateway
from app.core.prompt_loader import load_prompt


# 内置默认系统提示词（外置 prompts/intent_classifier.md 缺失时的回退）
_DEFAULT_SYSTEM_PROMPT = """你是一个自然语言意图分类器，请将用户的消息分类为以下意图之一：

可用意图：
- change_chart: 修改图表类型（把饼图改成折线图等）
- add_chart: 新增一个图表
- delete_chart: 删除一个图表
- reorder_chart: 调整图表位置/排序
- filter_drill: 筛选数据、下钻分析
- attribution: 追问原因、归因分析
- edit_title: 修改标题
- unknown: 不确定

当前看板上下文：
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


class IntentType(str, Enum):
    """意图类型"""
    CHANGE_CHART = "change_chart"      # 换图
    ADD_CHART = "add_chart"            # 新增图
    DELETE_CHART = "delete_chart"      # 删图
    REORDER_CHART = "reorder_chart"    # 排序调整
    FILTER_DRILL = "filter_drill"      # 筛选下钻
    ATTRIBUTION = "attribution"        # 归因追问
    EDIT_TITLE = "edit_title"          # 标题编辑
    QUALITY_FIX = "quality_fix"        # 数据质量修复（清洗层）
    UNKNOWN = "unknown"


class IntentClassifier:
    """意图分类器"""
    
    # 意图关键词映射
    INTENT_PATTERNS = {
        IntentType.CHANGE_CHART: [
            r"(换|改|变成|换成).{0,5}(图|图表|饼图|柱图|线图|散点图|表格)",
            r"(饼图|柱图|线图|散点图).{0,3}(改|换).{0,3}(饼图|柱图|线图|散点图|表格)",
            r"(把|将|给).{0,8}?(图|图表|柱状图|柱图|饼图|线图|折线图|散点图|圆环图|环形图|表格).{0,6}(改|换|变成)(成|为)",
        ],
        IntentType.ADD_CHART: [
            r"(新增|添加|加|插入|加个|加张).{0,8}(图|图表|饼图|柱图|线图|散点图|表格|指标|业务量|KPI|卡)",
            r"(再|右边|右侧|下面|上面|旁边|追加).{0,4}(加|放|来|新增).{0,3}(个|张)?.{0,6}(图|图表|饼图|柱图|线图|散点图|表格|指标|KPI)",
            r"(能不能|帮我).{0,6}(加|添加|新增|来).{0,2}(图|图表|指标|KPI)",
            r"(新增|加|添加).{0,4}(一个|一张|个)?.{0,4}(指标|业务量|笔数|总额|KPI|kpi卡)",
            r"来\s*(一个|一张|个|张)?\s*(图|图表|饼图|柱状图|柱图|线图|折线图|散点图|圆环图|表格)",
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
            r"(只看|只查|只显示|只查看|过滤掉|排除)[^，。；]*?(的|数据|记录)?",
            r"(筛选|过滤)[^，。；]*?(的|数据)?",
            r"按.{0,4}(地区|区域|省份|城市|类别|类型|状态|分类|分组|维度).{0,6}(的|数据)?",
            r"(下钻|钻取|深入|展开).{0,5}(看|分析)?",
            r"(按|根据).{0,5}(分类|分组|维度)",
        ],
        IntentType.ATTRIBUTION: [
            r"(为什么|怎么回事|什么原因|为何).{0,10}(异常|波动|变化|下降|上升)?",
            r"(分析|解释|说明).{0,5}(原因|理由)",
            r"(分析|解释|看看|看下|说明|说下|讲下).{0,8}(一下|下|这个|这|这种)?[^，。；]{0,6}(上升|下降|异常|波动|变化|趋势|原因)",
            r"[^，。；]*?(上升|下降|异常|波动|变化|增长|骤增)的原因",
            r"(归因|溯源|追溯)",
        ],
        IntentType.EDIT_TITLE: [
            r"(改|修改|编辑|换).{0,5}(标题|名字|名称)",
            r"标题.{0,3}(改|换成|改为)",
            r"(重命名|改名)",
        ],
        IntentType.QUALITY_FIX: [
            r"(质检|质量检查|质量检测).{0,8}(发现|查出|提示)?.{0,6}(问题|重复|空值|缺失|异常|格式|错误)?",
            r"(修复|清洗|清理).{0,6}(数据|重复|空值|缺失|异常|格式|错误|问题)?",
            r"(去重|去重复|消除重复|合并重复).{0,6}(数据|记录)?",
            r"[^，。；]*?(重复|重复数据|一列多值|空值|缺失值|格式不正确|乱码).{0,6}(修复|处理|清理|去重|补全|纠正)?",
            r"(帮我|请|把).{0,4}(修复|去重|清洗|清理|补全).{0,6}(数据|重复|空值|缺失)?",
            r"(数据|字段).{0,4}(有|存在|出现).{0,4}(重复|空值|缺失|异常|格式问题)",
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
        # 外置被控提示词优先（prompts/intent_classifier.md），缺失回退内置默认
        system_prompt = load_prompt(
            "intent_classifier",
            _DEFAULT_SYSTEM_PROMPT,
            context=json.dumps(context or {}, ensure_ascii=False),
        )

        user_prompt = f"""请分类意图并提取参数。"""

        try:
            from app.core.llm_gateway import get_llm_gateway, LLMRequest
            prompt = system_prompt
            prompt += f"\n用户消息：{message}\n{user_prompt}"

            # 可能在 async 事件循环内被同步调用，用独立线程跑 asyncio.run 避免冲突
            import concurrent.futures
            request = LLMRequest(
                prompt=prompt,
                json_mode=True,
                max_tokens=500,
                temperature=0.2
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(
                    lambda r: asyncio.run(get_llm_gateway().chat_complete(r)),
                    request
                )
                response = future.result(timeout=40)
            if not response or not response.success or not response.content:
                return None

            data = response.response_json or json.loads(response.content)
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
        except Exception:
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
            IntentType.QUALITY_FIX: ["质检", "修复", "去重", "重复", "清洗", "空值", "缺失"],
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
            # 提取要添加的图表类型（优先具体图表类型，如"饼图"）
            chart_types = ["饼图", "柱图", "柱状图", "线图", "折线图", "散点图", "表格"]
            kpi_keywords = ["指标", "业务量", "笔数", "总额", "kpi", "KPI", "金额", "余额", "数量"]
            is_kpi = any(kw in message for kw in kpi_keywords) and not any(t in message for t in chart_types)
            if is_kpi:
                analysis["extracted_params"] = {"chart_type": "kpi"}
                # 尝试提取指标名（如"借据总笔数"）
                m = re.search(r"(新增|添加|加)\s*(?:一个|一张|个)?([^，。；\s]{2,16}?(?:指标|笔数|总额|金额|余额|数量|KPI|kpi))", message)
                if not m:
                    m = re.search(r"([^，。；\s]{2,16}?(?:指标|笔数|总额|金额|余额|数量))", message)
                if m:
                    analysis["extracted_params"]["metric_name"] = m.group(1).lstrip("新增添加加个一张和")
                if analysis["extracted_params"].get("metric_name") in (None, ""):
                    analysis["extracted_params"]["metric_name"] = "新增指标"
            else:
                for t in chart_types:
                    if t in message:
                        analysis["extracted_params"] = {"chart_type": t}
                        break

            # 尝试提取指标名（如"借据总笔数""担保总额"）
            metric_raw = ""
            mm = re.search(r"([一-龥A-Za-z_]*)(总笔数|总金额|总额|笔数|金额|余额|数量)", message)
            if mm:
                metric_raw = mm.group(1) + mm.group(2)
                for stop in ("新增", "添加", "看板", "指标", "一个", "一张", "加", "和"):
                    metric_raw = metric_raw.replace(stop, "")
            metric_name = metric_raw or analysis["extracted_params"].get("metric_name") or "新增指标"
            # 清除括在指标名里的非指标残留
            metric_name = metric_name.strip("新增添加加个一张和看板指标完")
            if not metric_name:
                metric_name = "新增指标"
            analysis["extracted_params"]["metric_name"] = metric_name
        
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
            filter_match = re.search(r"(只看|只查看|只显示|筛选|过滤|聚焦)[^，。；]*?(地区|区域|省份|城市|类别|类型|状态|分类)", message)
            val_match = re.search(r"(只看|只查看|只看|只显示|筛选|过滤|聚焦)\s*([^，。；的\s]{2,16}?(?:省|市|区|县|类别|类型|状态))", message)
            if filter_match:
                analysis["extracted_params"] = {
                    "filter_field": filter_match.group(2),
                    "filter_value": None
                }
                # 提取具体值（如"华东""杭州"）
                m = re.search(r"(只看|只查看|只显示|筛选|过滤|聚焦)([^，。；的\s]{1,12}?)[的地区省市区]", message)
                if m:
                    analysis["extracted_params"]["filter_value"] = m.group(2)
            elif val_match:
                analysis["extracted_params"] = {
                    "filter_field": None,
                    "filter_value": val_match.group(2)
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

        elif intent_type == IntentType.QUALITY_FIX:
            # 数据质量修复：提取问题类型、目标列、修复策略
            ep = {}
            # 问题类型
            if re.search(r"重复|去重|一列多值", message):
                ep["issue_type"] = "duplicate"
            elif re.search(r"空值|缺失|null|为空", message):
                ep["issue_type"] = "null"
            elif re.search(r"格式|日期|乱码|不正确", message):
                ep["issue_type"] = "format"
            elif re.search(r"异常|越界|超范围", message):
                ep["issue_type"] = "anomaly"
            else:
                ep["issue_type"] = "duplicate"  # 默认按重复处理

            # 目标列（如"借据号""借据编号"）——优先匹配"XX号/编号"
            col_match = re.search(r"([一-龥A-Za-z_]{1,8}?(?:号|编号|序号|类型|日期|状态))", message)
            if col_match:
                col = col_match.group(1)
                for noise in ("质检", "发现", "检查", "清洗", "修复", "有", "后", "异常", "问题", "重复", "缺失", "空值", "帮我", "请", "的"):
                    col = col.replace(noise, "")
                ep["column"] = col
            elif "借据" in message:
                ep["column"] = "借据号"
            else:
                ep["column"] = ""

            # 修复策略
            if "去重" in message:
                ep["fix_strategy"] = "keep_first"
            else:
                ep["fix_strategy"] = "keep_first"

            analysis["extracted_params"] = ep
        
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
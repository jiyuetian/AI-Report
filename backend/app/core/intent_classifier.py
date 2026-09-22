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

"注意：纠正类消息（'不是 A 是 B'/'我指的是…'）仍按原始意图分类，不要改成 unknown；"
"若原意图是加图/换图，继续判为 add_chart/change_chart。\n"
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
    ADD_CONCLUSION = "add_conclusion"  # 追加结论/总结（2026-09-18 新增：复合指令「改标题+补结论」必需）
    QUALITY_FIX = "quality_fix"        # 数据质量修复（清洗层）
    CHART_FIX = "chart_fix"            # 图表问题诊断/修复（空图、没数据）
    UNKNOWN = "unknown"


# 中文/英文引号集合：标题抽取必须同时支持，老实现只认弯引号 ""''，
# 导致「标题改成『客户风险画像』并补充结论」把整句当标题。
_QUOTE_CHARS = "\"'“”‘’《》〈〉「」『』【】[]"

# 复合指令连接词：标题/结论抽取遇到这些词必须截断
_CLAUSE_BOUNDARY = r"[，。；！？、]|并且|并|同时|然后|接着|而且|另外|还有|再|以及"


def clean_title_keyword(kw: str) -> str:
    """把「转化率那张」这类带噪声的删除/改图定位词清洗成可匹配的标题关键词。

    老实现直接把「删除转化率那张图」里「图」之前的整段当 title_keyword，
    得到「转化率那张」，执行器用 `kw in title` 永远匹配不到，
    于是 DELETE_CHART 静默回退到"删最后一张"——这就是"删错图/误删"的根因。
    """
    if not kw:
        return ""
    # 去掉前缀指令词
    kw = re.sub(r"^(删?除|移除|去掉|删掉|删了|不要|不需要|把|将|那个|这个|那张|这张|第[一二三四五六七八九十\d]{1,2}[个张幅])\s*", "", kw)
    # 去掉后缀噪声（可重复）
    for _ in range(4):
        new = re.sub(r"(那张|这张|那个|这个|张|个|幅|图表|图|的|那|这|一份|一项)$", "", kw).strip()
        if new == kw:
            break
        kw = new
    return kw.strip(" 的")


def extract_clean_title(message: str) -> str:
    """从「标题改成XX」「把标题改为XX」里精确抽出新标题，绝不把整句当标题。"""
    if not message:
        return ""
    parts = re.split(r"(?:改成|改为|换成|改叫|命名为|重命名为|设置成|设为)", message, maxsplit=1)
    if len(parts) < 2:
        return ""
    tail = parts[1]
    # 遇到分句/连接词立即截断
    tail = re.split(_CLAUSE_BOUNDARY, tail, maxsplit=1)[0]
    # 去引号
    tail = tail.strip().strip(_QUOTE_CHARS).strip()
    return tail


class IntentClassifier:
    """意图分类器"""
    
    # 意图关键词映射
    INTENT_PATTERNS = {
        # 2026-09-18 新增：必须排在 ADD_CHART 之前，否则「补充一段结论」里的"加"
        # 会被 ADD_CHART 的"(新增|添加|加|插入)"抢走，导致补结论动作被丢弃。
        IntentType.ADD_CONCLUSION: [
            r"(追加|补充|添加|加上|加|写上|写|生成|来|给)\s*[^，。；！？]{0,10}?(一段|一句|一个)?\s*(结论|总结|小结|洞察|分析结论)",
            r"(结论|总结|小结|洞察)\s*(追加|补充|加上|写|生成|来一段|来一句)",
            r"在\s*(末尾|最后|底部|下面|结尾)\s*[^，。；]{0,8}?(追加|补充|加上|写|生成)\s*[^，。；]{0,10}?(结论|总结|小结)",
        ],
        IntentType.CHANGE_CHART: [
            r"(换|改|变成|换成).{0,20}(图|图表|饼图|柱图|线图|散点图|表格)",
            r"(饼图|柱图|线图|散点图).{0,12}(改|换).{0,12}(饼图|柱图|线图|散点图|表格)",
            r"(把|将|给).{0,20}?(图|图表|柱状图|柱图|饼图|线图|折线图|散点图|圆环图|环形图|表格).{0,12}(改|换|变成)(成|为)",
        ],
        IntentType.ADD_CHART: [
            # 新增/添加/加/插入/来个 + 可选量词 + 任意描述(维度/指标/占比, 放宽间隙至30) + 图型词
            r"(新增|添加|再加|加|插入|来个|来一张)\s*(?:一?\s*个|一?\s*张|些)?\s*[^，。；！？]{0,30}?(饼图|柱状图|柱图|条形图|直方图|线图|折线图|散点图|圆环图|环形图|表格|图|图表|指标卡|kpi|KPI)",
            # 再/右边等方位词 + 加/新增 + 图型词
            r"(再|右边|右侧|下面|上面|旁边|追加)\s*(?:一?\s*个|一?\s*张)?\s*(加|放|来|新增)\s*[^，。；]{0,12}?(图|图表|饼图|柱状图|柱图|线图|折线图|散点图|表格|指标|KPI)",
            # 帮我/能不能 + 加图
            r"(能不能|帮我|请帮我)\s*[^，。；]{0,8}?(加|添加|新增|来)\s*[^，。；]{0,12}?(图|图表|指标|KPI)",
            # 新增/加 + 指标类名词(无图型词也识别为加指标图)
            r"(新增|添加|加|插入)\s*[^，。；]{0,20}?(指标|业务量|笔数|总额|总数|余额|金额|数量)\s*(?:指标|卡|KPI)?",
            # 来 + 量词 + 图型词
            r"来\s*(一个|一张|个|张)?\s*(图|图表|饼图|柱状图|柱图|线图|折线图|散点图|圆环图|表格)",
            # 2026-09-18：「把不存在的字段做成饼图」此前 ADD_CHART 识别不到（没有"新增/添加"），
            # 直接落到 UNKNOWN 走 LLM 闲聊，用户得不到"字段不存在"的明确拦截。
            r"(把|用|将|拿|对)\s*[^，。；]{0,20}?(做成|做成|画成|画个|画|生成|来个|做成一张|来一张)\s*(饼图|柱状图|柱图|条形图|直方图|线图|折线图|散点图|圆环图|环形图|表格|图|图表)",
            # 2026-09-21 问题2：加上/新增 + （多字段列举，允许逗号）+ 平均值/均值/汇总
            # → 识别为加图（用户「加上每个：A，B，C 的平均值汇总」此前无图型词/指标词，被漏判为 unknown）。
            # 用 .{0,80}? 跨逗号匹配字段列举；必须含动作动词(新增/添加/加/插入/来个/来一张)与聚合词(平均值/均值/平均/汇总)。
            r"(新增|添加|加|插入|来个|来一张).{0,80}?(平均值|均值|平均|汇总|平均汇总)",
            # 2026-09-22 N1-D1：纠正/泛指类新增（无动作动词，靠泛指量词+聚合词识别）。
            # 「我指的是每一项的平均值」此前无动作动词 → 落 UNKNOWN/LLM 臆造 4 张 bar；
            # 现用泛指量词(每一项/每个/各/所有/全部/各项) + 聚合词(平均/均值/汇总)直接判 ADD_CHART。
            r"(每一项|每一个|每个|各个|各|所有|全部|这些|那些|各项)\s*[^，。；]{0,15}?(平均值|均值|平均|汇总|平均汇总)",
        ],
        IntentType.DELETE_CHART: [
            r"(删除|移除|去掉|删掉|删了).{0,20}(图|图表|这个|那个|第.{1,2}个)",
            r"把.{0,20}(删掉|删了|删除|移除)",
            r"(不要|不需要|去掉).{0,12}(图|图表)",
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
        # 图表问题诊断/修复：必须排在 QUALITY_FIX 之前，
        # 否则「修复这张图」会被数据清洗规则抢走，落不到图表修复上
        IntentType.CHART_FIX: [
            r"(图|图表|饼图|柱图|柱状图|线图|折线图)[^，。；]{0,10}(是)?(空的|没数据|没有数据|无数据|空白|不显示|显示不出来|画不出来|出不来)",
            r"(为什么|咋|怎么|为啥)[^，。；]{0,8}(图|图表)[^，。；]{0,8}(空|没数据|没有数据|无数据)",
            r"(修|修复|处理|解决|弄)[^，。；]{0,6}(一下|下)?(这个|这张|该|那个)?(空)?(图|图表)",
            r"(图|图表)[^，。；]{0,6}(坏|错了|有问题|不对)",
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

            # 问题2 修复（Layer2）：LLM 直接返回的字段名可能带「每个：」前缀或表述差异，
            # 执行前用 _match_field 规范化成真实字段名，避免执行器报「匹配不到字段」。
            fps = (context.get("dataset_info") or {}).get("field_profiles") or context.get("field_profiles") or []
            if fps:
                analysis = cls._canonicalize_analysis(analysis, fps)

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
            IntentType.ADD_CONCLUSION: ["结论", "总结", "小结", "洞察", "追加", "补充"],
            IntentType.QUALITY_FIX: ["质检", "修复", "去重", "重复", "清洗", "空值", "缺失"],
            IntentType.CHART_FIX: ["图是空的", "图表空", "图没数据", "空图", "修图", "图有问题"],
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
            # 2026-09-18 修复："把地区分布 换成饼图"这类带图表名的换图指令，
            # 此前只提取目标类型，执行器找不到图就退化为"改第一张"（常误改 KPI 卡）。
            # 现在把「换成/改成/变为」前的非类型词提取为图表名，供执行器按标题精确定位。
            tm = re.search(
                r"(?:把|将)?\s*([^，。；！？\s]{2,20}?)\s*(?:换成|改成|改为|变为|变成|换为)",
                message,
            )
            if tm:
                title_kw = tm.group(1).strip().strip("\"'“”「」《》")
                generic = ("图表", "图", "它", "这个", "那个", "第一个", "最后一个")
                if title_kw and title_kw not in chart_types and title_kw not in generic:
                    analysis["extracted_params"]["title_keyword"] = clean_title_keyword(title_kw)
            # 2026-09-18 新增：时间粒度（"按月聚合的折线图"）
            # 老实现完全丢弃"按月"，用户说完之后图表仍是原粒度，看上去"没改对"。
            grain = None
            for kw, g in (("按月", "month"), ("每月", "month"), ("月度", "month"), ("按月份", "month"),
                          ("按天", "day"), ("每天", "day"), ("按日", "day"), ("按周", "week"),
                          ("按季度", "quarter"), ("按季", "quarter"), ("按年", "year"), ("每年", "year"), ("年度", "year")):
                if kw in message:
                    grain = g
                    break
            if grain:
                analysis["extracted_params"]["time_grain"] = grain
        
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

            # === 增强：LLM/规则结构化提取多图（带真实字段），支持顿号拆分 ===
            fps = (context.get("dataset_info") or {}).get("field_profiles") or context.get("field_profiles") or []
            if fps:
                charts_spec = cls._extract_add_charts(message, fps)
                if charts_spec:
                    analysis["extracted_params"]["charts"] = charts_spec
                    analysis["extracted_params"]["chart_type"] = charts_spec[0]["chart_type"]
                    analysis["extracted_params"]["metric_name"] = charts_spec[0]["title"]
                    analysis["extracted_params"]["classified_by"] = "llm_add_chart"

        elif intent_type == IntentType.DELETE_CHART:
            # 2026-09-18 修复：①支持"删掉所有图"的语义识别（此前只删最后一张，还误判）；
            # ②标题关键词清洗（去掉"那张/这个/的"等噪声），否则匹配不到会静默回退删最后一张。
            if re.search(r"(删掉|删除|移除|去掉|清空|清掉|干掉)\s*(所有|全部|一切)?\s*(的)?\s*(图|图表)?\s*$", message) and re.search(r"(所有|全部|一切)", message):
                analysis["extracted_params"] = {"delete_all": True}
            elif re.search(r"(所有|全部|一切)\s*(的)?\s*(图|图表)", message) and re.search(r"(删|去掉|移除|清空)", message):
                analysis["extracted_params"] = {"delete_all": True}
            else:
                # 提取要删除的图表序号或类型
                idx_match = re.search(r"第(.{1,2})(个|张|幅)", message)
                if idx_match:
                    cn_nums = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
                    raw = idx_match.group(1)
                    chart_idx = cn_nums.get(raw) if raw in cn_nums else (int(raw) if raw.isdigit() else None)
                    analysis["extracted_params"] = {"chart_index": chart_idx}
                else:
                    chart_types = ["饼图", "柱图", "柱状图", "线图", "折线图", "散点图", "表格", "图表", "图"]
                    title_keyword = ""
                    matched_type = ""
                    for t in chart_types:
                        if t in message:
                            matched_type = t
                            pos = message.rfind(t)
                            prefix = message[:pos].strip()
                            prefix = re.sub(r"^(删?除|移除|去掉|删掉|删了|不要|不需要)\s*", "", prefix)
                            title_keyword = clean_title_keyword(prefix.strip(" 的"))
                            break
                    params = {}
                    if matched_type and matched_type not in ("图表", "图"):
                        params["chart_type"] = matched_type
                    if title_keyword:
                        params["title_keyword"] = title_keyword
                    analysis["extracted_params"] = params
        
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
            # 2026-09-18 修复：老正则 (改成|改为|换成)\s*[""']?([^""']+)[""']?
            # 只排除弯引号，且 ([^""']+) 贪婪吃到句尾 —— 于是
            # 「标题改成『客户风险画像』并补充一段结论」整句被当成新标题。
            # 现改为：按"改成/改为/…"切分 → 遇到分句/连接词截断 → 去各类引号。
            new_title = extract_clean_title(message)
            if new_title:
                analysis["extracted_params"] = {
                    "new_title": new_title,
                    # 图表标题 vs 看板标题：出现"图表/这张图/第N张"时改的是图表标题
                    "scope": "chart" if re.search(r"(图|图表|这张|那张|第[一二三四五六七八九十\d]{1,2}[张个])", message) else "dashboard",
                }

        elif intent_type == IntentType.ADD_CONCLUSION:
            # 追加结论：只记录位置与来源约束，正文由 action_executor 基于真实字段生成
            position = "end"
            if re.search(r"(开头|最前面|顶部|上面)", message):
                position = "start"
            analysis["extracted_params"] = {
                "position": position,
                "require_real_fields": True,
            }

        elif intent_type == IntentType.CHART_FIX:
            # 图表问题诊断/修复：提取图表标题 + 用户选择的处理方案
            ep = {}
            # 图表标题：优先「《》/引号」包裹，其次「XX图/XX分布/XX趋势」这类命名
            tm = re.search(r"[《\"'“”「]([^》\"'“”」]{2,30})[》\"'“”」]", message)
            if tm:
                ep["chart_title"] = tm.group(1)
            else:
                tm2 = re.search(r"([一-龥A-Za-z0-9]{2,20}(?:分布|趋势|占比|构成|对比|情况|统计|图))", message)
                if tm2:
                    ep["chart_title"] = tm2.group(1)

            # 处理方案（用户回复选了哪一项）
            if re.search(r"(删除|去掉|移除|删掉)", message):
                ep["fix_strategy"] = "drop"
            elif re.search(r"(众数|出现最多|最多的值)", message):
                ep["fix_strategy"] = "fill_mode"
            elif re.search(r"(中位数)", message):
                ep["fix_strategy"] = "fill_median"
            elif re.search(r"(填充|填成|填为|改成|换成|未知|补上|补全)", message):
                ep["fix_strategy"] = "fill_constant"
                fm = re.search(r"(?:填成|填为|改成|换成|填充为|填)\s*[:：]?\s*([^\s，。；]{1,10})", message)
                if fm:
                    ep["fill_value"] = fm.group(1)

            analysis["extracted_params"] = ep

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

    # ============ ADD_CHART 结构化提取（LLM 优先 + 规则兜底）============
    _CHART_TYPE_ALIAS = {
        "饼图": "pie", "柱图": "bar", "柱状图": "bar", "条形图": "bar",
        "直方图": "bar", "环形图": "pie", "圆环图": "pie",
        "线图": "line", "折线图": "line", "曲线图": "line",
        "散点图": "scatter", "散点": "scatter", "表格": "table", "表": "table",
        "kpi": "kpi", "KPI": "kpi", "指标卡": "kpi", "指标": "kpi",
        "pie": "pie", "bar": "bar", "line": "line", "scatter": "scatter", "table": "table",
    }

    @classmethod
    def _normalize_chart_type(cls, t: str) -> str:
        if not t:
            return "bar"
        return cls._CHART_TYPE_ALIAS.get(t, t)

    @classmethod
    def _field_names(cls, field_profiles):
        names = []
        for fp in field_profiles:
            nm = fp.get("name") or fp.get("column") or ""
            if nm:
                names.append(nm)
        return names

    @classmethod
    def _is_numeric_profile(cls, fp) -> bool:
        ftype = (fp.get("type") or fp.get("dtype") or "").upper()
        return any(t in ftype for t in ("DECIMAL", "DOUBLE", "FLOAT", "INT", "BIGINT", "NUMERIC", "REAL", "NUMBER", "DEC"))

    @classmethod
    def _match_field(cls, candidate, field_profiles, expect_role):
        """把候选词映射到真实字段名：精确 → 子串包含 → 按角色回退第一个字段。"""
        cand = (candidate or "").strip()
        names = cls._field_names(field_profiles)
        if cand in names:
            return cand
        if cand:
            for fp in field_profiles:
                nm = fp.get("name") or fp.get("column") or ""
                if cand in nm or nm in cand:
                    return nm
        for fp in field_profiles:
            nm = fp.get("name") or fp.get("column") or ""
            if not nm:
                continue
            if expect_role == "metric" and cls._is_numeric_profile(fp):
                return nm
            if expect_role == "dim" and not cls._is_numeric_profile(fp):
                return nm
        return ""

    @classmethod
    def _build_field_prompt(cls, field_profiles):
        lines = []
        for fp in field_profiles[:40]:
            nm = fp.get("name") or fp.get("column") or ""
            role = "数值" if cls._is_numeric_profile(fp) else "文本/分类"
            lines.append(f"- {nm}（{role}）")
        return "\n".join(lines) if lines else "（无字段信息）"

    @classmethod
    def _llm_extract_add_charts(cls, message, field_profiles):
        """LLM 结构化提取多图（带真实字段）。失败返回 None。"""
        if not field_profiles:
            return None
        field_text = cls._build_field_prompt(field_profiles)
        system_prompt = (
            "你是一个 BI 图表配置助手。用户会在看板对话里要求新增图表。\n"
            "请根据用户的自然语言，从给定字段画像中结构化输出要新增的图表列表。\n\n"
            "字段画像（name 是真实字段名，必须原样引用，不得臆造）：\n"
            f"{field_text}\n\n"
            "要求：\n"
            "1. 支持一次性新增多张图（用户用顿号/、或并列列举时拆成多张）。\n"
            "2. 每张图必须选择真实存在的 dimension_field（分类/文本字段）和 metric_field（数值字段）。\n"
            "3. chart_type 取值：pie(饼图)/bar(柱图)/line(折线图)/scatter(散点图)/table(表格)/kpi(指标卡)。\n"
            "4. title 简洁准确（如'产品销售分布'），不要用'新增'前缀。\n"
            "5. 只输出 JSON 数组，不要任何解释。\n"
            "6. 泛指展开：当用户说'每一项/每个/所有 X'或'各项/各指标'时，遍历 field_profiles 中"
            "**所有匹配 X 的数值字段**，逐个产出一张图（不要只出 1 张，也不要合并成 1 张）。\n"
            "7. 聚合口径：当用户说'平均值/均值/平均'时，该图必须带 \"aggregation\":\"avg\""
            "（KPI 卡显示均值而非求和）；未提聚合词默认 \"sum\"。\n"
            "8. 纠正理解：当用户说'不是 A 是 B'或'我指的是…'等纠正时，先判断这仅是改参数"
            "（口径/图型/字段），若是，只返回参数修正后的图表配置，不要重新生成整套不相关的图表。"
            "你是主导，可以自由决定图型、数量和顺序，不要被任何规则限制。\n\n"
            "输出示例：\n"
            '[{"title":"产品销售分布","chart_type":"pie","dimension_field":"产品名称","metric_field":"销售金额","aggregation":"sum"},'
            '{"title":"各产品平均值","chart_type":"kpi","dimension_field":"","metric_field":"销售金额","aggregation":"avg"}]'
        )
        user_prompt = f"用户要求：{message}\n请输出图表配置 JSON 数组。"
        try:
            from app.core.llm_gateway import get_llm_gateway, LLMRequest
            request = LLMRequest(
                prompt=system_prompt + "\n" + user_prompt,
                json_mode=True,
                max_tokens=900,
                temperature=0.2,
            )
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                response = ex.submit(
                    lambda r: asyncio.run(get_llm_gateway().chat_complete(r)),
                    request,
                ).result(timeout=40)
            if not response or not response.success or not response.content:
                return None
            data = response.response_json or json.loads(response.content)
            if not isinstance(data, list):
                return None
            charts = []
            for item in data[:6]:
                if not isinstance(item, dict):
                    continue
                ct = cls._normalize_chart_type(item.get("chart_type", "bar"))
                dim = cls._match_field(item.get("dimension_field") or "", field_profiles, "dim")
                metric = cls._match_field(item.get("metric_field") or "", field_profiles, "metric")
                title = (item.get("title") or "").strip() or f"{dim or '数据'}分布"
                agg = item.get("aggregation") or None
                charts.append({
                    "title": title,
                    "chart_type": ct,
                    "dimension_field": dim,
                    "metric_field": metric,
                    "aggregation": agg,
                })
            return charts if charts else None
        except Exception:
            return None

    @classmethod
    def _rule_extract_add_charts(cls, message, field_profiles):
        """规则兜底：顿号拆分多图 + 维度/指标关键词匹配字段画像。

        2026-09-22 N1-D1 泛指展开：消息含泛指量词(每一项/每个/各/所有/全部/各项)
        且含聚合词(平均值/均值/平均/汇总)时，遍历数据集**所有数值字段**，
        逐个产出一张 KPI 卡(aggregation=avg)——即"各项平均值"=每个指标各出一张均值卡。
        早于逐子句拆分，避免只命中单个点名字段而漏掉"等"的其余字段。
        """
        import re
        # ---- N1-D1 泛指展开（早于逐子句拆分）----
        _GEN = re.compile(r"(每一项|每一个|每个|各个|各|所有|全部|这些|那些|各项|各指标|各字段|各维度)")
        _AGG = re.compile(r"(平均值|均值|平均|汇总|平均汇总)")
        if _GEN.search(message) and _AGG.search(message):
            nums = [fp for fp in field_profiles if cls._is_numeric_profile(fp)]
            expanded = []
            for fp in nums:
                nm = fp.get("name") or fp.get("column") or ""
                if not nm:
                    continue
                expanded.append({
                    "title": f"{nm}平均值",
                    "chart_type": cls._normalize_chart_type("kpi"),
                    "dimension_field": "",
                    "metric_field": nm,
                    "aggregation": "avg",
                })
            if expanded:
                return expanded
        parts = re.split(r'[、，,；;与及和]+', message)
        parts = [p.strip() for p in parts if p.strip()]
        dim_keywords = ["产品", "地区", "区域", "省份", "城市", "类型", "类别", "分类",
                        "状态", "渠道", "部门", "客户", "月份", "年份", "季度", "性别", "等级", "业务"]
        metric_keywords = ["销售额", "销售", "金额", "余额", "数量", "笔数", "总额", "总数",
                           "均值", "平均", "占比", "收入", "利润", "成本", "额度"]
        charts = []
        for p in parts:
            ct = None
            for t in ["饼图", "柱图", "柱状图", "条形图", "直方图", "线图", "折线图", "散点图", "环形图", "圆环图", "表格"]:
                if t in p:
                    ct = t
                    break
            # 问题2 修复：优先把「子句中命中的真实数值字段」当作指标（合规率类字段本身就是数值指标），
            # 避免被维度/指标关键词噪声误导（如「业务」维度词误把合规率当维度导致 metric 为空、
            # 或「均值」关键词回退到首个数值字段而非真实字段）。仅当子句无真实数值字段时，
            # 才走原有维度/指标关键词匹配（处理「地区分布柱状图」类表述）。
            _mf = cls._match_field(p, field_profiles, "metric")
            _mf_fp = next((fp for fp in field_profiles
                           if (fp.get("name") or fp.get("column")) == _mf), None)
            if _mf and cls._is_numeric_profile(_mf_fp or {}):
                is_avg = bool(re.search(r"(平均值|均值|平均|汇总|平均汇总)", p))
                metric = _mf
                dim = ""
                title = f"{_mf}平均值" if is_avg else _mf
                ct = "kpi" if is_avg else (ct or "bar")
            else:
                dim = ""
                for k in dim_keywords:
                    if k in p:
                        dim = cls._match_field(k, field_profiles, "dim")
                        if dim:
                            break
                metric = ""
                # 取子句中位置最靠后的指标关键词（如"产品销售数量分布"应取"数量"而非"销售"）；同位取更长词
                matched = [(p.find(k), len(k), k) for k in metric_keywords if k in p]
                if matched:
                    metric = cls._match_field(max(matched)[2], field_profiles, "metric")
            # 仅当该子句含图型或维度/指标，才视为一个新增图请求
            if ct or dim or metric:
                title = p
                # 去掉开头的指令前缀（含冒号，注意不能先拆"再加工"否则残留"再工"）
                title = re.sub(
                    r'^(?:再)?\s*(?:加工|新增|添加|加|来)\s*(?:一个|一张|个|张)?\s*'
                    r'(?:饼图|柱图|柱状图|条形图|直方图|线图|折线图|散点图|环形图|圆环图|表格)?\s*[：: ]*',
                    '', title
                )
                # 去掉结尾的图型词
                title = re.sub(r'(饼图|柱图|柱状图|条形图|直方图|线图|折线图|散点图|圆环图|环形图|表格|指标卡|kpi|KPI|图)$',
                               '', title, flags=re.I)
                # 2026-09-18：规则兜底的标题会残留"按客户风险等级的"这类前缀/助词，
                # 去掉"按/把/用/将/拿/对"前缀与结尾"的/了/来"，得到干净的图表名。
                title = re.sub(r'^(?:按|把|用|将|拿|对|根据|按照)\s*', '', title.strip())
                title = re.sub(r'(?:的|了|来)$', '', title.strip())
                title = title.strip('：: ').strip()
                title = title or (dim and f"{dim}分布") or "新图表"
                charts.append({
                    "title": title,
                    "chart_type": cls._normalize_chart_type(ct or "pie"),
                    "dimension_field": dim,
                    "metric_field": metric,
                    "aggregation": "avg" if is_avg else None,
                })
        # 问题2 修复（Change C）：上述按子句拆图全空时，兜底——若消息含聚合/统称词
        # （平均值/均值/平均/汇总/每个/所有/各）且列举了真实字段名，则按「每个字段的均值」生成一张图。
        # 直接对字段画像做子串扫描，避免「加上每个：A，B，C，D，E 的平均值汇总」被漏判（裸字段无图型/指标词）。
        if not charts:
            agg = re.search(r"(平均值|均值|平均|汇总|平均汇总|每个|所有|各|这些|全部)", message)
            if agg and field_profiles:
                seen = set()
                for fp in field_profiles:
                    nm = fp.get("name") or fp.get("column") or ""
                    if not nm or nm in seen:
                        continue
                    seen.add(nm)
                    if nm in message or message in nm:
                        is_avg = bool(re.search(r"(平均值|均值|平均|汇总|平均汇总)", message))
                        charts.append({
                            "title": f"{nm}平均值" if is_avg else nm,
                            "chart_type": cls._normalize_chart_type("kpi" if is_avg else "bar"),
                            "dimension_field": "",
                            "metric_field": nm,
                            "aggregation": "avg" if is_avg else None,
                        })
        return charts if charts else None

    @classmethod
    def _canonicalize_analysis(cls, analysis, field_profiles):
        """问题2 修复（Layer2）：把 LLM 返回的 analysis 中的字段名规范化成真实字段名。

        覆盖 extracted_params 的 dimension_field/metric_field，以及 charts[] 列表里每项的同名字段。
        LLM 路径此前直接采用原始 JSON、从不调用 _match_field，导致「每个：业务流程合规率」等
        带前缀的候选名到执行器仍匹配不到（问题2 匹配失败根因之一）。
        """
        def _fix(v, role):
            return cls._match_field(v, field_profiles, role) if v else v

        ep = analysis.get("extracted_params") or {}
        if isinstance(ep, dict):
            for k, role in (("dimension_field", "dim"), ("metric_field", "metric"),
                            ("value_field", "metric"), ("y_field", "metric")):
                if ep.get(k):
                    ep[k] = _fix(ep[k], role)
            charts = ep.get("charts")
            if isinstance(charts, list):
                for c in charts:
                    if not isinstance(c, dict):
                        continue
                    if c.get("dimension_field"):
                        c["dimension_field"] = _fix(c["dimension_field"], "dim")
                    if c.get("metric_field"):
                        c["metric_field"] = _fix(c["metric_field"], "metric")
        return analysis

    @classmethod
    def _extract_add_charts(cls, message, field_profiles):
        """ADD_CHART 结构化提取：规则优先（多字段确定性），LLM 兜底。

        2026-09-21 修复（1.4 多字段截断）：此前 LLM 优先，当消息含
        「A，B，C，D，E 的平均值汇总」这类多字段列举时，LLM 常把 5 字段合并成 1 张图
        → 用户看到"5 字段只识别 1 个"。规则提取 `_rule_extract_add_charts` 能确定性地
        按列举字段产出 N 张图，故当规则产出 ≥2 张时直接采用，避免 LLM 合并。
        单图/常规表述（规则 ≤1 张）仍走 LLM 优先，保留其灵活性。
        """
        rule = cls._rule_extract_add_charts(message, field_profiles)
        if rule and len(rule) >= 2:
            return rule
        llm = cls._llm_extract_add_charts(message, field_profiles)
        if llm:
            return llm
        return rule


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
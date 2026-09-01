"""
S2 目标生成器 - M2-04
生成6个候选分析目标（含中文业务化表述）
Prompt模板v1入库
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.core.brain_config_manager import BrainConfigManager
from app.core.llm_gateway import llm_chat


@dataclass
class AnalysisGoal:
    """分析目标"""
    goal_id: str
    title: str
    description: str
    type: str  # KPI/趋势/对比/分布/预警/画像/关联
    priority: int = 1  # 优先级 1-10
    expected_charts: List[str] = None
    
    def to_dict(self) -> Dict:
        result = {
            "goal_id": self.goal_id,
            "title": self.title,
            "description": self.description,
            "type": self.type,
            "priority": self.priority
        }
        if self.expected_charts:
            result["expected_charts"] = self.expected_charts
        return result


class S2GoalGenerator:
    """
    S2 目标生成器
    
    功能：
    1. 基于主题和数据特征生成6个候选分析目标
    2. 目标为中文业务化表述，避免技术术语
    3. 包含KPI/趋势/对比/分布/预警/画像/关联等类型
    4. 基于规则的快速生成（无需LLM）
    5. 基于LLM的增强生成（可选）
    
    输出：6个候选目标的列表
    """
    
    def __init__(self):
        self.theme_rules = {}
    
    async def load_rules(self, db: AsyncSession):
        """加载目标生成规则"""
        config = await BrainConfigManager.get_config(db, "goal_rules")
        if config and "content" in config:
            self.theme_rules = config["content"]
        else:
            # 默认规则
            self.theme_rules = self._default_rules()
    
    def _default_rules(self) -> Dict:
        """默认规则库"""
        return {
            "担保风控": {
                "必出": [
                    ("G1", "逾期率趋势监控", "趋势", ["line", "area"]),
                    ("G2", "地区风险对比", "对比", ["bar", "map"]),
                    ("G3", "抵押风险分布", "分布", ["pie"]),
                ],
                "候选": [
                    ("G4", "大额担保风险预警", "预警", ["kpi", "table"]),
                    ("G5", "担保类型占比分析", "分布", ["pie", "bar"]),
                    ("G6", "担保期限结构分析", "关联", ["bar", "heatmap"]),
                ]
            },
            "逾期分析": {
                "必出": [
                    ("G1", "逾期金额趋势", "趋势", ["line"]),
                    ("G2", "逾期天数分布", "分布", ["histogram", "bar"]),
                    ("G3", "不良率地区对比", "对比", ["bar", "map"]),
                ],
                "候选": [
                    ("G4", "高风险客户预警", "预警", ["kpi", "table"]),
                    ("G5", "逾期原因分析", "分布", ["pie"]),
                    ("G6", "回收率趋势", "趋势", ["line", "area"]),
                ]
            },
            "客户画像": {
                "必出": [
                    ("G1", "客户规模分布", "分布", ["pie", "bar"]),
                    ("G2", "客户类型占比", "分布", ["pie"]),
                    ("G3", "地区客户分布", "分布", ["map", "bar"]),
                ],
                "候选": [
                    ("G4", "重点客户识别", "画像", ["table", "kpi"]),
                    ("G5", "客户增长趋势", "趋势", ["line"]),
                    ("G6", "客户风险分层", "分布", ["bar", "pie"]),
                ]
            },
            "产品分析": {
                "必出": [
                    ("G1", "产品规模分布", "分布", ["pie", "bar"]),
                    ("G2", "产品结构变化", "趋势", ["line", "bar"]),
                    ("G3", "产品收益率对比", "对比", ["bar"]),
                ],
                "候选": [
                    ("G4", "热销产品排名", "KPI", ["kpi", "bar"]),
                    ("G5", "产品期限分布", "分布", ["pie", "bar"]),
                    ("G6", "产品风险分析", "对比", ["bar", "heatmap"]),
                ]
            },
            "地区分布": {
                "必出": [
                    ("G1", "地区规模分布", "分布", ["map", "bar"]),
                    ("G2", "地区增长趋势", "趋势", ["line"]),
                    ("G3", "地区对比分析", "对比", ["bar", "map"]),
                ],
                "候选": [
                    ("G4", "重点地区识别", "KPI", ["kpi"]),
                    ("G5", "地区风险地图", "分布", ["map", "heatmap"]),
                    ("G6", "区域集中度分析", "分布", ["pie", "bar"]),
                ]
            }
        }
    
    def _generate_description(self, goal_id: str, title: str, theme: str, fields: List[str]) -> str:
        """
        生成目标描述（中文业务化表述）
        
        避免技术术语，使用业务语言
        """
        descriptions = {
            "逾期率趋势监控": f"追踪{theme}下的逾期率变化情况，识别风险趋势，帮助及时预警",
            "地区风险对比": f"比较不同地区的{theme}风险水平，发现高风险地区，指导资源配置",
            "抵押风险分布": f"分析抵押物的风险分布情况，了解高风险抵押物类型",
            "大额担保风险预警": f"识别担保金额较大的高风险记录，优先关注",
            "担保类型占比分析": f"了解各类担保方式的占比情况，掌握业务结构",
            "担保期限结构分析": f"分析担保期限的分布特征，评估期限风险",
            "逾期金额趋势": f"追踪逾期金额的变化趋势，评估资产质量",
            "逾期天数分布": f"了解逾期天数的分布情况，识别逾期严重程度",
            "不良率地区对比": f"对比各地区的不良率水平，发现风险集中区域",
            "高风险客户预警": f"识别风险较高的客户，提前采取防范措施",
            "客户规模分布": f"了解客户规模的分布情况，掌握客户结构",
            "客户类型占比": f"分析个人与企业客户占比，了解客户构成",
            "地区客户分布": f"了解客户在各地区的分布情况",
            "重点客户识别": f"识别重要的战略客户，优先服务",
            "产品规模分布": f"了解各产品的规模占比，掌握产品结构",
            "产品结构变化": f"追踪产品结构的演变趋势，发现业务变化",
            "产品收益率对比": f"比较各产品的收益水平，优化产品策略"
        }
        
        return descriptions.get(title, f"分析{theme}下的{title}，辅助业务决策")
    
    def generate_goals_rule_based(
        self,
        theme: str,
        fields: List[str],
        grain: str = "detail"
    ) -> List[AnalysisGoal]:
        """
        基于规则生成目标（无需LLM，快速响应）
        
        策略：
        1. 根据主题选择必出目标（3个）
        2. 从候选中选择3个补充目标（考虑粒度）
        """
        goals = []
        
        # 获取主题规则
        theme_rule = self.theme_rules.get(theme, self.theme_rules.get("担保风控", {}))
        
        # 必出目标（3个）
        must_have = theme_rule.get("必出", [])
        for i, (gid, title, gtype, charts) in enumerate(must_have[:3]):
            goals.append(AnalysisGoal(
                goal_id=gid,
                title=title,
                description=self._generate_description(gid, title, theme, fields),
                type=gtype,
                priority=10 - i,
                expected_charts=charts
            ))
        
        # 候选目标（根据粒度筛选）
        candidates = theme_rule.get("候选", [])
        
        # 粒度过滤：宏观指标禁行级明细
        if grain == "macro":
            # 过滤掉需要明细的目标
            filtered = [c for c in candidates if c[2] not in ["画像", "明细"]]
        else:
            filtered = candidates
        
        # 选择3个候选
        for i, (gid, title, gtype, charts) in enumerate(filtered[:3]):
            goals.append(AnalysisGoal(
                goal_id=gid,
                title=title,
                description=self._generate_description(gid, title, theme, fields),
                type=gtype,
                priority=6 - i,
                expected_charts=charts
            ))
        
        return goals[:6]  # 确保最多6个
    
    async def generate_goals_llm_enhanced(
        self,
        db: AsyncSession,
        theme: str,
        fields: List[str],
        grain: str = "detail",
        sample_data: Optional[List[Dict]] = None
    ) -> List[AnalysisGoal]:
        """
        基于LLM增强生成
        
        使用Prompt模板从brain_configs读取
        """
        # 1. 先基于规则生成
        base_goals = self.generate_goals_rule_based(theme, fields, grain)
        
        # 2. 加载Prompt模板
        try:
            template_config = await BrainConfigManager.get_config(db, "goal_prompt_v1")
            if template_config:
                template = template_config["content"].get("template", "")
            else:
                template = self._default_prompt_template()
        except:
            template = self._default_prompt_template()
        
        # 3. 构建Prompt
        base_goals_json = json.dumps([g.to_dict() for g in base_goals], ensure_ascii=False, indent=2)
        
        prompt = template.replace("{{theme}}", theme) \
                         .replace("{{grain}}", grain) \
                         .replace("{{fields}}", json.dumps(fields, ensure_ascii=False)) \
                         .replace("{{base_goals}}", base_goals_json)
        
        if sample_data:
            prompt = prompt.replace("{{sample_data}}", json.dumps(sample_data[:3], ensure_ascii=False))
        
        # 4. 调用LLM
        response = await llm_chat(
            prompt=prompt,
            json_mode=True,
            user_id="s2_goal_generator",
            fallback={
                "goals": [g.to_dict() for g in base_goals],
                "source": "fallback_rule_based"
            }
        )
        
        if response.success and response.response_json:
            llm_goals = response.response_json.get("goals", [])
            
            # 转换为AnalysisGoal
            goals = []
            for g in llm_goals[:6]:
                goals.append(AnalysisGoal(
                    goal_id=g.get("goal_id", f"G{len(goals)+1}"),
                    title=g.get("title", "未命名目标"),
                    description=g.get("description", ""),
                    type=g.get("type", "分析"),
                    priority=g.get("priority", 5),
                    expected_charts=g.get("expected_charts", [])
                ))
            
            return goals if goals else base_goals
        
        return base_goals
    
    def _default_prompt_template(self) -> str:
        """默认Prompt模板"""
        return """你是一位资深风控分析师。请基于以下信息优化分析目标：

数据主题: {{theme}}
数据粒度: {{grain}}
字段列表: {{fields}}

基础目标（由规则生成）：
{{base_goals}}

要求：
1. 目标必须是中文业务化表述，避免技术术语（如"维度分析"、"指标"等）
2. 每句话要像业务人员说的话，例如："看看哪些地区风险高"而不是"进行地区风险维度分析"
3. 包含以下类型：
   - 1个KPI类（如"总担保金额多少"）
   - 1个趋势类（如"逾期率怎么变化"）
   - 1个对比类（如"各地区风险对比"）
   - 1个分布类（如"担保类型分布"）
   - 1个预警类（如"哪些是大额风险"）
   - 1个画像/关联类（如"客户风险长什么样"）

4. 描述要通俗易懂，不用专业术语

请以JSON格式返回优化后的目标：
{
    "goals": [
        {
            "goal_id": "G1",
            "title": "业务化标题",
            "description": "通俗易懂的描述",
            "type": "KPI/趋势/对比/分布/预警/画像/关联",
            "priority": 10,
            "expected_charts": ["line", "bar"]
        }
    ]
}"""
    
    async def generate(
        self,
        db: AsyncSession,
        theme: str,
        fields: List[str],
        grain: str = "detail",
        use_llm: bool = False,
        sample_data: Optional[List[Dict]] = None
    ) -> List[AnalysisGoal]:
        """
        目标生成入口
        
        Args:
            use_llm: 是否使用LLM增强（默认False，降本）
        """
        # 加载规则
        await self.load_rules(db)
        
        if use_llm and theme != "未知":
            # LLM增强
            return await self.generate_goals_llm_enhanced(
                db, theme, fields, grain, sample_data
            )
        else:
            # 纯规则（更快，更可控）
            return self.generate_goals_rule_based(theme, fields, grain)


# 便捷函数
async def generate_analysis_goals(
    db: AsyncSession,
    theme: str,
    fields: List[str],
    grain: str = "detail",
    use_llm: bool = False
) -> List[Dict]:
    """
    便捷目标生成函数
    
    Returns:
        [
            {
                "goal_id": "G1",
                "title": "逾期率趋势监控",
                "description": "追踪逾期率变化...",
                "type": "趋势",
                "priority": 10,
                "expected_charts": ["line"]
            }
        ]
    """
    generator = S2GoalGenerator()
    goals = await generator.generate(db, theme, fields, grain, use_llm)
    return [g.to_dict() for g in goals]
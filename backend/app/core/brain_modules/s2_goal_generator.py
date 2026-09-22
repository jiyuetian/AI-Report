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
from app.core.prompt_loader import load_prompt
from app.models.analysis_template import AnalysisTemplate


@dataclass
class AnalysisGoal:
    """分析目标"""
    goal_id: str
    title: str
    description: str
    type: str  # KPI/趋势/对比/分布/预警/画像/关联
    priority: int = 1  # 优先级 1-10
    expected_charts: List[str] = None
    generated_by: str = "rule"  # 2.3-B：标记目标由 LLM 还是规则生成（路演可证明 AI 参与）
    
    def to_dict(self) -> Dict:
        result = {
            "goal_id": self.goal_id,
            "title": self.title,
            "description": self.description,
            "type": self.type,
            "priority": self.priority,
            "generated_by": self.generated_by
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
        sample_data: Optional[List[Dict]] = None,
        field_profiles: Optional[List[Dict[str, Any]]] = None
    ) -> List[AnalysisGoal]:
        """
        基于LLM增强生成
        
        使用Prompt模板从brain_configs读取
        """
        # 1. 先基于规则生成
        base_goals = self.generate_goals_rule_based(theme, fields, grain)
        # 2.6 P0：并入命中 approved 模板（按字段画像特征，不绑列名；不破坏下方规则兜底）
        base_goals = await self._apply_templates(db, base_goals, theme, fields, grain, field_profiles)
        
        # 2. 构建Prompt（外置被控提示词优先 prompts/s2_goal_generator.md，缺失回退内置默认）
        base_goals_json = json.dumps([g.to_dict() for g in base_goals], ensure_ascii=False, indent=2)
        sample_json = json.dumps(sample_data[:3], ensure_ascii=False) if sample_data else ""

        # 3. 调用LLM
        prompt = load_prompt(
            "s2_goal_generator",
            self._default_prompt_template(),
            theme=theme,
            grain=grain,
            fields=json.dumps(fields, ensure_ascii=False),
            base_goals=base_goals_json,
            sample_data=sample_json,
        )
        print(f"[LLM] S2 目标生成调用 LLM (theme={theme}, fields={len(fields)})")
        response = await llm_chat(
            prompt=prompt,
            json_mode=True,
            user_id="s2_goal_generator",
            timeout=30,  # 目标生成：超时直接用规则生成的 base_goals 兜底
            fallback={
                "goals": [g.to_dict() for g in base_goals],
                "source": "fallback_rule_based"
            }
        )
        
        if response.success and response.response_json:
            llm_goals = response.response_json.get("goals", [])
            print(f"[LLM] S2 LLM 返回 {len(llm_goals)} 个目标，转为 AnalysisGoal")
            # 转换为AnalysisGoal（标记由 LLM 生成）
            goals = []
            for g in llm_goals[:6]:
                goals.append(AnalysisGoal(
                    goal_id=g.get("goal_id", f"G{len(goals)+1}"),
                    title=g.get("title", "未命名目标"),
                    description=g.get("description", ""),
                    type=g.get("type", "分析"),
                    priority=g.get("priority", 5),
                    expected_charts=g.get("expected_charts", []),
                    generated_by="llm"
                ))
            
            return goals if goals else base_goals
        
        return base_goals
    
    def _default_prompt_template(self) -> str:
        """默认Prompt模板（外置 prompts/s2_goal_generator.md 缺失时的回退）"""
        return """你是一位资深风控分析师。请基于以下信息优化分析目标：

数据主题: {theme}
数据粒度: {grain}
字段列表: {fields}

基础目标（由规则生成）：
{base_goals}

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

{sample_data}

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
        sample_data: Optional[List[Dict]] = None,
        field_profiles: Optional[List[Dict[str, Any]]] = None
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
                db, theme, fields, grain, sample_data, field_profiles
            )
        else:
            # 纯规则（更快，更可控）
            goals = self.generate_goals_rule_based(theme, fields, grain)
            # 2.6 P0：规则路径同样并入命中模板
            return await self._apply_templates(db, goals, theme, fields, grain, field_profiles)


    async def _apply_templates(
        self,
        db: AsyncSession,
        base_goals: List[AnalysisGoal],
        theme: str,
        fields: List[str],
        grain: str,
        field_profiles: Optional[List[Dict[str, Any]]]
    ) -> List[AnalysisGoal]:
        """
        2.6 P0：模板匹配并入候选（不破坏规则兜底）。

        - 按字段画像特征（不绑列名）对 approved 模板做交集打分
        - 命中则把 base_goals 并入候选，generated_by='template'
        - 任何异常都忽略，原样返回 base_goals（零影响）
        """
        try:
            profile = _build_dataset_profile(fields, theme, field_profiles)
            matched = await match_templates(db, profile)
        except Exception as e:
            print(f"[S2] 模板匹配异常(忽略): {e}")
            return base_goals
        if not matched:
            return base_goals
        for t in matched:
            tg = t.base_goals if isinstance(t.base_goals, list) else []
            for g in tg:
                if isinstance(g, dict) and g.get("title"):
                    base_goals.append(AnalysisGoal(
                        goal_id=g.get("goal_id", f"T{len(base_goals) + 1}"),
                        title=g.get("title"),
                        description=g.get("description", ""),
                        type=g.get("type", "分析"),
                        priority=g.get("priority", 4),
                        expected_charts=g.get("expected_charts", []),
                        generated_by="template",
                    ))
        merged = sum(len(t.base_goals or []) for t in matched)
        print(f"[S2] 模板命中 {len(matched)} 个，并入 {merged} 个候选目标")
        return base_goals


# 便捷函数
async def generate_analysis_goals(
    db: AsyncSession,
    theme: str,
    fields: List[str],
    grain: str = "detail",
    use_llm: bool = False,
    field_profiles: Optional[List[Dict[str, Any]]] = None
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
    goals = await generator.generate(db, theme, fields, grain, use_llm, field_profiles=field_profiles)
    return [g.to_dict() for g in goals]


# ============================================================================
# 2.6 P0：分析模板匹配（按字段画像特征，不绑列名）
# ============================================================================

def _build_dataset_profile(
    fields: List[str],
    theme: str,
    field_profiles: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    构建数据集字段画像 profile（供 match_templates 打分）。

    设计原则：
    - 不触发 AI（build_semantics 含 LLM 调用，S2 不该触发）→ 用便宜规则推导
    - type_buckets：FieldAnalyzer.infer_field_type（纯规则）逐个推断
    - cardinality_buckets：由 2.5 的 field_profiles(distinct_count) 推 low/mid/high
    - recommended_aggs：由 type 映射（NUMBER→sum/avg，CATEGORY/GEO/DATE→count）
    - business_roles：需 AI 标注，S2 不触发 → 生产环境留空；
      测试或后续接入 field_semantics 后可填充，模板的 semantic_hints 才会生效
    """
    type_buckets: List[str] = []
    try:
        from app.core.brain_modules.schema_enricher import FieldAnalyzer
        type_buckets = [FieldAnalyzer.infer_field_type(f).name for f in fields]
    except Exception as e:
        print(f"[S2] 字段类型推断失败(降级空): {e}")

    cardinality_buckets: List[str] = []
    if field_profiles:
        for p in field_profiles:
            dc = p.get("distinct_count")
            if dc is None:
                cardinality_buckets.append("unknown")
            elif dc <= 20:
                cardinality_buckets.append("low")
            elif dc <= 200:
                cardinality_buckets.append("mid")
            else:
                cardinality_buckets.append("high")

    recommended_aggs: List[str] = []
    for t in set(type_buckets):
        if t == "NUMBER":
            recommended_aggs += ["sum", "avg"]
        elif t in ("CATEGORY", "GEO"):
            recommended_aggs += ["count"]
        elif t == "DATE":
            recommended_aggs += ["count"]

    return {
        "type_buckets": type_buckets,
        "business_roles": [],
        "recommended_aggs": recommended_aggs,
        "cardinality_buckets": cardinality_buckets,
        "field_count": len(fields),
        "theme": theme,
    }


def _score_template(match_features: Dict[str, Any], profile: Dict[str, Any]) -> float:
    """
    单模板打分：与 profile 做特征交集，返回 0~N 的得分（0 = 不命中）。

    各特征组等权；声明了某个组就按「命中比例」计分；全部未命中 → 0。
    match_features 支持的键：
      - must_have_types:   要求的字段类型桶（CATEGORY/NUMBER/DATE/TEXT/GEO）集合
      - semantic_hints:    要求的 business_role / recommended_agg 提示集合
      - min_fields:        要求的最少字段数
      - theme_hint:        主题正则（re.search，忽略大小写）
      - cardinality_need:  要求至少存在一个的 cardinality 桶（low/mid/high）
    """
    if not match_features or not isinstance(match_features, dict):
        return 0.0

    score = 0.0

    # 主题硬约束（2.6 收尾）：声明了 theme_hint 必须命中，否则整体不命中。
    # 避免"通用型" match_features（must_have_types + min_fields）跨主题误套用，污染候选目标。
    _th = match_features.get("theme_hint")
    if _th:
        import re as _re
        if not _re.search(_th, (profile.get("theme") or ""), _re.IGNORECASE):
            return 0.0

    # 字段类型桶
    mht = match_features.get("must_have_types") or []
    if mht:
        have = set(profile.get("type_buckets") or [])
        hit = len(set(mht) & have)
        score += (hit / len(mht)) if hit else 0.0

    # 语义提示（business_role / recommended_agg）
    hints = match_features.get("semantic_hints") or []
    if hints:
        have = set(profile.get("business_roles") or []) | set(profile.get("recommended_aggs") or [])
        hit = len(set(hints) & have)
        score += (hit / len(hints)) if hit else 0.0

    # 最少字段数
    mf_min = match_features.get("min_fields")
    if mf_min:
        if (profile.get("field_count") or 0) >= int(mf_min):
            score += 1.0

    # 主题正则
    th = match_features.get("theme_hint")
    if th:
        import re
        if re.search(th, profile.get("theme") or "", re.IGNORECASE):
            score += 1.0

    # 基数列要求
    cn = match_features.get("cardinality_need") or []
    if cn:
        have = set(profile.get("cardinality_buckets") or [])
        if set(cn) & have:
            score += 1.0

    return score


async def match_templates(db, profile: Dict[str, Any]) -> List["AnalysisTemplate"]:
    """
    2.6 P0：匹配分析模板。

    - 仅 approved=True 参与（未确认模板不套用，防污染）
    - 按 match_features 与 profile 做特征交集打分
    - 返回得分>0 的模板，降序（最匹配在前）
    """
    from app.models.analysis_template import AnalysisTemplate
    from sqlalchemy import select

    result = await db.execute(select(AnalysisTemplate).where(AnalysisTemplate.approved == True))  # noqa: E712
    rows = result.scalars().all()

    scored = []
    for t in rows:
        mf = t.match_features
        if isinstance(mf, str):
            try:
                mf = json.loads(mf)
            except Exception:
                mf = {}
        s = _score_template(mf or {}, profile)
        if s > 0:
            scored.append((s, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored]


async def propose_template_candidate(
    db,
    theme: str,
    fields: List[str],
    field_profiles: Optional[List[Dict[str, Any]]],
    goals: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """2.6 P1：AI 自动沉淀候选模板。

    - 从本次 dataset profile + S2 goals 提炼可复用模板
    - approved=False（待管理后台确认，防污染）
    - 去重：相同 match_features 签名（任意来源）不重复写入
    - 任何异常忽略，不影响主链路（S2 之后的可选增强）
    """
    try:
        if not goals or len(goals) < 3:
            return None
        profile = _build_dataset_profile(fields, theme, field_profiles)
        mf = {
            "must_have_types": sorted(set(profile.get("type_buckets") or [])),
            "min_fields": profile.get("field_count") or len(fields or []),
            "theme_hint": theme or "",
        }
        if not mf["theme_hint"]:
            mf.pop("theme_hint", None)
        sig = json.dumps(mf, sort_keys=True, ensure_ascii=False)

        # 去重：同 match_features 签名（任意来源）已存在则跳过
        from sqlalchemy import select as _select
        existing = (await db.execute(_select(AnalysisTemplate))).scalars().all()
        for t in existing:
            tf = t.match_features
            if isinstance(tf, str):
                try:
                    tf = json.loads(tf)
                except Exception:
                    tf = {}
            if json.dumps(tf, sort_keys=True, ensure_ascii=False) == sig:
                return None

        base_goals = [g for g in goals[:6]]
        goal_skeleton = [{"type": g.get("type"), "title": g.get("title")} for g in base_goals]
        tpl = AnalysisTemplate(
            name=f"{(theme or '通用')}分析模板候选",
            description=f"由 S2 自动沉淀（theme={theme}, {len(base_goals)} 个目标，待确认）",
            match_features=mf,
            base_goals=base_goals,
            goal_skeleton=goal_skeleton,
            approved=False,
            source="ai",
        )
        db.add(tpl)
        await db.commit()
        print(f"[S2] 模板沉淀候选已写入（source=ai, approved=False）：{tpl.name}")
        return tpl.to_dict()
    except Exception as e:
        print(f"[S2] 模板沉淀异常(忽略): {e}")
        return None
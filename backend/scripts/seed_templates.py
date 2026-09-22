"""
2.6 收尾 · 种子分析模板（幂等，可重复运行，零第三方依赖）

- 用标准库 sqlite3 直接对真实元数据库 backend/data/aibi.db 建表 + 幂等 INSERT
  （本地沙箱未安装 SQLAlchemy/aiosqlite，无法走 ORM；此处落库格式与
   AnalysisTemplate 模型列完全一致，后端运行时可直接读取）
- 同时对典型 profile 用「与运行时 match_templates 一字不差的」源码级 _score_template
  做命中验证，作为真跑证据（不依赖任何后端依赖 / 网络）
- 设计约束（来自 s2_goal_generator._build_dataset_profile）：
    * business_roles 生产环境恒为空 → match_features 不依赖 semantic_hints 非聚合词
    * cardinality_buckets 在 S2 未必传 field_profiles → 不作为必中维度
    * theme_hint 走 re.search(theme)；theme 来自 S1 词典
      （担保风控/逾期分析/地区分布/客户画像/产品分析）
    * 2.6 收尾增强：theme_hint 为硬约束（声明且不匹配则整体 0 分），避免跨主题误套用
"""
import os
import re
import json
import sqlite3
import uuid

# ---- 路径：backend/scripts/seed_templates.py -> backend/data/aibi.db ----
_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(_HERE, "..", "data", "aibi.db"))

# ============================================================================
# 种子模板（5 个业务主题，覆盖路演常见场景）
# ============================================================================
SEED_TEMPLATES = [
    {
        "name": "担保风控标准六图",
        "description": "覆盖担保/抵押/质押业务的标准分析目标：金额、逾期、地区、抵押率、类型、预警。",
        "match_features": {
            "must_have_types": ["CATEGORY", "NUMBER"],
            "min_fields": 5,
            "theme_hint": "担保|风控|抵押|质押|代偿|保证",
        },
        "base_goals": [
            {"goal_id": "TG1", "title": "总担保金额", "type": "KPI", "priority": 10, "expected_charts": ["kpi"]},
            {"goal_id": "TG2", "title": "逾期率趋势监控", "type": "趋势", "priority": 9, "expected_charts": ["line", "area"]},
            {"goal_id": "TG3", "title": "地区风险对比", "type": "对比", "priority": 8, "expected_charts": ["bar", "map"]},
            {"goal_id": "TG4", "title": "抵押率分布", "type": "分布", "priority": 7, "expected_charts": ["pie"]},
            {"goal_id": "TG5", "title": "大额担保风险预警", "type": "预警", "priority": 6, "expected_charts": ["kpi", "table"]},
            {"goal_id": "TG6", "title": "担保类型占比分析", "type": "分布", "priority": 5, "expected_charts": ["pie", "bar"]},
        ],
        "goal_skeleton": [
            {"type": "KPI", "role_hint": "金额指标", "title": "总担保金额"},
            {"type": "趋势", "title": "逾期率趋势监控"},
        ],
    },
    {
        "name": "客户画像分析",
        "description": "客户/借款人维度画像：规模分布、类型占比、地区分布、重点客户识别。",
        "match_features": {
            "must_have_types": ["CATEGORY", "NUMBER"],
            "min_fields": 4,
            "theme_hint": "客户|画像|借款人|企业|客群",
        },
        "base_goals": [
            {"goal_id": "CG1", "title": "客户规模分布", "type": "分布", "priority": 10, "expected_charts": ["pie", "bar"]},
            {"goal_id": "CG2", "title": "客户类型占比", "type": "分布", "priority": 8, "expected_charts": ["pie"]},
            {"goal_id": "CG3", "title": "地区客户分布", "type": "分布", "priority": 7, "expected_charts": ["map", "bar"]},
            {"goal_id": "CG4", "title": "重点客户识别", "type": "画像", "priority": 6, "expected_charts": ["table", "kpi"]},
        ],
        "goal_skeleton": [
            {"type": "分布", "title": "客户规模分布"},
            {"type": "画像", "title": "重点客户识别"},
        ],
    },
    {
        "name": "贷款借据明细分析",
        "description": "单笔借据/贷款明细：放款趋势、逾期分布、借据类型、大额预警、还款结构。",
        "match_features": {
            "must_have_types": ["CATEGORY", "NUMBER", "DATE"],
            "min_fields": 6,
            "theme_hint": "贷款|借据|放款|还款|合同|逾期|不良",
        },
        "base_goals": [
            {"goal_id": "LG1", "title": "放款金额趋势", "type": "趋势", "priority": 10, "expected_charts": ["line"]},
            {"goal_id": "LG2", "title": "逾期金额分布", "type": "分布", "priority": 8, "expected_charts": ["histogram", "bar"]},
            {"goal_id": "LG3", "title": "借据类型占比", "type": "分布", "priority": 7, "expected_charts": ["pie"]},
            {"goal_id": "LG4", "title": "大额借据风险预警", "type": "预警", "priority": 6, "expected_charts": ["kpi", "table"]},
            {"goal_id": "LG5", "title": "还款结构分析", "type": "关联", "priority": 5, "expected_charts": ["bar", "heatmap"]},
        ],
        "goal_skeleton": [
            {"type": "趋势", "title": "放款金额趋势"},
            {"type": "预警", "title": "大额借据风险预警"},
        ],
    },
    {
        "name": "销售经营分析",
        "description": "销售/经营类数据：收入趋势、产品占比、区域对比、热销排名。",
        "match_features": {
            "must_have_types": ["CATEGORY", "NUMBER"],
            "min_fields": 4,
            "theme_hint": "销售|营收|经营|收入|产品|业绩",
        },
        "base_goals": [
            {"goal_id": "SG1", "title": "销售收入趋势", "type": "趋势", "priority": 10, "expected_charts": ["line"]},
            {"goal_id": "SG2", "title": "产品销售额占比", "type": "分布", "priority": 8, "expected_charts": ["pie"]},
            {"goal_id": "SG3", "title": "区域销售对比", "type": "对比", "priority": 7, "expected_charts": ["bar", "map"]},
            {"goal_id": "SG4", "title": "热销产品排名", "type": "KPI", "priority": 6, "expected_charts": ["kpi", "bar"]},
        ],
        "goal_skeleton": [
            {"type": "趋势", "title": "销售收入趋势"},
            {"type": "分布", "title": "产品销售额占比"},
        ],
    },
    {
        "name": "地区分布分析",
        "description": "地理维度：地区规模、增长趋势、对比、重点地区识别。",
        "match_features": {
            "must_have_types": ["CATEGORY", "NUMBER"],
            "min_fields": 4,
            "theme_hint": "地区|省份|城市|区域|地理|行政区",
        },
        "base_goals": [
            {"goal_id": "RG1", "title": "地区规模分布", "type": "分布", "priority": 10, "expected_charts": ["map", "bar"]},
            {"goal_id": "RG2", "title": "地区增长趋势", "type": "趋势", "priority": 8, "expected_charts": ["line"]},
            {"goal_id": "RG3", "title": "地区对比分析", "type": "对比", "priority": 7, "expected_charts": ["bar", "map"]},
            {"goal_id": "RG4", "title": "重点地区识别", "type": "KPI", "priority": 6, "expected_charts": ["kpi"]},
        ],
        "goal_skeleton": [
            {"type": "分布", "title": "地区规模分布"},
            {"type": "对比", "title": "地区对比分析"},
        ],
    },
]


# ============================================================================
# 源码级复刻 _score_template（与 s2_goal_generator._score_template 一字不差，
# 含 2.6 收尾增强的 theme_hint 硬约束），用于离线命中验证
# ============================================================================
def score_template(match_features: dict, profile: dict) -> float:
    if not match_features or not isinstance(match_features, dict):
        return 0.0
    score = 0.0
    # 主题硬约束（2.6 收尾）：声明了 theme_hint 必须命中，否则整体不命中
    th = match_features.get("theme_hint")
    if th:
        if not re.search(th, (profile.get("theme") or ""), re.IGNORECASE):
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
    # 主题正则（已硬约束命中才到此处）
    if th:
        score += 1.0
    # 基数列要求
    cn = match_features.get("cardinality_need") or []
    if cn:
        have = set(profile.get("cardinality_buckets") or [])
        if set(cn) & have:
            score += 1.0
    return score


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_template (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            goal_skeleton TEXT,
            match_features TEXT,
            base_goals TEXT,
            approved INTEGER DEFAULT 0,
            usage_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'system',
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_analysis_template_approved ON analysis_template(approved)"
    )


def seed(conn: sqlite3.Connection) -> list:
    """幂等插入种子模板，返回本次新插入的 name 列表。"""
    inserted = []
    for s in SEED_TEMPLATES:
        exists = conn.execute(
            "SELECT 1 FROM analysis_template WHERE name = ?", (s["name"],)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO analysis_template
            (id, name, description, goal_skeleton, match_features, base_goals, approved, usage_count, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, 0, 'system', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                uuid.uuid4().hex,
                s["name"],
                s["description"],
                json.dumps(s["goal_skeleton"], ensure_ascii=False),
                json.dumps(s["match_features"], ensure_ascii=False),
                json.dumps(s["base_goals"], ensure_ascii=False),
            ),
        )
        inserted.append(s["name"])
    conn.commit()
    return inserted


def verify(conn: sqlite3.Connection) -> None:
    """对典型 profile 用源码级 _score_template 验证命中。"""
    rows = conn.execute(
        "SELECT name, match_features FROM analysis_template WHERE approved = 1"
    ).fetchall()
    templates = [(r[0], json.loads(r[1])) for r in rows]

    profiles = {
        "担保风控数据集": {
            "type_buckets": ["CATEGORY", "NUMBER", "DATE"],
            "business_roles": [],
            "recommended_aggs": ["sum", "avg", "count"],
            "cardinality_buckets": ["low", "high"],
            "field_count": 8,
            "theme": "担保风控",
        },
        "客户画像数据集": {
            "type_buckets": ["CATEGORY", "NUMBER"],
            "business_roles": [],
            "recommended_aggs": ["count", "sum"],
            "cardinality_buckets": ["mid"],
            "field_count": 5,
            "theme": "客户画像",
        },
        "通用分析数据集（无明确主题）": {
            "type_buckets": ["CATEGORY", "NUMBER"],
            "business_roles": [],
            "recommended_aggs": ["count", "sum"],
            "cardinality_buckets": ["low"],
            "field_count": 10,
            "theme": "通用分析",
        },
    }

    print("=== 种子模板命中验证（源码级 _score_template）===")
    for pname, prof in profiles.items():
        hit = []
        for tname, mf in templates:
            if score_template(mf, prof) > 0:
                hit.append(tname)
        print(f"[{pname}] theme={prof['theme']!r} -> 命中: {hit}")


def main() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_table(conn)
        inserted = seed(conn)
        total = conn.execute(
            "SELECT COUNT(*) FROM analysis_template WHERE source='system' AND approved=1"
        ).fetchone()[0]
        print(f"=== seed_templates 完成 ===")
        print(f"元数据库: {DB_PATH}")
        print(f"本次新插入: {inserted if inserted else '(无，已存在则跳过)'}")
        print(f"system 已批准模板总数: {total}")
        verify(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

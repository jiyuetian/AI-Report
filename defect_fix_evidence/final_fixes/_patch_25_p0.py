# -*- coding: utf-8 -*-
"""2.5 P0 确定性补丁：扩展 _desc 注入 distinct/空值率/高基数 + 调用方传 field_profiles。"""
import io, sys

REPO = "C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report"

# ---------- s3_llm_enhancer.py ----------
P1 = f"{REPO}/backend/app/core/brain_modules/s3_llm_enhancer.py"
s1 = io.open(P1, encoding="utf-8").read()
orig1 = s1

# A: _build_prompt 签名加 field_profiles
A_OLD = '''        previous_error: Optional[str] = None,
        semantics: Optional[Dict[str, Any]] = None,
        derived_metrics: Optional[Dict[str, Any]] = None
    ) -> str:'''
A_NEW = '''        previous_error: Optional[str] = None,
        semantics: Optional[Dict[str, Any]] = None,
        derived_metrics: Optional[Dict[str, Any]] = None,
        field_profiles: Optional[List[Dict[str, Any]]] = None
    ) -> str:'''
assert s1.count(A_OLD) == 1, ("A", s1.count(A_OLD))
s1 = s1.replace(A_OLD, A_NEW)

# B: _desc 扩展 + profile_index + fields_desc
B_OLD = '''        def _desc(f: str) -> str:
            t = field_types.get(f, FieldType.TEXT)
            base = type_label.get(t, "文本")
            m = meta.get(f, {})
            role = m.get("business_role") or ""
            hint = m.get("chart_hint") or ""
            parts = [base]
            if role:
                parts.append(role)
            if hint:
                parts.append(f"建议:{hint}")
            return "，".join(parts) if len(parts) > 1 else base

        fields_desc = "\\n".join(f"  - {f}（{_desc(f)}）" for f in fields)'''
B_NEW = '''        # 2.5 P0：字段画像索引（归一化匹配，复用与 D2 同套去空格/全角/大小写）
        _profile_index: Dict[str, Dict[str, Any]] = {}
        if field_profiles:
            for _fp in field_profiles:
                if not isinstance(_fp, dict):
                    continue
                _nm = str(_fp.get("name") or _fp.get("column") or "").strip()
                if not _nm:
                    continue
                _profile_index[_nm] = _fp
                _profile_index[_nm.replace(" ", "").replace("\\u3000", "")] = _fp

        def _lookup_profile(field: str) -> Optional[Dict[str, Any]]:
            _key = str(field or "").strip()
            return _profile_index.get(_key) or _profile_index.get(_key.replace(" ", "").replace("\\u3000", ""))

        def _desc(f: str) -> str:
            t = field_types.get(f, FieldType.TEXT)
            base = type_label.get(t, "文本")
            m = meta.get(f, {})
            role = m.get("business_role") or ""
            hint = m.get("chart_hint") or ""
            card = m.get("cardinality") or ""
            extras = []
            if role:
                extras.append(role)
            if hint:
                extras.append(f"建议:{hint}")
            # 2.5 P0：真实画像（distinct/空值率/取值样例/高基数）——来自 S3 调用前 duckdb 实算
            prof = _lookup_profile(f)
            prof_parts = []
            if prof:
                _dc = prof.get("distinct_count")
                if _dc is not None:
                    prof_parts.append(f"distinct={_dc}")
                _nr = prof.get("null_rate")
                if _nr is not None:
                    try:
                        prof_parts.append(f"空值率{round(float(_nr) * 100)}%")
                    except (TypeError, ValueError):
                        pass
                if card == "high":
                    prof_parts.append("⚠️高基数，禁止作为分类维度")
                elif prof.get("sample_values"):
                    _sv = prof["sample_values"][:5]
                    if _sv:
                        prof_parts.append("取值:" + "/".join(str(v) for v in _sv))
            if prof_parts:
                extras.append(" | ".join(prof_parts))
            return "，".join([base] + extras) if extras else base

        fields_desc = "\\n".join(f"  - {f}（{_desc(f)}）" for f in fields)'''
assert s1.count(B_OLD) == 1, ("B", s1.count(B_OLD))
s1 = s1.replace(B_OLD, B_NEW)

# C: generate_with_self_healing 签名加 field_profiles
C_OLD = '''        grain: str = "detail",
        semantics: Optional[Dict[str, Any]] = None,
        derived_metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:'''
C_NEW = '''        grain: str = "detail",
        semantics: Optional[Dict[str, Any]] = None,
        derived_metrics: Optional[Dict[str, Any]] = None,
        field_profiles: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:'''
assert s1.count(C_OLD) == 1, ("C", s1.count(C_OLD))
s1 = s1.replace(C_OLD, C_NEW)

# D: _build_prompt 调用传 field_profiles
D_OLD = '''            prompt = self._build_prompt(theme, fields, goals, grain, last_error,
                                        semantics, self.derived_metrics)'''
D_NEW = '''            prompt = self._build_prompt(theme, fields, goals, grain, last_error,
                                        semantics, self.derived_metrics, field_profiles)'''
assert s1.count(D_OLD) == 1, ("D", s1.count(D_OLD))
s1 = s1.replace(D_OLD, D_NEW)

# E: generate_charts_with_llm 签名 + 透传
E_OLD = '''async def generate_charts_with_llm(
    db: AsyncSession,
    theme: str,
    fields: List[str],
    goals: List[Dict],
    grain: str = "detail",
    semantics: Optional[Dict[str, Any]] = None,
    derived_metrics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    便捷函数：LLM生成图表（带自愈 + 字段语义增强 + 派生指标反哺）
    """
    enhancer = S3LLMEnhancer()
    return await enhancer.generate_with_self_healing(
        db, theme, fields, goals, grain, semantics, derived_metrics
    )'''
E_NEW = '''async def generate_charts_with_llm(
    db: AsyncSession,
    theme: str,
    fields: List[str],
    goals: List[Dict],
    grain: str = "detail",
    semantics: Optional[Dict[str, Any]] = None,
    derived_metrics: Optional[Dict[str, Any]] = None,
    field_profiles: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    便捷函数：LLM生成图表（带自愈 + 字段语义增强 + 派生指标反哺）
    """
    enhancer = S3LLMEnhancer()
    return await enhancer.generate_with_self_healing(
        db, theme, fields, goals, grain, semantics, derived_metrics, field_profiles
    )'''
assert s1.count(E_OLD) == 1, ("E", s1.count(E_OLD))
s1 = s1.replace(E_OLD, E_NEW)

io.open(P1, "w", encoding="utf-8").write(s1)
print("[s3_llm_enhancer] changed:", s1 != orig1)

# ---------- brain_run_sse.py ----------
P2 = f"{REPO}/backend/app/api/brain_run_sse.py"
s2 = io.open(P2, encoding="utf-8").read()
orig2 = s2

# F: import re
F_OLD = "import uuid\n"
F_NEW = "import uuid\nimport re\n"
assert s2.count(F_OLD) == 1
s2 = s2.replace(F_OLD, F_NEW, 1)

# G: 插入 _compute_field_profiles + _is_sensitive_field 助手（在 get_dataset_info 之后，brain_run_pipeline 之前）
G_ANCHOR = '        "derived_metrics": derived_metrics,\n    }\n\n\nasync def brain_run_pipeline('
G_HELPER = '''        "derived_metrics": derived_metrics,
    }


def _is_sensitive_field(f: str) -> bool:
    """2.5 P0 前置防御：敏感字段不注入取值样例（V4 红线前置），distinct 计数仍保留。"""
    return bool(re.search(r"(身份证|手机号|手机|电话|姓名|名称|地址|邮箱|邮件|证件|编号)", f or "", re.IGNORECASE))


def _compute_field_profiles(duck, table_name: str, fields: List[str],
                            sample_data: Optional[List[Dict]] = None) -> Optional[List[Dict[str, Any]]]:
    """S3 调用前算真实 distinct + 空值率（2.5 P0：L2 画像升级）。

    一次查询算所有字段的 COUNT(DISTINCT) 与空值数；失败返回 None，不阻断生成。
    列名来自数据集自有 schema（已校验），按白名单正则再过滤一次防注入。
    """
    if duck is None or not getattr(duck, "table_exists", lambda t: False)(table_name):
        return None
    safe = [f for f in fields if re.match(r"^[A-Za-z0-9_\\u4e00-\\u9fff]+$", f)]
    if not safe:
        return None
    try:
        parts = ["COUNT(*) AS _total"]
        for f in safe:
            q = '"' + f.replace('"', '""') + '"'
            parts.append(f"COUNT(DISTINCT {q})")
            parts.append(f"SUM(CASE WHEN {q} IS NULL THEN 1 ELSE 0 END)")
        row = duck.conn.execute(f'SELECT {", ".join(parts)} FROM "{table_name}"').fetchone()
        if not row:
            return None
        total = row[0] or 0
        profiles: List[Dict[str, Any]] = []
        idx = 1
        for f in safe:
            d = row[idx]
            n = row[idx + 1]
            idx += 2
            profiles.append({
                "name": f,
                "distinct_count": int(d) if d is not None else None,
                "null_rate": round(n / total, 4) if (total and n is not None) else 0.0,
            })
        # 取值样例：从 sample_data 取（敏感字段跳过，V4 前置防御）
        if sample_data:
            for p in profiles:
                if _is_sensitive_field(p["name"]):
                    continue
                vals: List[str] = []
                for r in sample_data:
                    v = r.get(p["name"])
                    if v is not None and str(v) not in vals:
                        vals.append(str(v))
                    if len(vals) >= 5:
                        break
                if vals:
                    p["sample_values"] = vals
        return profiles
    except Exception as e:
        print(f"[Brain] 字段画像计算失败(不阻断): {e}")
        return None


async def brain_run_pipeline('''
assert s2.count(G_ANCHOR) == 1, ("G", s2.count(G_ANCHOR))
s2 = s2.replace(G_ANCHOR, G_HELPER)

# H: S3 阶段计算 field_profiles + 传入（主调用）
H_ANCHOR = '''            s3_ai_reason = None
            try:'''
H_INSERT = '''            s3_ai_reason = None
            # 2.5 P0：S3 调用前算真实字段画像（distinct/空值率/取值样例），喂给 LLM 出图决策
            _s3_table = f"ds_{dataset_id.replace('-', '_')}"
            field_profiles = _compute_field_profiles(
                get_duckdb(), _s3_table, fields, dataset_info.get("sample_data")
            )
            try:'''
assert s2.count(H_ANCHOR) == 1, ("H", s2.count(H_ANCHOR))
s2 = s2.replace(H_ANCHOR, H_INSERT)

H2_OLD = '''                            generate_charts_with_llm(
                                db=db,
                                theme=theme_tag,
                                fields=fields,
                                goals=goals,
                                grain=grain,
                                derived_metrics=derived_metrics,
                            ),'''
H2_NEW = '''                            generate_charts_with_llm(
                                db=db,
                                theme=theme_tag,
                                fields=fields,
                                goals=goals,
                                grain=grain,
                                derived_metrics=derived_metrics,
                                field_profiles=field_profiles,
                            ),'''
assert s2.count(H2_OLD) == 1, ("H2", s2.count(H2_OLD))
s2 = s2.replace(H2_OLD, H2_NEW)

# I: _retry_s3_with_ai 签名 + 透传 + 调用点
I_OLD = '''async def _retry_s3_with_ai(run_id, db, theme_tag, fields, goals, grain, reason,
                            max_rounds: int = 3, derived_metrics=None):'''
I_NEW = '''async def _retry_s3_with_ai(run_id, db, theme_tag, fields, goals, grain, reason,
                            max_rounds: int = 3, derived_metrics=None, field_profiles=None):'''
assert s2.count(I_OLD) == 1, ("I", s2.count(I_OLD))
s2 = s2.replace(I_OLD, I_NEW)

I2_OLD = '''            res = await generate_charts_with_llm(
                db=db, theme=theme_tag, fields=fields, goals=goals, grain=grain,
                derived_metrics=derived_metrics or {}
            )'''
I2_NEW = '''            res = await generate_charts_with_llm(
                db=db, theme=theme_tag, fields=fields, goals=goals, grain=grain,
                derived_metrics=derived_metrics or {}, field_profiles=field_profiles
            )'''
assert s2.count(I2_OLD) == 1, ("I2", s2.count(I2_OLD))
s2 = s2.replace(I2_OLD, I2_NEW)

I3_OLD = '''                s3_result, s3_ai_failed = await _retry_s3_with_ai(
                        run_id, db, theme_tag, fields, goals, grain, s3_ai_reason,
                        derived_metrics=derived_metrics
                    )'''
I3_NEW = '''                s3_result, s3_ai_failed = await _retry_s3_with_ai(
                        run_id, db, theme_tag, fields, goals, grain, s3_ai_reason,
                        derived_metrics=derived_metrics, field_profiles=field_profiles
                    )'''
assert s2.count(I3_OLD) == 1, ("I3", s2.count(I3_OLD))
s2 = s2.replace(I3_OLD, I3_NEW)

io.open(P2, "w", encoding="utf-8").write(s2)
print("[brain_run_sse] changed:", s2 != orig2)
print("DONE")

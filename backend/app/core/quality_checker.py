"""八类质检引擎 - 完整性/唯一性/有效性/准确性/一致性/及时性/分布/业务规则
移植 B 的「数据契约驱动 + 全维度质检」理念，补全原六类为八类（新增及时性、分布）。"""
import re
from datetime import date, datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class IssueSeverity(Enum):
    """问题严重级别"""
    BLOCKING = "blocking"      # 必拦
    WARNING = "warning"        # 提示


class IssueType(Enum):
    """八类质检类型"""
    NULL = "null"              # 空值（完整性）
    FORMAT = "format"          # 格式（有效性）
    UNIQUE = "unique"          # 唯一（重复）
    RANGE = "range"            # 范围（准确性-域）
    LOGIC = "logic"            # 逻辑（业务规则）
    CODE = "code"             # 码值（准确性-编码）
    TIMELINESS = "timeliness"  # 及时性（日期时效：未来/过早）
    DISTRIBUTION = "distribution"  # 分布（统计异常值/IQR）


@dataclass
class QualityIssue:
    """质量问题"""
    issue_type: IssueType
    severity: IssueSeverity
    column: str
    row_indices: List[int]
    message: str
    sample_values: List[Any]
    rule_name: str
    repair_options: Optional[List[Dict]] = None  # 修复方案列表


class QualityChecker:
    """六类质检引擎"""
    
    # 检测顺序（唯一→空值→范围→逻辑→码值→格式→及时性→分布）
    DETECTION_ORDER = [
        IssueType.UNIQUE,
        IssueType.NULL,
        IssueType.RANGE,
        IssueType.LOGIC,
        IssueType.CODE,
        IssueType.FORMAT,
        IssueType.TIMELINESS,
        IssueType.DISTRIBUTION,
    ]
    
    def __init__(self, db_manager, brain_config: Optional[Dict] = None):
        """
        初始化质检引擎
        
        Args:
            db_manager: DuckDBManager实例
            brain_config: brain_configs中的阈值配置
        """
        self.db = db_manager
        self.config = brain_config or {}
        # 强制解析（coerce_numeric 清理货币/空白）与警告态修复受限开关
        self.coerce_numeric_on = bool(self.config.get("coerce_numeric_on", True))
        self._type_options_restricted = bool(self.config.get("restrict_repair_when_warn", False))
        
        # 默认阈值（从brain_configs读取，否则使用默认值）
        self.thresholds = {
            "null_rate": self.config.get("null_threshold", 0.05),      # 空值率阈值
            "format_error_rate": self.config.get("format_threshold", 0.05),  # 格式错误率
            "duplicate_rate": self.config.get("duplicate_threshold", 0.01),  # 重复率
        }
    
    def check_table(self, table_name: str, columns: List[Dict]) -> Dict[str, Any]:
        """
        对表进行六类质检
        
        Returns:
            {
                "issues": [QualityIssue, ...],
                "summary": {
                    "total_issues": 10,
                    "blocking_count": 5,
                    "warning_count": 5,
                    "by_type": {...}
                }
            }
        """
        self._cur_table = table_name  # 供 _build_samples / _col_fill 等复用到当前表
        issues = []
        
        # 按固定顺序执行检测器
        for issue_type in self.DETECTION_ORDER:
            if issue_type == IssueType.NULL:
                issues.extend(self._check_null(table_name, columns))
            elif issue_type == IssueType.FORMAT:
                issues.extend(self._check_format(table_name, columns))
                issues.extend(self._check_type_consistency(table_name, columns))
            elif issue_type == IssueType.UNIQUE:
                issues.extend(self._check_unique(table_name, columns))
            elif issue_type == IssueType.RANGE:
                issues.extend(self._check_range(table_name, columns))
            elif issue_type == IssueType.LOGIC:
                issues.extend(self._check_logic(table_name, columns))
            elif issue_type == IssueType.CODE:
                issues.extend(self._check_code(table_name, columns))
            elif issue_type == IssueType.TIMELINESS:
                issues.extend(self._check_timeliness(table_name, columns))
            elif issue_type == IssueType.DISTRIBUTION:
                issues.extend(self._check_distribution(table_name, columns))
        
        # 汇总
        blocking_count = sum(1 for i in issues if i.severity == IssueSeverity.BLOCKING)
        warning_count = len(issues) - blocking_count
        
        by_type = {}
        for t in IssueType:
            count = sum(1 for i in issues if i.issue_type == t)
            if count > 0:
                by_type[t.value] = count
        
        return {
            "issues": [
                {
                    "type": i.issue_type.value,
                    "severity": i.severity.value,
                    "column": i.column,
                    "row_count": len(i.row_indices),
                    "row_indices": list(i.row_indices),  # 行号列表，给修复接口精确定位
                    "message": i.message,
                    "sample_values": i.sample_values[:5],
                    "rule": i.rule_name,
                    "repair_options": i.repair_options or [],
                    # 2026-09-18 产品化：每个问题附最多 5 条真实受影响样本，
                    # 供前端展示「原始数据第几行 + 清洗前的值 + 对应的问题 + 清洗后处理成的结果」
                    "samples": self._build_samples(i, table_name),
                }
                for i in issues
            ],
            "summary": {
                "total_issues": len(issues),
                "blocking_count": blocking_count,
                "warning_count": warning_count,
                "by_type": by_type,
                "can_proceed": blocking_count == 0  # 必拦清零才能继续
            }
        }
    
    def _is_primary_key(self, col_name: str) -> bool:
        """
        判断是否为可明确的主键字段
        
        根据字段名关键词识别主键类型字段
        """
        col_lower = col_name.lower()
        # 主键/编号关键词
        pk_keywords = ['id', '编号', '借据', '合同', '订单', '流水', 'no.', '序号', 'code', '编码']
        return any(kw in col_lower for kw in pk_keywords)
    
    def _get_repair_options(self, issue_type: IssueType, column: str) -> List[Dict]:
        """获取预设修复方案（不依赖AI）；带 recommended 标记的是该类问题的默认推荐方案，
        供前端"一键采纳推荐方案"批量执行（2026-09-17 对齐 B 的推荐清洗计划交互）"""
        REPAIR_OPTIONS = {
            IssueType.NULL: [
                {"strategy": "fill_median", "label": "用中位数填充", "description": "使用该字段的中位数填充空值", "recommended": True},
                {"strategy": "fill_mean", "label": "用均值填充", "description": "使用该字段的平均值填充空值"},
                {"strategy": "fill_mode", "label": "用众数填充", "description": "使用该字段出现最多的值填充空值"},
                {"strategy": "fill_constant", "label": "指定值填充", "description": "输入自定义值填充空值"},
                {"strategy": "drop", "label": "删除空值行", "description": "删除包含空值的行"},
            ],
            IssueType.FORMAT: [
                {"strategy": "convert_standard", "label": "统一转换为标准格式", "description": "自动转换为标准格式（如日期YYYY-MM-DD）"},
                {"strategy": "coerce_numeric", "label": "强制转换为数值", "description": "清理千分位/货币/空格，尝试转为真正的数值类型", "recommended": True},
                {"strategy": "mark_anomaly", "label": "标记为异常值", "description": "标记为异常值，后续分析时跳过"},
                {"strategy": "drop", "label": "删除错误行", "description": "删除格式错误的数据行"},
            ],
            IssueType.UNIQUE: [
                {"strategy": "keep_first", "label": "去重保留第一条", "description": "保留首次出现的记录，删除重复行", "recommended": True},
                {"strategy": "keep_last", "label": "去重保留最后一条", "description": "保留最后一次出现的记录，删除重复行"},
                {"strategy": "mark_duplicate", "label": "标记重复不删除", "description": "标记为重复值，保留所有数据"},
            ],
            IssueType.RANGE: [
                {"strategy": "fill_boundary", "label": "用边界值替换", "description": "将超出范围的值替换为边界值（最大/最小）", "recommended": True},
                {"strategy": "fill_median", "label": "用中位数替换异常值", "description": "使用该字段中位数替换超出范围的值"},
                {"strategy": "mark_anomaly", "label": "标记为异常值", "description": "标记为异常值，后续分析时跳过"},
                {"strategy": "drop", "label": "删除异常行", "description": "删除包含异常值的行"},
            ],
            IssueType.LOGIC: [
                {"strategy": "mark_anomaly", "label": "标记为异常值", "description": "标记为逻辑矛盾，后续分析时跳过", "recommended": True},
                {"strategy": "swap_values", "label": "交换矛盾字段值", "description": "交换逻辑矛盾的两个字段值"},
                {"strategy": "drop", "label": "删除矛盾行", "description": "删除包含逻辑矛盾的行"},
            ],
            IssueType.CODE: [
                {"strategy": "map_closest", "label": "映射到最接近的标准码值", "description": "自动匹配并映射到标准码值", "recommended": True},
                {"strategy": "mark_anomaly", "label": "标记为异常码值", "description": "标记为非标准码值，后续处理"},
                {"strategy": "drop", "label": "删除异常码值行", "description": "删除包含非标准码值的行"},
            ],
            IssueType.TIMELINESS: [
                {"strategy": "set_today", "label": "未来日期置为今天", "description": "将未来日期修正为当前日期", "recommended": True},
                {"strategy": "mark_anomaly", "label": "标记为时效异常", "description": "标记为时效异常，后续分析时跳过"},
                {"strategy": "drop", "label": "删除异常日期行", "description": "删除未来/过早日期的数据行"},
            ],
            IssueType.DISTRIBUTION: [
                {"strategy": "winsorize", "label": "截断到 P1/P99", "description": "将离群值裁剪到第1/99百分位边界（缩尾处理）", "recommended": True},
                {"strategy": "fill_median", "label": "用中位数替换离群值", "description": "使用中位数替换统计离群值"},
                {"strategy": "mark_anomaly", "label": "标记为离群值", "description": "标记为统计离群，后续分析时跳过"},
                {"strategy": "drop", "label": "删除离群行", "description": "删除统计离群的数据行"},
            ],
        }
        # 警告（非阻断）时不提供破坏性修复，只建议确认/忽略，防止误删干净数据
        if self._type_options_restricted:
            REPAIR_OPTIONS = {
                t: [o for o in opts if o["strategy"] != "drop"]
                for t, opts in REPAIR_OPTIONS.items()
            }
        return REPAIR_OPTIONS.get(issue_type, [])
    
    # ==================== 产品化样本（原始行 + 清洗后结果） ====================
    # 2026-09-18 产品化：为每个问题附最多 5 条真实受影响样本，供前端展示
    # 「原始数据第几行 + 清洗前的值 + 对应的问题 + 清洗后处理成的结果」。
    # 清洗后结果由本类按推荐修复策略做轻量模拟（与 /quality/fix 的实际 SQL 口径一致），
    # 不改原始层、不影响修复写库，仅用于预览告知用户「点了修复后会变成什么样」。

    def _build_samples(self, issue, table_name: str) -> List[Dict[str, Any]]:
        """为单条问题构造产品化样本（行号 / 原值 / 问题说明 / 清洗后结果）"""
        rids = list(issue.row_indices or [])[:5]
        if not rids:
            return []
        cols = [c.strip() for c in str(issue.column).split(",") if c.strip()]
        if not cols:
            return []
        sel = ", ".join(f'"{c}"' for c in cols)
        # rowid 来自本类自身查询（整数），内联安全，无注入风险
        rid_list = ", ".join(str(int(r)) for r in rids)
        try:
            rows = self.db.conn.execute(
                f'SELECT rowid, {sel} FROM {table_name} WHERE rowid IN ({rid_list})'
            ).fetchall()
        except Exception:
            return []

        # 推荐修复策略（与前端"一键采纳推荐方案"口径一致：优先 recommended）
        rec = None
        for o in (issue.repair_options or []):
            if o.get("recommended"):
                rec = o.get("strategy")
                break
        if rec is None:
            for o in (issue.repair_options or []):
                s = o.get("strategy")
                if s and s not in ("ignore",):
                    rec = s
                    break

        samples = []
        for row in rows:
            rowid = row[0]
            vals = list(row[1:])
            raw = str(vals[0]) if len(vals) == 1 else " → ".join(str(v) for v in vals)
            note = self._problem_note(issue)
            fixed, action = self._simulate_fix(issue, rec, vals)
            samples.append({
                "row": int(rowid),
                "raw": raw,
                "problem": note,
                "fixed": fixed,
                "action": action,
            })
        return samples

    def _problem_note(self, issue) -> str:
        """把技术问题翻译成用户能看懂的一句话问题说明"""
        t = issue.issue_type.value if hasattr(issue.issue_type, "value") else issue.issue_type
        col_l = (issue.column or "").lower()
        msg = issue.message or ""
        if t == "null":
            return "该单元格为空，分析时会被忽略或报错"
        if t == "range":
            if any(k in col_l for k in ("rate", "比率", "抵押率", "dyl")):
                return "抵押率应介于 0~100%，当前超出范围"
            return "数值超出合理取值范围"
        if t == "format":
            if any(k in col_l for k in ("date", "日期", "时间", "rq", "sj")):
                return "日期格式不标准，应为 YYYY-MM-DD"
            return "数字被当成文本，无法参与计算"
        if t == "unique":
            return "与其它行重复，主键必须唯一"
        if t == "logic":
            return "到期日早于放款日，存在逻辑矛盾"
        if t == "code":
            return "使用了非标准码值"
        if t == "timeliness":
            if "未来" in msg:
                return "日期晚于今天，疑似录入错误"
            return "日期过早，疑似错误"
        if t == "distribution":
            return "偏离正常分布，属统计离群值"
        return "数据异常"

    def _simulate_fix(self, issue, strategy, vals) -> tuple:
        """按推荐策略模拟清洗结果。返回 (清洗后结果字符串|None, 动作)。
        action: modify 改写 / delete 删除该行 / keep 保留（标记）/ mask 脱敏"""
        t = issue.issue_type.value if hasattr(issue.issue_type, "value") else issue.issue_type
        msg = issue.message or ""
        raw = vals[0] if vals else None
        table = self._cur_table
        if strategy in ("drop",):
            return (None, "delete")
        if t == "null":
            if strategy in ("fill_median", "fill_mean", "fill_mode"):
                v = self._col_fill(issue.column, strategy, table)
                return (f"{v}", "modify") if v is not None else ("填充统计值", "modify")
            if strategy == "fill_constant":
                return ("0", "modify")
            return ("填充", "modify")
        if t == "format":
            if strategy == "convert_standard" and raw is not None:
                f = self._reformat_date(str(raw))
                return (f, "modify") if f else ("标准格式", "modify")
            if strategy == "coerce_numeric" and raw is not None:
                s = re.sub(r'[￥¥$\s\u00a0,，]', '', str(raw).strip())
                try:
                    float(s)
                    return (s, "modify")
                except ValueError:
                    return ("（无法转数值，置空）", "modify")
            return ("修正格式", "modify")
        if t == "unique":
            return (None, "delete")
        if t == "range":
            if strategy in ("fill_boundary", "fill_median"):
                v = self._col_fill(issue.column, "fill_median", table)
                return (f"{v}（列中位数）" if v is not None else "边界值", "modify")
            return ("修正异常值", "modify")
        if t == "logic":
            if strategy == "swap_values":
                return ("交换放款日与到期日", "modify")
            if strategy == "mark_anomaly":
                return (str(raw), "keep")
            return ("（删除矛盾行）", "delete")
        if t == "code":
            if strategy == "map_closest" and raw is not None and "其它" in str(raw):
                return ("其他", "modify")
            return ("映射为标准码值", "modify")
        if t == "timeliness":
            if "未来" in msg:
                return (date.today().isoformat(), "modify")
            return ("（建议人工确认日期）", "keep")
        if t == "distribution":
            if strategy == "winsorize":
                lo, hi = self._col_quantiles(issue.column, table)
                if lo is not None and hi is not None and raw is not None:
                    try:
                        x = float(re.sub(r'[￥¥$\s\u00a0,，]', '', str(raw)))
                        cval = max(lo, min(hi, x))
                        return (f"{cval:.2f}（截断到 P1/P99）", "modify")
                    except ValueError:
                        pass
                return ("截断到 P1/P99", "modify")
            if strategy == "fill_median":
                v = self._col_fill(issue.column, "fill_median", table)
                return (f"{v}" if v is not None else "中位数", "modify")
            if strategy == "ignore":
                return (str(raw), "keep")
            return ("修正离群值", "modify")
        return ("修复", "modify")

    def _col_fill(self, col, kind, table) -> Any:
        """计算列的填充统计值（median/mean/mode），用于空值/异常值修复预览"""
        try:
            qc = f'"{col}"'
            if kind == "fill_median":
                r = self.db.conn.execute(f'SELECT MEDIAN(CAST({qc} AS DOUBLE)) FROM {table} WHERE {qc} IS NOT NULL').fetchone()
            elif kind == "fill_mean":
                r = self.db.conn.execute(f'SELECT AVG(CAST({qc} AS DOUBLE)) FROM {table} WHERE {qc} IS NOT NULL').fetchone()
            elif kind == "fill_mode":
                r = self.db.conn.execute(f'SELECT {qc} FROM {table} WHERE {qc} IS NOT NULL GROUP BY {qc} ORDER BY COUNT(*) DESC LIMIT 1').fetchone()
            else:
                return None
            return r[0] if r and r[0] is not None else None
        except Exception:
            return None

    def _col_quantiles(self, col, table) -> tuple:
        """返回列 P1/P99 分位，用于分布离群缩尾预览"""
        try:
            qc = f'"{col}"'
            r = self.db.conn.execute(
                f'SELECT quantile_cont(CAST({qc} AS DOUBLE), 0.01), quantile_cont(CAST({qc} AS DOUBLE), 0.99) '
                f'FROM {table} WHERE {qc} IS NOT NULL'
            ).fetchone()
            if r and r[0] is not None and r[1] is not None:
                return float(r[0]), float(r[1])
        except Exception:
            pass
        return (None, None)

    def _reformat_date(self, s: str) -> Optional[str]:
        """把常见日期写法归一为 YYYY-MM-DD"""
        s = s.strip()
        fmts = [
            ("%Y/%m/%d", "%Y-%m-%d"),
            ("%Y%m%d", "%Y-%m-%d"),
            ("%Y年%m月%d日", "%Y-%m-%d"),
        ]
        for src, dst in fmts:
            try:
                return datetime.strptime(s, src).strftime(dst)
            except ValueError:
                continue
        return None

    # ==================== M1-08a: 空值检测（必拦/提示） ====================
    
    def _check_null(self, table_name: str, columns: List[Dict]) -> List[QualityIssue]:
        """
        空值检测 - 主键空值必拦，其他空值提示
        
        规则：主键字段空值 → BLOCKING
              普通字段空值超阈值 → WARNING
        """
        issues = []
        threshold = self.thresholds["null_rate"]
        
        for col in columns:
            col_name = col["name"]
            is_pk = self._is_primary_key(col_name)
            
            # 计算空值数量和行号
            null_rows = self.db.conn.execute(f"""
                SELECT rowid 
                FROM {table_name} 
                WHERE "{col_name}" IS NULL 
                   OR CAST("{col_name}" AS VARCHAR) = '' 
                   OR TRIM(CAST("{col_name}" AS VARCHAR)) = ''
            """).fetchall()
            
            if not null_rows:
                continue
            
            # 计算空值率
            total_rows = self.db.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            null_rate = len(null_rows) / total_rows
            
            # 主键空值 → 必拦（即使空值率很低）
            if is_pk and null_rows:
                issues.append(QualityIssue(
                    issue_type=IssueType.NULL,
                    severity=IssueSeverity.BLOCKING,
                    column=col_name,
                    row_indices=[r[0] for r in null_rows[:10]],
                    message=f"主键字段存在 {len(null_rows)} 个空值，必须修复",
                    sample_values=["NULL"] * min(5, len(null_rows)),
                    rule_name="主键空值检测",
                    repair_options=self._get_repair_options(IssueType.NULL, col_name)
                ))
                continue
            
            # 普通字段空值超阈值 → 提示
            if null_rate > threshold:
                issues.append(QualityIssue(
                    issue_type=IssueType.NULL,
                    severity=IssueSeverity.WARNING,
                    column=col_name,
                    row_indices=[r[0] for r in null_rows[:10]],
                    message=f"空值率 {null_rate:.1%} 超过阈值 {threshold:.1%}，建议修复",
                    sample_values=["NULL"] * min(5, len(null_rows)),
                    rule_name="空值检测",
                    repair_options=self._get_repair_options(IssueType.NULL, col_name)
                ))
        
        return issues
    
    # ==================== M1-08a: 格式检测（必拦） ====================
    
    def _check_format(self, table_name: str, columns: List[Dict]) -> List[QualityIssue]:
        """
        格式检测 - 必拦项
        
        检测：日期格式、手机号、身份证等格式错误
        """
        issues = []
        threshold = self.thresholds["format_error_rate"]
        
        for col in columns:
            col_name = col["name"].lower()
            col_type = self._guess_column_type(col_name)
            
            if col_type == "date":
                # 检测日期格式
                issues.extend(self._check_date_format(table_name, col["name"], threshold))
            elif col_type == "phone":
                # 检测手机号格式
                issues.extend(self._check_phone_format(table_name, col["name"], threshold))
            elif col_type == "idcard":
                # 检测身份证格式
                issues.extend(self._check_idcard_format(table_name, col["name"], threshold))
        
        return issues
    
    def _check_date_format(self, table_name: str, col_name: str, threshold: float) -> List[QualityIssue]:
        """检测日期格式（支持多种格式）"""
        # 支持的日期格式正则
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',           # 2024-01-01
            r'^\d{4}/\d{2}/\d{2}$',           # 2024/01/01
            r'^\d{8}$',                        # 20240101
            r'^\d{4}年\d{2}月\d{2}日$',       # 2024年01月01日
        ]
        
        # 获取所有非空值
        rows = self.db.conn.execute(f"""
            SELECT rowid, "{col_name}" 
            FROM {table_name} 
            WHERE "{col_name}" IS NOT NULL
        """).fetchall()
        
        # 检测格式错误
        error_rows = []
        error_samples = []
        
        for rowid, value in rows:
            value_str = str(value).strip()
            # 尝试匹配任一格式
            matched = any(re.match(p, value_str) for p in date_patterns)
            if not matched:
                error_rows.append(rowid)
                if len(error_samples) < 5:
                    error_samples.append(value_str)
        
        if not error_rows:
            return []
        
        # 计算错误率
        total_rows = len(rows)
        error_rate = len(error_rows) / total_rows if total_rows > 0 else 0
        
        if error_rate > threshold:
            return [QualityIssue(
                issue_type=IssueType.FORMAT,
                severity=IssueSeverity.BLOCKING,
                column=col_name,
                row_indices=error_rows[:10],
                message=f"检测到 {len(error_rows)} 行日期格式错误，发现 {self._count_date_patterns(rows)} 种不同格式",
                sample_values=error_samples,
                rule_name="日期格式检测",
                repair_options=self._get_repair_options(IssueType.FORMAT, col_name)
            )]
        
        return []
    
    def _count_date_patterns(self, rows: List[tuple]) -> int:
        """统计日期格式种类"""
        patterns = set()
        date_patterns = [
            (r'^\d{4}-\d{2}-\d{2}$', 'YYYY-MM-DD'),
            (r'^\d{4}/\d{2}/\d{2}$', 'YYYY/MM/DD'),
            (r'^\d{8}$', 'YYYYMMDD'),
            (r'^\d{4}年\d{2}月\d{2}日$', 'YYYY年MM月DD日'),
        ]
        
        for _, value in rows[:100]:  # 抽样100行
            value_str = str(value).strip()
            for pattern, name in date_patterns:
                if re.match(pattern, value_str):
                    patterns.add(name)
                    break
        
        return len(patterns)
    
    def _check_phone_format(self, table_name: str, col_name: str, threshold: float) -> List[QualityIssue]:
        """检测手机号格式"""
        # 手机号正则
        phone_pattern = r'^1[3-9]\d{9}$'
        
        rows = self.db.conn.execute(f"""
            SELECT rowid, CAST("{col_name}" AS VARCHAR) 
            FROM {table_name} 
            WHERE "{col_name}" IS NOT NULL
        """).fetchall()
        
        error_rows = []
        error_samples = []
        
        for rowid, value in rows:
            value_str = str(value).strip().replace('-', '').replace(' ', '')
            if not re.match(phone_pattern, value_str):
                error_rows.append(rowid)
                if len(error_samples) < 5:
                    error_samples.append(value_str[:20])
        
        if error_rows:
            return [QualityIssue(
                issue_type=IssueType.FORMAT,
                severity=IssueSeverity.BLOCKING,
                column=col_name,
                row_indices=error_rows[:10],
                message=f"检测到 {len(error_rows)} 行手机号格式错误",
                sample_values=error_samples,
                rule_name="手机号格式检测",
                repair_options=self._get_repair_options(IssueType.FORMAT, col_name)
            )]
        
        return []
    
    def _check_idcard_format(self, table_name: str, col_name: str, threshold: float) -> List[QualityIssue]:
        """检测身份证格式"""
        # 身份证正则（简化版）
        idcard_pattern = r'(^\d{15}$)|(^\d{18}$)|(^\d{17}[\dXx]$)'
        
        rows = self.db.conn.execute(f"""
            SELECT rowid, CAST("{col_name}" AS VARCHAR) 
            FROM {table_name} 
            WHERE "{col_name}" IS NOT NULL
        """).fetchall()
        
        error_rows = []
        error_samples = []
        
        for rowid, value in rows:
            value_str = str(value).strip()
            if not re.match(idcard_pattern, value_str):
                error_rows.append(rowid)
                if len(error_samples) < 5:
                    # 脱敏显示
                    if len(value_str) > 8:
                        error_samples.append(value_str[:3] + "***" + value_str[-4:])
                    else:
                        error_samples.append(value_str)
        
        if error_rows:
            return [QualityIssue(
                issue_type=IssueType.FORMAT,
                severity=IssueSeverity.BLOCKING,
                column=col_name,
                row_indices=error_rows[:10],
                message=f"检测到 {len(error_rows)} 行身份证格式错误",
                sample_values=error_samples,
                rule_name="身份证格式检测",
                repair_options=self._get_repair_options(IssueType.FORMAT, col_name)
            )]
        
        return []
    
    def _guess_column_type(self, col_name: str) -> str:
        """根据列名猜测字段类型"""
        col_lower = col_name.lower()
        
        # 主键/编号
        if any(kw in col_lower for kw in ['id', '编号', '借据', '合同', '订单', 'no.', '序号']):
            return "id"
        
        # 日期
        if any(kw in col_lower for kw in ['date', 'dt', '日期', '时间', 'rq', 'sj']):
            return "date"
        
        # 手机号
        if any(kw in col_lower for kw in ['phone', 'mobile', '电话', '手机', 'dh', 'sjh']):
            return "phone"
        
        # 身份证
        if any(kw in col_lower for kw in ['idcard', '身份证', 'sfz', 'id_no']):
            return "idcard"
        
        # 数值
        if any(kw in col_lower for kw in ['amount', 'rate', '金额', '价格', '率', '值', '数量']):
            return "number"
        
        return "unknown"

    # ==================== 文本型数字检测（数值被识别成文本，必拦） ====================
    # 通用规则（不依赖AI，可随业务不断丰富）：把"看起来像数值、实际被读成文本"的列识别出来，
    # 并给出「强制转数值」一键修复。规则库常量放文件底部 _TEXTNUM_RE 等，便于持续扩充。

    def _normalize_numeric_str(self, s: str) -> str:
        """把文本型数字清洗成可解析形式。清洗规则必须与 /quality/fix 的 coerce_numeric 完全一致，
        否则会出现『检测判定可转、修复却置 NULL』的不一致。当前仅处理：货币符/千分位/空白(NBSP)。
        尾缀单位（元/万元/%）不做剥离，避免量级误转（如 1.2万元→1.2）。"""
        return re.sub(r'[￥¥$\s\u00a0,，]', '', s.strip())

    def _coercible_numeric(self, s: str) -> bool:
        """该值清洗后能否转为 float（据此判断"文本型数字"）"""
        if s is None:
            return True  # 空值不参与文本污染判断
        try:
            float(self._normalize_numeric_str(str(s)))
            return True
        except (ValueError, TypeError):
            return False

    def _check_type_consistency(self, table_name: str, columns: List[Dict]) -> List[QualityIssue]:
        """
        类型一致性检测 - 必拦项
        识别"数值列被读成文本"（如 1,234 / ￥100 / '5000' / 混入'N/A' 导致整列文本）。
        高置信文本型数字 → 强转数值修复（写清洗层，不动原始层）。
        """
        issues = []
        if not self.coerce_numeric_on:
            return issues

        total = self.db.conn.execute(f'SELECT COUNT(*) FROM {table_name}').fetchone()[0]
        if not total:
            return issues

        for col in columns:
            col_name = col["name"]
            if self._is_primary_key(col_name):
                continue
            rows = self.db.conn.execute(
                f'SELECT rowid, CAST("{col_name}" AS VARCHAR) FROM {table_name} '
                f'WHERE "{col_name}" IS NOT NULL AND TRIM(CAST("{col_name}" AS VARCHAR)) != \'\''
            ).fetchall()
            if not rows:
                continue
            values = [r[1] for r in rows]
            contaminated = [v for v in values if not self._coercible_numeric(v)]
            coercible_rate = (len(values) - len(contaminated)) / len(values)

            # 高置信判数值：可转率过半才进入数字判定；真实枚举列（性别/状态）可转率低，天然被这个门槛挡掉
            if coercible_rate < _NUMERIC_RATIO:
                continue
            if not contaminated:
                continue

            severity = (
                IssueSeverity.BLOCKING
                if len(contaminated) / len(values) <= _NUMERIC_DOMINANT_RATIO
                else IssueSeverity.WARNING
            )
            rule_name = "文本型数字强制检测" if severity == IssueSeverity.BLOCKING else "文本型数字提示验证"
            issues.append(QualityIssue(
                issue_type=IssueType.FORMAT,
                severity=severity,
                column=col_name,
                row_indices=[r[0] for r in rows[:10]],
                message=(
                    f"字段『{col_name}』疑似数值被读成文本：{len(contaminated)}/{len(values)} 行无法转数值"
                    f"（样例 {contaminated[:3]}），建议一键转为数值后继续"
                ),
                sample_values=contaminated[:5],
                rule_name=rule_name,
                repair_options=self._get_repair_options(IssueType.FORMAT, col_name)
            ))
        return issues

    # ==================== M1-08b: 其余四类（提示项） ====================
    
    def _check_unique(self, table_name: str, columns: List[Dict]) -> List[QualityIssue]:
        """唯一性检测 - 可明确主键则阻断，否则提示"""
        issues = []

        for col in columns:
            col_name = col["name"]

            # 只有识别为主键才检测唯一性
            if not self._is_primary_key(col_name):
                continue

            # ===== 唯一度复核（防误伤）：名字像主键 ≠ 真是主键 =====
            # 2026-09-17 取长补短自 InsightDesk：客户号/客户ID 天然一对多（一个客户多笔借据），
            # 只凭列名关键词判主键会把这类 1:N 业务列误 BLOCKING。
            # 故加 UNIQ_KEY_RATIO 门槛：实际唯一度（不同值/非空值）≥ 95% 才按唯一键处理。
            UNIQ_KEY_RATIO = 0.95
            try:
                stat = self.db.conn.execute(
                    f'SELECT COUNT("{col_name}"), COUNT(DISTINCT "{col_name}") '
                    f'FROM {table_name} WHERE "{col_name}" IS NOT NULL'
                ).fetchone()
                non_null, distinct_cnt = (stat[0] or 0), (stat[1] or 0)
            except Exception:
                non_null, distinct_cnt = 0, 0
            if non_null > 0:
                ratio = (distinct_cnt / non_null) if non_null else 0
                if ratio < UNIQ_KEY_RATIO:
                    # 形似主键但唯一度明显偏低 → 判为维度/外键，仅提示、不阻断
                    issues.append(QualityIssue(
                        issue_type=IssueType.UNIQUE,
                        severity=IssueSeverity.WARNING,
                        column=col_name,
                        row_indices=[],
                        sample_values=[],
                        message=(
                            f"「{col_name}」名称形似主键，但实际唯一度仅 {ratio*100:.1f}%"
                            f"（{non_null} 个非空值中仅 {distinct_cnt} 个不同），更可能是维度/外键"
                            f"（如一个客户对应多笔借据），重复属正常业务形态。"
                            f"已按非唯一键处理、不阻断分析；若确认它必须是唯一键，请在清洗中人工处理。"
                        ),
                        rule_name="主键唯一性检测(唯一度复核)",
                        repair_options=[{
                            "strategy": "ignore",
                            "label": "忽略（确认非主键）",
                            "description": "该列为业务外键/维度，重复属正常形态"
                        }]
                    ))
                    continue

            # 查找重复值（先按字段值聚合，再单独取这些值对应的 rowid）
            dups = self.db.conn.execute(f"""
                SELECT "{col_name}", COUNT(*) as cnt
                FROM {table_name}
                WHERE "{col_name}" IS NOT NULL
                GROUP BY "{col_name}"
                HAVING COUNT(*) > 1
            """).fetchall()

            if dups:
                total_dup_rows = sum(d[1] for d in dups)
                sample_values = [str(d[0]) for d in dups[:5]]

                # 取所有重复行 rowid：用于前端展示"数量=涉及行数"，并让"去重"修复能精确定位行
                dup_value_set = [d[0] for d in dups]
                placeholders = ','.join(['?'] * len(dup_value_set))
                dup_row_ids_res = self.db.conn.execute(
                    f'SELECT rowid FROM {table_name} WHERE "{col_name}" IN ({placeholders})',
                    dup_value_set,
                ).fetchall()
                dup_row_ids = [r[0] for r in dup_row_ids_res]

                issues.append(QualityIssue(
                    issue_type=IssueType.UNIQUE,
                    severity=IssueSeverity.BLOCKING,  # 主键重复必须修复
                    column=col_name,
                    row_indices=dup_row_ids,  # 所有重复行 rowid（前端 row_count 由此展示真实"涉及行数"）
                    message=f"检测到 {len(dups)} 个重复值，涉及 {total_dup_rows} 行，主键必须唯一",
                    sample_values=sample_values,
                    rule_name="主键唯一性检测",
                    repair_options=self._get_repair_options(IssueType.UNIQUE, col_name)
                ))

        return issues
    
    def _check_range(self, table_name: str, columns: List[Dict]) -> List[QualityIssue]:
        """范围检测 - 提示项"""
        issues = []
        
        for col in columns:
            col_name = col["name"]
            col_lower = col_name.lower()
            
            # 检测抵押率>100%
            if any(kw in col_lower for kw in ['rate', '比率', '抵押率', 'dyl']):
                invalid = self.db.conn.execute(f"""
                    SELECT rowid, "{col_name}"
                    FROM {table_name}
                    WHERE CAST("{col_name}" AS DOUBLE) > 1.0
                       OR CAST("{col_name}" AS DOUBLE) < 0
                """).fetchall()
                
                if invalid:
                    issues.append(QualityIssue(
                        issue_type=IssueType.RANGE,
                        severity=IssueSeverity.WARNING,
                        column=col_name,
                        row_indices=[r[0] for r in invalid[:10]],
                        message=f"检测到 {len(invalid)} 行抵押率超出0-100%范围",
                        sample_values=[r[1] for r in invalid[:5]],
                        rule_name="抵押率范围检测",
                        repair_options=self._get_repair_options(IssueType.RANGE, col_name)
                    ))
        
        return issues
    
    def _check_logic(self, table_name: str, columns: List[Dict]) -> List[QualityIssue]:
        """逻辑检测 - 提示项"""
        issues = []
        
        # 检测到期日期 < 放款日期
        col_names = [c["name"].lower() for c in columns]
        
        start_date_col = None
        end_date_col = None
        
        for c in columns:
            cl = c["name"].lower()
            if any(kw in cl for kw in ['start', '放款', '开始', 'fk']):
                start_date_col = c["name"]
            if any(kw in cl for kw in ['end', '到期', '结束', 'dq']):
                end_date_col = c["name"]
        
        if start_date_col and end_date_col:
            invalid = self.db.conn.execute(f"""
                SELECT rowid, "{start_date_col}", "{end_date_col}"
                FROM {table_name}
                WHERE "{end_date_col}" < "{start_date_col}"
            """).fetchall()
            
            if invalid:
                issues.append(QualityIssue(
                    issue_type=IssueType.LOGIC,
                    severity=IssueSeverity.WARNING,
                    column=f"{start_date_col}, {end_date_col}",
                    row_indices=[r[0] for r in invalid[:10]],
                    message=f"检测到 {len(invalid)} 行到期日期早于放款日期",
                    sample_values=[f"{r[1]} -> {r[2]}" for r in invalid[:5]],
                    rule_name="日期逻辑检测",
                    repair_options=self._get_repair_options(IssueType.LOGIC, f"{start_date_col}, {end_date_col}")
                ))
        
        return issues
    
    def _check_code(self, table_name: str, columns: List[Dict]) -> List[QualityIssue]:
        """码值检测 - 提示项"""
        issues = []
        
        for col in columns:
            col_name = col["name"]
            col_lower = col_name.lower()
            
            # 检测担保类型中的"其它"
            if any(kw in col_lower for kw in ['type', '类型', '担保', 'db']):
                others = self.db.conn.execute(f"""
                    SELECT rowid, "{col_name}"
                    FROM {table_name}
                    WHERE LOWER(CAST("{col_name}" AS VARCHAR)) IN ('其它', '其他', '其他类型', '其它类型')
                """).fetchall()
                
                if others:
                    issues.append(QualityIssue(
                        issue_type=IssueType.CODE,
                        severity=IssueSeverity.WARNING,
                        column=col_name,
                        row_indices=[r[0] for r in others[:10]],
                        message=f"检测到 {len(others)} 行使用'其它'码值",
                        sample_values=[r[1] for r in others[:5]],
                        rule_name="码值规范性检测",
                        repair_options=self._get_repair_options(IssueType.CODE, col_name)
                    ))
        
        return issues

    # ==================== 新增：及时性（TIMELINESS） ====================

    def _check_timeliness(self, table_name: str, columns: List[Dict]) -> List[QualityIssue]:
        """及时性检测 - 提示项：日期列中存在未来日期或过早(>10年)日期"""
        issues = []
        today = date.today()
        old_threshold_days = 3650  # 10 年
        for col in columns:
            col_name = col["name"]
            ctype = (col.get("type") or "").upper()
            if not any(k in ctype for k in ("DATE", "TIME", "DATETIME", "TIMESTAMP")):
                # 列名含时间语义也纳入（如 create_time / 更新日期）
                if not any(k in col_name.lower() for k in ("date", "time", "日期", "时间", "日期", "年份", "月")):
                    continue
            try:
                rows = self.db.conn.execute(f"""
                    SELECT rowid, TRY_CAST("{col_name}" AS DATE)
                    FROM {table_name}
                    WHERE "{col_name}" IS NOT NULL
                """).fetchall()
            except Exception:
                continue
            future, too_old = [], []
            for rid, d in rows:
                if d is None:
                    continue
                if isinstance(d, datetime):
                    d = d.date()
                if d > today:
                    future.append(rid)
                elif (today - d).days > old_threshold_days:
                    too_old.append(rid)
            if future:
                issues.append(QualityIssue(
                    issue_type=IssueType.TIMELINESS,
                    severity=IssueSeverity.WARNING,
                    column=col_name,
                    row_indices=future[:10],
                    message=f"检测到 {len(future)} 行日期为未来日期（>{today}）",
                    sample_values=[str(today)],
                    rule_name="未来日期检测",
                    repair_options=self._get_repair_options(IssueType.TIMELINESS, col_name)
                ))
            if too_old:
                issues.append(QualityIssue(
                    issue_type=IssueType.TIMELINESS,
                    severity=IssueSeverity.WARNING,
                    column=col_name,
                    row_indices=too_old[:10],
                    message=f"检测到 {len(too_old)} 行日期过早（早于 {today.year - 10} 年）",
                    sample_values=[str(today)],
                    rule_name="过早日期检测",
                    repair_options=self._get_repair_options(IssueType.TIMELINESS, col_name)
                ))
        return issues

    # ==================== 新增：分布（DISTRIBUTION，统计异常值） ====================

    def _check_distribution(self, table_name: str, columns: List[Dict]) -> List[QualityIssue]:
        """分布检测 - 提示项（2026-09-17 对齐 InsightDesk 三口径）：
        ① P1/P99 统计异常值（B 同口径，如"有 47 个统计异常值（超出 [lo, hi]）"）
        ② 3σ 极端值（偏离均值 3 个标准差以上）
        ③ 零值占比（某列 ≥80% 为 0，提示确认业务形态，如逾期天数）
        旧 IQR×3 口径过松（同数据仅检出 B 的一半不到），已替换为 P1/P99。"""
        issues = []
        for col in columns:
            col_name = col["name"]
            ctype = (col.get("type") or "").upper()
            if not any(t in ctype for t in ("DECIMAL", "DOUBLE", "FLOAT", "INT", "BIGINT", "NUMERIC", "REAL")):
                continue
            try:
                res = self.db.conn.execute(f"""
                    SELECT rowid, CAST("{col_name}" AS DOUBLE) AS v
                    FROM {table_name}
                    WHERE "{col_name}" IS NOT NULL
                """).fetchall()
                stats = self.db.conn.execute(f"""
                    SELECT quantile_cont(CAST("{col_name}" AS DOUBLE), 0.01),
                           quantile_cont(CAST("{col_name}" AS DOUBLE), 0.99),
                           AVG(CAST("{col_name}" AS DOUBLE)),
                           STDDEV(CAST("{col_name}" AS DOUBLE))
                    FROM {table_name}
                    WHERE "{col_name}" IS NOT NULL
                """).fetchone()
            except Exception:
                continue
            pairs = [(r[0], r[1]) for r in res if r[1] is not None]
            if len(pairs) < 10 or stats is None:
                continue  # 样本不足不判定
            p1, p99, mu, sd = stats
            n = len(pairs)

            # ① P1/P99 统计异常值
            if p1 is not None and p99 is not None and p99 > p1:
                out_rows = [rid for rid, v in pairs if v < p1 or v > p99]
                if out_rows:
                    sample_vals = [v for _, v in pairs if v < p1 or v > p99][:5]
                    issues.append(QualityIssue(
                        issue_type=IssueType.DISTRIBUTION,
                        severity=IssueSeverity.WARNING,
                        column=col_name,
                        row_indices=out_rows[:10],
                        message=f"列「{col_name}」有 {len(out_rows)} 个统计异常值（超出 [{p1:.2f}, {p99:.2f}]）",
                        sample_values=sample_vals,
                        rule_name="分布异常值检测(P1/P99)",
                        repair_options=self._get_repair_options(IssueType.DISTRIBUTION, col_name)
                    ))

            # ② 3σ 极端值
            if mu is not None and sd is not None and sd > 0:
                lo, hi = mu - 3 * sd, mu + 3 * sd
                ext_rows = [rid for rid, v in pairs if v < lo or v > hi]
                if ext_rows:
                    sample_vals = [v for _, v in pairs if v < lo or v > hi][:5]
                    issues.append(QualityIssue(
                        issue_type=IssueType.DISTRIBUTION,
                        severity=IssueSeverity.WARNING,
                        column=col_name,
                        row_indices=ext_rows[:10],
                        message=f"列「{col_name}」有 {len(ext_rows)} 个极端值（偏离均值 3 个标准差以上）",
                        sample_values=sample_vals,
                        rule_name="极端值检测(3σ)",
                        repair_options=self._get_repair_options(IssueType.DISTRIBUTION, col_name)
                    ))

            # ③ 零值占比（≥80% 为 0 时提示，不自动修复——零值常为正常业务形态）
            zeros = sum(1 for _, v in pairs if v == 0)
            if zeros and zeros / n >= 0.8:
                # 零值占比不带"recommended"，一键采纳会跳过（不能拿截断/填充去动正常业务零值）
                base_opts = [dict(o) for o in self._get_repair_options(IssueType.DISTRIBUTION, col_name)]
                for o in base_opts:
                    o.pop("recommended", None)
                issues.append(QualityIssue(
                    issue_type=IssueType.DISTRIBUTION,
                    severity=IssueSeverity.WARNING,
                    column=col_name,
                    row_indices=[rid for rid, v in pairs if v == 0][:10],
                    message=f"列「{col_name}」零值占比 {zeros / n:.0%}（{zeros}/{n} 行为 0），请确认是否为正常业务形态"
                            f"（如逾期天数未逾期记 0 属正常，无需修复）",
                    sample_values=[0],
                    rule_name="零值占比检测",
                    repair_options=[{
                        "strategy": "ignore",
                        "label": "确认为正常形态，忽略",
                        "description": "零值是业务默认值（如未逾期=0天），保留不动",
                        "recommended": True,
                    }] + base_opts
                ))
        return issues


# ==================== 类型一致性规则库（可生长，不依赖AI） ====================
# 规则引擎的可迭代规则库：数值尾缀单位、判定阈值都集中在此，后续按行业/场景持续扩充，
# 让系统在完全不依赖 LLM 的情况下也能识别"文本型数字"，AI 只在规则低置信时介入增强。

# 文本型数字常见"尾缀单位"（判定与清洗共用，可随业务扩充）
_NUMERIC_SUFFIXES = [
    r'万元', r'千元', r'亿元', r'元', r'万', r'亿',
    r'公斤', r'千克', r'克', r'吨', r'斤',
    r'万元', r'mm', r'cm', r'm', r'km',
    r'个百分点', r'个百分点', r'%', r'％',
    r'个', r'笔', r'户', r'人', r'次', r'家', r'辆',
]

# 判定阈值（集中管理，便于调优/演进）
_NUMERIC_RATIO = 0.5            # 可转数值占比≥50% 才视为"疑似数值列"（低置信交给AI）
_NUMERIC_DOMINANT_RATIO = 0.3   # 脏值占比≤30% → 高置信数值列，阻断强转；超过则数值/文本五五开，降为提示交AI验证

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
                    "message": i.message,
                    "sample_values": i.sample_values[:5],
                    "rule": i.rule_name,
                    "repair_options": i.repair_options or []
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
        """获取预设修复方案（不依赖AI）"""
        REPAIR_OPTIONS = {
            IssueType.NULL: [
                {"strategy": "fill_mean", "label": "用均值填充", "description": "使用该字段的平均值填充空值"},
                {"strategy": "fill_median", "label": "用中位数填充", "description": "使用该字段的中位数填充空值"},
                {"strategy": "fill_mode", "label": "用众数填充", "description": "使用该字段出现最多的值填充空值"},
                {"strategy": "fill_constant", "label": "指定值填充", "description": "输入自定义值填充空值"},
                {"strategy": "drop", "label": "删除空值行", "description": "删除包含空值的行"},
            ],
            IssueType.FORMAT: [
                {"strategy": "convert_standard", "label": "统一转换为标准格式", "description": "自动转换为标准格式（如日期YYYY-MM-DD）"},
                {"strategy": "coerce_numeric", "label": "强制转换为数值", "description": "清理千分位/货币/空格，尝试转为真正的数值类型"},
                {"strategy": "mark_anomaly", "label": "标记为异常值", "description": "标记为异常值，后续分析时跳过"},
                {"strategy": "drop", "label": "删除错误行", "description": "删除格式错误的数据行"},
            ],
            IssueType.UNIQUE: [
                {"strategy": "keep_first", "label": "去重保留第一条", "description": "保留首次出现的记录，删除重复行"},
                {"strategy": "keep_last", "label": "去重保留最后一条", "description": "保留最后一次出现的记录，删除重复行"},
                {"strategy": "mark_duplicate", "label": "标记重复不删除", "description": "标记为重复值，保留所有数据"},
            ],
            IssueType.RANGE: [
                {"strategy": "fill_median", "label": "用中位数替换异常值", "description": "使用该字段中位数替换超出范围的值"},
                {"strategy": "fill_boundary", "label": "用边界值替换", "description": "将超出范围的值替换为边界值（最大/最小）"},
                {"strategy": "mark_anomaly", "label": "标记为异常值", "description": "标记为异常值，后续分析时跳过"},
                {"strategy": "drop", "label": "删除异常行", "description": "删除包含异常值的行"},
            ],
            IssueType.LOGIC: [
                {"strategy": "swap_values", "label": "交换矛盾字段值", "description": "交换逻辑矛盾的两个字段值"},
                {"strategy": "mark_anomaly", "label": "标记为异常值", "description": "标记为逻辑矛盾，后续分析时跳过"},
                {"strategy": "drop", "label": "删除矛盾行", "description": "删除包含逻辑矛盾的行"},
            ],
            IssueType.CODE: [
                {"strategy": "map_closest", "label": "映射到最接近的标准码值", "description": "自动匹配并映射到标准码值"},
                {"strategy": "mark_anomaly", "label": "标记为异常码值", "description": "标记为非标准码值，后续处理"},
                {"strategy": "drop", "label": "删除异常码值行", "description": "删除包含非标准码值的行"},
            ],
            IssueType.TIMELINESS: [
                {"strategy": "set_today", "label": "未来日期置为今天", "description": "将未来日期修正为当前日期"},
                {"strategy": "mark_anomaly", "label": "标记为时效异常", "description": "标记为时效异常，后续分析时跳过"},
                {"strategy": "drop", "label": "删除异常日期行", "description": "删除未来/过早日期的数据行"},
            ],
            IssueType.DISTRIBUTION: [
                {"strategy": "fill_median", "label": "用中位数替换离群值", "description": "使用中位数替换统计离群值"},
                {"strategy": "winsorize", "label": "缩尾处理", "description": "将离群值裁剪到上下界（IQR×3）"},
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
            
            # 查找重复值
            dups = self.db.conn.execute(f"""
                SELECT "{col_name}", COUNT(*) as cnt, array_agg(rowid) as row_ids
                FROM {table_name}
                WHERE "{col_name}" IS NOT NULL
                GROUP BY "{col_name}"
                HAVING COUNT(*) > 1
            """).fetchall()
            
            if dups:
                total_dup_rows = sum(d[1] for d in dups)
                sample_values = [str(d[0]) for d in dups[:5]]
                
                issues.append(QualityIssue(
                    issue_type=IssueType.UNIQUE,
                    severity=IssueSeverity.BLOCKING,  # 主键重复必须修复
                    column=col_name,
                    row_indices=[],
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
        """分布检测 - 提示项：数值列经 IQR(3×) 判定统计异常值（离群点）"""
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
            except Exception:
                continue
            xs = [r[1] for r in res if r[1] is not None]
            if len(xs) < 10:
                continue  # 样本不足不判定
            try:
                q1 = self.db.conn.execute(
                    f'SELECT quantile_cont(CAST("{col_name}" AS DOUBLE), 0.25) FROM {table_name} WHERE "{col_name}" IS NOT NULL'
                ).fetchone()[0]
                q3 = self.db.conn.execute(
                    f'SELECT quantile_cont(CAST("{col_name}" AS DOUBLE), 0.75) FROM {table_name} WHERE "{col_name}" IS NOT NULL'
                ).fetchone()[0]
            except Exception:
                continue
            iqr = (q3 - q1) or 0.0
            if iqr == 0.0:
                continue  # 无离散度不判定
            low, high = q1 - 3 * iqr, q3 + 3 * iqr
            outliers = [r[0] for r in res if r[1] is not None and (r[1] < low or r[1] > high)]
            if outliers:
                sample_vals = [r[1] for r in res if r[0] in outliers[:5]]
                issues.append(QualityIssue(
                    issue_type=IssueType.DISTRIBUTION,
                    severity=IssueSeverity.WARNING,
                    column=col_name,
                    row_indices=outliers[:10],
                    message=f"数值列 {col_name} 检出 {len(outliers)} 个统计离群值（IQR×3，区间[{low:.2f},{high:.2f}]）",
                    sample_values=sample_vals,
                    rule_name="分布离群检测",
                    repair_options=self._get_repair_options(IssueType.DISTRIBUTION, col_name)
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

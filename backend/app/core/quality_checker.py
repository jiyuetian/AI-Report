"""六类质检引擎 - M1-08a 空值与格式（必拦）"""
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class IssueSeverity(Enum):
    """问题严重级别"""
    BLOCKING = "blocking"      # 必拦
    WARNING = "warning"        # 提示


class IssueType(Enum):
    """六类质检类型"""
    NULL = "null"              # 空值
    FORMAT = "format"          # 格式
    UNIQUE = "unique"          # 唯一
    RANGE = "range"            # 范围
    LOGIC = "logic"            # 逻辑
    CODE = "code"              # 码值


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
    
    # 检测顺序（唯一→空值→范围→逻辑→码值→格式）
    DETECTION_ORDER = [
        IssueType.UNIQUE,
        IssueType.NULL,
        IssueType.RANGE,
        IssueType.LOGIC,
        IssueType.CODE,
        IssueType.FORMAT
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
            elif issue_type == IssueType.UNIQUE:
                issues.extend(self._check_unique(table_name, columns))
            elif issue_type == IssueType.RANGE:
                issues.extend(self._check_range(table_name, columns))
            elif issue_type == IssueType.LOGIC:
                issues.extend(self._check_logic(table_name, columns))
            elif issue_type == IssueType.CODE:
                issues.extend(self._check_code(table_name, columns))
        
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
                {"strategy": "fill_mode", "label": "用众数填充", "description": "使用该字段出现最多的值填充"},
                {"strategy": "fill_constant", "label": "指定值填充", "description": "输入自定义值填充空值"},
                {"strategy": "drop", "label": "删除空值行", "description": "删除包含空值的行"},
            ],
            IssueType.FORMAT: [
                {"strategy": "convert_standard", "label": "统一转换为标准格式", "description": "自动转换为标准格式（如日期YYYY-MM-DD）"},
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

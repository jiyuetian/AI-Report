"""数据修复执行器 - M1-09"""
import pandas as pd
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json


@dataclass
class CleanRule:
    """清洗规则记录"""
    rule_id: str
    dataset_id: str
    issue_type: str
    column: str
    strategy: str  # 修复策略
    params: Dict[str, Any]  # 策略参数
    affected_rows: int
    created_at: str
    is_active: bool = True


class DataCleaner:
    """数据修复执行器"""
    
    # 支持的修复策略（扩展至 20+ 类）
    STRATEGIES = {
        # ── 缺失值处理 ──────────────────────────────────────────────
        "deduplicate": "去重 - 删除重复行",
        "fill_median": "分组中位填充 - 按分组填充中位数",
        "fill_mean": "分组均值填充 - 按分组填充平均值",
        "fill_mode": "分组众数填充 - 按分组填充最常见值",
        "fill_forward": "前向填充 - 用前一行值填充",
        "fill_backward": "后向填充 - 用后一行值填充",
        "fill_by_group": "按分组填充 - 用组内统计值填充",
        "delete": "剔除 - 删除问题行",
        # ── 异常值处理 ──────────────────────────────────────────────
        "mark": "标记 - 标记但不删除",
        "truncate": "截断 - 删除超出范围的值",
        "winsorize": "缩尾处理 - 将极端值截断到百分位",
        "iqr_outlier": "IQR异常值 - 用四分位范围检测并替换",
        # ── 格式与一致性 ──────────────────────────────────────────────
        "convert_format": "格式转换 - 统一日期/数字格式",
        "enum_normalize": "枚举归一 - 统一大小写/别名（如wx→微信）",
        "unit_unify": "单位统一 - 统一金额/长度单位（如万元→元）",
        "date_normalize": "日期归一 - 统一日期格式",
        # ── 逻辑校验 ──────────────────────────────────────────────
        "logic_date_reverse": "日期倒挂 - 修正开始日期>结束日期",
        "logic_amount_check": "金额校验 - 金额=数量×单价",
        "logic_repayment": "回款校验 - 回款≤应收",
        # ── 合规脱敏 ──────────────────────────────────────────────
        "phone_mask": "手机号脱敏 - 中间4位替换为****",
        "id_card_mask": "身份证脱敏 - 保留前3后4位",
        "bank_card_mask": "银行卡脱敏 - 保留后4位",
    }
    
    def __init__(self, db_manager):
        """
        初始化修复执行器
        
        Args:
            db_manager: DuckDBManager实例
        """
        self.db = db_manager
        self.clean_rules: List[CleanRule] = []
    
    def execute_fix(self, table_name: str, issue_type: str, column: str,
                   strategy: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        执行修复
        
        Args:
            table_name: 表名
            issue_type: 问题类型
            column: 列名
            strategy: 修复策略
            params: 策略参数
            
        Returns:
            {
                "rule_id": "xxx",
                "strategy": "deduplicate",
                "affected_rows": 10,
                "status": "success",
                "sql": "..."
            }
        """
        params = params or {}
        
        # 生成规则ID
        import uuid
        rule_id = str(uuid.uuid4())[:8]
        
        # 根据策略执行修复
        if strategy == "deduplicate":
            result = self._fix_deduplicate(table_name, column)
        elif strategy == "fill_median":
            group_by = params.get("group_by")
            result = self._fix_fill_median(table_name, column, group_by)
        elif strategy == "fill_mean":
            group_by = params.get("group_by")
            result = self._fix_fill_mean(table_name, column, group_by)
        elif strategy == "fill_mode":
            group_by = params.get("group_by")
            result = self._fix_fill_mode(table_name, column, group_by)
        elif strategy == "fill_forward":
            result = self._fix_fill_forward(table_name, column)
        elif strategy == "fill_backward":
            result = self._fix_fill_backward(table_name, column)
        elif strategy == "fill_by_group":
            group_by = params.get("group_by")
            result = self._fix_fill_by_group(table_name, column, group_by)
        elif strategy == "convert_format":
            target_format = params.get("target_format", "standard")
            result = self._fix_convert_format(table_name, column, target_format)
        elif strategy == "enum_normalize":
            alias_map = params.get("alias_map", {})
            result = self._fix_enum_normalize(table_name, column, alias_map)
        elif strategy == "unit_unify":
            target_unit = params.get("target_unit", "")
            result = self._fix_unit_unify(table_name, column, target_unit)
        elif strategy == "delete":
            condition = params.get("condition")
            result = self._fix_delete(table_name, column, condition)
        elif strategy == "mark":
            result = self._fix_mark(table_name, column, issue_type)
        elif strategy == "truncate":
            threshold = params.get("threshold")
            result = self._fix_truncate(table_name, column, threshold)
        elif strategy == "winsorize":
            low = params.get("low", 0.01)
            high = params.get("high", 0.99)
            result = self._fix_winsorize(table_name, column, low, high)
        elif strategy == "iqr_outlier":
            k = params.get("k", 1.5)
            result = self._fix_iqr_outlier(table_name, column, k)
        elif strategy == "date_normalize":
            target_fmt = params.get("target_format", "%Y-%m-%d")
            result = self._fix_date_normalize(table_name, column, target_fmt)
        elif strategy == "phone_mask":
            result = self._fix_phone_mask(table_name, column)
        elif strategy == "id_card_mask":
            result = self._fix_id_card_mask(table_name, column)
        elif strategy == "bank_card_mask":
            result = self._fix_bank_card_mask(table_name, column)
        else:
            raise ValueError(f"不支持的修复策略: {strategy}")
        
        # 记录规则
        rule = CleanRule(
            rule_id=rule_id,
            dataset_id=table_name.replace("ds_", ""),
            issue_type=issue_type,
            column=column,
            strategy=strategy,
            params=params,
            affected_rows=result["affected_rows"],
            created_at=datetime.now().isoformat()
        )
        self.clean_rules.append(rule)
        
        return {
            "rule_id": rule_id,
            **result
        }
    
    def _fix_deduplicate(self, table_name: str, column: str) -> Dict[str, Any]:
        """
        去重修复
        
        策略：保留首次出现，删除重复行
        """
        # 查找重复行
        dup_count = self.db.conn.execute(f"""
            SELECT COUNT(*) - COUNT(DISTINCT "{column}")
            FROM {table_name}
        """).fetchone()[0]
        
        if dup_count == 0:
            return {"affected_rows": 0, "status": "no_duplicates", "sql": None}
        
        # 创建去重后的临时表
        temp_table = f"{table_name}_dedup"
        self.db.conn.execute(f"""
            CREATE TABLE {temp_table} AS
            SELECT DISTINCT ON ("{column}") *
            FROM {table_name}
            ORDER BY "{column}", rowid
        """)
        
        # 删除原表，重命名临时表
        self.db.conn.execute(f"DROP TABLE {table_name}")
        self.db.conn.execute(f"ALTER TABLE {temp_table} RENAME TO {table_name}")
        
        return {
            "affected_rows": dup_count,
            "status": "success",
            "sql": f"CREATE TABLE {temp_table} AS SELECT DISTINCT ON ({column}) * FROM {table_name}"
        }
    
    def _fix_fill_median(self, table_name: str, column: str, group_by: Optional[str]) -> Dict[str, Any]:
        """
        分组中位填充
        
        策略：按分组计算中位数，填充空值
        """
        if group_by:
            # 按分组填充
            sql = f"""
                UPDATE {table_name}
                SET "{column}" = (
                    SELECT median("{column}") 
                    FROM {table_name} AS t2 
                    WHERE t2."{group_by}" = {table_name}."{group_by}"
                )
                WHERE "{column}" IS NULL
            """
        else:
            # 全局填充
            sql = f"""
                UPDATE {table_name}
                SET "{column}" = (SELECT median("{column}") FROM {table_name})
                WHERE "{column}" IS NULL
            """
        
        # 执行更新
        self.db.conn.execute(sql)
        
        # 获取影响行数（DuckDB不支持直接获取，需要额外查询）
        # 简化：返回估计值
        return {
            "affected_rows": -1,  # 表示未知
            "status": "success",
            "sql": sql,
            "note": "估算值填充完成"
        }
    
    def _fix_convert_format(self, table_name: str, column: str, target_format: str) -> Dict[str, Any]:
        """
        格式转换
        
        策略：统一日期格式为标准格式
        """
        # 支持的日期格式转换
        conversions = {
            "standard": {
                "2024/01/01": "2024-01-01",
                "20240101": "2024-01-01",
                "2024年01月01日": "2024-01-01"
            }
        }
        
        # 使用CASE WHEN进行转换
        sql = f"""
            UPDATE {table_name}
            SET "{column}" = CASE
                WHEN "{column}" LIKE '%/%' THEN replace("{column}", '/', '-')
                WHEN "{column}" LIKE '%年%' THEN regexp_replace("{column}", '年|月', '-')
                ELSE "{column}"
            END
            WHERE "{column}" IS NOT NULL
        """
        
        self.db.conn.execute(sql)
        
        return {
            "affected_rows": -1,
            "status": "success",
            "sql": sql,
            "target_format": target_format
        }
    
    def _fix_delete(self, table_name: str, column: str, condition: Optional[str]) -> Dict[str, Any]:
        """
        剔除修复
        
        策略：删除问题行
        """
        if condition:
            sql = f"DELETE FROM {table_name} WHERE {condition}"
        else:
            sql = f"DELETE FROM {table_name} WHERE \"{column}\" IS NULL"
        
        self.db.conn.execute(sql)
        
        return {
            "affected_rows": -1,
            "status": "success",
            "sql": sql
        }
    
    def _fix_mark(self, table_name: str, column: str, issue_type: str) -> Dict[str, Any]:
        """
        标记修复
        
        策略：添加标记列，不删除数据
        """
        mark_column = f"_qc_mark_{issue_type}"
        
        # 添加标记列
        try:
            self.db.conn.execute(f"""
                ALTER TABLE {table_name} ADD COLUMN "{mark_column}" VARCHAR
            """)
        except:
            pass  # 列已存在
        
        # 标记问题行
        sql = f"""
            UPDATE {table_name}
            SET "{mark_column}" = '{issue_type}'
            WHERE "{column}" IS NULL
        """
        
        self.db.conn.execute(sql)
        
        return {
            "affected_rows": -1,
            "status": "success",
            "sql": sql,
            "mark_column": mark_column
        }
    
    def _fix_truncate(self, table_name: str, column: str, threshold: float) -> Dict[str, Any]:
        """截断修复"""
        sql = f"""
            UPDATE {table_name}
            SET "{column}" = {threshold}
            WHERE CAST("{column}" AS DOUBLE) > {threshold}
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql, "threshold": threshold}

    # ── 新增策略实现 ──────────────────────────────────────────────────

    def _fix_fill_mean(self, table_name: str, column: str, group_by: Optional[str]) -> Dict:
        sql = f"""
            UPDATE {table_name} SET "{column}" = (
                SELECT AVG("{column}") FROM {table_name}
                {f'WHERE "{group_by}" = {table_name}."{group_by}"' if group_by else ''}
            ) WHERE "{column}" IS NULL
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql}

    def _fix_fill_mode(self, table_name: str, column: str, group_by: Optional[str]) -> Dict:
        grp = f'"{group_by}" = {table_name}."{group_by}"' if group_by else "1=1"
        sql = f"""
            UPDATE {table_name} SET "{column}" = (
                SELECT "{column}" FROM {table_name} WHERE {grp}
                GROUP BY "{column}" ORDER BY COUNT(*) DESC LIMIT 1
            ) WHERE "{column}" IS NULL
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql}

    def _fix_fill_forward(self, table_name: str, column: str) -> Dict:
        sql = f"""
            WITH ordered AS (
                SELECT *, ROW_NUMBER() OVER (ORDER BY rowid) AS rn
                FROM {table_name}
            )
            UPDATE {table_name} SET "{column}" = (
                SELECT o2."{column}" FROM ordered o2
                WHERE o2.rn = (SELECT MAX(rn) FROM ordered o3 WHERE o3.rn < ordered.rn AND o3."{column}" IS NOT NULL)
                LIMIT 1
            ) WHERE "{column}" IS NULL
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql}

    def _fix_fill_backward(self, table_name: str, column: str) -> Dict:
        sql = f"""
            WITH ordered AS (
                SELECT *, ROW_NUMBER() OVER (ORDER BY rowid) AS rn
                FROM {table_name}
            )
            UPDATE {table_name} SET "{column}" = (
                SELECT o2."{column}" FROM ordered o2
                WHERE o2.rn = (SELECT MIN(rn) FROM ordered o3 WHERE o3.rn > ordered.rn AND o3."{column}" IS NOT NULL)
                LIMIT 1
            ) WHERE "{column}" IS NULL
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql}

    def _fix_fill_by_group(self, table_name: str, column: str, group_by: str) -> Dict:
        sql = f"""
            UPDATE {table_name} SET "{column}" = (
                SELECT AVG(t2."{column}") FROM {table_name} t2
                WHERE t2."{group_by}" = {table_name}."{group_by}"
            ) WHERE "{column}" IS NULL
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql}

    def _fix_enum_normalize(self, table_name: str, column: str, alias_map: Dict) -> Dict:
        if not alias_map:
            return {"affected_rows": 0, "status": "no_aliases", "sql": None}
        sets = " OR ".join(f'"{column}" = ?' for _ in alias_map)
        params = list(alias_map.keys())
        self.db.conn.execute(f'UPDATE {table_name} SET "{column}" = ? WHERE {sets}', params + list(alias_map.values()))
        return {"affected_rows": -1, "status": "success", "sql": f"UPDATE {table_name} SET {column}=... WHERE ..."}

    def _fix_unit_unify(self, table_name: str, column: str, target_unit: str) -> Dict:
        factor = {"元": 1, "万元": 10000, "千元": 1000}.get(target_unit, 1)
        sql = f"""
            UPDATE {table_name} SET "{column}" = CAST("{column}" AS DOUBLE) * {factor}
            WHERE "{column}" IS NOT NULL
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql, "target_unit": target_unit}

    def _fix_date_normalize(self, table_name: str, column: str, target_fmt: str) -> Dict:
        sql = f"""
            UPDATE {table_name} SET "{column}" = strftime('%Y-%m-%d', "{column}")
            WHERE "{column}" IS NOT NULL AND "{column}" NOT LIKE '____-__-__'
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql, "target_fmt": target_fmt}

    def _fix_winsorize(self, table_name: str, column: str, low: float, high: float) -> Dict:
        sql = f"""
            UPDATE {table_name} SET "{column}" = MAX(MIN("{column}",
                (SELECT "{column}" FROM {table_name} ORDER BY "{column}" LIMIT 1 OFFSET CAST(({high - low} * (SELECT COUNT(*) FROM {table_name})) AS INT)),
                (SELECT "{column}" FROM {table_name} ORDER BY "{column}" DESC LIMIT 1 OFFSET CAST(({low} * (SELECT COUNT(*) FROM {table_name})) AS INT))
            ))
            WHERE "{column}" IS NOT NULL
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql, "low": low, "high": high}

    def _fix_iqr_outlier(self, table_name: str, column: str, k: float = 1.5) -> Dict:
        sql = f"""
            WITH stats AS (
                SELECT QUANTILE_CONT("{column}", 0.25) AS q1, QUANTILE_CONT("{column}", 0.75) AS q3
                FROM {table_name}
            )
            UPDATE {table_name} SET "{column}" = (
                SELECT CASE
                    WHEN "{column}" < s.q1 - {k} * (s.q3 - s.q1) THEN s.q1 - {k} * (s.q3 - s.q1)
                    WHEN "{column}" > s.q3 + {k} * (s.q3 - s.q1) THEN s.q3 + {k} * (s.q3 - s.q1)
                    ELSE "{column}"
                END FROM stats s
            ) WHERE "{column}" IS NOT NULL
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql, "k": k}

    def _fix_phone_mask(self, table_name: str, column: str) -> Dict:
        sql = f"""
            UPDATE {table_name} SET "{column}" = substr("{column}", 1, 3) || '****' || substr("{column}", -4)
            WHERE "{column}" IS NOT NULL AND length(replace("{column}", '-', '')) = 11
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql}

    def _fix_id_card_mask(self, table_name: str, column: str) -> Dict:
        sql = f"""
            UPDATE {table_name} SET "{column}" = substr("{column}", 1, 3) || '**********' || substr("{column}", -4)
            WHERE "{column}" IS NOT NULL AND length(replace("{column}", 'X', 'x')) = 18
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql}

    def _fix_bank_card_mask(self, table_name: str, column: str) -> Dict:
        sql = f"""
            UPDATE {table_name} SET "{column}" = '**** **** **** ' || substr("{column}", -4)
            WHERE "{column}" IS NOT NULL AND length(replace("{column}", ' ', '')) >= 13
        """
        self.db.conn.execute(sql)
        return {"affected_rows": -1, "status": "success", "sql": sql}
    
    def rollback(self, table_name: str, rule_id: str) -> Dict[str, Any]:
        """
        撤销修复
        
        M1-09: 一键撤销
        """
        # 查找规则
        rule = next((r for r in self.clean_rules if r.rule_id == rule_id), None)
        
        if not rule:
            return {"status": "error", "message": "规则不存在"}
        
        # 标记规则为失效
        rule.is_active = False
        
        # TODO: 实现真正的回滚（需要保存原始数据快照）
        # 简化版：提示用户重新导入数据
        
        return {
            "status": "rolled_back",
            "rule_id": rule_id,
            "message": "规则已撤销，建议重新导入原始数据"
        }
    
    def get_rules(self, dataset_id: Optional[str] = None) -> List[Dict]:
        """获取清洗规则列表"""
        rules = self.clean_rules
        
        if dataset_id:
            rules = [r for r in rules if r.dataset_id == dataset_id]
        
        return [asdict(r) for r in rules]
    
    def export_rules(self, dataset_id: str) -> str:
        """导出清洗规则为JSON"""
        rules = self.get_rules(dataset_id)
        return json.dumps(rules, indent=2, ensure_ascii=False)

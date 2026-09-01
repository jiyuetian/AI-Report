"""DuckDB 管理器 - M1-07c 大数据优化版"""
import duckdb
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, Any, List
import json

from app.core.config import settings

# DuckDB内存配置
DUCKDB_MEMORY_LIMIT = getattr(settings, 'DUCKDB_MEMORY_LIMIT', '4GB')
DUCKDB_MAX_ROWS_PROFILE = 100000  # profile计算的最大行数


class DuckDBManager:
    """DuckDB 数据库管理器 - 大数据优化"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化DuckDB连接
        
        Args:
            db_path: DuckDB文件路径，None则使用内存模式
        """
        self.db_path = db_path or settings.DUCKDB_PATH or ":memory:"
        self.conn = None
        self._connect()
    
    def _connect(self):
        """建立连接并配置内存限制"""
        self.conn = duckdb.connect(self.db_path)
        
        # M1-07c: 配置内存上限
        self.conn.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT}'")
        
        # 启用并行处理
        import multiprocessing
        threads = min(multiprocessing.cpu_count(), 8)
        self.conn.execute(f"SET threads = {threads}")
        
        # 配置临时目录（用于大数据溢出）
        temp_dir = Path(self.db_path).parent / "temp"
        temp_dir.mkdir(exist_ok=True)
        self.conn.execute(f"SET temp_directory = '{temp_dir}'")
    
    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def create_dataset_table(self, dataset_id: str, df: pd.DataFrame) -> str:
        """
        创建数据集表 ds_{dataset_id}
        
        M1-07c优化：
        - 大数据时分批插入
        - 列数>500时Top20收敛
        """
        table_name = f"ds_{dataset_id.replace('-', '_')}"
        
        # 检查列数
        if len(df.columns) > 500:
            # Top20收敛：只保留前20列+关键列
            df = self._converge_columns(df)
        
        # 大数据分批处理
        total_rows = len(df)
        if total_rows > 100000:
            # 分批创建表
            self._create_table_batch(table_name, df)
        else:
            # 小数据直接创建
            self.conn.register("temp_df", df)
            self.conn.execute(f"""
                CREATE OR REPLACE TABLE {table_name} AS 
                SELECT * FROM temp_df
            """)
            self.conn.unregister("temp_df")
        
        return table_name
    
    def _converge_columns(self, df: pd.DataFrame, max_cols: int = 20) -> pd.DataFrame:
        """
        M1-07c: 列数>500时Top20收敛
        
        策略：保留前20列 + 名称中包含关键字的列
        """
        priority_keywords = ['id', 'no', '编号', 'date', '日期', 'amt', 'amount', '金额', 
                          'type', '类型', 'cust', '客户', 'name', '名称']
        
        # 识别关键列
        key_cols = []
        for i, col in enumerate(df.columns):
            if any(kw in str(col).lower() for kw in priority_keywords):
                key_cols.append(col)
            if len(key_cols) >= max_cols:
                break
        
        # 如果没有识别到足够的关键列，取前max_cols列
        if len(key_cols) < max_cols:
            remaining = [c for c in df.columns if c not in key_cols]
            key_cols.extend(remaining[:max_cols - len(key_cols)])
        
        return df[key_cols[:max_cols]]
    
    def _create_table_batch(self, table_name: str, df: pd.DataFrame, batch_size: int = 50000):
        """分批创建大表"""
        total_rows = len(df)
        
        # 第一批：创建表
        first_batch = df.iloc[:batch_size]
        self.conn.register("batch_df", first_batch)
        self.conn.execute(f"""
            CREATE OR REPLACE TABLE {table_name} AS 
            SELECT * FROM batch_df
        """)
        self.conn.unregister("batch_df")
        
        # 后续批次：插入
        for start in range(batch_size, total_rows, batch_size):
            end = min(start + batch_size, total_rows)
            batch = df.iloc[start:end]
            self.conn.register("batch_df", batch)
            self.conn.execute(f"INSERT INTO {table_name} SELECT * FROM batch_df")
            self.conn.unregister("batch_df")
    
    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """获取表信息"""
        # 表结构
        columns = self.conn.execute(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
        """).fetchall()
        
        # 行数
        row_count = self.conn.execute(f"""
            SELECT COUNT(*) FROM {table_name}
        """).fetchone()[0]
        
        return {
            "table_name": table_name,
            "columns": [{"name": c[0], "type": c[1]} for c in columns],
            "row_count": row_count
        }
    
    def list_tables(self) -> List[str]:
        """列出所有表"""
        result = self.conn.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'main'
        """).fetchall()
        return [r[0] for r in result]
    
    def execute_query(self, query: str) -> pd.DataFrame:
        """执行SQL查询"""
        return self.conn.execute(query).fetchdf()
    
    def get_profile(self, table_name: str, column_name: str) -> Dict[str, Any]:
        """
        M1-07c优化：大数据时分层抽样计算profile
        """
        # 总行数
        total_rows = self.conn.execute(f"""
            SELECT COUNT(*) FROM {table_name}
        """).fetchone()[0]
        
        # M1-07c: 大数据时使用近似计算
        use_approx = total_rows > DUCKDB_MAX_ROWS_PROFILE
        
        if use_approx:
            # 近似计算：使用RESERVOIR抽样
            null_count = self.conn.execute(f"""
                SELECT COUNT(*) FROM (
                    SELECT {column_name} 
                    FROM {table_name} 
                    USING SAMPLE RESERVOIR ({DUCKDB_MAX_ROWS_PROFILE})
                ) 
                WHERE {column_name} IS NULL
            """).fetchone()[0]
            
            # 对抽样数据计算基数
            sample_table = f"(SELECT {column_name} FROM {table_name} USING SAMPLE RESERVOIR ({DUCKDB_MAX_ROWS_PROFILE}))"
            cardinality = self.conn.execute(f"""
                SELECT COUNT(DISTINCT {column_name}) FROM {sample_table}
            """).fetchone()[0]
            
            # 估算真实基数（简单线性放大）
            estimated_cardinality = int(cardinality * (total_rows / min(total_rows, DUCKDB_MAX_ROWS_PROFILE)))
        else:
            # 精确计算
            null_count = self.conn.execute(f"""
                SELECT COUNT(*) FROM {table_name} 
                WHERE {column_name} IS NULL
            """).fetchone()[0]
            cardinality = self.conn.execute(f"""
                SELECT COUNT(DISTINCT {column_name}) FROM {table_name}
            """).fetchone()[0]
            estimated_cardinality = cardinality
        
        # 缺失率
        null_rate = null_count / total_rows if total_rows > 0 else 0
        
        # 类型推断（抽样）
        sample_values = self.conn.execute(f"""
            SELECT {column_name} 
            FROM {table_name} 
            WHERE {column_name} IS NOT NULL 
            LIMIT 5
        """).fetchall()
        
        inferred_type = self._infer_column_type([v[0] for v in sample_values])
        
        return {
            "column": column_name,
            "total_rows": total_rows,
            "null_count": null_count,
            "null_rate": round(null_rate, 4),
            "cardinality": estimated_cardinality,
            "cardinality_ratio": round(estimated_cardinality / total_rows, 4) if total_rows > 0 else 0,
            "inferred_type": inferred_type,
            "sample_values": [v[0] for v in sample_values],
            "calculation_mode": "approximate" if use_approx else "exact"
        }
    
    def _infer_column_type(self, samples: List[Any]) -> str:
        """推断字段类型（8类字段）"""
        if not samples:
            return "unknown"
        
        # 检查是否为日期
        date_keywords = ['date', 'time', '日期', '时间', 'dt', 'rq']
        if any(str(s).lower() in date_keywords for s in samples if s):
            return "datetime"
        
        # 检查是否为ID列
        id_keywords = ['id', 'no', '编号', '编码', 'bh', 'bm']
        if any(kw in str(samples[0]).lower() for kw in id_keywords):
            return "id"
        
        # 检查是否为数值
        numeric_count = 0
        for s in samples:
            try:
                float(str(s).replace(',', ''))
                numeric_count += 1
            except:
                pass
        
        if numeric_count == len([s for s in samples if s is not None]):
            int_count = 0
            for s in samples:
                try:
                    if float(str(s).replace(',', '')) == int(float(str(s).replace(',', ''))):
                        int_count += 1
                except:
                    pass
            return "integer" if int_count == len([s for s in samples if s is not None]) else "float"
        
        # 检查是否为布尔
        bool_values = {'true', 'false', '0', '1', 'yes', 'no', '是', '否', 'y', 'n'}
        if all(str(s).lower() in bool_values for s in samples if s):
            return "boolean"
        
        # 检查是否为分类
        unique_samples = set(str(s) for s in samples if s)
        if len(unique_samples) <= 5:
            return "categorical"
        
        # 检查是否为文本
        avg_len = sum(len(str(s)) for s in samples if s) / max(len(samples), 1)
        if avg_len > 50:
            return "text"
        
        return "string"
    
    def detect_grain(self, table_name: str, columns: List[Dict]) -> Dict[str, Any]:
        """识别数据粒度"""
        col_names = [c['name'].lower() for c in columns]
        
        id_indicators = ['id', 'no', '编号', '借据号', '合同号', 'htbh', 'jjh']
        has_id_column = any(any(ind in col for ind in id_indicators) for col in col_names)
        
        date_indicators = ['date', 'dt', '日期', '月份', 'month', '年月', 'yearmonth']
        has_date_column = any(any(ind in col for ind in date_indicators) for col in col_names)
        
        cust_indicators = ['cust', '客户', 'kh', '客户号', 'cust_id']
        has_cust_column = any(any(ind in col for ind in cust_indicators) for col in col_names)
        
        type_indicators = ['type', '类型', '担保', 'db', 'lx', '类别']
        has_type_column = any(any(ind in col for ind in type_indicators) for col in col_names)
        
        total_rows = self.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        
        grain_type = "unknown"
        grain_desc = "未知粒度"
        
        if has_id_column and not has_date_column:
            id_col = next((c['name'] for c in columns if any(ind in c['name'].lower() for ind in id_indicators)), None)
            if id_col:
                unique_ids = self.conn.execute(f"SELECT COUNT(DISTINCT \"{id_col}\") FROM {table_name}").fetchone()[0]
                if unique_ids == total_rows:
                    grain_type = "single_record"
                    grain_desc = "单笔借据"
        
        if grain_type == "unknown" and has_date_column and has_type_column:
            grain_type = "monthly_type"
            grain_desc = "月份×担保类型(宏观)"
        
        if grain_type == "unknown" and has_date_column:
            grain_type = "monthly_summary"
            grain_desc = "月份汇总"
        
        if grain_type == "unknown" and has_cust_column and not has_id_column:
            grain_type = "customer_level"
            grain_desc = "客户级"
        
        return {
            "grain_type": grain_type,
            "grain_desc": grain_desc,
            "total_rows": total_rows,
            "indicators": {
                "has_id_column": has_id_column,
                "has_date_column": has_date_column,
                "has_cust_column": has_cust_column,
                "has_type_column": has_type_column
            }
        }
    
    def pre_aggregate(self, table_name: str, group_columns: List[str], 
                     agg_columns: List[str], agg_funcs: List[str]) -> str:
        """
        M1-07c: 预聚合缓存
        
        创建聚合表用于大数据加速
        """
        agg_table = f"{table_name}_agg"
        
        # 构建聚合SQL
        select_parts = group_columns.copy()
        for col, func in zip(agg_columns, agg_funcs):
            select_parts.append(f"{func}({col}) AS {col}_{func.lower()}")
        
        sql = f"""
            CREATE OR REPLACE TABLE {agg_table} AS
            SELECT {', '.join(select_parts)}
            FROM {table_name}
            GROUP BY {', '.join(group_columns)}
        """
        
        self.conn.execute(sql)
        return agg_table
    
    def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        result = self.conn.execute(f"""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = 'main' AND table_name = '{table_name}'
        """).fetchone()
        return result[0] > 0
    
    def get_layer_table_name(self, dataset_id: str, layer: str) -> str:
        """
        获取分层表名（完整六层架构）
        
        分层：
        0. raw - 原始数据层（原始解析）
        1. norm - 字段标准化层（类型转换）
        2. cleaned - 数据清洗层（质量修复：去重/空值填充/格式转换）
        3. processed - 业务加工层（衍生字段/过滤）
        4. agg - 聚合计算层（按维度预聚合，可多个子表）
        5. output - 看板输出层（最终生成看板）
        """
        base = f"ds_{dataset_id.replace('-', '_')}"
        layer_map = {
            'raw': base,
            'norm': f"{base}_norm",
            'cleaned': f"{base}_cleaned",
            'processed': f"{base}_processed",
            'agg': f"{base}_agg",
            'output': f"{base}_output",
        }
        return layer_map.get(layer, base)
    
    def create_cleaned_from_original(self, dataset_id: str) -> str:
        """
        创建清洗层从原始层复制数据
        
        如果清洗层已存在，直接返回
        如果不存在，从原始层全量复制
        """
        cleaned_table = self.get_layer_table_name(dataset_id, 'cleaned')
        if self.table_exists(cleaned_table):
            return cleaned_table
        
        raw_table = self.get_layer_table_name(dataset_id, 'raw')
        if not self.table_exists(raw_table):
            raise ValueError(f"原始层表 {raw_table} 不存在")
        
        self.conn.execute(f"""
            CREATE TABLE {cleaned_table} AS 
            SELECT * FROM {raw_table}
        """)
        return cleaned_table
    
    def create_norm_from_raw(self, dataset_id: str) -> str:
        """创建标准化层从原始层复制（后续做类型转换）"""
        norm_table = self.get_layer_table_name(dataset_id, 'norm')
        if self.table_exists(norm_table):
            return norm_table
        
        raw_table = self.get_layer_table_name(dataset_id, 'raw')
        self.conn.execute(f"""
            CREATE TABLE {norm_table} AS 
            SELECT * FROM {raw_table}
        """)
        return norm_table
    
    def drop_table(self, table_name: str):
        """删除表"""
        self.conn.execute(f"DROP TABLE IF EXISTS {table_name}")


# 全局实例管理
duckdb_manager: Optional[DuckDBManager] = None


def get_duckdb() -> DuckDBManager:
    """获取DuckDB管理器实例（单例）"""
    global duckdb_manager
    if duckdb_manager is None:
        duckdb_manager = DuckDBManager()
    return duckdb_manager


def reset_duckdb():
    """重置DuckDB连接（用于测试）"""
    global duckdb_manager
    if duckdb_manager:
        duckdb_manager.close()
    duckdb_manager = None
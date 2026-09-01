"""文件解析工具 - M1-06 多Sheet与编码 + M1-11 敏感字段"""
import pandas as pd
import chardet
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import openpyxl
import re


class FileParser:
    """文件解析器"""
    
    SUPPORTED_ENCODINGS = ['utf-8', 'gbk', 'gb18030', 'big5']
    
    @staticmethod
    def detect_encoding(file_path: Path, sample_size: int = 100000) -> Tuple[str, float]:
        """
        自动检测CSV文件编码
        
        Returns:
            (encoding, confidence)
        """
        with open(file_path, 'rb') as f:
            raw_data = f.read(sample_size)
        
        result = chardet.detect(raw_data)
        encoding = result.get('encoding', 'utf-8')
        confidence = result.get('confidence', 0.0)
        
        # 标准化编码名称
        if encoding:
            encoding = encoding.lower()
            if encoding == 'gb2312':
                encoding = 'gbk'
        
        return encoding, confidence
    
    @staticmethod
    def read_csv_with_encoding(
        file_path: Path, 
        encoding: Optional[str] = None
    ) -> Tuple[pd.DataFrame, str]:
        """
        读取CSV文件，支持编码自动检测和手动指定
        
        Returns:
            (dataframe, used_encoding)
        """
        if encoding is None:
            encoding, confidence = FileParser.detect_encoding(file_path)
            # 如果置信度太低，可能需要手动选择
            if confidence < 0.7:
                encoding = 'utf-8'  # 默认回退
        
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            return df, encoding
        except UnicodeDecodeError:
            # 尝试其他编码
            for enc in FileParser.SUPPORTED_ENCODINGS:
                if enc != encoding:
                    try:
                        df = pd.read_csv(file_path, encoding=enc)
                        return df, enc
                    except UnicodeDecodeError:
                        continue
            raise ValueError(f"无法识别文件编码，支持的编码: {FileParser.SUPPORTED_ENCODINGS}")
    
    @staticmethod
    def get_excel_sheets(file_path: Path) -> List[Dict[str, Any]]:
        """
        获取Excel文件的所有Sheet信息
        
        Returns:
            [{"name": "Sheet1", "index": 0, "row_count": 100}, ...]
        """
        workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheets = []
        
        for idx, sheet_name in enumerate(workbook.sheetnames):
            sheet = workbook[sheet_name]
            row_count = sheet.max_row
            col_count = sheet.max_column
            
            # 读取第一行作为列名预览
            headers = []
            if row_count > 0:
                for col in range(1, min(col_count + 1, 6)):  # 只读前5列
                    cell_value = sheet.cell(1, col).value
                    headers.append(str(cell_value) if cell_value else f"Column{col}")
            
            sheets.append({
                "index": idx,
                "name": sheet_name,
                "row_count": row_count,
                "col_count": col_count,
                "headers": headers
            })
        
        workbook.close()
        return sheets
    
    @staticmethod
    def read_excel_sheet(
        file_path: Path, 
        sheet_name: Optional[str] = None,
        sheet_index: Optional[int] = None
    ) -> pd.DataFrame:
        """读取指定Sheet"""
        if sheet_name:
            return pd.read_excel(file_path, sheet_name=sheet_name)
        elif sheet_index is not None:
            return pd.read_excel(file_path, sheet_name=sheet_index)
        else:
            return pd.read_excel(file_path)  # 默认第一个sheet
    
    @staticmethod
    def preview_data(
        df: pd.DataFrame, 
        max_rows: int = 5,
        max_cols: int = 20
    ) -> Dict[str, Any]:
        """
        生成数据预览
        
        Returns:
            {
                "columns": ["col1", "col2", ...],
                "rows": [[val1, val2, ...], ...],
                "total_rows": 100,
                "total_cols": 5
            }
        """
        # 限制列数
        if len(df.columns) > max_cols:
            df = df.iloc[:, :max_cols]
        
        preview_rows = df.head(max_rows)
        
        # 将NaN/Inf转换为None以便JSON序列化
        rows = []
        for _, row in preview_rows.iterrows():
            row_values = []
            for val in row.values:
                if pd.isna(val) or pd.isnull(val) or (isinstance(val, float) and (float('inf') == val or -float('inf') == val)):
                    row_values.append(None)
                else:
                    row_values.append(val)
            rows.append(row_values)
        
        return {
            "columns": df.columns.tolist(),
            "rows": rows,
            "total_rows": len(df),
            "total_cols": len(df.columns),
            "preview_rows": min(max_rows, len(df))
        }
    
    # ==================== M1-11: 敏感字段检测与脱敏 ====================
    
    # 敏感字段正则模式
    SENSITIVE_PATTERNS = {
        "idcard": {
            "patterns": [
                r'^\d{15}$',           # 15位身份证
                r'^\d{18}$',           # 18位身份证
                r'^\d{17}[\dXx]$',     # 18位身份证含X
            ],
            "keywords": ['身份证', 'idcard', 'sfz', '身份证号'],
            "mask": lambda x: x[:3] + "***" + x[-4:] if len(x) > 7 else "***"
        },
        "phone": {
            "patterns": [
                r'^1[3-9]\d{9}$',      # 手机号
            ],
            "keywords": ['手机', 'phone', '电话', 'mobile', 'sjh'],
            "mask": lambda x: x[:3] + "****" + x[-4:] if len(x) == 11 else "***"
        },
        "bankcard": {
            "patterns": [
                r'^\d{16,19}$',        # 银行卡号
            ],
            "keywords": ['银行卡', 'bankcard', '卡号', 'card'],
            "mask": lambda x: x[:4] + " **** **** " + x[-4:] if len(x) >= 16 else "***"
        },
        "email": {
            "patterns": [
                r'^[\w\.-]+@[\w\.-]+\.\w+$',  # 邮箱
            ],
            "keywords": ['邮箱', 'email', 'mail'],
            "mask": lambda x: x[:2] + "***@***" + x[x.rfind('.'):] if '@' in x else "***"
        }
    }
    
    @classmethod
    def detect_sensitive_columns(cls, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        检测敏感字段列
        
        Returns:
            [
                {
                    "column": "身份证号",
                    "type": "idcard",
                    "confidence": 0.95,
                    "sample_masked": "110***1234"
                }
            ]
        """
        sensitive_cols = []
        
        for col in df.columns:
            col_str = str(col).lower()
            
            for sens_type, config in cls.SENSITIVE_PATTERNS.items():
                # 检查列名关键词
                name_match = any(kw in col_str for kw in config["keywords"])
                
                # 检查样本值
                sample_values = df[col].dropna().astype(str).head(5).tolist()
                value_matches = 0
                
                for val in sample_values:
                    for pattern in config["patterns"]:
                        if re.match(pattern, val.strip()):
                            value_matches += 1
                            break
                
                # 如果列名匹配或值匹配，判定为敏感字段
                if name_match or value_matches >= 3:
                    # 计算置信度
                    confidence = 1.0 if name_match else (value_matches / len(sample_values) if sample_values else 0)
                    
                    # 脱敏样本
                    masked_samples = [
                        config["mask"](str(v)) for v in sample_values[:3]
                    ]
                    
                    sensitive_cols.append({
                        "column": col,
                        "type": sens_type,
                        "confidence": confidence,
                        "sample_masked": masked_samples
                    })
                    break  # 一个列只归类一种敏感类型
        
        return sensitive_cols
    
    @classmethod
    def mask_sensitive_data(cls, df: pd.DataFrame, sensitive_cols: List[str]) -> pd.DataFrame:
        """
        对敏感字段进行脱敏处理
        
        规则：
        - 默认脱敏存储
        - 看板/导出不出原文
        - 不可关闭（强制脱敏）
        """
        df_masked = df.copy()
        
        for col in sensitive_cols:
            if col not in df_masked.columns:
                continue
            
            col_str = str(col).lower()
            
            # 确定脱敏方式
            mask_func = None
            for sens_type, config in cls.SENSITIVE_PATTERNS.items():
                if any(kw in col_str for kw in config["keywords"]):
                    mask_func = config["mask"]
                    break
            
            if mask_func:
                df_masked[col] = df_masked[col].apply(
                    lambda x: mask_func(str(x)) if pd.notna(x) else x
                )
        
        return df_masked
    
    @classmethod
    def parse_file(
        cls,
        file_path: Path,
        file_ext: str,
        sheet_name: Optional[str] = None,
        encoding: Optional[str] = None,
        disable_masking: bool = False  # M1-11: 强制为False，不可关闭
    ) -> Dict[str, Any]:
        """
        通用文件解析入口（M1-11增强版）
        
        Args:
            disable_masking: 必须保持False，敏感字段永远脱敏
        
        Returns:
            {
                "type": "excel" | "csv",
                "sheets": [...],
                "detected_encoding": "utf-8",
                "preview": {...},
                "dataframe": pd.DataFrame,  # 已脱敏
                "sensitive_columns": [...],  # 敏感字段列表
                "masking_applied": True  # 始终为True
            }
        """
        result = {
            "type": "unknown",
            "file_path": str(file_path),
            "file_ext": file_ext,
            "masking_applied": True  # M1-11: 强制脱敏
        }
        
        if file_ext in ['.xlsx', '.xls']:
            # Excel文件
            result["type"] = "excel"
            result["sheets"] = cls.get_excel_sheets(file_path)
            
            # 如果指定了sheet，读取数据
            if sheet_name:
                df = cls.read_excel_sheet(file_path, sheet_name=sheet_name)
                df = cls._process_sensitive_data(df)  # M1-11脱敏
                result["preview"] = cls.preview_data(df)
                result["dataframe"] = df
            elif len(result["sheets"]) == 1:
                # 只有一个sheet，自动读取
                df = cls.read_excel_sheet(file_path, sheet_index=0)
                df = cls._process_sensitive_data(df)  # M1-11脱敏
                result["preview"] = cls.preview_data(df)
                result["dataframe"] = df
                
        elif file_ext == '.csv':
            # CSV文件
            result["type"] = "csv"
            
            # 检测编码
            detected_encoding, confidence = cls.detect_encoding(file_path)
            result["detected_encoding"] = detected_encoding
            result["encoding_confidence"] = confidence
            
            # 如果置信度低或手动指定了编码，需要选择
            use_encoding = encoding or detected_encoding
            result["needs_encoding_selection"] = (
                encoding is None and confidence < 0.7
            )
            
            # 读取数据
            df, used_encoding = cls.read_csv_with_encoding(file_path, use_encoding)
            df = cls._process_sensitive_data(df)  # M1-11脱敏
            result["used_encoding"] = used_encoding
            result["preview"] = cls.preview_data(df)
            result["dataframe"] = df
        
        return result
    
    @classmethod
    def _process_sensitive_data(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        处理敏感字段（M1-11）
        
        1. 检测敏感字段
        2. 脱敏处理
        3. 记录敏感字段信息
        """
        # 检测敏感字段
        sensitive_cols_info = cls.detect_sensitive_columns(df)
        
        if sensitive_cols_info:
            # 提取需要脱敏的列名
            sensitive_col_names = [s["column"] for s in sensitive_cols_info]
            
            # 脱敏处理
            df = cls.mask_sensitive_data(df, sensitive_col_names)
        
        return df
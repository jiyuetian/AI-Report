"""数据集API - M1-07a DuckDB入库"""
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path

from app.core.config import settings
from app.core.file_parser import FileParser
from app.core.duckdb_manager import get_duckdb
from app.core.database import get_db
from app.models.dataset import Dataset
from app.models.file import File as FileModel
import pandas as pd

router = APIRouter(prefix="/datasets", tags=["Datasets"])

UPLOAD_DIR = Path(settings.UPLOAD_DIR)


class DatasetCreateRequest(BaseModel):
    file_id: str
    name: str
    sheet_name: Optional[str] = None
    encoding: Optional[str] = None


@router.post("", response_model=dict)
async def create_dataset(request: DatasetCreateRequest, db: AsyncSession = Depends(get_db)):
    """
    创建数据集（文件入库DuckDB）
    
    流程：
    1. 根据file_id找到上传的文件
    2. 解析文件（Excel/CSV）
    3. 创建DuckDB表 ds_{dataset_id}
    4. 返回dataset信息
    """
    file_id = request.file_id
    
    # 查找文件
    file_path = None
    file_ext = None
    
    for ext in ['.xlsx', '.xls', '.csv']:
        path = UPLOAD_DIR / f"{file_id}{ext}"
        if path.exists():
            file_path = path
            file_ext = ext
            break
    
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "FILE_NOT_FOUND", "message": "文件不存在"}
        )
    
    try:
        # 解析文件
        parse_result = FileParser.parse_file(
            file_path,
            file_ext,
            sheet_name=request.sheet_name,
            encoding=request.encoding
        )
        
        if "dataframe" not in parse_result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "PARSE_ERROR", "message": "无法解析文件数据"}
            )
        
        df = parse_result["dataframe"]
        
        # 生成dataset_id
        import uuid
        dataset_id = str(uuid.uuid4())
        
        # 入库DuckDB
        duckdb = get_duckdb()
        table_name = duckdb.create_dataset_table(dataset_id, df)
        
        # 获取表信息
        table_info = duckdb.get_table_info(table_name)
        
        # 保存到数据库 datasets表
        dataset_record = Dataset(
            id=dataset_id,
            name=request.name,
            file_id=file_id,
            duckdb_table=table_name,
            row_count=table_info["row_count"],
            schema_json={
                "columns": table_info["columns"],
                "column_count": len(table_info["columns"])
            },
            status="ready"
        )
        sql_db = db  # 保持语义清晰：db是SQLAlchemy session
        sql_db.add(dataset_record)
        await sql_db.flush()
        
        return {
            "dataset_id": dataset_id,
            "name": request.name,
            "table_name": table_name,
            "file_id": file_id,
            "sheet_name": request.sheet_name,
            "encoding": request.encoding,
            "row_count": table_info["row_count"],
            "column_count": len(table_info["columns"]),
            "columns": table_info["columns"],
            "preview": parse_result.get("preview"),
            "status": "created",
            "message": "数据集创建成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "CREATE_ERROR", "message": f"创建数据集失败: {str(e)}"}
        )


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)):
    """获取数据集信息"""
    result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DATASET_NOT_FOUND", "message": "数据集不存在"}
        )
    return record.to_dict()


@router.get("/{dataset_id}/preview")
async def preview_dataset(dataset_id: str, limit: int = 5):
    """预览数据集（前N行）"""
    try:
        db = get_duckdb()
        table_name = f"ds_{dataset_id.replace('-', '_')}"
        
        # 检查表是否存在
        tables = db.list_tables()
        if table_name not in tables:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "TABLE_NOT_FOUND", "message": "数据集表不存在"}
            )
        
        # 查询数据
        df = db.execute_query(f"SELECT * FROM {table_name} LIMIT {limit}")
        
        return {
            "dataset_id": dataset_id,
            "table_name": table_name,
            "columns": df.columns.tolist(),
            "rows": df.values.tolist(),
            "limit": limit
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "PREVIEW_ERROR", "message": f"预览失败: {str(e)}"}
        )


@router.get("/{dataset_id}/profile")
async def profile_dataset(dataset_id: str):
    """
    获取数据集字段画像（M1-07b）
    
    返回：
    - 8类字段类型推断
    - 每个字段的缺失率、基数、分布
    - 数据粒度识别（grain）
    """
    try:
        db = get_duckdb()
        table_name = f"ds_{dataset_id.replace('-', '_')}"
        
        # 检查表是否存在
        tables = db.list_tables()
        if table_name not in tables:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "TABLE_NOT_FOUND", "message": "数据集表不存在"}
            )
        
        # 获取表结构
        table_info = db.get_table_info(table_name)
        
        # 获取每个字段的画像
        profiles = []
        for col in table_info["columns"]:
            profile = db.get_profile(table_name, col["name"])
            # 添加DuckDB类型信息
            profile["duckdb_type"] = col["type"]
            profiles.append(profile)
        
        # 识别数据粒度
        grain = db.detect_grain(table_name, table_info["columns"])
        
        return {
            "dataset_id": dataset_id,
            "table_name": table_name,
            "total_rows": table_info["row_count"],
            "column_count": len(table_info["columns"]),
            "profiles": profiles,
            "grain": grain
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "PROFILE_ERROR", "message": f"画像生成失败: {str(e)}"}
        )


# M1-07b 验收专用接口：模拟v2五表数据
@router.post("/_internal/seed-test-data")
async def seed_test_data():
    """内部接口：创建测试数据用于验证（验收用）"""
    try:
        db = get_duckdb()
        
        # 01表：单笔借据示例
        df_01 = pd.DataFrame({
            "借据编号": ["JJ001", "JJ002", "JJ003", "JJ004", "JJ005"],
            "客户编号": ["C001", "C002", "C001", "C003", "C002"],
            "放款日期": ["2024-01-01", "2024-01-05", "2024-02-01", "2024-02-10", "2024-03-05"],
            "到期日期": ["2025-01-01", "2025-01-05", "2025-02-01", "2025-02-10", "2025-03-05"],
            "贷款金额": [100000, 200000, 150000, 300000, 250000],
            "担保类型": ["信用", "抵押", "质押", "抵押", "信用"],
            "抵押率": [0, 0.7, 0.8, 0.75, 0]
        })
        db.create_dataset_table("test_01_single_loan", df_01)
        grain_01 = db.detect_grain("ds_test_01_single_loan", [{"name": c, "type": "VARCHAR"} for c in df_01.columns])
        
        # 03表：月份×担保类型(宏观)示例
        df_03 = pd.DataFrame({
            "年月": ["2024-01", "2024-01", "2024-02", "2024-02", "2024-03"],
            "担保类型": ["信用", "抵押", "信用", "抵押", "质押"],
            "放款笔数": [100, 80, 120, 90, 60],
            "放款金额": [10000000, 50000000, 12000000, 60000000, 30000000],
            "平均期限": [12, 24, 12, 24, 6]
        })
        db.create_dataset_table("test_03_monthly_macro", df_03)
        grain_03 = db.detect_grain("ds_test_03_monthly_macro", [{"name": c, "type": "VARCHAR"} for c in df_03.columns])
        
        return {
            "message": "测试数据已创建",
            "tables": [
                {
                    "name": "ds_test_01_single_loan",
                    "desc": "01表：单笔借据",
                    "grain": grain_01
                },
                {
                    "name": "ds_test_03_monthly_macro",
                    "desc": "03表：月份×担保类型(宏观)",
                    "grain": grain_03
                }
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": str(e)}
        )


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)):
    """删除数据集"""
    try:
        # 删除DuckDB表
        duckdb = get_duckdb()
        table_name = f"ds_{dataset_id.replace('-', '_')}"
        duckdb.drop_table(table_name)
        
        # 从SQLite数据库删除记录
        result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
        record = result.scalar_one_or_none()
        if record:
            await db.delete(record)
            await db.flush()
        
        return {"message": "数据集删除成功", "dataset_id": dataset_id}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "DELETE_ERROR", "message": f"删除失败: {str(e)}"}
        )


# M1-07a 验收专用接口
@router.get("/_internal/duckdb/tables")
async def list_duckdb_tables():
    """内部接口：列出所有DuckDB表（验收用）"""
    try:
        db = get_duckdb()
        tables = db.list_tables()
        return {
            "tables": tables,
            "count": len(tables)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": str(e)}
        )


@router.get("/{dataset_id}/chart-data")
async def get_chart_data(dataset_id: str):
    """
    获取图表数据（用于前端渲染真实的ECharts图表）
    
    返回数据包括：
    - 所有字段的样本数据
    - 数值字段统计（min/max/avg/median）
    - 分类字段分布
    """
    try:
        db = get_duckdb()
        # 优先读取清洗层
        table_name = f"ds_{dataset_id.replace('-', '_')}_cleaned"
        if not db.table_exists(table_name):
            table_name = f"ds_{dataset_id.replace('-', '_')}"
            if not db.table_exists(table_name):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "TABLE_NOT_FOUND", "message": "数据集表不存在"}
                )
        
        # 获取表信息
        table_info = db.get_table_info(table_name)
        columns = [c["name"] for c in table_info.get("columns", [])]
        row_count = table_info.get("row_count", 0)
        
        # 获取所有数据
        limit = min(1000, row_count)
        rows = db.conn.execute(f'SELECT * FROM "{table_name}" LIMIT {limit}').fetchall()
        data = [dict(zip(columns, row)) for row in rows]
        
        # 数值字段统计
        numeric_stats = {}
        for col in columns:
            try:
                result = db.conn.execute(f"""
                    SELECT COUNT(*) as total,
                           COUNT(CASE WHEN "{col}" IS NOT NULL THEN 1 END) as not_null,
                           MIN(CAST("{col}" AS DOUBLE)) as min_val,
                           MAX(CAST("{col}" AS DOUBLE)) as max_val,
                           AVG(CAST("{col}" AS DOUBLE)) as avg_val,
                           MEDIAN(CAST("{col}" AS DOUBLE)) as median_val
                    FROM "{table_name}"
                    WHERE TRY_CAST("{col}" AS DOUBLE) IS NOT NULL
                """).fetchone()
                if result and result[1] > 0:
                    numeric_stats[col] = {
                        "total": result[0], "not_null": result[1],
                        "min": float(result[2]) if result[2] is not None else None,
                        "max": float(result[3]) if result[3] is not None else None,
                        "avg": round(float(result[4]), 2) if result[4] is not None else None,
                        "median": float(result[5]) if result[5] is not None else None,
                    }
            except:
                pass
        
        # 分类字段分布
        categorical_stats = {}
        for col in columns:
            try:
                result = db.conn.execute(f"""
                    SELECT "{col}", COUNT(*) as cnt 
                    FROM "{table_name}" WHERE "{col}" IS NOT NULL 
                    GROUP BY "{col}" ORDER BY cnt DESC LIMIT 20
                """).fetchall()
                if result and len(result) > 0:
                    categorical_stats[col] = [{"value": r[0], "count": r[1]} for r in result]
            except:
                pass
        
        return {
            "dataset_id": dataset_id,
            "table_name": table_name,
            "columns": columns,
            "row_count": row_count,
            "sample_count": len(data),
            "data": data,
            "numeric_stats": numeric_stats,
            "categorical_stats": categorical_stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "CHART_DATA_ERROR", "message": f"获取图表数据失败: {str(e)}"}
        )
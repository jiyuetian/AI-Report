"""文件上传API - M1-05a"""
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import os
import shutil
import uuid
import hashlib
from pathlib import Path
from typing import Optional
import magic

from app.core.config import settings
from app.core.audit import audit_log
from app.core.database import get_db
from app.models.file import File as FileModel

router = APIRouter(prefix="/files", tags=["Files"])

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'.xlsx', '.xls', '.csv'}

# 最大文件大小 100MB
MAX_FILE_SIZE = 100 * 1024 * 1024


def calculate_file_hash(file_path: Path) -> str:
    """计算文件MD5哈希（指纹）"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def detect_mime_type(file_path: Path) -> str:
    """检测文件真实MIME类型"""
    try:
        return magic.from_file(str(file_path), mime=True)
    except:
        return "application/octet-stream"


async def check_duplicate_file(file_hash: str, db: AsyncSession) -> Optional[dict]:
    """
    检查是否存在相同hash的文件
    返回已有文件信息或None
    使用limit(1)避免hash重复时scalar_one_or_none()抛MultipleResultsFound
    """
    from sqlalchemy import select
    result = await db.execute(
        select(FileModel).where(FileModel.hash == file_hash, FileModel.status != "deleted").limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {
            "file_id": existing.id,
            "filename": existing.name,
            "size": existing.size,
            "uploaded_at": existing.created_at.isoformat() if existing.created_at else None
        }
    return None


@router.post("", response_model=dict)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    上传数据文件
    
    支持格式: .xlsx, .xls, .csv
    最大大小: 100MB
    自动计算hash指纹用于查重
    """
    # 检查文件大小（Content-Length）
    content_length = request.headers.get('content-length')
    if content_length:
        file_size = int(content_length)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": "UPLOAD_413",
                    "message": f"文件过大: {file_size / 1024 / 1024:.1f}MB > 100MB"
                }
            )
    
    # 检查文件扩展名
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "UPLOAD_415",
                "message": f"不支持的文件类型: {file_ext}，仅支持 {ALLOWED_EXTENSIONS}"
            }
        )
    
    # 生成文件ID
    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    
    try:
        # 保存文件
        total_size = 0
        with open(file_path, "wb") as buffer:
            while chunk := file.file.read(8192):
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    # 删除已写入的部分
                    buffer.close()
                    file_path.unlink()
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail={
                            "code": "UPLOAD_413",
                            "message": f"文件过大: 超过100MB限制"
                        }
                    )
                buffer.write(chunk)
        
        # 检测MIME类型
        mime_type = detect_mime_type(file_path)
        
        # 计算文件hash指纹
        file_hash = calculate_file_hash(file_path)
        
        # 检查是否重复文件
        duplicate = await check_duplicate_file(file_hash, db)
        
        # 记录审计日志
        audit_log(
            action="FILE_UPLOAD",
            ip=request.client.host if request.client else None,
            detail={
                "file_id": file_id,
                "filename": file.filename,
                "size": total_size,
                "hash": file_hash,
                "mime_type": mime_type
            }
        )
        
        # 保存到数据库 (files表)
        from datetime import datetime, timedelta
        file_record = FileModel(
            id=file_id,
            name=file.filename,
            hash=file_hash,
            size=total_size,
            mime_type=mime_type,
            extension=file_ext,
            storage_path=str(file_path),
            status="temporary",
            expire_at=datetime.utcnow() + timedelta(days=7)
        )
        db.add(file_record)
        await db.flush()
        
        response_data = {
            "file_id": file_id,
            "filename": file.filename,
            "size": total_size,
            "hash": file_hash,
            "mime_type": mime_type,
            "extension": file_ext,
            "status": "uploaded",
            "is_duplicate": duplicate is not None,
            "existing_file": duplicate,
            "message": "文件上传成功"
        }
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # 清理失败的上传
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "UPLOAD_500",
                "message": f"文件上传失败: {str(e)}"
            }
        )


@router.get("/{file_id}")
async def get_file_info(file_id: str, db: AsyncSession = Depends(get_db)):
    """获取文件信息"""
    from sqlalchemy import select
    result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "FILE_NOT_FOUND", "message": "文件不存在"}
        )
    return record.to_dict()


@router.delete("/{file_id}")
async def delete_file(file_id: str, db: AsyncSession = Depends(get_db)):
    """删除文件"""
    from sqlalchemy import select
    result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "FILE_NOT_FOUND", "message": "文件不存在"}
        )
    
    # 删除磁盘文件
    file_path = Path(record.storage_path)
    if file_path.exists():
        file_path.unlink()
    
    # 删除数据库记录
    await db.delete(record)
    await db.flush()
    
    return {"message": "删除成功"}


# ============== M1-06 多Sheet与编码 ==============

from app.core.file_parser import FileParser
from pydantic import BaseModel


class SheetSelectRequest(BaseModel):
    file_id: str
    sheet_name: str


class EncodingSelectRequest(BaseModel):
    file_id: str
    encoding: str  # utf-8, gbk, gb18030, big5


@router.get("/{file_id}/sheets")
async def get_excel_sheets(file_id: str):
    """
    获取Excel文件的所有Sheet列表
    对应原型: m-sheet-select 弹窗数据
    """
    # 查找文件
    file_path = None
    file_ext = None
    for ext in ['.xlsx', '.xls']:
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
        sheets = FileParser.get_excel_sheets(file_path)
        return {
            "file_id": file_id,
            "sheets": sheets,
            "sheet_count": len(sheets),
            "needs_selection": len(sheets) > 1
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "PARSE_ERROR", "message": f"解析失败: {str(e)}"}
        )


@router.post("/{file_id}/select-sheet")
async def select_sheet(file_id: str, request: SheetSelectRequest):
    """
    选择Sheet并返回预览数据
    对应原型: m-sheet-select 确认后
    """
    # 查找文件
    file_path = None
    file_ext = None
    for ext in ['.xlsx', '.xls']:
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
        # 读取指定Sheet
        df = FileParser.read_excel_sheet(file_path, sheet_name=request.sheet_name)
        preview = FileParser.preview_data(df)
        
        return {
            "file_id": file_id,
            "selected_sheet": request.sheet_name,
            "preview": preview,
            "row_count": len(df),
            "col_count": len(df.columns)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "READ_ERROR", "message": f"读取失败: {str(e)}"}
        )


@router.get("/{file_id}/encoding")
async def detect_csv_encoding(file_id: str):
    """
    检测CSV文件编码
    对应原型: m-encoding 弹窗数据
    """
    # 查找CSV文件
    file_path = UPLOAD_DIR / f"{file_id}.csv"
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "FILE_NOT_FOUND", "message": "CSV文件不存在"}
        )
    
    try:
        detected_encoding, confidence = FileParser.detect_encoding(file_path)
        
        return {
            "file_id": file_id,
            "detected_encoding": detected_encoding,
            "confidence": confidence,
            "needs_selection": confidence < 0.7,
            "supported_encodings": FileParser.SUPPORTED_ENCODINGS,
            "suggested_encoding": detected_encoding if confidence >= 0.7 else "utf-8"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "DETECT_ERROR", "message": f"编码检测失败: {str(e)}"}
        )


@router.post("/{file_id}/select-encoding")
async def select_encoding(file_id: str, request: EncodingSelectRequest):
    """
    选择编码并返回预览数据
    对应原型: m-encoding 确认后
    """
    # 查找CSV文件
    file_path = UPLOAD_DIR / f"{file_id}.csv"
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "FILE_NOT_FOUND", "message": "CSV文件不存在"}
        )
    
    # 验证编码支持
    if request.encoding not in FileParser.SUPPORTED_ENCODINGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_ENCODING",
                "message": f"不支持的编码: {request.encoding}，支持的编码: {FileParser.SUPPORTED_ENCODINGS}"
            }
        )
    
    try:
        # 使用指定编码读取
        df, used_encoding = FileParser.read_csv_with_encoding(file_path, request.encoding)
        preview = FileParser.preview_data(df)
        
        return {
            "file_id": file_id,
            "selected_encoding": request.encoding,
            "used_encoding": used_encoding,
            "preview": preview,
            "row_count": len(df),
            "col_count": len(df.columns)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "READ_ERROR", "message": f"读取失败: {str(e)}"}
        )


@router.get("/{file_id}/preview")
async def preview_file(
    file_id: str,
    sheet_name: Optional[str] = None,
    encoding: Optional[str] = None
):
    """
    通用预览接口（自动处理Excel/CSV）
    """
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
        result = FileParser.parse_file(
            file_path,
            file_ext,
            sheet_name=sheet_name,
            encoding=encoding
        )
        
        # 移除dataframe对象，只返回可序列化的数据
        if "dataframe" in result:
            del result["dataframe"]
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "PREVIEW_ERROR", "message": f"预览失败: {str(e)}"}
        )
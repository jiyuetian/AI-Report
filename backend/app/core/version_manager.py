"""
版本管理 - M4-03
保存自动存档≤20、回退、两版对比、配置快照（含prompt版本）随版保存
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
import uuid
import json

from app.models.dashboard import Dashboard, DashboardVersion
from app.core.brain_config_manager import BrainConfigManager


@dataclass
class VersionSnapshot:
    """版本快照"""
    version_id: str
    dashboard_id: str
    version_number: int
    name: str
    description: str
    config_snapshot: Dict[str, Any]
    prompt_version: str
    created_by: str
    created_at: datetime
    is_auto_save: bool = False


class VersionManager:
    """版本管理器"""
    
    MAX_AUTO_SAVES = 20  # 最大自动存档数
    
    @staticmethod
    async def create_version(
        db: AsyncSession,
        dashboard_id: str,
        name: str,
        description: str = "",
        created_by: str = "anonymous",
        is_auto_save: bool = False
    ) -> VersionSnapshot:
        """
        创建新版本（含配置快照和prompt版本）
        """
        # 获取当前看板配置
        result = await db.execute(
            select(Dashboard).where(Dashboard.id == dashboard_id)
        )
        dashboard = result.scalar_one_or_none()
        
        if not dashboard:
            raise ValueError(f"看板不存在: {dashboard_id}")
        
        # 获取当前brain配置版本（prompt版本）
        brain_config = await BrainConfigManager.get_config(db, "s3_prompt_template")
        prompt_version = brain_config.get("version", "v1.0") if brain_config else "v1.0"
        
        # 生成版本号
        version_result = await db.execute(
            select(func.count(DashboardVersion.id)).where(
                DashboardVersion.dashboard_id == dashboard_id
            )
        )
        version_count = version_result.scalar() or 0
        version_number = version_count + 1
        
        # 创建版本记录
        version = DashboardVersion(
            id=str(uuid.uuid4()),
            dashboard_id=dashboard_id,
            version_number=version_number,
            name=name or f"版本 {version_number}",
            description=description,
            config_snapshot=dashboard.config_json,
            prompt_version=prompt_version,
            created_by=created_by,
            is_auto_save=is_auto_save
        )
        
        db.add(version)
        await db.commit()
        
        # 如果是自动保存，清理旧版本
        if is_auto_save:
            await VersionManager._cleanup_old_auto_saves(db, dashboard_id)
        
        return VersionSnapshot(
            version_id=version.id,
            dashboard_id=dashboard_id,
            version_number=version_number,
            name=version.name,
            description=version.description,
            config_snapshot=dashboard.config_json,
            prompt_version=prompt_version,
            created_by=created_by,
            created_at=version.created_at,
            is_auto_save=is_auto_save
        )
    
    @staticmethod
    async def _cleanup_old_auto_saves(db: AsyncSession, dashboard_id: str):
        """清理旧自动存档，保留最新的20个"""
        result = await db.execute(
            select(DashboardVersion).where(
                DashboardVersion.dashboard_id == dashboard_id,
                DashboardVersion.is_auto_save == True
            ).order_by(desc(DashboardVersion.created_at))
        )
        auto_saves = result.scalars().all()
        
        if len(auto_saves) > VersionManager.MAX_AUTO_SAVES:
            # 删除超出的旧版本
            to_delete = auto_saves[VersionManager.MAX_AUTO_SAVES:]
            for version in to_delete:
                await db.delete(version)
            await db.commit()
    
    @staticmethod
    async def get_version_list(
        db: AsyncSession,
        dashboard_id: str,
        include_auto_save: bool = True
    ) -> List[VersionSnapshot]:
        """获取版本列表"""
        query = select(DashboardVersion).where(
            DashboardVersion.dashboard_id == dashboard_id
        )
        
        if not include_auto_save:
            query = query.where(DashboardVersion.is_auto_save == False)
        
        query = query.order_by(desc(DashboardVersion.created_at))
        
        result = await db.execute(query)
        versions = result.scalars().all()
        
        return [
            VersionSnapshot(
                version_id=v.id,
                dashboard_id=v.dashboard_id,
                version_number=v.version_number,
                name=v.name,
                description=v.description,
                config_snapshot=v.config_snapshot,
                prompt_version=v.prompt_version,
                created_by=v.created_by,
                created_at=v.created_at,
                is_auto_save=v.is_auto_save
            )
            for v in versions
        ]
    
    @staticmethod
    async def rollback_to_version(
        db: AsyncSession,
        dashboard_id: str,
        version_id: str,
        user_id: str = "anonymous"
    ) -> Dict[str, Any]:
        """
        回退到指定版本
        """
        # 获取目标版本
        result = await db.execute(
            select(DashboardVersion).where(
                DashboardVersion.id == version_id,
                DashboardVersion.dashboard_id == dashboard_id
            )
        )
        target_version = result.scalar_one_or_none()
        
        if not target_version:
            raise ValueError(f"版本不存在: {version_id}")
        
        # 获取当前看板
        dashboard_result = await db.execute(
            select(Dashboard).where(Dashboard.id == dashboard_id)
        )
        dashboard = dashboard_result.scalar_one_or_none()
        
        if not dashboard:
            raise ValueError(f"看板不存在: {dashboard_id}")
        
        # 保存当前状态（自动存档）
        await VersionManager.create_version(
            db, dashboard_id,
            name=f"回退前自动保存",
            description=f"回退到版本 {target_version.version_number} 前的自动保存",
            created_by=user_id,
            is_auto_save=True
        )
        
        # 回退配置
        dashboard.config_json = target_version.config_snapshot
        dashboard.updated_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"已回退到版本 {target_version.version_number}: {target_version.name}",
            "rolled_back_version": {
                "id": target_version.id,
                "number": target_version.version_number,
                "name": target_version.name
            },
            "dashboard_id": dashboard_id
        }
    
    @staticmethod
    async def compare_versions(
        db: AsyncSession,
        version_id_1: str,
        version_id_2: str
    ) -> Dict[str, Any]:
        """
        对比两个版本
        """
        # 获取两个版本
        result1 = await db.execute(
            select(DashboardVersion).where(DashboardVersion.id == version_id_1)
        )
        version1 = result1.scalar_one_or_none()
        
        result2 = await db.execute(
            select(DashboardVersion).where(DashboardVersion.id == version_id_2)
        )
        version2 = result2.scalar_one_or_none()
        
        if not version1 or not version2:
            raise ValueError("版本不存在")
        
        # 对比配置差异
        config1 = version1.config_snapshot or {}
        config2 = version2.config_snapshot or {}
        
        differences = VersionManager._diff_configs(config1, config2)
        
        return {
            "version_1": {
                "id": version1.id,
                "number": version1.version_number,
                "name": version1.name,
                "created_at": version1.created_at.isoformat(),
                "prompt_version": version1.prompt_version
            },
            "version_2": {
                "id": version2.id,
                "number": version2.version_number,
                "name": version2.name,
                "created_at": version2.created_at.isoformat(),
                "prompt_version": version2.prompt_version
            },
            "differences": differences,
            "same_prompt": version1.prompt_version == version2.prompt_version
        }
    
    @staticmethod
    def _diff_configs(config1: Dict, config2: Dict) -> List[Dict[str, Any]]:
        """对比两个配置，返回差异列表"""
        differences = []
        
        # 对比图表配置
        charts1 = {c.get("id"): c for c in config1.get("charts", [])}
        charts2 = {c.get("id"): c for c in config2.get("charts", [])}
        
        all_chart_ids = set(charts1.keys()) | set(charts2.keys())
        
        for chart_id in all_chart_ids:
            if chart_id not in charts1:
                differences.append({
                    "type": "added",
                    "field": f"chart.{chart_id}",
                    "description": f"新增图表: {charts2[chart_id].get('title', chart_id)}"
                })
            elif chart_id not in charts2:
                differences.append({
                    "type": "removed",
                    "field": f"chart.{chart_id}",
                    "description": f"删除图表: {charts1[chart_id].get('title', chart_id)}"
                })
            elif charts1[chart_id] != charts2[chart_id]:
                differences.append({
                    "type": "modified",
                    "field": f"chart.{chart_id}",
                    "description": f"修改图表: {charts1[chart_id].get('title', chart_id)}"
                })
        
        # 对比标题
        if config1.get("title") != config2.get("title"):
            differences.append({
                "type": "modified",
                "field": "title",
                "old_value": config1.get("title"),
                "new_value": config2.get("title")
            })
        
        return differences
    
    @staticmethod
    async def auto_save(
        db: AsyncSession,
        dashboard_id: str,
        user_id: str = "anonymous"
    ) -> Optional[VersionSnapshot]:
        """
        自动保存（当配置发生变化时）
        """
        # 获取最新自动存档
        result = await db.execute(
            select(DashboardVersion).where(
                DashboardVersion.dashboard_id == dashboard_id,
                DashboardVersion.is_auto_save == True
            ).order_by(desc(DashboardVersion.created_at))
        )
        latest_auto_save = result.scalar_one_or_none()
        
        # 获取当前看板
        dashboard_result = await db.execute(
            select(Dashboard).where(Dashboard.id == dashboard_id)
        )
        dashboard = dashboard_result.scalar_one_or_none()
        
        if not dashboard:
            return None
        
        # 如果配置没有变化，不保存
        if latest_auto_save:
            if latest_auto_save.config_snapshot == dashboard.config_json:
                return None
        
        # 创建新的自动存档
        return await VersionManager.create_version(
            db, dashboard_id,
            name=f"自动保存 {datetime.now().strftime('%m-%d %H:%M')}",
            description="系统自动保存",
            created_by=user_id,
            is_auto_save=True
        )

from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, DateTime
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import logging
from .models import Base, DBVersion

logger = logging.getLogger(__name__)

class DBMigration:
    """数据库迁移管理器"""
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库迁移管理器
        
        Args:
            db_path (str, optional): 数据库文件路径
        """
        # 延迟导入，避免循环依赖
        from .chats_db import get_engine
        self.db_path = db_path
        self.engine = get_engine(db_path)
        self.Session = sessionmaker(bind=self.engine)
        
    def get_current_version(self) -> Optional[str]:
        """获取当前数据库版本"""
        session = self.Session()
        try:
            version = DBVersion.get_current_version(session)
            return version.version if version else None
        finally:
            session.close()
            
    def upgrade_to_version(self, target_version: str, description: str = None) -> bool:
        """
        升级数据库到指定版本
        
        Args:
            target_version (str): 目标版本号
            description (str, optional): 升级描述
            
        Returns:
            bool: 升级是否成功
        """
        current_version = self.get_current_version()
        if not current_version:
            logger.error("无法获取当前数据库版本")
            return False
        
        # 版本号比较，禁止降级
        current_parts = [int(x) for x in current_version.split('.')]
        target_parts = [int(x) for x in target_version.split('.')]
        if current_parts > target_parts:
            logger.error(f"不允许降级操作: {current_version} -> {target_version}")
            return False
        
        # 获取所有可用的升级脚本
        upgrade_scripts = self._get_upgrade_scripts(current_version, target_version)
        if not upgrade_scripts:
            logger.info(f"数据库已经是最新版本 {current_version}")
            return True
        
        session = self.Session()
        try:
            # 执行每个升级脚本
            for script in upgrade_scripts:
                logger.info(f"执行升级脚本: {script['version']} - {script['description']}")
                if not self._execute_upgrade_script(session, script):
                    session.rollback()
                    return False
            # 更新版本记录
            DBVersion.upgrade_version(session, target_version, description)
            session.commit()
            logger.info(f"数据库升级成功: {current_version} -> {target_version}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"数据库升级失败: {str(e)}")
            return False
        finally:
            session.close()
            
    def _get_upgrade_scripts(self, current_version: str, target_version: str) -> List[Dict[str, Any]]:
        """
        获取从当前版本到目标版本的所有升级脚本
        
        Args:
            current_version (str): 当前版本
            target_version (str): 目标版本
            
        Returns:
            List[Dict[str, Any]]: 升级脚本列表
        """
        current_parts = [int(x) for x in current_version.split('.')]
        target_parts = [int(x) for x in target_version.split('.')]
        # 检查是否需要升级
        if current_parts < target_parts:
            return [{
                'version': target_version,
                'description': f'Upgrade from {current_version} to {target_version}',
                'upgrade_func': self._create_upgrade_function(current_version, target_version)
            }]
        # 如果是相同版本或降级，返回空列表
        return []
        
    def _execute_upgrade_script(self, session, script: Dict[str, Any]) -> bool:
        """
        执行升级脚本
        
        Args:
            session: 数据库会话
            script (Dict[str, Any]): 升级脚本信息
            
        Returns:
            bool: 执行是否成功
        """
        try:
            # 执行升级函数
            script['upgrade_func'](session)
            return True
        except Exception as e:
            logger.error(f"执行升级脚本失败: {str(e)}")
            return False
            
    def _create_upgrade_function(self, from_version: str, to_version: str):
        """
        创建升级函数
        
        Args:
            from_version (str): 起始版本
            to_version (str): 目标版本
            
        Returns:
            function: 升级函数
        """
        def upgrade_func(session):
            # 这里实现具体的数据库结构升级逻辑
            # 例如：添加新表、修改表结构等
            if from_version == "1.0.0" and to_version == "2.0.0":
                # 示例：添加新表
                metadata = MetaData()
                new_table = Table(
                    'new_feature_table',
                    metadata,
                    Column('id', Integer, primary_key=True),
                    Column('name', String(50)),
                    Column('created_at', DateTime, default=datetime.utcnow)
                )
                new_table.create(self.engine)
                
            elif from_version == "2.0.0" and to_version == "2.1.0":
                # 示例：修改表结构
                # 这里可以添加修改表结构的SQL语句
                pass
                
        return upgrade_func
        
    def create_migration_script(self, version: str, description: str) -> str:
        """
        创建迁移脚本模板
        
        Args:
            version (str): 版本号
            description (str): 描述
            
        Returns:
            str: 迁移脚本模板
        """
        template = f"""from datetime import datetime
from sqlalchemy import Table, Column, String, Integer, DateTime, MetaData

def upgrade(session, engine):
    \"\"\"
    数据库升级脚本: {version}
    描述: {description}
    \"\"\"
    metadata = MetaData()
    
    # 在这里添加升级逻辑
    # 例如：
    # new_table = Table(
    #     'new_table',
    #     metadata,
    #     Column('id', Integer, primary_key=True),
    #     Column('name', String(50)),
    #     Column('created_at', DateTime, default=datetime.utcnow)
    # )
    # new_table.create(engine)
    
    return True
"""
        return template 
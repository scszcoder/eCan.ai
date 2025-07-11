from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, DateTime, JSON, Boolean
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import logging
from .models import Base, DBVersion

from utils.logger_helper import logger_helper as logger

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
        """获取当前数据库版本，若无则自动插入1.0.0"""
        session = self.Session()
        try:
            from agent.chats.models import DBVersion
            version = DBVersion.get_current_version(session)
            if not version:
                # 自动插入初始版本
                DBVersion.upgrade_version(session, '1.0.0', description='初始化版本')
                version = DBVersion.get_current_version(session)
            return version.version if version else '1.0.0'
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
        # 定义所有已知的升级路径
        upgrade_path = [
            ("1.0.0", "1.0.1"),
            ("1.0.1", "2.0.0"),
        ]
        # 生成所有需要执行的升级步骤
        scripts = []
        version = current_version
        while version != target_version:
            for from_v, to_v in upgrade_path:
                if from_v == version:
                    scripts.append({
                        'version': to_v,
                        'description': f'Upgrade from {from_v} to {to_v}',
                        'upgrade_func': self._create_upgrade_function(from_v, to_v)
                    })
                    version = to_v
                    break
            else:
                # 没有找到下一个升级路径，说明目标版本不可达
                break
        return scripts
        
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
        """
        def upgrade_func(session):
            # 这里实现具体的数据库结构升级逻辑
            # 例如：添加新表、修改表结构等
            if from_version == "1.0.0" and to_version == "1.0.1":
                # 为 db_version 表添加 upgraded_at 字段（如果不存在）
                with self.engine.connect() as conn:
                    result = conn.execute(text("PRAGMA table_info(db_version);"))
                    columns = [row[1] for row in result]
                    if "upgraded_at" not in columns:
                        conn.execute(text("ALTER TABLE db_version ADD COLUMN upgraded_at DATETIME;"))
            if from_version == "1.0.1" and to_version == "2.0.0":
                # 创建 chat_notification 表
                metadata = MetaData()
                chat_notification = Table(
                    'chat_notification',
                    metadata,
                    Column('uid', String(64), primary_key=True),
                    Column('chatId', String(64), nullable=False),
                    Column('notification', JSON, nullable=False),
                    Column('time', Integer, nullable=False),
                    Column('isRead', Boolean, default=False)
                )
                metadata.create_all(self.engine, tables=[chat_notification])
            # 可继续添加更多升级分支
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
from sqlalchemy import Table, Column, String, Integer, DateTime, MetaData, JSON, Boolean

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
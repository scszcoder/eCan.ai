import pytest
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, DateTime
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import tempfile
from ..db_migration import DBMigration
from ..chats_db import Base, DBVersion, init_chats_db

@pytest.fixture(scope="function")
def temp_db():
    """创建临时数据库文件"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture(scope="function")
def db_migration(temp_db):
    """创建数据库迁移管理器实例"""
    # 初始化数据库
    init_chats_db(temp_db)
    return DBMigration(temp_db)

class TestDBMigration:
    """测试数据库迁移管理器"""
    
    def test_get_current_version(self, db_migration):
        """测试获取当前版本"""
        version = db_migration.get_current_version()
        assert version == "1.0.0"
        
    def test_upgrade_to_version(self, db_migration):
        """测试升级到新版本"""
        # 升级到2.0.0
        success = db_migration.upgrade_to_version("2.0.0", "升级到2.0.0版本")
        assert success is True
        
        # 验证版本已更新
        version = db_migration.get_current_version()
        assert version == "2.0.0"
        
        # 验证新表已创建
        engine = db_migration.engine
        metadata = MetaData()
        metadata.reflect(bind=engine)
        assert 'new_feature_table' in metadata.tables
        
    def test_upgrade_to_same_version(self, db_migration):
        """测试升级到当前版本"""
        success = db_migration.upgrade_to_version("1.0.0", "升级到当前版本")
        assert success is True
        version = db_migration.get_current_version()
        assert version == "1.0.0"
        
    def test_upgrade_to_older_version(self, db_migration):
        """测试升级到旧版本（应该失败）"""
        # 先升级到2.0.0
        db_migration.upgrade_to_version("2.0.0", "升级到2.0.0版本")
        
        # 尝试升级到1.0.0
        success = db_migration.upgrade_to_version("1.0.0", "尝试升级到旧版本")
        assert success is False
        version = db_migration.get_current_version()
        assert version == "2.0.0"
        
    def test_create_migration_script(self, db_migration):
        """测试创建迁移脚本模板"""
        template = db_migration.create_migration_script(
            "2.0.0",
            "添加新功能表"
        )
        assert "数据库升级脚本: 2.0.0" in template
        assert "描述: 添加新功能表" in template
        assert "def upgrade(session, engine):" in template 
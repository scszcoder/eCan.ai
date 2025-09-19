import os

from sqlalchemy import create_engine, Engine, inspect,  text
from sqlalchemy.orm import declarative_base, sessionmaker

from utils.logger_helper import logger_helper

Base = declarative_base()
engine: Engine

def init_db(dbfile):
    """
    优化的数据库初始化，提供更好的性能和错误处理
    """
    global engine
    
    try:
        logger_helper.info(f"🗄️ Initializing database: {dbfile}")

        # 确保目录和文件存在
        if not os.path.isfile(dbfile):
            # 获取文件所在目录
            dir_name = os.path.dirname(dbfile)
            # 确保目录存在
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)
                logger_helper.info(f"📁 Created database directory: {dir_name}")
            
            # 创建空文件
            with open(dbfile, 'w') as f:
                pass  # 创建一个空文件
            logger_helper.info(f"📄 Created database file: {dbfile}")

        # 创建引擎，使用优化设置提升启动速度
        engine = create_engine(
            f"sqlite:///{dbfile}",
            echo=False,
            # SQLite 特定优化
            connect_args={
                'check_same_thread': False,  # 允许多线程
                'timeout': 30,  # 连接超时
            },
            # 连接池设置，提升性能
            pool_pre_ping=True,  # 使用前验证连接
            pool_recycle=3600,   # 每小时回收连接
        )

        # 创建表（SQLite 通常很快）
        logger_helper.info("🔧 Creating database tables...")
        Base.metadata.create_all(engine)
        logger_helper.info("✅ Database initialization completed successfully")

        return engine

    except Exception as e:
        logger_helper.error(f"❌ Database initialization failed: {e}")
        # 简化的回退方案
        try:
            engine = create_engine(f"sqlite:///{dbfile}", echo=False)
            Base.metadata.create_all(engine)
            logger_helper.info("✅ Database initialized with fallback method")
            return engine
        except Exception as fallback_error:
            logger_helper.error(f"❌ Fallback database initialization also failed: {fallback_error}")
            raise


def sync_table_columns(model_class, table_name, db_engine=None):
    """检查并尝试添加缺失的列"""
    # 使用传入的引擎或全局引擎
    target_engine = db_engine if db_engine is not None else engine

    # 获取表的元数据
    inspector = inspect(target_engine)
    # 获取模型中定义的列
    existing_columns = {col['name']: col for col in inspector.get_columns(table_name)}
    model_columns = {c.name: c for c in model_class.__table__.columns}
    with target_engine.begin() as conn:
        for col_name, column in model_columns.items():
            if col_name not in existing_columns:
                # 构造并执行ALTER TABLE ADD COLUMN语句
                alter_query = text(
                    f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column.type.compile(dialect=target_engine.dialect)}")
                logger_helper.info(f"Adding column {column.name} to table {table_name}, sql: {alter_query}")
                conn.execute(alter_query)


def get_session(engine):
    """获取数据库会话"""
    Session = sessionmaker(bind=engine)
    return Session()
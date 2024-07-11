import os

from sqlalchemy import create_engine, Engine, inspect,  text
from sqlalchemy.orm import declarative_base, sessionmaker

from utils.logger_helper import logger_helper

Base = declarative_base()
engine: Engine

def init_db(dbfile):
    """
    初始化数据库
    """
    if not os.path.isfile(dbfile):
        # 获取文件所在目录
        dir_name = os.path.dirname(dbfile)
        # 确保目录存在
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        with open(dbfile, 'w') as f:
            pass  # 创建一个空文件
    global engine
    engine = create_engine("sqlite:///" + dbfile, echo=True)
    Base.metadata.create_all(engine)
    return engine


def sync_table_columns(model_class, table_name):
    """检查并尝试添加缺失的列"""
    # 获取表的元数据
    inspector = inspect(engine)
    # 获取模型中定义的列
    existing_columns = {col['name']: col for col in inspector.get_columns(table_name)}
    model_columns = {c.name: c for c in model_class.__table__.columns}
    with engine.begin() as conn:
        for col_name, column in model_columns.items():
            if col_name not in existing_columns:
                # 构造并执行ALTER TABLE ADD COLUMN语句
                alter_query = text(
                    f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column.type.compile(dialect=engine.dialect)}")
                logger_helper.info(f"Adding column {column.name} to table bots, sql: {alter_query}")
                conn.execute(alter_query)


def get_session(engine):
    """获取数据库会话"""
    Session = sessionmaker(bind=engine)
    return Session()
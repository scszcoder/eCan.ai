import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
def init_db(dbfile):
    if not os.path.isfile(dbfile):
        # 获取文件所在目录
        dir_name = os.path.dirname(dbfile)
        # 确保目录存在
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        with open(dbfile, 'w') as f:
            pass  # 创建一个空文件
    engine = create_engine("sqlite:///" + dbfile, echo=True)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    """获取数据库会话"""
    Session = sessionmaker(bind=engine)
    return Session()

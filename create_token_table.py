"""Create token_usage table in the database"""
import sys
sys.path.insert(0, '.')

from agent.db.ec_db_mgr import ECDBMgr
from agent.db.models.token_usage_model import TokenUsage
from utils.logger_helper import logger_helper as logger

# Initialize database manager
db_mgr = ECDBMgr(db_path='scszsj_gmail_com', auto_migrate=False)

# ECDBMgr auto-initializes in __init__, just get the engine
engine = db_mgr.get_engine()

# Create token_usage table
TokenUsage.__table__.create(engine, checkfirst=True)
logger.info("token_usage table created successfully")

# Verify table exists
from sqlalchemy import inspect
inspector = inspect(engine)
tables = inspector.get_table_names()
logger.info(f"Tables in database: {tables}")
logger.info(f"token_usage table exists: {'token_usage' in tables}")

import os

from sqlalchemy import create_engine, Engine, inspect,  text
from sqlalchemy.orm import declarative_base, sessionmaker

from utils.logger_helper import logger_helper

Base = declarative_base()
engine: Engine

def init_db(dbfile):
    """
    Optimized database initialization with better performance and error handling
    """
    global engine

    try:
        logger_helper.info(f"🗄️ Initializing database: {dbfile}")

        # Ensure directory and file exist
        if not os.path.isfile(dbfile):
            # Get directory containing the file
            dir_name = os.path.dirname(dbfile)
            # Ensure directory exists
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)
                logger_helper.info(f"📁 Created database directory: {dir_name}")

            # Create empty file
            with open(dbfile, 'w') as f:
                pass  # Create an empty file
            logger_helper.info(f"📄 Created database file: {dbfile}")

        # Create engine with optimized settings to improve startup speed
        engine = create_engine(
            f"sqlite:///{dbfile}",
            echo=False,
            # SQLite specific optimizations
            connect_args={
                'check_same_thread': False,  # Allow multi-threading
                'timeout': 30,  # Connection timeout
            },
            # Connection pool settings to improve performance
            pool_pre_ping=True,  # Verify connection before use
            pool_recycle=3600,   # Recycle connections every hour
        )

        # Create tables (SQLite is usually fast)
        logger_helper.info("🔧 Creating database tables...")
        Base.metadata.create_all(engine)
        logger_helper.info("✅ Database initialization completed successfully")

        return engine

    except Exception as e:
        logger_helper.error(f"❌ Database initialization failed: {e}")
        # Simplified fallback solution
        try:
            engine = create_engine(f"sqlite:///{dbfile}", echo=False)
            Base.metadata.create_all(engine)
            logger_helper.info("✅ Database initialized with fallback method")
            return engine
        except Exception as fallback_error:
            logger_helper.error(f"❌ Fallback database initialization also failed: {fallback_error}")
            raise


def sync_table_columns(model_class, table_name, db_engine=None):
    """Check and attempt to add missing columns"""
    # Use passed engine or global engine
    target_engine = db_engine if db_engine is not None else engine

    # Get table metadata
    inspector = inspect(target_engine)
    # Get columns defined in model
    existing_columns = {col['name']: col for col in inspector.get_columns(table_name)}
    model_columns = {c.name: c for c in model_class.__table__.columns}
    with target_engine.begin() as conn:
        for col_name, column in model_columns.items():
            if col_name not in existing_columns:
                # Construct and execute ALTER TABLE ADD COLUMN statement
                alter_query = text(
                    f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column.type.compile(dialect=target_engine.dialect)}")
                logger_helper.info(f"Adding column {column.name} to table {table_name}, sql: {alter_query}")
                conn.execute(alter_query)


def get_session(engine):
    """Get database session"""
    Session = sessionmaker(bind=engine)
    return Session()
"""
Migration from version 3.0.3 to 3.0.4

This migration makes the following changes:
1. agents table: Rename personality_traits column to personalities

Rationale:
- Unify field naming across all layers (object, DTO, database, frontend)
- Follow naming convention: multiple values use plural form (personalities)
- Simplify naming: personalities is more concise than personality_traits
"""

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..base_migration import BaseMigration
from utils.logger_helper import logger_helper as logger


class Migration303To304(BaseMigration):
    """Migration from 3.0.3 to 3.0.4 - Rename personality_traits to personalities"""
    
    @property
    def version(self) -> str:
        return "3.0.4"
    
    @property
    def previous_version(self) -> str:
        return "3.0.3"
    
    @property
    def description(self) -> str:
        return "Rename personality_traits column to personalities in agents table"
    
    def upgrade(self, session: Session) -> bool:
        """
        Perform the migration to 3.0.4.
        
        Changes:
        1. Rename personality_traits column to personalities in agents table
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if agents table exists
            if not self.table_exists('agents'):
                logger.error("agents table does not exist, cannot apply migration")
                return False
            
            # Check if personality_traits column exists
            if not self.column_exists('agents', 'personality_traits'):
                # Check if personalities column already exists (migration already applied)
                if self.column_exists('agents', 'personalities'):
                    logger.info("personalities column already exists, migration may have been applied")
                    return True
                else:
                    logger.error("Neither personality_traits nor personalities column exists")
                    return False
            
            # Rename personality_traits to personalities
            if not self._rename_personality_traits_column(session):
                return False
            
            logger.info("Successfully completed migration to 3.0.4")
            return True
            
        except Exception as e:
            logger.error(f"Failed to migrate to 3.0.4: {e}")
            return False
    
    def _rename_personality_traits_column(self, session: Session) -> bool:
        """
        Rename personality_traits column to personalities in agents table.
        
        Note: SQLite doesn't support ALTER COLUMN RENAME directly, so we need to:
        1. Create a new table with the correct schema
        2. Copy data from old table
        3. Drop old table
        4. Rename new table
        """
        try:
            logger.info("Renaming personality_traits column to personalities in agents table")
            
            # Step 1: Create new table with personalities column
            create_new_table_sql = """
            CREATE TABLE agents_new (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(128) NOT NULL,
                description TEXT,
                owner VARCHAR(128) NOT NULL,
                gender VARCHAR(16),
                title JSON,
                rank VARCHAR(64),
                birthday VARCHAR(32),
                supervisor_id VARCHAR(64),
                personalities JSON,
                capabilities JSON,
                tasks JSON,
                skills JSON,
                status VARCHAR(32) DEFAULT 'active',
                version VARCHAR(32),
                url VARCHAR(256),
                extra_data JSON,
                vehicle_id VARCHAR(64),
                created_at DATETIME,
                updated_at DATETIME,
                ext JSON,
                FOREIGN KEY (supervisor_id) REFERENCES agents(id)
            )
            """
            
            if not self.execute_sql(session, create_new_table_sql):
                logger.error("Failed to create new agents table")
                return False
            
            logger.info("Created new agents_new table")
            
            # Step 2: Copy data from old table to new table
            # Map personality_traits to personalities
            # Explicitly specify all columns to prevent column count mismatch
            copy_data_sql = """
            INSERT INTO agents_new 
            (id, name, description, owner, gender, title, rank, birthday, 
             supervisor_id, personalities, capabilities, tasks, skills, 
             status, version, url, extra_data, vehicle_id, 
             created_at, updated_at, ext)
            SELECT 
                id, name, description, owner, gender, title, rank, birthday, 
                supervisor_id,
                personality_traits as personalities,
                capabilities, tasks, skills, status, version, url, extra_data, 
                vehicle_id, created_at, updated_at, ext
            FROM agents
            """
            
            if not self.execute_sql(session, copy_data_sql):
                logger.error("Failed to copy data to new table")
                # Cleanup: drop the new table
                self.execute_sql(session, "DROP TABLE IF EXISTS agents_new")
                return False
            
            logger.info("Copied data to new table with renamed column")
            
            # Step 3: Drop old table
            drop_old_table_sql = "DROP TABLE agents"
            
            if not self.execute_sql(session, drop_old_table_sql):
                logger.error("Failed to drop old agents table")
                # Cleanup: drop the new table
                self.execute_sql(session, "DROP TABLE IF EXISTS agents_new")
                return False
            
            logger.info("Dropped old agents table")
            
            # Step 4: Rename new table to original name
            rename_table_sql = "ALTER TABLE agents_new RENAME TO agents"
            
            if not self.execute_sql(session, rename_table_sql):
                logger.error("Failed to rename new table")
                return False
            
            logger.info("Renamed new table to agents")
            
            # Flush the changes
            session.flush()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to rename personality_traits column: {e}")
            session.rollback()
            # Try to cleanup
            try:
                self.execute_sql(session, "DROP TABLE IF EXISTS agents_new")
            except:
                pass
            return False
    
    def validate_postconditions(self, session: Session) -> bool:
        """
        Validate that all migration changes were applied successfully.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if validation passes, False otherwise
        """
        # Flush session to ensure all changes are committed
        session.flush()
        
        try:
            # Check that agents table exists
            if not self.table_exists('agents'):
                logger.error("agents table does not exist after migration")
                return False
            
            # Get table schema
            result = session.execute(text("PRAGMA table_info(agents)"))
            agent_columns = {row[1]: {'type': row[2], 'notnull': row[3]} for row in result.fetchall()}
            
            # Check that personalities column exists
            if 'personalities' not in agent_columns:
                logger.error("personalities column missing from agents table")
                return False
            
            # Check that personality_traits column no longer exists
            if 'personality_traits' in agent_columns:
                logger.error("personality_traits column still exists in agents table")
                return False
            
            # Check if personalities is JSON type (SQLite may show it as JSON or TEXT)
            personalities_type = agent_columns['personalities']['type'].upper()
            if personalities_type not in ['JSON', 'TEXT']:
                logger.error(f"personalities column has unexpected type: {personalities_type}")
                return False
            
            logger.info("✓ personality_traits column successfully renamed to personalities")
            logger.info("✓ personalities column is JSON type")
            
            # Verify data integrity - check that we can read personalities data
            result = session.execute(text("SELECT COUNT(*) FROM agents WHERE personalities IS NOT NULL"))
            count = result.scalar()
            logger.info(f"✓ Found {count} agents with personalities data")
            
            logger.info("All postconditions validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate postconditions: {e}")
            return False
    
    def downgrade(self, session: Session) -> bool:
        """
        Downgrade from 3.0.4 to 3.0.3.
        
        This renames personalities back to personality_traits.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.warning("Downgrade from 3.0.4 to 3.0.3: Renaming personalities back to personality_traits")
            
            # Check if personalities column exists
            if not self.column_exists('agents', 'personalities'):
                logger.error("personalities column does not exist, cannot downgrade")
                return False
            
            # Create new table with personality_traits column
            create_new_table_sql = """
            CREATE TABLE agents_new (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(128) NOT NULL,
                description TEXT,
                owner VARCHAR(128) NOT NULL,
                gender VARCHAR(16),
                title JSON,
                rank VARCHAR(64),
                birthday VARCHAR(32),
                supervisor_id VARCHAR(64),
                personality_traits JSON,
                capabilities JSON,
                tasks JSON,
                skills JSON,
                status VARCHAR(32) DEFAULT 'active',
                version VARCHAR(32),
                url VARCHAR(256),
                extra_data JSON,
                vehicle_id VARCHAR(64),
                created_at DATETIME,
                updated_at DATETIME,
                ext JSON,
                FOREIGN KEY (supervisor_id) REFERENCES agents(id)
            )
            """
            
            if not self.execute_sql(session, create_new_table_sql):
                logger.error("Failed to create new agents table for downgrade")
                return False
            
            # Copy data, renaming personalities back to personality_traits
            # Explicitly specify all columns to prevent column count mismatch
            copy_data_sql = """
            INSERT INTO agents_new 
            (id, name, description, owner, gender, title, rank, birthday, 
             supervisor_id, personality_traits, capabilities, tasks, skills, 
             status, version, url, extra_data, vehicle_id, 
             created_at, updated_at, ext)
            SELECT 
                id, name, description, owner, gender, title, rank, birthday, 
                supervisor_id,
                personalities as personality_traits,
                capabilities, tasks, skills, status, version, url, extra_data, 
                vehicle_id, created_at, updated_at, ext
            FROM agents
            """
            
            if not self.execute_sql(session, copy_data_sql):
                logger.error("Failed to copy data during downgrade")
                self.execute_sql(session, "DROP TABLE IF EXISTS agents_new")
                return False
            
            # Drop old table and rename new table
            if not self.execute_sql(session, "DROP TABLE agents"):
                logger.error("Failed to drop old table during downgrade")
                self.execute_sql(session, "DROP TABLE IF EXISTS agents_new")
                return False
            
            if not self.execute_sql(session, "ALTER TABLE agents_new RENAME TO agents"):
                logger.error("Failed to rename table during downgrade")
                return False
            
            session.flush()
            
            logger.info("Downgrade completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to downgrade: {e}")
            session.rollback()
            try:
                self.execute_sql(session, "DROP TABLE IF EXISTS agents_new")
            except:
                pass
            return False

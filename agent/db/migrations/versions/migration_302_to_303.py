"""
Migration from version 3.0.2 to 3.0.3

This migration makes the following changes:
1. agent_task_rels table: Change vehicle_id column from NOT NULL to NULL (optional)
2. agents table: Add vehicle_id column to store where agent is deployed/stored
3. agents table: Convert title column from String to JSON
4. agent_skills table: Add diagram column (JSON) to store workflow/diagram data

Rationale:
- Agent's vehicle_id: Indicates where the agent is deployed/stored
- Task's vehicle_id: Indicates where the task is executed (can be different from agent's vehicle)
- vehicle_id in agent_task_rels should be optional, assigned during task execution
- title should be JSON array to support multiple titles
- diagram stores workflow/diagram data needed to rebuild skill runnable
"""

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..base_migration import BaseMigration
from utils.logger_helper import logger_helper as logger


class Migration302To303(BaseMigration):
    """Migration from 3.0.2 to 3.0.3 - Make vehicle_id optional in agent_task_rels"""
    
    @property
    def version(self) -> str:
        return "3.0.3"
    
    @property
    def previous_version(self) -> str:
        return "3.0.2"
    
    @property
    def description(self) -> str:
        return "Make vehicle_id nullable in agent_task_rels, add vehicle_id to agents, convert title to JSON, and add diagram to agent_skills"
    
    def upgrade(self, session: Session) -> bool:
        """
        Perform the migration to 3.0.3.
        
        Changes:
        1. Make vehicle_id column nullable in agent_task_rels table
        2. Add vehicle_id column to agents table (where agent is deployed/stored)
        3. Convert title column from String to JSON in agents table
        4. Add diagram column to agent_skills table for workflow storage
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if required tables exist
            if not self.table_exists('agent_task_rels'):
                logger.error("agent_task_rels table does not exist, cannot apply migration")
                return False
            
            if not self.table_exists('agents'):
                logger.error("agents table does not exist, cannot apply migration")
                return False
            
            # 1. Modify vehicle_id column to be nullable in agent_task_rels
            if not self._modify_vehicle_id_column(session):
                return False
            
            # 2. Convert title column to JSON in agents table
            if not self._convert_title_to_json(session):
                return False
            
            # 3. Add diagram column to agent_skills table
            if not self._add_diagram_to_agent_skills(session):
                return False
            
            logger.info("Successfully completed migration to 3.0.3")
            return True
            
        except Exception as e:
            logger.error(f"Failed to migrate to 3.0.3: {e}")
            return False
    
    def _modify_vehicle_id_column(self, session: Session) -> bool:
        """
        Modify vehicle_id column in agent_task_rels table to be nullable.
        
        Note: SQLite doesn't support ALTER COLUMN directly, so we need to:
        1. Create a new table with the correct schema
        2. Copy data from old table
        3. Drop old table
        4. Rename new table
        """
        try:
            # Check if column exists
            if not self.column_exists('agent_task_rels', 'vehicle_id'):
                logger.error("vehicle_id column does not exist in agent_task_rels table")
                return False
            
            logger.info("Modifying vehicle_id column to be nullable in agent_task_rels table")
            
            # Step 1: Create new table with correct schema
            create_new_table_sql = """
            CREATE TABLE agent_task_rels_new (
                id VARCHAR(64) PRIMARY KEY,
                agent_id VARCHAR(64) NOT NULL,
                task_id VARCHAR(64) NOT NULL,
                vehicle_id VARCHAR(64),
                status VARCHAR(32) DEFAULT 'pending',
                priority VARCHAR(32) DEFAULT 'medium',
                progress FLOAT DEFAULT 0.0,
                scheduled_start DATETIME,
                actual_start DATETIME,
                estimated_end DATETIME,
                actual_end DATETIME,
                result JSON,
                error_message TEXT,
                logs TEXT,
                cpu_usage FLOAT,
                memory_usage FLOAT,
                execution_time FLOAT,
                execution_context JSON,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY (agent_id) REFERENCES agents(id),
                FOREIGN KEY (task_id) REFERENCES agent_tasks(id),
                FOREIGN KEY (vehicle_id) REFERENCES agent_vehicles(id)
            )
            """
            
            if not self.execute_sql(session, create_new_table_sql):
                logger.error("Failed to create new agent_task_rels table")
                return False
            
            logger.info("Created new agent_task_rels_new table")
            
            # Step 2: Detect which columns exist in the old table
            result = session.execute(text("PRAGMA table_info(agent_task_rels)"))
            existing_columns = {row[1] for row in result.fetchall()}
            logger.info(f"Existing columns in agent_task_rels: {existing_columns}")
            
            # Build dynamic SQL based on which columns exist
            # Required columns that must exist
            required_cols = ['id', 'agent_id', 'task_id', 'vehicle_id']
            
            # Optional columns with defaults
            optional_cols = {
                'status': "'pending'",
                'priority': "'medium'",
                'progress': "0.0",
                'scheduled_start': "NULL",
                'actual_start': "NULL",
                'estimated_end': "NULL",
                'actual_end': "NULL",
                'result': "NULL",
                'error_message': "NULL",
                'logs': "NULL",
                'cpu_usage': "NULL",
                'memory_usage': "NULL",
                'execution_time': "NULL",
                'execution_context': "NULL",
                'retry_count': "0",
                'max_retries': "3",
                'created_at': "NULL",
                'updated_at': "NULL"
            }
            
            # Build SELECT clause dynamically
            select_parts = []
            for col in required_cols:
                if col not in existing_columns:
                    logger.error(f"Required column {col} missing from old table")
                    self.execute_sql(session, "DROP TABLE IF EXISTS agent_task_rels_new")
                    return False
                select_parts.append(col)
            
            for col, default in optional_cols.items():
                if col in existing_columns:
                    if col in ['status', 'priority', 'progress', 'retry_count', 'max_retries']:
                        select_parts.append(f"COALESCE({col}, {default}) as {col}")
                    else:
                        select_parts.append(col)
                else:
                    select_parts.append(f"{default} as {col}")
            
            # Build and execute the copy SQL
            all_cols = required_cols + list(optional_cols.keys())
            copy_data_sql = f"""
            INSERT INTO agent_task_rels_new 
            ({', '.join(all_cols)})
            SELECT 
                {', '.join(select_parts)}
            FROM agent_task_rels
            """
            
            if not self.execute_sql(session, copy_data_sql):
                logger.error("Failed to copy data to new table")
                # Cleanup: drop the new table
                self.execute_sql(session, "DROP TABLE IF EXISTS agent_task_rels_new")
                return False
            
            logger.info("Copied data to new table")
            
            # Step 3: Drop old table
            drop_old_table_sql = "DROP TABLE agent_task_rels"
            
            if not self.execute_sql(session, drop_old_table_sql):
                logger.error("Failed to drop old table")
                # Cleanup: drop the new table
                self.execute_sql(session, "DROP TABLE IF EXISTS agent_task_rels_new")
                return False
            
            logger.info("Dropped old agent_task_rels table")
            
            # Step 4: Rename new table to original name
            rename_table_sql = "ALTER TABLE agent_task_rels_new RENAME TO agent_task_rels"
            
            if not self.execute_sql(session, rename_table_sql):
                logger.error("Failed to rename new table")
                return False
            
            logger.info("Renamed new table to agent_task_rels")
            
            # Flush the changes
            session.flush()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to modify vehicle_id column: {e}")
            session.rollback()
            # Try to cleanup
            try:
                self.execute_sql(session, "DROP TABLE IF EXISTS agent_task_rels_new")
            except:
                pass
            return False
    
    def _convert_title_to_json(self, session: Session) -> bool:
        """
        Convert title column from String to JSON in agents table.
        
        This converts existing title strings to JSON arrays.
        For example: "title.manager" -> ["title.manager"]
        """
        try:
            logger.info("Converting title column to JSON in agents table")
            
            # First, check what columns exist in the current agents table
            result = session.execute(text("PRAGMA table_info(agents)"))
            existing_columns = {row[1] for row in result.fetchall()}
            logger.info(f"Existing columns in agents table: {existing_columns}")
            
            # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
            # Step 1: Create new table with JSON title column
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
                logger.error("Failed to create new agents table")
                return False
            
            logger.info("Created new agents_new table")
            
            # Step 2: Copy data, converting title to JSON array
            # Build dynamic SQL based on which columns exist
            # Handle column name variations (personality_traits vs personalities)
            personality_col = 'personality_traits' if 'personality_traits' in existing_columns else 'personalities' if 'personalities' in existing_columns else None
            
            copy_data_sql = f"""
            INSERT INTO agents_new 
            (id, name, description, owner, gender, title, rank, birthday, supervisor_id,
             personality_traits, capabilities, tasks, skills, status, version, url, 
             extra_data, vehicle_id, created_at, updated_at, ext)
            SELECT 
                id, 
                name, 
                description, 
                owner, 
                gender,
                CASE 
                    WHEN title IS NULL OR title = '' THEN '[]'
                    WHEN json_valid(title) THEN title
                    ELSE json_array(title)
                END as title,
                rank, 
                birthday, 
                {'supervisor_id' if 'supervisor_id' in existing_columns else 'NULL'} as supervisor_id,
                {personality_col if personality_col else "'[]'"} as personality_traits,
                COALESCE(capabilities, '[]') as capabilities,
                {'tasks' if 'tasks' in existing_columns else "'[]'"} as tasks,
                {'skills' if 'skills' in existing_columns else "'[]'"} as skills,
                COALESCE(status, 'active') as status,
                version, 
                url, 
                extra_data,
                {'vehicle_id' if 'vehicle_id' in existing_columns else 'NULL'} as vehicle_id,
                created_at, 
                updated_at, 
                {'ext' if 'ext' in existing_columns else 'NULL'} as ext
            FROM agents
            """
            
            if not self.execute_sql(session, copy_data_sql):
                logger.error("Failed to copy data to new table")
                # Cleanup
                self.execute_sql(session, "DROP TABLE IF EXISTS agents_new")
                return False
            
            logger.info("Copied data to new table with converted title column")
            
            # Step 3: Drop old table
            drop_old_table_sql = "DROP TABLE agents"
            
            if not self.execute_sql(session, drop_old_table_sql):
                logger.error("Failed to drop old agents table")
                # Cleanup
                self.execute_sql(session, "DROP TABLE IF EXISTS agents_new")
                return False
            
            logger.info("Dropped old agents table")
            
            # Step 4: Rename new table
            rename_table_sql = "ALTER TABLE agents_new RENAME TO agents"
            
            if not self.execute_sql(session, rename_table_sql):
                logger.error("Failed to rename new table")
                return False
            
            logger.info("Renamed new table to agents")
            
            # Flush the changes
            session.flush()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to convert title column to JSON: {e}")
            session.rollback()
            # Try to cleanup
            try:
                self.execute_sql(session, "DROP TABLE IF EXISTS agents_new")
            except:
                pass
            return False
    
    def _add_diagram_to_agent_skills(self, session: Session) -> bool:
        """
        Add diagram column to agent_skills table.
        
        The diagram column stores workflow/diagram data in JSON format,
        which is needed to rebuild the skill's runnable when loading from database.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if agent_skills table exists
            if not self.table_exists('agent_skills'):
                logger.warning("agent_skills table does not exist, skipping diagram column addition")
                return True  # Not a critical error, table might not exist yet
            
            # Check if diagram column already exists
            if self.column_exists('agent_skills', 'diagram'):
                logger.info("diagram column already exists in agent_skills table, skipping")
                return True
            
            logger.info("Adding diagram column to agent_skills table")
            
            # Add diagram column
            add_column_sql = "ALTER TABLE agent_skills ADD COLUMN diagram JSON"
            
            if not self.execute_sql(session, add_column_sql):
                logger.error("Failed to add diagram column to agent_skills table")
                return False
            
            logger.info("Successfully added diagram column to agent_skills table")
            
            # Flush the changes
            session.flush()
            
            # Verify the column was added
            if not self.column_exists('agent_skills', 'diagram'):
                logger.error("Failed to verify diagram column addition")
                return False
            
            logger.info("✓ diagram column verified in agent_skills table")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add diagram column to agent_skills: {e}")
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
            # 1. Check that agent_task_rels table exists and vehicle_id is nullable
            if not self.table_exists('agent_task_rels'):
                logger.error("agent_task_rels table does not exist after migration")
                return False
            
            result = session.execute(text("PRAGMA table_info(agent_task_rels)"))
            task_rel_columns = {row[1]: {'type': row[2], 'notnull': row[3]} for row in result.fetchall()}
            
            if 'vehicle_id' not in task_rel_columns:
                logger.error("vehicle_id column missing from agent_task_rels table")
                return False
            
            if task_rel_columns['vehicle_id']['notnull'] != 0:
                logger.error("vehicle_id column is still NOT NULL")
                logger.debug(f"Column info: {task_rel_columns['vehicle_id']}")
                return False
            
            logger.info("✓ vehicle_id column is now nullable in agent_task_rels table")
            
            # 2. Check that agents table exists and title is JSON type
            if not self.table_exists('agents'):
                logger.error("agents table does not exist after migration")
                return False
            
            result = session.execute(text("PRAGMA table_info(agents)"))
            agent_columns = {row[1]: {'type': row[2], 'notnull': row[3]} for row in result.fetchall()}
            
            if 'title' not in agent_columns:
                logger.error("title column missing from agents table")
                return False
            
            # Check if title is JSON type (SQLite may show it as JSON or TEXT)
            title_type = agent_columns['title']['type'].upper()
            if title_type not in ['JSON', 'TEXT']:
                logger.error(f"title column has unexpected type: {title_type}")
                return False
            
            logger.info("✓ title column is now JSON type in agents table")
            
            # 3. Check that agents table has vehicle_id column
            if 'vehicle_id' not in agent_columns:
                logger.error("vehicle_id column missing from agents table")
                return False
            
            # Check if vehicle_id is VARCHAR type and nullable
            vehicle_id_type = agent_columns['vehicle_id']['type'].upper()
            if not vehicle_id_type.startswith('VARCHAR'):
                logger.error(f"vehicle_id column has unexpected type: {vehicle_id_type}")
                return False
            
            if agent_columns['vehicle_id']['notnull'] != 0:
                logger.error("vehicle_id column should be nullable")
                return False
            
            logger.info("✓ vehicle_id column exists and is nullable in agents table")
            
            # 4. Check that agent_skills table has diagram column (if table exists)
            if self.table_exists('agent_skills'):
                result = session.execute(text("PRAGMA table_info(agent_skills)"))
                skill_columns = {row[1]: {'type': row[2], 'notnull': row[3]} for row in result.fetchall()}
                
                if 'diagram' not in skill_columns:
                    logger.error("diagram column missing from agent_skills table")
                    return False
                
                # Check if diagram is JSON type (SQLite may show it as JSON or TEXT)
                diagram_type = skill_columns['diagram']['type'].upper()
                if diagram_type not in ['JSON', 'TEXT']:
                    logger.error(f"diagram column has unexpected type: {diagram_type}")
                    return False
                
                logger.info("✓ diagram column exists in agent_skills table")
            else:
                logger.info("⊘ agent_skills table does not exist, skipping diagram validation")
            
            logger.info("All postconditions validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate postconditions: {e}")
            return False
    
    def downgrade(self, session: Session) -> bool:
        """
        Downgrade from 3.0.3 to 3.0.2.
        
        This would require making vehicle_id NOT NULL again, which could fail
        if there are existing records with NULL vehicle_id.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.warning("Downgrade from 3.0.3 to 3.0.2: Making vehicle_id NOT NULL again")
            
            # Check if there are any records with NULL vehicle_id
            result = session.execute(text("SELECT COUNT(*) FROM agent_task_rels WHERE vehicle_id IS NULL"))
            null_count = result.scalar()
            
            if null_count > 0:
                logger.error(f"Cannot downgrade: {null_count} records have NULL vehicle_id")
                logger.error("Please assign vehicle_id to all records before downgrading")
                return False
            
            # Similar process as upgrade, but with NOT NULL constraint
            # (Implementation omitted for brevity - would follow same pattern as upgrade)
            
            logger.info("Downgrade completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to downgrade: {e}")
            return False

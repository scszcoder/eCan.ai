"""
Migration from version 2.0.0 to 3.0.0

This migration adds the agent management system with:
- agent_id column to chats table
- agent_vehicles table
- agent_orgs table (renamed from orgs)
- Association tables for complex relationships
"""

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..base_migration import BaseMigration
from utils.logger_helper import logger_helper as logger


class Migration200To300(BaseMigration):
    """Migration from 2.0.0 to 3.0.0"""
    
    @property
    def version(self) -> str:
        return "3.0.0"
    
    @property
    def previous_version(self) -> str:
        return "2.0.0"
    
    @property
    def description(self) -> str:
        return "Add agent management system with vehicles, organizations and association tables"
    
    def upgrade(self, session: Session) -> bool:
        """
        Perform the full migration to 3.0.0.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Step 1: Add agent_id to chats table
            if not self._add_agent_id_to_chats(session):
                return False
            
            # Step 2: Create agent_vehicles table
            if not self._create_agent_vehicles_table(session):
                return False
            
            # Step 3: Create agent_orgs table
            if not self._create_agent_orgs_table(session):
                return False
            
            # Step 4: Create association tables
            if not self._create_association_tables(session):
                return False
            
            logger.info("Successfully completed migration to 3.0.0")
            return True
            
        except Exception as e:
            logger.error(f"Failed to migrate to 3.0.0: {e}")
            return False
    
    def _add_agent_id_to_chats(self, session: Session) -> bool:
        """Add agent_id column to chats table"""
        try:
            if self.column_exists('chats', 'agent_id'):
                logger.info("Column agent_id already exists in chats table")
                return True
            
            # Use simpler ALTER TABLE without foreign key constraint to avoid locking issues
            sql = "ALTER TABLE chats ADD COLUMN agent_id VARCHAR(64)"
            
            # Execute with retry logic for better reliability
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if not self.execute_sql(session, sql):
                        if attempt < max_retries - 1:
                            logger.warning(f"Failed to add agent_id column, retrying... (attempt {attempt + 1})")
                            session.rollback()
                            import time
                            time.sleep(1)  # Wait 1 second before retry
                            continue
                        return False
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Exception adding agent_id column, retrying... (attempt {attempt + 1}): {e}")
                        session.rollback()
                        import time
                        time.sleep(1)
                        continue
                    raise e
            
            # Flush the change but don't commit yet (let the migration manager handle commits)
            session.flush()
            
            logger.info("Added agent_id column to chats table")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add agent_id column to chats table: {e}")
            session.rollback()
            return False
    
    def _create_agent_vehicles_table(self, session: Session) -> bool:
        """Create agent_vehicles table"""
        try:
            if self.table_exists('agent_vehicles'):
                logger.info("Table agent_vehicles already exists")
                return True
            
            sql = """
            CREATE TABLE agent_vehicles (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                vehicle_type VARCHAR(50) NOT NULL,
                description TEXT,
                capabilities JSON,
                status VARCHAR(32) DEFAULT 'active',
                config JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            
            if not self.execute_sql(session, sql):
                return False
            
            logger.info("Created agent_vehicles table")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create agent_vehicles table: {e}")
            return False
    
    def _create_agent_orgs_table(self, session: Session) -> bool:
        """Create agent_orgs table"""
        try:
            if self.table_exists('agent_orgs'):
                logger.info("Table agent_orgs already exists")
                return True
            
            sql = """
            CREATE TABLE agent_orgs (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(128) NOT NULL,
                description TEXT,
                parent_id VARCHAR(64) REFERENCES agent_orgs(id),
                org_type VARCHAR(64) DEFAULT 'department',
                level INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                status VARCHAR(32) DEFAULT 'active',
                settings JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                ext TEXT
            )
            """
            
            if not self.execute_sql(session, sql):
                return False
            
            logger.info("Created agent_orgs table")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create agent_orgs table: {e}")
            return False
    
    def _create_association_tables(self, session: Session) -> bool:
        """Create all association tables"""
        association_tables = [
            {
                'name': 'agent_org_rels',
                'sql': """
                CREATE TABLE agent_org_rels (
                    id VARCHAR(64) PRIMARY KEY,
                    agent_id VARCHAR(64) NOT NULL,
                    org_id VARCHAR(64) NOT NULL,
                    role VARCHAR(64) DEFAULT 'member',
                    status VARCHAR(32) DEFAULT 'active',
                    join_date DATETIME,
                    leave_date DATETIME,
                    permissions JSON,
                    access_level VARCHAR(32) DEFAULT 'read',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
                    FOREIGN KEY (org_id) REFERENCES agent_orgs(id) ON DELETE CASCADE,
                    UNIQUE(agent_id, org_id)
                )
                """
            },
            {
                'name': 'agent_skill_rels',
                'sql': """
                CREATE TABLE agent_skill_rels (
                    id VARCHAR(64) PRIMARY KEY,
                    agent_id VARCHAR(64) NOT NULL,
                    skill_id VARCHAR(64) NOT NULL,
                    proficiency_level VARCHAR(32) DEFAULT 'beginner',
                    experience_points INTEGER DEFAULT 0,
                    certification_level VARCHAR(32),
                    usage_count INTEGER DEFAULT 0,
                    success_rate FLOAT DEFAULT 0.0,
                    last_used DATETIME,
                    status VARCHAR(32) DEFAULT 'active',
                    is_favorite BOOLEAN DEFAULT FALSE,
                    priority INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
                    FOREIGN KEY (skill_id) REFERENCES agent_skills(id) ON DELETE CASCADE,
                    UNIQUE(agent_id, skill_id)
                )
                """
            },
            {
                'name': 'agent_task_rels',
                'sql': """
                CREATE TABLE agent_task_rels (
                    id VARCHAR(64) PRIMARY KEY,
                    agent_id VARCHAR(64) NOT NULL,
                    task_id VARCHAR(64) NOT NULL,
                    vehicle_id VARCHAR(64) NOT NULL,
                    status VARCHAR(32) DEFAULT 'pending',
                    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    started_at DATETIME,
                    completed_at DATETIME,
                    priority INTEGER DEFAULT 0,
                    progress REAL DEFAULT 0.0,
                    result JSON,
                    error_message TEXT,
                    estimated_duration INTEGER,
                    actual_duration INTEGER,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (agent_id) REFERENCES agents(id),
                    FOREIGN KEY (task_id) REFERENCES agent_tasks(id),
                    FOREIGN KEY (vehicle_id) REFERENCES agent_vehicles(id)
                )
                """
            },
            {
                'name': 'agent_skill_tool_rels',
                'sql': """
                CREATE TABLE agent_skill_tool_rels (
                    id VARCHAR(64) PRIMARY KEY,
                    skill_id VARCHAR(64) NOT NULL,
                    tool_id VARCHAR(64) NOT NULL,
                    is_required BOOLEAN DEFAULT FALSE,
                    proficiency_required VARCHAR(32) DEFAULT 'beginner',
                    usage_frequency VARCHAR(32) DEFAULT 'occasional',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (skill_id) REFERENCES agent_skills(id),
                    FOREIGN KEY (tool_id) REFERENCES agent_tools(id),
                    UNIQUE(skill_id, tool_id)
                )
                """
            },
            {
                'name': 'agent_skill_knowledge_rels',
                'sql': """
                CREATE TABLE agent_skill_knowledge_rels (
                    id VARCHAR(64) PRIMARY KEY,
                    skill_id VARCHAR(64) NOT NULL,
                    knowledge_id VARCHAR(64) NOT NULL,
                    relevance_score REAL DEFAULT 0.5,
                    is_prerequisite BOOLEAN DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (skill_id) REFERENCES agent_skills(id),
                    FOREIGN KEY (knowledge_id) REFERENCES agent_knowledges(id),
                    UNIQUE(skill_id, knowledge_id)
                )
                """
            },
            {
                'name': 'agent_task_skill_rels',
                'sql': """
                CREATE TABLE agent_task_skill_rels (
                    id VARCHAR(64) PRIMARY KEY,
                    task_id VARCHAR(64) NOT NULL,
                    skill_id VARCHAR(64) NOT NULL,
                    required_proficiency VARCHAR(32) DEFAULT 'beginner',
                    importance VARCHAR(32) DEFAULT 'medium',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES agent_tasks(id),
                    FOREIGN KEY (skill_id) REFERENCES agent_skills(id),
                    UNIQUE(task_id, skill_id)
                )
                """
            }
        ]
        
        try:
            for table_info in association_tables:
                table_name = table_info['name']
                
                if self.table_exists(table_name):
                    logger.info(f"Table {table_name} already exists")
                    continue
                
                if not self.execute_sql(session, table_info['sql']):
                    logger.error(f"Failed to create table {table_name}")
                    return False
                
                logger.info(f"Created table {table_name}")
            
            logger.info("All association tables created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create association tables: {e}")
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
        
        # Check agent_id column in chats using direct SQL to avoid caching issues
        try:
            from sqlalchemy import text
            result = session.execute(text("PRAGMA table_info(chats)"))
            columns = [row[1] for row in result.fetchall()]
            agent_id_exists = 'agent_id' in columns
            
            if not agent_id_exists:
                logger.error("agent_id column missing from chats table")
                logger.debug(f"Available columns: {columns}")
                return False
        except Exception as e:
            logger.error(f"Failed to check agent_id column: {e}")
            return False
        
        # Check required tables
        required_tables = [
            'agent_vehicles', 'agent_orgs', 'agent_org_rels', 
            'agent_skill_rels', 'agent_task_rels', 'agent_skill_tool_rels',
            'agent_skill_knowledge_rels', 'agent_task_skill_rels'
        ]
        
        for table_name in required_tables:
            if not self.table_exists(table_name):
                logger.error(f"Required table {table_name} is missing")
                return False
        
        logger.info("All postconditions validated successfully")
        return True
    
    def downgrade(self, session: Session) -> bool:
        """
        Downgrade from 3.0.0 to 2.0.0 (limited support).
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.warning("Downgrade from 3.0.0 to 2.0.0 has limited support")
        
        # We can't easily remove the agent_id column from chats due to SQLite limitations
        # But we can drop the new tables
        
        tables_to_drop = [
            'agent_task_skill_rels', 'agent_skill_knowledge_rels', 'agent_skill_tool_rels',
            'agent_task_rels', 'agent_skill_rels', 'agent_org_rels',
            'agent_orgs', 'agent_vehicles'
        ]
        
        try:
            for table_name in tables_to_drop:
                if self.table_exists(table_name):
                    sql = f"DROP TABLE {table_name}"
                    if not self.execute_sql(session, sql):
                        logger.warning(f"Failed to drop table {table_name}")
                    else:
                        logger.info(f"Dropped table {table_name}")
            
            logger.info("Downgrade completed (agent_id column in chats table preserved)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to downgrade from 3.0.0: {e}")
            return False

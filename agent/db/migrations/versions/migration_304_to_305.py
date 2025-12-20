"""
Migration from version 3.0.4 to 3.0.5
Add avatar support for agents and create avatar_resources table
"""

from sqlalchemy import text
from ..base_migration import BaseMigration
import logging

logger = logging.getLogger(__name__)


class Migration_304_to_305(BaseMigration):
    """Migration to add avatar support"""
    
    @property
    def version(self) -> str:
        """Target version"""
        return "3.0.5"
    
    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.0.4"
    
    @property
    def description(self) -> str:
        """Migration description"""
        return "Add avatar fields to agents table and create avatar_resources table"
    
    def upgrade(self, session):
        """Add avatar fields to agents table and create avatar_resources table"""
        logger.info("[Migration 3.0.4→3.0.5] Starting upgrade...")
        
        try:
            with self.engine.connect() as conn:
                # Check if avatar fields already exist
                result = conn.execute(text("PRAGMA table_info(agents)"))
                columns = [row[1] for row in result.fetchall()]
                
                # Add avatar_resource_id foreign key to agents table
                if 'avatar_resource_id' not in columns:
                    logger.info("[Migration] Adding avatar_resource_id to agents table...")
                    conn.execute(text("""
                        ALTER TABLE agents ADD COLUMN avatar_resource_id VARCHAR(64)
                    """))
                    conn.commit()
                
                # Check if avatar_resources table exists
                result = conn.execute(text("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='avatar_resources'
                """))
                table_exists = result.fetchone() is not None
                
                if not table_exists:
                    # Create avatar_resources table
                    logger.info("[Migration] Creating avatar_resources table...")
                    conn.execute(text("""
                        CREATE TABLE avatar_resources (
                            id VARCHAR(64) PRIMARY KEY,
                            resource_type VARCHAR(32) NOT NULL,
                            name VARCHAR(128),
                            description VARCHAR(512),
                            image_path VARCHAR(512),
                            video_path VARCHAR(512),
                            image_hash VARCHAR(64),
                            video_hash VARCHAR(64),
                            cloud_image_url VARCHAR(512),
                            cloud_video_url VARCHAR(512),
                            cloud_image_key VARCHAR(512),
                            cloud_video_key VARCHAR(512),
                            cloud_synced INTEGER DEFAULT 0,
                            avatar_metadata TEXT,
                            usage_count INTEGER DEFAULT 0,
                            last_used_at TIMESTAMP,
                            owner VARCHAR(128),
                            is_public INTEGER DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    conn.commit()
                    
                    # Create indexes for better query performance
                    logger.info("[Migration] Creating indexes on avatar_resources...")
                    conn.execute(text("""
                        CREATE INDEX idx_avatar_resources_owner 
                        ON avatar_resources(owner)
                    """))
                    conn.execute(text("""
                        CREATE INDEX idx_avatar_resources_type 
                        ON avatar_resources(resource_type)
                    """))
                    conn.execute(text("""
                        CREATE INDEX idx_avatar_resources_hash 
                        ON avatar_resources(image_hash)
                    """))
                    conn.commit()
                else:
                    logger.info("[Migration] avatar_resources table already exists, skipping creation")
                
            logger.info("[Migration 3.0.4→3.0.5] ✅ Upgrade completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.4→3.0.5] ❌ Upgrade failed: {e}", exc_info=True)
            raise
    
    def downgrade(self, session):
        """Remove avatar support (partial - SQLite limitation)"""
        logger.info("[Migration 3.0.5→3.0.4] Starting downgrade...")
        
        try:
            with self.engine.connect() as conn:
                # Drop avatar_resources table
                logger.info("[Migration] Dropping avatar_resources table...")
                conn.execute(text("DROP TABLE IF EXISTS avatar_resources"))
                conn.commit()
                
                # Note: SQLite doesn't support DROP COLUMN directly
                # Avatar fields in agents table will remain but won't be used
                logger.warning(
                    "[Migration] SQLite doesn't support DROP COLUMN. "
                    "Avatar fields in agents table will remain but won't be used."
                )
                
            logger.info("[Migration 3.0.5→3.0.4] ✅ Downgrade completed")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.5→3.0.4] ❌ Downgrade failed: {e}", exc_info=True)
            raise
    
    def validate_postconditions(self, session):
        """Validate the migration was successful"""
        logger.info("[Migration 3.0.4→3.0.5] Validating migration...")
        
        try:
            with self.engine.connect() as conn:
                # Check agents table has avatar_resource_id field
                result = conn.execute(text("PRAGMA table_info(agents)"))
                columns = [row[1] for row in result.fetchall()]
                
                if 'avatar_resource_id' not in columns:
                    logger.error("[Migration] Validation failed: Missing column avatar_resource_id in agents table")
                    return False
                
                # Check avatar_resources table exists
                result = conn.execute(text("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='avatar_resources'
                """))
                if not result.fetchone():
                    logger.error("[Migration] Validation failed: avatar_resources table not found")
                    return False
                
                # Check indexes exist
                result = conn.execute(text("""
                    SELECT name FROM sqlite_master 
                    WHERE type='index' AND tbl_name='avatar_resources'
                """))
                indexes = [row[0] for row in result.fetchall()]
                
                expected_indexes = ['idx_avatar_resources_owner', 'idx_avatar_resources_type', 'idx_avatar_resources_hash']
                for idx in expected_indexes:
                    if idx not in indexes:
                        logger.warning(f"[Migration] Index {idx} not found (non-critical)")
                
            logger.info("[Migration 3.0.4→3.0.5] ✅ Validation successful")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.4→3.0.5] ❌ Validation failed: {e}", exc_info=True)
            return False

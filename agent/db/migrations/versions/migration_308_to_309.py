"""
Migration from version 3.0.8 to 3.0.9
Minor updates and fixes
"""

from sqlalchemy import text
from ..base_migration import BaseMigration

from utils.logger_helper import logger_helper as logger


class Migration_308_to_309(BaseMigration):
    """Migration from 3.0.8 to 3.0.9"""
    
    @property
    def version(self) -> str:
        """Target version"""
        return "3.0.9"
    
    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.0.8"
    
    @property
    def description(self) -> str:
        """Migration description"""
        return "Minor updates and optimizations for 3.0.9"
    
    def upgrade(self, session):
        """Apply minor updates"""
        logger.info("[Migration 3.0.8→3.0.9] Starting upgrade...")
        
        try:
            # No schema changes for this minor version
            # This migration serves as a placeholder for any minor updates
            
            logger.info("[Migration 3.0.8→3.0.9] ✅ Upgrade completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.8→3.0.9] ❌ Upgrade failed: {e}", exc_info=True)
            raise
    
    def downgrade(self, session):
        """Downgrade (no changes to revert)"""
        logger.info("[Migration 3.0.9→3.0.8] Starting downgrade...")
        logger.info("[Migration] No changes to revert for 3.0.9")
        return True
    
    def validate_preconditions(self, session):
        """Validate preconditions before migration"""
        logger.info("[Migration 3.0.8→3.0.9] Validating preconditions...")
        # No specific preconditions needed
        logger.info("[Migration 3.0.8→3.0.9] ✅ Preconditions validated")
        return True
    
    def validate_postconditions(self, session):
        """Validate the migration was successful"""
        logger.info("[Migration 3.0.8→3.0.9] Validating migration...")
        # No specific postconditions needed
        logger.info("[Migration 3.0.8→3.0.9] ✅ Validation successful")
        return True

#!/usr/bin/env python3
"""
Database Migration CLI Tool

This tool provides command-line interface for managing database migrations.
It can create new migration templates, run migrations, and check migration status.
"""

import os
import sys
import argparse
from datetime import datetime
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from agent.db.core import get_engine, ECAN_BASE_DB
from agent.db.migrations import MigrationManager
from utils.logger_helper import logger_helper as logger


def create_migration_template(from_version: str, to_version: str, description: str) -> str:
    """
    Create a new migration template file.
    
    Args:
        from_version: Source version (e.g., "3.0.0")
        to_version: Target version (e.g., "3.1.0")
        description: Migration description
        
    Returns:
        str: Path to the created migration file
    """
    # Generate filename
    from_clean = from_version.replace('.', '')
    to_clean = to_version.replace('.', '')
    filename = f"migration_{from_clean}_to_{to_clean}.py"
    
    # Generate class name
    class_name = f"Migration{from_clean}To{to_clean}"
    
    # Create template content
    template = f'''"""
Migration from version {from_version} to {to_version}

{description}
"""

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..base_migration import BaseMigration
from utils.logger_helper import logger_helper as logger


class {class_name}(BaseMigration):
    """Migration from {from_version} to {to_version}"""
    
    @property
    def version(self) -> str:
        return "{to_version}"
    
    @property
    def previous_version(self) -> str:
        return "{from_version}"
    
    @property
    def description(self) -> str:
        return "{description}"
    
    def upgrade(self, session: Session) -> bool:
        """
        Perform the database upgrade.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # TODO: Implement your migration logic here
            # Example:
            # if not self.table_exists('new_table'):
            #     sql = \"\"\"
            #     CREATE TABLE new_table (
            #         id VARCHAR(64) PRIMARY KEY,
            #         name VARCHAR(100) NOT NULL,
            #         created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            #     )
            #     \"\"\"
            #     if not self.execute_sql(session, sql):
            #         return False
            
            logger.info("Migration {to_version} upgrade completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upgrade to {to_version}: {{e}}")
            return False
    
    def validate_postconditions(self, session: Session) -> bool:
        """
        Validate that the migration was applied successfully.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if validation passes, False otherwise
        """
        # TODO: Implement validation logic
        # Example:
        # return self.table_exists('new_table')
        
        return True
    
    def downgrade(self, session: Session) -> bool:
        """
        Perform the database downgrade (optional).
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # TODO: Implement downgrade logic if needed
            logger.warning("Downgrade from {to_version} to {from_version} not implemented")
            return True
            
        except Exception as e:
            logger.error(f"Failed to downgrade from {to_version}: {{e}}")
            return False
'''
    
    # Write to file
    versions_dir = os.path.join(os.path.dirname(__file__), 'versions')
    file_path = os.path.join(versions_dir, filename)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(template)
    
    return file_path


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description='Database Migration Management Tool')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create migration command
    create_parser = subparsers.add_parser('create', help='Create a new migration template')
    create_parser.add_argument('from_version', help='Source version (e.g., 3.0.0)')
    create_parser.add_argument('to_version', help='Target version (e.g., 3.1.0)')
    create_parser.add_argument('description', help='Migration description')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show migration status')
    status_parser.add_argument('--db-path', help='Database path', default=ECAN_BASE_DB)
    
    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Run migrations')
    migrate_parser.add_argument('--db-path', help='Database path', default=ECAN_BASE_DB)
    migrate_parser.add_argument('--target', help='Target version (default: latest)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available migrations')
    list_parser.add_argument('--db-path', help='Database path', default=ECAN_BASE_DB)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'create':
            file_path = create_migration_template(
                args.from_version, 
                args.to_version, 
                args.description
            )
            print(f"[OK] Created migration template: {file_path}")
            print(f"📝 Please edit the file to implement your migration logic")
            
        elif args.command == 'status':
            engine = get_engine(args.db_path)
            manager = MigrationManager(engine)
            status = manager.get_migration_status()
            
            print(f"📊 Migration Status")
            print(f"Current Version: {status['current_version']}")
            print(f"Latest Version:  {status['latest_version']}")
            print(f"Up to Date:      {'[OK] Yes' if status['is_up_to_date'] else '[ERROR] No'}")
            print(f"Total Migrations: {status['total_migrations']}")
            
        elif args.command == 'migrate':
            engine = get_engine(args.db_path)
            manager = MigrationManager(engine)
            
            if args.target:
                success = manager.migrate_to_version(args.target)
                action = f"migrate to {args.target}"
            else:
                success = manager.migrate_to_latest()
                action = "migrate to latest version"
            
            if success:
                print(f"[OK] Successfully completed: {action}")
            else:
                print(f"[ERROR] Failed to {action}")
                sys.exit(1)
                
        elif args.command == 'list':
            engine = get_engine(args.db_path)
            manager = MigrationManager(engine)
            migrations = manager.get_available_migrations()
            
            print(f"📋 Available Migrations ({len(migrations)} total)")
            print("-" * 80)
            
            for migration in migrations:
                print(f"Version: {migration['version']}")
                print(f"From:    {migration['previous_version']}")
                print(f"Desc:    {migration['description']}")
                print(f"Class:   {migration['class_name']}")
                print("-" * 40)
                
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

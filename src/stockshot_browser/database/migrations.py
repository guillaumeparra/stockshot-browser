"""
Database migration utilities for Stockshot Browser.
"""

import logging
from sqlalchemy import text, inspect
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)


def migrate_database(engine):
    """
    Apply database migrations to update schema.
    
    Args:
        engine: SQLAlchemy engine instance
    """
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        
        # Check if thumbnails table exists
        if 'thumbnails' in inspector.get_table_names():
            # Get existing columns
            columns = [col['name'] for col in inspector.get_columns('thumbnails')]
            
            # Add extra_data column if it doesn't exist
            if 'extra_data' not in columns:
                try:
                    conn.execute(text("""
                        ALTER TABLE thumbnails 
                        ADD COLUMN extra_data TEXT
                    """))
                    conn.commit()
                except OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
                    else:
                        logger.debug("Column 'extra_data' already exists")
        

def check_schema_version(engine):
    """
    Check and update database schema version.
    
    Args:
        engine: SQLAlchemy engine instance
        
    Returns:
        Current schema version
    """
    with engine.connect() as conn:
        # Check if schema_version table exists
        inspector = inspect(engine)
        if 'schema_version' not in inspector.get_table_names():
            # Create schema version table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            # Insert initial version
            conn.execute(text("INSERT INTO schema_version (version) VALUES (1)"))
            conn.commit()
            return 1
        
        # Get current version
        result = conn.execute(text("SELECT MAX(version) FROM schema_version"))
        version = result.scalar() or 0
        
        return version


def apply_migrations(engine):
    """
    Apply all pending migrations based on schema version.
    
    Args:
        engine: SQLAlchemy engine instance
    """
    current_version = check_schema_version(engine)
    
    migrations = {
        1: migrate_v1_to_v2,  # Add extra_data column to thumbnails
        2: migrate_v2_to_v3,  # Add last_accessed to entities and category to metadata
    }
    
    for version, migration_func in sorted(migrations.items()):
        if version > current_version:
            migration_func(engine)
            
            # Update schema version
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO schema_version (version) VALUES (:version)"
                ), {"version": version})
                conn.commit()
            
    

def migrate_v1_to_v2(engine):
    """
    Migration from v1 to v2: Add extra_data column to thumbnails table.
    """
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                ALTER TABLE thumbnails 
                ADD COLUMN extra_data TEXT
            """))
            conn.commit()
        except OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.debug("Column 'extra_data' already exists")
            else:
                raise


def migrate_v2_to_v3(engine):
    """
    Migration from v2 to v3: Add last_accessed column to entities table and category column to metadata table.
    """
    with engine.connect() as conn:
        inspector = inspect(engine)
        
        # Add last_accessed column to entities table
        if 'entities' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('entities')]
            
            if 'last_accessed' not in columns:
                try:
                    conn.execute(text("""
                        ALTER TABLE entities
                        ADD COLUMN last_accessed TIMESTAMP
                    """))
                    conn.commit()
                except OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.debug("Column 'last_accessed' already exists")
                    else:
                        raise
        
        # Add category column to metadata table
        if 'metadata' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('metadata')]
            
            if 'category' not in columns:
                try:
                    conn.execute(text("""
                        ALTER TABLE metadata
                        ADD COLUMN category VARCHAR(100)
                    """))
                    # Create index for category column
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_metadata_category ON metadata (category)
                    """))
                    conn.commit()
                except OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.debug("Column 'category' already exists")
                    else:
                        raise
"""
Multi-Database Manager for Stockshot Browser.

Manages multiple database instances based on path context.
"""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Generator, Optional, Any
from sqlalchemy.orm import Session

from .connection import DatabaseManager
from ..core.path_context_manager import PathContextManager, ContextType

logger = logging.getLogger(__name__)


class MultiDatabaseManager:
    """Manages multiple database instances based on path context."""
    
    def __init__(self, config_manager, path_context_manager: PathContextManager):
        self.config_manager = config_manager
        self.path_context_manager = path_context_manager
        
        # Dictionary to store database managers by context type
        self._database_managers: Dict[ContextType, DatabaseManager] = {}
        
        # Current context for compatibility with single-database code
        self._current_context: ContextType = ContextType.GENERAL
        self._current_path: Optional[str] = None
        
    
    def initialize_databases(self) -> None:
        """Initialize all database contexts."""
        # Get paths for each context
        contexts_to_init = [
            (ContextType.GENERAL, self.path_context_manager.get_database_path(ContextType.GENERAL)),
            (ContextType.USER, self.path_context_manager.get_database_path(ContextType.USER)),
            (ContextType.PROJECT, self.path_context_manager.get_database_path(ContextType.PROJECT))
        ]
        
        for context_type, db_path in contexts_to_init:
            if db_path:
                try:
                    # Handle migration from old database structure
                    db_path_obj = Path(db_path)
                    old_db_file = db_path_obj  # Old structure: path is the database file directly
                    new_db_dir = db_path_obj   # New structure: path is the directory containing stockshot.db
                    new_db_file = new_db_dir / "stockshot.db"
                    
                    # Check if we need to migrate from old structure
                    if old_db_file.is_file() and not new_db_dir.is_dir():
                        # Rename the old database file to a temporary name
                        temp_db_file = old_db_file.parent / f"{old_db_file.name}.old"
                        old_db_file.rename(temp_db_file)
                        
                        # Create the new directory structure
                        new_db_dir.mkdir(parents=True, exist_ok=True)
                        
                        # Move the database to the new location
                        temp_db_file.rename(new_db_file)
                    else:
                        # Normal case - ensure directory exists
                        new_db_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Initialize database manager for this context
                    db_manager = DatabaseManager(str(new_db_file))
                    db_manager.initialize_database()
                    
                    self._database_managers[context_type] = db_manager
                    
                except Exception as e:
                    # Don't fail completely - just skip this context
                    continue
        
        # Ensure we have at least the general database
        if ContextType.GENERAL not in self._database_managers:
            raise RuntimeError("Failed to initialize general database - cannot proceed")
        
    
    def set_current_path(self, path: str) -> None:
        """Set the current path context for database operations."""
        if path != self._current_path:
            self._current_path = path
            self._current_context = self.path_context_manager.get_context_for_path(path)
    
    def get_current_context(self) -> ContextType:
        """Get the current database context."""
        return self._current_context
    
    def get_database_manager(self, context: Optional[ContextType] = None) -> DatabaseManager:
        """Get the database manager for the specified or current context."""
        target_context = context or self._current_context
        
        if target_context not in self._database_managers:
            # Fallback to general database if specific context not available
            target_context = ContextType.GENERAL
            
            if target_context not in self._database_managers:
                raise RuntimeError("No database contexts available")
        
        return self._database_managers[target_context]
    
    @contextmanager
    def get_session(self, context: Optional[ContextType] = None, path: Optional[str] = None, for_tags: bool = False) -> Generator[Session, None, None]:
        """Get database session for the specified context or current path.
        
        Args:
            context: Database context type
            path: Path to determine context from
            for_tags: If True, uses tag session pool for higher concurrency
        """
        # Determine context from path if provided
        if path:
            target_context = self.path_context_manager.get_context_for_path(path)
        else:
            target_context = context or self._current_context
        
        db_manager = self.get_database_manager(target_context)
        
        with db_manager.get_session(for_tags=for_tags) as session:
            yield session
    
    @contextmanager
    def get_session_for_path(self, path: str, for_tags: bool = False) -> Generator[Session, None, None]:
        """Get database session for a specific path.
        
        Args:
            path: Path to get session for
            for_tags: If True, uses tag session pool for higher concurrency
        """
        context = self.path_context_manager.get_context_for_path(path)
        db_manager = self.get_database_manager(context)
        
        with db_manager.get_session(for_tags=for_tags) as session:
            yield session
    
    def get_database_info(self, context: Optional[ContextType] = None) -> Dict[str, Any]:
        """Get database information for all or specific context."""
        if context:
            if context in self._database_managers:
                return {
                    context.value: self._database_managers[context].get_database_info()
                }
            else:
                return {context.value: {"status": "not_initialized"}}
        
        # Return info for all contexts
        info = {}
        for ctx_type, db_manager in self._database_managers.items():
            info[ctx_type.value] = db_manager.get_database_info()
        
        # Add info for contexts that weren't initialized
        all_contexts = [ContextType.GENERAL, ContextType.USER, ContextType.PROJECT]
        for ctx_type in all_contexts:
            if ctx_type not in info:
                info[ctx_type.value] = {"status": "not_initialized"}
        
        return info
    
    def test_connection(self, context: Optional[ContextType] = None) -> bool:
        """Test database connection for specific or all contexts."""
        if context:
            if context in self._database_managers:
                return self._database_managers[context].test_connection()
            return False
        
        # Test all connections
        results = {}
        for ctx_type, db_manager in self._database_managers.items():
            results[ctx_type.value] = db_manager.test_connection()
        
        # Return True if at least general database is working
        return results.get(ContextType.GENERAL.value, False)
    
    def create_backup(self, context: Optional[ContextType] = None, backup_path: Optional[str] = None) -> Dict[str, Path]:
        """Create backup for specific or all database contexts."""
        backups = {}
        
        if context:
            if context in self._database_managers:
                backup_file = self._database_managers[context].create_backup(backup_path)
                backups[context.value] = backup_file
        else:
            # Backup all contexts
            for ctx_type, db_manager in self._database_managers.items():
                try:
                    ctx_backup_path = None
                    if backup_path:
                        # Create context-specific backup paths
                        backup_base = Path(backup_path)
                        ctx_backup_path = str(backup_base.parent / f"{backup_base.stem}_{ctx_type.value}{backup_base.suffix}")
                    
                    backup_file = db_manager.create_backup(ctx_backup_path)
                    backups[ctx_type.value] = backup_file
                except Exception as e:
                    backups[ctx_type.value] = None
        
        return backups
    
    def vacuum_database(self, context: Optional[ContextType] = None) -> None:
        """Vacuum database for specific or all contexts."""
        if context:
            if context in self._database_managers:
                self._database_managers[context].vacuum_database()
        else:
            # Vacuum all contexts
            for ctx_type, db_manager in self._database_managers.items():
                try:
                    db_manager.vacuum_database()
                except Exception as e:
                    logger.error(f"Failed to vacuum {ctx_type.value} database: {e}")
    
    def close(self) -> None:
        """Close all database connections."""
        for ctx_type, db_manager in self._database_managers.items():
            try:
                db_manager.close()
            except Exception as e:
                logger.error(f"Error closing {ctx_type.value} database: {e}")
        
        self._database_managers.clear()
    
    def reload_configuration(self) -> None:
        """Reload configuration and reinitialize databases if needed."""
        
        # Reload path context manager configuration
        self.path_context_manager.reload_configuration()
        
        # Check if we need to initialize new databases
        all_contexts = [ContextType.GENERAL, ContextType.USER, ContextType.PROJECT]
        
        for context_type in all_contexts:
            if context_type not in self._database_managers:
                db_path = self.path_context_manager.get_database_path(context_type)
                if db_path:
                    try:
                        db_path_obj = Path(db_path)
                        db_path_obj.mkdir(parents=True, exist_ok=True)
                        db_file_path = db_path_obj / "stockshot.db"
                        
                        db_manager = DatabaseManager(str(db_file_path))
                        db_manager.initialize_database()
                        
                        self._database_managers[context_type] = db_manager
                        
                    except Exception as e:
                        logger.error(f"Failed to initialize new {context_type.value} database: {e}")
        
    
    # Compatibility methods for existing code that expects a single database manager
    def initialize_database(self) -> None:
        """Compatibility method - initializes all databases."""
        self.initialize_databases()
    
    def setup_auto_backup(self, interval_hours: int = 24, max_backups: int = 7) -> None:
        """Setup automatic backups for all database contexts."""
        for ctx_type, db_manager in self._database_managers.items():
            try:
                db_manager.setup_auto_backup(interval_hours, max_backups)
            except Exception as e:
                logger.error(f"Failed to setup auto-backup for {ctx_type.value} database: {e}")
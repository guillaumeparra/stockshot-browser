"""
Path Context Manager for Stockshot Browser.

Determines the appropriate database and thumbnail context based on the current path.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ContextType(Enum):
    """Types of storage contexts."""
    GENERAL = "general"  # Default context - uses gen_* paths
    USER = "user"        # User context - uses user_* paths
    PROJECT = "project"  # Project context - uses project_* paths


class PathContextManager:
    """Manages database and thumbnail contexts based on current paths."""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self._context_cache = {}  # Cache for path-to-context mappings
        self._user_paths = []
        self._project_paths = []
        self._reload_configured_paths()
        
        logger.info("PathContextManager initialized")
    
    def _reload_configured_paths(self):
        """Reload configured paths from all configuration layers."""
        try:
            # Get user configured paths
            user_config = self.config_manager.get_user_config()
            user_tree_config = user_config.get('directory_tree', {})
            self._user_paths = user_tree_config.get('configured_paths', [])
            
            # Get project configured paths
            project_config = self.config_manager.get_project_config()
            project_tree_config = project_config.get('directory_tree', {})
            self._project_paths = project_tree_config.get('configured_paths', [])
            
            logger.info(f"Loaded {len(self._user_paths)} user paths and {len(self._project_paths)} project paths")
            
            # Clear cache when paths change
            self._context_cache.clear()
            
        except Exception as e:
            logger.error(f"Error reloading configured paths: {e}")
            self._user_paths = []
            self._project_paths = []
    
    def get_context_for_path(self, path: str) -> ContextType:
        """Determine the context type for a given path."""
        if not path:
            return ContextType.GENERAL
        
        # Check cache first
        if path in self._context_cache:
            return self._context_cache[path]
        
        try:
            path_obj = Path(path).resolve()
            context = self._determine_context(path_obj)
            
            # Cache the result
            self._context_cache[path] = context
            return context
            
        except Exception as e:
            logger.debug(f"Error determining context for path {path}: {e}")
            return ContextType.GENERAL
    
    def _determine_context(self, path_obj: Path) -> ContextType:
        """Determine context based on path matching."""
        path_str = str(path_obj)
        
        # Check if path is under any user-configured paths
        for user_path in self._user_paths:
            try:
                user_path_obj = Path(user_path).resolve()
                if self._is_path_under(path_obj, user_path_obj):
                    logger.debug(f"Path {path_str} matches user context (under {user_path})")
                    return ContextType.USER
            except Exception as e:
                logger.debug(f"Error checking user path {user_path}: {e}")
                continue
        
        # Check if path is under any project-configured paths
        for project_path in self._project_paths:
            try:
                project_path_obj = Path(project_path).resolve()
                if self._is_path_under(path_obj, project_path_obj):
                    logger.debug(f"Path {path_str} matches project context (under {project_path})")
                    return ContextType.PROJECT
            except Exception as e:
                logger.debug(f"Error checking project path {project_path}: {e}")
                continue
        
        # Default to general context
        logger.debug(f"Path {path_str} uses general context (no specific match)")
        return ContextType.GENERAL
    
    def _is_path_under(self, path: Path, parent: Path) -> bool:
        """Check if path is under parent directory."""
        try:
            # Use relative_to to check if path is under parent
            path.relative_to(parent)
            return True
        except ValueError:
            # path is not under parent
            return False
    
    def get_database_path(self, context: ContextType) -> str:
        """Get the database path for the given context."""
        paths_config = self.config_manager.get('paths', {})
        
        if context == ContextType.USER:
            return paths_config.get('user_db_path', paths_config.get('gen_db_directory', ''))
        elif context == ContextType.PROJECT:
            return paths_config.get('project_db_path', paths_config.get('gen_db_directory', ''))
        else:  # GENERAL
            return paths_config.get('gen_db_directory', '')
    
    def get_thumbnail_path(self, context: ContextType) -> str:
        """Get the thumbnail directory path for the given context."""
        paths_config = self.config_manager.get('paths', {})
        
        if context == ContextType.USER:
            return paths_config.get('user_thumbnail_path', paths_config.get('gen_thumbnail_directory', ''))
        elif context == ContextType.PROJECT:
            return paths_config.get('project_thumbnail_path', paths_config.get('gen_thumbnail_directory', ''))
        else:  # GENERAL
            return paths_config.get('gen_thumbnail_directory', '')
    
    def get_database_config(self, path: str) -> Dict[str, str]:
        """Get database configuration for a given path."""
        context = self.get_context_for_path(path)
        db_path = self.get_database_path(context)
        
        return {
            'context_type': context.value,
            'database_path': db_path,
            'database_file': str(Path(db_path) / 'stockshot.db'),
        }
    
    def get_thumbnail_config(self, path: str) -> Dict[str, str]:
        """Get thumbnail configuration for a given path."""
        context = self.get_context_for_path(path)
        thumbnail_path = self.get_thumbnail_path(context)
        
        return {
            'context_type': context.value,
            'thumbnail_directory': thumbnail_path,
        }
    
    def get_context_info(self, path: str) -> Dict[str, any]:
        """Get complete context information for a path."""
        context = self.get_context_for_path(path)
        
        return {
            'context_type': context.value,
            'database': self.get_database_config(path),
            'thumbnails': self.get_thumbnail_config(path),
        }
    
    def reload_configuration(self):
        """Reload configuration when config files change."""
        self._reload_configured_paths()
        logger.info("PathContextManager configuration reloaded")
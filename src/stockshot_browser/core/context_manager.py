"""
Context management for Stockshot Browser.
"""

import logging
from PySide6.QtCore import QObject, Signal

from ..config.manager import ConfigurationManager
from ..database.connection import DatabaseManager


logger = logging.getLogger(__name__)


class ContextManager(QObject):
    """Manages project contexts and user profiles."""
    
    # Signals
    project_changed = Signal(str)  # project_name
    
    def __init__(self, config_manager: ConfigurationManager, database_manager: DatabaseManager):
        super().__init__()
        self.config_manager = config_manager
        self.database_manager = database_manager
        self.current_project = None
        
        logger.info("ContextManager initialized")
    
    def switch_to_project(self, project_name: str) -> None:
        """Switch to a project context."""
        logger.info(f"Switching to project: {project_name}")
        self.current_project = project_name
        self.project_changed.emit(project_name)
    
    def create_project(self, project_name: str) -> None:
        """Create a new project."""
        logger.info(f"Creating project: {project_name}")
        # Basic implementation - just log for now
        self.current_project = project_name
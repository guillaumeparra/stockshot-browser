"""
Main application class for Stockshot Browser.
"""

import logging
import sys
from typing import Optional

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QIcon

from ..config.manager import ConfigurationManager
from ..database.multi_database_manager import MultiDatabaseManager
from ..ui.main_window import MainWindow
from .multi_entity_manager import MultiEntityManager
from .multi_metadata_manager import MultiMetadataManager
from .multi_thumbnail_manager import MultiThumbnailManager
from .path_context_manager import PathContextManager
from .context_manager import ContextManager
from .color_manager import ColorManager
from .metadata_exporter import MetadataExporter


logger = logging.getLogger(__name__)


class StockshotBrowserApp(QObject):
    """Main application controller for Stockshot Browser."""
    
    # Signals
    application_started = Signal()
    application_closing = Signal()
    project_changed = Signal(str)  # project_name
    
    def __init__(self, qt_app: QApplication, config_manager: ConfigurationManager):
        super().__init__()
        
        self.qt_app = qt_app
        self.config_manager = config_manager
        
        # Core managers
        self.path_context_manager: Optional[PathContextManager] = None
        self.multi_database_manager: Optional[MultiDatabaseManager] = None
        self.multi_entity_manager: Optional[MultiEntityManager] = None
        self.multi_metadata_manager: Optional[MultiMetadataManager] = None
        self.multi_thumbnail_manager: Optional[MultiThumbnailManager] = None
        self.context_manager: Optional[ContextManager] = None
        self.color_manager: Optional[ColorManager] = None
        self.metadata_exporter: Optional[MetadataExporter] = None
        
        # Legacy aliases for backward compatibility
        self.database_manager: Optional[MultiDatabaseManager] = None
        self.entity_manager: Optional[MultiEntityManager] = None
        self.metadata_manager: Optional[MultiMetadataManager] = None
        self.thumbnail_manager: Optional[MultiThumbnailManager] = None
        
        # UI
        self.main_window: Optional[MainWindow] = None
        
        # Application state
        self._initialized = False
        self._current_project = None
        
        # Setup Qt application connections
        self.qt_app.aboutToQuit.connect(self._on_application_quit)
        
        # Initialize application
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize application components."""
        try:
            logger.info("Initializing Stockshot Browser application...")
            
            # Initialize database
            self._initialize_database()
            
            # Initialize core managers
            self._initialize_managers()
            
            # Setup auto-save timer
            self._setup_auto_save()
            
            self._initialized = True
            logger.info("Application initialization completed successfully")
            
        except Exception as e:
            self._show_error_dialog("Initialization Error", 
                                  f"Failed to initialize Stockshot Browser:\n{e}")
            sys.exit(1)
    
    def _initialize_database(self) -> None:
        """Initialize multi-context database system."""
        
        # Initialize path context manager first
        self.path_context_manager = PathContextManager(self.config_manager)
        
        # Initialize multi-database manager
        self.multi_database_manager = MultiDatabaseManager(
            self.config_manager, self.path_context_manager
        )
        self.multi_database_manager.initialize_databases()
        
        # Set legacy alias for backward compatibility
        self.database_manager = self.multi_database_manager
        
        # Enable backup if configured
        if self.config_manager.get('database.backup_enabled', True):
            backup_interval = self.config_manager.get('database.backup_interval_hours', 24)
            max_backups = self.config_manager.get('database.max_backups', 7)
            self.multi_database_manager.setup_auto_backup(backup_interval, max_backups)
    
    def _initialize_managers(self) -> None:
        """Initialize core application managers."""
        
        # Color Manager (initialize first as it might be needed by others)
        self.color_manager = ColorManager(
            config_manager=self.config_manager
        )
        
        # Multi-Entity Manager
        self.multi_entity_manager = MultiEntityManager(
            config_manager=self.config_manager,
            multi_database_manager=self.multi_database_manager,
            path_context_manager=self.path_context_manager
        )
        
        # Multi-Metadata Manager
        self.multi_metadata_manager = MultiMetadataManager(
            config_manager=self.config_manager,
            multi_database_manager=self.multi_database_manager,
            path_context_manager=self.path_context_manager
        )
        
        # Multi-Thumbnail Manager
        self.multi_thumbnail_manager = MultiThumbnailManager(
            config_manager=self.config_manager,
            multi_database_manager=self.multi_database_manager,
            path_context_manager=self.path_context_manager,
            color_manager=self.color_manager
        )
        
        # Context Manager (for project management)
        self.context_manager = ContextManager(
            config_manager=self.config_manager,
            database_manager=self.multi_database_manager
        )
        
        # Set legacy aliases for backward compatibility
        self.entity_manager = self.multi_entity_manager
        self.metadata_manager = self.multi_metadata_manager
        self.thumbnail_manager = self.multi_thumbnail_manager
        
        # Connect manager signals
        self._connect_manager_signals()
            
    def _connect_manager_signals(self) -> None:
        """Connect signals between managers."""
        # Multi-Entity manager signals
        if self.multi_entity_manager:
            self.multi_entity_manager.entities_discovered.connect(
                self.multi_metadata_manager.process_new_entities
            )
            self.multi_entity_manager.entities_discovered.connect(
                self.multi_thumbnail_manager.queue_thumbnail_generation
            )
        
        # Context manager signals
        if self.context_manager:
            self.context_manager.project_changed.connect(self._on_project_changed)
    
    def _setup_auto_save(self) -> None:
        """Setup automatic saving of user preferences."""
        auto_save_interval = self.config_manager.get('ui.auto_save_interval_minutes', 5)
        if auto_save_interval > 0:
            self.auto_save_timer = QTimer()
            self.auto_save_timer.timeout.connect(self._auto_save)
            self.auto_save_timer.start(auto_save_interval * 60 * 1000)  # Convert to milliseconds
    
    def show_main_window(self) -> None:
        """Create and show the main application window."""
        if not self._initialized:
            return
        
        try:
            
            self.main_window = MainWindow(self)
            
            # Restore window state
            self._restore_window_state()
            
            # Show window
            self.main_window.show()
            
            # Load initial project
            self._load_initial_project()
            
            # Emit application started signal
            self.application_started.emit()
            
            
        except Exception as e:
            self._show_error_dialog("Window Error", 
                                  f"Failed to create main window:\n{e}")
    
    def _restore_window_state(self) -> None:
        """Restore main window state from configuration."""
        if not self.main_window:
            return
        
        # Restore geometry
        geometry = self.config_manager.get('ui.window_geometry', {})
        if geometry:
            self.main_window.setGeometry(
                geometry.get('x', 100),
                geometry.get('y', 100),
                geometry.get('width', 1200),
                geometry.get('height', 800)
            )
        
        # Restore splitter sizes
        splitter_sizes = self.config_manager.get('ui.splitter_sizes', [300, 900])
        if hasattr(self.main_window, 'set_splitter_sizes'):
            self.main_window.set_splitter_sizes(splitter_sizes)
        
        # Restore open tabs
        open_tabs = self.config_manager.get('ui.open_tabs', [])
        if open_tabs and hasattr(self.main_window, 'restore_tabs'):
            self.main_window.restore_tabs(open_tabs)
    
    def _load_initial_project(self) -> None:
        """Load the initial project context."""
        # Get last used project or default
        last_project = self.config_manager.get('projects.last_project')
        default_project = self.config_manager.get('projects.default_project', 'Default')
        
        project_name = last_project or default_project
        
        try:
            self.context_manager.switch_to_project(project_name)
        except Exception as e:
            # Try to create default project
            try:
                self.context_manager.create_project(default_project)
                self.context_manager.switch_to_project(default_project)
            except Exception as e2:
                raise
    
    def _on_project_changed(self, project_name: str) -> None:
        """Handle project change."""
        self._current_project = project_name
        self.config_manager.set('projects.last_project', project_name, persist=True)
        self.project_changed.emit(project_name)
    
    def _auto_save(self) -> None:
        """Perform automatic save of user preferences."""
        try:
            if self.main_window:
                # Save window state
                geometry = self.main_window.geometry()
                self.config_manager.set('ui.window_geometry', {
                    'x': geometry.x(),
                    'y': geometry.y(),
                    'width': geometry.width(),
                    'height': geometry.height(),
                }, persist=True)
                
                # Save splitter sizes
                if hasattr(self.main_window, 'get_splitter_sizes'):
                    splitter_sizes = self.main_window.get_splitter_sizes()
                    self.config_manager.set('ui.splitter_sizes', splitter_sizes, persist=True)
                
                # Save open tabs
                if hasattr(self.main_window, 'get_open_tabs'):
                    open_tabs = self.main_window.get_open_tabs()
                    self.config_manager.set('ui.open_tabs', open_tabs, persist=True)
            
            
        except Exception as e:
            logger.warning(f"Auto-save failed: {e}")
    
    def _on_application_quit(self) -> None:
        """Handle application quit event."""
        
        try:
            # Emit closing signal
            self.application_closing.emit()
            
            # Save current state
            self._auto_save()
            
            # Shutdown managers
            if self.multi_thumbnail_manager:
                self.multi_thumbnail_manager.shutdown()
            elif self.thumbnail_manager:
                self.thumbnail_manager.shutdown()
            
            if self.multi_database_manager:
                self.multi_database_manager.close()
            elif self.database_manager:
                self.database_manager.close()
            
            
        except Exception as e:
            logger.error(f"Error during application shutdown: {e}")
    
    def _show_error_dialog(self, title: str, message: str) -> None:
        """Show error dialog to user."""
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()
    
    def get_current_project(self) -> Optional[str]:
        """Get current project name."""
        return self._current_project
    
    def is_initialized(self) -> bool:
        """Check if application is fully initialized."""
        return self._initialized
    
    def restart_application(self) -> None:
        """Restart the application."""
        logger.info("Restarting application...")
        self.qt_app.quit()
        # Note: Actual restart would be handled by external process manager
    
    def show_about_dialog(self) -> None:
        """Show about dialog."""
        about_text = f"""
        <h2>Stockshot Browser</h2>
        <p>Version: {self.config_manager.get('version', '1.0.0')}</p>
        <p>Professional video file explorer for industry workflows.</p>
        <p>Built with Python and PySide6.</p>
        <p><a href="https://github.com/stockshot/stockshot-browser">GitHub Repository</a></p>
        """
        
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("About Stockshot Browser")
        msg_box.setText(about_text)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()
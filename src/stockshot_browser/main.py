#!/usr/bin/env python3
"""
Main entry point for Stockshot Browser application.
"""

import sys
import os
import logging
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QDir
from PySide6.QtGui import QIcon

# Import qt_material from our local looks folder
from .looks.qt_material import apply_stylesheet

from .core.application import StockshotBrowserApp
from .config.manager import ConfigurationManager


def setup_logging(log_level: str = None, log_file_path: str = None) -> None:
    """Setup application logging with configurable settings from defaults.py."""
    # Import defaults to get the logging configuration
    from .config.defaults import DEFAULT_CONFIG
    
    logging_config = DEFAULT_CONFIG.get('logging', {})
    
    # Use provided parameters or fall back to configuration
    if log_level is None:
        log_level = logging_config.get('level', 'INFO')
    if log_file_path is None:
        log_file_path = logging_config.get('file_path', 'stockshot_browser.log')
    
    # Get other logging settings
    file_enabled = logging_config.get('file_enabled', True)
    console_enabled = logging_config.get('console_enabled', True)
    
    # Ensure log directory exists if file logging is enabled
    if file_enabled:
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Setup handlers based on configuration
    handlers = []
    if console_enabled:
        handlers.append(logging.StreamHandler(sys.stdout))
    if file_enabled:
        handlers.append(logging.FileHandler(str(log_path)))
    
    # Fallback to console if no handlers enabled
    if not handlers:
        handlers.append(logging.StreamHandler(sys.stdout))
    
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=handlers,
    )


def setup_qt_application() -> QApplication:
    """Setup Qt application with proper attributes and material design theme."""
    # Note: High DPI scaling is enabled by default in Qt6/PySide6
    # The AA_EnableHighDpiScaling and AA_UseHighDpiPixmaps attributes are deprecated
    
    app = QApplication(sys.argv)
    app.setApplicationName("Stockshot Browser")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Stockshot")
    app.setOrganizationDomain("stockshot.com")
    
    # Apply material design theme from DEFAULT_CONFIG
    try:
        from .config.defaults import DEFAULT_CONFIG
        theme_name = DEFAULT_CONFIG.get('ui', {}).get('theme', 'dark_blue.xml')
        apply_stylesheet(app, theme=theme_name)
    except Exception as e:
        # Fallback if theming fails - continue with default theme
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to apply qt_material theme: {e}")
    
    # Set application icon
    icon_path = Path(__file__).parent / "resources" / "icons" / "app_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    return app


def find_config_files() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Find configuration files using paths from defaults.py configuration."""
    from .config.defaults import DEFAULT_CONFIG
    
    # Get configurable paths from defaults
    config_files = DEFAULT_CONFIG.get('config_files', {})
    
    # Primary config file paths from defaults.py
    default_general_config = config_files.get('general_config_file')
    default_project_config = config_files.get('project_config_file')
    default_user_config = config_files.get('user_config_file')
    
    # Alternative search locations from defaults.py
    alternative_locations = config_files.get('alternative_locations', {})
    
    # Build search directories list
    search_dirs = [
        Path.cwd(),  # Current directory
        Path(default_user_config).parent if default_user_config else None,  # Primary config directory
        Path.home() / ".stockshot_browser",  # Legacy location
        Path("/etc/stockshot_browser") if os.name != 'nt' else None,  # System-wide (Linux/macOS)
    ]
    
    # Remove None entries
    search_dirs = [d for d in search_dirs if d is not None]
    
    general_config = None
    project_config = None
    user_config = None
    
    # Search for existing config files
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
            
        # Look for general config
        general_path = search_dir / "global_config.json"
        if general_path.exists() and general_config is None:
            general_config = str(general_path)
        
        # Look for project config
        project_path = search_dir / "project_config.json"
        if project_path.exists() and project_config is None:
            project_config = str(project_path)
        
        # Look for user config
        user_path = search_dir / "user_config.json"
        if user_path.exists() and user_config is None:
            user_config = str(user_path)
    
    # If no existing configs found, use default paths from defaults.py
    if general_config is None and default_general_config:
        general_config = default_general_config
    
    if project_config is None and default_project_config:
        project_config = default_project_config
    
    if user_config is None and default_user_config:
        user_config = default_user_config
    
    return general_config, project_config, user_config


def main() -> int:
    """Main application entry point."""
    try:
        # Setup logging
        setup_logging()
        logger = logging.getLogger(__name__)
        logger.info("Starting Stockshot Browser...")
        
        # Create Qt application
        qt_app = setup_qt_application()
        
        # Find configuration files
        general_config, project_config, user_config = find_config_files()
        logger.info(f"Configuration files found:")
        logger.info(f"  General: {general_config}")
        logger.info(f"  Project: {project_config}")
        logger.info(f"  User: {user_config}")
        
        # Create configuration manager
        config_manager = ConfigurationManager()
        config_manager.load_configuration(
            general_config_path=general_config,
            project_config_path=project_config,
            user_config_path=user_config,
        )
        
        # Create main application
        app = StockshotBrowserApp(qt_app, config_manager)
        
        # Show main window
        app.show_main_window()
        
        logger.info("Stockshot Browser started successfully")
        
        # Run Qt event loop
        return qt_app.exec()
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to start Stockshot Browser: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
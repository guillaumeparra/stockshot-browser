"""
Main window for Stockshot Browser.
"""

import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QMenuBar, QStatusBar, QMessageBox,
    QFileDialog, QPushButton, QDockWidget
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence

from .tabbed_navigation import TabbedNavigationWidget
from .drag_drop_mixin import DragDropMixin
from .search_widget import SearchWidget
from .metadata_viewer import MetadataViewerWidget

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow, DragDropMixin):
    """Main application window with tabbed navigation interface and drag-drop support."""
    
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self.config = app_controller.config_manager
        
        self.setWindowTitle("Stockshot Browser")
        self.setMinimumSize(1200, 800)
        
        self._setup_ui()
        self._setup_metadata_dock()
        self._setup_menus()
        self._setup_statusbar()
        self._setup_drag_drop()
        self._setup_search_dock()
        
        logger.info("MainWindow initialized with tabbed navigation, drag-drop, search, and metadata viewer")
    
    def _setup_ui(self):
        """Setup the main UI layout."""
        # Create central widget with vertical layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create search widget (horizontal, below menu)
        self.search_widget = SearchWidget(self)
        self.search_widget.search_requested.connect(self._on_search_requested)
        self.search_widget.search_cleared.connect(self._on_search_cleared)
        main_layout.addWidget(self.search_widget)
        
        # Create tabbed navigation
        self.tabbed_navigation = TabbedNavigationWidget(self)
        self.tabbed_navigation.app_controller = self.app_controller
        self.tabbed_navigation.create_initial_tab()  # Create initial tab after setting app_controller
        main_layout.addWidget(self.tabbed_navigation)
        
        # Connect signals
        self.tabbed_navigation.directory_changed.connect(self._on_directory_changed)
        self.tabbed_navigation.entity_selected.connect(self._on_entity_selected)
        self.tabbed_navigation.entity_double_clicked.connect(self._on_entity_double_clicked)
        self.tabbed_navigation.tab_changed.connect(self._on_tab_changed)
    
    def _setup_metadata_dock(self):
        """Setup the metadata viewer dock widget."""
        # Create metadata viewer widget
        self.metadata_viewer = MetadataViewerWidget(self.app_controller, self)
        
        # Create dock widget
        self.metadata_dock = QDockWidget("Metadata Viewer", self)
        self.metadata_dock.setWidget(self.metadata_viewer)
        self.metadata_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.metadata_dock.setFeatures(
            QDockWidget.DockWidgetClosable |
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable
        )
        
        # Add dock to right side
        self.addDockWidget(Qt.RightDockWidgetArea, self.metadata_dock)
        
        # Initially hide the metadata dock
        self.metadata_dock.setVisible(False)
        
        # Initialize metadata viewer with clear state
        self.metadata_viewer.clear_metadata()
        
        # Connect dock visibility changes
        self.metadata_dock.visibilityChanged.connect(self._on_metadata_dock_visibility_changed)
    
    def _setup_menus(self):
        """Setup application menus."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        # New tab action
        new_tab_action = QAction("New &Tab", self)
        new_tab_action.setShortcut(QKeySequence("Ctrl+T"))
        new_tab_action.setStatusTip("Open a new tab")
        new_tab_action.triggered.connect(self.tabbed_navigation.add_new_tab)
        file_menu.addAction(new_tab_action)
        
        # Close tab action
        close_tab_action = QAction("&Close Tab", self)
        close_tab_action.setShortcut(QKeySequence("Ctrl+W"))
        close_tab_action.setStatusTip("Close current tab")
        close_tab_action.triggered.connect(self._close_current_tab)
        file_menu.addAction(close_tab_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        # Refresh current tab
        refresh_action = QAction("&Refresh", self)
        refresh_action.setShortcut(QKeySequence.Refresh)
        refresh_action.setStatusTip("Refresh current tab")
        refresh_action.triggered.connect(self.tabbed_navigation.refresh_current_tab)
        view_menu.addAction(refresh_action)
        
        # Refresh all tabs
        refresh_all_action = QAction("Refresh &All Tabs", self)
        refresh_all_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        refresh_all_action.setStatusTip("Refresh all open tabs")
        refresh_all_action.triggered.connect(self.tabbed_navigation.refresh_all_tabs)
        view_menu.addAction(refresh_all_action)
        
        view_menu.addSeparator()
        
        # Next tab
        next_tab_action = QAction("&Next Tab", self)
        next_tab_action.setShortcut(QKeySequence("Ctrl+Tab"))
        next_tab_action.setStatusTip("Switch to next tab")
        next_tab_action.triggered.connect(self._next_tab)
        view_menu.addAction(next_tab_action)
        
        # Previous tab
        prev_tab_action = QAction("&Previous Tab", self)
        prev_tab_action.setShortcut(QKeySequence("Ctrl+Shift+Tab"))
        prev_tab_action.setStatusTip("Switch to previous tab")
        prev_tab_action.triggered.connect(self._previous_tab)
        view_menu.addAction(prev_tab_action)
        
        view_menu.addSeparator()
        
        # Toggle search panel
        self.toggle_search_action = QAction("&Search Panel", self)
        self.toggle_search_action.setShortcut(QKeySequence("Ctrl+F"))
        self.toggle_search_action.setStatusTip("Toggle search panel")
        self.toggle_search_action.setCheckable(True)
        self.toggle_search_action.setChecked(True)
        self.toggle_search_action.triggered.connect(self._toggle_search_panel)
        view_menu.addAction(self.toggle_search_action)
        
        # Toggle metadata panel
        self.toggle_metadata_action = QAction("&Metadata Panel", self)
        self.toggle_metadata_action.setShortcut(QKeySequence("Ctrl+M"))
        self.toggle_metadata_action.setStatusTip("Toggle metadata panel")
        self.toggle_metadata_action.setCheckable(True)
        self.toggle_metadata_action.setChecked(False)
        self.toggle_metadata_action.triggered.connect(self._toggle_metadata_panel)
        view_menu.addAction(self.toggle_metadata_action)
        
        view_menu.addSeparator()
        
        # Color Settings
        color_settings_action = QAction("&Color Settings...", self)
        color_settings_action.setStatusTip("Open color management settings")
        color_settings_action.triggered.connect(self._show_color_settings)
        view_menu.addAction(color_settings_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_statusbar(self):
        """Setup status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Status bar will only show temporary messages, no permanent widgets
        # Removed tab count and "Ready" message as requested
    
    
    @Slot(str)
    def _on_directory_changed(self, path: str):
        """Handle directory change."""
        self.status_bar.showMessage(f"Loaded: {path}", 3000)
        logger.debug(f"Directory changed: {path}")
    
    @Slot(object)
    def _on_entity_selected(self, entity):
        """Handle entity selection."""
        self.status_bar.showMessage(f"Selected: {entity.name}")
        
        # Update metadata viewer if visible
        if self.metadata_dock.isVisible():
            self.metadata_viewer.show_entity_metadata(entity)
        else:
            pass
    
    @Slot(object)
    def _on_entity_double_clicked(self, entity):
        """Handle entity double click."""
        self.status_bar.showMessage(f"Double-clicked: {entity.name}")
        logger.info(f"Entity double-clicked: {entity.name}")
        # In a full implementation, this would open the entity in an external player
    
    @Slot(int)
    def _on_tab_changed(self, index: int):
        """Handle tab change."""
        logger.debug(f"Tab changed to index: {index}")
        
        # Update search widget to reflect current tab's filter state
        current_tab = self.tabbed_navigation.get_current_tab()
        if current_tab:
            filter_state = current_tab.get_filter_state()
            if filter_state:
                # Restore search widget state
                self.search_widget.restore_search_state(filter_state)
            else:
                # Clear search widget
                self.search_widget.clear_search()
    
    def _close_current_tab(self):
        """Close the current tab."""
        current_index = self.tabbed_navigation.tab_widget.currentIndex()
        self.tabbed_navigation.close_tab(current_index)
    
    def _next_tab(self):
        """Switch to next tab."""
        tab_widget = self.tabbed_navigation.tab_widget
        current = tab_widget.currentIndex()
        next_index = (current + 1) % tab_widget.count()
        tab_widget.setCurrentIndex(next_index)
    
    def _previous_tab(self):
        """Switch to previous tab."""
        tab_widget = self.tabbed_navigation.tab_widget
        current = tab_widget.currentIndex()
        prev_index = (current - 1) % tab_widget.count()
        tab_widget.setCurrentIndex(prev_index)
    
    
    def _show_about(self):
        """Show about dialog."""
        self.app_controller.show_about_dialog()
    
    def _show_color_settings(self):
        """Show color settings dialog."""
        try:
            from .color_settings_widget import ColorSettingsWidget
            from PySide6.QtWidgets import QDialog, QVBoxLayout
            
            # Create a dialog wrapper for the color settings widget
            dialog = QDialog(self)
            dialog.setWindowTitle("Color Management Settings")
            dialog.setModal(True)
            dialog.resize(600, 500)
            
            layout = QVBoxLayout(dialog)
            
            # Create color settings widget
            color_widget = ColorSettingsWidget(self.app_controller)
            layout.addWidget(color_widget)
            
            # Show dialog
            dialog.exec()
            
        except Exception as e:
            logger.error(f"Error opening color settings: {e}")
            QMessageBox.warning(
                self,
                "Color Settings Error",
                f"Failed to open color settings: {e}"
            )
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Save complete tab states for session restoration
        tab_states = self.tabbed_navigation.get_all_tab_states()
        
        # Save to user configuration
        try:
            self.app_controller.config_manager.set('session.tab_states', tab_states)
            self.app_controller.config_manager.save_user_config()
            logger.info(f"Saved session state with {len(tab_states)} tabs")
        except Exception as e:
            logger.error(f"Failed to save session state: {e}")
        
        logger.info(f"Closing with {len(tab_states)} tabs open")
        event.accept()
    
    # Compatibility methods for existing code
    def set_splitter_sizes(self, sizes):
        """Set splitter sizes (compatibility method)."""
        # No longer using a single splitter, but keep for compatibility
        pass
    
    def get_splitter_sizes(self):
        """Get current splitter sizes (compatibility method)."""
        # Return default values for compatibility
        return [300, 900]
    
    def restore_tabs(self, tabs):
        """Restore tabs from saved session (legacy method)."""
        if tabs:
            self.tabbed_navigation.restore_tabs(tabs)
            logger.info(f"Restored {len(tabs)} tabs")
    
    def restore_session_state(self):
        """Restore complete session state including tab states and filters."""
        try:
            tab_states = self.app_controller.config_manager.get('session.tab_states', [])
            if tab_states:
                self.tabbed_navigation.restore_tab_states(tab_states)
                logger.info(f"Restored session state with {len(tab_states)} tabs")
                
                # Update search widget to reflect current tab's filter state
                current_tab = self.tabbed_navigation.get_current_tab()
                if current_tab:
                    filter_state = current_tab.get_filter_state()
                    if filter_state:
                        self.search_widget.restore_search_state(filter_state)
            else:
                # No saved session, create initial tab
                self.tabbed_navigation.create_initial_tab()
        except Exception as e:
            logger.error(f"Failed to restore session state: {e}")
            # Fallback to creating initial tab
            self.tabbed_navigation.create_initial_tab()
    
    def get_open_tabs(self):
        """Get list of open tab paths."""
        return self.tabbed_navigation.get_open_paths()
    
    def _setup_search_dock(self):
        """Setup the search functionality (now integrated in main layout)."""
        # Search widget is now created in _setup_ui()
        # This method kept for compatibility
        pass
    
    def _toggle_search_panel(self, visible: bool):
        """Toggle search panel visibility."""
        self.search_widget.setVisible(visible)
    
    def _toggle_metadata_panel(self, visible: bool):
        """Toggle metadata panel visibility."""
        self.metadata_dock.setVisible(visible)
        if visible:
            # When showing the dock, clear metadata if no entity is currently selected
            current_tab = self.tabbed_navigation.get_current_tab()
            if current_tab and hasattr(current_tab, 'content_view'):
                selected_entities = current_tab.content_view.get_selected_entities()
                if selected_entities:
                    # Show metadata for the first selected entity
                    self.metadata_viewer.show_entity_metadata(selected_entities[0])
                else:
                    # Clear metadata display
                    self.metadata_viewer.clear_metadata()
            else:
                self.metadata_viewer.clear_metadata()
    
    def _on_metadata_dock_visibility_changed(self, visible: bool):
        """Handle metadata dock visibility changes."""
        # Update menu action state
        self.toggle_metadata_action.setChecked(visible)
        
        if visible:
            # When dock becomes visible, update with current selection if any
            current_tab = self.tabbed_navigation.get_current_tab()
            if current_tab and hasattr(current_tab, 'content_view'):
                selected_entities = current_tab.content_view.get_selected_entities()
                if selected_entities:
                    self.metadata_viewer.show_entity_metadata(selected_entities[0])
                else:
                    self.metadata_viewer.clear_metadata()
            else:
                self.metadata_viewer.clear_metadata()
        else:
            pass
    
    @Slot(dict)
    def _on_search_requested(self, criteria: dict):
        """Handle search request."""
        logger.info(f"Search requested with criteria: {criteria}")
        
        # Set filter state for current tab (this will persist across tab switches)
        self.tabbed_navigation.set_current_tab_filter(criteria)
        
        # Get current tab and apply filter
        current_tab = self.tabbed_navigation.get_current_tab()
        if current_tab and hasattr(current_tab, 'content_view'):
            # Apply search filter to content view
            current_tab.content_view.apply_search_filter(criteria)
            
            # Update search widget with results
            visible_count = current_tab.content_view.get_visible_entity_count()
            total_count = len(current_tab.content_view.current_entities)
            self.search_widget.update_results_info(visible_count, total_count)
            
            self.status_bar.showMessage(f"Search found {visible_count} of {total_count} items", 3000)
    
    @Slot()
    def _on_search_cleared(self):
        """Handle search clear."""
        logger.info("Search cleared")
        
        # Clear filter state for current tab
        self.tabbed_navigation.set_current_tab_filter(None)
        
        # Clear filter in current tab
        current_tab = self.tabbed_navigation.get_current_tab()
        if current_tab and hasattr(current_tab, 'content_view'):
            current_tab.content_view.clear_search_filter()
            
        self.status_bar.showMessage("Search cleared", 2000)
    
    def _setup_drag_drop(self):
        """Setup drag and drop functionality for the main window."""
        # Accept video and image files, and directories
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.mpg', '.mpeg']
        image_extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.exr', '.dpx', '.bmp']
        
        self.setup_drag_drop(
            accept_files=True,
            accept_directories=True,
            file_extensions=video_extensions + image_extensions
        )
        
        # Connect drop signals
        self.files_dropped.connect(self._handle_dropped_files)
        self.directories_dropped.connect(self._handle_dropped_directories)
    
    @Slot(list)
    def _handle_dropped_files(self, file_paths: list):
        """Handle files dropped on the main window."""
        logger.info(f"Files dropped on main window: {file_paths}")
        
        # For now, just show in status bar
        if len(file_paths) == 1:
            self.status_bar.showMessage(f"File dropped: {Path(file_paths[0]).name}", 5000)
        else:
            self.status_bar.showMessage(f"{len(file_paths)} files dropped", 5000)
        
        # In a full implementation, you could:
        # - Open files in a viewer
        # - Add them to the current directory
        # - Create a new tab with the file's directory
        
        # For now, let's open the directory of the first file in a new tab
        if file_paths:
            file_dir = str(Path(file_paths[0]).parent)
            self.tabbed_navigation.add_new_tab(file_dir)
    
    @Slot(list)
    def _handle_dropped_directories(self, directory_paths: list):
        """Handle directories dropped on the main window."""
        logger.info(f"Directories dropped on main window: {directory_paths}")
        
        # Open each directory in a new tab
        for directory in directory_paths:
            self.tabbed_navigation.add_new_tab(directory)
            
        if len(directory_paths) == 1:
            self.status_bar.showMessage(f"Opened directory: {Path(directory_paths[0]).name}", 5000)
        else:
            self.status_bar.showMessage(f"Opened {len(directory_paths)} directories in new tabs", 5000)
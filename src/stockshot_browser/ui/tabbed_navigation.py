"""
Tabbed navigation widget for Stockshot Browser.
Allows multiple directory views in separate tabs.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal, Slot, QPoint
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QMenu, QMessageBox, QInputDialog,
    QToolButton, QStyle, QSplitter
)
from PySide6.QtGui import QAction, QIcon

from .directory_tree import DirectoryTreeWidget
from .multi_content_view import MultiContentViewWidget


logger = logging.getLogger(__name__)


class NavigationTab(QWidget):
    """Single navigation tab containing directory tree and content view."""
    
    # Signals
    directory_changed = Signal(str)  # path
    entity_selected = Signal(object)  # entity
    entity_double_clicked = Signal(object)  # entity
    
    def __init__(self, initial_path: Optional[str] = None, app_controller=None, parent=None):
        super().__init__(parent)
        self.current_path = initial_path
        self.app_controller = app_controller
        self.filter_state = None  # Store filter criteria for this tab
        self.view_mode = "Grid"  # Store view mode for this tab
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the tab UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create splitter with directory tree and content view
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.directory_tree = DirectoryTreeWidget(self.app_controller)
        self.content_view = MultiContentViewWidget(self.app_controller)
        
        # Add widgets to splitter
        self.splitter.addWidget(self.directory_tree)
        self.splitter.addWidget(self.content_view)
        
        # Set initial sizes (30% tree, 70% content) - assuming 1200px width
        self.splitter.setSizes([360, 840])  # 30% and 70% of typical window width
        
        # Configure splitter
        self.splitter.setCollapsible(0, False)  # Don't allow directory tree to collapse completely
        self.splitter.setCollapsible(1, False)  # Don't allow content view to collapse completely
        
        # Add splitter to layout
        layout.addWidget(self.splitter)
        
        # Connect signals
        self.directory_tree.directory_selected.connect(self.on_directory_selected)
        self.directory_tree.directories_selected.connect(self.on_directories_selected)
        self.content_view.entity_selected.connect(self.entity_selected.emit)
        self.content_view.entity_double_clicked.connect(self.entity_double_clicked.emit)
        
        # Load initial directory if provided
        if self.current_path:
            self.directory_tree.set_current_directory(self.current_path)
    
    @Slot(str)
    def on_directory_selected(self, path: str):
        """Handle single directory selection from tree."""
        self.current_path = path
        self.content_view.load_directory(path)
        # Restore filter state after loading directory
        if self.filter_state:
            self.content_view.apply_search_filter(self.filter_state)
        self.directory_changed.emit(path)
    
    @Slot(list)
    def on_directories_selected(self, paths: list):
        """Handle multiple directories selection from tree."""
        if len(paths) == 1:
            # Single directory - use existing logic
            self.on_directory_selected(paths[0])
        else:
            # Multiple directories - load all entities from all directories
            self.current_path = f"Multiple directories ({len(paths)} selected)"
            self.content_view.load_multiple_directories(paths)
            # Restore filter state after loading directories
            if self.filter_state:
                self.content_view.apply_search_filter(self.filter_state)
            self.directory_changed.emit(self.current_path)
    
    def get_current_path(self) -> str:
        """Get the current directory path."""
        return self.current_path
    
    def navigate_to(self, path: str):
        """Navigate to a specific path."""
        self.directory_tree.set_current_directory(path)
    
    def refresh(self):
        """Refresh the current view."""
        self.directory_tree.refresh_tree()
        if self.current_path:
            self.content_view.load_directory(self.current_path)
            # Restore filter state after refresh
            if self.filter_state:
                self.content_view.apply_search_filter(self.filter_state)
    
    def get_selected_entities(self):
        """Get currently selected entities."""
        return self.content_view.get_selected_entities()
    
    def set_filter_state(self, filter_criteria):
        """Set the filter state for this tab."""
        self.filter_state = filter_criteria
        if self.content_view and self.content_view.current_entities:
            if filter_criteria:
                self.content_view.apply_search_filter(filter_criteria)
            else:
                self.content_view.clear_search_filter()
    
    def get_filter_state(self):
        """Get the current filter state for this tab."""
        return self.filter_state
    
    def set_view_mode(self, mode: str):
        """Set the view mode for this tab."""
        self.view_mode = mode
        if self.content_view:
            # Update the content view's view mode
            if hasattr(self.content_view, 'view_mode_combo'):
                self.content_view.view_mode_combo.setCurrentText(mode)
    
    def get_view_mode(self) -> str:
        """Get the current view mode for this tab."""
        return self.view_mode
    
    def activate_tab(self):
        """Called when this tab becomes active - ensures content is properly loaded."""
        logger.info(f"Activating tab with path: {self.current_path}")
        
        if self.current_path:
            # Update directory tree to show current path
            if self.directory_tree and isinstance(self.current_path, str) and not self.current_path.startswith("Multiple directories"):
                logger.info(f"Tab activation: Setting directory tree to {self.current_path}")
                self.directory_tree.set_current_directory(self.current_path)
            
            # Force update content view - clear first then reload to ensure complete refresh
            if self.content_view:
                logger.info(f"Tab activation: Force loading directory {self.current_path}")
                
                if isinstance(self.current_path, str) and self.current_path.startswith("Multiple directories"):
                    # Handle multi-directory selection - for now skip reloading
                    # but still restore filter state and view mode
                    logger.info(f"Tab activation: Multi-directory selection, preserving current content")
                else:
                    # Single directory - force clear and reload to ensure complete refresh
                    logger.info(f"Tab activation: Clearing content view and reloading {self.current_path}")
                    
                    # Clear the content view first to force a complete refresh
                    if hasattr(self.content_view, 'clear_content'):
                        self.content_view.clear_content()
                    elif hasattr(self.content_view, 'current_entities'):
                        self.content_view.current_entities = []
                        if hasattr(self.content_view, '_update_display'):
                            self.content_view._update_display()
                    
                    # Force reload the directory
                    self.content_view.load_directory(self.current_path)
                
                # Restore view mode first (before applying filters)
                if hasattr(self.content_view, 'view_mode_combo'):
                    logger.info(f"Tab activation: Restoring view mode to {self.view_mode}")
                    self.content_view.view_mode_combo.setCurrentText(self.view_mode)
                    # Force trigger view mode change to ensure widgets are updated
                    if hasattr(self.content_view, '_on_view_mode_changed'):
                        self.content_view._on_view_mode_changed(self.view_mode)
                
                # Restore filter state after loading and view mode
                if self.filter_state:
                    logger.info(f"Tab activation: Applying filter state: {self.filter_state}")
                    self.content_view.apply_search_filter(self.filter_state)
                else:
                    # Clear any existing filters
                    if hasattr(self.content_view, 'clear_search_filter'):
                        self.content_view.clear_search_filter()
                
                # Fix rubber band overlay geometry after tab switch
                if hasattr(self.content_view, 'refresh_rubber_band_overlay'):
                    self.content_view.refresh_rubber_band_overlay()
        
        logger.info(f"Tab activation completed for path: {self.current_path}")
    
    def get_tab_state(self) -> dict:
        """Get the complete state of this tab for persistence."""
        state = {
            'path': self.current_path,
            'filter_state': self.filter_state,
            'view_mode': self.view_mode
        }
        
        # Save splitter state if available
        if hasattr(self, 'splitter'):
            state['splitter_sizes'] = self.splitter.sizes()
        
        return state
    
    def restore_tab_state(self, state: dict):
        """Restore tab state from saved data."""
        if 'path' in state:
            self.current_path = state['path']
            self.navigate_to(self.current_path)
        
        if 'filter_state' in state:
            self.filter_state = state['filter_state']
        
        if 'view_mode' in state:
            self.view_mode = state['view_mode']
        
        # Restore splitter state if available
        if 'splitter_sizes' in state and hasattr(self, 'splitter'):
            self.splitter.setSizes(state['splitter_sizes'])


class TabbedNavigationWidget(QWidget):
    """Tabbed navigation widget supporting multiple directory views."""
    
    # Signals
    tab_changed = Signal(int)  # index
    directory_changed = Signal(str)  # path
    entity_selected = Signal(object)  # entity
    entity_double_clicked = Signal(object)  # entity
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tabs: Dict[int, NavigationTab] = {}
        self.app_controller = None  # Will be set by main window
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the tabbed navigation UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create tab widget
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        
        # Add new tab button - will be positioned after tabs are added
        self.new_tab_button = QToolButton(self)
        self.new_tab_button.setText("+")
        self.new_tab_button.setToolTip("Open new tab")
        self.new_tab_button.setFixedSize(24, 24)  # Small, compact button
        self.new_tab_button.clicked.connect(self.add_new_tab)
        
        # Initially hide the button - we'll position it manually
        self.new_tab_button.setParent(self.tab_widget.tabBar())
        
        # Tab bar context menu
        self.tab_widget.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self.show_tab_context_menu)
        
        # Connect signals
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.tabBar().tabMoved.connect(self._update_new_tab_button_position)
        
        layout.addWidget(self.tab_widget)
        
        logger.info("TabbedNavigationWidget initialized")
    
    def _update_new_tab_button_position(self):
        """Update the position of the new tab button to be flush with the last tab."""
        if not hasattr(self, 'new_tab_button'):
            return
            
        tab_bar = self.tab_widget.tabBar()
        if tab_bar.count() == 0:
            self.new_tab_button.hide()
            return
        
        # Calculate position after the last tab
        last_tab_rect = tab_bar.tabRect(tab_bar.count() - 1)
        button_x = last_tab_rect.right() + 2  # Small gap
        button_y = last_tab_rect.top() + (last_tab_rect.height() - self.new_tab_button.height()) // 2
        
        # Position the button
        self.new_tab_button.move(button_x, button_y)
        self.new_tab_button.show()
    
    def resizeEvent(self, event):
        """Handle resize events to reposition the new tab button."""
        super().resizeEvent(event)
        self._update_new_tab_button_position()
    
    def showEvent(self, event):
        """Handle show events to position the new tab button."""
        super().showEvent(event)
        self._update_new_tab_button_position()
    
    def create_initial_tab(self):
        """Create the initial tab."""
        if self.app_controller:
            self.add_new_tab(str(Path.home()), "Home")
    
    @Slot()
    def add_new_tab(self, path: Optional[str] = None, title: Optional[str] = None):
        """Add a new navigation tab."""
        if path is None:
            # Use current tab's path or home
            current_tab = self.get_current_tab()
            if current_tab:
                current_path = current_tab.get_current_path()
                # Handle case where current_path might be a complex string (e.g., "Multiple directories...")
                if isinstance(current_path, str) and not current_path.startswith("Multiple directories"):
                    path = current_path
        
        # Create new tab
        tab = NavigationTab(path, self.app_controller, self)
        
        # Connect tab signals
        tab.directory_changed.connect(self.on_tab_directory_changed)
        tab.entity_selected.connect(self.entity_selected.emit)
        tab.entity_double_clicked.connect(self.entity_double_clicked.emit)
        
        # Determine tab title
        if title is None:
            try:
                title = Path(path).name or "Root"
            except (TypeError, ValueError) as e:
                logger.warning(f"Error determining tab title from path '{path}': {e}")
                title = "New Tab"
        
        # Add tab to widget
        index = self.tab_widget.addTab(tab, title)
        self.tabs[index] = tab
        
        # Switch to new tab
        self.tab_widget.setCurrentIndex(index)
        
        # Update new tab button position
        self._update_new_tab_button_position()
        
        logger.info(f"Added new tab: {title} at {path}")
        
        return tab
    
    @Slot(int)
    def close_tab(self, index: int):
        """Close a tab."""
        # Don't close if it's the last tab
        if self.tab_widget.count() <= 1:
            QMessageBox.information(
                self,
                "Cannot Close Tab",
                "Cannot close the last tab. At least one tab must remain open."
            )
            return
        
        # Remove tab
        if index in self.tabs:
            del self.tabs[index]
        self.tab_widget.removeTab(index)
        
        # Update tab indices in dictionary
        new_tabs = {}
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            for old_index, tab in self.tabs.items():
                if tab == widget:
                    new_tabs[i] = tab
                    break
        self.tabs = new_tabs
        
        # Update new tab button position after closing tab
        self._update_new_tab_button_position()
        
        logger.info(f"Closed tab at index {index}")
    
    @Slot(int)
    def on_tab_changed(self, index: int):
        """Handle tab change."""
        if index >= 0:
            tab = self.tabs.get(index)
            if tab:
                # Activate the tab to ensure content is properly loaded
                tab.activate_tab()
                self.directory_changed.emit(tab.get_current_path())
                self.tab_changed.emit(index)
    
    @Slot(str)
    def on_tab_directory_changed(self, path: str):
        """Handle directory change in a tab."""
        # Update tab title
        sender_tab = self.sender()
        for index, tab in self.tabs.items():
            if tab == sender_tab:
                # Handle special case for multiple directories
                if path.startswith("Multiple directories"):
                    title = path  # Use the full text for multiple directories
                else:
                    title = Path(path).name or "Root"
                
                self.tab_widget.setTabText(index, title)
                self.tab_widget.setTabToolTip(index, path)
                
                # Update + button position after tab title change
                self._update_new_tab_button_position()
                break
        
        # Emit signal if it's the current tab
        if sender_tab == self.get_current_tab():
            self.directory_changed.emit(path)
    
    @Slot(QPoint)
    def show_tab_context_menu(self, position: QPoint):
        """Show context menu for tab bar."""
        # Get tab index at position
        tab_bar = self.tab_widget.tabBar()
        index = tab_bar.tabAt(position)
        
        if index < 0:
            return
        
        menu = QMenu(self)
        
        # Duplicate tab action
        duplicate_action = QAction("Duplicate Tab", self)
        duplicate_action.triggered.connect(lambda checked: self.duplicate_tab(index))
        menu.addAction(duplicate_action)
        
        # Rename tab action
        rename_action = QAction("Rename Tab", self)
        rename_action.triggered.connect(lambda checked: self.rename_tab(index))
        menu.addAction(rename_action)
        
        menu.addSeparator()
        
        # Close tab action
        close_action = QAction("Close Tab", self)
        close_action.triggered.connect(lambda checked: self.close_tab(index))
        close_action.setEnabled(self.tab_widget.count() > 1)
        menu.addAction(close_action)
        
        # Close other tabs action
        close_others_action = QAction("Close Other Tabs", self)
        close_others_action.triggered.connect(lambda checked: self.close_other_tabs(index))
        close_others_action.setEnabled(self.tab_widget.count() > 1)
        menu.addAction(close_others_action)
        
        # Close tabs to the right
        close_right_action = QAction("Close Tabs to the Right", self)
        close_right_action.triggered.connect(lambda checked: self.close_tabs_to_right(index))
        close_right_action.setEnabled(index < self.tab_widget.count() - 1)
        menu.addAction(close_right_action)
        
        menu.exec_(tab_bar.mapToGlobal(position))
    
    def duplicate_tab(self, index: int):
        """Duplicate a tab."""
        if index in self.tabs:
            source_tab = self.tabs[index]
            path = source_tab.get_current_path()
            title = self.tab_widget.tabText(index) + " (Copy)"
            self.add_new_tab(path, title)
    
    def rename_tab(self, index: int):
        """Rename a tab."""
        current_title = self.tab_widget.tabText(index)
        new_title, ok = QInputDialog.getText(
            self,
            "Rename Tab",
            "Enter new tab name:",
            text=current_title
        )
        
        if ok and new_title:
            self.tab_widget.setTabText(index, new_title)
    
    def close_other_tabs(self, keep_index: int):
        """Close all tabs except the specified one."""
        # Close tabs from right to left, skipping the one to keep
        for i in range(self.tab_widget.count() - 1, -1, -1):
            if i != keep_index and self.tab_widget.count() > 1:
                self.close_tab(i if i > keep_index else 0)
    
    def close_tabs_to_right(self, index: int):
        """Close all tabs to the right of the specified index."""
        for i in range(self.tab_widget.count() - 1, index, -1):
            self.close_tab(i)
    
    def get_current_tab(self) -> Optional[NavigationTab]:
        """Get the currently active tab."""
        index = self.tab_widget.currentIndex()
        return self.tabs.get(index)
    
    def get_current_path(self) -> Optional[str]:
        """Get the current directory path."""
        tab = self.get_current_tab()
        return tab.get_current_path() if tab else None
    
    def navigate_to(self, path: str):
        """Navigate current tab to a specific path."""
        tab = self.get_current_tab()
        if tab:
            tab.navigate_to(path)
    
    def refresh_current_tab(self):
        """Refresh the current tab."""
        tab = self.get_current_tab()
        if tab:
            tab.refresh()
    
    def refresh_all_tabs(self):
        """Refresh all tabs."""
        for tab in self.tabs.values():
            tab.refresh()
    
    def get_open_paths(self) -> list:
        """Get list of paths open in all tabs."""
        return [tab.get_current_path() for tab in self.tabs.values()]
    
    def restore_tabs(self, paths: list):
        """Restore tabs from a list of paths."""
        # Clear existing tabs
        while self.tab_widget.count() > 0:
            self.tab_widget.removeTab(0)
        self.tabs.clear()
        
        # Create tabs for each path
        for path in paths:
            if Path(path).exists():
                self.add_new_tab(path)
        
        # Ensure at least one tab exists
        if self.tab_widget.count() == 0:
            self.create_initial_tab()
    
    def get_all_tab_states(self) -> list:
        """Get complete state of all tabs for session persistence."""
        states = []
        for index in range(self.tab_widget.count()):
            tab = self.tabs.get(index)
            if tab:
                state = tab.get_tab_state()
                state['title'] = self.tab_widget.tabText(index)
                states.append(state)
        return states
    
    def restore_tab_states(self, states: list):
        """Restore tabs from complete state data."""
        # Clear existing tabs
        while self.tab_widget.count() > 0:
            self.tab_widget.removeTab(0)
        self.tabs.clear()
        
        # Create tabs from states
        for state in states:
            if 'path' in state and Path(state['path']).exists():
                title = state.get('title', Path(state['path']).name or "Root")
                tab = self.add_new_tab(state['path'], title)
                if tab:
                    tab.restore_tab_state(state)
        
        # Ensure at least one tab exists
        if self.tab_widget.count() == 0:
            self.create_initial_tab()
    
    def set_current_tab_filter(self, filter_criteria):
        """Set filter state for the current tab."""
        current_tab = self.get_current_tab()
        if current_tab:
            current_tab.set_filter_state(filter_criteria)
    
    def get_current_tab_filter(self):
        """Get filter state from the current tab."""
        current_tab = self.get_current_tab()
        return current_tab.get_filter_state() if current_tab else None
    
    def set_current_tab_view_mode(self, mode: str):
        """Set view mode for the current tab."""
        current_tab = self.get_current_tab()
        if current_tab:
            current_tab.set_view_mode(mode)
    
    def get_current_tab_view_mode(self) -> str:
        """Get view mode from the current tab."""
        current_tab = self.get_current_tab()
        return current_tab.get_view_mode() if current_tab else "Grid"
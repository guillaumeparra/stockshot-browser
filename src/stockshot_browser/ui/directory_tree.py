"""
Directory tree widget for Stockshot Browser.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    QHBoxLayout, QPushButton, QLineEdit, QLabel, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon

logger = logging.getLogger(__name__)


class DirectoryTreeWidget(QWidget):
    """Directory tree widget with navigation capabilities."""
    
    # Signals
    directory_selected = Signal(str)  # directory_path (single selection - backward compatibility)
    directories_selected = Signal(list)  # list of directory_paths (multi-selection)
    
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self.config = app_controller.config_manager
        
        self._setup_ui()
        self._populate_initial_tree()
        
        logger.info("DirectoryTreeWidget initialized")
    
    def _setup_ui(self):
        """Setup the directory tree UI."""
        layout = QVBoxLayout(self)
        
        # Header
        header_label = QLabel("Directory Tree")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px; color: white;")
        layout.addWidget(header_label)
        
        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Enable multi-selection
        
        # Apply directory tree styling with reduced height
        from .theme_utils import theme_manager
        directory_tree_style = theme_manager.get_directory_tree_stylesheet()
        self.tree.setStyleSheet(directory_tree_style)
        
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.tree)
    
    
    def _populate_initial_tree(self):
        """Populate the tree with initial directories."""
        self.tree.clear()
        
        # Get directory tree configuration from cascading config system
        tree_config = self.config.get('directory_tree', {})
        show_configured_only = tree_config.get('show_configured_paths_only', True)
        show_home = tree_config.get('show_home', True)
        show_root = tree_config.get('show_root', False)
        show_drives = tree_config.get('show_drives', True)
        
        # Collect configured paths from all configuration layers
        configured_paths = self._collect_configured_paths()
        
        roots = []
        
        if show_configured_only:
            # Only show configured paths
            for path_str in configured_paths:
                try:
                    path = Path(path_str)
                    if path.exists() and path.is_dir():
                        # Use a friendly name for the path
                        name = self._get_friendly_path_name(path)
                        roots.append((name, path))
                except Exception as e:
                    logger.warning(f"Invalid configured path {path_str}: {e}")
        else:            
            if show_drives and hasattr(Path, 'drives'):
                for drive in Path.drives():
                    roots.append((f"Drive {drive}", Path(drive)))
            
            # Add configured paths as well
            for path_str in configured_paths:
                try:
                    path = Path(path_str)
                    if path.exists() and path.is_dir():
                        # Avoid duplicates
                        if not any(existing_path == path for _, existing_path in roots):
                            name = self._get_friendly_path_name(path)
                            roots.append((name, path))
                except Exception as e:
                    logger.warning(f"Invalid configured path {path_str}: {e}")
        
        # Create tree items
        for name, path in roots:
            root_item = QTreeWidgetItem([name])
            root_item.setData(0, Qt.UserRole, str(path))
            self.tree.addTopLevelItem(root_item)
            
            # Add a dummy child to make it expandable
            dummy_item = QTreeWidgetItem(["Loading..."])
            root_item.addChild(dummy_item)
        
        # Auto-expand configured paths if requested
        if tree_config.get('expand_configured_paths', True):
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                item.setExpanded(True)
                self._on_item_expanded(item)
    
    def _collect_configured_paths(self):
        """Collect configured paths from all configuration layers (defaults + project + user)."""
        all_paths = []
        
        # Get paths from defaults - access DEFAULT_CONFIG directly to avoid merged overrides
        try:
            from ..config.defaults import DEFAULT_CONFIG
            default_tree_config = DEFAULT_CONFIG.get('directory_tree', {})
            default_paths = default_tree_config.get('configured_paths', [])
            all_paths.extend(default_paths)
            logger.debug(f"Added {len(default_paths)} paths from defaults: {default_paths}")
        except Exception as e:
            logger.debug(f"Could not load default paths: {e}")
        
        # Get paths from project config - always include these
        try:
            project_tree_config = self.config.get_project_config().get('directory_tree', {})
            project_paths = project_tree_config.get('configured_paths', [])
            all_paths.extend(project_paths)
            logger.debug(f"Added {len(project_paths)} paths from project config: {project_paths}")
        except Exception as e:
            logger.debug(f"No project config paths found: {e}")
        
        # Get paths from user config - always include these
        try:
            user_tree_config = self.config.get_user_config().get('directory_tree', {})
            user_paths = user_tree_config.get('configured_paths', [])
            all_paths.extend(user_paths)
            logger.debug(f"Added {len(user_paths)} paths from user config: {user_paths}")
        except Exception as e:
            logger.debug(f"No user config paths found: {e}")
        
        # Remove duplicates while preserving order (first occurrence wins)
        seen = set()
        unique_paths = []
        for path in all_paths:
            if path and path not in seen:  # Only add non-empty, non-duplicate paths
                seen.add(path)
                unique_paths.append(path)
        
        logger.info(f"Collected {len(unique_paths)} unique configured paths from all config layers: {unique_paths}")
        return unique_paths
    
    def _get_friendly_path_name(self, path: Path) -> str:
        """Get a friendly display name for a path."""
        if path == Path.home():
            return "Home"
        elif path == Path.home() / "Videos":
            return "Videos"
        elif path == Path.home() / "Pictures":
            return "Pictures"
        elif path == Path.home() / "Desktop":
            return "Desktop"
        elif path == Path.home() / "Documents":
            return "Documents"
        elif "/comfyui/output" in str(path):
            return "ComfyUI Output"
        elif "/storage/projects/footage" in str(path):
            return "Project Footage"
        elif "/storage/projects/renders" in str(path):
            return "Project Renders"
        elif "footage" in path.name.lower():
            return f"Footage ({path.name})"
        elif "render" in path.name.lower():
            return f"Renders ({path.name})"
        elif "output" in path.name.lower():
            return f"Output ({path.name})"
        else:
            return path.name or str(path)
    
    def _on_item_expanded(self, item: QTreeWidgetItem):
        """Handle item expansion."""
        # Remove dummy children and add real directories
        if item.childCount() == 1 and item.child(0).text(0) == "Loading...":
            item.removeChild(item.child(0))
            self._populate_children(item)
    
    def _populate_children(self, parent_item: QTreeWidgetItem):
        """Populate children for a directory item."""
        directory_path = Path(parent_item.data(0, Qt.UserRole))
        
        try:
            if not directory_path.exists() or not directory_path.is_dir():
                return
            
            # Get subdirectories
            subdirs = []
            for item in directory_path.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    subdirs.append(item)
            
            # Sort directories
            subdirs.sort(key=lambda x: x.name.lower())
            
            # Add directory items
            for subdir in subdirs:
                try:
                    # Check if we can access the directory
                    list(subdir.iterdir())
                    
                    dir_item = QTreeWidgetItem([subdir.name])
                    dir_item.setData(0, Qt.UserRole, str(subdir))
                    parent_item.addChild(dir_item)
                    
                    # Check if this directory has subdirectories
                    has_subdirs = any(item.is_dir() for item in subdir.iterdir() 
                                    if not item.name.startswith('.'))
                    
                    if has_subdirs:
                        # Add dummy child to make it expandable
                        dummy_item = QTreeWidgetItem(["Loading..."])
                        dir_item.addChild(dummy_item)
                        
                except (PermissionError, OSError):
                    # Skip directories we can't access
                    continue
                    
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot access directory {directory_path}: {e}")
    
    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle item click."""
        directory_path = item.data(0, Qt.UserRole)
        if directory_path:
            # Emit single selection signal for backward compatibility
            self.directory_selected.emit(directory_path)
            logger.debug(f"Directory clicked: {directory_path}")
    
    def _on_selection_changed(self):
        """Handle selection change (supports multi-selection)."""
        selected_items = self.tree.selectedItems()
        selected_paths = []
        
        for item in selected_items:
            directory_path = item.data(0, Qt.UserRole)
            if directory_path:
                selected_paths.append(directory_path)
        
        if selected_paths:
            # Emit multi-selection signal
            self.directories_selected.emit(selected_paths)
            
            # Also emit single selection signal for backward compatibility (first selected)
            self.directory_selected.emit(selected_paths[0])
            
            logger.debug(f"Directories selected: {len(selected_paths)} directories")
    
    def _navigate_to_directory(self, directory: Path):
        """Navigate to a specific directory."""
        if directory.exists() and directory.is_dir():
            self.directory_selected.emit(str(directory))
            
            # Try to expand the tree to show this directory
            self._expand_to_directory(directory)
        else:
            logger.warning(f"Directory does not exist: {directory}")
    
    def _expand_to_directory(self, directory: Path):
        """Expand the tree to show the specified directory."""
        logger.debug(f"Attempting to expand to directory: {directory}")
        
        # Find the best matching root for this directory
        best_root = None
        best_root_item = None
        
        for i in range(self.tree.topLevelItemCount()):
            root_item = self.tree.topLevelItem(i)
            root_path = Path(root_item.data(0, Qt.UserRole))
            
            try:
                # Check if the directory is under this root
                directory.relative_to(root_path)
                if not best_root or len(str(root_path)) > len(str(best_root)):
                    best_root = root_path
                    best_root_item = root_item
            except ValueError:
                # Directory is not under this root, continue
                continue
        
        if best_root_item and best_root:
            logger.debug(f"Found best root for expansion: {best_root}")
            # Expand the root item if not already expanded
            if not best_root_item.isExpanded():
                best_root_item.setExpanded(True)
                self._on_item_expanded(best_root_item)
            
            # Try to expand the path to the target directory
            self._expand_path_to_directory(best_root_item, best_root, directory)
    
    def _expand_path_to_directory(self, root_item: QTreeWidgetItem, root_path: Path, target_directory: Path):
        """Recursively expand the tree path to reach the target directory."""
        try:
            # Calculate the relative path from root to target
            relative_path = target_directory.relative_to(root_path)
            path_parts = relative_path.parts
            
            current_item = root_item
            current_path = root_path
            
            # Traverse each part of the path
            for part in path_parts:
                current_path = current_path / part
                found_child = None
                
                # Look for the child with this name
                for i in range(current_item.childCount()):
                    child_item = current_item.child(i)
                    if child_item.text(0) == part:
                        found_child = child_item
                        break
                
                if found_child:
                    # Expand this child if it's not expanded and has children
                    if not found_child.isExpanded() and found_child.childCount() > 0:
                        found_child.setExpanded(True)
                        self._on_item_expanded(found_child)
                    
                    current_item = found_child
                    
                    # If this is the target directory, select it
                    if current_path == target_directory:
                        self.tree.clearSelection()
                        found_child.setSelected(True)
                        self.tree.scrollToItem(found_child)
                        logger.debug(f"Successfully expanded and selected: {target_directory}")
                        return True
                else:
                    # Path not found, stop here
                    logger.debug(f"Could not find path part '{part}' in tree")
                    return False
            
            return False
            
        except ValueError:
            logger.debug(f"Target directory {target_directory} is not under root {root_path}")
            return False
        except Exception as e:
            logger.error(f"Error expanding path to directory: {e}")
            return False
    
    def _find_directory_item(self, directory: Path) -> Optional[QTreeWidgetItem]:
        """Find an existing directory item in the tree."""
        def search_item(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
            # Check if this item matches
            item_path = item.data(0, Qt.UserRole)
            if item_path and Path(item_path) == directory:
                return item
            
            # Recursively search children
            for i in range(item.childCount()):
                child_result = search_item(item.child(i))
                if child_result:
                    return child_result
            
            return None
        
        # Search all top-level items
        for i in range(self.tree.topLevelItemCount()):
            result = search_item(self.tree.topLevelItem(i))
            if result:
                return result
        
        return None
    
    def refresh_tree(self):
        """Refresh the directory tree."""
        logger.debug("Refreshing directory tree")
        self._populate_initial_tree()
    
    def set_current_directory(self, directory: str):
        """Set the current directory and select it in the tree."""
        try:
            path = Path(directory)
            if path.exists() and path.is_dir():
                logger.debug(f"Setting current directory to: {directory}")
                
                # Find and select the directory in the tree
                found_item = self._find_directory_item(path)
                if found_item:
                    # Clear current selection and select the found item
                    self.tree.clearSelection()
                    found_item.setSelected(True)
                    self.tree.scrollToItem(found_item)
                    logger.debug(f"Found and selected directory item: {directory}")
                else:
                    # If not found, try to expand the tree to show this directory
                    logger.debug(f"Directory not found in tree, attempting to expand: {directory}")
                    self._expand_to_directory(path)
        except Exception as e:
            logger.error(f"Error setting current directory: {e}")
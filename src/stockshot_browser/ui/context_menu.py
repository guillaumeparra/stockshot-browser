"""
Context menu system for Stockshot Browser.
"""

import logging
import subprocess
import platform
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from PySide6.QtCore import Qt, Signal, Slot, QObject
from PySide6.QtWidgets import QMenu, QMessageBox
from PySide6.QtGui import QIcon, QAction

logger = logging.getLogger(__name__)


class ExternalPlayerManager:
    """Manages external media players and applications."""
    
    def __init__(self, config_manager=None):
        self.system = platform.system()
        self.config_manager = config_manager
        self.players = self._detect_players()
        
    def _detect_players(self) -> Dict[str, Dict[str, Any]]:
        """Detect available media players on the system."""
        players = {}
        
        # Get common players from configuration if available
        config_players = {}
        if self.config_manager:
            config_players = self.config_manager.get('external_players.common_players', {})
        
        # Platform-specific defaults (fallback if config not available)
        if self.system == "Linux":
            # Common Linux media players
            player_commands = {
                "VLC": ["vlc", "vlc"],
                "MPV": ["mpv", "mpv"],
                "MPlayer": ["mplayer", "mplayer"],
                "Totem": ["totem", "totem"],
                "GIMP": ["gimp", "gimp"],
                "Krita": ["krita", "krita"],
                "Blender": ["blender", "blender"],
                "DJV": ["djv", "djv_view"],
                "RV": ["rv", "rv"],
                "Nuke": ["Nuke", "Nuke13.2", "Nuke14.0"],
            }
        elif self.system == "Windows":
            # Common Windows media players
            player_commands = {
                "VLC": ["vlc.exe", r"C:\Program Files\VideoLAN\VLC\vlc.exe"],
                "Windows Media Player": ["wmplayer.exe", "wmplayer"],
                "MPC-HC": ["mpc-hc.exe", "mpc-hc64.exe"],
                "PotPlayer": ["PotPlayerMini64.exe", "PotPlayer.exe"],
                "GIMP": ["gimp.exe", r"C:\Program Files\GIMP 2\bin\gimp-2.10.exe"],
                "Krita": ["krita.exe", r"C:\Program Files\Krita\bin\krita.exe"],
                "Blender": ["blender.exe", r"C:\Program Files\Blender Foundation\Blender\blender.exe"],
                "DJV": ["djv.exe", r"C:\Program Files\DJV2\bin\djv.exe"],
                "Nuke": ["Nuke13.2.exe", "Nuke14.0.exe"],
            }
        elif self.system == "Darwin":  # macOS
            # Common macOS media players
            player_commands = {
                "VLC": ["vlc", "/Applications/VLC.app/Contents/MacOS/VLC"],
                "QuickTime": ["open", "-a", "QuickTime Player"],
                "IINA": ["iina", "/Applications/IINA.app/Contents/MacOS/IINA"],
                "GIMP": ["gimp", "/Applications/GIMP.app/Contents/MacOS/GIMP"],
                "Krita": ["krita", "/Applications/krita.app/Contents/MacOS/krita"],
                "Blender": ["blender", "/Applications/Blender.app/Contents/MacOS/Blender"],
                "DJV": ["djv", "/Applications/DJV2.app/Contents/MacOS/djv"],
                "Nuke": ["Nuke13.2", "Nuke14.0"],
            }
        else:
            player_commands = {}
        
        # Merge configuration players with platform defaults
        # Config players take precedence
        for player_key, player_paths in config_players.items():
            player_name = player_key.upper()  # Convert to display name (e.g., 'djv' -> 'DJV')
            if isinstance(player_paths, list):
                player_commands[player_name] = player_paths
            else:
                logger.warning(f"Invalid player configuration for {player_key}: expected list, got {type(player_paths)}")
        
        # Check which players are available
        for name, commands in player_commands.items():
            for cmd in commands:
                if self._check_command_exists(cmd):
                    players[name] = {
                        "command": cmd if isinstance(cmd, list) else [cmd],
                        "name": name,
                        "available": True
                    }
                    break
        
        # Add system default
        if self.system == "Linux":
            players["System Default"] = {
                "command": ["xdg-open"],
                "name": "System Default",
                "available": True
            }
        elif self.system == "Windows":
            players["System Default"] = {
                "command": ["start", ""],
                "name": "System Default",
                "available": True
            }
        elif self.system == "Darwin":
            players["System Default"] = {
                "command": ["open"],
                "name": "System Default",
                "available": True
            }
        
        logger.info(f"Detected {len(players)} media players: {list(players.keys())}")
        return players
    
    def _check_command_exists(self, command: str) -> bool:
        """Check if a command exists on the system."""
        try:
            if self.system == "Windows":
                result = subprocess.run(
                    ["where", command],
                    capture_output=True,
                    text=True,
                    shell=True
                )
            else:
                result = subprocess.run(
                    ["which", command],
                    capture_output=True,
                    text=True
                )
            return result.returncode == 0
        except Exception:
            return False
    
    def open_with_player(self, file_path: str, player_name: str) -> bool:
        """Open a file with a specific player."""
        if player_name not in self.players:
            logger.error(f"Player not found: {player_name}")
            return False
        
        player = self.players[player_name]
        command = player["command"].copy()
        
        # Special handling for Windows "start" command
        if self.system == "Windows" and player_name == "System Default":
            command = ["cmd", "/c", "start", "", file_path]
        else:
            command.append(file_path)
        
        try:
            logger.info(f"Opening {file_path} with {player_name}")
            subprocess.Popen(command)
            return True
        except Exception as e:
            logger.error(f"Failed to open with {player_name}: {e}")
            return False
    
    def get_available_players(self) -> List[str]:
        """Get list of available player names."""
        return list(self.players.keys())


class ContextMenuManager(QObject):
    """Manages context menus for media entities."""
    
    # Signals
    action_triggered = Signal(str, object)  # action_name, entity
    
    def __init__(self, parent=None, config_manager=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.player_manager = ExternalPlayerManager(config_manager)
        self.recent_players = []  # Track recently used players
        self._opening_entities = set()  # Track entities currently being opened to prevent duplicates
        
    def create_entity_menu(self, entities, parent_widget=None) -> QMenu:
        """Create context menu for media entities (single or multiple)."""
        menu = QMenu(parent_widget)
        
        # Support both single entity and multiple entities
        if not isinstance(entities, list):
            entities = [entities]
        
        is_multi_selection = len(entities) > 1
        
        # Open actions
        self._add_open_actions(menu, entities, is_multi_selection)
        
        menu.addSeparator()
        
        # File operations
        self._add_file_operations(menu, entities, is_multi_selection)
        
        menu.addSeparator()
        
        # Metadata actions
        self._add_metadata_actions(menu, entities, is_multi_selection)
        
        menu.addSeparator()
        
        # Favorites and tags
        self._add_favorites_actions(menu, entities, is_multi_selection)
        
        return menu
    
    def _add_open_actions(self, menu: QMenu, entities, is_multi_selection):
        """Add open with player actions."""
        if is_multi_selection:
            # Multi-selection: Open all entities
            default_action = QAction(f"Open All ({len(entities)})", menu)
            default_action.setShortcut("Return")
            default_action.triggered.connect(
                lambda: self._open_multiple_entities(entities, "System Default")
            )
            menu.addAction(default_action)
            
            # Open with submenu for multiple entities
            open_menu = menu.addMenu("Open All With")
            
            # Get available players
            players = self.player_manager.get_available_players()
            
            # Add system default first
            if "System Default" in players:
                action = QAction("System Default", menu)
                action.triggered.connect(
                    lambda: self._open_multiple_entities(entities, "System Default")
                )
                open_menu.addAction(action)
                open_menu.addSeparator()
            
            # Add recently used players
            if self.recent_players:
                for player in self.recent_players[:3]:
                    if player in players and player != "System Default":
                        action = QAction(player, menu)
                        action.triggered.connect(
                            lambda p=player: self._open_multiple_entities(entities, p)
                        )
                        open_menu.addAction(action)
                open_menu.addSeparator()
            
            # Add all available players
            for player in sorted(players):
                if player != "System Default":
                    action = QAction(player, menu)
                    action.triggered.connect(
                        lambda checked, p=player: self._open_multiple_entities(entities, p)
                    )
                    open_menu.addAction(action)
        else:
            # Single selection: Original behavior
            entity = entities[0]
            default_action = QAction("Open", menu)
            default_action.setShortcut("Return")
            default_action.triggered.connect(
                lambda: self._open_with_player(entity, "System Default")
            )
            menu.addAction(default_action)
            
            # Open with submenu (moved below Open)
            open_menu = menu.addMenu("Open With")
            
            # Get available players
            players = self.player_manager.get_available_players()
            
            # Add system default first
            if "System Default" in players:
                action = QAction("System Default", menu)
                action.triggered.connect(
                    lambda: self._open_with_player(entity, "System Default")
                )
                open_menu.addAction(action)
                open_menu.addSeparator()
            
            # Add recently used players
            if self.recent_players:
                for player in self.recent_players[:3]:
                    if player in players and player != "System Default":
                        action = QAction(player, menu)
                        action.triggered.connect(
                            lambda p=player: self._open_with_player(entity, p)
                        )
                        open_menu.addAction(action)
                open_menu.addSeparator()
            
            # Add all available players
            for player in sorted(players):
                if player != "System Default":
                    action = QAction(player, menu)
                    action.triggered.connect(
                        lambda checked, p=player: self._open_with_player(entity, p)
                    )
                    open_menu.addAction(action)
    
    def _add_file_operations(self, menu: QMenu, entities, is_multi_selection):
        """Add file operation actions."""
        if is_multi_selection:
            # Multi-selection operations
            show_action = QAction(f"Show All in File Manager ({len(entities)})", menu)
            show_action.triggered.connect(lambda: self._show_multiple_in_file_manager(entities))
            menu.addAction(show_action)
            
            # Copy paths (multiple)
            copy_path_action = QAction("Copy All Paths", menu)
            copy_path_action.setShortcut("Ctrl+Shift+C")
            copy_path_action.triggered.connect(lambda: self._copy_multiple_paths(entities))
            menu.addAction(copy_path_action)
            
            # Copy names (multiple)
            copy_name_action = QAction("Copy All Names", menu)
            copy_name_action.triggered.connect(lambda: self._copy_multiple_names(entities))
            menu.addAction(copy_name_action)
        else:
            # Single selection operations
            entity = entities[0]
            show_action = QAction("Show in File Manager", menu)
            show_action.triggered.connect(lambda: self._show_in_file_manager(entity))
            menu.addAction(show_action)
            
            # Copy path
            copy_path_action = QAction("Copy Path", menu)
            copy_path_action.setShortcut("Ctrl+Shift+C")
            copy_path_action.triggered.connect(lambda: self._copy_path(entity))
            menu.addAction(copy_path_action)
            
            # Copy name
            copy_name_action = QAction("Copy Name", menu)
            copy_name_action.triggered.connect(lambda: self._copy_name(entity))
            menu.addAction(copy_name_action)
    
    def _add_metadata_actions(self, menu: QMenu, entities, is_multi_selection):
        """Add metadata-related actions."""
        if is_multi_selection:
            # Multi-selection metadata operations
            view_metadata_action = QAction(f"View Metadata ({len(entities)} entities)", menu)
            view_metadata_action.triggered.connect(lambda: self._view_multiple_metadata(entities))
            menu.addAction(view_metadata_action)
            
            # Export metadata for multiple entities
            export_metadata_action = QAction("Export All Metadata...", menu)
            export_metadata_action.triggered.connect(lambda: self._export_multiple_metadata(entities))
            menu.addAction(export_metadata_action)
        else:
            # Single selection metadata operations
            entity = entities[0]
            view_metadata_action = QAction("View Metadata", menu)
            view_metadata_action.triggered.connect(lambda: self._view_metadata(entity))
            menu.addAction(view_metadata_action)
            
            # Export metadata
            export_metadata_action = QAction("Export Metadata...", menu)
            export_metadata_action.triggered.connect(lambda: self._export_metadata(entity))
            menu.addAction(export_metadata_action)
    
    def _add_favorites_actions(self, menu: QMenu, entities, is_multi_selection):
        """Add favorites and tag actions."""
        if is_multi_selection:
            # Multi-selection favorites and tags - add to root menu
            # User favorites for multiple entities
            user_action = QAction(f"Add All to User Favorites ({len(entities)})", menu)
            user_action.setShortcut("F1")
            user_action.triggered.connect(lambda: self._toggle_multiple_user_favorites(entities))
            menu.addAction(user_action)
            
            # Project favorites - always show for multiple selection
            project_action = QAction(f"Add All to Project Favorites ({len(entities)})", menu)
            project_action.setShortcut("F2")
            project_action.triggered.connect(lambda: self._toggle_multiple_project_favorites(entities))
            menu.addAction(project_action)
            
            menu.addSeparator()
            
            # Edit tags for multiple entities
            add_tag_action = QAction(f"Edit Tags to All ({len(entities)})...", menu)
            add_tag_action.triggered.connect(lambda: self._add_tags_to_multiple(entities))
            menu.addAction(add_tag_action)
        else:
            # Single selection favorites and tags - add to root menu
            entity = entities[0]
            user_favorite, project_favorite = self._check_entity_favorite_status(entity)
            
            # User favorites - add to root menu
            user_text = "Remove from User Favorites" if user_favorite else "Add to User Favorites"
            user_action = QAction(user_text, menu)
            user_action.setShortcut("F1")
            user_action.triggered.connect(lambda: self._toggle_user_favorite(entity))
            menu.addAction(user_action)
            
            # Project favorites - always show, use default project if none set
            project_text = "Remove from Project Favorites" if project_favorite else "Add to Project Favorites"
            project_action = QAction(project_text, menu)
            project_action.setShortcut("F2")
            project_action.triggered.connect(lambda: self._toggle_project_favorite(entity))
            menu.addAction(project_action)
            
            menu.addSeparator()
            
            # Edit tags
            add_tag_action = QAction("Edit Tags...", menu)
            add_tag_action.triggered.connect(lambda: self._add_tags(entity))
            menu.addAction(add_tag_action)
    
    def _check_entity_favorite_status(self, entity) -> Tuple[bool, bool]:
        """Check if entity is currently marked as favorite. Returns (user_favorite, project_favorite)."""
        try:
            # Get the parent widget that has app_controller
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if not parent_widget or not hasattr(parent_widget, 'app_controller'):
                return False, False
            
            app_controller = parent_widget.app_controller
            if not app_controller or not hasattr(app_controller, 'config_manager'):
                return False, False
            
            config_manager = app_controller.config_manager
            file_path = str(entity.path)
            
            # Check user favorite
            user_favorite = config_manager.is_user_favorite(file_path)
            
            # Check project favorite - always check since we now always have a project name
            current_project_name = self._get_current_project_name()
            project_favorite = config_manager.is_project_favorite(file_path, current_project_name)
            
            return user_favorite, project_favorite
        except Exception as e:
            logger.debug(f"Error checking favorite status for {entity.name}: {e}")
            return False, False
    
    @Slot()
    def _open_with_player(self, entity, player_name: str):
        """Open entity with specified player."""
        # Create a unique key for this entity to prevent duplicate opens
        entity_key = str(entity.path)
        
        # Check if this entity is already being opened
        if entity_key in self._opening_entities:
            logger.debug(f"Entity {entity.name} is already being opened, ignoring duplicate request")
            return
        
        # Mark entity as being opened
        self._opening_entities.add(entity_key)
        
        try:
            file_path = str(entity.path)
            
            # For sequences, open the first file
            if hasattr(entity, 'files') and entity.files:
                file_path = str(entity.files[0])
            
            success = self.player_manager.open_with_player(file_path, player_name)
            
            if success:
                # Update recent players
                if player_name != "System Default" and player_name not in self.recent_players:
                    self.recent_players.insert(0, player_name)
                    self.recent_players = self.recent_players[:5]  # Keep only 5 recent
                
                self.action_triggered.emit("open", entity)
                logger.info(f"Opened {entity.name} with {player_name}")
            else:
                logger.error(f"Failed to open {entity.name} with {player_name}")
        
        finally:
            # Always remove from opening set after a short delay to allow the process to start
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1000, lambda: self._opening_entities.discard(entity_key))
    
    @Slot()
    def _show_in_file_manager(self, entity):
        """Show entity in system file manager."""
        file_path = str(entity.path)
        
        try:
            system = platform.system()
            if system == "Linux":
                # Try to select the file in the file manager
                subprocess.Popen(["xdg-open", str(entity.path.parent)])
            elif system == "Windows":
                # Open explorer and select the file
                subprocess.Popen(["explorer", "/select,", file_path])
            elif system == "Darwin":
                # Open Finder and select the file
                subprocess.Popen(["open", "-R", file_path])
            
            self.action_triggered.emit("show_in_manager", entity)
            logger.info(f"Showed {entity.name} in file manager")
        except Exception as e:
            logger.error(f"Failed to show in file manager: {e}")
    
    @Slot()
    def _copy_path(self, entity):
        """Copy entity path to clipboard."""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(str(entity.path))
        self.action_triggered.emit("copy_path", entity)
        logger.info(f"Copied path: {entity.path}")
    
    @Slot()
    def _copy_name(self, entity):
        """Copy entity name to clipboard."""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(entity.name)
        self.action_triggered.emit("copy_name", entity)
        logger.info(f"Copied name: {entity.name}")
    
    @Slot()
    def _rename_entity(self, entity):
        """Rename entity (placeholder)."""
        self.action_triggered.emit("rename", entity)
        logger.info(f"Rename requested for: {entity.name}")
    
    @Slot()
    def _delete_entity(self, entity):
        """Delete entity (placeholder)."""
        self.action_triggered.emit("delete", entity)
        logger.info(f"Delete requested for: {entity.name}")
    
    @Slot()
    def _view_metadata(self, entity):
        """View entity metadata."""
        try:
            # Import here to avoid circular imports
            from .metadata_viewer import MetadataViewerWidget
            
            # Get the main window or parent widget
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and hasattr(parent_widget, 'app_controller'):
                # Create metadata viewer window
                metadata_viewer = MetadataViewerWidget(parent_widget.app_controller, parent_widget)
                metadata_viewer.show_entity_metadata(entity)
            else:
                logger.warning("Could not find app_controller for metadata viewer")
            
            self.action_triggered.emit("view_metadata", entity)
            logger.info(f"Metadata viewer opened for: {entity.name}")
            
        except Exception as e:
            logger.error(f"Error opening metadata viewer: {e}")
            # Show error message if possible
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self.parent(),
                    "Metadata Viewer Error",
                    f"Failed to open metadata viewer: {e}"
                )
            except:
                pass
    
    @Slot()
    def _refresh_metadata(self, entity):
        """Refresh entity metadata (placeholder)."""
        self.action_triggered.emit("refresh_metadata", entity)
        logger.info(f"Refresh metadata for: {entity.name}")
    
    @Slot()
    def _export_metadata(self, entity):
        """Export entity metadata."""
        try:
            # Import here to avoid circular imports
            from .export_dialog import ExportDialog
            
            # Get the main window or parent widget
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and hasattr(parent_widget, 'app_controller'):
                # Create export dialog with the selected entity
                dialog = ExportDialog(parent_widget.app_controller, entities=[entity])
                dialog.exec()
            else:
                logger.warning("Could not find app_controller for export dialog")
            
            self.action_triggered.emit("export_metadata", entity)
            logger.info(f"Export metadata dialog opened for: {entity.name}")
            
        except Exception as e:
            logger.error(f"Error opening export dialog: {e}")
            # Show error message if possible
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self.parent(),
                    "Export Error",
                    f"Failed to open export dialog: {e}"
                )
            except:
                pass
    
    def _has_current_project(self) -> bool:
        """Check if there's a current project context."""
        try:
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if not parent_widget or not hasattr(parent_widget, 'app_controller'):
                return False
            
            app_controller = parent_widget.app_controller
            return hasattr(app_controller, 'project_manager') and app_controller.project_manager.current_project is not None
        except Exception:
            return False
    
    def _get_current_project_name(self) -> str:
        """Get current project name if available, otherwise return default."""
        try:
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if not parent_widget or not hasattr(parent_widget, 'app_controller'):
                return "Default"
            
            app_controller = parent_widget.app_controller
            if hasattr(app_controller, 'project_manager') and app_controller.project_manager.current_project:
                return app_controller.project_manager.current_project.name
            return "Default"
        except Exception:
            return "Default"
    
    def _get_current_project_id(self) -> Optional[int]:
        """Get current project ID if available (legacy method for backward compatibility)."""
        try:
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if not parent_widget or not hasattr(parent_widget, 'app_controller'):
                return None
            
            app_controller = parent_widget.app_controller
            if hasattr(app_controller, 'project_manager') and app_controller.project_manager.current_project:
                return app_controller.project_manager.current_project.id
            return None
        except Exception:
            return None
    
    @Slot()
    def _toggle_user_favorite(self, entity):
        """Toggle entity user favorite status."""
        try:
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if not parent_widget or not hasattr(parent_widget, 'app_controller'):
                logger.warning("Could not find app_controller for user favorite toggle")
                return
            
            app_controller = parent_widget.app_controller
            config_manager = app_controller.config_manager
            file_path = str(entity.path)
            
            # Check current status and toggle
            if config_manager.is_user_favorite(file_path):
                # Remove from user favorites
                success = config_manager.remove_user_favorite(file_path)
                action = "removed from" if success else "failed to remove from"
            else:
                # Add to user favorites
                success = config_manager.add_user_favorite(file_path)
                action = "added to" if success else "failed to add to"
            
            if success:
                self.action_triggered.emit("user_favorite_toggled", entity)
                logger.info(f"Entity {entity.name} {action} user favorites")
            else:
                logger.warning(f"Failed to toggle user favorite for {entity.name}")
                
        except Exception as e:
            logger.error(f"Error toggling user favorite for {entity.name}: {e}")
    
    @Slot()
    def _toggle_project_favorite(self, entity):
        """Toggle entity project favorite status."""
        try:
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if not parent_widget or not hasattr(parent_widget, 'app_controller'):
                logger.warning("Could not find app_controller for project favorite toggle")
                return
            
            app_controller = parent_widget.app_controller
            config_manager = app_controller.config_manager
            current_project_name = self._get_current_project_name()  # This now always returns a project name
            
            file_path = str(entity.path)
            
            # Check current status and toggle
            if config_manager.is_project_favorite(file_path, current_project_name):
                # Remove from project favorites
                success = config_manager.remove_project_favorite(file_path, current_project_name)
                action = "removed from" if success else "failed to remove from"
            else:
                # Add to project favorites
                success = config_manager.add_project_favorite(file_path, current_project_name)
                action = "added to" if success else "failed to add to"
            
            if success:
                self.action_triggered.emit("project_favorite_toggled", entity)
                logger.info(f"Entity {entity.name} {action} project favorites ({current_project_name})")
            else:
                logger.warning(f"Failed to toggle project favorite for {entity.name}")
                
        except Exception as e:
            logger.error(f"Error toggling project favorite for {entity.name}: {e}")
    
    @Slot()
    def _add_to_favorites(self, entity):
        """Legacy method - toggle user favorite for backward compatibility."""
        self._toggle_user_favorite(entity)
    
    @Slot()
    def _add_tags(self, entity):
        """Add tags to entity."""
        try:
            # Import here to avoid circular imports
            from .tag_dialog import TagDialog
            
            # Get the main window or parent widget
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and hasattr(parent_widget, 'app_controller'):
                # Create tag dialog
                dialog = TagDialog(entity, parent_widget.app_controller, parent_widget)
                dialog.tags_updated.connect(lambda tags: self._on_tags_updated(entity, tags))
                dialog.exec()
            else:
                logger.warning("Could not find app_controller for tag dialog")

            self.action_triggered.emit("add_tags", entity)
            logger.info(f"Tag dialog opened for: {entity.name}")
            
        except Exception as e:
            logger.error(f"Error opening tag dialog: {e}")
            # Show error message if possible
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self.parent(),
                    "Tag Error",
                    f"Failed to open tag dialog: {e}"
                )
            except:
                pass
    
    def _on_tags_updated(self, entity, tags):
        """Handle tags updated for entity."""
        logger.info(f"Tags updated for {entity.name}: {tags}")
        # Emit a signal that can be caught by the content view to refresh display
        self.action_triggered.emit("tags_updated", entity)
    
    # Multi-entity operation methods
    def _open_multiple_entities(self, entities, player_name: str):
        """Open multiple entities with specified player."""
        for entity in entities:
            self._open_with_player(entity, player_name)
    
    def _show_multiple_in_file_manager(self, entities):
        """Show multiple entities in file manager."""
        for entity in entities:
            self._show_in_file_manager(entity)
    
    def _copy_multiple_paths(self, entities):
        """Copy multiple entity paths to clipboard."""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        paths = [str(entity.path) for entity in entities]
        clipboard.setText('\n'.join(paths))
        self.action_triggered.emit("copy_paths", entities)
        logger.info(f"Copied {len(paths)} paths to clipboard")
    
    def _copy_multiple_names(self, entities):
        """Copy multiple entity names to clipboard."""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        names = [entity.name for entity in entities]
        clipboard.setText('\n'.join(names))
        self.action_triggered.emit("copy_names", entities)
        logger.info(f"Copied {len(names)} names to clipboard")
    
    def _view_multiple_metadata(self, entities):
        """View metadata for multiple entities."""
        # For now, just view the first entity's metadata
        # Could be enhanced to show a combined view
        if entities:
            self._view_metadata(entities[0])
    
    def _export_multiple_metadata(self, entities):
        """Export metadata for multiple entities."""
        try:
            # Import here to avoid circular imports
            from .export_dialog import ExportDialog
            
            # Get the main window or parent widget
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and hasattr(parent_widget, 'app_controller'):
                # Create export dialog with multiple entities
                dialog = ExportDialog(parent_widget.app_controller, entities=entities)
                dialog.exec()
            else:
                logger.warning("Could not find app_controller for export dialog")
            
            self.action_triggered.emit("export_metadata", entities)
            logger.info(f"Export metadata dialog opened for {len(entities)} entities")
            
        except Exception as e:
            logger.error(f"Error opening export dialog: {e}")
    
    def _toggle_multiple_user_favorites(self, entities):
        """Toggle user favorite status for multiple entities."""
        for entity in entities:
            self._toggle_user_favorite(entity)
    
    def _toggle_multiple_project_favorites(self, entities):
        """Toggle project favorite status for multiple entities."""
        for entity in entities:
            self._toggle_project_favorite(entity)
    
    def _add_tags_to_multiple(self, entities):
        """Add tags to multiple entities."""
        try:
            # Import here to avoid circular imports
            from .tag_dialog import TagDialog
            
            # Get the main window or parent widget
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'app_controller'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and hasattr(parent_widget, 'app_controller'):
                # Create tag dialog for multiple entities
                dialog = TagDialog(entities, parent_widget.app_controller, parent_widget)
                dialog.tags_updated.connect(lambda tags: self._on_multiple_tags_updated(entities, tags))
                dialog.exec()
            else:
                logger.warning("Could not find app_controller for tag dialog")
            
            self.action_triggered.emit("add_tags", entities)
            logger.info(f"Tag dialog opened for {len(entities)} entities")
            
        except Exception as e:
            logger.error(f"Error opening tag dialog: {e}")
            # Show error message if possible
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self.parent(),
                    "Tag Error",
                    f"Failed to open tag dialog: {e}"
                )
            except:
                pass
    
    def _on_multiple_tags_updated(self, entities, tags):
        """Handle tags updated for multiple entities with batch refresh."""
        logger.info(f"Tags updated for {len(entities)} entities: {tags}")
        
        # Emit a signal for each entity to refresh display
        for entity in entities:
            self.action_triggered.emit("tags_updated", entity)
        
        # Also emit a batch update signal if the content view supports it
        self.action_triggered.emit("multiple_tags_updated", entities)
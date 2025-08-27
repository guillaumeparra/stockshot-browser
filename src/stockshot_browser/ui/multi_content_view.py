"""
Multi-context Content view widget for Stockshot Browser.

Context-aware content view that switches database and thumbnail contexts based on path.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QComboBox, QGridLayout,
    QFrame, QSizePolicy, QProgressBar,
    QAbstractItemView, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QSplitter, QApplication
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, Slot, QByteArray, QBuffer, QIODevice, QMimeData, QUrl, QPoint, QRect
from PySide6.QtGui import QPixmap, QFont, QPalette, QMovie, QDrag, QPainter, QPen, QBrush, QColor

from ..core.multi_entity_manager import MediaEntity, EntityType
from ..core.path_context_manager import ContextType
from .drag_drop_mixin import DragDropMixin
from .context_menu import ContextMenuManager
from .theme_utils import theme_manager

logger = logging.getLogger(__name__)


class RubberBandOverlay(QWidget):
    """Transparent overlay widget for rubber band selection that covers the entire scroll area."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Initially make the overlay transparent to mouse events so entity clicks work
        # self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # self.setAttribute(Qt.WA_TranslucentBackground, True)
        # self.setStyleSheet("background: rgba(0,0,0,0);")  # Fully transparent background
        
        # Ensure the widget is visible and on top
        self.show()
        self.raise_()
        
        self.rubber_band_active = False
        self.rubber_band_start = QPoint()
        self.rubber_band_current = QPoint()
        self.rubber_band_rect = QRect()
        
        # Reference to content view for selection updates
        self.content_view = None
        self.scroll_area = None
    
    def set_content_view(self, content_view):
        """Set reference to content view for selection updates."""
        self.content_view = content_view
        self.scroll_area = content_view.scroll_area
    
    def mousePressEvent(self, event):
        """Start rubber band selection with modifier support."""
        if event.button() == Qt.LeftButton:
            self.rubber_band_active = True
            self.rubber_band_start = event.pos()
            self.rubber_band_current = event.pos()
            self.rubber_band_rect = QRect(self.rubber_band_start, self.rubber_band_current).normalized()
            
            # Handle selection clearing based on modifier keys
            modifiers = QApplication.keyboardModifiers()
            shift_pressed = bool(modifiers & Qt.ShiftModifier)
            ctrl_pressed = bool(modifiers & Qt.ControlModifier)
            
            if self.content_view:
                if shift_pressed:
                    # Shift+rubber band: Append mode - keep existing selection
                    pass  # Don't clear selection
                elif ctrl_pressed:
                    # Ctrl+rubber band: Remove mode - keep existing selection
                    pass  # Don't clear selection
                else:
                    # Normal rubber band: Replace mode - clear existing selection
                    self.content_view.clear_selection()
            
            self.update()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Update rubber band selection."""
        if self.rubber_band_active:
            self.rubber_band_current = event.pos()
            self.rubber_band_rect = QRect(self.rubber_band_start, self.rubber_band_current).normalized()
            
            
            # Update selection
            if self.content_view:
                self.content_view._update_rubber_band_selection_from_overlay(self.rubber_band_rect)
            
            self.update()
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """End rubber band selection."""
        if event.button() == Qt.LeftButton and self.rubber_band_active:
            self.rubber_band_active = False
            
            # Final selection update
            if self.content_view:
                self.content_view._update_rubber_band_selection_from_overlay(self.rubber_band_rect)
            
            # Clear rubber band
            self.rubber_band_rect = QRect()
            
            self.update()
        super().mouseReleaseEvent(event)
    
    def paintEvent(self, event):
        """Paint the rubber band rectangle."""
        super().paintEvent(event)
        
        if self.rubber_band_active and not self.rubber_band_rect.isEmpty():
            painter = QPainter(self)
            
            # Get dynamic rubber band colors from theme
            colors = theme_manager.get_rubber_band_colors()
            outline_color = colors['border']
            bg_color = colors['background']
            
            # Convert string colors to QColor objects
            outline_qcolor = QColor(outline_color)
            background_qcolor = QColor(bg_color[0], bg_color[1], bg_color[2], bg_color[3])

            # Set up rubber band style with theme colors
            pen = QPen(outline_qcolor, 1, Qt.SolidLine)
            brush = QBrush(background_qcolor)
            
            painter.setPen(pen)
            painter.setBrush(brush)
            
            # Draw the rubber band rectangle
            painter.drawRect(self.rubber_band_rect)


class EntityThumbnailWidget(QFrame):
    """Widget displaying a single entity with thumbnail and metadata."""

    # Signals
    entity_selected = Signal(object, bool, bool)  # MediaEntity, ctrl_pressed, shift_pressed
    entity_double_clicked = Signal(object)  # MediaEntity


    def __init__(self, entity: MediaEntity, thumbnail_path: Optional[str] = None,
                 animated_path: Optional[str] = None, app_controller=None):
        super().__init__()
        self.entity = entity
        self.thumbnail_path = thumbnail_path
        self.animated_path = animated_path
        self.app_controller = app_controller
        self.movie = None
        self.static_pixmap = None
        self.is_hovering = False
        self.drag_start_position = None
        
        self._setup_ui()
        self._load_thumbnail()
    
    def _setup_ui(self):
        """Setup the thumbnail widget UI."""
        self.setFrameStyle(QFrame.Box)
        self.setLineWidth(1)
        self.setFixedSize(150, 180)
        
        # Get base background color and make it 10% lighter
        base_bg = "#2b2b2b"  # Dark theme base color
        lighter_bg = self._lighten_color(base_bg, 0.1)
        
        self.setStyleSheet(f"""
            EntityThumbnailWidget {{
                border: 1px solid #555;
                border-radius: 4px;
                background-color: {lighter_bg};
            }}
            EntityThumbnailWidget:hover {{
                border: 2px solid #0078d4;
                background-color: #3a3a3a;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        # Create thumbnail container with overlay for favorite dots
        thumbnail_container = QWidget()
        thumbnail_container.setFixedSize(140, 100)
        thumbnail_layout = QVBoxLayout(thumbnail_container)
        thumbnail_layout.setContentsMargins(0, 0, 0, 0)
        thumbnail_layout.setAlignment(Qt.AlignCenter)  # Center the QLabel within container
        
        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(140, 100)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet(f"border: 1px solid #555; background-color: {lighter_bg};")
        
        # Note: Favorite icons will be displayed inline with the filename
        # No separate icon widgets needed - they'll be part of the name label text
        
        thumbnail_layout.addWidget(self.thumbnail_label, 0, Qt.AlignCenter)
        layout.addWidget(thumbnail_container)
        
        # Entity name
        self.name_label = QLabel(self.entity.name)
        self.name_label.setObjectName("name_label")
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        self.name_label.setFont(font)
        self.name_label.setStyleSheet("color: white;")
        layout.addWidget(self.name_label)
        
        # Entity info
        info_text = self._get_entity_info_text()
        self.info_label = QLabel(info_text)
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(7)
        self.info_label.setFont(font)
        self.info_label.setStyleSheet("color: white;")
        layout.addWidget(self.info_label)
        
        # Tags display
        self.tags_label = QLabel()
        self.tags_label.setWordWrap(True)
        self.tags_label.setAlignment(Qt.AlignCenter)
        self.tags_label.setMaximumHeight(30)
        font = QFont()
        font.setPointSize(6)
        self.tags_label.setFont(font)
        self.tags_label.setStyleSheet("color: white; background-color: rgba(68, 138, 255, 0.2); border-radius: 3px; padding: 2px;")
        layout.addWidget(self.tags_label)
        
        # Load and display tags
        self._update_tags_display()
        
        layout.addStretch()
    
    def _get_entity_info_text(self) -> str:
        """Get entity information text."""
        info_parts = []
        
        # Get file extension for display
        if len(self.entity.files) > 1:
            # For sequences, use extension from first file
            first_file_path = Path(self.entity.files[0])
            file_ext = first_file_path.suffix.lstrip('.').lower()
        else:
            # For single files, use the entity path extension
            file_ext = self.entity.path.suffix.lstrip('.').lower()
        
        # Entity type with frame count and file extension
        if self.entity.entity_type == EntityType.VIDEO:
            # Check if this is actually an image sequence (multiple files) or a real video
            if len(self.entity.files) > 1:
                info_parts.append(f"Sequence ({file_ext}) ({len(self.entity.files)} frames)")
                # Frame range for sequences
                if self.entity.frame_range:
                    info_parts.append(f"Range: {self.entity.frame_range[0]}-{self.entity.frame_range[1]}")
            elif len(self.entity.files) == 1 and self.entity.frame_count == 1:
                # Single image file
                info_parts.append(f"Image ({file_ext})")
            else:
                # Real video file
                info_parts.append(f"Video ({file_ext})")
                # Try to get frame count from metadata
                frame_count = self._get_frame_count()
                if frame_count:
                    info_parts.append(f"Frames: {frame_count}")
        else:
            # Fallback for SEQUENCE type (should not occur with new implementation)
            if len(self.entity.files) > 1:
                info_parts.append(f"Sequence ({file_ext}) ({len(self.entity.files)} frames)")
                # Frame range for sequences
                if self.entity.frame_range:
                    info_parts.append(f"Range: {self.entity.frame_range[0]}-{self.entity.frame_range[1]}")
            else:
                info_parts.append(f"Image ({file_ext})")
        
        # Resolution
        resolution = self._get_resolution()
        if resolution:
            info_parts.append(f"{resolution}")
        
        # File size
        if self.entity.file_size:
            size_mb = self.entity.file_size / (1024 * 1024)
            if size_mb >= 1:
                info_parts.append(f"{size_mb:.1f} MB")
            else:
                size_kb = self.entity.file_size / 1024
                info_parts.append(f"{size_kb:.1f} KB")
        
        return "\n".join(info_parts)
    
    def _get_frame_count(self) -> Optional[str]:
        """Get frame count from metadata for videos."""
        if not self.app_controller or not hasattr(self.app_controller, 'database_manager'):
            return None
        
        try:
            with self.app_controller.database_manager.get_session() as session:
                from ..database.models import Metadata, Entity
                
                # Find the entity in database
                db_entity = session.query(Entity).filter_by(
                    path=str(self.entity.path),
                    entity_type=self.entity.entity_type.value
                ).first()
                
                if db_entity:
                    # Look for frame count in metadata
                    metadata_records = session.query(Metadata).filter_by(
                        entity_id=db_entity.id
                    ).all()
                    
                    for meta in metadata_records:
                        # Check direct field first
                        if meta.frame_count:
                            return str(meta.frame_count)
                        
                        # Check custom fields if direct field is not available
                        if meta.custom_fields:
                            try:
                                import json
                                custom_data = json.loads(meta.custom_fields)
                                
                                # Look for frame count in custom fields
                                if 'nb_frames' in custom_data:
                                    return str(custom_data['nb_frames'])
                                elif 'frame_count' in custom_data:
                                    return str(custom_data['frame_count'])
                                elif 'streams' in custom_data:
                                    for stream in custom_data['streams']:
                                        if stream.get('codec_type') == 'video' and 'nb_frames' in stream:
                                            return str(stream['nb_frames'])
                                        
                            except json.JSONDecodeError:
                                continue
                                
        except Exception as e:
            logger.debug(f"Error getting frame count for {self.entity.name}: {e}")
        
        return None
    
    def _get_resolution(self) -> Optional[str]:
        """Get resolution from metadata."""
        if not self.app_controller or not hasattr(self.app_controller, 'database_manager'):
            return None
        
        try:
            with self.app_controller.database_manager.get_session() as session:
                from ..database.models import Metadata, Entity
                
                # Find the entity in database
                db_entity = session.query(Entity).filter_by(
                    path=str(self.entity.path),
                    entity_type=self.entity.entity_type.value
                ).first()
                
                if db_entity:
                    # Look for resolution in metadata
                    metadata_records = session.query(Metadata).filter_by(
                        entity_id=db_entity.id
                    ).all()
                    
                    for meta in metadata_records:
                        # Check direct fields first
                        if meta.width and meta.height:
                            return f"{meta.width}×{meta.height}"
                        
                        # Check custom fields if direct fields are not available
                        if meta.custom_fields:
                            try:
                                import json
                                custom_data = json.loads(meta.custom_fields)
                                
                                # Look for resolution in custom fields
                                width = height = None
                                
                                if 'width' in custom_data and 'height' in custom_data:
                                    width = custom_data['width']
                                    height = custom_data['height']
                                elif 'streams' in custom_data:
                                    for stream in custom_data['streams']:
                                        if stream.get('codec_type') == 'video':
                                            if 'width' in stream and 'height' in stream:
                                                width = stream['width']
                                                height = stream['height']
                                                break
                                
                                if width and height:
                                    return f"{width}×{height}"
                                        
                            except json.JSONDecodeError:
                                continue
                                
        except Exception as e:
            logger.debug(f"Error getting resolution for {self.entity.name}: {e}")
        
        return None
    
    def _load_thumbnail(self):
        """Load and display thumbnail."""
        # Load static thumbnail
        if self.thumbnail_path and Path(self.thumbnail_path).exists():
            try:
                pixmap = QPixmap(self.thumbnail_path)
                if not pixmap.isNull():
                    # Apply color management if available
                    if (self.app_controller and
                        hasattr(self.app_controller, 'color_manager') and
                        self.app_controller.color_manager and
                        self.app_controller.color_manager.is_available()):
                        
                        color_config = self.app_controller.config_manager.get('color_management', {})
                        if color_config.get('apply_to_thumbnails', True):
                            try:
                                # Apply color transform to thumbnail
                                pixmap = self.app_controller.color_manager.transform_pixmap(
                                    pixmap,
                                    source_colorspace='sRGB'  # Assume thumbnails are in sRGB
                                )
                                logger.debug(f"Applied color management to thumbnail: {self.entity.name}")
                            except Exception as e:
                                logger.warning(f"Color management failed for thumbnail {self.entity.name}: {e}")
                    
                    # Calculate proper label size based on pixmap aspect ratio
                    self._resize_thumbnail_label_for_aspect_ratio(pixmap.size())
                    
                    # Scale pixmap to fit the resized label
                    self.static_pixmap = pixmap.scaled(
                        self.thumbnail_label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.thumbnail_label.setPixmap(self.static_pixmap)
                    
                    # Load animated thumbnail if available
                    if self.animated_path and Path(self.animated_path).exists():
                        self._load_animated_thumbnail()
                    
                    # Check and update favorite status
                    self._update_favorite_status()
                    return
            except Exception as e:
                logger.warning(f"Error loading thumbnail {self.thumbnail_path}: {e}")
        
        # Show placeholder
        self._show_placeholder()
        # Check and update favorite status even for placeholders
        self._update_favorite_status()
    
    def _load_animated_thumbnail(self):
        """Load animated thumbnail (GIF) for hover playback."""
        try:
            logger.debug(f"🎬 Loading animated thumbnail for {self.entity.name} from {self.animated_path}")
            self.movie = QMovie(self.animated_path)
            
            if self.movie.isValid():
                logger.debug(f"🎬 Movie is valid for {self.entity.name}")
                
                # The thumbnail label has already been resized to the correct aspect ratio
                # Just let the movie fill the label naturally - no scaling needed
                logger.debug(f"🎬 Movie will use label size {self.thumbnail_label.size()} for {self.entity.name}")
                logger.debug(f"🎬 Movie state after loading: {self.movie.state()} for {self.entity.name}")
                
                # Don't start playing yet - wait for hover
                logger.debug(f"🎬 Animated thumbnail ready for {self.entity.name}")
            else:
                self.movie = None
                logger.warning(f"🎬 Invalid animated thumbnail: {self.animated_path}")
        except Exception as e:
            logger.warning(f"🎬 Error loading animated thumbnail {self.animated_path}: {e}")
            self.movie = None
    
    def _resize_thumbnail_label_for_aspect_ratio(self, image_size):
        """Resize the thumbnail label to maintain aspect ratio within the available space."""
        # Available space in the container (140x100)
        max_width = 140
        max_height = 100
        
        # Calculate aspect ratio
        if image_size.width() > 0 and image_size.height() > 0:
            aspect_ratio = image_size.width() / image_size.height()
            
            # Calculate new size maintaining aspect ratio
            if aspect_ratio > (max_width / max_height):
                # Image is wider - fit by width
                new_width = max_width
                new_height = int(max_width / aspect_ratio)
            else:
                # Image is taller - fit by height
                new_height = max_height
                new_width = int(max_height * aspect_ratio)
            
            # Resize the thumbnail label and ensure it's centered
            self.thumbnail_label.setFixedSize(new_width, new_height)
            
            # Update the layout to ensure proper centering
            thumbnail_container = self.thumbnail_label.parent()
            if thumbnail_container:
                layout = thumbnail_container.layout()
                if layout:
                    # Remove and re-add with center alignment to ensure centering
                    layout.removeWidget(self.thumbnail_label)
                    layout.addWidget(self.thumbnail_label, 0, Qt.AlignCenter)
            
            logger.debug(f"Resized and centered thumbnail label for {self.entity.name} from {image_size} to {new_width}x{new_height}")
        else:
            # Fallback to default size if image size is invalid
            self.thumbnail_label.setFixedSize(max_width, max_height)
    
    def _update_favorite_status(self):
        """Update the favorite dots visibility based on entity favorite status."""
        if self.app_controller and hasattr(self.app_controller, 'config_manager'):
            try:
                config_manager = self.app_controller.config_manager
                file_path = str(self.entity.path)
                
                # Check user favorite
                user_favorite = config_manager.is_user_favorite(file_path)
                
                # Check project favorite - always check since we now always have a project name
                current_project_name = self._get_current_project_name()
                project_favorite = config_manager.is_project_favorite(file_path, current_project_name)
                
                self.set_favorite_status(user_favorite, project_favorite)
            except Exception as e:
                logger.debug(f"Error checking favorite status: {e}")
                self.set_favorite_status(False, False)
        else:
            self.set_favorite_status(False, False)
    
    def _show_placeholder(self):
        """Show placeholder when no thumbnail is available."""
        # Use folder icon for multi-file sequences, film icon for videos/single images
        if len(self.entity.files) > 1:
            placeholder_text = "📁"  # Multi-file sequence
        else:
            placeholder_text = "🎬"  # Single video or image file
        self.thumbnail_label.setText(placeholder_text)
        base_bg = "#2b2b2b"
        lighter_bg = self._lighten_color(base_bg, 0.15)
        self.thumbnail_label.setStyleSheet(f"""
            border: 1px solid #555;
            background-color: {lighter_bg};
            font-size: 24px;
            color: #ccc;
        """)
    
    def _lighten_color(self, hex_color: str, factor: float) -> str:
        """Lighten a hex color by a given factor (0.0 to 1.0)."""
        # Remove # if present
        hex_color = hex_color.lstrip('#')
        
        # Convert to RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        # Lighten each component
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def _get_current_project_name(self) -> str:
        """Get current project name if available, with fallback to 'Default'."""
        try:
            if (self.app_controller and
                hasattr(self.app_controller, 'project_manager') and
                self.app_controller.project_manager.current_project):
                return self.app_controller.project_manager.current_project.name
            return "Default"  # Fallback to ensure project favorites always work
        except Exception:
            return "Default"
    
    def _get_current_project_id(self) -> Optional[int]:
        """Get current project ID if available (legacy method for backward compatibility)."""
        try:
            if (self.app_controller and
                hasattr(self.app_controller, 'project_manager') and
                self.app_controller.project_manager.current_project):
                return self.app_controller.project_manager.current_project.id
            return None
        except Exception:
            return None
    
    def set_favorite_status(self, user_favorite: bool, project_favorite: bool):
        """Set the favorite status and show appropriate icons inline with filename."""
        # Get base background color and make it 10% lighter
        base_bg = "#2b2b2b"  # Dark theme base color
        lighter_bg = self._lighten_color(base_bg, 0.1)
        
        # Check if this widget is currently selected by looking for selection styling
        current_style = self.styleSheet()
        is_selected = "border: 3px solid #0078d4" in current_style
        
        if is_selected:
            # Preserve selection styling
            self.setStyleSheet(f"""
                EntityThumbnailWidget {{
                    border: 3px solid #0078d4;
                    border-radius: 4px;
                    background-color: rgba(0, 120, 212, 0.15);
                }}
                EntityThumbnailWidget:hover {{
                    border: 3px solid #0078d4;
                    background-color: rgba(0, 120, 212, 0.25);
                }}
            """)
        else:
            # Use default styling
            self.setStyleSheet(f"""
                EntityThumbnailWidget {{
                    border: 1px solid #555;
                    border-radius: 4px;
                    background-color: {lighter_bg};
                }}
                EntityThumbnailWidget:hover {{
                    border: 2px solid #0078d4;
                    background-color: #3a3a3a;
                }}
            """)
        
        # Update the name label to include favorite icons inline using SVG icons
        base_name = self.entity.name
        favorite_icons = ""
        
        if user_favorite and project_favorite:
            # Both user and project favorite - show both SVG icons as text
            user_icon = self._load_svg_icon_as_text("icon_user_favorite.svg")
            project_icon = self._load_svg_icon_as_text("icon_project_favorite.svg")
            favorite_icons = f" {user_icon}{project_icon}"
        elif user_favorite:
            # User favorite only - show star SVG icon as text
            user_icon = self._load_svg_icon_as_text("icon_user_favorite.svg")
            favorite_icons = f" {user_icon}"
        elif project_favorite:
            # Project favorite only - show diamond SVG icon as text
            project_icon = self._load_svg_icon_as_text("icon_project_favorite.svg")
            favorite_icons = f" {project_icon}"
        
        # Update the name label text with icons
        self.name_label.setText(base_name + favorite_icons)
    
    def _load_svg_icon_as_text(self, icon_filename: str) -> str:
        """Load SVG icon and return as text symbol (fallback to emoji if SVG not available)."""
        try:
            # Get the absolute path to the resources directory
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent  # Go up to project root
            icon_path = project_root / "src" / "stockshot_browser" / "resources" / icon_filename
            
            if icon_path.exists():
                # For now, return Unicode symbols that look similar to the icons
                # In a full implementation, you could render SVG to a small pixmap and embed it
                if icon_filename == "icon_user_favorite.svg":
                    return "★"  # Unicode star for user favorites
                elif icon_filename == "icon_project_favorite.svg":
                    return "◆"  # Unicode diamond for project favorites
                else:
                    return "●"  # Fallback symbol
            else:
                # Fallback to emoji symbols if SVG not found
                if icon_filename == "icon_user_favorite.svg":
                    return "⭐"
                elif icon_filename == "icon_project_favorite.svg":
                    return "🔶"
                else:
                    return "●"
        except Exception as e:
            logger.debug(f"Error loading SVG icon {icon_filename}: {e}")
            # Fallback to emoji symbols on error
            if icon_filename == "icon_user_favorite.svg":
                return "⭐"
            elif icon_filename == "icon_project_favorite.svg":
                return "🔶"
            else:
                return "●"
    
    def set_favorite(self, is_favorite: bool):
        """Legacy method for backward compatibility."""
        self.set_favorite_status(is_favorite, False)
        
    def is_favorite(self) -> bool:
        """Check if entity is marked as favorite."""
        if not self.app_controller:
            return False
        
        # Check if entity is in favorites (this would need to be implemented in the database)
        # For now, return False as placeholder
        return False
    
    def update_thumbnail(self, thumbnail_path: str, animated_path: Optional[str] = None):
        """Update the thumbnail."""
        self.thumbnail_path = thumbnail_path
        self.animated_path = animated_path
        
        # Stop any playing movie
        if self.movie:
            self.movie.stop()
            self.movie = None
        
        self._load_thumbnail()
    
    def _update_tags_display(self):

        """Update the tags display for this entity."""
        if not self.app_controller or not hasattr(self.app_controller, 'database_manager'):
            self.tags_label.setVisible(False)
            return
        
        try:
            with self.app_controller.database_manager.get_session(for_tags=True) as session:
                from ..database.models import Tag, Entity, entity_tags

                # Find the entity in database
                db_entity = session.query(Entity).filter_by(
                    path=str(self.entity.path),
                    entity_type=self.entity.entity_type.value
                ).first()

                if db_entity:
                    # Get entity tags
                    tags = session.query(Tag).join(entity_tags).filter(
                        entity_tags.c.entity_id == db_entity.id
                    ).all()
                    if tags:
                        tag_names = [tag.name for tag in tags]
                        self._display_tags(tag_names)
                    else:
                        self.tags_label.setVisible(False)
                else:
                    self.tags_label.setVisible(False)
                    
        except Exception as e:
            logger.debug(f"Error loading tags for {self.entity.name}: {e}")
            self.tags_label.setVisible(False)
    
    def _display_tags(self, tag_names):
        """Display tags with truncation if too many."""
        if not tag_names:
            self.tags_label.setVisible(False)
            return
        
        # Sort tags for consistent display
        sorted_tags = sorted(tag_names)
        
        # Create display text with truncation
        max_display_length = 40  # Maximum characters to display
        full_text = ", ".join(sorted_tags)
        
        if len(full_text) <= max_display_length:
            display_text = full_text
            tooltip_text = f"Tags: {full_text}"
        else:
            # Truncate and add ellipsis
            truncated = full_text[:max_display_length-3] + "..."
            display_text = truncated
            tooltip_text = f"Tags: {full_text}"
        
        # Update label
        self.tags_label.setText(f"🏷️ {display_text}")
        self.tags_label.setToolTip(tooltip_text)
        self.tags_label.setVisible(True)
    
    def enterEvent(self, event):
        """Handle mouse enter - start playing animated thumbnail without scaling."""
        super().enterEvent(event)
        self.is_hovering = True
        
        if self.movie:
            if self.movie.isValid():
                # Set the movie's scaled size to match the current label size to prevent auto-scaling
                current_size = self.thumbnail_label.size()
                self.movie.setScaledSize(current_size)
                
                # Connect the movie to the label and start playing
                self.thumbnail_label.setMovie(self.movie)
                self.movie.start()
            else:
                logger.debug(f"Movie is invalid, cannot start for {self.entity.name}")
        else:
            logger.debug(f"No movie available for {self.entity.name}")
    
    def leaveEvent(self, event):
        """Handle mouse leave - stop playing animated thumbnail."""
        super().leaveEvent(event)
        self.is_hovering = False
        
        if self.movie:
            if self.movie.state() == QMovie.Running:
                # Stop the movie and restore static thumbnail
                self.movie.stop()
                
                if self.static_pixmap:
                    self.thumbnail_label.setPixmap(self.static_pixmap)
    
    def mousePressEvent(self, event):
        """Handle mouse press with multi-selection support."""
        if event.button() == Qt.LeftButton:
            # Check current selection state BEFORE processing click
            content_view = self.parent()
            while content_view and not isinstance(content_view, MultiContentViewWidget):
                content_view = content_view.parent()
            
            if content_view:
                current_selection = content_view.get_selected_entities()
            
            self.drag_start_position = event.pos()
            
            # Check for keyboard modifiers for multi-selection
            modifiers = QApplication.keyboardModifiers()
            ctrl_pressed = bool(modifiers & Qt.ControlModifier)
            shift_pressed = bool(modifiers & Qt.ShiftModifier)
            
            # CRITICAL FIX: If multiple entities are selected and this is a drag start (not a selection change),
            # don't emit the selection signal that would clear the selection
            if content_view and len(current_selection) > 1:
                # Check if current entity is already in selection
                current_entity_selected = any(str(e.path) == str(self.entity.path) for e in current_selection)
                
                if current_entity_selected and not ctrl_pressed and not shift_pressed:
                    # This is likely a drag start on an already-selected entity in a multi-selection
                    # Don't emit selection signal to avoid clearing the selection
                    pass  # Don't call self.entity_selected.emit() here
                else:
                    # Normal selection behavior
                    self.entity_selected.emit(self.entity, ctrl_pressed, shift_pressed)
            else:
                # Normal selection behavior for single selection or first selection
                self.entity_selected.emit(self.entity, ctrl_pressed, shift_pressed)
                
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for drag operations."""
        if not (event.buttons() & Qt.LeftButton):
            return
        
        if not self.drag_start_position:
            return
        
        # Calculate distance moved
        distance = (event.pos() - self.drag_start_position).manhattanLength()
        min_distance = QApplication.startDragDistance()
        
        # Check if we've moved far enough to start a drag
        if distance < min_distance:
            return
        
        # Start drag operation
        self._start_drag()
        super().mouseMoveEvent(event)
    
    def _start_drag(self):
        """Start drag operation with entity file path(s) - supports multi-selection."""
        # Get the content view widget to check for multi-selection
        content_view = self.parent()
        while content_view and not isinstance(content_view, MultiContentViewWidget):
            content_view = content_view.parent()
        
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Determine drag content based on selection
        if content_view:
            selected_entities = content_view.get_selected_entities()
            
            if len(selected_entities) > 1:
                # Multi-entity drag - get all selected entities
                file_paths = [str(entity.path) for entity in selected_entities]
                
                # Set multiple file paths as plain text (one per line)
                text_content = '\n'.join(file_paths)
                mime_data.setText(text_content)
                
                # Set as HTML for better text editor compatibility
                html_content = '<br>'.join(file_paths)
                mime_data.setHtml(html_content)
                
                # Set as URLs for file manager compatibility
                urls = [QUrl.fromLocalFile(file_path) for file_path in file_paths]
                mime_data.setUrls(urls)
                
                # Set custom MIME types for maximum compatibility
                mime_data.setData("text/plain", text_content.encode('utf-8'))
                mime_data.setData("text/uri-list", '\n'.join([QUrl.fromLocalFile(fp).toString() for fp in file_paths]).encode('utf-8'))
                
                # Use a generic multi-file icon or the first entity's thumbnail
                if self.static_pixmap:
                    drag_pixmap = self.static_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    # Add a small indicator for multiple files
                    from PySide6.QtGui import QPainter, QFont
                    painter = QPainter(drag_pixmap)
                    painter.setFont(QFont("Arial", 8, QFont.Bold))
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(drag_pixmap.rect().bottomRight() - QPoint(15, 5), f"{len(selected_entities)}")
                    painter.end()
                    drag.setPixmap(drag_pixmap)
            else:
                # Single entity drag
                file_path = str(self.entity.path)
                
                # Set as plain text
                mime_data.setText(file_path)
                
                # Set as HTML for better text editor compatibility
                mime_data.setHtml(file_path)
                
                # Set as URL for file manager compatibility
                urls = [QUrl.fromLocalFile(file_path)]
                mime_data.setUrls(urls)
                
                # Set custom MIME types for maximum compatibility
                mime_data.setData("text/plain", file_path.encode('utf-8'))
                mime_data.setData("text/uri-list", QUrl.fromLocalFile(file_path).toString().encode('utf-8'))
                
                # Use thumbnail as drag pixmap if available
                if self.static_pixmap:
                    drag.setPixmap(self.static_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            # Fallback: single entity drag
            file_path = str(self.entity.path)
            mime_data.setText(file_path)
            mime_data.setData("text/plain", file_path.encode('utf-8'))
            
            if self.static_pixmap:
                drag.setPixmap(self.static_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        # Set the MIME data on the drag object
        drag.setMimeData(mime_data)
        
        # Execute drag with all possible actions
        drag.exec_(Qt.CopyAction | Qt.MoveAction | Qt.LinkAction, Qt.CopyAction)
    
    def mouseDoubleClickEvent(self, event):
        """Handle mouse double click."""
        if event.button() == Qt.LeftButton:
            # Get the content view widget to access the open functionality
            content_view = self.parent()
            while content_view and not isinstance(content_view, MultiContentViewWidget):
                content_view = content_view.parent()
            
            if content_view:
                content_view._open_entity_with_default_player(self.entity)
            
            self.entity_double_clicked.emit(self.entity)
        super().mouseDoubleClickEvent(event)
    
    def contextMenuEvent(self, event):
        """Handle context menu event."""
        # Get the content view widget (parent's parent)
        content_view = self.parent()
        while content_view and not isinstance(content_view, MultiContentViewWidget):
            content_view = content_view.parent()
        
        if content_view and hasattr(content_view, 'context_menu_manager'):
            # Check if multiple entities are selected
            selected_entities = content_view.get_selected_entities()
            
            if len(selected_entities) > 1:
                # Multiple entities selected - pass all selected entities to context menu
                entities_for_menu = selected_entities
            else:
                # Single entity or no selection - use this entity
                entities_for_menu = self.entity
            
            menu = content_view.context_menu_manager.create_entity_menu(entities_for_menu, self)
            menu.exec_(event.globalPos())


class MultiEntityThumbnailWidget(EntityThumbnailWidget):
    """Custom entity thumbnail widget for multi-context content view."""
    
    def __init__(self, entity: MediaEntity, thumbnail_path: Optional[str] = None,
                 animated_path: Optional[str] = None, app_controller=None):
        """Initialize MultiEntityThumbnailWidget."""
        try:
            # Call parent constructor with proper parameters
            super().__init__(entity, thumbnail_path, animated_path, app_controller)
        except Exception as e:
            logger.error(f"ERROR creating MultiEntityThumbnailWidget for {entity.name}: {e}")
            raise
    
    def contextMenuEvent(self, event):
        """Handle context menu event."""
        # Get the MultiContentViewWidget (parent traversal)
        content_view = self.parent()
        while content_view and not isinstance(content_view, MultiContentViewWidget):
            content_view = content_view.parent()
        
        if content_view and hasattr(content_view, 'context_menu_manager'):
            # Check if multiple entities are selected
            selected_entities = content_view.get_selected_entities()
            
            if len(selected_entities) > 1:
                # Multiple entities selected - pass all selected entities to context menu
                entities_for_menu = selected_entities
            else:
                # Single entity or no selection - use this entity
                entities_for_menu = self.entity
            
            menu = content_view.context_menu_manager.create_entity_menu(entities_for_menu, self)
            menu.exec_(event.globalPos())
    
    def mouseDoubleClickEvent(self, event):
        """Handle mouse double click."""
        if event.button() == Qt.LeftButton:
            # Get the MultiContentViewWidget to access the open functionality
            content_view = self.parent()
            while content_view and not isinstance(content_view, MultiContentViewWidget):
                content_view = content_view.parent()
            
            if content_view:
                content_view._open_entity_with_default_player(self.entity)
            
            self.entity_double_clicked.emit(self.entity)
        super().mouseDoubleClickEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse press - STEP 3: Single-click + Ctrl+click toggle + Shift+click range selection + Multi-entity drag support."""
        if event.button() == Qt.LeftButton:
            # Get the MultiContentViewWidget (parent traversal)
            content_view = self.parent()
            while content_view and not isinstance(content_view, MultiContentViewWidget):
                content_view = content_view.parent()
            
            if content_view:
                # Check for modifier keys
                modifiers = QApplication.keyboardModifiers()
                ctrl_pressed = bool(modifiers & Qt.ControlModifier)
                shift_pressed = bool(modifiers & Qt.ShiftModifier)
                
                if shift_pressed:
                    # Step 3: Shift+click range selection
                    content_view._select_range_to_entity(self.entity)
                elif ctrl_pressed:
                    # Step 2: Ctrl+click toggle selection
                    if content_view._is_entity_selected(self.entity):
                        # Entity is selected, deselect it
                        content_view.deselect_entity(self.entity)
                    else:
                        # Entity is not selected, add to selection
                        content_view.select_entity(self.entity, add_to_selection=True)
                else:
                    # Step 1 + Multi-entity drag support: Smart single-click selection
                    is_entity_selected = content_view._is_entity_selected(self.entity)
                    selected_count = len(content_view.get_selected_entities())
                    
                    if is_entity_selected and selected_count > 1:
                        # Entity is already selected and part of multi-selection
                        # DO NOT change selection - preserve for drag & drop
                        pass
                    elif is_entity_selected and selected_count == 1:
                        # Entity is the only selected entity - keep it selected
                        pass
                    else:
                        # Entity is not selected - clear selection and select this entity
                        content_view.clear_selection()
                        content_view.select_entity(self.entity, add_to_selection=False)
                
                # Store drag start position for potential drag operations
                self.drag_start_position = event.pos()
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for drag operations."""
        if not (event.buttons() & Qt.LeftButton):
            return
        
        if not self.drag_start_position:
            return
        
        # Calculate distance moved
        distance = (event.pos() - self.drag_start_position).manhattanLength()
        min_distance = QApplication.startDragDistance()
        
        # Check if we've moved far enough to start a drag
        if distance < min_distance:
            return
        
        # Start drag operation
        self._start_drag()
        super().mouseMoveEvent(event)
    
    def _start_drag(self):
        """Start drag operation with entity file path(s) - supports multi-selection."""
        # Get the MultiContentViewWidget to check for multi-selection
        content_view = self.parent()
        while content_view and not isinstance(content_view, MultiContentViewWidget):
            content_view = content_view.parent()
        
        if not content_view:
            logger.error("ERROR: Could not find MultiContentViewWidget parent for drag operation")
            return
        
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Get current selection
        selected_entities = content_view.get_selected_entities()
        
        if len(selected_entities) > 1:
            # Multi-entity drag - get all selected entities
            file_paths = [str(entity.path) for entity in selected_entities]
            
            # Set multiple file paths as plain text (one per line)
            text_content = '\n'.join(file_paths)
            mime_data.setText(text_content)
            
            # Set as HTML for better text editor compatibility
            html_content = '<br>'.join(file_paths)
            mime_data.setHtml(html_content)
            
            # Set as URLs for file manager compatibility
            urls = [QUrl.fromLocalFile(file_path) for file_path in file_paths]
            mime_data.setUrls(urls)
            
            # Set custom MIME types for maximum compatibility
            mime_data.setData("text/plain", text_content.encode('utf-8'))
            uri_list = '\n'.join([QUrl.fromLocalFile(fp).toString() for fp in file_paths])
            mime_data.setData("text/uri-list", uri_list.encode('utf-8'))
            
            # Use a generic multi-file icon or the first entity's thumbnail
            if self.static_pixmap:
                drag_pixmap = self.static_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                # Add a small indicator for multiple files
                from PySide6.QtGui import QPainter, QFont
                painter = QPainter(drag_pixmap)
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(drag_pixmap.rect().bottomRight() - QPoint(15, 5), f"{len(selected_entities)}")
                painter.end()
                drag.setPixmap(drag_pixmap)
        else:
            # Single entity drag
            file_path = str(self.entity.path)
            
            # Set as plain text
            mime_data.setText(file_path)
            
            # Set as HTML for better text editor compatibility
            mime_data.setHtml(file_path)
            
            # Set as URL for file manager compatibility
            urls = [QUrl.fromLocalFile(file_path)]
            mime_data.setUrls(urls)
            
            # Set custom MIME types for maximum compatibility
            mime_data.setData("text/plain", file_path.encode('utf-8'))
            mime_data.setData("text/uri-list", QUrl.fromLocalFile(file_path).toString().encode('utf-8'))
            
            # Use thumbnail as drag pixmap if available
            if self.static_pixmap:
                drag.setPixmap(self.static_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        # Set the MIME data on the drag object
        drag.setMimeData(mime_data)
        
        # Execute drag with all possible actions
        result = drag.exec_(Qt.CopyAction | Qt.MoveAction | Qt.LinkAction, Qt.CopyAction)


class MultiContentViewWidget(QWidget, DragDropMixin):
    """Context-aware content view widget displaying media entities with multi-database support."""
    
    # Signals
    entity_selected = Signal(object)  # MediaEntity
    entity_double_clicked = Signal(object)  # MediaEntity
    files_dropped = Signal(list)  # List of file paths (from DragDropMixin)
    directories_dropped = Signal(list)  # List of directory paths (from DragDropMixin)
    
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self.config = app_controller.config_manager
        
        # Multi-context managers
        self.multi_entity_manager = getattr(app_controller, 'multi_entity_manager', None)
        self.multi_thumbnail_manager = getattr(app_controller, 'multi_thumbnail_manager', None)
        self.multi_database_manager = getattr(app_controller, 'multi_database_manager', None)
        self.multi_metadata_manager = getattr(app_controller, 'multi_metadata_manager', None)
        self.path_context_manager = getattr(app_controller, 'path_context_manager', None)
        
        # State
        self.current_entities: List[MediaEntity] = []
        self.filtered_entities: List[MediaEntity] = []
        self.entity_widgets: Dict[str, EntityThumbnailWidget] = {}  # Key format: "path::name"
        self.selected_entities: List[MediaEntity] = []  # Track selected entities
        self.current_directory: Optional[str] = None
        self.current_context: ContextType = ContextType.GENERAL
        self.search_criteria: Optional[Dict[str, Any]] = None
        self.current_view_mode: str = "Grid"
        
        # Widget creation state tracking - CRITICAL: Initialize in __init__
        self._widgets_created = False
        self._widget_creation_in_progress = False
        
        self._setup_ui()
        self._connect_signals()
        self._setup_drag_drop()
        self._setup_context_menu()
        self._setup_keyboard_shortcuts()
        
        # Setup rubber band overlay for area selection
        self._setup_rubber_band_overlay()
        
        
        # Connect resize event for dynamic grid columns
        self.scroll_area.resizeEvent = self._on_scroll_area_resize
        
        # Enable mouse tracking for click-to-deselect functionality
        self.setMouseTracking(True)
        self.scroll_area.setMouseTracking(True)
        self.content_widget.setMouseTracking(True)
    
    def _setup_ui(self):
        """Setup the content view UI."""
        layout = QVBoxLayout(self)
        
        # Header with controls
        header_layout = QHBoxLayout()
        
        # Title with context indicator
        self.title_label = QLabel("Content View")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(self.title_label)
        
        # Context indicator
        self.context_label = QLabel("General")
        self.context_label.setStyleSheet("font-size: 10px; color: #666; font-style: italic;")
        header_layout.addWidget(self.context_label)
        
        header_layout.addStretch()
        
        # View mode selector
        header_layout.addWidget(QLabel("View:"))
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Grid", "Details"])
        self.view_mode_combo.currentTextChanged.connect(self._on_view_mode_changed)
        header_layout.addWidget(self.view_mode_combo)
        
        # Remove refresh button as requested
        
        layout.addLayout(header_layout)
        
        # Progress bar for loading
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("Ready - Select a directory to view content")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.status_label)
        
        # Create container for different view modes
        self.view_container = QWidget()
        view_container_layout = QVBoxLayout(self.view_container)
        view_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Grid view (default)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.content_widget = QWidget()
        self.grid_layout = QGridLayout(self.content_widget)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll_area.setWidget(self.content_widget)
        
        # Apply dynamic theme-based styling to content view background
        self._apply_content_view_styling()
        
        # Details view (tree widget)
        self.details_widget = QTreeWidget()
        self.details_widget.setHeaderLabels([
            "Name", "Type", "Size", "Duration", "Resolution", "Favorites", "Tags", "Modified", "Path"
        ])
        self.details_widget.setAlternatingRowColors(True)
        self.details_widget.setSortingEnabled(True)
        self.details_widget.setVisible(False)
        # Enable multi-selection in details view
        self.details_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.details_widget.itemDoubleClicked.connect(self._on_details_item_double_clicked)
        self.details_widget.itemClicked.connect(self._on_details_item_clicked)
        self.details_widget.itemSelectionChanged.connect(self._on_details_selection_changed)
        self.details_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.details_widget.customContextMenuRequested.connect(self._on_details_context_menu)
        
        # Configure details widget columns
        header = self.details_widget.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Name column stretches
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Size
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Duration
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Resolution
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Favorites
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Modified
        header.setSectionResizeMode(7, QHeaderView.Stretch)  # Path
        
        # Add all views to container
        view_container_layout.addWidget(self.scroll_area)
        view_container_layout.addWidget(self.details_widget)
        
        layout.addWidget(self.view_container)
    
    def _apply_content_view_styling(self):
        """Apply dynamic theme-based styling to the content view."""
        content_style = theme_manager.get_content_view_stylesheet()
        self.scroll_area.setStyleSheet(content_style)
    
    def _connect_signals(self):
        """Connect application signals."""
        # Connect to multi-entity manager signals
        if self.multi_entity_manager:
            self.multi_entity_manager.entities_discovered.connect(
                self._on_entities_discovered
            )
            self.multi_entity_manager.scan_progress.connect(
                self._on_scan_progress
            )
        
        # Connect to multi-thumbnail manager signals
        if self.multi_thumbnail_manager:
            self.multi_thumbnail_manager.thumbnail_generated.connect(
                self._on_thumbnail_generated
            )
            self.multi_thumbnail_manager.generation_progress.connect(
                self._on_thumbnail_progress
            )
    
    def _update_context_display(self, context: ContextType, path: str):
        """Update the context display in the UI."""
        self.current_context = context
        self.context_label.setText(f"{context.value.title()} Context")
        
        # Update context label color based on context
        colors = {
            ContextType.GENERAL: "#666",
            ContextType.USER: "#0078d4",
            ContextType.PROJECT: "#ff6b35"
        }
        
        color = colors.get(context, "#666")
        self.context_label.setStyleSheet(f"font-size: 10px; color: {color}; font-style: italic; font-weight: bold;")
        
    
    def _set_path_context(self, directory_path: str):
        """Set the path context for all multi-managers."""
        if self.path_context_manager:
            context = self.path_context_manager.get_context_for_path(directory_path)
            
            # Update all multi-managers with new path context
            if self.multi_entity_manager:
                self.multi_entity_manager.set_current_path(directory_path)
            
            if self.multi_thumbnail_manager:
                self.multi_thumbnail_manager.set_current_path(directory_path)
            
            if self.multi_metadata_manager:
                self.multi_metadata_manager.set_current_path(directory_path)
            
            # Update UI context display
            self._update_context_display(context, directory_path)
            
    
    def _on_view_mode_changed(self, mode: str):
        """Handle view mode change."""
        self.current_view_mode = mode
        
        # Hide all views first
        self.scroll_area.setVisible(False)
        self.details_widget.setVisible(False)
        
        # Show the selected view
        if mode == "Grid":
            self.scroll_area.setVisible(True)
        elif mode == "Details":
            self.details_widget.setVisible(True)
        
        # Recreate content for the new view mode
        self._create_entity_widgets()
    
    def _refresh_content(self):
        """Refresh the current content."""
        if self.current_directory:
            self.load_directory(self.current_directory)
    
    def load_directory(self, directory_path: str):
        """Load content from a directory with context awareness."""
        
        # Set path context first
        self._set_path_context(directory_path)
        
        # Check if we're already showing this directory with content
        if (self.current_directory == directory_path and
            self.current_entities and
            not self.progress_bar.isVisible()):
            return
        
        self.current_directory = directory_path
        self.status_label.setText(f"Scanning: {directory_path}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        # Clear current content
        self._clear_content()
        
        # Update title
        dir_name = Path(directory_path).name or directory_path
        self.title_label.setText(f"Content View - {dir_name}")
        
        # Trigger directory scan using multi-entity manager
        if self.multi_entity_manager:
            try:
                directory = Path(directory_path)
                recursive_scan = self.config.get('ui.recursive_scan', True)
                self.multi_entity_manager.scan_directory(directory, recursive=recursive_scan)
            except Exception as e:
                logger.error(f"Error loading directory {directory_path}: {e}")
                self.status_label.setText(f"Error: {e}")
                self.progress_bar.setVisible(False)
        else:
            logger.error("MultiEntityManager not available")
            self.status_label.setText("Error: MultiEntityManager not available")
            self.progress_bar.setVisible(False)
    
    def load_multiple_directories(self, directory_paths: list):
        """Load content from multiple directories with context awareness."""
        if not directory_paths:
            return
        
        # Set context based on first directory for now
        # In a more sophisticated implementation, you might need to handle mixed contexts
        self._set_path_context(directory_paths[0])
        
        self.current_directory = f"Multiple directories ({len(directory_paths)} selected)"
        self.status_label.setText(f"Scanning {len(directory_paths)} directories...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        # Clear current content
        self._clear_content()
        
        # Update title
        self.title_label.setText(f"Content View - {len(directory_paths)} Directories")
        
        # Collect all entities from all directories
        all_entities = []
        total_directories = len(directory_paths)
        
        if self.multi_entity_manager:
            try:
                for i, directory_path in enumerate(directory_paths):
                    directory = Path(directory_path)
                    if directory.exists() and directory.is_dir():
                        # Set context for each directory
                        self._set_path_context(str(directory))
                        
                        # Scan each directory recursively
                        recursive_scan = self.config.get('ui.recursive_scan', True)
                        entities = self.multi_entity_manager.scan_directory(directory, recursive=recursive_scan)
                        all_entities.extend(entities)
                        
                        # Update progress
                        self.progress_bar.setRange(0, total_directories)
                        self.progress_bar.setValue(i + 1)
                        self.status_label.setText(f"Scanning... {i + 1}/{total_directories} directories")
                    else:
                        logger.warning(f"Directory does not exist or is not accessible: {directory_path}")
                
                # Process all collected entities
                self.current_entities = all_entities
                self.progress_bar.setVisible(False)
                
                if not all_entities:
                    self.status_label.setText(f"No media files found in {len(directory_paths)} directories")
                    return
                
                # Count entities by type for status
                video_count = sum(1 for e in all_entities if len(e.files) == 1 and e.frame_count != 1)
                sequence_count = sum(1 for e in all_entities if len(e.files) > 1)
                image_count = sum(1 for e in all_entities if len(e.files) == 1 and e.frame_count == 1)
                
                status_parts = []
                if video_count > 0:
                    status_parts.append(f"{video_count} videos")
                if sequence_count > 0:
                    status_parts.append(f"{sequence_count} sequences")
                if image_count > 0:
                    status_parts.append(f"{image_count} images")
                
                status_text = f"Found {len(all_entities)} items ({', '.join(status_parts)}) from {len(directory_paths)} directories"
                self.status_label.setText(status_text)
                
                # Create thumbnail widgets
                self._create_entity_widgets()
                
            except Exception as e:
                logger.error(f"Error loading multiple directories: {e}")
                self.status_label.setText(f"Error: {e}")
                self.progress_bar.setVisible(False)
        else:
            self.status_label.setText("Error: MultiEntityManager not available")
            self.progress_bar.setVisible(False)
    
    def _clear_content(self):
        """Clear all content widgets."""
        # Remove all widgets from grid layout
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        self.current_entities.clear()
        self.entity_widgets.clear()
        self.selected_entities.clear()  # Clear selection when clearing content
    
    def _on_entities_discovered(self, entities: List[MediaEntity]):
        """Handle entities discovered."""
        
        self.current_entities = entities
        self.progress_bar.setVisible(False)
        
        if not entities:
            self.status_label.setText("No media files found in this directory")
            return
        
        self.status_label.setText(f"Found {len(entities)} media files")
        
        # SIMPLE APPROACH: Allow discovery but make widget creation idempotent
        
        # Create widgets - the _create_entity_widgets method should handle duplicates
        self._create_entity_widgets()
        
        # Queue thumbnail generation using multi-thumbnail manager
        if self.multi_thumbnail_manager:
            self.multi_thumbnail_manager.queue_thumbnail_generation(entities, self.current_directory)
    
    def _create_entity_widgets(self):
        """Create widgets for entities based on current view mode."""
        
        # CRITICAL: Always clear existing widgets first to prevent duplicates
        self._clear_widgets()
        
        # Use filtered entities if search is active, otherwise all entities
        entities_to_show = self.filtered_entities if self.search_criteria else self.current_entities
        
        if self.current_view_mode == "Grid":
            self._create_grid_widgets(entities_to_show)
        elif self.current_view_mode == "Details":
            self._create_details_widgets(entities_to_show)
    
    def _create_grid_widgets(self, entities: List[MediaEntity]):
        """Create grid view widgets with lazy loading."""
        
        # Store entities for lazy loading
        self.grid_entities = entities
        self.grid_entity_positions = {}  # Map entity path to (row, col) position
        
        # Calculate dynamic number of columns based on available width
        max_cols = self._calculate_grid_columns()
        
        
        # Calculate positions for all entities but don't create widgets yet
        row = 0
        col = 0
        
        for i, entity in enumerate(entities):
            # Create unique entity key using path + name to avoid collisions
            entity_key = f"{entity.path}::{entity.name}"
            self.grid_entity_positions[entity_key] = (row, col)
            
            # Update grid position
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        # Set the content widget size to accommodate all entities
        widget_width = 150 + 10  # Entity width + margin
        widget_height = 180 + 10  # Entity height + margin
        total_width = max_cols * widget_width
        total_height = (row + 1) * widget_height
        
        self.content_widget.setMinimumSize(total_width, total_height)
        
        # Connect scroll area viewport change to trigger lazy loading
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self._on_scroll_changed)
        
        # Initial load of visible widgets
        self._load_visible_widgets()
        
        
    
    def _calculate_grid_columns(self) -> int:
        """Calculate the number of columns for the grid based on available width."""
        # Get the available width of the scroll area
        available_width = self.scroll_area.viewport().width()
        
        # Entity widget width (150px) + some margin for spacing
        widget_width = 150 + 10  # 10px margin between widgets
        
        # Calculate how many widgets can fit
        max_cols = max(1, available_width // widget_width)
        
        # Limit to reasonable bounds (minimum 1, maximum 10)
        return min(max(max_cols, 1), 10)
    
    def _on_scroll_changed(self):
        """Handle scroll position change to load visible widgets."""
        if hasattr(self, 'grid_entities') and self.current_view_mode == "Grid":
            self._load_visible_widgets()
    
    def _load_visible_widgets(self):
        """Load widgets that are currently visible in the viewport."""
        if not hasattr(self, 'grid_entities') or not self.grid_entities:
            return
        
        # Get viewport rectangle
        viewport = self.scroll_area.viewport()
        viewport_rect = viewport.rect()
        
        # Get scroll position
        scroll_x = self.scroll_area.horizontalScrollBar().value()
        scroll_y = self.scroll_area.verticalScrollBar().value()
        
        # Adjust viewport rect for scroll position
        visible_rect = QRect(
            scroll_x,
            scroll_y,
            viewport_rect.width(),
            viewport_rect.height()
        )
        
        # Add some buffer to load widgets slightly outside viewport
        buffer = 200  # pixels
        visible_rect.adjust(-buffer, -buffer, buffer, buffer)
        
        widget_width = 150 + 10
        widget_height = 180 + 10
        
        entities_to_load = []
        
        for entity in self.grid_entities:
            # Create unique entity key using path + name to avoid collisions
            entity_key = f"{entity.path}::{entity.name}"
            
            # Skip if widget already exists
            if entity_key in self.entity_widgets:
                continue
            
            # Get entity position
            if entity_key not in self.grid_entity_positions:
                continue
                
            row, col = self.grid_entity_positions[entity_key]
            
            # Calculate widget rectangle
            widget_x = col * widget_width
            widget_y = row * widget_height
            widget_rect = QRect(widget_x, widget_y, 150, 180)
            
            # Check if widget is visible or near visible area
            if visible_rect.intersects(widget_rect):
                entities_to_load.append(entity)
        
        # Create widgets for visible entities
        if entities_to_load:
            self._create_entity_widgets_batch(entities_to_load)
    
    def _create_entity_widgets_batch(self, entities: List[MediaEntity]):
        """Create a batch of entity widgets."""
        for entity in entities:
            # Create unique entity key using path + name to avoid collisions
            entity_key = f"{entity.path}::{entity.name}"
            
            # Skip if widget already exists (prevents duplicate creation)
            if entity_key in self.entity_widgets:
                continue
            
            # Get position using the same unique key
            if entity_key not in self.grid_entity_positions:
                continue
                
            row, col = self.grid_entity_positions[entity_key]
            
            # Check if we already have thumbnails for this entity
            thumbnail_path = None
            animated_path = None
            
            if self.multi_thumbnail_manager:
                thumbnail_path = self.multi_thumbnail_manager.get_thumbnail_path(entity, self.current_directory)
                
                # For videos and sequences, check for animated thumbnail
                is_video = entity.entity_type.value == "video"
                is_sequence = len(entity.files) > 1
                
                if is_video or is_sequence:
                    animated_path = self.multi_thumbnail_manager.get_animated_thumbnail_path(entity, self.current_directory)
            
            # Create thumbnail widget using custom multi-context widget
            try:
                # FIXED: Create with correct parameter order - no size parameter!
                widget = MultiEntityThumbnailWidget(entity, thumbnail_path, animated_path, self.app_controller)
                
                # Apply dynamic theme-based entity styling
                entity_style = theme_manager.get_entity_widget_stylesheet(is_selected=False)
                widget.setStyleSheet(entity_style)
                
                # SIGNAL CONNECTIONS REMOVED FOR CLEAN REBUILD
                # All signal connections will be rebuilt step by step
                
            except Exception as e:
                raise
            
            # Add to grid at calculated position
            self.grid_layout.addWidget(widget, row, col)
            
            # Store reference
            self.entity_widgets[entity_key] = widget
            
            
    
    def _on_scroll_area_resize(self, event):
        """Handle scroll area resize to recalculate grid columns."""
        # Call the original resize event
        QScrollArea.resizeEvent(self.scroll_area, event)
        
        # Only recalculate if we're in grid mode and have entities
        if (self.current_view_mode == "Grid" and
            (self.current_entities or self.filtered_entities)):
            # Recalculate and recreate grid if column count changed
            new_cols = self._calculate_grid_columns()
            current_cols = getattr(self, '_current_grid_cols', 5)
            
            if new_cols != current_cols:
                self._current_grid_cols = new_cols
                # CRITICAL FIX: DO NOT recreate widgets on resize - this causes duplicate signal connections!
                # Instead, just update the layout positions
                # self._create_entity_widgets()  # DISABLED - This was causing duplicate creation
                self._load_visible_widgets()  # Load any newly visible widgets instead
            else:
                # Just load visible widgets if column count didn't change
                self._load_visible_widgets()
    
    def _create_details_widgets(self, entities: List[MediaEntity]):
        """Create details view widgets."""
        for entity in entities:
            # Create tree item
            item = QTreeWidgetItem()
            item.setData(0, Qt.UserRole, entity)
            
            # Set column data
            item.setText(0, entity.name)  # Name
            
            # Type - determine actual type based on file characteristics and extension
            file_ext = entity.path.suffix.lstrip('.').lower()
            
            # Define video and image extensions
            video_extensions = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v', 'mpg', 'mpeg', 'wmv', 'flv', 'f4v']
            image_extensions = ['jpg', 'jpeg', 'png', 'tiff', 'tif', 'exr', 'dpx', 'bmp', 'gif', 'webp']
            
            if len(entity.files) > 1:
                # Multiple files = sequence
                first_file_path = Path(entity.files[0])
                seq_ext = first_file_path.suffix.lstrip('.').lower()
                item.setText(1, f"Sequence ({seq_ext}) ({len(entity.files)})")
            elif file_ext in video_extensions:
                # Single file with video extension = video
                item.setText(1, f"Video ({file_ext})")
            elif file_ext in image_extensions:
                # Single file with image extension = image
                item.setText(1, f"Image ({file_ext})")
            else:
                # Fallback - check frame count if available
                if entity.frame_count and entity.frame_count > 1:
                    item.setText(1, f"Video ({file_ext})")
                else:
                    item.setText(1, f"Media ({file_ext})")
            
            # Size
            if entity.file_size:
                size_mb = entity.file_size / (1024 * 1024)
                if size_mb >= 1:
                    item.setText(2, f"{size_mb:.1f} MB")
                else:
                    size_kb = entity.file_size / 1024
                    item.setText(2, f"{size_kb:.1f} KB")
            else:
                item.setText(2, "Unknown")
            
            # Duration - get from metadata for videos and sequences
            duration = self._get_entity_duration(entity)
            item.setText(3, duration if duration else "N/A")
            
            # Resolution
            resolution = self._get_entity_resolution(entity)
            item.setText(4, resolution if resolution else "N/A")
            
            # Favorites - show appropriate icon based on favorite status
            favorites_display = self._get_entity_favorites_display(entity)
            item.setText(5, favorites_display)
            
            # Tags - show entity tags
            tags_display = self._get_entity_tags_display(entity)
            item.setText(6, tags_display)
            
            # Modified date
            try:
                mtime = entity.path.stat().st_mtime
                from datetime import datetime
                mod_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                item.setText(7, mod_date)
            except:
                item.setText(7, "Unknown")
            
            # Path
            item.setText(8, str(entity.path))
            
            # Set tooltip
            tooltip = self._get_entity_tooltip(entity)
            item.setToolTip(0, tooltip)
# Add to tree
            self.details_widget.addTopLevelItem(item)
    
    def _get_entity_tooltip(self, entity: MediaEntity) -> str:
        """Get tooltip text for entity."""
        tooltip_parts = [f"Name: {entity.name}"]
        tooltip_parts.append(f"Path: {entity.path}")
        
        # Determine type based on file characteristics and extension
        file_ext = entity.path.suffix.lstrip('.').lower()
        video_extensions = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v', 'mpg', 'mpeg', 'wmv', 'flv', 'f4v']
        image_extensions = ['jpg', 'jpeg', 'png', 'tiff', 'tif', 'exr', 'dpx', 'bmp', 'gif', 'webp']
        
        if len(entity.files) > 1:
            tooltip_parts.append(f"Type: Image Sequence ({len(entity.files)} frames)")
        elif file_ext in video_extensions:
            tooltip_parts.append("Type: Video")
        elif file_ext in image_extensions:
            tooltip_parts.append("Type: Single Image")
        else:
            # Fallback - check frame count if available
            if entity.frame_count and entity.frame_count > 1:
                tooltip_parts.append("Type: Video")
            else:
                tooltip_parts.append("Type: Media File")
        
        if entity.frame_range and len(entity.files) > 1:
            tooltip_parts.append(f"Frame Range: {entity.frame_range[0]}-{entity.frame_range[1]}")
        
        if entity.file_size:
            size_mb = entity.file_size / (1024 * 1024)
            if size_mb >= 1:
                tooltip_parts.append(f"Size: {size_mb:.1f} MB")
            else:
                size_kb = entity.file_size / 1024
                tooltip_parts.append(f"Size: {size_kb:.1f} KB")
        
        return "\n".join(tooltip_parts)
    
    def _get_entity_resolution(self, entity: MediaEntity) -> Optional[str]:
        """Get resolution for an entity from metadata using multi-database manager."""
        if not self.multi_metadata_manager:
            return None
        
        try:
            metadata = self.multi_metadata_manager.get_entity_metadata(
                str(entity.path), 
                context_path=self.current_directory
            )
            
            if metadata and 'width' in metadata and 'height' in metadata:
                return f"{metadata['width']}×{metadata['height']}"
            
        except Exception as e:
            logger.debug(f"Error getting resolution for {entity.name}: {e}")
        
        return None
    
    def _get_entity_duration(self, entity: MediaEntity) -> Optional[str]:
        """Get duration for an entity from metadata using multi-database manager."""
        # Skip duration for single images (frame_count == 1 indicates single image)
        if len(entity.files) == 1 and entity.frame_count == 1:
            return None
        
        if not self.multi_metadata_manager:
            return None
        
        try:
            metadata = self.multi_metadata_manager.get_entity_metadata(
                str(entity.path),
                context_path=self.current_directory
            )
            
            if metadata and 'duration' in metadata:
                duration = metadata['duration']
                # Format duration as HH:MM:SS or MM:SS
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                seconds = int(duration % 60)
                
                if hours > 0:
                    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    return f"{minutes:02d}:{seconds:02d}"
            
        except Exception as e:
            logger.debug(f"Error getting duration for {entity.name}: {e}")
        
        return None
    
    def _get_entity_favorites_display(self, entity: MediaEntity) -> str:
        """Get favorites display text for an entity in details view using SVG icons."""
        if not self.app_controller or not hasattr(self.app_controller, 'config_manager'):
            return ""
        
        try:
            config_manager = self.app_controller.config_manager
            file_path = str(entity.path)
            
            # Check user favorite
            user_favorite = config_manager.is_user_favorite(file_path)
            
            # Check project favorite
            current_project_name = self._get_current_project_name()
            project_favorite = config_manager.is_project_favorite(file_path, current_project_name)
            
            # Return appropriate display text using SVG icons
            if user_favorite and project_favorite:
                # Both user and project favorite - show both SVG icons
                user_icon = self._load_svg_icon_as_text("icon_user_favorite.svg")
                project_icon = self._load_svg_icon_as_text("icon_project_favorite.svg")
                return f"{user_icon}{project_icon}"
            elif user_favorite:
                # User favorite only - show star SVG icon
                return self._load_svg_icon_as_text("icon_user_favorite.svg")
            elif project_favorite:
                # Project favorite only - show diamond SVG icon
                return self._load_svg_icon_as_text("icon_project_favorite.svg")
            else:
                return ""      # Not a favorite
                    
        except Exception as e:
            logger.debug(f"Error getting favorites display for {entity.name}: {e}")
            return ""
    
    def _load_svg_icon_as_text(self, icon_filename: str) -> str:
        """Load SVG icon and return as text symbol (fallback to emoji if SVG not available)."""
        try:
            # Get the absolute path to the resources directory
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent  # Go up to project root
            icon_path = project_root / "src" / "stockshot_browser" / "resources" / icon_filename
            
            if icon_path.exists():
                # For now, return Unicode symbols that look similar to the icons
                # In a full implementation, you could render SVG to a small pixmap and embed it
                if icon_filename == "icon_user_favorite.svg":
                    return "★"  # Unicode star for user favorites
                elif icon_filename == "icon_project_favorite.svg":
                    return "◆"  # Unicode diamond for project favorites
                else:
                    return "●"  # Fallback symbol
            else:
                # Fallback to emoji symbols if SVG not found
                if icon_filename == "icon_user_favorite.svg":
                    return "⭐"
                elif icon_filename == "icon_project_favorite.svg":
                    return "🔶"
                else:
                    return "●"
        except Exception as e:
            logger.debug(f"Error loading SVG icon {icon_filename}: {e}")
            # Fallback to emoji symbols on error
            if icon_filename == "icon_user_favorite.svg":
                return "⭐"
            elif icon_filename == "icon_project_favorite.svg":
                return "🔶"
            else:
                return "●"
    
    def _get_entity_tags_display(self, entity: MediaEntity) -> str:
        """Get tags display text for an entity in details view."""
        if not self.multi_database_manager:
            return ""
        
        try:
            with self.multi_database_manager.get_session_for_path(self.current_directory, for_tags=True) as session:
                from ..database.models import Tag, Entity, entity_tags
                
                # Find the entity in database
                db_entity = session.query(Entity).filter_by(
                    path=str(entity.path),
                    entity_type=entity.entity_type.value
                ).first()
                
                if db_entity:
                    # Get entity tags
                    tags = session.query(Tag).join(entity_tags).filter(
                        entity_tags.c.entity_id == db_entity.id
                    ).all()
                    
                    if tags:
                        tag_names = [tag.name for tag in tags]
                        return ", ".join(sorted(tag_names))
                    else:
                        return ""
                else:
                    return ""
                    
        except Exception as e:
            logger.debug(f"Error getting tags display for {entity.name}: {e}")
            return ""

    def _get_current_project_name(self) -> str:
        """Get current project name if available, with fallback to 'Default'."""
        try:
            if (self.app_controller and
                hasattr(self.app_controller, 'project_manager') and
                self.app_controller.project_manager.current_project):
                return self.app_controller.project_manager.current_project.name
            return "Default"  # Fallback to ensure project favorites always work
        except Exception:
            return "Default"
    
    def _clear_widgets(self):
        """Clear all entity widgets from all views."""
        # Clear grid layout
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Clear details widget
        self.details_widget.clear()
        
        self.entity_widgets.clear()
        
        # Clear lazy loading data
        if hasattr(self, 'grid_entities'):
            self.grid_entities = []
        if hasattr(self, 'grid_entity_positions'):
            self.grid_entity_positions = {}
    
    def _on_scan_progress(self, current: int, total: int):
        """Handle scan progress."""
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
            self.status_label.setText(f"Scanning... {current}/{total}")
    
    def _on_thumbnail_generated(self, entity: MediaEntity, thumbnail_path: str):
        """Handle thumbnail generation."""
        # Create unique entity key using path + name to avoid collisions
        entity_key = f"{entity.path}::{entity.name}"
        if entity_key in self.entity_widgets:
            # Check for animated thumbnail (videos and sequences)
            animated_path = None
            is_video = entity.entity_type.value == "video"
            is_sequence = len(entity.files) > 1
            
            if (is_video or is_sequence) and self.multi_thumbnail_manager:
                animated_path = self.multi_thumbnail_manager.get_animated_thumbnail_path(
                    entity, self.current_directory
                )
            
            self.entity_widgets[entity_key].update_thumbnail(thumbnail_path, animated_path)
            logger.debug(f"Updated thumbnail for: {entity.name} (animated: {animated_path is not None})")
    
    def _on_thumbnail_progress(self, current: int, total: int):
        """Handle thumbnail generation progress."""
        if total > 0 and current <= total:
            progress_text = f"Generating thumbnails... {current}/{total}"
            self.status_label.setText(progress_text)
    
    # Selection methods - Complete implementation from ContentViewWidget
    def get_selected_entities(self) -> List[MediaEntity]:
        """Get currently selected entities."""
        return self.selected_entities.copy()
    
    def select_entity(self, entity: MediaEntity, add_to_selection: bool = False):
        """Select a specific entity."""
        if not add_to_selection:
            self.clear_selection()
        
        # Use path-based comparison for more reliable entity matching
        if not self._is_entity_selected(entity):
            self.selected_entities.append(entity)
            self._update_entity_selection_visual(entity, True)
        
        self._update_selection_status()
        self.entity_selected.emit(entity)
        logger.debug(f"Selected entity: {entity.name} (total selected: {len(self.selected_entities)})")
    
    def deselect_entity(self, entity: MediaEntity):
        """Deselect a specific entity."""
        # Use path-based comparison to find and remove the entity
        entity_path = str(entity.path)
        entity_to_remove = None
        
        for selected_entity in self.selected_entities:
            if str(selected_entity.path) == entity_path:
                entity_to_remove = selected_entity
                break
        
        if entity_to_remove:
            self.selected_entities.remove(entity_to_remove)
            self._update_entity_selection_visual(entity, False)
            self._update_selection_status()
            logger.debug(f"Deselected entity: {entity.name} (total selected: {len(self.selected_entities)})")
    
    def clear_selection(self):
        """Clear all selected entities."""
        for entity in self.selected_entities:
            self._update_entity_selection_visual(entity, False)
        self.selected_entities.clear()
        self._update_selection_status()
        logger.debug("Cleared all entity selections")
    
    def _update_entity_selection_visual(self, entity: MediaEntity, selected: bool):
        """Update visual selection state for an entity using dynamic theme colors."""
        # Create unique entity key using path + name to avoid collisions
        entity_key = f"{entity.path}::{entity.name}"
        # Update grid view widget if it exists
        if entity_key in self.entity_widgets:
            widget = self.entity_widgets[entity_key]
            
            # Apply dynamic theme-based entity styling
            entity_style = theme_manager.get_entity_widget_stylesheet(is_selected=selected)
            widget.setStyleSheet(entity_style)
        
        # Update details view selection if in details mode
        if self.current_view_mode == "Details":
            for i in range(self.details_widget.topLevelItemCount()):
                item = self.details_widget.topLevelItem(i)
                item_entity = item.data(0, Qt.UserRole)
                if item_entity and str(item_entity.path) == str(entity.path):
                    item.setSelected(selected)
                    break
    
    def _update_selection_status(self):
        """Update status label to show selection count."""
        if not self.selected_entities:
            # Show normal status
            if self.search_criteria:
                visible = len(self.filtered_entities)
                total = len(self.current_entities)
                self.status_label.setText(f"Showing {visible} of {total} items (filtered)")
            else:
                total = len(self.current_entities)
                if total > 0:
                    self.status_label.setText(f"Found {total} media files")
                else:
                    self.status_label.setText("No media files found in this directory")
        else:
            # Show selection count
            selected_count = len(self.selected_entities)
            if self.search_criteria:
                visible = len(self.filtered_entities)
                total = len(self.current_entities)
                self.status_label.setText(f"{selected_count} selected - Showing {visible} of {total} items (filtered)")
            else:
                total = len(self.current_entities)
                self.status_label.setText(f"{selected_count} of {total} items selected")
    
    # SELECTION HANDLERS REMOVED FOR CLEAN REBUILD
    # def _on_grid_entity_selected(self, entity: MediaEntity, ctrl_pressed: bool = False, shift_pressed: bool = False):
    #     """Handle entity selection in grid view."""
    #     # All selection logic removed - will be rebuilt step by step
    #     pass
    
    def _is_entity_selected(self, entity: MediaEntity) -> bool:
        """Check if entity is currently selected using path-based comparison."""
        entity_path = str(entity.path)
        for selected_entity in self.selected_entities:
            if str(selected_entity.path) == entity_path:
                return True
        return False
    
    def _add_to_selection(self, entity: MediaEntity):
        """Add entity to selection if not already selected."""
        if not self._is_entity_selected(entity):
            self.selected_entities.append(entity)
            self._update_entity_selection_visual(entity, True)
    
    def _remove_from_selection(self, entity: MediaEntity):
        """Remove entity from selection."""
        entity_path = str(entity.path)
        entity_to_remove = None
        
        for selected_entity in self.selected_entities:
            if str(selected_entity.path) == entity_path:
                entity_to_remove = selected_entity
                break
        
        if entity_to_remove:
            self.selected_entities.remove(entity_to_remove)
            self._update_entity_selection_visual(entity, False)
    
    def _clear_selection(self):
        """Clear all selected entities without updating status."""
        for entity in self.selected_entities:
            self._update_entity_selection_visual(entity, False)
        self.selected_entities.clear()
    
    def _select_range_to_entity(self, target_entity: MediaEntity):
        """Select range from first selected entity to target entity."""
        if not self.selected_entities:
            self._add_to_selection(target_entity)
            return
        
        # Get the list of entities to work with (filtered or all)
        entities_to_show = self.filtered_entities if self.search_criteria else self.current_entities
        
        try:
            # Find the index of the first selected entity (anchor point)
            first_selected_entity = self.selected_entities[0]
            anchor_idx = None
            target_idx = None
            
            # Find indices using path-based comparison
            for i, entity in enumerate(entities_to_show):
                if str(entity.path) == str(first_selected_entity.path):
                    anchor_idx = i
                if str(entity.path) == str(target_entity.path):
                    target_idx = i
                
                # Break early if we found both
                if anchor_idx is not None and target_idx is not None:
                    break
            
            if anchor_idx is not None and target_idx is not None:
                # Clear current selection
                self._clear_selection()
                
                # Select range from anchor to target (inclusive)
                start_idx = min(anchor_idx, target_idx)
                end_idx = max(anchor_idx, target_idx)
                
                for i in range(start_idx, end_idx + 1):
                    self._add_to_selection(entities_to_show[i])
                
                logger.debug(f"Range selection: selected {end_idx - start_idx + 1} entities from index {start_idx} to {end_idx}")
            else:
                # Fallback: couldn't find indices, just select the target
                logger.warning("Could not find entity indices for range selection, falling back to single selection")
                self._clear_selection()
                self._add_to_selection(target_entity)
                
        except Exception as e:
            logger.error(f"Error in range selection: {e}")
            # Fallback: clear and select target only
            self._clear_selection()
            self._add_to_selection(target_entity)
        
        # Update selection status
        self._update_selection_status()
    
    def _restore_selection_by_paths(self, selected_paths: List[str]):
        """Restore selection for entities with matching paths."""
        if not selected_paths:
            return
        
        # Get entities to check (filtered or all)
        entities_to_check = self.filtered_entities if self.search_criteria else self.current_entities
        
        # Find and select entities with matching paths
        for entity in entities_to_check:
            entity_path_str = str(entity.path)
            
            if entity_path_str in selected_paths:
                # Add to selection list
                if not self._is_entity_selected(entity):
                    self.selected_entities.append(entity)
                
                # Apply visual selection styling
                entity_key = f"{entity.path}::{entity.name}"
                if entity_key in self.entity_widgets:
                    self._update_entity_selection_visual(entity, True)
        
        # Update selection status
        self._update_selection_status()
    
    def _on_details_selection_changed(self):
        """Handle selection change in details view."""
        selected_items = self.details_widget.selectedItems()
        
        self.selected_entities.clear()
        for item in selected_items:
            entity = item.data(0, Qt.UserRole)
            if entity:
                self.selected_entities.append(entity)
        
        if self.selected_entities:
            self.entity_selected.emit(self.selected_entities[0])
    
    def _on_details_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle details item click."""
        pass  # Selection is handled by _on_details_selection_changed
    
    def _on_details_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle details item double click."""
        entity = item.data(0, Qt.UserRole)
        if entity:
            self.entity_double_clicked.emit(entity)
    
    def _on_details_context_menu(self, position):
        """Handle context menu request for details view."""
        item = self.details_widget.itemAt(position)
        if item:
            entity = item.data(0, Qt.UserRole)
            if entity and hasattr(self, 'context_menu_manager'):
                selected_items = self.details_widget.selectedItems()
                if len(selected_items) > 1:
                    selected_entities = [item.data(0, Qt.UserRole) for item in selected_items if item.data(0, Qt.UserRole)]
                    entities_for_menu = selected_entities
                else:
                    entities_for_menu = entity
                
                menu = self.context_menu_manager.create_entity_menu(entities_for_menu, self.details_widget)
                global_pos = self.details_widget.mapToGlobal(position)
                menu.exec_(global_pos)
    
    # Drag-drop and context menu setup (simplified versions)
    def _setup_drag_drop(self):
        """Setup drag and drop functionality."""
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.mpg', '.mpeg']
        image_extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.exr', '.dpx', '.bmp']
        
        self.setup_drag_drop(
            accept_files=True,
            accept_directories=True,
            file_extensions=video_extensions + image_extensions
        )
        
        self.files_dropped.connect(self._handle_dropped_files)
        self.directories_dropped.connect(self._handle_dropped_directories)
    
    @Slot(list)
    def _handle_dropped_files(self, file_paths: list):
        """Handle dropped files."""
        logger.info(f"Files dropped: {file_paths}")
        if len(file_paths) == 1:
            self.status_label.setText(f"File dropped: {Path(file_paths[0]).name}")
        else:
            self.status_label.setText(f"{len(file_paths)} files dropped")
    
    @Slot(list)
    def _handle_dropped_directories(self, directory_paths: list):
        """Handle dropped directories."""
        logger.info(f"Directories dropped: {directory_paths}")
        if directory_paths:
            self.load_directory(directory_paths[0])
            self.status_label.setText(f"Loaded directory: {Path(directory_paths[0]).name}")
    
    def _setup_context_menu(self):
        """Setup context menu manager."""
        self.context_menu_manager = ContextMenuManager(self)
        self.context_menu_manager.action_triggered.connect(self._on_context_action)
    
    @Slot(str, object)
    def _on_context_action(self, action: str, entity):
        """Handle context menu action."""
        logger.info(f"Context menu action '{action}' for entity: {entity.name}")
        
        # Handle favorites actions
        if action == "add_favorite":
            self._toggle_entity_favorite(entity)
        elif action == "user_favorite_toggled":
            self._refresh_entity_favorite_display(entity)
        elif action == "project_favorite_toggled":
            self._refresh_entity_favorite_display(entity)
        # Handle open action
        elif action == "open":
            self._open_entity_with_default_player(entity)
        # Handle tags updated
        elif action == "tags_updated":
            self._refresh_entity_display(entity)
        elif action == "multiple_tags_updated":
            self._refresh_multiple_entities_display(entity)  # entity is actually a list of entities in this case
        elif action == "copy_path":
            self.status_label.setText(f"Copied path: {entity.path}")
        elif action == "copy_name":
            self.status_label.setText(f"Copied name: {entity.name}")
        elif action == "show_in_manager":
            self.status_label.setText(f"Showing in file manager: {entity.name}")
    
    def _refresh_entity_display(self, entity):
        """Refresh the display for a specific entity (e.g., after tags update)."""

        entity_key = f"{entity.path}::{entity.name}"
        if entity_key in self.entity_widgets:
            try:
                # Update the thumbnail widget to show new tags
                self.entity_widgets[entity_key]._update_tags_display()
                logger.info(f"Refreshed tags display for: {entity.name}")
                self.status_label.setText(f"Tags updated for: {entity.name}")
            except Exception as e:
                logger.error(f"Error refreshing entity display for {entity.name}: {e}")
        else:
            # Entity widget doesn't exist yet - might be due to lazy loading
            # Trigger a refresh of visible widgets to ensure the entity gets updated
            logger.info(f"Entity widget not found for {entity.name}, triggering visible widget refresh")
            if hasattr(self, '_load_visible_widgets'):
                self._load_visible_widgets()
    
    def _refresh_multiple_entities_display(self, entities):
        """Refresh the display for multiple entities after batch tag update."""
        updated_count = 0
        try:
            for entity in entities:
                entity_key = f"{entity.path}::{entity.name}"
                if entity_key in self.entity_widgets:
                    try:
                        # Update the thumbnail widget to show new tags
                        self.entity_widgets[entity_key]._update_tags_display()
                        updated_count += 1
                    except Exception as e:
                        logger.error(f"Error refreshing entity display for {entity.name}: {e}")
                else:
                    # Entity widget doesn't exist yet - might be due to lazy loading
                    logger.debug(f"Entity widget not found for {entity.name}")
            
            logger.info(f"Refreshed tags display for {updated_count}/{len(entities)} entities")
            self.status_label.setText(f"Tags updated for {len(entities)} entities")
            
            # If some entities weren't found, refresh visible widgets
            if updated_count < len(entities) and hasattr(self, '_load_visible_widgets'):
                logger.info("Some entity widgets not found, triggering visible widget refresh")
                self._load_visible_widgets()
                
        except Exception as e:
            logger.error(f"Error in batch entity refresh: {e}")
    
    def _open_entity_with_default_player(self, entity):
        """Open entity with default system player."""
        if hasattr(self, 'context_menu_manager'):
            # Use the context menu manager's open functionality
            self.context_menu_manager._open_with_player(entity, "System Default")
            self.status_label.setText(f"Opened: {entity.name}")
        else:
            logger.warning("No context menu manager available for opening entity")
    
    def _refresh_entity_favorite_display(self, entity):
        """Refresh the favorite display for a specific entity."""
        entity_key = f"{entity.path}::{entity.name}"
        if entity_key in self.entity_widgets:
            # Update the thumbnail widget to show new favorite status
            self.entity_widgets[entity_key]._update_favorite_status()
            
            # If favorites filter is active, refresh the view but preserve selection
            if (self.search_criteria and
                (self.search_criteria.get('user_favorites_only') or
                 self.search_criteria.get('project_favorites_only') or
                 self.search_criteria.get('favorites_only'))):
                # Store current selection before recreating widgets
                selected_paths = [str(entity.path) for entity in self.selected_entities]
                self._create_entity_widgets()
                # Restore selection after recreating widgets
                self._restore_selection_by_paths(selected_paths)
    
    def _setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for selection and favorites."""
        from PySide6.QtGui import QShortcut, QKeySequence
        
        # Ctrl+A - Select All
        select_all_shortcut = QShortcut(QKeySequence.SelectAll, self)
        select_all_shortcut.activated.connect(self.select_all_entities)
        
        # Escape - Clear Selection
        clear_selection_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        clear_selection_shortcut.activated.connect(self.clear_selection)
        
        # F1 - Toggle User Favorites
        user_favorite_shortcut = QShortcut(QKeySequence(Qt.Key_F1), self)
        user_favorite_shortcut.activated.connect(self.toggle_selected_user_favorites)
        
        # F2 - Toggle Project Favorites
        project_favorite_shortcut = QShortcut(QKeySequence(Qt.Key_F2), self)
        project_favorite_shortcut.activated.connect(self.toggle_selected_project_favorites)
    
    def select_all_entities(self):
        """Select all visible entities."""
        entities_to_show = self.filtered_entities if self.search_criteria else self.current_entities
        
        self.clear_selection()
        for entity in entities_to_show:
            self.select_entity(entity, add_to_selection=True)
        
        logger.info(f"Selected all {len(entities_to_show)} entities")
    
    def toggle_selected_user_favorites(self):
        """Toggle user favorites status for all selected entities."""
        if not self.selected_entities:
            logger.info("No entities selected for toggling user favorites")
            self.status_label.setText("No entities selected for toggling user favorites")
            return
        
        if not self.app_controller or not hasattr(self.app_controller, 'config_manager'):
            logger.warning("Cannot toggle user favorites: no config manager available")
            return
        
        config_manager = self.app_controller.config_manager
        added_count = 0
        removed_count = 0
        
        for entity in self.selected_entities:
            try:
                file_path = str(entity.path)
                if config_manager.is_user_favorite(file_path):
                    # Remove from favorites
                    config_manager.remove_user_favorite(file_path)
                    removed_count += 1
                else:
                    # Add to favorites
                    config_manager.add_user_favorite(file_path)
                    added_count += 1
                    
                # Update the entity widget display
                entity_key = f"{entity.path}::{entity.name}"
                if entity_key in self.entity_widgets:
                    self.entity_widgets[entity_key]._update_favorite_status()
                        
            except Exception as e:
                logger.error(f"Error toggling user favorites for {entity.name}: {e}")
        
        # Save configuration
        try:
            config_manager.save_user_config()
            
            # Show appropriate status message
            if added_count > 0 and removed_count > 0:
                self.status_label.setText(f"Added {added_count}, removed {removed_count} from user favorites")
            elif added_count > 0:
                self.status_label.setText(f"Added {added_count} entities to user favorites")
            elif removed_count > 0:
                self.status_label.setText(f"Removed {removed_count} entities from user favorites")
            else:
                self.status_label.setText("No changes to user favorites")
                
            logger.info(f"Toggled user favorites: +{added_count}, -{removed_count}")
            
            # Check if we need to refresh view due to favorites filter
            needs_refresh = (self.search_criteria and
                            (self.search_criteria.get('user_favorites_only') or
                             self.search_criteria.get('favorites_only')))
            
            if needs_refresh:
                # Store current selection before recreating widgets
                selected_paths = [str(entity.path) for entity in self.selected_entities]
                self._create_entity_widgets()
                self._restore_selection_by_paths(selected_paths)
                
        except Exception as e:
            logger.error(f"Error saving user favorites: {e}")
            self.status_label.setText(f"Error saving user favorites: {e}")
    
    def toggle_selected_project_favorites(self):
        """Toggle project favorites status for all selected entities."""
        if not self.selected_entities:
            logger.info("No entities selected for toggling project favorites")
            self.status_label.setText("No entities selected for toggling project favorites")
            return
        
        if not self.app_controller or not hasattr(self.app_controller, 'config_manager'):
            logger.warning("Cannot toggle project favorites: no config manager available")
            return
        
        config_manager = self.app_controller.config_manager
        current_project_name = self._get_current_project_name()
        added_count = 0
        removed_count = 0
        
        for entity in self.selected_entities:
            try:
                file_path = str(entity.path)
                if config_manager.is_project_favorite(file_path, current_project_name):
                    # Remove from favorites
                    config_manager.remove_project_favorite(file_path, current_project_name)
                    removed_count += 1
                else:
                    # Add to favorites
                    config_manager.add_project_favorite(file_path, current_project_name)
                    added_count += 1
                    
                # Update the entity widget display
                entity_key = f"{entity.path}::{entity.name}"
                if entity_key in self.entity_widgets:
                    self.entity_widgets[entity_key]._update_favorite_status()
                        
            except Exception as e:
                logger.error(f"Error toggling project favorites for {entity.name}: {e}")
        
        # Save configuration
        try:
            config_manager.save_user_config()  # Project favorites are stored in user config
            
            # Show appropriate status message
            if added_count > 0 and removed_count > 0:
                self.status_label.setText(f"Added {added_count}, removed {removed_count} from project favorites ({current_project_name})")
            elif added_count > 0:
                self.status_label.setText(f"Added {added_count} entities to project favorites ({current_project_name})")
            elif removed_count > 0:
                self.status_label.setText(f"Removed {removed_count} entities from project favorites ({current_project_name})")
            else:
                self.status_label.setText(f"No changes to project favorites ({current_project_name})")
                
            logger.info(f"Toggled project favorites ({current_project_name}): +{added_count}, -{removed_count}")
            
            # Check if we need to refresh view due to favorites filter
            needs_refresh = (self.search_criteria and
                            (self.search_criteria.get('project_favorites_only') or
                             self.search_criteria.get('favorites_only')))
            
            if needs_refresh:
                # Store current selection before recreating widgets
                selected_paths = [str(entity.path) for entity in self.selected_entities]
                self._create_entity_widgets()
                self._restore_selection_by_paths(selected_paths)
                
        except Exception as e:
            logger.error(f"Error saving project favorites: {e}")
            self.status_label.setText(f"Error saving project favorites: {e}")
    
    def _setup_rubber_band_overlay(self):
        """Setup rubber band overlay widget."""
        try:
            # Use the local RubberBandOverlay class from this same file
            self.rubber_band_overlay = RubberBandOverlay(self)
            self.rubber_band_overlay.set_content_view(self)
            
            # Position overlay to cover the entire scroll area
            self._update_overlay_geometry()
            
            # Setup handlers to update overlay geometry when content changes
            self._setup_overlay_update_handlers()
            
            logger.info("Rubber band overlay setup completed successfully")
        except Exception as e:
            logger.error(f"Failed to setup rubber band overlay: {e}")
            self.rubber_band_overlay = None
    
    def refresh_rubber_band_overlay(self):
        """Refresh rubber band overlay geometry - called when tab is activated."""
        if hasattr(self, 'rubber_band_overlay') and self.rubber_band_overlay is not None:
            # Update overlay geometry to ensure it matches current scroll area
            self._update_overlay_geometry()
            logger.debug("Rubber band overlay geometry refreshed")
        
        
    
    def _update_overlay_geometry(self):
        """Update overlay geometry to cover the scroll area viewport."""
        if not hasattr(self, 'rubber_band_overlay') or self.rubber_band_overlay is None:
            return
            
        # Get scroll area viewport geometry relative to this widget
        # This ensures the overlay covers only the content area, not the scrollbars
        viewport = self.scroll_area.viewport()
        viewport_pos = self.scroll_area.mapTo(self, viewport.pos())
        viewport_size = viewport.size()
        
        # Create rectangle for the viewport area
        viewport_rect = QRect(viewport_pos, viewport_size)
        
        # Set overlay to cover only the viewport (content area)
        self.rubber_band_overlay.setGeometry(viewport_rect)
        self.rubber_band_overlay.show()
        self.rubber_band_overlay.raise_()
        
        
    
    def _setup_overlay_update_handlers(self):
        """Setup handlers to update overlay geometry when needed."""
        if not hasattr(self, 'rubber_band_overlay') or self.rubber_band_overlay is None:
            return
            
        # Override scroll area resize event
        original_resize = self.scroll_area.resizeEvent
        def new_resize_event(event):
            original_resize(event)
            self._update_overlay_geometry()
        
        self.scroll_area.resizeEvent = new_resize_event
        
        # Override this widget's resize event to update overlay
        original_widget_resize = self.resizeEvent
        def new_widget_resize_event(event):
            original_widget_resize(event)
            self._update_overlay_geometry()
        
        self.resizeEvent = new_widget_resize_event
    
    def _update_rubber_band_selection_from_overlay(self, rubber_band_rect: QRect):
        """Update entity selection based on rubber band rectangle from overlay with modifier support."""
        # Get entities to check (filtered or all)
        entities_to_check = self.filtered_entities if self.search_criteria else self.current_entities
        
        # Check modifier keys for different rubber band behaviors
        modifiers = QApplication.keyboardModifiers()
        shift_pressed = bool(modifiers & Qt.ShiftModifier)
        ctrl_pressed = bool(modifiers & Qt.ControlModifier)
        
        # Determine rubber band mode based on modifiers
        if shift_pressed:
            # Shift+rubber band: Append mode - add entities to existing selection
            rubber_band_mode = "append"
        elif ctrl_pressed:
            # Ctrl+rubber band: Remove mode - remove entities from existing selection
            rubber_band_mode = "remove"
        else:
            # No modifiers: Replace mode - replace selection with rubber band selection
            rubber_band_mode = "replace"
        
        # Store original selection for replace mode
        if rubber_band_mode == "replace":
            original_selection = self.selected_entities.copy()
            # Clear selection first, we'll rebuild it with rubber band results
            self._clear_selection()
        
        # Process entities based on rubber band intersection
        for entity in entities_to_check:
            entity_key = f"{entity.path}::{entity.name}"
            if entity_key in self.entity_widgets:
                widget = self.entity_widgets[entity_key]
                
                # Get widget position and size in content widget coordinates
                widget_pos_in_content = widget.pos()
                widget_size = widget.size()
                
                # Map widget position from content widget to scroll area viewport coordinates
                # The overlay is positioned to cover the scroll area viewport
                widget_pos_in_viewport = self.content_widget.mapTo(self.scroll_area.viewport(), widget_pos_in_content)
                
                # Create widget rectangle in viewport coordinates (which match overlay coordinates)
                widget_rect_in_overlay = QRect(widget_pos_in_viewport, widget_size)
                
                # Check if widget intersects with rubber band
                intersects = rubber_band_rect.intersects(widget_rect_in_overlay)
                
                if intersects:
                    if rubber_band_mode == "append":
                        # Shift+rubber band: Add entity to selection if not already selected
                        if not self._is_entity_selected(entity):
                            self._add_to_selection(entity)
                    elif rubber_band_mode == "remove":
                        # Ctrl+rubber band: Remove entity from selection if currently selected
                        if self._is_entity_selected(entity):
                            self._remove_from_selection(entity)
                    else:  # replace mode
                        # Normal rubber band: Add entity to new selection
                        self._add_to_selection(entity)
                
                # For replace mode, we don't need to handle non-intersecting entities
                # since we already cleared the selection
        
        # Update selection status
        self._update_selection_status()
    
    def mousePressEvent(self, event):
        """Handle mouse press events with rubber band support."""
        if event.button() == Qt.LeftButton:
            clicked_widget = self.childAt(event.pos())
            if (clicked_widget is None or
                clicked_widget == self.scroll_area or
                clicked_widget == self.content_widget or
                clicked_widget == self.scroll_area.viewport() or
                (hasattr(self, 'rubber_band_overlay') and clicked_widget == self.rubber_band_overlay)):
                
                # Clicking on empty space - start rubber band selection
                if hasattr(self, 'rubber_band_overlay'):
                    # Don't clear selection immediately - let rubber band handle it
                    self.rubber_band_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                    overlay_pos = self.rubber_band_overlay.mapFromParent(event.pos())
                    overlay_event = event.__class__(
                        event.type(), overlay_pos, event.globalPos(),
                        event.button(), event.buttons(), event.modifiers()
                    )
                    self.rubber_band_overlay.mousePressEvent(overlay_event)
                else:
                    # Fallback if no rubber band overlay
                    self.clear_selection()
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move events with rubber band support."""
        if (hasattr(self, 'rubber_band_overlay') and
            self.rubber_band_overlay is not None and
            not self.rubber_band_overlay.testAttribute(Qt.WA_TransparentForMouseEvents)):
            overlay_pos = self.rubber_band_overlay.mapFromParent(event.pos())
            overlay_event = event.__class__(
                event.type(), overlay_pos, event.globalPos(),
                event.button(), event.buttons(), event.modifiers()
            )
            self.rubber_band_overlay.mouseMoveEvent(overlay_event)
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release events with rubber band support."""
        if event.button() == Qt.LeftButton:
            if (hasattr(self, 'rubber_band_overlay') and
                self.rubber_band_overlay is not None and
                not self.rubber_band_overlay.testAttribute(Qt.WA_TransparentForMouseEvents)):
                overlay_pos = self.rubber_band_overlay.mapFromParent(event.pos())
                overlay_event = event.__class__(
                    event.type(), overlay_pos, event.globalPos(),
                    event.button(), event.buttons(), event.modifiers()
                )
                self.rubber_band_overlay.mouseReleaseEvent(overlay_event)
                self.rubber_band_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        
        super().mouseReleaseEvent(event)
    
    # Search and filtering methods (simplified)
    def apply_search_filter(self, criteria: Dict[str, Any]):
        """Apply search filter to current entities."""
        self.search_criteria = criteria
        self.filtered_entities = []
        
        for entity in self.current_entities:
            if self._entity_matches_criteria(entity, criteria):
                self.filtered_entities.append(entity)
        
        self._create_entity_widgets()
        
        visible = len(self.filtered_entities)
        total = len(self.current_entities)
        self.status_label.setText(f"Showing {visible} of {total} items (filtered)")
    
    def clear_search_filter(self):
        """Clear search filter and show all entities."""
        self.search_criteria = None
        self.filtered_entities = []
        self._create_entity_widgets()
        
        total = len(self.current_entities)
        self.status_label.setText(f"Showing all {total} items")
    
    def _entity_matches_criteria(self, entity: MediaEntity, criteria: Dict[str, Any]) -> bool:
        """Check if entity matches search criteria."""
        # Text search
        if 'text' in criteria:
            search_text = criteria['text'].lower()
            search_type = criteria.get('search_type', 'name')
            
            if search_type == 'name':
                if search_text not in entity.name.lower():
                    return False
            elif search_type == 'path':
                if search_text not in str(entity.path).lower():
                    return False
            else:  # all fields (name, path, tags)
                # Check name and path
                name_match = search_text in entity.name.lower()
                path_match = search_text in str(entity.path).lower()
                
                # Check tags
                tags_match = False
                entity_tags = self._get_entity_tags(entity)
                for tag in entity_tags:
                    if search_text in tag.lower():
                        tags_match = True
                        break
                
                if not (name_match or path_match or tags_match):
                    return False
        
        # User favorites filter
        if 'user_favorites_only' in criteria and criteria['user_favorites_only']:
            if not self._is_entity_user_favorite(entity):
                return False
        
        # Project favorites filter
        if 'project_favorites_only' in criteria and criteria['project_favorites_only']:
            if not self._is_entity_project_favorite(entity):
                return False
        
        # Legacy favorites filter (backward compatibility)
        if 'favorites_only' in criteria and criteria['favorites_only']:
            if not self._is_entity_user_favorite(entity):
                return False
        
        # File type filter
        if 'file_types' in criteria:
            # Determine actual type based on file characteristics and extension
            file_ext = entity.path.suffix.lstrip('.').lower()
            video_extensions = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v', 'mpg', 'mpeg', 'wmv', 'flv', 'f4v']
            image_extensions = ['jpg', 'jpeg', 'png', 'tiff', 'tif', 'exr', 'dpx', 'bmp', 'gif', 'webp']
            
            if len(entity.files) > 1:
                actual_type = "sequence"
            elif file_ext in video_extensions:
                actual_type = "video"
            elif file_ext in image_extensions:
                actual_type = "image"
            else:
                # Fallback - check frame count if available
                if entity.frame_count and entity.frame_count > 1:
                    actual_type = "video"
                else:
                    actual_type = "image"  # Default fallback
            
            if actual_type not in criteria['file_types']:
                return False
        
        return True
    
    def _is_entity_user_favorite(self, entity: MediaEntity) -> bool:
        """Check if entity is marked as user favorite in configuration."""
        if not self.app_controller or not hasattr(self.app_controller, 'config_manager'):
            return False
        
        try:
            config_manager = self.app_controller.config_manager
            file_path = str(entity.path)
            return config_manager.is_user_favorite(file_path)
        except Exception as e:
            logger.debug(f"Error checking user favorite status for {entity.name}: {e}")
            return False
    
    def _is_entity_project_favorite(self, entity: MediaEntity) -> bool:
        """Check if entity is marked as project favorite in configuration."""
        if not self.app_controller or not hasattr(self.app_controller, 'config_manager'):
            return False
        
        try:
            config_manager = self.app_controller.config_manager
            file_path = str(entity.path)
            # Always check since we now always have a project name
            current_project_name = self._get_current_project_name()
            return config_manager.is_project_favorite(file_path, current_project_name)
        except Exception as e:
            logger.debug(f"Error checking project favorite status for {entity.name}: {e}")
            return False
    
    def _get_entity_tags(self, entity: MediaEntity) -> List[str]:
        """Get tags for an entity using direct database access."""
        if not self.multi_database_manager:
            return []
        
        try:
            with self.multi_database_manager.get_session_for_path(self.current_directory, for_tags=True) as session:
                from ..database.models import Tag, Entity, entity_tags
                
                # Find the entity in database
                db_entity = session.query(Entity).filter_by(
                    path=str(entity.path),
                    entity_type=entity.entity_type.value
                ).first()
                
                if db_entity:
                    # Get entity tags
                    tags = session.query(Tag).join(entity_tags).filter(
                        entity_tags.c.entity_id == db_entity.id
                    ).all()
                    
                    return [tag.name for tag in tags]
                
                return []
        except Exception as e:
            logger.debug(f"Error getting tags for {entity.name}: {e}")
            return []
    
    def get_visible_entity_count(self) -> int:
        """Get count of currently visible entities."""
        if self.search_criteria:
            return len(self.filtered_entities)
        return len(self.current_entities)
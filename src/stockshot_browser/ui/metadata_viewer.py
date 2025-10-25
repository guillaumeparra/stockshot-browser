"""
Metadata viewer widget for Stockshot Browser.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QScrollArea, QFrame, QSplitter, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QCheckBox, QDateTimeEdit, QPlainTextEdit
)
from PySide6.QtCore import Qt, Signal, QDateTime
from PySide6.QtGui import QFont, QPixmap, QPalette

from ..core.entity_manager import MediaEntity
from ..core.metadata_exporter import MetadataExporter

logger = logging.getLogger(__name__)


class MetadataViewerWidget(QWidget):
    """Widget for displaying comprehensive metadata for media entities."""
    
    # Signals
    closed = Signal()
    
    def __init__(self, app_controller, parent=None):
        super().__init__(parent)
        self.app_controller = app_controller
        self.current_entity: Optional[MediaEntity] = None
        self.metadata_exporter = MetadataExporter(app_controller.database_manager)
        
        self._setup_ui()
        
        logger.info("MetadataViewerWidget initialized")
    
    def _setup_ui(self):
        """Setup the metadata viewer UI."""
        layout = QVBoxLayout(self)
        
        # Header with entity info
        header_layout = QHBoxLayout()
        
        # Entity info
        self.entity_info_label = QLabel("No entity selected")
        self.entity_info_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #0078d4;")
        header_layout.addWidget(self.entity_info_label)
        
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Main content area - single combined tab
        self.main_content = self._create_combined_info_tab()
        layout.addWidget(self.main_content)
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666; font-style: italic; padding: 5px;")
        layout.addWidget(self.status_label)
    
    def _create_combined_info_tab(self) -> QWidget:
        """Create combined basic information and tags tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Create form layout for basic info
        form_group = QGroupBox("Entity Information")
        form_layout = QFormLayout(form_group)
        
        # White text styling for form fields
        field_style = """
        QLineEdit {
            color: white;
            background-color: #2d2d2d;
            border: 1px solid #555555;
            border-radius: 3px;
            padding: 4px;
        }
        QLineEdit:focus {
            border-color: #0078d4;
        }
        """
        
        # Basic fields with white text
        self.name_field = QLineEdit()
        self.name_field.setReadOnly(True)
        self.name_field.setStyleSheet(field_style)
        form_layout.addRow("Name:", self.name_field)
        
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        self.path_field.setStyleSheet(field_style)
        form_layout.addRow("Path:", self.path_field)
        
        self.type_field = QLineEdit()
        self.type_field.setReadOnly(True)
        self.type_field.setStyleSheet(field_style)
        form_layout.addRow("Type:", self.type_field)
        
        self.size_field = QLineEdit()
        self.size_field.setReadOnly(True)
        self.size_field.setStyleSheet(field_style)
        form_layout.addRow("File Size:", self.size_field)
        
        self.modified_field = QLineEdit()
        self.modified_field.setReadOnly(True)
        self.modified_field.setStyleSheet(field_style)
        form_layout.addRow("Modified:", self.modified_field)
        
        self.frames_field = QLineEdit()
        self.frames_field.setReadOnly(True)
        self.frames_field.setStyleSheet(field_style)
        form_layout.addRow("Frame Count:", self.frames_field)
        
        layout.addWidget(form_group)
        
        # Tags section
        tags_group = QGroupBox("Tags")
        tags_layout = QVBoxLayout(tags_group)
        
        self.tags_list = QTreeWidget()
        self.tags_list.setHeaderLabels(["Tag"])
        self.tags_list.setAlternatingRowColors(True)
        self.tags_list.setMaximumHeight(150)  # Limit height for compact display
        self.tags_list.setRootIsDecorated(False)  # Remove expand/collapse decorations
        tags_layout.addWidget(self.tags_list)
        
        layout.addWidget(tags_group)
        layout.addStretch()
        
        return widget
    
    
    def show_entity_metadata(self, entity: MediaEntity):
        """Display metadata for the given entity."""
        self.current_entity = entity
        # Truncate long names for better display in dock
        display_name = entity.name
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."
        self.entity_info_label.setText(f"{display_name}")
        self.status_label.setText(f"Loading metadata...")
        
        # Load metadata
        self._load_entity_metadata()
    
    def _load_entity_metadata(self):
        """Load and display metadata for current entity."""
        if not self.current_entity:
            logger.warning("🔍 MetadataViewer: _load_entity_metadata called but no current_entity")
            return
        
        
        try:
            # Get entity from database
            with self.app_controller.database_manager.get_session() as session:
                from ..database.models import Entity, Metadata, Tag, entity_tags
                
                # Find entity in database
                db_entity = session.query(Entity).filter_by(
                    path=str(self.current_entity.path),
                    entity_type=self.current_entity.entity_type.value
                ).first()
                
                
                if db_entity:
                    # Load basic info
                    self._load_basic_info(db_entity)
                    
                    # Load tags
                    self._load_tags_metadata(db_entity, session)
                    
                    self.status_label.setText("Metadata loaded successfully")
                else:
                    logger.warning(f"🔍 MetadataViewer: Entity not found in database: {self.current_entity.path}")
                    self._clear_all_fields()
                    self.status_label.setText("Entity not found in database")
                    
        except Exception as e:
            logger.error(f"🔍 MetadataViewer: Error loading metadata for {self.current_entity.name}: {e}")
            self.status_label.setText(f"Error loading metadata: {e}")
    
    def _load_basic_info(self, db_entity):
        """Load basic entity information."""
        self.name_field.setText(db_entity.name or "")
        self.path_field.setText(db_entity.path or "")
        self.type_field.setText(db_entity.entity_type or "")
        
        # File size
        if db_entity.file_size:
            size_mb = db_entity.file_size / (1024 * 1024)
            if size_mb >= 1:
                self.size_field.setText(f"{size_mb:.1f} MB")
            else:
                size_kb = db_entity.file_size / 1024
                self.size_field.setText(f"{size_kb:.1f} KB")
        else:
            self.size_field.setText("Unknown")
        
        # Modified date
        try:
            if self.current_entity.path.exists():
                mtime = self.current_entity.path.stat().st_mtime
                from datetime import datetime
                mod_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                self.modified_field.setText(mod_date)
            else:
                self.modified_field.setText("File not found")
        except:
            self.modified_field.setText("Unknown")
        
        # Frame count
        if hasattr(self.current_entity, 'files') and len(self.current_entity.files) > 1:
            self.frames_field.setText(str(len(self.current_entity.files)))
        else:
            self.frames_field.setText("1" if self.current_entity.entity_type.value != "video" else "N/A")
    
    
    def _load_tags_metadata(self, db_entity, session):
        """Load tags metadata."""
        self.tags_list.clear()
        
        try:
            from ..database.models import Tag, entity_tags
            
            # Load tags
            tags = session.query(Tag).join(entity_tags).filter(
                entity_tags.c.entity_id == db_entity.id
            ).all()
            
            for tag in tags:
                item = QTreeWidgetItem([tag.name])
                self.tags_list.addTopLevelItem(item)
                
        except Exception as e:
            logger.error(f"Error loading tags metadata: {e}")
            error_item = QTreeWidgetItem(["Error loading tags"])
            self.tags_list.addTopLevelItem(error_item)
    
    
    def _clear_all_fields(self):
        """Clear all metadata fields."""
        # Basic info
        self.name_field.clear()
        self.path_field.clear()
        self.type_field.clear()
        self.size_field.clear()
        self.modified_field.clear()
        self.frames_field.clear()
        
        # Tags
        self.tags_list.clear()
    
    
    def clear_metadata(self):
        """Clear metadata display when no entity is selected."""
        self.current_entity = None
        self.entity_info_label.setText("No entity selected")
        self.status_label.setText("Select an entity to view its metadata")
        self._clear_all_fields()
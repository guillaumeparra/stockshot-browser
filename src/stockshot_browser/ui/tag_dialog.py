"""
Tag management dialog for Stockshot Browser.
"""

import logging
from typing import List, Set
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox,
    QCompleter
)
from PySide6.QtCore import Qt, Signal, QStringListModel
from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)


class TagDialog(QDialog):
    """Dialog for adding/editing tags for media entities."""
    
    tags_updated = Signal(list)  # Emitted when tags are updated
    
    def __init__(self, entities, app_controller, parent=None):
        super().__init__(parent)
        # Support both single entity and multiple entities
        if isinstance(entities, list):
            self.entities = entities
            self.is_multi_entity = True
        else:
            self.entities = [entities]
            self.is_multi_entity = False
        
        self.app_controller = app_controller
        self.current_tags = set()
        self.all_existing_tags = set()
        
        # Set window title based on single or multiple entities
        if self.is_multi_entity:
            self.setWindowTitle(f"Manage Tags - {len(self.entities)} entities")
        else:
            self.setWindowTitle(f"Manage Tags - {self.entities[0].name}")
        
        self.setModal(True)
        self.setMinimumSize(400, 300)
        
        self._setup_ui()
        self._load_existing_tags()
        self._load_entity_tags()
        
    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Title
        if self.is_multi_entity:
            title_text = f"Tags for {len(self.entities)} selected entities"
        else:
            title_text = f"Tags for: {self.entities[0].name}"
        
        title_label = QLabel(title_text)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Show entity names for multi-selection (limited to first few)
        if self.is_multi_entity:
            entity_names = [entity.name for entity in self.entities[:3]]
            if len(self.entities) > 3:
                entity_names.append(f"... and {len(self.entities) - 3} more")
            
            names_label = QLabel("Entities: " + ", ".join(entity_names))
            names_label.setStyleSheet("color: #666; font-style: italic;")
            names_label.setWordWrap(True)
            layout.addWidget(names_label)
        
        # Add tag section
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("Add Tag:"))
        
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Enter tag name...")
        self.tag_input.returnPressed.connect(self._add_tag)
        add_layout.addWidget(self.tag_input)
        
        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self._add_tag)
        add_layout.addWidget(self.add_button)
        
        layout.addLayout(add_layout)
        
        # Current tags list
        layout.addWidget(QLabel("Current Tags:"))
        self.tags_list = QListWidget()
        self.tags_list.setMaximumHeight(150)
        layout.addWidget(self.tags_list)
        
        # Remove button
        remove_layout = QHBoxLayout()
        remove_layout.addStretch()
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._remove_selected_tag)
        self.remove_button.setEnabled(False)
        remove_layout.addWidget(self.remove_button)
        layout.addLayout(remove_layout)
        
        # Connect list selection
        self.tags_list.itemSelectionChanged.connect(self._on_selection_changed)
        
        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save_tags)
        save_button.setDefault(True)
        button_layout.addWidget(save_button)
        
        layout.addLayout(button_layout)
    
    def _load_existing_tags(self):
        """Load all existing tags for autocomplete."""
        try:
            # Use multi-context database manager if available
            db_manager = getattr(self.app_controller, 'multi_database_manager', None)
            if not db_manager:
                db_manager = self.app_controller.database_manager
            
            with db_manager.get_session(for_tags=True) as session:
                from ..database.models import Tag
                
                existing_tags = session.query(Tag.name).distinct().all()
                self.all_existing_tags = {tag.name for tag in existing_tags}
                
                # Setup autocomplete
                if self.all_existing_tags:
                    completer = QCompleter(list(self.all_existing_tags))
                    completer.setCaseSensitivity(Qt.CaseInsensitive)
                    self.tag_input.setCompleter(completer)
                    
        except Exception as e:
            logger.error(f"Error loading existing tags: {e}")
    
    def _load_entity_tags(self):
        """Load current tags for the entities."""
        try:
            # Use multi-context database manager if available
            db_manager = getattr(self.app_controller, 'multi_database_manager', None)
            if not db_manager:
                db_manager = self.app_controller.database_manager
            
            with db_manager.get_session(for_tags=True) as session:
                from ..database.models import Tag, Entity, entity_tags
                
                if self.is_multi_entity:
                    # For multiple entities, load common tags (intersection)
                    all_entity_tags = []
                    
                    for entity in self.entities:
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
                            
                            entity_tag_names = {tag.name for tag in tags}
                            all_entity_tags.append(entity_tag_names)
                    
                    # Find common tags across all entities
                    if all_entity_tags:
                        self.current_tags = set.intersection(*all_entity_tags) if all_entity_tags else set()
                    else:
                        self.current_tags = set()
                else:
                    # Single entity - load its tags
                    entity = self.entities[0]
                    db_entity = session.query(Entity).filter_by(
                        path=str(entity.path),
                        entity_type=entity.entity_type.value
                    ).first()
                    
                    if db_entity:
                        # Get entity tags
                        tags = session.query(Tag).join(entity_tags).filter(
                            entity_tags.c.entity_id == db_entity.id
                        ).all()
                        
                        self.current_tags = {tag.name for tag in tags}
                
                self._update_tags_list()
                    
        except Exception as e:
            logger.error(f"Error loading entity tags: {e}")
    
    def _update_tags_list(self):
        """Update the tags list widget."""
        self.tags_list.clear()
        for tag in sorted(self.current_tags):
            item = QListWidgetItem(tag)
            self.tags_list.addItem(item)
    
    def _add_tag(self):
        """Add a new tag."""
        tag_name = self.tag_input.text().strip()
        if not tag_name:
            return
        
        if tag_name in self.current_tags:
            QMessageBox.information(self, "Tag Exists", f"Tag '{tag_name}' already exists for this entity.")
            return
        
        self.current_tags.add(tag_name)
        self._update_tags_list()
        self.tag_input.clear()
        
        if self.is_multi_entity:
            logger.debug(f"Added tag '{tag_name}' to {len(self.entities)} entities")
        else:
            logger.debug(f"Added tag '{tag_name}' to entity {self.entities[0].name}")
    
    def _remove_selected_tag(self):
        """Remove the selected tag."""
        current_item = self.tags_list.currentItem()
        if current_item:
            tag_name = current_item.text()
            self.current_tags.discard(tag_name)
            self._update_tags_list()
            if self.is_multi_entity:
                logger.debug(f"Removed tag '{tag_name}' from {len(self.entities)} entities")
            else:
                logger.debug(f"Removed tag '{tag_name}' from entity {self.entities[0].name}")
    
    def _on_selection_changed(self):
        """Handle tag selection change."""
        has_selection = self.tags_list.currentItem() is not None
        self.remove_button.setEnabled(has_selection)
    
    def _save_tags(self):
        """Save tags to database for all entities with optimized batch operations."""
        try:
            # Use multi-context database manager if available
            db_manager = getattr(self.app_controller, 'multi_database_manager', None)
            if not db_manager:
                db_manager = self.app_controller.database_manager
            with db_manager.get_session(for_tags=True) as session:
                from ..database.models import Tag, Entity, entity_tags
                
                # Batch create/find all tags first to avoid repeated queries
                tag_objects = {}
                for tag_name in self.current_tags:
                    tag = session.query(Tag).filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        session.add(tag)
                        session.flush()  # Get the ID
                    tag_objects[tag_name] = tag
                
                # Process entities with optimized operations
                entity_ids = []
                for entity in self.entities:
                    # Find or create the entity in database
                    db_entity = session.query(Entity).filter_by(
                        path=str(entity.path),
                        entity_type=entity.entity_type.value
                    ).first()
                    
                    if not db_entity:
                        # Create entity in database if it doesn't exist
                        db_entity = Entity(
                            path=str(entity.path),
                            name=entity.name,
                            entity_type=entity.entity_type.value,
                            file_size=entity.file_size
                        )
                        session.add(db_entity)
                        session.flush()  # Get the ID
                    
                    entity_ids.append(db_entity.id)
                
                # Batch clear existing tags for all entities
                if entity_ids:
                    session.execute(
                        entity_tags.delete().where(entity_tags.c.entity_id.in_(entity_ids))
                    )
                
                # Batch create new tag relationships
                if self.current_tags and entity_ids:
                    relationships = []
                    for entity_id in entity_ids:
                        for tag_name in self.current_tags:
                            relationships.append({
                                'entity_id': entity_id,
                                'tag_id': tag_objects[tag_name].id
                            })
                    
                    if relationships:
                        session.execute(entity_tags.insert(), relationships)
                
                session.commit()
                # Emit signal with updated tags - this will trigger content refresh
                self.tags_updated.emit(list(self.current_tags))
                
                self.accept()
                
                if self.is_multi_entity:
                    logger.info(f"Saved {len(self.current_tags)} tags for {len(self.entities)} entities")
                else:
                    logger.info(f"Saved {len(self.current_tags)} tags for entity {self.entities[0].name}")
        except Exception as e:
            logger.error(f"Error saving tags: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save tags: {e}")
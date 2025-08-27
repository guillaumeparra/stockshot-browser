# Stockshot Browser - Technical Specification

## Development Environment Setup

### Dependencies and Requirements

```python
# requirements.txt
PySide6>=6.5.0
SQLAlchemy>=2.0.0
ffmpeg-python>=0.2.0
OpenColorIO>=2.2.0
Pillow>=10.0.0
watchdog>=3.0.0
pytest>=7.0.0
pytest-qt>=4.0.0
black>=23.0.0
flake8>=6.0.0
```

### Project Structure

```
stockshot_browser/
├── src/
│   ├── stockshot_browser/
│   │   ├── __init__.py
│   │   ├── main.py                    # Application entry point
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── manager.py             # Configuration management
│   │   │   ├── schemas.py             # Configuration validation schemas
│   │   │   └── defaults.py            # Default configuration values
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── application.py         # Main application class
│   │   │   ├── entity_manager.py      # Entity management
│   │   │   ├── metadata_manager.py    # Metadata handling
│   │   │   ├── thumbnail_manager.py   # Thumbnail generation
│   │   │   └── context_manager.py     # Project context handling
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── models.py              # SQLAlchemy models
│   │   │   ├── connection.py          # Database connection
│   │   │   └── migrations/            # Database migrations
│   │   ├── ui/
│   │   │   ├── __init__.py
│   │   │   ├── main_window.py         # Main application window
│   │   │   ├── directory_tree.py      # Directory tree widget
│   │   │   ├── content_view.py        # Content display widget
│   │   │   ├── tab_manager.py         # Tab management
│   │   │   ├── search_widget.py       # Search and filter UI
│   │   │   ├── context_menu.py        # Context menu implementation
│   │   │   └── dialogs/               # Various dialog windows
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── file_utils.py          # File system utilities
│   │   │   ├── ffmpeg_utils.py        # FFmpeg integration
│   │   │   ├── sequence_detector.py   # Image sequence detection
│   │   │   └── color_management.py    # OCIO integration
│   │   └── resources/
│   │       ├── icons/                 # Application icons
│   │       ├── styles/                # Qt stylesheets
│   │       └── config_templates/      # Configuration templates
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
├── scripts/
│   ├── build.py                       # Build script
│   └── package.py                     # Packaging script
├── requirements.txt
├── setup.py
├── pyproject.toml
└── README.md
```

## Core Component Implementation Details

### 1. Configuration Manager

```python
# config/manager.py
from typing import Dict, Any, Optional
import json
import os
from pathlib import Path
from .schemas import ConfigSchema
from .defaults import DEFAULT_CONFIG

class ConfigurationManager:
    """Manages cascading configuration system."""
    
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._config_paths: Dict[str, Path] = {}
        self._loaded = False
    
    def load_configuration(self, 
                          general_config_path: Optional[str] = None,
                          project_config_path: Optional[str] = None,
                          user_config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load and merge configuration files in cascade order."""
        
        # Start with defaults
        self._config = DEFAULT_CONFIG.copy()
        
        # Load general configuration
        if general_config_path and os.path.exists(general_config_path):
            general_config = self._load_json_config(general_config_path)
            self._merge_config(self._config, general_config)
            self._config_paths['general'] = Path(general_config_path)
        
        # Load project configuration
        if project_config_path and os.path.exists(project_config_path):
            project_config = self._load_json_config(project_config_path)
            self._merge_config(self._config, project_config)
            self._config_paths['project'] = Path(project_config_path)
        
        # Load user configuration
        if user_config_path and os.path.exists(user_config_path):
            user_config = self._load_json_config(user_config_path)
            self._merge_config(self._config, user_config)
            self._config_paths['user'] = Path(user_config_path)
        
        # Validate final configuration
        self._validate_config()
        self._loaded = True
        
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation."""
        if not self._loaded:
            raise RuntimeError("Configuration not loaded")
        
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any, persist: bool = True) -> None:
        """Set configuration value and optionally persist to user config."""
        keys = key.split('.')
        config = self._config
        
        # Navigate to parent of target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
        
        if persist and 'user' in self._config_paths:
            self._save_user_config()
```

### 2. Entity Manager

```python
# core/entity_manager.py
from typing import List, Dict, Optional, Set
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import os
import re
from ..utils.sequence_detector import SequenceDetector
from ..database.models import Entity, EntityType

class EntityType(Enum):
    VIDEO = "video"
    SEQUENCE = "sequence"

@dataclass
class MediaEntity:
    """Represents a media entity (video file or image sequence)."""
    path: Path
    entity_type: EntityType
    name: str
    files: List[Path]  # For sequences, contains all files
    frame_range: Optional[tuple] = None  # (start_frame, end_frame)
    
class EntityManager:
    """Manages media entities and their detection."""
    
    def __init__(self, config_manager, sequence_detector: SequenceDetector):
        self.config = config_manager
        self.sequence_detector = sequence_detector
        self.video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.wmv'}
        self.image_extensions = {'.exr', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.dpx'}
    
    def scan_directory(self, directory_path: Path) -> List[MediaEntity]:
        """Scan directory for media entities."""
        entities = []
        
        if not directory_path.exists() or not directory_path.is_dir():
            return entities
        
        # Get all files in directory
        all_files = [f for f in directory_path.iterdir() if f.is_file()]
        
        # Separate video files and image files
        video_files = [f for f in all_files if f.suffix.lower() in self.video_extensions]
        image_files = [f for f in all_files if f.suffix.lower() in self.image_extensions]
        
        # Process video files
        for video_file in video_files:
            entity = MediaEntity(
                path=video_file,
                entity_type=EntityType.VIDEO,
                name=video_file.stem,
                files=[video_file]
            )
            entities.append(entity)
        
        # Process image sequences
        sequences = self.sequence_detector.detect_sequences(image_files)
        for sequence_info in sequences:
            entity = MediaEntity(
                path=sequence_info['base_path'],
                entity_type=EntityType.SEQUENCE,
                name=sequence_info['name'],
                files=sequence_info['files'],
                frame_range=sequence_info.get('frame_range')
            )
            entities.append(entity)
        
        return entities
    
    def get_entity_thumbnail_path(self, entity: MediaEntity) -> Path:
        """Get the path where entity thumbnail should be stored."""
        cache_dir = Path(self.config.get('thumbnails.cache_directory', '.thumbnails'))
        resolution = self.config.get('thumbnails.default_resolution', 128)
        
        # Create unique identifier for entity
        if entity.entity_type == EntityType.VIDEO:
            identifier = f"{entity.path.stem}_{entity.path.stat().st_mtime}"
        else:
            # For sequences, use first file's mtime and file count
            first_file = entity.files[0] if entity.files else entity.path
            identifier = f"{entity.name}_{first_file.stat().st_mtime}_{len(entity.files)}"
        
        thumbnail_name = f"{identifier}_{resolution}.jpg"
        return cache_dir / thumbnail_name
```

### 3. Metadata Manager

```python
# core/metadata_manager.py
from typing import Dict, Any, List, Optional
import json
from pathlib import Path
from sqlalchemy.orm import Session
from ..database.models import Entity, Metadata, Tag
from ..database.connection import get_session
from ..utils.ffmpeg_utils import FFmpegExtractor

class MetadataManager:
    """Manages metadata extraction, storage, and retrieval."""
    
    def __init__(self, config_manager):
        self.config = config_manager
        self.ffmpeg_extractor = FFmpegExtractor(config_manager)
    
    def extract_metadata(self, entity_path: Path, entity_type: str) -> Dict[str, Any]:
        """Extract metadata from media entity."""
        metadata = {}
        
        try:
            if entity_type == "video":
                metadata = self._extract_video_metadata(entity_path)
            elif entity_type == "sequence":
                metadata = self._extract_sequence_metadata(entity_path)
        except Exception as e:
            print(f"Error extracting metadata from {entity_path}: {e}")
            metadata = self._get_basic_file_metadata(entity_path)
        
        return metadata
    
    def _extract_video_metadata(self, video_path: Path) -> Dict[str, Any]:
        """Extract metadata from video file using FFmpeg."""
        metadata = self.ffmpeg_extractor.extract_video_info(video_path)
        
        # Add file system metadata
        stat = video_path.stat()
        metadata.update({
            'file_size': stat.st_size,
            'created_at': stat.st_ctime,
            'modified_at': stat.st_mtime,
            'file_path': str(video_path)
        })
        
        return metadata
    
    def _extract_sequence_metadata(self, sequence_path: Path) -> Dict[str, Any]:
        """Extract metadata from image sequence."""
        # For sequences, analyze the first frame
        first_frame = None
        if sequence_path.is_dir():
            image_files = [f for f in sequence_path.iterdir() 
                          if f.suffix.lower() in {'.exr', '.png', '.jpg', '.jpeg', '.tiff', '.dpx'}]
            if image_files:
                first_frame = sorted(image_files)[0]
        else:
            first_frame = sequence_path
        
        if first_frame and first_frame.exists():
            metadata = self.ffmpeg_extractor.extract_image_info(first_frame)
            
            # Add sequence-specific metadata
            if sequence_path.is_dir():
                frame_count = len([f for f in sequence_path.iterdir() 
                                 if f.suffix.lower() in {'.exr', '.png', '.jpg', '.jpeg', '.tiff', '.dpx'}])
                metadata['frame_count'] = frame_count
                metadata['total_size'] = sum(f.stat().st_size for f in sequence_path.iterdir() if f.is_file())
            
            return metadata
        
        return self._get_basic_file_metadata(sequence_path)
    
    def store_metadata(self, entity_id: int, metadata: Dict[str, Any]) -> None:
        """Store metadata in database."""
        with get_session() as session:
            # Check if metadata already exists
            existing = session.query(Metadata).filter_by(entity_id=entity_id).first()
            
            if existing:
                # Update existing metadata
                for key, value in metadata.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                    else:
                        # Store in custom_fields JSON
                        custom_fields = json.loads(existing.custom_fields or '{}')
                        custom_fields[key] = value
                        existing.custom_fields = json.dumps(custom_fields)
            else:
                # Create new metadata record
                custom_fields = {}
                metadata_obj = Metadata(entity_id=entity_id)
                
                # Set standard fields
                standard_fields = ['duration', 'fps', 'width', 'height', 'colorspace', 
                                 'file_size', 'format', 'codec']
                
                for field in standard_fields:
                    if field in metadata:
                        setattr(metadata_obj, field, metadata[field])
                    else:
                        custom_fields[field] = metadata[field]
                
                metadata_obj.custom_fields = json.dumps(custom_fields)
                session.add(metadata_obj)
            
            session.commit()
    
    def search_entities(self, query: str, filters: Dict[str, Any] = None) -> List[int]:
        """Search entities based on metadata."""
        with get_session() as session:
            # Build query
            base_query = session.query(Entity.id)
            
            if query:
                # Search in entity name and metadata
                base_query = base_query.join(Metadata).filter(
                    Entity.name.contains(query) |
                    Metadata.format.contains(query) |
                    Metadata.codec.contains(query)
                )
            
            if filters:
                base_query = base_query.join(Metadata)
                
                for key, value in filters.items():
                    if key == 'duration_min':
                        base_query = base_query.filter(Metadata.duration >= value)
                    elif key == 'duration_max':
                        base_query = base_query.filter(Metadata.duration <= value)
                    elif key == 'colorspace':
                        base_query = base_query.filter(Metadata.colorspace == value)
                    elif key == 'fps':
                        base_query = base_query.filter(Metadata.fps == value)
                    # Add more filter conditions as needed
            
            return [result[0] for result in base_query.all()]
```

### 4. Thumbnail Manager

```python
# core/thumbnail_manager.py
from typing import Optional, Tuple
from pathlib import Path
import threading
from queue import Queue
from PIL import Image
import subprocess
from ..utils.ffmpeg_utils import FFmpegThumbnailGenerator
from ..utils.color_management import ColorManager

class ThumbnailManager:
    """Manages thumbnail generation and caching."""
    
    def __init__(self, config_manager):
        self.config = config_manager
        self.ffmpeg_generator = FFmpegThumbnailGenerator(config_manager)
        self.color_manager = ColorManager(config_manager)
        
        # Threading for background generation
        self.generation_queue = Queue()
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        
        # Cache directory setup
        self.cache_dir = Path(self.config.get('thumbnails.cache_directory', '.thumbnails'))
        self.cache_dir.mkdir(exist_ok=True)
    
    def get_thumbnail(self, entity_path: Path, entity_type: str, 
                     resolution: int = None, force_regenerate: bool = False) -> Optional[Path]:
        """Get thumbnail for entity, generating if necessary."""
        
        if resolution is None:
            resolution = self.config.get('thumbnails.default_resolution', 128)
        
        thumbnail_path = self._get_thumbnail_path(entity_path, entity_type, resolution)
        
        # Check if thumbnail exists and is up to date
        if not force_regenerate and thumbnail_path.exists():
            entity_mtime = entity_path.stat().st_mtime
            thumb_mtime = thumbnail_path.stat().st_mtime
            
            if thumb_mtime > entity_mtime:
                return thumbnail_path
        
        # Generate thumbnail
        if entity_type == "video":
            success = self._generate_video_thumbnail(entity_path, thumbnail_path, resolution)
        elif entity_type == "sequence":
            success = self._generate_sequence_thumbnail(entity_path, thumbnail_path, resolution)
        else:
            return None
        
        return thumbnail_path if success else None
    
    def generate_thumbnail_async(self, entity_path: Path, entity_type: str, 
                               resolution: int = None, callback=None):
        """Queue thumbnail generation for background processing."""
        self.generation_queue.put({
            'entity_path': entity_path,
            'entity_type': entity_type,
            'resolution': resolution or self.config.get('thumbnails.default_resolution', 128),
            'callback': callback
        })
    
    def _generate_video_thumbnail(self, video_path: Path, output_path: Path, 
                                resolution: int) -> bool:
        """Generate thumbnail from video file."""
        try:
            # Extract frame at 10% of video duration
            duration = self.ffmpeg_generator.get_video_duration(video_path)
            timestamp = duration * 0.1 if duration else 1.0
            
            # Generate thumbnail using FFmpeg
            success = self.ffmpeg_generator.extract_frame(
                video_path, output_path, timestamp, resolution
            )
            
            if success and self.config.get('color_management.enabled', False):
                # Apply color management
                self.color_manager.apply_color_transform(output_path)
            
            return success
            
        except Exception as e:
            print(f"Error generating video thumbnail: {e}")
            return False
    
    def _generate_sequence_thumbnail(self, sequence_path: Path, output_path: Path, 
                                   resolution: int) -> bool:
        """Generate thumbnail from image sequence."""
        try:
            # Find middle frame of sequence
            if sequence_path.is_dir():
                image_files = sorted([f for f in sequence_path.iterdir() 
                                    if f.suffix.lower() in {'.exr', '.png', '.jpg', '.jpeg', '.tiff', '.dpx'}])
                if not image_files:
                    return False
                
                middle_frame = image_files[len(image_files) // 2]
            else:
                middle_frame = sequence_path
            
            # Generate thumbnail from middle frame
            success = self.ffmpeg_generator.extract_image_thumbnail(
                middle_frame, output_path, resolution
            )
            
            if success and self.config.get('color_management.enabled', False):
                self.color_manager.apply_color_transform(output_path)
            
            return success
            
        except Exception as e:
            print(f"Error generating sequence thumbnail: {e}")
            return False
    
    def _worker(self):
        """Background worker for thumbnail generation."""
        while True:
            try:
                task = self.generation_queue.get()
                if task is None:  # Shutdown signal
                    break
                
                thumbnail_path = self.get_thumbnail(
                    task['entity_path'],
                    task['entity_type'],
                    task['resolution']
                )
                
                if task['callback']:
                    task['callback'](thumbnail_path)
                
                self.generation_queue.task_done()
                
            except Exception as e:
                print(f"Error in thumbnail worker: {e}")
```

### 5. Main UI Implementation

```python
# ui/main_window.py
from PySide6.QtWidgets import (QMainWindow, QHBoxLayout, QVBoxLayout, 
                               QWidget, QSplitter, QTabWidget, QMenuBar, 
                               QStatusBar, QToolBar)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence

from .directory_tree import DirectoryTreeWidget
from .content_view import ContentViewWidget
from .tab_manager import TabManager
from .search_widget import SearchWidget

class MainWindow(QMainWindow):
    """Main application window with Thunar-like interface."""
    
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self.config = app_controller.config_manager
        
        self.setWindowTitle("Stockshot Browser")
        self.setMinimumSize(1200, 800)
        
        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()
        
        # Restore window state
        self._restore_window_state()
    
    def _setup_ui(self):
        """Setup the main UI layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main horizontal layout
        main_layout = QHBoxLayout(central_widget)
        
        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel - Directory tree
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Search widget
        self.search_widget = SearchWidget(self.app_controller)
        left_layout.addWidget(self.search_widget)
        
        # Directory tree
        self.directory_tree = DirectoryTreeWidget(self.app_controller)
        left_layout.addWidget(self.directory_tree)
        
        splitter.addWidget(left_panel)
        
        # Right panel - Tabbed content view
        self.tab_manager = TabManager(self.app_controller)
        splitter.addWidget(self.tab_manager)
        
        # Set splitter proportions
        splitter.setSizes([300, 900])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
    
    def _setup_menus(self):
        """Setup application menus."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        new_tab_action = QAction("&New Tab", self)
        new_tab_action.setShortcut(QKeySequence.AddTab)
        new_tab_action.triggered.connect(self.tab_manager.new_tab)
        file_menu.addAction(new_tab_action)
        
        close_tab_action = QAction("&Close Tab", self)
        close_tab_action.setShortcut(QKeySequence.Close)
        close_tab_action.triggered.connect(self.tab_manager.close_current_tab)
        file_menu.addAction(close_tab_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        grid_view_action = QAction("&Grid View", self)
        grid_view_action.setCheckable(True)
        grid_view_action.triggered.connect(lambda: self._set_view_mode('grid'))
        view_menu.addAction(grid_view_action)
        
        list_view_action = QAction("&List View", self)
        list_view_action.setCheckable(True)
        list_view_action.triggered.connect(lambda: self._set_view_mode('list'))
        view_menu.addAction(list_view_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        generate_thumbs_action = QAction("Generate &Thumbnails", self)
        generate_thumbs_action.triggered.connect(self._generate_thumbnails)
        tools_menu.addAction(generate_thumbs_action)
        
        refresh_action = QAction("&Refresh", self)
        refresh_action.setShortcut(QKeySequence.Refresh)
        refresh_action.triggered.connect(self._refresh_current_view)
        tools_menu.addAction(refresh_action)
    
    def _connect_signals(self):
        """Connect UI signals."""
        # Directory tree selection changes content view
        self.directory_tree.directory_selected.connect(
            self.tab_manager.navigate_to_directory
        )
        
        # Search widget filters content
        self.search_widget.search_changed.connect(
            self.tab_manager.filter_content
        )
```

## Implementation Priority and Dependencies

### Phase 1: Foundation (Weeks 1-2)
1. Project structure setup
2. Configuration system implementation
3. Database schema and models
4. Basic entity detection

### Phase 2: Core Functionality (Weeks 3-4)
1. FFmpeg integration
2. Thumbnail generation system
3. Basic UI framework
4. File system scanning

### Phase 3: User Interface (Weeks 5-6)
1. Main window implementation
2. Directory tree widget
3. Content view widgets
4. Tabbed navigation

### Phase 4: Advanced Features (Weeks 7-8)
1. Search and filtering
2. Context menus and external players
3. Drag-and-drop functionality
4. Batch processing

### Phase 5: Polish and Testing (Weeks 9-10)
1. Color management integration
2. Performance optimization
3. Comprehensive testing
4. Cross-platform packaging

This technical specification provides the detailed implementation roadmap for building Stockshot Browser according to the architectural design.
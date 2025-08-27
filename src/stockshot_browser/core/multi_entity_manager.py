"""
Multi-context Entity Manager for Stockshot Browser.

Manages entities across different contexts (general, user, project) based on path.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Set
from PySide6.QtCore import QObject, Signal

from ..config.manager import ConfigurationManager
from ..database.multi_database_manager import MultiDatabaseManager
from ..core.path_context_manager import PathContextManager, ContextType
from ..utils.sequence_detector import SequenceDetector
from ..utils.file_utils import FileUtils


logger = logging.getLogger(__name__)


class EntityType(Enum):
    """Types of media entities."""
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
    file_size: Optional[int] = None  # Total size in bytes
    frame_count: Optional[int] = None  # Number of frames for sequences


class MultiEntityManager(QObject):
    """Context-aware entity manager that stores entities in appropriate databases."""
    
    # Signals
    entities_discovered = Signal(list)  # List of MediaEntity objects
    scan_progress = Signal(int, int)  # current, total
    
    def __init__(self, config_manager: ConfigurationManager, 
                 multi_database_manager: MultiDatabaseManager,
                 path_context_manager: PathContextManager):
        super().__init__()
        self.config_manager = config_manager
        self.multi_database_manager = multi_database_manager
        self.path_context_manager = path_context_manager
        
        # Initialize sequence detector
        self.sequence_detector = SequenceDetector(config_manager)
        
        # Get supported extensions from config
        self.video_extensions = set(self.config_manager.get('thumbnails.supported_formats', [
            '.mp4', '.mov', '.avi', '.mkv', '.m4v', '.wmv', '.flv', '.webm'
        ]))
        
        self.image_extensions = set(self.config_manager.get('sequence_detection.supported_extensions', [
            '.exr', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.dpx'
        ]))
        
        # Configuration options
        self.show_hidden_files = self.config_manager.get('ui.show_hidden_files', False)
        
        # Folder-based sequence detection settings
        self.folder_sequence_enabled = self.config_manager.get('sequence_detection.folder_sequence_detection.enabled', True)
        self.ignored_extensions = set(
            ext.lower() for ext in self.config_manager.get('sequence_detection.folder_sequence_detection.ignored_extensions', [
                '.tx', '.thumbs', '.thumb', '.tmp', '.bak', '.log', '.txt', '.nfo', '.db', '.DS_Store'
            ])
        )
        self.ignored_filenames = set(
            name.lower() for name in self.config_manager.get('sequence_detection.folder_sequence_detection.ignored_filenames', [
                'Thumbs.db', '.DS_Store', 'desktop.ini', '.directory'
            ])
        )
        
        # Current context for operations
        self._current_context: ContextType = ContextType.GENERAL
        self._current_path: Optional[str] = None
        
    
    def set_current_path(self, path: str) -> None:
        """Set the current path context for entity operations."""
        if path != self._current_path:
            self._current_path = path
            self._current_context = self.path_context_manager.get_context_for_path(path)
            logger.debug(f"Switched to {self._current_context.value} entity context for path: {path}")
    
    def scan_directory(self, directory_path: Path, recursive: bool = False) -> List[MediaEntity]:
        """Scan directory for media entities with context awareness."""
        # Set context based on directory being scanned
        self.set_current_path(str(directory_path))
        
        if recursive:
            return self.scan_directory_recursive(directory_path)
        else:
            return self._scan_single_directory(directory_path)
    
    def _is_folder_sequence(self, folder_path: Path) -> bool:
        """
        Check if a folder contains ONLY image sequence files and should be treated as a single sequence.
        """
        if not self.folder_sequence_enabled or not folder_path.is_dir():
            return False
        
        try:
            all_items = list(folder_path.iterdir())
            
            # Filter out hidden files if configured
            if not self.show_hidden_files:
                all_items = [item for item in all_items if not FileUtils.is_hidden_file(item)]
            
            # STRICT CHECK: No subdirectories allowed at all
            subdirs = [item for item in all_items if item.is_dir()]
            if subdirs:
                return False
            
            # Get all files
            all_files = [item for item in all_items if item.is_file()]
            
            if not all_files:
                return False
            
            # STRICT CATEGORIZATION: Separate all files into categories
            image_files = []
            video_files = []
            ignored_files = []
            other_files = []
            
            for file_path in all_files:
                file_ext = file_path.suffix.lower()
                file_name = file_path.name.lower()
                
                # First check if it's an ignored file
                if file_ext in self.ignored_extensions or file_name in self.ignored_filenames:
                    ignored_files.append(file_path)
                # Then check if it's an image file
                elif file_ext in self.image_extensions:
                    image_files.append(file_path)
                # Then check if it's a video file
                elif file_ext in self.video_extensions:
                    video_files.append(file_path)
                # Everything else is "other"
                else:
                    other_files.append(file_path)
            
            # STRICT RULE: If there are ANY video files, not a sequence folder
            if video_files:
                return False
            
            # STRICT RULE: If there are ANY other non-image, non-ignored files, not a sequence folder
            if other_files:
                return False
            
            # Must have at least 2 image files to be considered a sequence
            if len(image_files) < 2:
                return False
            
            return True
            
        except Exception as e:
            return False
    
    def _create_folder_sequence_entity(self, folder_path: Path) -> MediaEntity:
        """Create a sequence entity from a folder containing image sequences."""
        try:
            all_items = list(folder_path.iterdir())
            
            # Filter out hidden files if configured
            if not self.show_hidden_files:
                all_items = [item for item in all_items if not FileUtils.is_hidden_file(item)]
            
            # Get all files and filter
            all_files = [item for item in all_items if item.is_file()]
            
            # Filter out ignored files and get only image files
            image_files = []
            for file_path in all_files:
                # Skip ignored files
                if (file_path.suffix.lower() in self.ignored_extensions or
                    file_path.name.lower() in self.ignored_filenames):
                    continue
                # Only include image files
                if file_path.suffix.lower() in self.image_extensions:
                    image_files.append(file_path)
            
            if not image_files:
                raise ValueError(f"No valid image files found in folder {folder_path}")
            
            # Sort files for consistent ordering
            image_files.sort()
            
            # Calculate total size
            total_size = 0
            for file_path in image_files:
                try:
                    total_size += file_path.stat().st_size
                except OSError:
                    pass
            
            # Try to detect sequences within the folder to get frame range info
            frame_range = (1, len(image_files))  # Default frame range
            sequences = self.sequence_detector.detect_sequences(image_files)
            
            if sequences:
                # Use the first/largest sequence for frame range information
                primary_sequence = max(sequences, key=lambda s: len(s['files']))
                frame_range = primary_sequence.get('frame_range', (1, len(image_files)))
            
            return MediaEntity(
                path=folder_path,  # Use folder path as entity path
                entity_type=EntityType.VIDEO,  # Treat as video entity for UI consistency
                name=folder_path.name,  # Use folder name
                files=image_files,  # Use all image files sorted
                frame_range=frame_range,
                file_size=total_size if total_size > 0 else None,
                frame_count=len(image_files)
            )
                
        except Exception as e:
            # Fallback: create a basic entity
            return MediaEntity(
                path=folder_path,
                entity_type=EntityType.VIDEO,
                name=folder_path.name,
                files=[],
                frame_range=(1, 1),
                file_size=None,
                frame_count=0
            )
    
    def _scan_single_directory(self, directory_path: Path) -> List[MediaEntity]:
        """Scan a single directory for media entities with context awareness."""
        entities = []
        
        if not directory_path.exists() or not directory_path.is_dir():
            return entities
        
        try:
            # FIRST: Check if the current directory itself is a sequence folder
            if self.folder_sequence_enabled:
                is_sequence_folder = self._is_folder_sequence(directory_path)
                
                if is_sequence_folder:
                    folder_entity = self._create_folder_sequence_entity(directory_path)
                    return [folder_entity]
            
            # SECOND: Check for folder-based sequences in subdirectories
            if self.folder_sequence_enabled:
                subdirs = [item for item in directory_path.iterdir() if item.is_dir()]
                
                # Filter hidden directories if configured
                if not self.show_hidden_files:
                    subdirs = [d for d in subdirs if not FileUtils.is_hidden_file(d)]
                
                # Check each subdirectory to see if it's a sequence folder
                for subdir in subdirs:
                    if self._is_folder_sequence(subdir):
                        folder_entity = self._create_folder_sequence_entity(subdir)
                        entities.append(folder_entity)
            
            # THIRD: Process files in current directory
            all_files = [f for f in directory_path.iterdir() if f.is_file()]
            
            # Filter hidden files if configured
            if not self.show_hidden_files:
                all_files = [f for f in all_files if not FileUtils.is_hidden_file(f)]
            
            # Separate video files and image files
            video_files, image_files = FileUtils.filter_media_files(
                all_files, self.video_extensions, self.image_extensions
            )
            
            total_items = len(video_files) + len(image_files)
            processed = 0
            
            # Process video files
            for video_file in video_files:
                entity = self._create_video_entity(video_file)
                entities.append(entity)
                processed += 1
                self.scan_progress.emit(processed, total_items)
            
            # Process image sequences
            if image_files:
                # Check if there are any video files in the same directory
                if video_files:
                    # When video files are present, treat all images as individual entities
                    for image_file in image_files:
                        entity = self._create_individual_image_entity(image_file)
                        entities.append(entity)
                        processed += 1
                        self.scan_progress.emit(processed, total_items)
                else:
                    # No video files present - normal sequence detection
                    sequences = self.sequence_detector.detect_sequences(image_files)
                    
                    # Create entities for detected sequences
                    processed_files = set()
                    for sequence_info in sequences:
                        entity = self._create_sequence_entity(sequence_info)
                        entities.append(entity)
                        processed_files.update(sequence_info['files'])
                    
                    # Create individual entities for unmatched image files
                    unmatched_files = [f for f in image_files if f not in processed_files]
                    for image_file in unmatched_files:
                        entity = self._create_individual_image_entity(image_file)
                        entities.append(entity)
                        processed += 1
                        self.scan_progress.emit(processed, total_items)
            
        except Exception as e:
            logger.error(f"Error scanning directory {directory_path}: {e}")
        
        return entities
    
    def scan_directory_recursive(self, directory_path: Path) -> List[MediaEntity]:
        """Recursively scan directory and all subdirectories for media entities."""
        all_entities = []
        
        if not directory_path.exists() or not directory_path.is_dir():
            return all_entities
        
        try:
            # Collect all directories to scan (including root)
            directories_to_scan = [directory_path]
            processed_sequence_folders = set()  # Track folders already processed as sequences
            
            # Find all subdirectories, but skip those that are sequence folders
            for item in directory_path.rglob('*'):
                if item.is_dir() and (self.show_hidden_files or not FileUtils.is_hidden_file(item)):
                    # Check if this directory is a sequence folder
                    if self.folder_sequence_enabled and self._is_folder_sequence(item):
                        processed_sequence_folders.add(item)
                        logger.debug(f"Directory {item} identified as sequence folder, will be processed by parent")
                    else:
                        directories_to_scan.append(item)
            
            total_directories = len(directories_to_scan)
            
            # Scan each directory
            for i, dir_path in enumerate(directories_to_scan):
                try:
                    # Skip directories that are sequence folders - they will be processed by their parent
                    if dir_path in processed_sequence_folders:
                        continue
                    
                    # Update context for each directory
                    self.set_current_path(str(dir_path))
                    
                    # Scan this directory (non-recursive to avoid infinite recursion)
                    dir_entities = self._scan_single_directory(dir_path)
                    all_entities.extend(dir_entities)
                    
                    # Update progress
                    self.scan_progress.emit(i + 1, total_directories)
                    
                except Exception as e:
                    continue
                        
            # Emit signal with all entities
            self.entities_discovered.emit(all_entities)
            
        except Exception as e:
            logger.error(f"Error during recursive scan of {directory_path}: {e}")
        
        return all_entities
    
    def _create_video_entity(self, video_file: Path) -> MediaEntity:
        """Create a video entity."""
        try:
            file_size = video_file.stat().st_size
        except OSError:
            file_size = None
        
        return MediaEntity(
            path=video_file,
            entity_type=EntityType.VIDEO,
            name=video_file.stem,
            files=[video_file],
            file_size=file_size
        )
    
    def _create_sequence_entity(self, sequence_info: dict) -> MediaEntity:
        """Create a sequence entity from sequence detection info."""
        total_size = 0
        for file_path in sequence_info['files']:
            try:
                total_size += file_path.stat().st_size
            except OSError:
                pass
        
        # Create sequence as VIDEO entity to make it appear as single video entity in Content View
        return MediaEntity(
            path=sequence_info['base_path'],
            entity_type=EntityType.VIDEO,  # Changed from SEQUENCE to VIDEO
            name=sequence_info['name'],
            files=sequence_info['files'],
            frame_range=sequence_info['frame_range'],
            file_size=total_size if total_size > 0 else None,
            frame_count=sequence_info['frame_count']
        )
    
    def _create_individual_image_entity(self, image_file: Path) -> MediaEntity:
        """Create an entity for an individual image file."""
        try:
            file_size = image_file.stat().st_size
        except OSError:
            file_size = None
        
        # Create individual image as VIDEO entity to make it appear as single video entity in Content View
        return MediaEntity(
            path=image_file,
            entity_type=EntityType.VIDEO,  # Changed from SEQUENCE to VIDEO
            name=image_file.stem,
            files=[image_file],
            frame_range=(1, 1),
            file_size=file_size,
            frame_count=1
        )
    
    def get_entity_info(self, entity: MediaEntity) -> dict:
        """Get detailed information about an entity."""
        info = {
            'name': entity.name,
            'type': entity.entity_type.value,
            'path': str(entity.path),
            'file_count': len(entity.files),
        }
        
        if entity.file_size:
            info['size'] = FileUtils.format_bytes(entity.file_size)
            info['size_bytes'] = entity.file_size
        
        if entity.frame_range:
            info['frame_range'] = f"{entity.frame_range[0]}-{entity.frame_range[1]}"
            info['frame_count'] = entity.frame_count or len(entity.files)
        
        if entity.entity_type == EntityType.SEQUENCE and len(entity.files) > 1:
            info['sequence_info'] = {
                'first_frame': str(entity.files[0]),
                'last_frame': str(entity.files[-1]),
                'missing_frames': []  # Could be enhanced to track missing frames
            }
        
        return info
    
    def get_current_context(self) -> ContextType:
        """Get the current context."""
        return self._current_context
    
    def get_current_path(self) -> Optional[str]:
        """Get the current path."""
        return self._current_path
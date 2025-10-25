"""
Multi-context Metadata Manager for Stockshot Browser.

Manages metadata across different contexts (general, user, project) based on path.
"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThread, QThreadPool, QRunnable, Slot
import json

from ..config.manager import ConfigurationManager
from ..database.multi_database_manager import MultiDatabaseManager
from ..database.models import Entity, Metadata
from ..core.path_context_manager import PathContextManager, ContextType
from ..utils.ffmpeg_utils import FFmpegExtractor, FFmpegError


logger = logging.getLogger(__name__)


class ContextAwareMetadataWorker(QRunnable):
    """Worker for extracting metadata in background thread with context awareness."""
    
    def __init__(self, entity, ffmpeg_extractor, callback, multi_db_manager, entity_path=None):
        super().__init__()
        self.entity = entity
        self.ffmpeg_extractor = ffmpeg_extractor
        self.callback = callback
        self.multi_db_manager = multi_db_manager
        self.entity_path = entity_path  # Path to determine context
    
    @Slot()
    def run(self):
        """Extract metadata for the entity with context awareness."""
        try:
            if self.entity.entity_type.value == "video":
                metadata = self.ffmpeg_extractor.extract_video_info(self.entity.path)
            else:  # sequence or image
                # For sequences, analyze the first frame
                first_file = self.entity.files[0] if self.entity.files else self.entity.path
                metadata = self.ffmpeg_extractor.extract_image_info(first_file)
                
                # Add sequence-specific metadata
                if len(self.entity.files) > 1:
                    metadata['frame_count'] = len(self.entity.files)
                    metadata['is_sequence'] = True
                    if self.entity.frame_range:
                        metadata['frame_range'] = f"{self.entity.frame_range[0]}-{self.entity.frame_range[1]}"
            
            # Add entity-specific metadata
            metadata['entity_name'] = self.entity.name
            metadata['entity_type'] = self.entity.entity_type.value
            metadata['file_count'] = len(self.entity.files)
            metadata['entity_path'] = self.entity_path  # Include path for context
            
            if self.entity.file_size:
                metadata['total_size'] = self.entity.file_size
            
            self.callback(self.entity, metadata, None)
            
        except Exception as e:
            logger.error(f"Error extracting metadata for {self.entity.name}: {e}")
            self.callback(self.entity, None, str(e))


class MultiMetadataManager(QObject):
    """Context-aware metadata manager that stores metadata in appropriate databases."""
    
    # Signals
    metadata_extracted = Signal(object, dict)  # entity, metadata
    metadata_extraction_failed = Signal(object, str)  # entity, error
    extraction_progress = Signal(int, int)  # current, total
    
    def __init__(self, config_manager: ConfigurationManager, 
                 multi_database_manager: MultiDatabaseManager,
                 path_context_manager: PathContextManager):
        super().__init__()
        self.config_manager = config_manager
        self.multi_database_manager = multi_database_manager
        self.path_context_manager = path_context_manager
        
        # Initialize FFmpeg extractor
        try:
            self.ffmpeg_extractor = FFmpegExtractor(config_manager)
            self.ffmpeg_available = True
        except FFmpegError as e:
            logger.warning(f"FFmpeg not available: {e}")
            self.ffmpeg_extractor = None
            self.ffmpeg_available = False
        
        # Thread pool for background processing
        self.thread_pool = QThreadPool()
        max_threads = self.config_manager.get('performance.max_concurrent_thumbnails', 4)
        self.thread_pool.setMaxThreadCount(max_threads)
        
        # Processing state
        self.processing_entities = []
        self.completed_count = 0
        
        # Current context for batch operations
        self._current_context: ContextType = ContextType.GENERAL
        self._current_path: Optional[str] = None
        
        logger.info(f"MultiMetadataManager initialized (FFmpeg available: {self.ffmpeg_available})")
    
    def set_current_path(self, path: str) -> None:
        """Set the current path context for metadata operations."""
        if path != self._current_path:
            self._current_path = path
            self._current_context = self.path_context_manager.get_context_for_path(path)
            logger.debug(f"Switched to {self._current_context.value} metadata context for path: {path}")
    
    def process_new_entities(self, entities: List, entity_path: Optional[str] = None) -> None:
        """Process newly discovered entities for metadata extraction with context awareness."""
        if not entities:
            return
        
        logger.info(f"Processing {len(entities)} entities for metadata extraction")
        
        if not self.ffmpeg_available:
            logger.warning("FFmpeg not available, skipping metadata extraction")
            return
        
        # Use provided path or current path to determine context
        target_path = entity_path or self._current_path or str(entities[0].path)
        context = self.path_context_manager.get_context_for_path(target_path)
        
        logger.info(f"Processing entities in {context.value} metadata context")
        
        # Filter entities that need metadata extraction
        entities_to_process = []
        for entity in entities:
            if self.config_manager.get('metadata.auto_extract', True):
                entities_to_process.append(entity)
        
        if not entities_to_process:
            return
        
        # Reset processing state
        self.processing_entities = entities_to_process
        self.completed_count = 0
        
        # Start extraction for each entity
        for entity in entities_to_process:
            worker = ContextAwareMetadataWorker(
                entity,
                self.ffmpeg_extractor,
                self._on_metadata_extracted,
                self.multi_database_manager,
                entity_path=target_path
            )
            self.thread_pool.start(worker)
    
    def _on_metadata_extracted(self, entity, metadata: Optional[Dict], error: Optional[str]):
        """Handle metadata extraction completion with context awareness."""
        self.completed_count += 1
        
        if error:
            logger.error(f"Metadata extraction failed for {entity.name}: {error}")
            self.metadata_extraction_failed.emit(entity, error)
        elif metadata:
            logger.debug(f"Metadata extracted for {entity.name}")
            
            # Extract entity path for context determination
            entity_path = metadata.get('entity_path') if isinstance(metadata, dict) else None
            
            # Store metadata in the appropriate database
            self._store_metadata(entity, metadata, entity_path)
            
            # Emit signal
            self.metadata_extracted.emit(entity, metadata)
        
        # Emit progress
        self.extraction_progress.emit(self.completed_count, len(self.processing_entities))
    
    def _store_metadata(self, entity, metadata: Dict[str, Any], entity_path: Optional[str] = None) -> None:
        """Store metadata in the appropriate database based on context."""
        try:
            # Determine which database to use
            if entity_path:
                with self.multi_database_manager.get_session_for_path(entity_path) as session:
                    self._store_in_session(session, entity, metadata)
            else:
                # Use current context
                with self.multi_database_manager.get_session() as session:
                    self._store_in_session(session, entity, metadata)
        except Exception as e:
            logger.error(f"Error storing metadata for {entity.name}: {e}")
    
    def _store_in_session(self, session, entity, metadata: Dict[str, Any]) -> None:
        """Store metadata in the provided database session."""
        # First, ensure entity exists in database
        db_entity = session.query(Entity).filter_by(
            path=str(entity.path),
            entity_type=entity.entity_type.value
        ).first()
        
        if not db_entity:
            # Create entity in database with proper type conversion
            db_entity = Entity(
                path=str(entity.path),
                entity_type=entity.entity_type.value,
                name=str(entity.name),
                file_size=int(entity.file_size) if entity.file_size else None,
                file_count=int(len(entity.files)) if hasattr(entity, 'files') and entity.files else 1,
                metadata_extracted=True,
                thumbnail_generated=False
            )
            session.add(db_entity)
            session.flush()  # Get the ID
        
        # Check if metadata already exists
        existing_metadata = session.query(Metadata).filter_by(
            entity_id=db_entity.id
        ).first()
        
        if existing_metadata:
            # Update existing metadata
            self._update_metadata_record(existing_metadata, metadata)
        else:
            # Create new metadata record
            metadata_record = self._create_metadata_record(db_entity.id, metadata)
            session.add(metadata_record)
        
        # Mark entity as having metadata extracted
        db_entity.metadata_extracted = True
        
        logger.debug(f"Successfully stored metadata for entity: {entity.name}")
    
    def _create_metadata_record(self, entity_id: int, metadata: Dict[str, Any]) -> Metadata:
        """Create a new metadata record."""
        # Helper function to safely convert values
        def safe_convert(value, target_type):
            if value is None:
                return None
            try:
                if target_type == float:
                    return float(value)
                elif target_type == int:
                    return int(value)
                elif target_type == bool:
                    return bool(value)
                elif target_type == str:
                    return str(value)
                else:
                    return value
            except (ValueError, TypeError):
                return None
        
        # Separate standard fields from custom fields with proper type conversion
        standard_fields = {
            'duration': safe_convert(metadata.get('duration'), float),
            'fps': safe_convert(metadata.get('fps'), float),
            'width': safe_convert(metadata.get('width'), int),
            'height': safe_convert(metadata.get('height'), int),
            'aspect_ratio': safe_convert(metadata.get('aspect_ratio'), float),
            'format': safe_convert(metadata.get('format'), str),
            'codec': safe_convert(metadata.get('codec'), str),
            'audio_codec': safe_convert(metadata.get('audio_codec'), str),
            'colorspace': safe_convert(metadata.get('colorspace'), str),
            'bit_depth': safe_convert(metadata.get('bit_depth'), int),
            'bitrate': safe_convert(metadata.get('bitrate'), int),
            'frame_count': safe_convert(metadata.get('frame_count'), int),
            'has_audio': safe_convert(metadata.get('has_audio', False), bool),
        }
        
        # Remove None values
        standard_fields = {k: v for k, v in standard_fields.items() if v is not None}
        
        # Custom fields (everything else) - exclude context-specific fields
        excluded_fields = ['duration', 'fps', 'width', 'height', 'aspect_ratio',
                          'format', 'codec', 'audio_codec', 'colorspace', 'bit_depth',
                          'bitrate', 'frame_count', 'has_audio', 'entity_path']
        
        custom_fields = {k: v for k, v in metadata.items()
                        if k not in excluded_fields and v is not None}
        
        metadata_record = Metadata(
            entity_id=int(entity_id),
            custom_fields=json.dumps(custom_fields) if custom_fields else None,
            **standard_fields
        )
        
        return metadata_record
    
    def _update_metadata_record(self, metadata_record: Metadata, metadata: Dict[str, Any]) -> None:
        """Update an existing metadata record."""
        # Update standard fields
        standard_fields = [
            'duration', 'fps', 'width', 'height', 'aspect_ratio', 'format',
            'codec', 'audio_codec', 'colorspace', 'bit_depth', 'bitrate',
            'frame_count', 'has_audio'
        ]
        
        for field in standard_fields:
            if field in metadata and metadata[field] is not None:
                setattr(metadata_record, field, metadata[field])
        
        # Update custom fields
        existing_custom = metadata_record.get_custom_fields()
        excluded_fields = standard_fields + ['entity_path']
        custom_fields = {k: v for k, v in metadata.items()
                        if k not in excluded_fields and v is not None}
        
        existing_custom.update(custom_fields)
        metadata_record.set_custom_fields(existing_custom)
    
    def get_entity_metadata(self, entity_path: str, context_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get metadata for an entity from the appropriate database."""
        try:
            # Determine which database to use
            if context_path:
                with self.multi_database_manager.get_session_for_path(context_path) as session:
                    return self._get_metadata_from_session(session, entity_path)
            else:
                with self.multi_database_manager.get_session() as session:
                    return self._get_metadata_from_session(session, entity_path)
        except Exception as e:
            logger.error(f"Error getting metadata for {entity_path}: {e}")
            return None
    
    def _get_metadata_from_session(self, session, entity_path: str) -> Optional[Dict[str, Any]]:
        """Get metadata from database session."""
        entity = session.query(Entity).filter_by(path=entity_path).first()
        if not entity or not entity.entity_metadata:
            return None
        
        metadata_dict = {
            'duration': entity.entity_metadata.duration,
            'fps': entity.entity_metadata.fps,
            'width': entity.entity_metadata.width,
            'height': entity.entity_metadata.height,
            'aspect_ratio': entity.entity_metadata.aspect_ratio,
            'format': entity.entity_metadata.format,
            'codec': entity.entity_metadata.codec,
            'audio_codec': entity.entity_metadata.audio_codec,
            'colorspace': entity.entity_metadata.colorspace,
            'bit_depth': entity.entity_metadata.bit_depth,
            'bitrate': entity.entity_metadata.bitrate,
            'frame_count': entity.entity_metadata.frame_count,
            'has_audio': entity.entity_metadata.has_audio,
        }
        
        # Add custom fields
        custom_fields = entity.entity_metadata.get_custom_fields()
        metadata_dict.update(custom_fields)
        
        # Remove None values
        return {k: v for k, v in metadata_dict.items() if v is not None}
    
    def search_by_metadata(self, filters: Dict[str, Any], context_path: Optional[str] = None) -> List[str]:
        """Search entities by metadata criteria in the appropriate database."""
        try:
            # Determine which database to use
            if context_path:
                with self.multi_database_manager.get_session_for_path(context_path) as session:
                    return self._search_in_session(session, filters)
            else:
                with self.multi_database_manager.get_session() as session:
                    return self._search_in_session(session, filters)
        except Exception as e:
            logger.error(f"Error searching by metadata: {e}")
            return []
    
    def _search_in_session(self, session, filters: Dict[str, Any]) -> List[str]:
        """Search by metadata in database session."""
        query = session.query(Entity).join(Metadata)
        
        # Apply filters
        for key, value in filters.items():
            if key == 'duration_min':
                query = query.filter(Metadata.duration >= value)
            elif key == 'duration_max':
                query = query.filter(Metadata.duration <= value)
            elif key == 'width_min':
                query = query.filter(Metadata.width >= value)
            elif key == 'width_max':
                query = query.filter(Metadata.width <= value)
            elif key == 'height_min':
                query = query.filter(Metadata.height >= value)
            elif key == 'height_max':
                query = query.filter(Metadata.height <= value)
            elif key == 'format':
                query = query.filter(Metadata.format == value)
            elif key == 'codec':
                query = query.filter(Metadata.codec == value)
            elif key == 'colorspace':
                query = query.filter(Metadata.colorspace == value)
            elif key == 'has_audio':
                query = query.filter(Metadata.has_audio == value)
        
        results = query.all()
        return [entity.path for entity in results]
    
    def get_metadata_summary(self, context: Optional[ContextType] = None) -> Dict[str, Any]:
        """Get summary statistics of metadata in appropriate database."""
        try:
            if context:
                # Get summary for specific context
                with self.multi_database_manager.get_session_for_context(context) as session:
                    return self._get_summary_from_session(session)
            else:
                # Get summary for current context
                with self.multi_database_manager.get_session() as session:
                    return self._get_summary_from_session(session)
        except Exception as e:
            logger.error(f"Error getting metadata summary: {e}")
            return {}
    
    def _get_summary_from_session(self, session) -> Dict[str, Any]:
        """Get metadata summary from database session."""
        total_entities = session.query(Entity).count()
        entities_with_metadata = session.query(Entity).filter(
            Entity.metadata_extracted == True
        ).count()
        
        # Get format distribution
        format_query = session.query(Metadata.format,
                                   session.query(Metadata).filter(
                                       Metadata.format == Metadata.format
                                   ).count().label('count')
                                  ).group_by(Metadata.format).all()
        
        format_distribution = {fmt: count for fmt, count in format_query}
        
        return {
            'total_entities': total_entities,
            'entities_with_metadata': entities_with_metadata,
            'extraction_percentage': round((entities_with_metadata / total_entities) * 100, 1) if total_entities > 0 else 0,
            'format_distribution': format_distribution
        }
    
    def get_current_context(self) -> ContextType:
        """Get the current context."""
        return self._current_context
    
    def get_current_path(self) -> Optional[str]:
        """Get the current path."""
        return self._current_path
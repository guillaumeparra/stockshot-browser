"""
Multi-context Thumbnail Manager for Stockshot Browser.

Manages thumbnails across different contexts (general, user, project) based on path.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from PySide6.QtCore import QObject, Signal, QThreadPool, QRunnable, Slot

from ..config.manager import ConfigurationManager
from ..database.multi_database_manager import MultiDatabaseManager
from ..database.models import Entity, Thumbnail
from ..utils.ffmpeg_utils import FFmpegThumbnailGenerator, FFmpegError
from ..utils.file_utils import FileUtils
from ..core.path_context_manager import PathContextManager, ContextType


logger = logging.getLogger(__name__)


class ContextAwareThumbnailWorker(QRunnable):
    """Worker for generating thumbnails in background thread with context awareness."""
    
    def __init__(self, entity, thumbnail_generator, output_path, resolution, callback,
                 animated=False, config_manager=None, color_manager=None, 
                 multi_db_manager=None, entity_path=None):
        super().__init__()
        self.entity = entity
        self.thumbnail_generator = thumbnail_generator
        self.output_path = output_path
        self.resolution = resolution
        self.callback = callback
        self.animated = animated
        self.config_manager = config_manager
        self.color_manager = color_manager
        self.multi_db_manager = multi_db_manager
        self.entity_path = entity_path  # Path to determine context
    
    @Slot()
    def run(self):
        """Generate thumbnail for the entity with context awareness."""
        start_time = time.time()
        
        try:
            success = False
            source_frame = None
            animated_path = None
            
            # Determine entity characteristics
            is_single_image = (len(self.entity.files) == 1 and self.entity.frame_count == 1)
            is_sequence = len(self.entity.files) > 1
            is_actual_video = (len(self.entity.files) == 1 and self.entity.frame_count != 1)
            
            
            if is_actual_video:
                # Process video file
                if self.animated and self.config_manager:
                    animated_enabled = self.config_manager.get('thumbnails.animated.enabled', True)
                    if animated_enabled:
                        # Generate animated thumbnail
                        animated_path = self.output_path.with_suffix('.gif')
                        frame_count = self.config_manager.get('thumbnails.animated.frame_count', 25)
                        fps = self.config_manager.get('thumbnails.animated.fps', 10)
                        
                        success = self.thumbnail_generator.generate_animated_thumbnail(
                            self.entity.path,
                            animated_path,
                            frame_count,
                            fps,
                            self.resolution
                        )
                        
                        if success:
                            # Generate static thumbnail as fallback
                            duration = self.thumbnail_generator.get_video_duration(self.entity.path)
                            source_frame = (duration * 0.1) if duration else 1.0
                            self.thumbnail_generator.extract_frame(
                                self.entity.path,
                                self.output_path,
                                source_frame,
                                self.resolution
                            )
                
                # Generate static thumbnail if animated failed or not enabled
                if not success:
                    duration = self.thumbnail_generator.get_video_duration(self.entity.path)
                    source_frame = (duration * 0.1) if duration else 1.0
                    success = self.thumbnail_generator.extract_frame(
                        self.entity.path,
                        self.output_path,
                        source_frame,
                        self.resolution
                    )
            else:
                # Process image or sequence
                if is_sequence:
                    # Generate animated thumbnail for sequence if enabled
                    if self.animated and self.config_manager:
                        animated_enabled = self.config_manager.get('thumbnails.animated.enabled', True)
                        if animated_enabled:
                            animated_path = self.output_path.with_suffix('.gif')
                            frame_count = self.config_manager.get('thumbnails.animated.frame_count', 25)
                            fps = self.config_manager.get('thumbnails.animated.fps', 10)
                            
                            success = self.thumbnail_generator.generate_animated_thumbnail_from_sequence(
                                self.entity.files,
                                animated_path,
                                frame_count,
                                fps,
                                self.resolution
                            )
                    
                    # Generate static thumbnail from middle frame
                    middle_index = len(self.entity.files) // 2
                    source_file = self.entity.files[middle_index]
                    static_success = self.thumbnail_generator.extract_image_thumbnail(
                        source_file,
                        self.output_path,
                        self.resolution
                    )
                    
                    if not success:
                        success = static_success
                else:
                    # Single image
                    source_file = self.entity.files[0] if self.entity.files else self.entity.path
                    success = self.thumbnail_generator.extract_image_thumbnail(
                        source_file,
                        self.output_path,
                        self.resolution
                    )
            
            generation_time = time.time() - start_time
            
            if success:
                # Get file size
                try:
                    file_size = self.output_path.stat().st_size
                except OSError:
                    file_size = None
                
                # Prepare thumbnail info
                thumbnail_info = {
                    'static_path': str(self.output_path),
                    'animated_path': str(animated_path) if animated_path and animated_path.exists() else None,
                    'entity_path': self.entity_path  # Include path for context
                }
                
                self.callback(self.entity, thumbnail_info, generation_time,
                            source_frame, file_size, None)
            else:
                self.callback(self.entity, None, generation_time, source_frame,
                            None, "Thumbnail generation failed")
                
        except Exception as e:
            generation_time = time.time() - start_time
            logger.error(f"🔍 ContextWorker: Exception in thumbnail generation for {self.entity.name}: {e}")
            self.callback(self.entity, None, generation_time, None, None, str(e))


class MultiThumbnailManager(QObject):
    """Context-aware thumbnail manager that uses different directories and databases based on path context."""
    
    # Signals
    thumbnail_generated = Signal(object, str)  # entity, thumbnail_path
    thumbnail_generation_failed = Signal(object, str)  # entity, error
    generation_progress = Signal(int, int)  # current, total
    
    def __init__(self, config_manager: ConfigurationManager, multi_database_manager: MultiDatabaseManager, 
                 path_context_manager: PathContextManager, color_manager=None):
        super().__init__()
        self.config_manager = config_manager
        self.multi_database_manager = multi_database_manager
        self.path_context_manager = path_context_manager
        self.color_manager = color_manager
        
        # Initialize FFmpeg thumbnail generator
        try:
            self.thumbnail_generator = FFmpegThumbnailGenerator(config_manager)
            self.ffmpeg_available = True
        except FFmpegError as e:
            logger.warning(f"FFmpeg not available for thumbnails: {e}")
            self.thumbnail_generator = None
            self.ffmpeg_available = False
        
        # Configuration
        self.default_resolution = self.config_manager.get('thumbnails.default_resolution', 128)
        self.max_cache_size_mb = self.config_manager.get('thumbnails.max_cache_size_mb', 1024)
        
        # Cache directories by context
        self._cache_directories = {}
        self._initialize_cache_directories()
        
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
        
        logger.info(f"MultiThumbnailManager initialized (FFmpeg available: {self.ffmpeg_available})")
    
    def _initialize_cache_directories(self):
        """Initialize cache directories for all contexts."""
        contexts = [ContextType.GENERAL, ContextType.USER, ContextType.PROJECT]
        
        for context in contexts:
            cache_dir = self.path_context_manager.get_thumbnail_path(context)
            if cache_dir:
                cache_path = Path(cache_dir)
                FileUtils.ensure_directory(cache_path)
                self._cache_directories[context] = cache_path
                logger.debug(f"Initialized {context.value} thumbnail cache: {cache_path}")
    
    def set_current_path(self, path: str) -> None:
        """Set the current path context for thumbnail operations."""
        if path != self._current_path:
            self._current_path = path
            self._current_context = self.path_context_manager.get_context_for_path(path)
            logger.debug(f"Switched to {self._current_context.value} thumbnail context for path: {path}")
    
    def get_cache_directory_for_context(self, context: ContextType) -> Path:
        """Get cache directory for the specified context."""
        if context in self._cache_directories:
            return self._cache_directories[context]
        
        # Fallback to general cache
        return self._cache_directories.get(ContextType.GENERAL, Path('.thumbnails'))
    
    def get_cache_directory_for_path(self, path: str) -> Path:
        """Get cache directory for the specified path."""
        context = self.path_context_manager.get_context_for_path(path)
        return self.get_cache_directory_for_context(context)
    
    def queue_thumbnail_generation(self, entities: List, entity_path: Optional[str] = None) -> None:
        """Queue thumbnail generation for entities with context awareness."""
        if not entities:
            return
        
        
        if not self.ffmpeg_available:
            logger.warning("🔍 MultiThumbnailManager: FFmpeg not available, skipping thumbnail generation")
            return
        
        # Use provided path or current path to determine context
        target_path = entity_path or self._current_path or str(entities[0].path)
        context = self.path_context_manager.get_context_for_path(target_path)
        
        # Filter entities that need thumbnails
        entities_to_process = []
        for entity in entities:
            if self._needs_thumbnail(entity, context):
                entities_to_process.append(entity)
        
        if not entities_to_process:
            return
        
        
        # Reset processing state
        self.processing_entities = entities_to_process
        self.completed_count = 0
        
        # Start generation for each entity
        for entity in entities_to_process:
            thumbnail_path = self._get_thumbnail_path_for_context(entity, context)
            
            # Check for animated thumbnail requirements
            is_video = entity.entity_type.value == "video"
            is_sequence = len(entity.files) > 1
            animated_enabled = self.config_manager.get('thumbnails.animated.enabled', True)
            enable_animated = (is_video or is_sequence) and animated_enabled
            
            worker = ContextAwareThumbnailWorker(
                entity,
                self.thumbnail_generator,
                thumbnail_path,
                self.default_resolution,
                self._on_thumbnail_generated,
                animated=enable_animated,
                config_manager=self.config_manager,
                color_manager=self.color_manager,
                multi_db_manager=self.multi_database_manager,
                entity_path=target_path
            )
            self.thread_pool.start(worker)
    
    def _needs_thumbnail(self, entity, context: ContextType) -> bool:
        """Check if entity needs thumbnail generation in the specified context."""
        thumbnail_path = self._get_thumbnail_path_for_context(entity, context)
        
        # Check if thumbnail already exists and is newer than source
        if thumbnail_path.exists():
            try:
                thumb_mtime = thumbnail_path.stat().st_mtime
                
                # For sequences, check the newest file
                if len(entity.files) > 1:
                    newest_file_mtime = max(f.stat().st_mtime for f in entity.files)
                else:
                    newest_file_mtime = entity.path.stat().st_mtime
                
                if thumb_mtime > newest_file_mtime:
                    return False  # Thumbnail is up to date
                    
            except OSError:
                pass  # If we can't check, assume we need to regenerate
        
        return True
    
    def _get_thumbnail_path_for_context(self, entity, context: ContextType) -> Path:
        """Get the thumbnail path for entity in the specified context."""
        cache_directory = self.get_cache_directory_for_context(context)
        
        # Create unique identifier for entity
        if entity.entity_type.value == "video":
            identifier = f"{entity.path.stem}_{entity.path.stat().st_mtime}"
        else:
            # For sequences, use name and file count
            identifier = f"{entity.name}_{len(entity.files)}"
            if entity.files:
                try:
                    identifier += f"_{entity.files[0].stat().st_mtime}"
                except OSError:
                    pass
        
        # Make identifier safe for filename
        safe_identifier = FileUtils.safe_filename(identifier)
        thumbnail_name = f"{safe_identifier}_{self.default_resolution}.jpg"
        
        return cache_directory / thumbnail_name
    
    def _on_thumbnail_generated(self, entity, thumbnail_info, generation_time: float, 
                               source_frame: Optional[float], file_size: Optional[int], 
                               error: Optional[str]):
        """Handle thumbnail generation completion with context awareness."""
        self.completed_count += 1
        
        if error:
            logger.error(f"Thumbnail generation failed for {entity.name}: {error}")
            self.thumbnail_generation_failed.emit(entity, error)
        elif thumbnail_info:
            # Extract entity path for context determination
            entity_path = thumbnail_info.get('entity_path') if isinstance(thumbnail_info, dict) else None
            
            if isinstance(thumbnail_info, dict):
                static_path = thumbnail_info.get('static_path')
                animated_path = thumbnail_info.get('animated_path')
                
                logger.debug(f"Thumbnail generated for {entity.name}: static={static_path}, animated={animated_path}")
                
                # Store thumbnail info in the appropriate database
                self._store_thumbnail_info(entity, static_path, generation_time,
                                         source_frame, file_size, animated_path, entity_path)
                
                # Emit signal with static path
                self.thumbnail_generated.emit(entity, static_path)
            else:
                # Legacy single path
                self._store_thumbnail_info(entity, thumbnail_info, generation_time,
                                         source_frame, file_size, None, entity_path)
                self.thumbnail_generated.emit(entity, thumbnail_info)
        
        # Emit progress
        self.generation_progress.emit(self.completed_count, len(self.processing_entities))
        
        # Check cache size periodically
        if self.completed_count % 10 == 0:
            self._check_cache_sizes()
    
    def _store_thumbnail_info(self, entity, thumbnail_path: str, generation_time: float,
                             source_frame: Optional[float], file_size: Optional[int],
                             animated_path: Optional[str] = None, entity_path: Optional[str] = None):
        """Store thumbnail information in the appropriate database."""
        try:
            # Determine which database to use
            if entity_path:
                with self.multi_database_manager.get_session_for_path(entity_path) as session:
                    self._store_in_session(session, entity, thumbnail_path, generation_time,
                                         source_frame, file_size, animated_path)
            else:
                # Use current context
                with self.multi_database_manager.get_session() as session:
                    self._store_in_session(session, entity, thumbnail_path, generation_time,
                                         source_frame, file_size, animated_path)
        except Exception as e:
            logger.error(f"Error storing thumbnail info for {entity.name}: {e}")
    
    def _store_in_session(self, session, entity, thumbnail_path: str, generation_time: float,
                         source_frame: Optional[float], file_size: Optional[int],
                         animated_path: Optional[str] = None):
        """Store thumbnail info in the provided database session."""
        # Find or create entity in database
        db_entity = session.query(Entity).filter_by(
            path=str(entity.path),
            entity_type=entity.entity_type.value
        ).first()
        
        if not db_entity:
            # Create entity in database
            db_entity = Entity(
                path=str(entity.path),
                entity_type=entity.entity_type.value,
                name=str(entity.name),
                file_size=int(entity.file_size) if entity.file_size else None,
                file_count=int(len(entity.files)),
                thumbnail_generated=True,
                metadata_extracted=False
            )
            session.add(db_entity)
            session.flush()
        
        # Check if thumbnail record already exists
        existing_thumbnail = session.query(Thumbnail).filter_by(
            entity_id=db_entity.id,
            resolution=self.default_resolution
        ).first()
        
        if existing_thumbnail:
            # Update existing record
            existing_thumbnail.path = str(thumbnail_path)
            existing_thumbnail.generation_time = float(generation_time) if generation_time else None
            existing_thumbnail.source_frame = float(source_frame) if source_frame else None
            existing_thumbnail.file_size = int(file_size) if file_size else None
            existing_thumbnail.is_valid = True
            if animated_path:
                existing_thumbnail.extra_data = {'animated_path': str(animated_path)}
        else:
            # Create new thumbnail record
            thumbnail_record = Thumbnail(
                entity_id=int(db_entity.id),
                path=str(thumbnail_path),
                resolution=int(self.default_resolution),
                generation_time=float(generation_time) if generation_time else None,
                source_frame=float(source_frame) if source_frame else None,
                file_size=int(file_size) if file_size else None,
                is_valid=True
            )
            if animated_path:
                thumbnail_record.extra_data = {'animated_path': str(animated_path)}
            session.add(thumbnail_record)
        
        # Mark entity as having thumbnail
        db_entity.thumbnail_generated = True
    
    def get_thumbnail_path(self, entity, entity_path: Optional[str] = None) -> Optional[str]:
        """Get thumbnail path for entity, considering context."""
        # Determine context
        if entity_path:
            context = self.path_context_manager.get_context_for_path(entity_path)
        else:
            context = self._current_context
        
        thumbnail_path = self._get_thumbnail_path_for_context(entity, context)
        
        if thumbnail_path.exists():
            return str(thumbnail_path)
        
        return None
    
    def get_animated_thumbnail_path(self, entity, entity_path: Optional[str] = None) -> Optional[str]:
        """Get animated thumbnail path for entity, considering context."""
        # Support both videos and sequences
        is_video = entity.entity_type.value == "video"
        is_sequence = len(entity.files) > 1
        
        if not (is_video or is_sequence):
            return None
        
        # Determine context
        if entity_path:
            context = self.path_context_manager.get_context_for_path(entity_path)
        else:
            context = self._current_context
        
        # Check for GIF version
        thumbnail_path = self._get_thumbnail_path_for_context(entity, context)
        animated_path = thumbnail_path.with_suffix('.gif')
        
        if animated_path.exists():
            return str(animated_path)
        
        # Check database for stored animated path
        try:
            if entity_path:
                with self.multi_database_manager.get_session_for_path(entity_path) as session:
                    return self._get_animated_path_from_session(session, entity)
            else:
                with self.multi_database_manager.get_session() as session:
                    return self._get_animated_path_from_session(session, entity)
        except Exception as e:
            logger.error(f"Error getting animated thumbnail path: {e}")
        
        return None
    
    def _get_animated_path_from_session(self, session, entity) -> Optional[str]:
        """Get animated thumbnail path from database session."""
        db_entity = session.query(Entity).filter_by(
            path=str(entity.path),
            entity_type=entity.entity_type.value
        ).first()
        
        if db_entity:
            thumbnail = session.query(Thumbnail).filter_by(
                entity_id=db_entity.id,
                resolution=self.default_resolution
            ).first()
            
            if thumbnail and hasattr(thumbnail, 'extra_data') and thumbnail.extra_data:
                animated_path = thumbnail.extra_data.get('animated_path')
                if animated_path and Path(animated_path).exists():
                    return animated_path
        
        return None
    
    def _check_cache_sizes(self):
        """Check and manage cache sizes for all contexts."""
        for context, cache_dir in self._cache_directories.items():
            try:
                cache_size_bytes = FileUtils.get_directory_size(cache_dir)
                cache_size_mb = cache_size_bytes / (1024 * 1024)
                
                if cache_size_mb > self.max_cache_size_mb:
                    logger.info(f"{context.value} cache size ({cache_size_mb:.1f} MB) exceeds limit")
                    self._cleanup_old_thumbnails_in_context(context)
                    
            except Exception as e:
                logger.error(f"Error checking {context.value} cache size: {e}")
    
    def _cleanup_old_thumbnails_in_context(self, context: ContextType):
        """Remove old thumbnails from specific context cache."""
        try:
            cache_dir = self._cache_directories[context]
            thumbnail_files = list(cache_dir.glob("*.jpg"))
            thumbnail_files.sort(key=lambda f: f.stat().st_mtime)
            
            # Remove oldest 25% of files
            files_to_remove = len(thumbnail_files) // 4
            
            for thumbnail_file in thumbnail_files[:files_to_remove]:
                try:
                    thumbnail_file.unlink()
                    logger.debug(f"Removed old {context.value} thumbnail: {thumbnail_file}")
                except OSError as e:
                    logger.warning(f"Could not remove thumbnail {thumbnail_file}: {e}")
            
            logger.info(f"Cleaned up {files_to_remove} old thumbnails in {context.value} context")
            
        except Exception as e:
            logger.error(f"Error cleaning up {context.value} thumbnails: {e}")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about thumbnail caches for all contexts."""
        cache_info = {}
        
        for context, cache_dir in self._cache_directories.items():
            try:
                cache_size_bytes = FileUtils.get_directory_size(cache_dir)
                thumbnail_count = len(list(cache_dir.glob("*.jpg")))
                
                cache_info[context.value] = {
                    'cache_directory': str(cache_dir),
                    'cache_size_bytes': cache_size_bytes,
                    'cache_size_formatted': FileUtils.format_bytes(cache_size_bytes),
                    'thumbnail_count': thumbnail_count,
                }
            except Exception as e:
                logger.error(f"Error getting {context.value} cache info: {e}")
                cache_info[context.value] = {'error': str(e)}
        
        cache_info['config'] = {
            'max_cache_size_mb': self.max_cache_size_mb,
            'default_resolution': self.default_resolution,
        }
        
        return cache_info
    
    def clear_cache(self, context: Optional[ContextType] = None) -> Dict[str, bool]:
        """Clear thumbnails from cache for specific or all contexts."""
        results = {}
        
        contexts_to_clear = [context] if context else list(self._cache_directories.keys())
        
        for ctx in contexts_to_clear:
            if ctx in self._cache_directories:
                try:
                    cache_dir = self._cache_directories[ctx]
                    thumbnail_files = list(cache_dir.glob("*.jpg"))
                    
                    for thumbnail_file in thumbnail_files:
                        try:
                            thumbnail_file.unlink()
                        except OSError as e:
                            logger.warning(f"Could not remove thumbnail {thumbnail_file}: {e}")
                    
                    logger.info(f"Cleared {len(thumbnail_files)} thumbnails from {ctx.value} cache")
                    results[ctx.value] = True
                    
                except Exception as e:
                    logger.error(f"Error clearing {ctx.value} cache: {e}")
                    results[ctx.value] = False
        
        return results
    
    def shutdown(self) -> None:
        """Shutdown thumbnail manager."""
        logger.info("MultiThumbnailManager shutting down")
        
        # Wait for all workers to complete (with timeout)
        if not self.thread_pool.waitForDone(5000):  # 5 second timeout
            logger.warning("Some thumbnail generation workers did not complete in time")
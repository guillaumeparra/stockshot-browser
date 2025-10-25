"""
Thumbnail management for Stockshot Browser.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional, Dict
from PySide6.QtCore import QObject, Signal, QThreadPool, QRunnable, Slot

from ..config.manager import ConfigurationManager
from ..database.connection import DatabaseManager, database_retry
from ..database.models import Entity, Thumbnail
from ..utils.ffmpeg_utils import FFmpegThumbnailGenerator, FFmpegError
from ..utils.file_utils import FileUtils


logger = logging.getLogger(__name__)


class ThumbnailGenerationWorker(QRunnable):
    """Worker for generating thumbnails in background thread."""
    
    def __init__(self, entity, thumbnail_generator, output_path, resolution, callback,
                 animated=False, config_manager=None, color_manager=None):
        super().__init__()
        self.entity = entity
        self.thumbnail_generator = thumbnail_generator
        self.output_path = output_path
        self.resolution = resolution
        self.callback = callback
        self.animated = animated
        self.config_manager = config_manager
        self.color_manager = color_manager
    
    @Slot()
    def run(self):
        """Generate thumbnail for the entity."""
        start_time = time.time()
        
        try:
            success = False
            source_frame = None
            animated_path = None
            
            # Determine if this is actually a video file or an image/sequence
            # Since all entities are now EntityType.VIDEO, we need to check file characteristics
            is_single_image = (len(self.entity.files) == 1 and self.entity.frame_count == 1)
            is_sequence = len(self.entity.files) > 1
            is_actual_video = (len(self.entity.files) == 1 and self.entity.frame_count != 1)
            
            
            
            if is_actual_video:
                # Check if we should generate animated thumbnail
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
                            # Also generate static thumbnail as fallback
                            duration = self.thumbnail_generator.get_video_duration(self.entity.path)
                            if duration:
                                source_frame = duration * 0.1
                            else:
                                source_frame = 1.0
                            
                            self.thumbnail_generator.extract_frame(
                                self.entity.path,
                                self.output_path,
                                source_frame,
                                self.resolution
                            )
                
                # If animated failed or not enabled, generate static thumbnail
                if not success:
                    duration = self.thumbnail_generator.get_video_duration(self.entity.path)
                    if duration:
                        source_frame = duration * 0.1
                    else:
                        source_frame = 1.0  # Default to 1 second
                    
                    success = self.thumbnail_generator.extract_frame(
                        self.entity.path,
                        self.output_path,
                        source_frame,
                        self.resolution
                    )
            else:  # Single image or sequence - use image processing
                
                if is_sequence:
                    # Check if we should generate animated thumbnail for sequence
                    if self.animated and self.config_manager:
                        animated_enabled = self.config_manager.get('thumbnails.animated.enabled', True)
                        if animated_enabled:
                            # Generate animated thumbnail from sequence
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
                    
                    # Generate static thumbnail (always, as fallback or standalone)
                    middle_index = len(self.entity.files) // 2
                    source_file = self.entity.files[middle_index]
                    
                    static_success = self.thumbnail_generator.extract_image_thumbnail(
                        source_file,
                        self.output_path,
                        self.resolution
                    )
                    
                    # Consider overall success if either static or animated succeeded
                    if not success:
                        success = static_success
                    
                else:  # Single image
                    source_file = self.entity.files[0] if self.entity.files else self.entity.path
                    
                    success = self.thumbnail_generator.extract_image_thumbnail(
                        source_file,
                        self.output_path,
                        self.resolution
                    )
            
            generation_time = time.time() - start_time
            
            if success:
                # Get file size of generated thumbnail
                try:
                    file_size = self.output_path.stat().st_size
                except OSError as e:
                    file_size = None
                    logger.warning(f"🔍 Worker: Could not get thumbnail file size for {self.entity.name}: {e}")
                
                # Pass both static and animated paths
                thumbnail_info = {
                    'static_path': str(self.output_path),
                    'animated_path': str(animated_path) if animated_path and animated_path.exists() else None
                }
                
                self.callback(self.entity, thumbnail_info, generation_time,
                            source_frame, file_size, None)
            else:
                self.callback(self.entity, None, generation_time, source_frame,
                            None, "Thumbnail generation failed")
                
        except Exception as e:
            generation_time = time.time() - start_time
            logger.error(f"🔍 Worker: ❌ Exception in thumbnail generation for {self.entity.name}: {e}")
            self.callback(self.entity, None, generation_time, None, None, str(e))


class ThumbnailManager(QObject):
    """Manages thumbnail generation and caching."""
    
    # Signals
    thumbnail_generated = Signal(object, str)  # entity, thumbnail_path
    thumbnail_generation_failed = Signal(object, str)  # entity, error
    generation_progress = Signal(int, int)  # current, total
    
    def __init__(self, config_manager: ConfigurationManager, database_manager: DatabaseManager, color_manager=None):
        super().__init__()
        self.config_manager = config_manager
        self.database_manager = database_manager
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
        self.cache_directory = Path(self.config_manager.get('thumbnails.cache_directory', '.thumbnails'))
        self.default_resolution = self.config_manager.get('thumbnails.default_resolution', 128)
        self.max_cache_size_mb = self.config_manager.get('thumbnails.max_cache_size_mb', 1024)
        
        # Ensure cache directory exists
        FileUtils.ensure_directory(self.cache_directory)
        
        # Thread pool for background processing
        self.thread_pool = QThreadPool()
        max_threads = self.config_manager.get('performance.max_concurrent_thumbnails', 4)
        self.thread_pool.setMaxThreadCount(max_threads)
        
        # Processing state
        self.processing_entities = []
        self.completed_count = 0
        
        logger.info(f"ThumbnailManager initialized (FFmpeg available: {self.ffmpeg_available})")
    
    def queue_thumbnail_generation(self, entities: List) -> None:
        """Queue thumbnail generation for entities."""
        if not entities:
            return
        
        
        if not self.ffmpeg_available:
            logger.warning("🔍 ThumbnailManager: FFmpeg not available, skipping thumbnail generation")
            return
        
        # Filter entities that need thumbnails
        entities_to_process = []
        for entity in entities:
            if self._needs_thumbnail(entity):
                entities_to_process.append(entity)
            else:
                pass
        
        if not entities_to_process:
            return
        
        # Reset processing state
        self.processing_entities = entities_to_process
        self.completed_count = 0
        
        # Start generation for each entity
        for entity in entities_to_process:
            thumbnail_path = self._get_thumbnail_path(entity)
            
            # Check if this is a video or sequence and animated thumbnails are enabled
            is_video = entity.entity_type.value == "video"
            is_sequence = len(entity.files) > 1
            animated_enabled = self.config_manager.get('thumbnails.animated.enabled', True)
            
            # Enable animated generation for both videos and sequences
            enable_animated = (is_video or is_sequence) and animated_enabled
            
            
            worker = ThumbnailGenerationWorker(
                entity,
                self.thumbnail_generator,
                thumbnail_path,
                self.default_resolution,
                self._on_thumbnail_generated,
                animated=enable_animated,
                config_manager=self.config_manager,
                color_manager=self.color_manager
            )
            self.thread_pool.start(worker)
    
    def _needs_thumbnail(self, entity) -> bool:
        """Check if entity needs thumbnail generation."""
        thumbnail_path = self._get_thumbnail_path(entity)
        
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
    
    def _get_thumbnail_path(self, entity) -> Path:
        """Get the path where entity thumbnail should be stored."""
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
        
        return self.cache_directory / thumbnail_name
    
    def _on_thumbnail_generated(self, entity, thumbnail_info,
                               generation_time: float, source_frame: Optional[float],
                               file_size: Optional[int], error: Optional[str]):
        """Handle thumbnail generation completion."""
        self.completed_count += 1
        
        if error:
            logger.error(f"Thumbnail generation failed for {entity.name}: {error}")
            self.thumbnail_generation_failed.emit(entity, error)
        elif thumbnail_info:
            # Handle both static and animated thumbnails
            if isinstance(thumbnail_info, dict):
                static_path = thumbnail_info.get('static_path')
                animated_path = thumbnail_info.get('animated_path')
                
                logger.debug(f"Thumbnail generated for {entity.name}: static={static_path}, animated={animated_path}")
                
                # Store thumbnail info in database
                self._store_thumbnail_info(entity, static_path, generation_time,
                                         source_frame, file_size, animated_path)
                
                # Emit signal with static path for backward compatibility
                self.thumbnail_generated.emit(entity, static_path)
            else:
                # Legacy single path
                logger.debug(f"Thumbnail generated for {entity.name}: {thumbnail_info}")
                self._store_thumbnail_info(entity, thumbnail_info, generation_time,
                                         source_frame, file_size)
                self.thumbnail_generated.emit(entity, thumbnail_info)
        
        # Emit progress
        self.generation_progress.emit(self.completed_count, len(self.processing_entities))
        
        # Check cache size periodically
        if self.completed_count % 10 == 0:
            self._check_cache_size()
    
    @database_retry(max_retries=5, base_delay=0.1)
    def _store_thumbnail_info(self, entity, thumbnail_path: str, generation_time: float,
                             source_frame: Optional[float], file_size: Optional[int],
                             animated_path: Optional[str] = None):
        """Store thumbnail information in database."""
        try:
            with self.database_manager.get_session() as session:
                # Find or create entity in database
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
                        file_count=int(len(entity.files)),
                        thumbnail_generated=True,
                        metadata_extracted=False
                    )
                    session.add(db_entity)
                    session.flush()  # Get the ID
                
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
                    # Store animated path in extra_data if available
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
                    # Store animated path in extra_data if available
                    if animated_path:
                        thumbnail_record.extra_data = {'animated_path': str(animated_path)}
                    session.add(thumbnail_record)
                
                # Mark entity as having thumbnail
                db_entity.thumbnail_generated = True
                
                logger.debug(f"Successfully stored thumbnail info for entity: {entity.name}")
                
        except Exception as e:
            logger.error(f"Error storing thumbnail info for {entity.name}: {e}")
            # Don't re-raise to allow application to continue
    
    def get_thumbnail_path(self, entity) -> Optional[str]:
        """Get thumbnail path for entity if it exists."""
        thumbnail_path = self._get_thumbnail_path(entity)
        
        if thumbnail_path.exists():
            return str(thumbnail_path)
        
        return None
    
    @database_retry(max_retries=3, base_delay=0.05)
    def get_animated_thumbnail_path(self, entity) -> Optional[str]:
        """Get animated thumbnail path for entity if it exists (supports videos and sequences)."""
        # Support both videos and image sequences for animated thumbnails
        is_video = entity.entity_type.value == "video"
        is_sequence = len(entity.files) > 1
        
        if not (is_video or is_sequence):
            return None
        
        # Check for GIF version
        thumbnail_path = self._get_thumbnail_path(entity)
        animated_path = thumbnail_path.with_suffix('.gif')
        
        if animated_path.exists():
            return str(animated_path)
        
        # Check database for stored animated path
        try:
            with self.database_manager.get_session() as session:
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
        except Exception as e:
            logger.error(f"Error getting animated thumbnail path: {e}")
        
        return None
    
    def _check_cache_size(self):
        """Check and manage cache size."""
        try:
            cache_size_bytes = FileUtils.get_directory_size(self.cache_directory)
            cache_size_mb = cache_size_bytes / (1024 * 1024)
            
            if cache_size_mb > self.max_cache_size_mb:
                logger.info(f"Cache size ({cache_size_mb:.1f} MB) exceeds limit ({self.max_cache_size_mb} MB)")
                self._cleanup_old_thumbnails()
                
        except Exception as e:
            logger.error(f"Error checking cache size: {e}")
    
    def _cleanup_old_thumbnails(self):
        """Remove old thumbnails to free up space."""
        try:
            # Get all thumbnail files sorted by modification time
            thumbnail_files = list(self.cache_directory.glob("*.jpg"))
            thumbnail_files.sort(key=lambda f: f.stat().st_mtime)
            
            # Remove oldest 25% of files
            files_to_remove = len(thumbnail_files) // 4
            
            for thumbnail_file in thumbnail_files[:files_to_remove]:
                try:
                    thumbnail_file.unlink()
                    logger.debug(f"Removed old thumbnail: {thumbnail_file}")
                except OSError as e:
                    logger.warning(f"Could not remove thumbnail {thumbnail_file}: {e}")
            
            logger.info(f"Cleaned up {files_to_remove} old thumbnails")
            
        except Exception as e:
            logger.error(f"Error cleaning up thumbnails: {e}")
    
    def get_cache_info(self) -> Dict[str, any]:
        """Get information about thumbnail cache."""
        try:
            cache_size_bytes = FileUtils.get_directory_size(self.cache_directory)
            thumbnail_count = len(list(self.cache_directory.glob("*.jpg")))
            
            return {
                'cache_directory': str(self.cache_directory),
                'cache_size_bytes': cache_size_bytes,
                'cache_size_formatted': FileUtils.format_bytes(cache_size_bytes),
                'thumbnail_count': thumbnail_count,
                'max_cache_size_mb': self.max_cache_size_mb,
                'default_resolution': self.default_resolution,
            }
            
        except Exception as e:
            logger.error(f"Error getting cache info: {e}")
            return {}
    
    def clear_cache(self) -> bool:
        """Clear all thumbnails from cache."""
        try:
            thumbnail_files = list(self.cache_directory.glob("*.jpg"))
            
            for thumbnail_file in thumbnail_files:
                try:
                    thumbnail_file.unlink()
                except OSError as e:
                    logger.warning(f"Could not remove thumbnail {thumbnail_file}: {e}")
            
            logger.info(f"Cleared {len(thumbnail_files)} thumbnails from cache")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
    
    def shutdown(self) -> None:
        """Shutdown thumbnail manager."""
        logger.info("ThumbnailManager shutting down")
        
        # Wait for all workers to complete (with timeout)
        if not self.thread_pool.waitForDone(5000):  # 5 second timeout
            logger.warning("Some thumbnail generation workers did not complete in time")
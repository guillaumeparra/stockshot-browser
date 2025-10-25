"""
File system utilities for Stockshot Browser.
"""

import logging
import os
from pathlib import Path
from typing import List, Set, Optional, Tuple
import hashlib

logger = logging.getLogger(__name__)


class FileUtils:
    """Utility functions for file system operations."""
    
    @staticmethod
    def get_file_hash(file_path: Path, algorithm: str = 'md5') -> Optional[str]:
        """
        Calculate hash of a file.
        
        Args:
            file_path: Path to the file
            algorithm: Hash algorithm ('md5', 'sha1', 'sha256')
            
        Returns:
            Hex digest of the file hash, or None if error
        """
        try:
            hash_obj = hashlib.new(algorithm)
            
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_obj.update(chunk)
            
            return hash_obj.hexdigest()
            
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            return None
    
    @staticmethod
    def get_file_size_formatted(file_path: Path) -> str:
        """
        Get formatted file size string.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Formatted size string (e.g., "1.5 MB")
        """
        try:
            size_bytes = file_path.stat().st_size
            return FileUtils.format_bytes(size_bytes)
        except Exception as e:
            logger.error(f"Error getting file size for {file_path}: {e}")
            return "Unknown"
    
    @staticmethod
    def format_bytes(size_bytes: int) -> str:
        """
        Format bytes into human readable string.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Formatted string (e.g., "1.5 MB")
        """
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    @staticmethod
    def is_hidden_file(file_path: Path) -> bool:
        """
        Check if a file is hidden.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file is hidden
        """
        # Unix-style hidden files (start with .)
        if file_path.name.startswith('.'):
            return True
        
        # Windows hidden files
        if os.name == 'nt':
            try:
                import stat
                return bool(file_path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
            except (AttributeError, OSError):
                pass
        
        return False
    
    @staticmethod
    def filter_media_files(files: List[Path], video_extensions: Set[str],
                          image_extensions: Set[str]) -> Tuple[List[Path], List[Path]]:
        """
        Filter files into video and image categories.
        
        Args:
            files: List of file paths
            video_extensions: Set of video file extensions
            image_extensions: Set of image file extensions
            
        Returns:
            Tuple of (video_files, image_files)
        """
        video_files = []
        image_files = []
        
        for file_path in files:
            if not file_path.is_file():
                continue
                
            extension = file_path.suffix.lower()
            
            if extension in video_extensions:
                video_files.append(file_path)
            elif extension in image_extensions:
                image_files.append(file_path)
        
        return video_files, image_files
    
    @staticmethod
    def safe_filename(filename: str, replacement: str = '_') -> str:
        """
        Create a safe filename by replacing invalid characters.
        
        Args:
            filename: Original filename
            replacement: Character to replace invalid chars with
            
        Returns:
            Safe filename
        """
        # Characters that are invalid in filenames
        invalid_chars = '<>:"/\\|?*'
        
        safe_name = filename
        for char in invalid_chars:
            safe_name = safe_name.replace(char, replacement)
        
        # Remove leading/trailing spaces and dots
        safe_name = safe_name.strip(' .')
        
        # Ensure it's not empty
        if not safe_name:
            safe_name = 'unnamed'
        
        return safe_name
    
    @staticmethod
    def ensure_directory(directory: Path) -> bool:
        """
        Ensure a directory exists, creating it if necessary.
        
        Args:
            directory: Directory path
            
        Returns:
            True if directory exists or was created successfully
        """
        try:
            directory.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Error creating directory {directory}: {e}")
            return False
    
    @staticmethod
    def get_directory_size(directory: Path) -> int:
        """
        Calculate total size of all files in a directory.
        
        Args:
            directory: Directory path
            
        Returns:
            Total size in bytes
        """
        total_size = 0
        
        try:
            for file_path in directory.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except Exception as e:
            logger.error(f"Error calculating directory size for {directory}: {e}")
        
        return total_size
    
    @staticmethod
    def find_files_by_pattern(directory: Path, pattern: str, recursive: bool = True) -> List[Path]:
        """
        Find files matching a glob pattern.
        
        Args:
            directory: Directory to search in
            pattern: Glob pattern (e.g., "*.mp4")
            recursive: Whether to search recursively
            
        Returns:
            List of matching file paths
        """
        try:
            if recursive:
                return list(directory.rglob(pattern))
            else:
                return list(directory.glob(pattern))
        except Exception as e:
            logger.error(f"Error finding files with pattern '{pattern}' in {directory}: {e}")
            return []
    
    @staticmethod
    def copy_file_with_progress(source: Path, destination: Path, 
                               progress_callback=None) -> bool:
        """
        Copy a file with optional progress callback.
        
        Args:
            source: Source file path
            destination: Destination file path
            progress_callback: Optional callback function(bytes_copied, total_bytes)
            
        Returns:
            True if copy was successful
        """
        try:
            # Ensure destination directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            total_size = source.stat().st_size
            bytes_copied = 0
            
            with open(source, 'rb') as src, open(destination, 'wb') as dst:
                while True:
                    chunk = src.read(64 * 1024)  # 64KB chunks
                    if not chunk:
                        break
                    
                    dst.write(chunk)
                    bytes_copied += len(chunk)
                    
                    if progress_callback:
                        progress_callback(bytes_copied, total_size)
            
            return True
            
        except Exception as e:
            logger.error(f"Error copying file from {source} to {destination}: {e}")
            return False
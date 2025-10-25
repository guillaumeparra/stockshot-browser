"""
FFmpeg integration utilities for Stockshot Browser.
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
import shutil

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    """Exception raised for FFmpeg-related errors."""
    pass


class FFmpegExtractor:
    """Extracts metadata and generates thumbnails using FFmpeg."""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.ffmpeg_path = self.config_manager.get('ffmpeg.executable_path', 'ffmpeg')
        self.ffprobe_path = self.config_manager.get('ffmpeg.ffprobe_path', 'ffprobe')
        self.timeout = self.config_manager.get('ffmpeg.timeout', 30)
        
        # Verify FFmpeg installation
        self._verify_ffmpeg()
        
    
    def _verify_ffmpeg(self) -> None:
        """Verify that FFmpeg and FFprobe are available."""
        try:
            # Check ffmpeg
            result = subprocess.run(
                [self.ffmpeg_path, '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                raise FFmpegError(f"FFmpeg not found at {self.ffmpeg_path}")
            
            # Check ffprobe
            result = subprocess.run(
                [self.ffprobe_path, '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.warning(f"FFprobe not found at {self.ffprobe_path}, using ffmpeg for probing")
                self.ffprobe_path = self.ffmpeg_path
                
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise FFmpegError(f"FFmpeg verification failed: {e}")
    
    def extract_video_info(self, video_path: Path) -> Dict[str, Any]:
        """
        Extract comprehensive metadata from video file.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary containing video metadata
        """
        
        try:
            # Use ffprobe to get detailed information
            cmd = [
                self.ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(video_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                raise FFmpegError(f"FFprobe failed: {result.stderr}")
            
            probe_data = json.loads(result.stdout)
            return self._parse_video_metadata(probe_data)
            
        except subprocess.TimeoutExpired:
            raise FFmpegError(f"FFprobe timeout after {self.timeout} seconds")
        except json.JSONDecodeError as e:
            raise FFmpegError(f"Failed to parse FFprobe output: {e}")
        except Exception as e:
            return self._get_basic_file_info(video_path)
    
    def extract_image_info(self, image_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from image file.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Dictionary containing image metadata
        """
        
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(image_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                raise FFmpegError(f"FFprobe failed: {result.stderr}")
            
            probe_data = json.loads(result.stdout)
            return self._parse_image_metadata(probe_data)
            
        except Exception as e:
            return self._get_basic_file_info(image_path)
    
    def _parse_video_metadata(self, probe_data: Dict) -> Dict[str, Any]:
        """Parse FFprobe output for video files."""
        metadata = {}
        
        # Format information
        if 'format' in probe_data:
            format_info = probe_data['format']
            metadata.update({
                'format': format_info.get('format_name', '').split(',')[0],
                'duration': float(format_info.get('duration', 0)),
                'bitrate': int(format_info.get('bit_rate', 0)) if format_info.get('bit_rate') else None,
                'file_size': int(format_info.get('size', 0)),
            })
            
            # Parse tags
            if 'tags' in format_info:
                tags = format_info['tags']
                metadata.update({
                    'title': tags.get('title'),
                    'artist': tags.get('artist'),
                    'album': tags.get('album'),
                    'date': tags.get('date'),
                    'comment': tags.get('comment'),
                })
        
        # Stream information
        if 'streams' in probe_data:
            video_stream = None
            audio_stream = None
            
            for stream in probe_data['streams']:
                if stream.get('codec_type') == 'video' and not video_stream:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio' and not audio_stream:
                    audio_stream = stream
            
            # Video stream info
            if video_stream:
                metadata.update({
                    'codec': video_stream.get('codec_name'),
                    'width': int(video_stream.get('width', 0)),
                    'height': int(video_stream.get('height', 0)),
                    'fps': self._parse_fps(video_stream.get('r_frame_rate', '0/1')),
                    'pixel_format': video_stream.get('pix_fmt'),
                    'colorspace': video_stream.get('color_space'),
                    'color_range': video_stream.get('color_range'),
                    'bit_depth': self._get_bit_depth(video_stream.get('pix_fmt')),
                })
                
                # Calculate frame count
                duration = metadata.get('duration', 0)
                fps = metadata.get('fps', 0)
                if duration and fps:
                    metadata['frame_count'] = int(duration * fps)
            
            # Audio stream info
            if audio_stream:
                metadata.update({
                    'has_audio': True,
                    'audio_codec': audio_stream.get('codec_name'),
                    'audio_channels': int(audio_stream.get('channels', 0)),
                    'audio_sample_rate': int(audio_stream.get('sample_rate', 0)),
                })
            else:
                metadata['has_audio'] = False
        
        # Calculate aspect ratio
        width = metadata.get('width')
        height = metadata.get('height')
        if width and height and height > 0:
            metadata['aspect_ratio'] = round(width / height, 3)
        
        return metadata
    
    def _parse_image_metadata(self, probe_data: Dict) -> Dict[str, Any]:
        """Parse FFprobe output for image files."""
        metadata = {}
        
        # Format information
        if 'format' in probe_data:
            format_info = probe_data['format']
            metadata.update({
                'format': format_info.get('format_name', '').split(',')[0],
                'file_size': int(format_info.get('size', 0)),
            })
        
        # Stream information
        if 'streams' in probe_data and probe_data['streams']:
            stream = probe_data['streams'][0]  # First stream for images
            
            metadata.update({
                'codec': stream.get('codec_name'),
                'width': int(stream.get('width', 0)),
                'height': int(stream.get('height', 0)),
                'pixel_format': stream.get('pix_fmt'),
                'colorspace': stream.get('color_space'),
                'color_range': stream.get('color_range'),
                'bit_depth': self._get_bit_depth(stream.get('pix_fmt')),
            })
            
            # Calculate aspect ratio
            width = metadata.get('width')
            height = metadata.get('height')
            if width and height and height > 0:
                metadata['aspect_ratio'] = round(width / height, 3)
        
        return metadata
    
    def _parse_fps(self, fps_string: str) -> Optional[float]:
        """Parse FPS from FFmpeg format (e.g., '25/1', '30000/1001')."""
        try:
            if '/' in fps_string:
                numerator, denominator = fps_string.split('/')
                return round(float(numerator) / float(denominator), 3)
            else:
                return float(fps_string)
        except (ValueError, ZeroDivisionError):
            return None
    
    def _get_bit_depth(self, pixel_format: Optional[str]) -> Optional[int]:
        """Get bit depth from pixel format."""
        if not pixel_format:
            return None
        
        # Common pixel format to bit depth mapping
        bit_depth_map = {
            'yuv420p': 8,
            'yuv422p': 8,
            'yuv444p': 8,
            'yuv420p10le': 10,
            'yuv422p10le': 10,
            'yuv444p10le': 10,
            'yuv420p12le': 12,
            'yuv422p12le': 12,
            'yuv444p12le': 12,
            'rgb24': 8,
            'rgba': 8,
            'rgb48le': 16,
            'rgba64le': 16,
        }
        
        return bit_depth_map.get(pixel_format.lower())
    
    def _get_basic_file_info(self, file_path: Path) -> Dict[str, Any]:
        """Get basic file information when FFmpeg fails."""
        try:
            stat = file_path.stat()
            return {
                'file_size': stat.st_size,
                'format': file_path.suffix.lstrip('.').lower(),
                'created_at': stat.st_ctime,
                'modified_at': stat.st_mtime,
            }
        except Exception:
            return {'format': file_path.suffix.lstrip('.').lower()}


class FFmpegThumbnailGenerator:
    """Generates thumbnails using FFmpeg."""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.ffmpeg_path = self.config_manager.get('ffmpeg.executable_path', 'ffmpeg')
        self.timeout = self.config_manager.get('ffmpeg.timeout', 30)
        self.thumbnail_time_offset = self.config_manager.get('ffmpeg.thumbnail_time_offset', 0.1)
        
    
    def extract_frame(self, video_path: Path, output_path: Path, 
                     timestamp: float, resolution: int) -> bool:
        """
        Extract a frame from video at specified timestamp.
        
        Args:
            video_path: Path to video file
            output_path: Path for output thumbnail
            timestamp: Time in seconds to extract frame
            resolution: Target resolution (height or width)
            
        Returns:
            True if successful
        """
        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            cmd = [
                self.ffmpeg_path,
                '-ss', str(timestamp),
                '-i', str(video_path),
                '-vframes', '1',
                '-vf', f'scale=-1:{resolution}',
                '-q:v', '2',  # High quality
                '-y',  # Overwrite output
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0 and output_path.exists():
                return True
            else:
                return False
                
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            return False
    
    def extract_image_thumbnail(self, image_path: Path, output_path: Path,
                               resolution: int) -> bool:
        """
        Generate thumbnail from image file using FFmpeg exclusively.
        
        Supports a wide variety of image formats and handles alpha channels properly
        by compositing against a black background when needed.
        
        Args:
            image_path: Path to image file
            output_path: Path for output thumbnail
            resolution: Target resolution
            
        Returns:
            True if successful
        """
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Try FFmpeg with alpha handling (most comprehensive approach)
        if self._extract_image_thumbnail_ffmpeg_with_alpha(image_path, output_path, resolution):
            return True
        else:
            logger.warning(f"FFmpeg alpha-aware method failed for: {image_path}")
        
        # Try simple FFmpeg approach as fallback
        if self._extract_image_thumbnail_ffmpeg_simple(image_path, output_path, resolution):
            return True
        else:
            logger.warning(f"Simple FFmpeg method failed for: {image_path}")
            
        # Try FFmpeg with explicit image format as final fallback
        if self._extract_image_thumbnail_ffmpeg_format(image_path, output_path, resolution):
            return True
        else:
            logger.warning(f"Format-specific FFmpeg method failed for: {image_path}")

        return False
    
    def _extract_image_thumbnail_ffmpeg_with_alpha(self, image_path: Path, output_path: Path, resolution: int) -> bool:
        """FFmpeg method with proper alpha channel handling."""
        try:
            # Remove any existing empty file
            if output_path.exists():
                if output_path.stat().st_size == 0:
                    output_path.unlink()
                    logger.debug(f"Removed empty thumbnail file: {output_path}")
            
            # Use FFmpeg with alpha overlay filter to handle transparency properly
            # This composites the image against a black background, ignoring alpha
            cmd = [
                self.ffmpeg_path,
                '-i', str(image_path),
                '-vf', (
                    f'scale=-1:{resolution}:flags=lanczos,'  # Scale to target resolution
                    f'split=2[bg][img];'  # Split the input into two streams
                    f'[bg]format=rgb24,drawbox=c=black:t=fill[bg];'  # Create black background
                    f'[bg][img]overlay=alpha=straight'  # Overlay image on black background, ignoring alpha
                ),
                '-frames:v', '1',
                '-q:v', '2',  # High quality
                '-y',  # Overwrite output
                str(output_path)
            ]
            
            logger.debug(f"FFmpeg alpha-aware command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            
            # Check if output file exists and has content
            if output_path.exists() and output_path.stat().st_size > 0:
                file_size = output_path.stat().st_size
                logger.debug(f"FFmpeg alpha-aware method succeeded: {output_path} ({file_size} bytes)")
                return True
            else:
                logger.debug(f"FFmpeg alpha-aware method failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.debug(f"FFmpeg alpha-aware method exception: {e}")
            return False
    
    def _extract_image_thumbnail_ffmpeg_simple(self, image_path: Path, output_path: Path, resolution: int) -> bool:
        """Simple FFmpeg method for image thumbnail extraction."""
        try:
            # Remove any existing empty file
            if output_path.exists():
                if output_path.stat().st_size == 0:
                    output_path.unlink()
                    logger.debug(f"Removed empty thumbnail file: {output_path}")
            
            # Use simple approach - treat as single image, not video stream
            cmd = [
                self.ffmpeg_path,
                '-i', str(image_path),
                '-vf', f'scale=-1:{resolution}:flags=lanczos',
                '-frames:v', '1',
                '-q:v', '2',
                '-y',
                str(output_path)
            ]
            
            logger.debug(f"Simple FFmpeg command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            
            # Check if output file exists and has content
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.debug(f"Simple FFmpeg method succeeded for: {image_path}")
                return True
            else:
                logger.debug(f"Simple FFmpeg method failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.debug(f"Simple FFmpeg method exception: {e}")
            return False
    
    def _extract_image_thumbnail_ffmpeg_format(self, image_path: Path, output_path: Path, resolution: int) -> bool:
        """FFmpeg method with explicit image format specification."""
        try:
            # Remove any existing empty file
            if output_path.exists():
                if output_path.stat().st_size == 0:
                    output_path.unlink()
                    logger.debug(f"Removed empty thumbnail file: {output_path}")
            
            # Detect input format from file extension
            ext = image_path.suffix.lower()
            input_format = 'png_pipe' if ext == '.png' else 'image2'
            
            cmd = [
                self.ffmpeg_path,
                '-f', input_format,
                '-i', str(image_path),
                '-vf', f'scale=-1:{resolution}:flags=lanczos',
                '-frames:v', '1',
                '-q:v', '2',
                '-y',
                str(output_path)
            ]
            
            logger.debug(f"Format-specific FFmpeg command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            
            # Check if output file exists and has content
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.debug(f"Format-specific FFmpeg method succeeded for: {image_path}")
                return True
            else:
                logger.debug(f"Format-specific FFmpeg method failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.debug(f"Format-specific FFmpeg method exception: {e}")
            return False
    
    
    def get_video_duration(self, video_path: Path) -> Optional[float]:
        """Get video duration in seconds. Returns None for single images."""
        # Check if this is likely a single image file
        image_extensions = {'.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.gif', '.webp', '.exr', '.hdr'}
        if video_path.suffix.lower() in image_extensions:
            # Don't try to get duration for single images - this is expected
            logger.debug(f"Skipping duration extraction for image file: {video_path}")
            return None
        
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                str(video_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if 'format' in data and 'duration' in data['format']:
                    return float(data['format']['duration'])
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting video duration for {video_path}: {e}")
            return None
    
    def generate_animated_thumbnail(self, video_path: Path, output_path: Path,
                                  frame_count: int = 25, fps: int = 10,
                                  resolution: int = 128) -> bool:
        """
        Generate an animated thumbnail (GIF) from a video file with alpha handling.
        
        Args:
            video_path: Path to video file
            output_path: Path for output animated thumbnail (should be .gif)
            frame_count: Number of frames to extract
            fps: Frames per second for the output GIF
            resolution: Target resolution (height)
            
        Returns:
            True if successful
        """
        try:
            # Get video duration
            duration = self.get_video_duration(video_path)
            if not duration or duration <= 0:
                logger.debug(f"Could not get duration for {video_path} - may be an image file")
                return False
            
            # Calculate frame interval
            # Extract frames evenly distributed throughout the video
            interval = duration / frame_count
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Build complex filter for extracting frames and creating GIF with alpha handling
            # This extracts frames at regular intervals, handles alpha by compositing on black background
            filter_complex = (
                f"fps=fps={frame_count}/{duration},"  # Extract frames at calculated rate
                f"scale=-1:{resolution}:flags=lanczos,"  # Scale to target resolution
                f"split=2[s0][s1];"  # Split for alpha handling and palette generation
                f"[s0]format=yuv420p,drawbox=c=black:t=fill[bg];"  # Create black background
                f"[bg][s1]overlay=alpha=straight[comp];"  # Overlay on black background, ignoring alpha
                f"[comp]split[s3][s4];"  # Split composited stream for palette generation
                f"[s3]palettegen=max_colors=128:stats_mode=single[p];"  # Generate optimized palette
                f"[s4][p]paletteuse=dither=bayer:bayer_scale=5"  # Apply palette with dithering
            )
            
            cmd = [
                self.ffmpeg_path,
                '-i', str(video_path),
                '-filter_complex', filter_complex,
                '-r', str(fps),  # Output frame rate
                '-loop', '0',  # Infinite loop
                '-y',  # Overwrite output
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0 and output_path.exists():
                # Check file size and optimize if needed
                file_size_kb = output_path.stat().st_size / 1024
                max_size_kb = self.config_manager.get('thumbnails.animated.max_size_kb', 500)
                
                if file_size_kb > max_size_kb:
                    # Try to optimize further by reducing colors
                    logger.debug(f"Animated thumbnail too large ({file_size_kb:.1f}KB), optimizing...")
                    return self._optimize_animated_thumbnail(video_path, output_path,
                                                           frame_count, fps, resolution)
                
                logger.debug(f"Generated animated thumbnail with alpha handling: {output_path} ({file_size_kb:.1f}KB)")
                return True
            else:
                logger.error(f"FFmpeg animated thumbnail generation failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg animated thumbnail generation timeout after {self.timeout} seconds")
            return False
        except Exception as e:
            logger.error(f"Error generating animated thumbnail for {video_path}: {e}")
            return False
    
    def _optimize_animated_thumbnail(self, video_path: Path, output_path: Path,
                                   frame_count: int, fps: int, resolution: int) -> bool:
        """
        Optimize animated thumbnail by reducing quality/colors with alpha handling.
        """
        try:
            duration = self.get_video_duration(video_path)
            if not duration:
                return False
            
            # More aggressive optimization with alpha handling
            filter_complex = (
                f"fps=fps={frame_count}/{duration},"
                f"scale=-1:{resolution}:flags=lanczos,"
                f"split=2[s0][s1];"  # Split for alpha handling and palette generation
                f"[s0]format=yuv420p,drawbox=c=black:t=fill[bg];"  # Create black background
                f"[bg][s1]overlay=alpha=straight[comp];"  # Overlay on black background, ignoring alpha
                f"[comp]split[s3][s4];"  # Split composited stream for palette generation
                f"[s3]palettegen=max_colors=64:stats_mode=single[p];"  # Fewer colors
                f"[s4][p]paletteuse=dither=none"  # No dithering for smaller size
            )
            
            cmd = [
                self.ffmpeg_path,
                '-i', str(video_path),
                '-filter_complex', filter_complex,
                '-r', str(fps),
                '-loop', '0',
                '-y',
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0 and output_path.exists():
                file_size_kb = output_path.stat().st_size / 1024
                logger.debug(f"Optimized animated thumbnail with alpha handling: {output_path} ({file_size_kb:.1f}KB)")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error optimizing animated thumbnail: {e}")
            return False
    
    def generate_animated_thumbnail_from_sequence(self, image_files: List[Path], output_path: Path,
                                                 frame_count: int = 25, fps: int = 10,
                                                 resolution: int = 128) -> bool:
        """
        Generate an animated thumbnail (GIF) from an image sequence.
        
        Args:
            image_files: List of image file paths in the sequence
            output_path: Path for output animated thumbnail (should be .gif)
            frame_count: Maximum number of frames to include
            fps: Frames per second for the output GIF
            resolution: Target resolution (height)
            
        Returns:
            True if successful
        """
        try:
            if not image_files or len(image_files) < 2:
                logger.debug(f"Not enough images for animation: {len(image_files) if image_files else 0}")
                return False
            
            # Sort files to ensure proper sequence order
            sorted_files = sorted(image_files)
            
            # Calculate sampling interval to get desired frame count
            if len(sorted_files) <= frame_count:
                # Use all files if we have fewer than requested
                sampled_files = sorted_files
            else:
                # Sample evenly throughout the sequence
                interval = len(sorted_files) / frame_count
                sampled_files = []
                for i in range(frame_count):
                    index = int(i * interval)
                    if index < len(sorted_files):
                        sampled_files.append(sorted_files[index])
            
            logger.debug(f"Creating animated thumbnail from {len(sampled_files)} frames (out of {len(sorted_files)} total)")
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create a temporary directory for processed frames
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                processed_frames = []
                
                # Process each selected frame with alpha handling
                for i, image_file in enumerate(sampled_files):
                    frame_output = temp_path / f"frame_{i:04d}.jpg"
                    
                    # Scale each frame to target resolution with alpha compositing on black background
                    # This handles transparency properly by ignoring alpha channels
                    cmd = [
                        self.ffmpeg_path,
                        '-i', str(image_file),
                        '-vf', (
                            f'scale=-1:{resolution}:flags=lanczos:force_original_aspect_ratio=decrease,'
                            f'split=2[bg][img];'  # Split the input into two streams
                            f'[bg]format=yuv420p,drawbox=c=black:t=fill[bg];'  # Create black background
                            f'[bg][img]overlay=alpha=straight'  # Overlay image on black background, ignoring alpha
                        ),
                        '-q:v', '2',
                        '-y',
                        str(frame_output)
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0 and frame_output.exists():
                        processed_frames.append(frame_output)
                    else:
                        logger.warning(f"Failed to process frame: {image_file}")
                
                if not processed_frames:
                    logger.error("No frames were successfully processed")
                    return False
                
                # Create input pattern for FFmpeg
                input_pattern = temp_path / "frame_%04d.jpg"
                
                # Generate GIF with palette optimization, aspect ratio preservation, and alpha handling
                filter_complex = (
                    f"fps={fps},"  # Set frame rate
                    f"scale=-1:{resolution}:flags=lanczos:force_original_aspect_ratio=decrease,"  # Ensure consistent scaling
                    f"split=2[s0][s1];"  # Split for alpha handling and palette generation
                    f"[s0]format=yuv420p,drawbox=c=black:t=fill[bg];"  # Create black background
                    f"[bg][s1]overlay=alpha=straight[comp];"  # Overlay on black background, ignoring alpha
                    f"[comp]split[s3][s4];"  # Split composited stream for palette generation
                    f"[s3]palettegen=max_colors=128:stats_mode=single[p];"  # Generate optimized palette
                    f"[s4][p]paletteuse=dither=bayer:bayer_scale=5"  # Apply palette with dithering
                )
                
                cmd = [
                    self.ffmpeg_path,
                    '-framerate', str(fps),
                    '-i', str(input_pattern),
                    '-filter_complex', filter_complex,
                    '-loop', '0',  # Infinite loop
                    '-y',  # Overwrite output
                    str(output_path)
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )
                
                if result.returncode == 0 and output_path.exists():
                    # Check file size and optimize if needed
                    file_size_kb = output_path.stat().st_size / 1024
                    max_size_kb = self.config_manager.get('thumbnails.animated.max_size_kb', 500)
                    
                    if file_size_kb > max_size_kb:
                        # Try to optimize by reducing colors
                        logger.debug(f"Sequence animated thumbnail too large ({file_size_kb:.1f}KB), optimizing...")
                        return self._optimize_sequence_animated_thumbnail(sampled_files, output_path, fps, resolution)
                    
                    logger.debug(f"Generated sequence animated thumbnail: {output_path} ({file_size_kb:.1f}KB)")
                    return True
                else:
                    logger.error(f"FFmpeg sequence animated thumbnail generation failed: {result.stderr}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error generating animated thumbnail from sequence: {e}")
            return False
    
    def _optimize_sequence_animated_thumbnail(self, image_files: List[Path], output_path: Path,
                                            fps: int, resolution: int) -> bool:
        """
        Optimize sequence animated thumbnail by reducing quality/colors.
        """
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                processed_frames = []
                
                # Process frames with lower quality and alpha handling
                for i, image_file in enumerate(image_files):
                    frame_output = temp_path / f"frame_{i:04d}.jpg"
                    
                    cmd = [
                        self.ffmpeg_path,
                        '-i', str(image_file),
                        '-vf', (
                            f'scale=-1:{resolution}:flags=lanczos:force_original_aspect_ratio=decrease,'
                            f'split=2[bg][img];'  # Split the input into two streams
                            f'[bg]format=yuv420p,drawbox=c=black:t=fill[bg];'  # Create black background
                            f'[bg][img]overlay=alpha=straight'  # Overlay image on black background, ignoring alpha
                        ),
                        '-q:v', '5',  # Lower quality
                        '-y',
                        str(frame_output)
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0 and frame_output.exists():
                        processed_frames.append(frame_output)
                
                if not processed_frames:
                    return False
                
                input_pattern = temp_path / "frame_%04d.jpg"
                
                # More aggressive optimization with aspect ratio preservation and alpha handling
                filter_complex = (
                    f"fps={fps},"
                    f"scale=-1:{resolution}:flags=lanczos:force_original_aspect_ratio=decrease,"  # Ensure consistent scaling
                    f"split=2[s0][s1];"  # Split for alpha handling and palette generation
                    f"[s0]format=yuv420p,drawbox=c=black:t=fill[bg];"  # Create black background
                    f"[bg][s1]overlay=alpha=straight[comp];"  # Overlay on black background, ignoring alpha
                    f"[comp]split[s3][s4];"  # Split composited stream for palette generation
                    f"[s3]palettegen=max_colors=64:stats_mode=single[p];"  # Fewer colors
                    f"[s4][p]paletteuse=dither=none"  # No dithering for smaller size
                )
                
                cmd = [
                    self.ffmpeg_path,
                    '-framerate', str(fps),
                    '-i', str(input_pattern),
                    '-filter_complex', filter_complex,
                    '-loop', '0',
                    '-y',
                    str(output_path)
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )
                
                if result.returncode == 0 and output_path.exists():
                    file_size_kb = output_path.stat().st_size / 1024
                    logger.debug(f"Optimized sequence animated thumbnail: {output_path} ({file_size_kb:.1f}KB)")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error optimizing sequence animated thumbnail: {e}")
            return False

    def extract_frames_for_animation(self, video_path: Path, output_dir: Path,
                                    frame_count: int = 25, resolution: int = 128) -> List[Path]:
        """
        Extract individual frames from video for custom animation.
        
        Args:
            video_path: Path to video file
            output_dir: Directory to save frames
            frame_count: Number of frames to extract
            resolution: Target resolution
            
        Returns:
            List of paths to extracted frames
        """
        try:
            duration = self.get_video_duration(video_path)
            if not duration or duration <= 0:
                return []
            
            output_dir.mkdir(parents=True, exist_ok=True)
            frame_paths = []
            
            # Calculate timestamps for frame extraction
            interval = duration / frame_count
            
            for i in range(frame_count):
                timestamp = i * interval
                frame_path = output_dir / f"frame_{i:04d}.jpg"
                
                cmd = [
                    self.ffmpeg_path,
                    '-ss', str(timestamp),
                    '-i', str(video_path),
                    '-vframes', '1',
                    '-vf', f'scale=-1:{resolution}',
                    '-q:v', '2',
                    '-y',
                    str(frame_path)
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0 and frame_path.exists():
                    frame_paths.append(frame_path)
                else:
                    logger.warning(f"Failed to extract frame at {timestamp}s")
            
            logger.debug(f"Extracted {len(frame_paths)} frames from {video_path}")
            return frame_paths
            
        except Exception as e:
            logger.error(f"Error extracting frames from {video_path}: {e}")
            return []
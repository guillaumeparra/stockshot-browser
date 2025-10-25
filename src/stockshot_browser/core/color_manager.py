"""
Color management system using OpenColorIO for Stockshot Browser.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import numpy as np

try:
    import PyOpenColorIO as ocio
    OCIO_AVAILABLE = True
except ImportError:
    OCIO_AVAILABLE = False
    ocio = None

from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class ColorManager(QObject):
    """Color management system using OpenColorIO."""
    
    # Signals
    config_loaded = Signal(str)  # config_path
    config_error = Signal(str)   # error_message
    
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.ocio_config: Optional[ocio.Config] = None
        self.display_transform: Optional[ocio.DisplayViewTransform] = None
        self.is_enabled = False
        
        # Cache for transforms
        self._transform_cache: Dict[str, Any] = {}
        
        self._initialize()
    
    def _initialize(self):
        """Initialize the color management system."""
        if not OCIO_AVAILABLE:
            logger.warning("OpenColorIO not available. Color management disabled.")
            return
        
        color_config = self.config_manager.get('color_management', {})
        
        if not color_config.get('enabled', False):
            logger.info("Color management disabled in configuration")
            return
        
        config_path = color_config.get('config_path', '')
        if config_path:
            self.load_config(config_path)
        else:
            # Try to use default OCIO config
            self._try_default_config()
    
    def _try_default_config(self):
        """Try to load default OCIO configuration."""
        try:
            # Try environment variable first
            if 'OCIO' in os.environ:
                config_path = os.environ['OCIO']
                if Path(config_path).exists():
                    self.load_config(config_path)
                    return
            
            # Try common OCIO config locations
            common_paths = [
                '/usr/share/color/nuke-default/config.ocio',
                '/opt/ocio/configs/nuke-default/config.ocio',
                Path.home() / '.ocio' / 'config.ocio',
            ]
            
            for path in common_paths:
                if Path(path).exists():
                    self.load_config(str(path))
                    return
            
            # Use built-in config as fallback
            self._create_basic_config()
            
        except Exception as e:
            logger.error(f"Failed to load default OCIO config: {e}")
    
    def _create_basic_config(self):
        """Create a basic OCIO configuration."""
        try:
            config = ocio.Config()
            
            # Add basic colorspaces
            # Linear colorspace
            linear_cs = ocio.ColorSpace(name='Linear')
            linear_cs.setDescription('Linear color space')
            linear_cs.setFamily('Linear')
            config.addColorSpace(linear_cs)
            
            # sRGB colorspace
            srgb_cs = ocio.ColorSpace(name='sRGB')
            srgb_cs.setDescription('sRGB color space')
            srgb_cs.setFamily('Input')
            
            # Add sRGB to Linear transform
            srgb_to_linear = ocio.ExponentTransform()
            srgb_to_linear.setValue([2.2, 2.2, 2.2, 1.0])
            srgb_cs.setTransform(srgb_to_linear, ocio.COLORSPACE_DIR_TO_REFERENCE)
            
            config.addColorSpace(srgb_cs)
            
            # Set roles
            config.setRole(ocio.ROLE_SCENE_LINEAR, 'Linear')
            config.setRole(ocio.ROLE_REFERENCE, 'Linear')
            config.setRole(ocio.ROLE_COLOR_TIMING, 'Linear')
            config.setRole(ocio.ROLE_COMPOSITING_LOG, 'Linear')
            config.setRole(ocio.ROLE_COLOR_PICKING, 'sRGB')
            config.setRole(ocio.ROLE_DATA, 'Linear')
            config.setRole(ocio.ROLE_DEFAULT, 'Linear')
            config.setRole(ocio.ROLE_MATTE_PAINT, 'Linear')
            config.setRole(ocio.ROLE_TEXTURE_PAINT, 'Linear')
            
            # Add display
            config.addDisplay('sRGB', 'Film', 'sRGB')
            config.setActiveDisplays('sRGB')
            config.setActiveViews('Film')
            
            self.ocio_config = config
            self.is_enabled = True
            
            logger.info("Created basic OCIO configuration")
            self.config_loaded.emit("Built-in Basic Config")
            
        except Exception as e:
            logger.error(f"Failed to create basic OCIO config: {e}")
            self.config_error.emit(f"Failed to create basic config: {e}")
    
    def load_config(self, config_path: str) -> bool:
        """Load OCIO configuration from file."""
        if not OCIO_AVAILABLE:
            logger.warning("OpenColorIO not available")
            return False
        
        try:
            config_path = Path(config_path)
            if not config_path.exists():
                raise FileNotFoundError(f"OCIO config not found: {config_path}")
            
            self.ocio_config = ocio.Config.CreateFromFile(str(config_path))
            self.is_enabled = True
            
            # Clear transform cache
            self._transform_cache.clear()
            
            # Setup default display transform
            self._setup_display_transform()
            
            logger.info(f"Loaded OCIO config: {config_path}")
            self.config_loaded.emit(str(config_path))
            return True
            
        except Exception as e:
            logger.error(f"Failed to load OCIO config {config_path}: {e}")
            self.config_error.emit(f"Failed to load config: {e}")
            self.is_enabled = False
            return False
    
    def _setup_display_transform(self):
        """Setup the display transform for thumbnails."""
        if not self.is_enabled or not self.ocio_config:
            return
        
        try:
            color_config = self.config_manager.get('color_management', {})
            display_colorspace = color_config.get('display_colorspace', 'sRGB')
            
            # Get available displays and views
            displays = self.ocio_config.getDisplays()
            if not displays:
                logger.warning("No displays available in OCIO config")
                return
            
            # Use first available display if specified one not found
            display = displays[0]
            if display_colorspace in displays:
                display = display_colorspace
            
            views = self.ocio_config.getViews(display)
            if not views:
                logger.warning(f"No views available for display {display}")
                return
            
            view = views[0]  # Use first available view
            
            # Create display transform
            self.display_transform = ocio.DisplayViewTransform()
            self.display_transform.setDisplay(display)
            self.display_transform.setView(view)
            
            logger.info(f"Setup display transform: {display}/{view}")
            
        except Exception as e:
            logger.error(f"Failed to setup display transform: {e}")
    
    def get_colorspaces(self) -> List[str]:
        """Get list of available colorspaces."""
        if not self.is_enabled or not self.ocio_config:
            return ['sRGB']  # Fallback
        
        try:
            colorspaces = []
            for i in range(self.ocio_config.getNumColorSpaces()):
                cs = self.ocio_config.getColorSpaceAtIndex(i)
                colorspaces.append(cs.getName())
            return colorspaces
        except Exception as e:
            logger.error(f"Failed to get colorspaces: {e}")
            return ['sRGB']
    
    def get_displays(self) -> List[str]:
        """Get list of available displays."""
        if not self.is_enabled or not self.ocio_config:
            return ['sRGB']
        
        try:
            return list(self.ocio_config.getDisplays())
        except Exception as e:
            logger.error(f"Failed to get displays: {e}")
            return ['sRGB']
    
    def get_views(self, display: str) -> List[str]:
        """Get list of available views for a display."""
        if not self.is_enabled or not self.ocio_config:
            return ['Film']
        
        try:
            return list(self.ocio_config.getViews(display))
        except Exception as e:
            logger.error(f"Failed to get views for display {display}: {e}")
            return ['Film']
    
    def transform_image(self, image: QImage, 
                       source_colorspace: str = 'sRGB',
                       target_colorspace: Optional[str] = None) -> QImage:
        """Transform image from source to target colorspace."""
        if not self.is_enabled or not self.ocio_config:
            return image  # Return unchanged if color management disabled
        
        try:
            # Convert QImage to numpy array
            width = image.width()
            height = image.height()
            
            # Convert to RGBA format if needed
            if image.format() != QImage.Format_RGBA8888:
                image = image.convertToFormat(QImage.Format_RGBA8888)
            
            # Get image data as numpy array
            ptr = image.constBits()
            arr = np.array(ptr).reshape(height, width, 4)
            
            # Convert to float and normalize
            float_arr = arr.astype(np.float32) / 255.0
            
            # Apply color transform
            if target_colorspace:
                # Transform between colorspaces
                transform_key = f"{source_colorspace}_to_{target_colorspace}"
                if transform_key not in self._transform_cache:
                    transform = ocio.ColorSpaceTransform()
                    transform.setSrc(source_colorspace)
                    transform.setDst(target_colorspace)
                    processor = self.ocio_config.getProcessor(transform)
                    self._transform_cache[transform_key] = processor
                else:
                    processor = self._transform_cache[transform_key]
            else:
                # Use display transform
                if self.display_transform:
                    self.display_transform.setSrc(source_colorspace)
                    processor = self.ocio_config.getProcessor(self.display_transform)
                else:
                    return image  # No transform available
            
            # Apply the transform
            cpu_processor = processor.getDefaultCPUProcessor()
            
            # Process RGB channels (leave alpha unchanged)
            rgb_data = float_arr[:, :, :3].copy()
            rgb_flat = rgb_data.reshape(-1, 3)
            
            # Apply transform
            cpu_processor.applyRGB(rgb_flat)
            
            # Reshape back and combine with alpha
            rgb_transformed = rgb_flat.reshape(height, width, 3)
            float_arr[:, :, :3] = rgb_transformed
            
            # Convert back to uint8
            uint8_arr = np.clip(float_arr * 255.0, 0, 255).astype(np.uint8)
            
            # Create new QImage
            result_image = QImage(uint8_arr.data, width, height, QImage.Format_RGBA8888)
            return result_image.copy()  # Make a copy to ensure data persistence
            
        except Exception as e:
            logger.error(f"Failed to transform image: {e}")
            return image  # Return original on error
    
    def transform_pixmap(self, pixmap: QPixmap,
                        source_colorspace: str = 'sRGB',
                        target_colorspace: Optional[str] = None) -> QPixmap:
        """Transform pixmap using color management."""
        if not self.is_enabled:
            return pixmap
        
        try:
            # Convert to QImage, transform, and convert back
            image = pixmap.toImage()
            transformed_image = self.transform_image(image, source_colorspace, target_colorspace)
            return QPixmap.fromImage(transformed_image)
        except Exception as e:
            logger.error(f"Failed to transform pixmap: {e}")
            return pixmap
    
    def is_available(self) -> bool:
        """Check if OpenColorIO is available and enabled."""
        return OCIO_AVAILABLE and self.is_enabled
    
    def get_config_info(self) -> Dict[str, Any]:
        """Get information about the current OCIO configuration."""
        if not self.is_enabled or not self.ocio_config:
            return {
                'enabled': False,
                'available': OCIO_AVAILABLE,
                'config_path': None,
                'colorspaces': [],
                'displays': [],
            }
        
        try:
            return {
                'enabled': True,
                'available': OCIO_AVAILABLE,
                'config_path': getattr(self.ocio_config, 'getSearchPath', lambda: 'Built-in')(),
                'colorspaces': self.get_colorspaces(),
                'displays': self.get_displays(),
                'description': getattr(self.ocio_config, 'getDescription', lambda: 'No description')(),
            }
        except Exception as e:
            logger.error(f"Failed to get config info: {e}")
            return {
                'enabled': False,
                'available': OCIO_AVAILABLE,
                'error': str(e)
            }
    
    def reload_config(self):
        """Reload the OCIO configuration."""
        color_config = self.config_manager.get('color_management', {})
        config_path = color_config.get('config_path', '')
        
        if config_path:
            self.load_config(config_path)
        else:
            self._try_default_config()
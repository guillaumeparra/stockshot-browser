"""
Theme utilities for dynamic color extraction and application.
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from PySide6.QtGui import QColor
from typing import Dict, Optional


class ThemeManager:
    """Manages dynamic theme colors and styling."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self._theme_colors = {}
            self._update_colors_from_xml()
    
    def _get_theme_path(self) -> Optional[Path]:
        """Get the theme file path from DEFAULT_CONFIG."""
        try:
            from ..config.defaults import DEFAULT_CONFIG
            theme_path = DEFAULT_CONFIG.get('ui', {}).get('theme_path', 'looks/qt_material/themes/dark_blue.xml')
            
            # Convert relative path to absolute path
            current_file = Path(__file__)
            project_root = current_file.parent.parent  # Go up to src/stockshot_browser
            full_path = project_root / theme_path
            
            return full_path
        except ImportError as e:
            # Fallback if defaults can't be imported
            current_file = Path(__file__)
            project_root = current_file.parent.parent
            return project_root / 'looks' / 'qt_material' / 'themes' / 'dark_blue.xml'
    
    def _update_colors_from_xml(self):
        """Update theme colors from XML theme file specified in DEFAULT_CONFIG."""
        theme_path = self._get_theme_path()
        
        if not theme_path or not theme_path.exists():
            # Fallback to environment variables if XML file doesn't exist
            self._update_colors_from_environment()
            return
        
        try:
            tree = ET.parse(theme_path)
            root = tree.getroot()
            
            # Parse color elements from XML
            for color_elem in root.findall('color'):
                color_name = color_elem.get('name')
                color_value = color_elem.text
                
                if color_name and color_value:
                    self._theme_colors[color_name] = color_value
                    
        except Exception as e:
            # Fallback to environment variables if XML parsing fails
            self._update_colors_from_environment()
    
    def _update_colors_from_environment(self):
        """Fallback: Update theme colors from environment variables set by qt_material."""
        color_keys = [
            'primaryColor',
            'primaryLightColor',
            'secondaryColor',
            'secondaryLightColor',
            'secondaryDarkColor',
            'primaryTextColor',
            'secondaryTextColor'
        ]
        
        for key in color_keys:
            env_key = f'QTMATERIAL_{key.upper()}'
            color_value = os.environ.get(env_key, '')
            if color_value:
                self._theme_colors[key] = color_value
    
    def get_color(self, color_name: str) -> Optional[str]:
        """Get theme color by name."""
        return self._theme_colors.get(color_name)
    
    def get_qcolor(self, color_name: str) -> Optional[QColor]:
        """Get theme color as QColor object."""
        hex_color = self.get_color(color_name)
        if hex_color:
            return QColor(hex_color)
        return None
    
    def get_rgba_color(self, color_name: str, alpha: float = 1.0) -> str:
        """Get theme color as RGBA string with specified alpha."""
        hex_color = self.get_color(color_name)
        if hex_color and hex_color.startswith('#'):
            # Convert hex to RGB
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            return [r, g, b, alpha]
        return [0, 0, 0, 0]
    
    def refresh_colors(self):
        """Refresh colors from XML theme file (call after theme change)."""
        self._update_colors_from_xml()
    
    def get_content_view_stylesheet(self) -> str:
        """Get stylesheet for content view with dynamic colors."""
        secondary_dark = self.get_color('secondaryDarkColor') or '#2b2b2b'
        
        return f"""
        QScrollArea {{
            background-color: {secondary_dark};
            border: none;
        }}
        QScrollArea > QWidget > QWidget {{
            background-color: {secondary_dark};
        }}
        QScrollArea QScrollBar:vertical {{
            background-color: {secondary_dark};
        }}
        QScrollArea QScrollBar:horizontal {{
            background-color: {secondary_dark};
        }}
        """
    
    def get_entity_widget_stylesheet(self, is_selected: bool = False) -> str:
        """Get stylesheet for entity widgets with dynamic colors - white text and smaller font sizes."""
        secondary_light = self.get_color('secondaryLightColor') or '#4f5b62'
        primary = self.get_color('primaryColor') or '#448aff'
        
        if is_selected:
            # Selected state: prominent border with white text and smaller fonts
            return f"""
            EntityThumbnailWidget, MultiEntityThumbnailWidget {{
                background-color: {secondary_light};
                border: 3px solid {primary};
                border-radius: 4px;
            }}
            EntityThumbnailWidget QLabel, MultiEntityThumbnailWidget QLabel {{
                color: white;
                font-size: 9px;
            }}
            EntityThumbnailWidget QLabel[objectName="name_label"], MultiEntityThumbnailWidget QLabel[objectName="name_label"] {{
                font-size: 10px;
                font-weight: bold;
            }}
            """
        else:
            # Normal state: transparent border with white text and smaller fonts
            return f"""
            EntityThumbnailWidget, MultiEntityThumbnailWidget {{
                background-color: {secondary_light};
                border: 1px solid transparent;
                border-radius: 4px;
            }}
            EntityThumbnailWidget:hover, MultiEntityThumbnailWidget:hover {{
                border: 1px solid {primary};
            }}
            EntityThumbnailWidget QLabel, MultiEntityThumbnailWidget QLabel {{
                color: white;
                font-size: 9px;
            }}
            EntityThumbnailWidget QLabel[objectName="name_label"], MultiEntityThumbnailWidget QLabel[objectName="name_label"] {{
                font-size: 10px;
                font-weight: bold;
            }}
            """
    
    def get_rubber_band_colors(self) -> Dict[str, str]:
        """Get rubber band selection colors."""
        primary = self.get_color('primaryColor') or '#448aff'
        primary_light = self.get_color('primaryLightColor') or '#83b9ff'
        return {
            'border': primary,
            'background': self.get_rgba_color('primaryLightColor', 30)
        }
    
    def get_input_field_stylesheet(self) -> str:
        """Get stylesheet for input fields and dropdowns with white text."""
        return """
        QLineEdit, QTextEdit, QPlainTextEdit {
            color: white;
        }
        QComboBox {
            color: white;
        }
        QComboBox QAbstractItemView {
            color: white;
            background-color: #2b2b2b;
        }
        QComboBox::drop-down {
            color: white;
        }
        """
    
    def get_button_stylesheet(self, min_width: int = None) -> str:
        """Get stylesheet for buttons with optional minimum width."""
        style = ""
        if min_width:
            style = f"QPushButton {{ min-width: {min_width}px; }}"
        return style
    
    def get_directory_tree_stylesheet(self) -> str:
        """Get stylesheet for directory tree with reduced item height."""
        return """
        QTreeWidget {
            color: white;
        }
        QTreeWidget::item {
            height: 18px;
            padding: 2px 4px;
            border: none;
        }
        QTreeWidget::item:selected {
            background-color: rgba(68, 138, 255, 0.3);
            color: white;
        }
        QTreeWidget::item:hover {
            background-color: rgba(68, 138, 255, 0.1);
        }
        """


# Global instance
theme_manager = ThemeManager()
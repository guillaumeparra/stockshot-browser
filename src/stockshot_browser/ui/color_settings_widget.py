"""
Color management settings widget for Stockshot Browser.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QCheckBox, QComboBox, QPushButton,
    QLineEdit, QFileDialog, QMessageBox, QTextEdit,
    QFormLayout, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)


class ColorSettingsWidget(QWidget):
    """Widget for configuring color management settings."""
    
    # Signals
    settings_changed = Signal()
    config_loaded = Signal(str)  # config_path
    
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self.config_manager = app_controller.config_manager
        self.color_manager = getattr(app_controller, 'color_manager', None)
        
        self._setup_ui()
        self._load_current_settings()
        self._connect_signals()
        
        logger.info("ColorSettingsWidget initialized")
    
    def _setup_ui(self):
        """Setup the color settings UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Title
        title_label = QLabel("Color Management Settings")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Status section
        self._create_status_section(layout)
        
        # Configuration section
        self._create_config_section(layout)
        
        # Display settings section
        self._create_display_section(layout)
        
        # Thumbnail settings section
        self._create_thumbnail_section(layout)
        
        # Action buttons
        self._create_action_buttons(layout)
        
        # Add stretch to push everything to top
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))
    
    def _create_status_section(self, parent_layout):
        """Create color management status section."""
        status_group = QGroupBox("Status")
        layout = QVBoxLayout(status_group)
        
        # Enable/disable checkbox
        self.enabled_checkbox = QCheckBox("Enable Color Management")
        self.enabled_checkbox.setToolTip("Enable OpenColorIO color management")
        layout.addWidget(self.enabled_checkbox)
        
        # Status info
        self.status_label = QLabel("Checking OpenColorIO availability...")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.status_label)
        
        # Config info display
        self.config_info = QTextEdit()
        self.config_info.setMaximumHeight(100)
        self.config_info.setReadOnly(True)
        self.config_info.setStyleSheet("background-color: #f5f5f5; border: 1px solid #ccc;")
        layout.addWidget(self.config_info)
        
        parent_layout.addWidget(status_group)
    
    def _create_config_section(self, parent_layout):
        """Create OCIO configuration section."""
        config_group = QGroupBox("OCIO Configuration")
        layout = QFormLayout(config_group)
        
        # Config file path
        config_layout = QHBoxLayout()
        self.config_path_edit = QLineEdit()
        self.config_path_edit.setPlaceholderText("Path to OCIO config file (leave empty for auto-detection)")
        config_layout.addWidget(self.config_path_edit)
        
        self.browse_config_button = QPushButton("Browse...")
        self.browse_config_button.clicked.connect(self._browse_config_file)
        config_layout.addWidget(self.browse_config_button)
        
        layout.addRow("Config File:", config_layout)
        
        # Auto-detection options
        self.auto_detect_checkbox = QCheckBox("Auto-detect OCIO configuration")
        self.auto_detect_checkbox.setToolTip("Try to find OCIO config from environment variables and common locations")
        layout.addRow(self.auto_detect_checkbox)
        
        self.fallback_builtin_checkbox = QCheckBox("Use built-in config as fallback")
        self.fallback_builtin_checkbox.setToolTip("Create a basic OCIO config if none is found")
        layout.addRow(self.fallback_builtin_checkbox)
        
        parent_layout.addWidget(config_group)
    
    def _create_display_section(self, parent_layout):
        """Create display settings section."""
        display_group = QGroupBox("Display Settings")
        layout = QFormLayout(display_group)
        
        # Default colorspace
        self.default_colorspace_combo = QComboBox()
        self.default_colorspace_combo.setToolTip("Default colorspace for media files")
        layout.addRow("Default Colorspace:", self.default_colorspace_combo)
        
        # Display colorspace
        self.display_colorspace_combo = QComboBox()
        self.display_colorspace_combo.setToolTip("Display colorspace for monitor output")
        layout.addRow("Display Colorspace:", self.display_colorspace_combo)
        
        parent_layout.addWidget(display_group)
    
    def _create_thumbnail_section(self, parent_layout):
        """Create thumbnail-specific settings."""
        thumbnail_group = QGroupBox("Thumbnail Settings")
        layout = QVBoxLayout(thumbnail_group)
        
        self.apply_to_thumbnails_checkbox = QCheckBox("Apply color management to thumbnails")
        self.apply_to_thumbnails_checkbox.setToolTip("Apply color transforms when displaying thumbnails")
        layout.addWidget(self.apply_to_thumbnails_checkbox)
        
        parent_layout.addWidget(thumbnail_group)
    
    def _create_action_buttons(self, parent_layout):
        """Create action buttons."""
        button_layout = QHBoxLayout()
        
        # Reload config button
        self.reload_button = QPushButton("Reload Configuration")
        self.reload_button.setToolTip("Reload OCIO configuration")
        self.reload_button.clicked.connect(self._reload_config)
        button_layout.addWidget(self.reload_button)
        
        # Test button
        self.test_button = QPushButton("Test Color Management")
        self.test_button.setToolTip("Test color management functionality")
        self.test_button.clicked.connect(self._test_color_management)
        button_layout.addWidget(self.test_button)
        
        button_layout.addStretch()
        
        # Apply button
        self.apply_button = QPushButton("Apply Settings")
        self.apply_button.setToolTip("Apply and save color management settings")
        self.apply_button.clicked.connect(self._apply_settings)
        button_layout.addWidget(self.apply_button)
        
        parent_layout.addLayout(button_layout)
    
    def _connect_signals(self):
        """Connect widget signals."""
        # Connect color manager signals if available
        if self.color_manager:
            self.color_manager.config_loaded.connect(self._on_config_loaded)
            self.color_manager.config_error.connect(self._on_config_error)
        
        # Connect UI signals
        self.enabled_checkbox.toggled.connect(self._on_enabled_changed)
        self.config_path_edit.textChanged.connect(self._on_config_path_changed)
    
    def _load_current_settings(self):
        """Load current color management settings."""
        color_config = self.config_manager.get('color_management', {})
        
        # Load basic settings
        self.enabled_checkbox.setChecked(color_config.get('enabled', False))
        self.config_path_edit.setText(color_config.get('config_path', ''))
        self.auto_detect_checkbox.setChecked(color_config.get('auto_detect_config', True))
        self.fallback_builtin_checkbox.setChecked(color_config.get('fallback_to_builtin', True))
        self.apply_to_thumbnails_checkbox.setChecked(color_config.get('apply_to_thumbnails', True))
        
        # Update status
        self._update_status()
        
        # Load colorspaces if color manager is available
        if self.color_manager and self.color_manager.is_available():
            self._update_colorspace_combos()
        else:
            # Add default options
            default_colorspaces = ['sRGB', 'Linear', 'Rec.709']
            self.default_colorspace_combo.addItems(default_colorspaces)
            self.display_colorspace_combo.addItems(default_colorspaces)
            
            # Set current values
            self.default_colorspace_combo.setCurrentText(color_config.get('default_colorspace', 'sRGB'))
            self.display_colorspace_combo.setCurrentText(color_config.get('display_colorspace', 'sRGB'))
    
    def _update_status(self):
        """Update color management status display."""
        if not self.color_manager:
            self.status_label.setText("❌ Color Manager not available")
            self.status_label.setStyleSheet("color: red;")
            return
        
        if not self.color_manager.is_available():
            self.status_label.setText("❌ OpenColorIO not available or not enabled")
            self.status_label.setStyleSheet("color: red;")
        else:
            self.status_label.setText("✅ OpenColorIO available and enabled")
            self.status_label.setStyleSheet("color: green;")
        
        # Update config info
        if self.color_manager:
            config_info = self.color_manager.get_config_info()
            info_text = []
            
            if config_info.get('enabled'):
                info_text.append(f"Status: Enabled")
                info_text.append(f"Config: {config_info.get('config_path', 'Built-in')}")
                info_text.append(f"Colorspaces: {len(config_info.get('colorspaces', []))}")
                info_text.append(f"Displays: {len(config_info.get('displays', []))}")
                if config_info.get('description'):
                    info_text.append(f"Description: {config_info['description']}")
            else:
                info_text.append("Status: Disabled")
                if config_info.get('error'):
                    info_text.append(f"Error: {config_info['error']}")
            
            self.config_info.setPlainText('\n'.join(info_text))
    
    def _update_colorspace_combos(self):
        """Update colorspace combo boxes with available options."""
        if not self.color_manager or not self.color_manager.is_available():
            return
        
        # Get available colorspaces
        colorspaces = self.color_manager.get_colorspaces()
        displays = self.color_manager.get_displays()
        
        # Update default colorspace combo
        current_default = self.default_colorspace_combo.currentText()
        self.default_colorspace_combo.clear()
        self.default_colorspace_combo.addItems(colorspaces)
        if current_default in colorspaces:
            self.default_colorspace_combo.setCurrentText(current_default)
        
        # Update display colorspace combo
        current_display = self.display_colorspace_combo.currentText()
        self.display_colorspace_combo.clear()
        self.display_colorspace_combo.addItems(displays)
        if current_display in displays:
            self.display_colorspace_combo.setCurrentText(current_display)
    
    @Slot(bool)
    def _on_enabled_changed(self, enabled: bool):
        """Handle enable/disable change."""
        # Enable/disable other controls
        self.config_path_edit.setEnabled(enabled)
        self.browse_config_button.setEnabled(enabled)
        self.auto_detect_checkbox.setEnabled(enabled)
        self.fallback_builtin_checkbox.setEnabled(enabled)
        self.default_colorspace_combo.setEnabled(enabled)
        self.display_colorspace_combo.setEnabled(enabled)
        self.apply_to_thumbnails_checkbox.setEnabled(enabled)
        self.reload_button.setEnabled(enabled)
        self.test_button.setEnabled(enabled)
    
    @Slot(str)
    def _on_config_path_changed(self, path: str):
        """Handle config path change."""
        # Enable/disable auto-detect based on whether path is specified
        has_path = bool(path.strip())
        self.auto_detect_checkbox.setEnabled(not has_path)
    
    @Slot()
    def _browse_config_file(self):
        """Browse for OCIO config file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select OCIO Configuration File",
            str(Path.home()),
            "OCIO Config Files (*.ocio);;All Files (*)"
        )
        
        if file_path:
            self.config_path_edit.setText(file_path)
    
    @Slot()
    def _reload_config(self):
        """Reload OCIO configuration."""
        if not self.color_manager:
            QMessageBox.warning(self, "Error", "Color manager not available")
            return
        
        config_path = self.config_path_edit.text().strip()
        if config_path:
            success = self.color_manager.load_config(config_path)
            if success:
                self._update_status()
                self._update_colorspace_combos()
                QMessageBox.information(self, "Success", f"Configuration loaded: {config_path}")
            else:
                QMessageBox.warning(self, "Error", f"Failed to load configuration: {config_path}")
        else:
            # Reload with auto-detection
            self.color_manager.reload_config()
            self._update_status()
            self._update_colorspace_combos()
            QMessageBox.information(self, "Success", "Configuration reloaded")
    
    @Slot()
    def _test_color_management(self):
        """Test color management functionality."""
        if not self.color_manager or not self.color_manager.is_available():
            QMessageBox.warning(self, "Error", "Color management not available")
            return
        
        try:
            # Create a simple test image and transform it
            from PySide6.QtGui import QPixmap, QImage
            
            # Create a test image (simple gradient)
            test_image = QImage(100, 100, QImage.Format_RGB888)
            test_image.fill(Qt.red)
            
            test_pixmap = QPixmap.fromImage(test_image)
            
            # Try to transform it
            transformed = self.color_manager.transform_pixmap(test_pixmap, 'sRGB')
            
            if transformed:
                QMessageBox.information(self, "Success", "Color management test passed!")
            else:
                QMessageBox.warning(self, "Error", "Color management test failed")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Color management test failed: {e}")
    
    @Slot()
    def _apply_settings(self):
        """Apply and save color management settings."""
        try:
            # Collect settings
            settings = {
                'enabled': self.enabled_checkbox.isChecked(),
                'config_path': self.config_path_edit.text().strip(),
                'auto_detect_config': self.auto_detect_checkbox.isChecked(),
                'fallback_to_builtin': self.fallback_builtin_checkbox.isChecked(),
                'default_colorspace': self.default_colorspace_combo.currentText(),
                'display_colorspace': self.display_colorspace_combo.currentText(),
                'apply_to_thumbnails': self.apply_to_thumbnails_checkbox.isChecked(),
            }
            
            # Save to configuration
            for key, value in settings.items():
                self.config_manager.set(f'color_management.{key}', value, persist=True)
            
            # Reload color manager if enabled
            if settings['enabled'] and self.color_manager:
                self.color_manager.reload_config()
                self._update_status()
                self._update_colorspace_combos()
            
            # Emit signal
            self.settings_changed.emit()
            
            QMessageBox.information(self, "Success", "Color management settings applied and saved")
            
        except Exception as e:
            logger.error(f"Error applying color settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {e}")
    
    @Slot(str)
    def _on_config_loaded(self, config_path: str):
        """Handle config loaded signal."""
        self._update_status()
        self._update_colorspace_combos()
        self.config_loaded.emit(config_path)
    
    @Slot(str)
    def _on_config_error(self, error_message: str):
        """Handle config error signal."""
        self._update_status()
        QMessageBox.warning(self, "Configuration Error", error_message)
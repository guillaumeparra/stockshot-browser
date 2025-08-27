"""
Search and filtering widget for Stockshot Browser.
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QComboBox, QLabel, QCheckBox,
    QGroupBox, QSpinBox, QDoubleSpinBox, QDateEdit,
    QScrollArea, QFrame, QGridLayout, QButtonGroup,
    QRadioButton
)
from PySide6.QtGui import QIcon

from .theme_utils import theme_manager

logger = logging.getLogger(__name__)


class SearchWidget(QWidget):
    """Advanced search and filtering widget."""
    
    # Signals
    search_requested = Signal(dict)  # Search criteria
    filter_changed = Signal(dict)  # Filter criteria
    search_cleared = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.connect_signals()
        
        # Debounce timer for live search
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)
        
    def setup_ui(self):
        """Setup the search widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Set minimum height for better visibility
        self.setMinimumHeight(60)
        
        # Apply theme-based styling
        self.apply_theme_styles()
        
        # Combined horizontal layout: filters first, then search
        self.create_combined_filter_search_layout(layout)
        
        # Search results info
        self.results_label = QLabel("Ready to search")
        self.results_label.setStyleSheet("color: #999; font-style: italic; font-size: 11px; padding: 2px;")
        layout.addWidget(self.results_label)
    
    def apply_theme_styles(self):
        """Apply theme-based styling to the widget."""
        # Apply input field styling for white text
        input_style = theme_manager.get_input_field_stylesheet()
        self.setStyleSheet(input_style)
    
    def create_combined_filter_search_layout(self, parent_layout):
        """Create combined horizontal layout with filters first, then search on the right."""
        # Main horizontal layout containing filters and search
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)
        
        # Filters section (left side)
        self.create_file_type_filters_horizontal(main_layout)
        
        # Separator
        separator = QLabel("|")
        separator.setStyleSheet("color: #888888; font-size: 16px; margin: 0 10px; font-weight: bold;")
        main_layout.addWidget(separator)
        
        # Search section (right side)
        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search files by name, path, or tag...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMaximumWidth(300)
        # Apply white text styling
        input_style = theme_manager.get_input_field_stylesheet()
        self.search_input.setStyleSheet(input_style)
        main_layout.addWidget(self.search_input)
        
        # Search type dropdown
        self.search_type = QComboBox()
        self.search_type.addItems(["Name", "Path", "All Fields"])
        self.search_type.setCurrentText("All Fields")
        self.search_type.setMaximumWidth(100)
        # Apply white text styling with white dropdown text
        dropdown_style = input_style + """
        QComboBox {
            color: white;
        }
        QComboBox QAbstractItemView {
            color: white;
            selection-background-color: rgba(68, 138, 255, 0.3);
        }
        """
        self.search_type.setStyleSheet(dropdown_style)
        main_layout.addWidget(self.search_type)
        
        # Clear button
        self.clear_button = QPushButton("Clear")
        self.clear_button.setMinimumWidth(80)
        button_style = theme_manager.get_button_stylesheet(min_width=80)
        self.clear_button.setStyleSheet(button_style)
        main_layout.addWidget(self.clear_button)
        
        main_layout.addStretch()
        
        # Add to parent layout
        parent_layout.addLayout(main_layout)
    
    def create_quick_search(self, parent_layout):
        """Legacy method - now handled by create_combined_filter_search_layout."""
        pass
    
    def create_advanced_filters(self, parent_layout):
        """Legacy method - now handled by create_combined_filter_search_layout."""
        pass
    
    def create_file_type_filters_horizontal(self, parent_layout):
        """Create horizontal file type filter options as toggle buttons."""
        # Toggle button styling for filters
        toggle_button_style = """
        QPushButton {
            background-color: #4f5b62;
            color: white;
            border: 2px solid transparent;
            border-radius: 6px;
            padding: 6px 12px;
            font-weight: bold;
            font-size: 11px;
            min-height: 20px;
        }
        QPushButton:hover {
            background-color: #5a6870;
            border-color: #448aff;
        }
        QPushButton:checked {
            background-color: #448aff;
            border-color: #83b9ff;
        }
        QPushButton:pressed {
            background-color: #357ae8;
        }
        """
        
        # File type toggle buttons
        self.type_video = QPushButton("Videos")
        self.type_video.setCheckable(True)
        self.type_video.setChecked(True)
        self.type_video.setStyleSheet(toggle_button_style)
        parent_layout.addWidget(self.type_video)
        
        self.type_sequence = QPushButton("Sequences")
        self.type_sequence.setCheckable(True)
        self.type_sequence.setChecked(True)
        self.type_sequence.setStyleSheet(toggle_button_style)
        parent_layout.addWidget(self.type_sequence)
        
        self.type_image = QPushButton("Images")
        self.type_image.setCheckable(True)
        self.type_image.setChecked(True)
        self.type_image.setStyleSheet(toggle_button_style)
        parent_layout.addWidget(self.type_image)
        
        # Separator
        separator = QLabel("|")
        separator.setStyleSheet("color: #888888; font-size: 16px; margin: 0 10px; font-weight: bold;")
        parent_layout.addWidget(separator)
        
        # Favorites filters with SVG icons as toggle buttons
        from pathlib import Path
        
        # User favorites toggle button with SVG icon
        self.user_favorites_only = QPushButton("User Favorites")
        self.user_favorites_only.setCheckable(True)
        self.user_favorites_only.setChecked(False)
        self.user_favorites_only.setStyleSheet(toggle_button_style)
        user_icon_path = Path(__file__).parent.parent / "resources" / "icon_user_favorite.svg"
        if user_icon_path.exists():
            user_icon = QIcon(str(user_icon_path))
            self.user_favorites_only.setIcon(user_icon)
        parent_layout.addWidget(self.user_favorites_only)
        
        # Project favorites toggle button with SVG icon
        self.project_favorites_only = QPushButton("Project Favorites")
        self.project_favorites_only.setCheckable(True)
        self.project_favorites_only.setChecked(False)
        self.project_favorites_only.setStyleSheet(toggle_button_style)
        project_icon_path = Path(__file__).parent.parent / "resources" / "icon_project_favorite.svg"
        if project_icon_path.exists():
            project_icon = QIcon(str(project_icon_path))
            self.project_favorites_only.setIcon(project_icon)
        parent_layout.addWidget(self.project_favorites_only)
    
    def create_size_filter_compact(self, parent_layout):
        """Create compact size filter."""
        # Separator
        separator = QLabel("|")
        separator.setStyleSheet("color: #666;")
        parent_layout.addWidget(separator)
        
        # Size filter
        size_checkbox_style = """
            QCheckBox {
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox:hover {
                color: #cccccc;
            }
            QCheckBox:checked {
                color: #0078d4;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #555555;
                border: 2px solid #777777;
                border-radius: 3px;
            }
            QCheckBox::indicator:unchecked:hover {
                background-color: #666666;
                border-color: #888888;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border: 2px solid #0078d4;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #1084e0;
            }
        """
        self.size_enabled = QCheckBox("Size (MB):")
        self.size_enabled.setStyleSheet(size_checkbox_style)
        parent_layout.addWidget(self.size_enabled)
        
        self.size_min = QDoubleSpinBox()
        self.size_min.setRange(0, 100000)
        self.size_min.setValue(0)
        self.size_min.setEnabled(False)
        self.size_min.setMaximumWidth(80)
        self.size_min.setDecimals(1)
        parent_layout.addWidget(self.size_min)
        
        dash_label = QLabel("-")
        parent_layout.addWidget(dash_label)
        
        self.size_max = QDoubleSpinBox()
        self.size_max.setRange(0, 100000)
        self.size_max.setValue(10000)
        self.size_max.setEnabled(False)
        self.size_max.setMaximumWidth(80)
        self.size_max.setDecimals(1)
        parent_layout.addWidget(self.size_max)
        
        # Connect enable checkbox
        self.size_enabled.toggled.connect(self.size_min.setEnabled)
        self.size_enabled.toggled.connect(self.size_max.setEnabled)
    
    def create_date_filter_compact(self, parent_layout):
        """Create compact date filter."""
        # Separator
        separator = QLabel("|")
        separator.setStyleSheet("color: #666;")
        parent_layout.addWidget(separator)
        
        # Date filter
        date_checkbox_style = """
            QCheckBox {
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox:hover {
                color: #cccccc;
            }
            QCheckBox:checked {
                color: #0078d4;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #555555;
                border: 2px solid #777777;
                border-radius: 3px;
            }
            QCheckBox::indicator:unchecked:hover {
                background-color: #666666;
                border-color: #888888;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border: 2px solid #0078d4;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #1084e0;
            }
        """
        self.date_enabled = QCheckBox("Date:")
        self.date_enabled.setStyleSheet(date_checkbox_style)
        parent_layout.addWidget(self.date_enabled)
        
        # Date range options
        self.date_option = QComboBox()
        self.date_option.addItems([
            "Last 24h",
            "Last 7d",
            "Last 30d",
            "Last year"
        ])
        self.date_option.setEnabled(False)
        self.date_option.setMaximumWidth(80)
        parent_layout.addWidget(self.date_option)
        
        # Hidden custom date range (simplified)
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setEnabled(False)
        self.date_from.setVisible(False)
        
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setEnabled(False)
        self.date_to.setVisible(False)
        
        # Connect signals
        self.date_enabled.toggled.connect(self.date_option.setEnabled)
        self.date_option.currentTextChanged.connect(self.on_date_option_changed)
    
    def create_resolution_filter_compact(self, parent_layout):
        """Create compact resolution filter."""
        # Resolution filter checkbox
        resolution_checkbox_style = """
            QCheckBox {
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox:hover {
                color: #cccccc;
            }
            QCheckBox:checked {
                color: #0078d4;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #555555;
                border: 2px solid #777777;
                border-radius: 3px;
            }
            QCheckBox::indicator:unchecked:hover {
                background-color: #666666;
                border-color: #888888;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border: 2px solid #0078d4;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #1084e0;
            }
        """
        
        combobox_style = """
            QComboBox {
                background-color: #2d2d2d;
                border: 2px solid #555555;
                border-radius: 6px;
                padding: 6px 8px;
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
                min-height: 20px;
            }
            QComboBox:focus {
                border-color: #0078d4;
                background-color: #3d3d3d;
            }
            QComboBox:hover {
                border-color: #777777;
                background-color: #3d3d3d;
            }
            QComboBox:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border-color: #333333;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
                margin-right: 6px;
            }
            QComboBox::down-arrow:disabled {
                border-top-color: #666666;
            }
        """
        
        self.resolution_enabled = QCheckBox("Resolution:")
        self.resolution_enabled.setStyleSheet(resolution_checkbox_style)
        parent_layout.addWidget(self.resolution_enabled)
        
        # Common resolutions
        self.resolution_option = QComboBox()
        self.resolution_option.addItems([
            "Any",
            "HD",
            "FHD",
            "2K",
            "4K"
        ])
        self.resolution_option.setEnabled(False)
        self.resolution_option.setMaximumWidth(70)
        self.resolution_option.setStyleSheet(combobox_style)
        parent_layout.addWidget(self.resolution_option)
        
        # Hidden custom resolution (simplified)
        self.width_min = QSpinBox()
        self.width_min.setRange(0, 10000)
        self.width_min.setEnabled(False)
        self.width_min.setVisible(False)
        
        self.height_min = QSpinBox()
        self.height_min.setRange(0, 10000)
        self.height_min.setEnabled(False)
        self.height_min.setVisible(False)
        
        # Connect signals
        self.resolution_enabled.toggled.connect(self.resolution_option.setEnabled)
        self.resolution_option.currentTextChanged.connect(self.on_resolution_option_changed)
    
    
    def connect_signals(self):
        """Connect widget signals."""
        # Quick search
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.search_input.returnPressed.connect(self.perform_search)
        self.clear_button.clicked.connect(self.clear_search)
        
        # Search type change
        self.search_type.currentTextChanged.connect(self.on_search_type_changed)
        
        # Connect toggle button filter controls to auto-apply
        self.type_video.toggled.connect(self.on_filter_changed)
        self.type_sequence.toggled.connect(self.on_filter_changed)
        self.type_image.toggled.connect(self.on_filter_changed)
        self.user_favorites_only.toggled.connect(self.on_filter_changed)
        self.project_favorites_only.toggled.connect(self.on_filter_changed)
        # Removed filters: format, size, date, resolution
    
    @Slot(str)
    def on_search_text_changed(self, text: str):
        """Handle search text change for live search."""
        # Start/restart timer for debounced search
        self.search_timer.stop()
        self.search_timer.start(300)  # 300ms delay for faster response
    
    @Slot(str)
    def on_search_type_changed(self, search_type: str):
        """Handle search type change."""
        self.perform_search()
    
    @Slot()
    def on_filter_changed(self):
        """Handle filter change - auto-apply filters."""
        self.perform_search()
    
    @Slot(str)
    def on_filter_text_changed(self, text: str):
        """Handle filter text change with debounce."""
        self.search_timer.stop()
        self.search_timer.start(300)  # 300ms delay
    
    @Slot()
    def perform_search(self):
        """Perform the search with current criteria."""
        criteria = self.get_search_criteria()
        
        if criteria:
            self.search_requested.emit(criteria)
            logger.info(f"Search requested with criteria: {criteria}")
        else:
            self.clear_search()
    
    @Slot()
    def clear_search(self):
        """Clear all search criteria."""
        self.search_input.clear()
        self.reset_filters()
        self.search_cleared.emit()
        self.results_label.setText("Search cleared")
    
    def reset_filters(self):
        """Reset all filter values to defaults."""
        # File types
        self.type_video.setChecked(True)
        self.type_sequence.setChecked(True)
        self.type_image.setChecked(True)
        self.user_favorites_only.setChecked(False)
        self.project_favorites_only.setChecked(False)
        
        # Removed filters: format, size, date, resolution - no longer exist
        
    
    def get_search_criteria(self) -> Dict[str, Any]:
        """Get current search criteria as dictionary."""
        criteria = {}
        
        # Quick search
        search_text = self.search_input.text().strip()
        if search_text:
            criteria['text'] = search_text
            criteria['search_type'] = self.search_type.currentText().lower()
        
        # Advanced filters (always active now)
        # File types
        file_types = []
        if self.type_video.isChecked():
            file_types.append('video')
        if self.type_sequence.isChecked():
            file_types.append('sequence')
        if self.type_image.isChecked():
            file_types.append('image')
        if file_types:
            criteria['file_types'] = file_types
        
        # Favorites filters
        if self.user_favorites_only.isChecked():
            criteria['user_favorites_only'] = True
        if self.project_favorites_only.isChecked():
            criteria['project_favorites_only'] = True
        
        # Removed filters: formats, size, date, resolution - no longer exist
        
        return criteria
    
    
    @Slot(str)
    def on_date_option_changed(self, option: str):
        """Handle date option change."""
        show_custom = (option == "Custom range")
        self.date_from.setVisible(show_custom)
        self.date_to.setVisible(show_custom)
        if show_custom:
            self.date_from.setEnabled(self.date_enabled.isChecked())
            self.date_to.setEnabled(self.date_enabled.isChecked())
    
    @Slot(str)
    def on_resolution_option_changed(self, option: str):
        """Handle resolution option change."""
        show_custom = (option == "Custom")
        self.width_min.setEnabled(show_custom and self.resolution_enabled.isChecked())
        self.height_min.setEnabled(show_custom and self.resolution_enabled.isChecked())
    
    def update_results_info(self, count: int, total: int):
        """Update search results information."""
        if count == total:
            self.results_label.setText(f"Showing all {total} items")
        else:
            self.results_label.setText(f"Found {count} of {total} items")
    
    def restore_search_state(self, criteria: Dict[str, Any]):
        """Restore search widget state from criteria."""
        # Block signals to prevent triggering search during restoration
        self.blockSignals(True)
        
        try:
            # Clear current state first
            self.reset_filters()
            
            # Restore text search
            if 'text' in criteria:
                self.search_input.setText(criteria['text'])
            
            if 'search_type' in criteria:
                search_type = criteria['search_type']
                if search_type == 'name':
                    self.search_type.setCurrentText('Name')
                elif search_type == 'path':
                    self.search_type.setCurrentText('Path')
                else:
                    self.search_type.setCurrentText('All Fields')
            
            # Restore file type filters
            if 'file_types' in criteria:
                file_types = criteria['file_types']
                self.type_video.setChecked('video' in file_types)
                self.type_sequence.setChecked('sequence' in file_types)
                self.type_image.setChecked('image' in file_types)
            
            # Restore favorites filters
            if 'user_favorites_only' in criteria:
                self.user_favorites_only.setChecked(criteria['user_favorites_only'])
            if 'project_favorites_only' in criteria:
                self.project_favorites_only.setChecked(criteria['project_favorites_only'])
            
            # Backward compatibility with old 'favorites_only' key
            if 'favorites_only' in criteria and criteria['favorites_only']:
                self.user_favorites_only.setChecked(True)
            
            # Removed filters: formats, size, date, resolution
            
        finally:
            # Re-enable signals
            self.blockSignals(False)
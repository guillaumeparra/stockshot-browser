"""
Export dialog for metadata and project data in Stockshot Browser.
"""

import logging
from pathlib import Path
from typing import Optional, List, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QCheckBox, QComboBox, QPushButton,
    QLineEdit, QFileDialog, QProgressBar, QTextEdit,
    QFormLayout, QSpacerItem, QSizePolicy, QMessageBox,
    QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, Signal, Slot, QThread, QTimer
from PySide6.QtGui import QFont

from ..core.metadata_exporter import MetadataExporter

logger = logging.getLogger(__name__)


class ExportWorker(QThread):
    """Worker thread for export operations."""
    
    # Signals
    progress_updated = Signal(int, str)  # progress, status
    export_completed = Signal(bool, str)  # success, message
    
    def __init__(self, exporter: MetadataExporter, export_params: dict):
        super().__init__()
        self.exporter = exporter
        self.export_params = export_params
    
    def run(self):
        """Run the export operation."""
        try:
            self.progress_updated.emit(10, "Preparing export...")
            
            output_path = Path(self.export_params['output_path'])
            format_type = self.export_params['format']
            export_type = self.export_params['export_type']
            
            self.progress_updated.emit(30, "Collecting data...")
            
            success = False
            if export_type == 'project':
                success = self.exporter.export_project_data(
                    output_path=output_path,
                    format=format_type,
                    project_name=self.export_params.get('project_name'),
                    include_thumbnails=self.export_params.get('include_thumbnails', False),
                    include_favorites=self.export_params.get('include_favorites', True),
                    include_tags=self.export_params.get('include_tags', True)
                )
            elif export_type == 'entities':
                entities = self.export_params.get('entities', [])
                success = self.exporter.export_entity_list(
                    entities=entities,
                    output_path=output_path,
                    format=format_type
                )
            
            self.progress_updated.emit(90, "Finalizing export...")
            
            if success:
                self.progress_updated.emit(100, "Export completed successfully")
                self.export_completed.emit(True, f"Export completed: {output_path}")
            else:
                self.export_completed.emit(False, "Export failed")
                
        except Exception as e:
            logger.error(f"Export worker error: {e}")
            self.export_completed.emit(False, f"Export error: {e}")


class ExportDialog(QDialog):
    """Dialog for exporting metadata and project data."""
    
    def __init__(self, app_controller, entities: Optional[List[Any]] = None):
        super().__init__()
        self.app_controller = app_controller
        self.entities = entities or []
        
        # Create exporter
        self.exporter = MetadataExporter(
            config_manager=app_controller.config_manager,
            database_manager=app_controller.database_manager
        )
        
        # Worker thread
        self.export_worker: Optional[ExportWorker] = None
        
        self._setup_ui()
        self._load_export_summary()
        self._connect_signals()
        
        logger.info("ExportDialog initialized")
    
    def _setup_ui(self):
        """Setup the export dialog UI."""
        self.setWindowTitle("Export Metadata")
        self.setModal(True)
        self.resize(600, 700)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Title
        title_label = QLabel("Export Project Data")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Export type section
        self._create_export_type_section(layout)
        
        # Format selection section
        self._create_format_section(layout)
        
        # Options section
        self._create_options_section(layout)
        
        # Output section
        self._create_output_section(layout)
        
        # Summary section
        self._create_summary_section(layout)
        
        # Progress section
        self._create_progress_section(layout)
        
        # Buttons
        self._create_buttons(layout)
        
        # Add stretch
        layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
    
    def _create_export_type_section(self, parent_layout):
        """Create export type selection section."""
        group = QGroupBox("Export Type")
        layout = QVBoxLayout(group)
        
        # Radio buttons for export type
        self.export_type_group = QButtonGroup()
        
        self.project_radio = QRadioButton("Complete Project Data")
        self.project_radio.setToolTip("Export all entities, metadata, favorites, and tags")
        self.project_radio.setChecked(True)
        self.export_type_group.addButton(self.project_radio, 0)
        layout.addWidget(self.project_radio)
        
        self.entities_radio = QRadioButton(f"Selected Entities ({len(self.entities)} items)")
        self.entities_radio.setToolTip("Export only the selected entities")
        self.entities_radio.setEnabled(len(self.entities) > 0)
        self.export_type_group.addButton(self.entities_radio, 1)
        layout.addWidget(self.entities_radio)
        
        parent_layout.addWidget(group)
    
    def _create_format_section(self, parent_layout):
        """Create format selection section."""
        group = QGroupBox("Export Format")
        layout = QFormLayout(group)
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(["JSON", "CSV", "XML"])
        self.format_combo.setCurrentText("JSON")
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        layout.addRow("Format:", self.format_combo)
        
        # Format description
        self.format_description = QLabel("JSON: Complete data with full structure and metadata")
        self.format_description.setStyleSheet("color: #666; font-style: italic;")
        self.format_description.setWordWrap(True)
        layout.addRow(self.format_description)
        
        parent_layout.addWidget(group)
    
    def _create_options_section(self, parent_layout):
        """Create export options section."""
        group = QGroupBox("Export Options")
        layout = QVBoxLayout(group)
        
        # Project selection (only for project export)
        project_layout = QHBoxLayout()
        project_layout.addWidget(QLabel("Project:"))
        self.project_combo = QComboBox()
        self.project_combo.addItems(["All Projects", "Current Project"])
        project_layout.addWidget(self.project_combo)
        project_layout.addStretch()
        layout.addLayout(project_layout)
        
        # Include options
        self.include_thumbnails = QCheckBox("Include thumbnail information")
        self.include_thumbnails.setToolTip("Include thumbnail paths and generation data")
        layout.addWidget(self.include_thumbnails)
        
        self.include_favorites = QCheckBox("Include favorites")
        self.include_favorites.setChecked(True)
        self.include_favorites.setToolTip("Include user favorites data")
        layout.addWidget(self.include_favorites)
        
        self.include_tags = QCheckBox("Include tags")
        self.include_tags.setChecked(True)
        self.include_tags.setToolTip("Include entity tags and labels")
        layout.addWidget(self.include_tags)
        
        parent_layout.addWidget(group)
    
    def _create_output_section(self, parent_layout):
        """Create output file selection section."""
        group = QGroupBox("Output File")
        layout = QFormLayout(group)
        
        # Output path
        output_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select output file path...")
        output_layout.addWidget(self.output_path_edit)
        
        self.browse_output_button = QPushButton("Browse...")
        self.browse_output_button.clicked.connect(self._browse_output_file)
        output_layout.addWidget(self.browse_output_button)
        
        layout.addRow("Output File:", output_layout)
        
        parent_layout.addWidget(group)
    
    def _create_summary_section(self, parent_layout):
        """Create export summary section."""
        group = QGroupBox("Export Summary")
        layout = QVBoxLayout(group)
        
        self.summary_text = QTextEdit()
        self.summary_text.setMaximumHeight(120)
        self.summary_text.setReadOnly(True)
        self.summary_text.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ddd;")
        layout.addWidget(self.summary_text)
        
        parent_layout.addWidget(group)
    
    def _create_progress_section(self, parent_layout):
        """Create progress section."""
        group = QGroupBox("Export Progress")
        layout = QVBoxLayout(group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #666; font-style: italic;")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)
        
        parent_layout.addWidget(group)
    
    def _create_buttons(self, parent_layout):
        """Create dialog buttons."""
        button_layout = QHBoxLayout()
        
        # Preview button
        self.preview_button = QPushButton("Preview Export")
        self.preview_button.setToolTip("Preview what will be exported")
        self.preview_button.clicked.connect(self._preview_export)
        button_layout.addWidget(self.preview_button)
        
        button_layout.addStretch()
        
        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        # Export button
        self.export_button = QPushButton("Export")
        self.export_button.setDefault(True)
        self.export_button.clicked.connect(self._start_export)
        button_layout.addWidget(self.export_button)
        
        parent_layout.addLayout(button_layout)
    
    def _connect_signals(self):
        """Connect dialog signals."""
        self.project_radio.toggled.connect(self._on_export_type_changed)
        self.entities_radio.toggled.connect(self._on_export_type_changed)
    
    def _load_export_summary(self):
        """Load and display export summary."""
        try:
            summary = self.exporter.get_export_summary()
            
            summary_text = []
            summary_text.append(f"Available for export:")
            summary_text.append(f"• Entities: {summary['entities']}")
            summary_text.append(f"• Metadata records: {summary['metadata_records']}")
            summary_text.append(f"• Thumbnails: {summary['thumbnails']}")
            summary_text.append(f"• Favorites: {summary['favorites']}")
            summary_text.append(f"• Tags: {summary['tags']}")
            
            if self.entities:
                summary_text.append(f"\nSelected entities: {len(self.entities)}")
            
            self.summary_text.setPlainText('\n'.join(summary_text))
            
        except Exception as e:
            logger.error(f"Error loading export summary: {e}")
            self.summary_text.setPlainText(f"Error loading summary: {e}")
    
    @Slot(str)
    def _on_format_changed(self, format_name: str):
        """Handle format selection change."""
        descriptions = {
            "JSON": "JSON: Complete data with full structure and metadata",
            "CSV": "CSV: Tabular format, entities only (best for spreadsheets)",
            "XML": "XML: Structured format with full data hierarchy"
        }
        
        self.format_description.setText(descriptions.get(format_name, ""))
        
        # Update file extension in output path
        if self.output_path_edit.text():
            current_path = Path(self.output_path_edit.text())
            new_extension = f".{format_name.lower()}"
            new_path = current_path.with_suffix(new_extension)
            self.output_path_edit.setText(str(new_path))
    
    @Slot(bool)
    def _on_export_type_changed(self, checked: bool):
        """Handle export type change."""
        is_project_export = self.project_radio.isChecked()
        
        # Enable/disable project-specific options
        self.project_combo.setEnabled(is_project_export)
        self.include_thumbnails.setEnabled(is_project_export)
        self.include_favorites.setEnabled(is_project_export)
        self.include_tags.setEnabled(is_project_export)
    
    @Slot()
    def _browse_output_file(self):
        """Browse for output file."""
        format_name = self.format_combo.currentText().lower()
        
        filters = {
            'json': "JSON Files (*.json);;All Files (*)",
            'csv': "CSV Files (*.csv);;All Files (*)",
            'xml': "XML Files (*.xml);;All Files (*)"
        }
        
        file_filter = filters.get(format_name, "All Files (*)")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Export File",
            str(Path.home() / f"stockshot_export.{format_name}"),
            file_filter
        )
        
        if file_path:
            self.output_path_edit.setText(file_path)
    
    @Slot()
    def _preview_export(self):
        """Preview what will be exported."""
        try:
            export_params = self._get_export_parameters()
            
            preview_text = []
            preview_text.append("Export Preview:")
            preview_text.append(f"Type: {export_params['export_type'].title()}")
            preview_text.append(f"Format: {export_params['format'].upper()}")
            preview_text.append(f"Output: {export_params['output_path']}")
            
            if export_params['export_type'] == 'project':
                preview_text.append(f"Project: {export_params.get('project_name', 'All')}")
                preview_text.append(f"Include thumbnails: {export_params.get('include_thumbnails', False)}")
                preview_text.append(f"Include favorites: {export_params.get('include_favorites', True)}")
                preview_text.append(f"Include tags: {export_params.get('include_tags', True)}")
            else:
                preview_text.append(f"Entities: {len(export_params.get('entities', []))}")
            
            QMessageBox.information(self, "Export Preview", '\n'.join(preview_text))
            
        except Exception as e:
            QMessageBox.warning(self, "Preview Error", f"Error generating preview: {e}")
    
    @Slot()
    def _start_export(self):
        """Start the export process."""
        try:
            # Validate inputs
            if not self.output_path_edit.text().strip():
                QMessageBox.warning(self, "Invalid Input", "Please select an output file.")
                return
            
            export_params = self._get_export_parameters()
            
            # Validate export path
            output_path = Path(export_params['output_path'])
            if not self.exporter.validate_export_path(output_path, export_params['format']):
                QMessageBox.warning(self, "Invalid Path", "Cannot write to the selected output path.")
                return
            
            # Disable UI during export
            self._set_export_ui_state(False)
            
            # Show progress
            self.progress_bar.setVisible(True)
            self.progress_label.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_label.setText("Starting export...")
            
            # Start export worker
            self.export_worker = ExportWorker(self.exporter, export_params)
            self.export_worker.progress_updated.connect(self._on_export_progress)
            self.export_worker.export_completed.connect(self._on_export_completed)
            self.export_worker.start()
            
        except Exception as e:
            logger.error(f"Error starting export: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to start export: {e}")
            self._set_export_ui_state(True)
    
    def _get_export_parameters(self) -> dict:
        """Get export parameters from UI."""
        params = {
            'output_path': self.output_path_edit.text().strip(),
            'format': self.format_combo.currentText().lower(),
            'export_type': 'project' if self.project_radio.isChecked() else 'entities'
        }
        
        if params['export_type'] == 'project':
            params['project_name'] = None if self.project_combo.currentText() == "All Projects" else "Current"
            params['include_thumbnails'] = self.include_thumbnails.isChecked()
            params['include_favorites'] = self.include_favorites.isChecked()
            params['include_tags'] = self.include_tags.isChecked()
        else:
            params['entities'] = self.entities
        
        return params
    
    def _set_export_ui_state(self, enabled: bool):
        """Enable/disable UI during export."""
        self.project_radio.setEnabled(enabled)
        self.entities_radio.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.project_combo.setEnabled(enabled)
        self.include_thumbnails.setEnabled(enabled)
        self.include_favorites.setEnabled(enabled)
        self.include_tags.setEnabled(enabled)
        self.output_path_edit.setEnabled(enabled)
        self.browse_output_button.setEnabled(enabled)
        self.preview_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled)
    
    @Slot(int, str)
    def _on_export_progress(self, progress: int, status: str):
        """Handle export progress update."""
        self.progress_bar.setValue(progress)
        self.progress_label.setText(status)
    
    @Slot(bool, str)
    def _on_export_completed(self, success: bool, message: str):
        """Handle export completion."""
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self._set_export_ui_state(True)
        
        if success:
            QMessageBox.information(self, "Export Successful", message)
            self.accept()
        else:
            QMessageBox.critical(self, "Export Failed", message)
        
        # Clean up worker
        if self.export_worker:
            self.export_worker.deleteLater()
            self.export_worker = None
    
    def closeEvent(self, event):
        """Handle dialog close event."""
        if self.export_worker and self.export_worker.isRunning():
            reply = QMessageBox.question(
                self, "Export in Progress",
                "Export is currently running. Do you want to cancel it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.export_worker.terminate()
                self.export_worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
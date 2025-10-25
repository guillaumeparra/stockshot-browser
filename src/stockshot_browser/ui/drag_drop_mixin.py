"""
Drag and drop functionality mixin for Stockshot Browser.
"""

import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QMimeData, QUrl
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent

logger = logging.getLogger(__name__)


class DragDropMixin:
    """
    Mixin class to add drag-and-drop functionality to widgets.
    
    Usage:
        class MyWidget(QWidget, DragDropMixin):
            def __init__(self):
                super().__init__()
                self.setup_drag_drop()
                self.files_dropped.connect(self.handle_dropped_files)
    """
    
    # Signal emitted when files are dropped
    files_dropped = Signal(list)  # List of file paths
    directories_dropped = Signal(list)  # List of directory paths
    
    def setup_drag_drop(self, accept_files=True, accept_directories=True, 
                       file_extensions=None):
        """
        Setup drag and drop for the widget.
        
        Args:
            accept_files: Whether to accept file drops
            accept_directories: Whether to accept directory drops
            file_extensions: List of accepted file extensions (e.g., ['.mp4', '.mov'])
                           None means accept all extensions
        """
        self.setAcceptDrops(True)
        self._accept_files = accept_files
        self._accept_directories = accept_directories
        self._accepted_extensions = file_extensions or []
        
        logger.debug(f"Drag-drop enabled for {self.__class__.__name__}")
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter event."""
        if self._has_valid_urls(event.mimeData()):
            event.acceptProposedAction()
            event.accept()
            # Visual feedback
            if hasattr(self, 'setStyleSheet'):
                self.setStyleSheet(self.styleSheet() + """
                    QWidget {
                        border: 2px dashed #4CAF50;
                        background-color: rgba(76, 175, 80, 0.1);
                    }
                """)
        else:
            event.ignore()
    
    def dragMoveEvent(self, event: QDragMoveEvent):
        """Handle drag move event."""
        if self._has_valid_urls(event.mimeData()):
            event.acceptProposedAction()
            event.accept()
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        """Handle drag leave event."""
        # Remove visual feedback
        if hasattr(self, 'setStyleSheet'):
            # Remove the drag styling
            style = self.styleSheet()
            if 'border: 2px dashed' in style:
                # Reset to original style
                self.setStyleSheet(style.replace("""
                    QWidget {
                        border: 2px dashed #4CAF50;
                        background-color: rgba(76, 175, 80, 0.1);
                    }
                """, ""))
        event.accept()
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop event."""
        # Remove visual feedback
        if hasattr(self, 'setStyleSheet'):
            style = self.styleSheet()
            if 'border: 2px dashed' in style:
                self.setStyleSheet(style.replace("""
                    QWidget {
                        border: 2px dashed #4CAF50;
                        background-color: rgba(76, 175, 80, 0.1);
                    }
                """, ""))
        
        if not self._has_valid_urls(event.mimeData()):
            event.ignore()
            return
        
        files = []
        directories = []
        
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                
                if path.exists():
                    if path.is_dir():
                        if self._accept_directories:
                            directories.append(str(path))
                            logger.info(f"Directory dropped: {path}")
                    elif path.is_file():
                        if self._accept_files:
                            if self._is_accepted_file(path):
                                files.append(str(path))
                                logger.info(f"File dropped: {path}")
        
        # Emit signals for dropped items
        if files:
            self.files_dropped.emit(files)
        if directories:
            self.directories_dropped.emit(directories)
        
        event.acceptProposedAction()
        event.accept()
    
    def _has_valid_urls(self, mime_data: QMimeData) -> bool:
        """Check if mime data contains valid URLs."""
        if not mime_data.hasUrls():
            return False
        
        for url in mime_data.urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.exists():
                    if path.is_dir() and self._accept_directories:
                        return True
                    if path.is_file() and self._accept_files:
                        if self._is_accepted_file(path):
                            return True
        
        return False
    
    def _is_accepted_file(self, path: Path) -> bool:
        """Check if file has an accepted extension."""
        if not self._accepted_extensions:
            return True  # Accept all files if no extensions specified
        
        return path.suffix.lower() in [ext.lower() for ext in self._accepted_extensions]


class DropZoneWidget(QWidget, DragDropMixin):
    """
    A dedicated drop zone widget that accepts drag and drop.
    Can be used as a placeholder or overlay.
    """
    
    def __init__(self, parent=None, message="Drop files here"):
        super().__init__(parent)
        self.message = message
        self.setup_ui()
        self.setup_drag_drop()
    
    def setup_ui(self):
        """Setup the drop zone UI."""
        from PySide6.QtWidgets import QVBoxLayout, QLabel
        from PySide6.QtCore import Qt
        
        layout = QVBoxLayout(self)
        
        # Create drop message label
        self.drop_label = QLabel(self.message)
        self.drop_label.setAlignment(Qt.AlignCenter)
        
        # Style the drop zone
        self.setStyleSheet("""
            DropZoneWidget {
                border: 2px dashed #ccc;
                border-radius: 10px;
                background-color: #f9f9f9;
                min-height: 200px;
            }
            QLabel {
                color: #999;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(self.drop_label)
    
    def set_message(self, message: str):
        """Update the drop zone message."""
        self.message = message
        self.drop_label.setText(message)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Override to update visual feedback."""
        super().dragEnterEvent(event)
        if event.isAccepted():
            self.drop_label.setText("Release to drop")
            self.setStyleSheet("""
                DropZoneWidget {
                    border: 2px dashed #4CAF50;
                    border-radius: 10px;
                    background-color: rgba(76, 175, 80, 0.1);
                    min-height: 200px;
                }
                QLabel {
                    color: #4CAF50;
                    font-size: 16px;
                    font-weight: bold;
                }
            """)
    
    def dragLeaveEvent(self, event):
        """Override to reset visual feedback."""
        super().dragLeaveEvent(event)
        self.drop_label.setText(self.message)
        self.setStyleSheet("""
            DropZoneWidget {
                border: 2px dashed #ccc;
                border-radius: 10px;
                background-color: #f9f9f9;
                min-height: 200px;
            }
            QLabel {
                color: #999;
                font-size: 16px;
                font-weight: bold;
            }
        """)
    
    def dropEvent(self, event: QDropEvent):
        """Override to reset visual feedback after drop."""
        super().dropEvent(event)
        self.drop_label.setText(self.message)
        self.setStyleSheet("""
            DropZoneWidget {
                border: 2px dashed #ccc;
                border-radius: 10px;
                background-color: #f9f9f9;
                min-height: 200px;
            }
            QLabel {
                color: #999;
                font-size: 16px;
                font-weight: bold;
            }
        """)
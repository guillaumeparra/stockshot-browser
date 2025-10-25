# Stockshot Browser

A video file explorer designed for industry workflows. Built with Python 3 and PySide6 for cross-platform compatibility and maximum responsiveness.

## Features

### Core Functionality
- **Thunar-like Interface**: Classic file explorer with directory tree and content view
- **Tabbed Navigation**: Multiple directory tabs for efficient workflow
- **Entity Management**: Unified handling of video files and image sequences
- **Smart Thumbnails**: FFmpeg-powered thumbnail generation with caching
- **Advanced Search**: Metadata-based filtering with complex queries

### Professional Features
- **Cascading Configuration**: General → Project → User configuration hierarchy
- **Project Contexts**: Isolated workspaces for different productions
- **Batch Processing**: Mass thumbnail generation and metadata extraction
- **External Integration**: Configurable external player support

## Technology Stack

- **Core Language**: Python 3.8+
- **GUI Framework**: PySide6 (Qt6)
- **Database**: SQLite with SQLAlchemy ORM
- **Video Processing**: FFmpeg
- **Color Management**: OpenColorIO (OCIO)
- **Testing**: pytest with pytest-qt

## Installation

### Prerequisites

- Python 3.8 or higher
- FFmpeg (for video processing)
- OpenColorIO (optional, for color management)

### From Source

1. Clone the repository:
```bash
git clone https://github.com/guillaumeparra/sbrowser.git
cd stockshot-browser
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Quick Start

### Running the Application

```bash
# From source
python -m stockshot_browser.main

# Or if installed via pip
stockshot-browser
```

### First Launch

On first launch, Stockshot Browser will:
1. Create default configuration files in your user directory
2. Initialize the SQLite database
3. Set up thumbnail cache directories
4. Launch with the default project context

### Configuration

Stockshot Browser uses a cascading configuration system:

1. **General Configuration** (`config/defaults.py`): System-wide settings
2. **Project Configuration** (`your/path/project_config.json`): Project-specific settings
3. **User Configuration** (`your/path/user_config.json`): Personal preferences


In the (`config/defaults.py`) file, you'll be able to specify where will be stored the config files (user and project), the thumbnails, the databases, logs, etc.

    "paths": {
        "log_directory": str(_default_paths['user_dir']),
        "gen_thumbnail_directory": str(_default_paths['gen_dir'] / "thumbnail"),
        "gen_db_directory": str(_default_paths['gen_dir'] / "database"),
        "user_config_path": str(_default_paths['user_dir']),
        "user_thumbnail_path": str(_default_paths['user_dir'] / "thumbnail"),
        "user_db_path": str(_default_paths['user_dir'] / "database"),
        "project_config_path": str(_default_paths['project_dir']),
        "project_thumbnail_path": str(_default_paths['project_dir'] / "thumbnail"),
        "project_db_path": str(_default_paths['project_dir'] / "database"),
    },
    "config_files": {
        # Configuration file locations - easily customizable
        "user_config_file": str(_default_paths['user_dir'] / "user_config.json"),
        "project_config_file": str(_default_paths['project_dir'] / "project_config.json"),

Also point the paths you'll want to expose in the directory tree : 

    "directory_tree": {
        "configured_paths": [
            "/my/path/",
        ],

## Configuration Examples

### General Configuration

In the user_config.json and project_config.json file, you'll be able to add more paths that will be added in the directory tree as well.

## Development

### Project Structure

```
stockshot_browser/
├── src/stockshot_browser/
│   ├── config/          # Configuration management
│   ├── core/            # Core business logic
│   ├── database/        # Data models and persistence
│   ├── ui/              # User interface components
│   ├── utils/           # Utility functions
│   └── resources/       # Assets and templates
├── tests/               # Test suites
├── docs/                # Documentation
└── scripts/             # Build and deployment
```

### Architecture Overview

Stockshot Browser follows a modular architecture:

- **Configuration Layer**: Cascading configuration management
- **Core Layer**: Business logic and entity management
- **Data Layer**: SQLite database with SQLAlchemy models
- **UI Layer**: PySide6 interface components
- **Utils Layer**: FFmpeg integration, file utilities, etc.

## Usage

### Basic Workflow

1. **Launch Application**: Start Stockshot Browser
2. **Select Directory**: Navigate to your video/image directory
3. **Scan Content**: Application automatically detects videos and sequences
4. **Generate Thumbnails**: Thumbnails are created in the background
5. **Browse and Search**: Use the interface to browse and search content
6. **External Playback**: Right-click to play in external applications

### Image Sequence Detection

Stockshot Browser automatically detects image sequences using configurable patterns:

- `filename.####.ext` (e.g., `shot_001.0001.exr`)
- `filename_####.ext` (e.g., `render_0001.png`)
- Custom patterns via configuration

### Project Contexts

Create isolated workspaces for different projects:
- Separate favorites and settings per project
- Project-specific configuration overrides
- Isolated metadata and thumbnails

### External Player Integration

Configure external players for different file types:
- VLC for general video playback
- DJV for image sequences
- RV for professional review
- Custom player configurations

## Supported Formats

### Video Formats
- MP4, MOV, AVI, MKV, M4V, WMV, FLV, WebM
- Professional formats via FFmpeg

### Image Sequence Formats
- EXR, PNG, JPG, JPEG, TIFF, TIF, DPX
- Any format supported by FFmpeg

## Performance

### Optimizations
- Background thumbnail generation
- SQLite with WAL mode for concurrent access
- Intelligent caching strategies
- Lazy loading of content
- Configurable worker thread pools

### System Requirements
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: SSD recommended for thumbnail cache
- **CPU**: Multi-core processor for parallel processing
- **GPU**: Not required, but helps with video decoding

## Troubleshooting

### Common Issues

**Application won't start**
- Check Python version (3.8+ required)
- Verify all dependencies are installed
- Check log files in data directory

**Thumbnails not generating**
- Verify FFmpeg is installed and accessible
- Check FFmpeg path in configuration
- Review thumbnail generation logs

**Database errors**
- Check database file permissions
- Verify SQLite version compatibility
- Try database vacuum operation

**Performance issues**
- Reduce thumbnail resolution in settings
- Limit concurrent thumbnail generation
- Check available disk space for cache

### Code Style

- Follow PEP 8 style guidelines
- Use Black for code formatting
- Add type hints where appropriate
- Write comprehensive docstrings
- Include unit tests for new features

## Acknowledgments

- **FFmpeg**: For video processing capabilities
- **Qt/PySide6**: For the cross-platform GUI framework
- **SQLAlchemy**: For database abstraction
- **OpenColorIO**: For professional color management
- **The Python Community**: For the excellent ecosystem

---

**Stockshot Browser** - Professional video file exploration for industry workflows.
# Stockshot Browser

A professional video file explorer designed for industry workflows. Built with Python 3 and PySide6 for cross-platform compatibility and maximum responsiveness.

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
- **Color Management**: OpenColorIO integration for accurate color display

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
git clone https://github.com/stockshot/stockshot-browser.git
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

4. Install in development mode:
```bash
pip install -e .
```

### Using pip (when available)

```bash
pip install stockshot-browser
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

1. **General Configuration** (`global_config.json`): System-wide settings
2. **Project Configuration** (`project_config.json`): Project-specific settings
3. **User Configuration** (`user_config.json`): Personal preferences

Configuration files are automatically created in:
- **Linux/macOS**: `~/.config/stockshot_browser/`
- **Windows**: `%APPDATA%\StockshotBrowser\`

## Configuration Examples

### General Configuration
```json
{
  "version": "1.0.0",
  "paths": {
    "base_video_path": "/shared/footage",
    "project_config_path": "/shared/configs"
  },
  "thumbnails": {
    "default_resolution": 128,
    "cache_directory": ".thumbnails"
  },
  "ffmpeg": {
    "executable_path": "ffmpeg"
  }
}
```

### Project Configuration
```json
{
  "project_name": "Feature_Film_2024",
  "sequence_patterns": [
    "*.####.exr",
    "shot_*.%04d.png"
  ],
  "metadata": {
    "required_fields": ["copyright", "source"],
    "custom_tags": ["exterior", "vfx", "practical"]
  }
}
```

### User Configuration
```json
{
  "user_id": "john_doe",
  "interface": {
    "theme": "dark",
    "default_view": "grid",
    "show_metadata_overlay": true
  },
  "external_players": {
    "default": "/usr/bin/vlc",
    "alternatives": {
      "djv": "/usr/local/bin/djv_view"
    }
  }
}
```

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

### Setting up Development Environment

1. Clone the repository and create virtual environment (see Installation)

2. Install development dependencies:
```bash
pip install -e ".[dev]"
```

3. Run tests:
```bash
pytest
```

4. Format code:
```bash
black src/ tests/
```

5. Lint code:
```bash
flake8 src/ tests/
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=stockshot_browser

# Run specific test file
pytest tests/test_config.py

# Run with GUI tests (requires display)
pytest tests/test_ui.py
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

### Log Files

Log files are stored in:
- **Linux/macOS**: `~/.local/share/stockshot_browser/stockshot_browser.log`
- **Windows**: `%LOCALAPPDATA%\StockshotBrowser\stockshot_browser.log`

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

### Code Style

- Follow PEP 8 style guidelines
- Use Black for code formatting
- Add type hints where appropriate
- Write comprehensive docstrings
- Include unit tests for new features

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: [GitHub Wiki](https://github.com/stockshot/stockshot-browser/wiki)
- **Issues**: [GitHub Issues](https://github.com/stockshot/stockshot-browser/issues)
- **Discussions**: [GitHub Discussions](https://github.com/stockshot/stockshot-browser/discussions)

## Roadmap

### Version 1.1
- [ ] Plugin system for custom metadata extractors
- [ ] Network storage support
- [ ] Advanced color management features
- [ ] Batch export functionality

### Version 1.2
- [ ] Web interface for remote access
- [ ] Integration with asset management systems
- [ ] Advanced search with AI-powered tagging
- [ ] Performance profiling tools

## Acknowledgments

- **FFmpeg**: For video processing capabilities
- **Qt/PySide6**: For the cross-platform GUI framework
- **SQLAlchemy**: For database abstraction
- **OpenColorIO**: For professional color management
- **The Python Community**: For the excellent ecosystem

---

**Stockshot Browser** - Professional video file exploration for industry workflows.
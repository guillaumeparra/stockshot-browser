# Stockshot Browser - Project Summary

## Executive Overview

Stockshot Browser is a professional-grade video file explorer designed for industry workflows. Built with Python 3 and PySide6, it provides fast, efficient media browsing with advanced metadata management, thumbnail generation, and project context support across Linux, macOS, and Windows.

## Key Features Summary

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

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Core Language** | Python 3.8+ | Main application development |
| **GUI Framework** | PySide6 (Qt6) | Cross-platform user interface |
| **Database** | SQLite | Local metadata storage |
| **Video Processing** | FFmpeg | Metadata extraction & thumbnails |
| **Color Management** | OpenColorIO | Professional color handling |
| **ORM** | SQLAlchemy | Database abstraction |
| **Testing** | pytest + pytest-qt | Automated testing |

## Architecture Highlights

### Modular Design
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   UI Layer      │    │  Core Layer     │    │  Data Layer     │
│                 │    │                 │    │                 │
│ • Main Window   │◄──►│ • Config Mgr    │◄──►│ • SQLite DB     │
│ • Directory Tree│    │ • Entity Mgr    │    │ • File System   │
│ • Content View  │    │ • Metadata Mgr  │    │ • Thumbnail     │
│ • Tab Manager   │    │ • Thumbnail Mgr │    │   Cache         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Configuration Cascade
```
General Config ──► Project Config ──► User Config ──► Final Settings
(Global paths)     (Project paths)    (UI preferences)  (Runtime)
```

## Development Plan

### Phase Structure (10-12 weeks)
1. **Foundation** (Weeks 1-2): Project setup, architecture, database
2. **Core Functionality** (Weeks 3-4): FFmpeg integration, basic UI
3. **User Interface** (Weeks 5-6): Complete UI, navigation, interactions
4. **Advanced Features** (Weeks 7-8): Batch processing, project contexts
5. **Polish & Deployment** (Weeks 9-10): Testing, packaging, documentation

### Critical Path Items
- FFmpeg integration and thumbnail generation
- Image sequence detection system
- PySide6 UI implementation
- Cross-platform packaging

## Key Design Decisions

### 1. SQLite for Metadata Storage
**Rationale**: Lightweight, serverless, perfect for local storage
**Benefits**: No server setup, excellent performance, cross-platform
**Trade-offs**: Single-user access, limited concurrent writes

### 2. Configurable External Players
**Rationale**: Maximum flexibility for professional workflows
**Implementation**: User-defined executable paths in configuration
**Benefits**: Works with any video player, studio-specific tools

### 3. Custom Sequence Detection Patterns
**Rationale**: Different studios use different naming conventions
**Implementation**: Regex-based patterns in project configuration
**Benefits**: Adapts to any workflow, user-configurable

### 4. Background Thumbnail Generation
**Rationale**: Maintains UI responsiveness with large datasets
**Implementation**: Worker thread queue with priority handling
**Benefits**: Non-blocking UI, efficient resource usage

## File Structure Overview

```
stockshot-browser/
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

## Configuration Examples

### General Configuration
```json
{
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

## Database Schema Summary

### Core Tables
- **projects**: Project contexts and settings
- **entities**: Video files and image sequences
- **metadata**: Technical and custom metadata
- **tags**: Tagging system for organization
- **favorites**: Project and user favorites
- **thumbnails**: Thumbnail cache tracking

## Performance Targets

| Metric | Target | Rationale |
|--------|--------|-----------|
| **Startup Time** | < 3 seconds | Professional tool responsiveness |
| **Directory Scan** | < 5 seconds (1000 files) | Efficient large dataset handling |
| **Thumbnail Generation** | < 2 seconds per video | Acceptable wait time |
| **Search Response** | < 1 second | Real-time search experience |
| **Memory Usage** | < 500MB typical | Resource efficiency |

## Risk Mitigation

### Technical Risks
- **FFmpeg Complexity**: Start simple, expand gradually
- **Cross-Platform Issues**: Test early and often
- **Performance with Large Datasets**: Implement optimization from start

### Schedule Risks
- **Feature Scope Creep**: Maintain clear requirements
- **Integration Delays**: Research and prototype early

## Success Criteria

### Functional Requirements
- ✅ Supports all major video formats
- ✅ Handles image sequences correctly
- ✅ Generates thumbnails efficiently
- ✅ Provides fast metadata search
- ✅ Manages project contexts

### Quality Requirements
- ✅ Cross-platform compatibility
- ✅ Professional-grade performance
- ✅ Intuitive user interface
- ✅ Comprehensive testing coverage

## Next Steps

1. **Review and Approve Plan**: Stakeholder review of architecture and timeline
2. **Environment Setup**: Prepare development environment and tools
3. **Team Assignment**: Assign developers to specific components
4. **Begin Phase 1**: Start with project structure and core architecture

## Questions for Implementation Team

1. **Development Environment**: Any specific IDE or tooling preferences?
2. **Testing Strategy**: Preference for test-driven development approach?
3. **Code Style**: Any specific Python style guide beyond PEP 8?
4. **Deployment**: Preferred packaging and distribution methods?
5. **Documentation**: Level of inline documentation required?

This project summary provides the essential information needed to begin development of Stockshot Browser, with clear architecture, timeline, and success criteria established.
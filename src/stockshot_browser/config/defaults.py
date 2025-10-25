"""
Default configuration values for Stockshot Browser.
"""

import os
from pathlib import Path

# Get platform-specific default paths
def get_default_paths():
    """Get platform-specific default paths."""
    home = Path('/storage/tmp/_cache_and_configs_')
    
    if os.name == 'nt':  # Windows
        app_data = Path(os.environ.get('APPDATA', home / 'AppData' / 'Roaming'))
        local_data = Path(os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local'))
        return {
            'config_dir': app_data / 'StockshotBrowser',
            'cache_dir': local_data / 'StockshotBrowser' / 'Cache',
            'data_dir': local_data / 'StockshotBrowser',
        }
    else:  # Linux/macOS
        gen_dir = home / '.main'
        user_dir = home / '.user'
        project_dir = home / '.project'

        return {
            'gen_dir': gen_dir,
            'user_dir': user_dir,
            'project_dir': project_dir,
        }

# Get default paths
_default_paths = get_default_paths()

DEFAULT_CONFIG = {
    "version": "1.0.0",
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

        # Whether to create config files automatically if they don't exist
        "auto_create": True,
        # Whether to create parent directories if they don't exist
        "create_directories": True,
        # File permissions (Unix only)
        "file_permissions": 0o644,
        "directory_permissions": 0o755,
    },
    "thumbnails": {
        "default_resolution": 128,
        "cache_directory": str(_default_paths['gen_dir'] / "thumbnail"),
        "quality": 85,
        "max_cache_size_mb": 1024,  # 1GB cache limit
        "background_generation": True,
        "supported_formats": [".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".flv", ".webm"],
        "animated": {
            "enabled": True,
            "frame_count": 25,  # Number of frames to extract for animated thumbnails
            "fps": 10,  # Frames per second for animated thumbnails
            "loop": True,  # Loop the animation
            "format": "gif",  # Output format (gif or webp)
            "optimize": True,  # Optimize file size
            "max_size_kb": 500,  # Maximum size for animated thumbnails
        },
    },
    "ffmpeg": {
        "executable_path": "ffmpeg",
        "timeout": 30,
        "thumbnail_time_offset": 0.1,  # Extract thumbnail at 10% of video duration
        "max_concurrent_processes": 4,
    },
    "database": {
        "path": str(_default_paths['gen_dir'] / "database"),
        "backup_enabled": True,
        "backup_interval_hours": 24,
        "max_backups": 7,
    },
    "ui": {
        "theme": "dark_blue.xml",
        "theme_path": "looks/qt_material/themes/dark_blue.xml",
        "theme_enabled": True,
        "default_view_mode": "grid",
        "show_metadata_overlay": True,
        "thumbnail_size": 128,
        "window_geometry": {
            "width": 1200,
            "height": 800,
            "x": 100,
            "y": 100,
        },
        "splitter_sizes": [300, 900],
        "show_hidden_files": False,
        "auto_refresh": True,
        "refresh_interval_seconds": 30,
        "recursive_scan": True,  # Enable recursive scanning by default
    },

    # Available Material Design Themes
    "available_themes": {
        "dark_themes": [
            "dark_teal.xml",
            "dark_blue.xml",
            "dark_amber.xml",
            "dark_cyan.xml",
            "dark_lightgreen.xml",
            "dark_pink.xml",
            "dark_purple.xml",
            "dark_red.xml",
            "dark_yellow.xml",
            "dark_medical.xml"
        ],
        "light_themes": [
            "light_teal.xml",
            "light_blue.xml",
            "light_amber.xml",
            "light_cyan.xml",
            "light_lightgreen.xml",
            "light_pink.xml",
            "light_purple.xml",
            "light_red.xml",
            "light_yellow.xml",
            "light_orange.xml"
        ]
    },
    "sequence_detection": {
        "enabled": True,
        "default_patterns": [
            r"(.+)\.(\d{4,})\.(exr|png|jpg|jpeg|tiff|tif|dpx|tga|bmp)$",
            r"(.+)_(\d{4,})\.(exr|png|jpg|jpeg|tiff|tif|dpx|tga|bmp)$",
            r"(.+)\.v\d+\.(\d{4,})\.(exr|png|jpg|jpeg|tiff|tif|dpx|tga|bmp)$",
        ],
        "custom_patterns": [],
        "min_sequence_length": 2,
        "max_gap_frames": 10,
        "supported_extensions": [".exr", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".dpx", "tga", "bmp"],
        "folder_sequence_detection": {
            "enabled": True,
            "ignored_extensions": [".tx", ".thumbs", ".thumb", ".tmp", ".bak", ".log", ".txt", ".nfo", ".db", ".DS_Store"],
            "ignored_filenames": ["Thumbs.db", ".DS_Store", "desktop.ini", ".directory"],
        },
    },
    "metadata": {
        "auto_extract": True,
        "extract_on_import": True,
        "custom_fields": [],
        "required_fields": [],
        "default_tags": ["untagged"],
        "export_formats": ["json", "csv", "xml"],
    },
    "external_players": {
        "default": "",  # Will be auto-detected
        "players": {},  # User-defined players
        "auto_detect": True,
        "common_players": {
            "vlc": ["vlc", "/usr/bin/vlc", "/Applications/VLC.app/Contents/MacOS/VLC"],
            "djv": ["djv", "/apps/djv/bin/djv"],
        },
    },
    "performance": {
        "max_concurrent_thumbnails": 4,
        "thumbnail_cache_size": 100000,
        "metadata_cache_size": 500000,
        "lazy_loading": True,
        "preload_thumbnails": True,
        "background_scanning": True,
    },
    "color_management": {
        "enabled": False,  # Requires OpenColorIO
        "default_colorspace": "sRGB",
        "display_colorspace": "sRGB",
        "config_path": "",  # Path to OCIO config file
        "apply_to_thumbnails": True,
        "auto_detect_config": True,  # Try to find OCIO config automatically
        "fallback_to_builtin": True,  # Use built-in config if none found
        "common_colorspaces": {
            "linear": "Linear",
            "srgb": "sRGB",
            "rec709": "Rec.709",
            "aces": "ACES - ACEScg",
            "log": "Cineon",
        },
        "display_settings": {
            "default_display": "sRGB",
            "default_view": "Film",
            "available_displays": ["sRGB", "Rec.709", "P3-D65"],
        },
    },
    "logging": {
        "level": "INFO", # "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
        "file_enabled": True,
        "file_path": str(_default_paths['user_dir'] / 'stockshot_browser.log'),
        "max_file_size_mb": 10,
        "backup_count": 5,
        "console_enabled": True,
    },
    "projects": {
        "default_project": "Default",
        "auto_create_projects": True,
        "project_isolation": True,
        "recent_projects": [],
        "max_recent_projects": 10,
    },
    "search": {
        "index_enabled": True,
        "index_content": True,
        "search_history_size": 50,
        "case_sensitive": False,
        "regex_enabled": True,
    },
    "import": {
        "auto_scan_on_startup": True,
        "watch_directories": True,
        "auto_generate_thumbnails": True,
        "auto_extract_metadata": True,
        "duplicate_handling": "skip",  # skip, overwrite, rename
    },
    "directory_tree": {
        "configured_paths": [
            "/apps/comfyui/input",
            "/apps/comfyui/output",
        ],
        "show_drives": False,  # Windows only
        "expand_configured_paths": True,
    },
}
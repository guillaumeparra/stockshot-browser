"""
Configuration schema validation for Stockshot Browser.
"""

from typing import Dict, Any, List, Union, Optional
import re
from pathlib import Path


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class ConfigSchema:
    """Configuration schema validator."""
    
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> None:
        """Validate complete configuration dictionary."""
        ConfigSchema._validate_paths(config.get("paths", {}))
        ConfigSchema._validate_ffmpeg(config.get("ffmpeg", {}))
        ConfigSchema._validate_database(config.get("database", {}))
        ConfigSchema._validate_ui(config.get("ui", {}))
        ConfigSchema._validate_sequence_detection(config.get("sequence_detection", {}))
        ConfigSchema._validate_metadata(config.get("metadata", {}))
        ConfigSchema._validate_external_players(config.get("external_players", {}))
        ConfigSchema._validate_color_management(config.get("color_management", {}))
        ConfigSchema._validate_logging(config.get("logging", {}))
    
    @staticmethod
    def _validate_paths(paths: Dict[str, Any]) -> None:
        """Validate paths configuration."""
        required_paths = ["project_config_path", "user_config_path"]
        
        for path_key in required_paths:
            if path_key not in paths:
                raise ConfigValidationError(f"Missing required path: {path_key}")
            
            path_value = paths[path_key]
            if not isinstance(path_value, str):
                raise ConfigValidationError(f"Path {path_key} must be a string")
            
            # Validate path exists or can be created
            try:
                path_obj = Path(path_value)
                if not path_obj.exists():
                    # Try to create directory if it doesn't exist
                    path_obj.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError) as e:
                raise ConfigValidationError(f"Cannot access or create path {path_key}: {e}")
    
    @staticmethod
    def _validate_ffmpeg(ffmpeg: Dict[str, Any]) -> None:
        """Validate FFmpeg configuration."""
        if "executable_path" in ffmpeg:
            executable = ffmpeg["executable_path"]
            if not isinstance(executable, str):
                raise ConfigValidationError("ffmpeg executable_path must be a string")
        
        if "timeout" in ffmpeg:
            timeout = ffmpeg["timeout"]
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                raise ConfigValidationError("ffmpeg timeout must be a positive number")
        
        if "max_concurrent_processes" in ffmpeg:
            max_processes = ffmpeg["max_concurrent_processes"]
            if not isinstance(max_processes, int) or max_processes < 1 or max_processes > 16:
                raise ConfigValidationError("max_concurrent_processes must be between 1 and 16")
    
    @staticmethod
    def _validate_database(database: Dict[str, Any]) -> None:
        """Validate database configuration."""
        if "path" in database:
            db_path = database["path"]
            if not isinstance(db_path, str):
                raise ConfigValidationError("database path must be a string")
            
            # Validate parent directory exists or can be created
            try:
                db_path_obj = Path(db_path)
                db_path_obj.parent.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError) as e:
                raise ConfigValidationError(f"Cannot access database directory: {e}")
        
        if "max_backups" in database:
            max_backups = database["max_backups"]
            if not isinstance(max_backups, int) or max_backups < 0:
                raise ConfigValidationError("max_backups must be a non-negative integer")
    
    @staticmethod
    def _validate_ui(ui: Dict[str, Any]) -> None:
        """Validate UI configuration."""
        if "theme" in ui:
            theme = ui["theme"]
            valid_themes = ["light", "dark", "auto"]
            if theme not in valid_themes:
                raise ConfigValidationError(f"theme must be one of: {valid_themes}")
        
        if "default_view_mode" in ui:
            view_mode = ui["default_view_mode"]
            valid_modes = ["grid", "list", "advanced"]
            if view_mode not in valid_modes:
                raise ConfigValidationError(f"default_view_mode must be one of: {valid_modes}")
        
        if "thumbnail_size" in ui:
            size = ui["thumbnail_size"]
            if not isinstance(size, int) or size < 32 or size > 512:
                raise ConfigValidationError("thumbnail_size must be between 32 and 512")
        
        if "window_geometry" in ui:
            geometry = ui["window_geometry"]
            required_keys = ["width", "height", "x", "y"]
            for key in required_keys:
                if key not in geometry:
                    raise ConfigValidationError(f"window_geometry missing required key: {key}")
                if not isinstance(geometry[key], int):
                    raise ConfigValidationError(f"window_geometry {key} must be an integer")
    
    @staticmethod
    def _validate_sequence_detection(sequence: Dict[str, Any]) -> None:
        """Validate sequence detection configuration."""
        if "default_patterns" in sequence:
            patterns = sequence["default_patterns"]
            if not isinstance(patterns, list):
                raise ConfigValidationError("default_patterns must be a list")
            
            for pattern in patterns:
                if not isinstance(pattern, str):
                    raise ConfigValidationError("sequence patterns must be strings")
                
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise ConfigValidationError(f"Invalid regex pattern '{pattern}': {e}")
        
        if "min_sequence_length" in sequence:
            min_length = sequence["min_sequence_length"]
            if not isinstance(min_length, int) or min_length < 1:
                raise ConfigValidationError("min_sequence_length must be a positive integer")
        
        if "max_gap_frames" in sequence:
            max_gap = sequence["max_gap_frames"]
            if not isinstance(max_gap, int) or max_gap < 0:
                raise ConfigValidationError("max_gap_frames must be a non-negative integer")
    
    @staticmethod
    def _validate_metadata(metadata: Dict[str, Any]) -> None:
        """Validate metadata configuration."""
        if "export_formats" in metadata:
            formats = metadata["export_formats"]
            if not isinstance(formats, list):
                raise ConfigValidationError("export_formats must be a list")
            
            valid_formats = ["json", "csv", "xml", "yaml"]
            for fmt in formats:
                if fmt not in valid_formats:
                    raise ConfigValidationError(f"Invalid export format: {fmt}")
        
        if "custom_fields" in metadata:
            fields = metadata["custom_fields"]
            if not isinstance(fields, list):
                raise ConfigValidationError("custom_fields must be a list")
    
    @staticmethod
    def _validate_external_players(players: Dict[str, Any]) -> None:
        """Validate external players configuration."""
        if "players" in players:
            player_dict = players["players"]
            if not isinstance(player_dict, dict):
                raise ConfigValidationError("players must be a dictionary")
            
            for name, path in player_dict.items():
                if not isinstance(name, str) or not isinstance(path, str):
                    raise ConfigValidationError("player names and paths must be strings")

    
    @staticmethod
    def _validate_color_management(color: Dict[str, Any]) -> None:
        """Validate color management configuration."""
        if "config_path" in color:
            config_path = color["config_path"]
            if not isinstance(config_path, str):
                raise ConfigValidationError("color_management config_path must be a string")
            
            if config_path and not Path(config_path).exists():
                raise ConfigValidationError(f"Color management config file not found: {config_path}")
    
    @staticmethod
    def _validate_logging(logging_config: Dict[str, Any]) -> None:
        """Validate logging configuration."""
        if "level" in logging_config:
            level = logging_config["level"]
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if level not in valid_levels:
                raise ConfigValidationError(f"logging level must be one of: {valid_levels}")


def validate_project_config(config: Dict[str, Any]) -> None:
    """Validate project-specific configuration."""
    if "project_name" in config:
        name = config["project_name"]
        if not isinstance(name, str) or not name.strip():
            raise ConfigValidationError("project_name must be a non-empty string")
    
    if "sequence_patterns" in config:
        patterns = config["sequence_patterns"]
        if not isinstance(patterns, list):
            raise ConfigValidationError("sequence_patterns must be a list")
        
        for pattern in patterns:
            if not isinstance(pattern, str):
                raise ConfigValidationError("sequence patterns must be strings")


def validate_user_config(config: Dict[str, Any]) -> None:
    """Validate user-specific configuration."""
    if "user_id" in config:
        user_id = config["user_id"]
        if not isinstance(user_id, str) or not user_id.strip():
            raise ConfigValidationError("user_id must be a non-empty string")
    
    if "favorites" in config:
        favorites = config["favorites"]
        if "personal" in favorites:
            personal = favorites["personal"]
            if not isinstance(personal, list):
                raise ConfigValidationError("personal favorites must be a list")
"""
Configuration manager for Stockshot Browser.

Handles cascading configuration system:
General Config -> Project Config -> User Config -> Final Settings
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from copy import deepcopy

from .defaults import DEFAULT_CONFIG
from .schemas import ConfigSchema, ConfigValidationError, validate_project_config, validate_user_config


logger = logging.getLogger(__name__)


class ConfigurationManager:
    """Manages cascading configuration system."""
    
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._config_paths: Dict[str, Path] = {}
        self._loaded = False
        self._watchers = []  # For future file watching implementation
    
    def load_configuration(
        self,
        general_config_path: Optional[str] = None,
        project_config_path: Optional[str] = None,
        user_config_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Load and merge configuration files in cascade order.
        
        Args:
            general_config_path: Path to general/global configuration
            project_config_path: Path to project-specific configuration
            user_config_path: Path to user-specific configuration
            
        Returns:
            Final merged configuration dictionary
            
        Raises:
            ConfigValidationError: If configuration validation fails
        """
        logger.info("Loading configuration files...")
        
        # Start with defaults
        self._config = deepcopy(DEFAULT_CONFIG)
        logger.debug("Loaded default configuration")
        
        # Store all provided paths (even if files don't exist yet)
        if general_config_path:
            self._config_paths['general'] = Path(general_config_path)
        if project_config_path:
            self._config_paths['project'] = Path(project_config_path)
        if user_config_path:
            self._config_paths['user'] = Path(user_config_path)
        
        # Load general configuration
        if general_config_path and os.path.exists(general_config_path):
            try:
                general_config = self._load_json_config(general_config_path)
                self._merge_config(self._config, general_config)
                logger.info(f"Loaded general configuration from: {general_config_path}")
            except Exception as e:
                logger.warning(f"Failed to load general config: {e}")
        
        # Load project configuration
        if project_config_path and os.path.exists(project_config_path):
            try:
                project_config = self._load_json_config(project_config_path)
                validate_project_config(project_config)
                self._merge_config(self._config, project_config)
                logger.info(f"Loaded project configuration from: {project_config_path}")
            except Exception as e:
                logger.warning(f"Failed to load project config: {e}")
        
        # Load user configuration
        if user_config_path and os.path.exists(user_config_path):
            try:
                user_config = self._load_json_config(user_config_path)
                validate_user_config(user_config)
                self._merge_config(self._config, user_config)
                logger.info(f"Loaded user configuration from: {user_config_path}")
            except Exception as e:
                logger.warning(f"Failed to load user config: {e}")
        
        # Validate final configuration
        try:
            ConfigSchema.validate_config(self._config)
            logger.info("Configuration validation passed")
        except ConfigValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise
        
        # Set loaded flag before ensuring directories
        self._loaded = True
        
        # Ensure required directories exist
        self._ensure_directories()
        
        # Ensure configuration files exist and are properly initialized
        self.ensure_config_files_exist()
        
        logger.info("Configuration loading completed successfully")
        
        return self._config
    
    def _load_json_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            if not isinstance(config, dict):
                raise ConfigValidationError(f"Configuration file must contain a JSON object: {config_path}")
            
            return config
            
        except json.JSONDecodeError as e:
            raise ConfigValidationError(f"Invalid JSON in config file {config_path}: {e}")
        except IOError as e:
            raise ConfigValidationError(f"Cannot read config file {config_path}: {e}")
    
    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """
        Recursively merge override configuration into base configuration.
        
        Args:
            base: Base configuration dictionary (modified in place)
            override: Override configuration dictionary
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                self._merge_config(base[key], value)
            else:
                # Override value
                base[key] = deepcopy(value)
    
    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        directories_to_create = [
            self.get('paths.cache_directory'),
            self.get('paths.data_directory'),
            self.get('thumbnails.cache_directory'),
            self.get('paths.project_config_path'),
            self.get('paths.user_config_path'),
        ]
        
        for directory in directories_to_create:
            if directory:
                try:
                    Path(directory).mkdir(parents=True, exist_ok=True)
                    logger.debug(f"Ensured directory exists: {directory}")
                except (OSError, PermissionError) as e:
                    logger.warning(f"Cannot create directory {directory}: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        
        Args:
            key: Configuration key in dot notation (e.g., 'thumbnails.default_resolution')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
            
        Raises:
            RuntimeError: If configuration not loaded
        """
        if not self._loaded:
            raise RuntimeError("Configuration not loaded. Call load_configuration() first.")
        
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any, persist: bool = True) -> None:
        """
        Set configuration value and optionally persist to user config.
        
        Args:
            key: Configuration key in dot notation
            value: Value to set
            persist: Whether to persist to user configuration file
            
        Raises:
            RuntimeError: If configuration not loaded
        """
        if not self._loaded:
            raise RuntimeError("Configuration not loaded. Call load_configuration() first.")
        
        keys = key.split('.')
        config = self._config
        
        # Navigate to parent of target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
        logger.debug(f"Set configuration: {key} = {value}")
        
        if persist and 'user' in self._config_paths:
            try:
                self._save_user_config()
                logger.debug(f"Persisted configuration change: {key}")
            except Exception as e:
                logger.warning(f"Failed to persist configuration: {e}")
    
    def _save_user_config(self) -> None:
        """Save current configuration to user config file."""
        if 'user' not in self._config_paths:
            logger.warning("No user config path available for saving")
            return
        
        user_config_path = self._config_paths['user']
        
        # Load existing user config to preserve structure
        existing_user_config = {}
        if user_config_path.exists():
            try:
                existing_user_config = self._load_json_config(str(user_config_path))
            except Exception as e:
                logger.warning(f"Failed to load existing user config: {e}")
        
        # Extract user-specific settings from current config
        user_settings = self._extract_user_settings()
        
        # Merge with existing user config
        self._merge_config(existing_user_config, user_settings)
        
        # Save to file
        try:
            user_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(user_config_path, 'w', encoding='utf-8') as f:
                json.dump(existing_user_config, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved user configuration to: {user_config_path}")
        except IOError as e:
            logger.error(f"Failed to save user config: {e}")
            raise
    
    def _extract_user_settings(self) -> Dict[str, Any]:
        """Extract user-specific settings from current configuration."""
        # Define which settings are user-specific
        user_specific_keys = [
            'ui',
            'favorites.user_favorites',
            'external_players.default',
            'external_players.players',
            'thumbnails.preferred_resolution',
            'logging.level',
            'session',  # Include session data like tab states
        ]
        
        user_settings = {}
        
        for key in user_specific_keys:
            value = self.get(key)
            if value is not None:
                # Set nested value in user_settings
                keys = key.split('.')
                current = user_settings
                for k in keys[:-1]:
                    if k not in current:
                        current[k] = {}
                    current = current[k]
                current[keys[-1]] = deepcopy(value)
        
        return user_settings
    
    def get_config_info(self) -> Dict[str, Any]:
        """Get information about loaded configuration files."""
        return {
            'loaded': self._loaded,
            'config_paths': {k: str(v) for k, v in self._config_paths.items()},
            'version': self.get('version'),
            'total_keys': self._count_config_keys(self._config),
        }
    
    def _count_config_keys(self, config: Dict[str, Any]) -> int:
        """Recursively count configuration keys."""
        count = 0
        for value in config.values():
            if isinstance(value, dict):
                count += self._count_config_keys(value)
            else:
                count += 1
        return count
    
    def reload_configuration(self) -> None:
        """Reload configuration from files."""
        if not self._loaded:
            logger.warning("Cannot reload configuration - not initially loaded")
            return
        
        config_paths = {k: str(v) for k, v in self._config_paths.items()}
        
        self.load_configuration(
            general_config_path=config_paths.get('general'),
            project_config_path=config_paths.get('project'),
            user_config_path=config_paths.get('user'),
        )
        
        logger.info("Configuration reloaded successfully")
    
    def ensure_config_files_exist(self) -> None:
        """Ensure that user and project configuration files exist, creating them if necessary."""
        try:
            # Check if auto-creation is enabled in defaults
            config_files_settings = self.get('config_files', {})
            auto_create = config_files_settings.get('auto_create', True)
            create_directories = config_files_settings.get('create_directories', True)
            
            if not auto_create:
                logger.debug("Auto-creation of config files is disabled")
                return
            
            # Ensure user config file exists
            if 'user' in self._config_paths:
                user_config_path = Path(self._config_paths['user'])
                if not user_config_path.exists():
                    logger.info(f"Creating user configuration file: {user_config_path}")
                    self._create_default_user_config(user_config_path, create_directories)
                else:
                    logger.debug(f"User configuration file exists: {user_config_path}")
            
            # Ensure project config file exists
            if 'project' in self._config_paths:
                project_config_path = Path(self._config_paths['project'])
                if not project_config_path.exists():
                    logger.info(f"Creating project configuration file: {project_config_path}")
                    self._create_default_project_config(project_config_path, create_directories)
                else:
                    logger.debug(f"Project configuration file exists: {project_config_path}")
                    
        except Exception as e:
            logger.error(f"Error ensuring configuration files exist: {e}")
    
    def _create_default_user_config(self, user_config_path: Path, create_directories: bool = True) -> None:
        """Create a default user configuration file."""
        try:
            # Create directory if it doesn't exist and creation is enabled
            if create_directories:
                user_config_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Set directory permissions on Unix systems
                if os.name != 'nt':
                    config_files_settings = self.get('config_files', {})
                    dir_permissions = config_files_settings.get('directory_permissions', 0o755)
                    try:
                        os.chmod(user_config_path.parent, dir_permissions)
                    except (OSError, PermissionError):
                        pass  # Ignore permission errors
            
            # Create default user configuration
            default_user_config = {
                "user_id": "default_user",
                "ui": {
                    "theme": "dark",
                    "default_view_mode": "grid",
                    "show_metadata_overlay": True,
                    "window_geometry": {
                        "width": 1200,
                        "height": 800,
                        "x": 100,
                        "y": 100
                    },
                    "splitter_sizes": [300, 900]
                },
                "favorites": {
                    "user_favorites": []
                },
                "external_players": {
                    "default": "",
                    "players": {}
                },
                "session": {
                    "tab_states": []
                }
            }
            
            # Write to file
            with open(user_config_path, 'w', encoding='utf-8') as f:
                json.dump(default_user_config, f, indent=2, ensure_ascii=False)
            
            # Set file permissions on Unix systems
            if os.name != 'nt':
                config_files_settings = self.get('config_files', {})
                file_permissions = config_files_settings.get('file_permissions', 0o644)
                try:
                    os.chmod(user_config_path, file_permissions)
                except (OSError, PermissionError):
                    pass  # Ignore permission errors
            
            logger.info(f"Created default user configuration: {user_config_path}")
            
        except Exception as e:
            logger.error(f"Failed to create default user config: {e}")
            raise
    
    def _create_default_project_config(self, project_config_path: Path, create_directories: bool = True) -> None:
        """Create a default project configuration file."""
        try:
            # Create directory if it doesn't exist and creation is enabled
            if create_directories:
                project_config_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Set directory permissions on Unix systems
                if os.name != 'nt':
                    config_files_settings = self.get('config_files', {})
                    dir_permissions = config_files_settings.get('directory_permissions', 0o755)
                    try:
                        os.chmod(project_config_path.parent, dir_permissions)
                    except (OSError, PermissionError):
                        pass  # Ignore permission errors
            
            # Create default project configuration
            default_project_config = {
                "project_name": "Default Project",
                "sequence_patterns": [
                    r"(.+)\.(\d{4,})\.(exr|png|jpg|jpeg|tiff|tif|dpx)$",
                    r"(.+)_(\d{4,})\.(exr|png|jpg|jpeg|tiff|tif|dpx)$",
                ],
                "metadata": {
                    "required_fields": ["source"],
                    "custom_tags": ["untagged"]
                },
                "favorites": {
                    "project_favorites": {}
                }
            }
            
            # Write to file
            with open(project_config_path, 'w', encoding='utf-8') as f:
                json.dump(default_project_config, f, indent=2, ensure_ascii=False)
            
            # Set file permissions on Unix systems
            if os.name != 'nt':
                config_files_settings = self.get('config_files', {})
                file_permissions = config_files_settings.get('file_permissions', 0o644)
                try:
                    os.chmod(project_config_path, file_permissions)
                except (OSError, PermissionError):
                    pass  # Ignore permission errors
            
            logger.info(f"Created default project configuration: {project_config_path}")
            
        except Exception as e:
            logger.error(f"Failed to create default project config: {e}")
            raise
    
    def create_default_config_files(self, config_dir: Path) -> None:
        """Create default configuration files in specified directory."""
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Create default general config
        general_config = {
            "version": "1.0.0",
            "paths": {
                "base_video_path": str(Path.home() / "Videos"),
                "project_config_path": str(config_dir / "projects"),
                "user_config_path": str(config_dir),
            },
            "thumbnails": {
                "default_resolution": 128,
                "cache_directory": str(config_dir / "thumbnails"),
                "quality": 85,
            },
            "ffmpeg": {
                "executable_path": "ffmpeg",
                "timeout": 30,
            },
            "database": {
                "path": str(config_dir / "stockshot_browser.db"),
            },
        }
        
        # Create default project config
        project_config = {
            "project_name": "Default Project",
            "sequence_patterns": [
                r"(.+)\.(\d{4,})\.(exr|png|jpg|jpeg|tiff|tif|dpx)$",
                r"(.+)_(\d{4,})\.(exr|png|jpg|jpeg|tiff|tif|dpx)$",
            ],
            "metadata": {
                "required_fields": ["source"],
                "custom_tags": ["untagged"],
            },
        }
        
        # Create default user config
        user_config = {
            "user_id": "default_user",
            "interface": {
                "theme": "dark",
                "default_view": "grid",
                "show_metadata_overlay": True,
            },
            "external_players": {
                "default": "",
            },
            "favorites": {
                "personal": [],
            },
        }
        
        # Write config files
        configs = [
            (config_dir / "global_config.json", general_config),
            (config_dir / "project_config.json", project_config),
            (config_dir / "user_config.json", user_config),
        ]
        
        for config_path, config_data in configs:
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2, ensure_ascii=False)
                logger.info(f"Created default config file: {config_path}")
            except IOError as e:
                logger.error(f"Failed to create config file {config_path}: {e}")
                raise
    
    def save_user_config(self) -> None:
        """Public method to save user configuration."""
        self._save_user_config()
    
    def add_user_favorite(self, file_path: str) -> bool:
        """Add a file to user favorites."""
        try:
            user_favorites = self.get('favorites.user_favorites', [])
            file_path_str = str(file_path)
            
            if file_path_str not in user_favorites:
                user_favorites.append(file_path_str)
                self.set('favorites.user_favorites', user_favorites, persist=True)
                logger.info(f"Added to user favorites: {file_path_str}")
                return True
            else:
                logger.debug(f"File already in user favorites: {file_path_str}")
                return False
        except Exception as e:
            logger.error(f"Error adding user favorite {file_path}: {e}")
            return False
    
    def remove_user_favorite(self, file_path: str) -> bool:
        """Remove a file from user favorites."""
        try:
            user_favorites = self.get('favorites.user_favorites', [])
            file_path_str = str(file_path)
            
            if file_path_str in user_favorites:
                user_favorites.remove(file_path_str)
                self.set('favorites.user_favorites', user_favorites, persist=True)
                logger.info(f"Removed from user favorites: {file_path_str}")
                return True
            else:
                logger.debug(f"File not in user favorites: {file_path_str}")
                return False
        except Exception as e:
            logger.error(f"Error removing user favorite {file_path}: {e}")
            return False
    
    def is_user_favorite(self, file_path: str) -> bool:
        """Check if a file is in user favorites."""
        try:
            user_favorites = self.get('favorites.user_favorites', [])
            return str(file_path) in user_favorites
        except Exception as e:
            logger.error(f"Error checking user favorite {file_path}: {e}")
            return False
    
    def add_project_favorite(self, file_path: str, project_name: str) -> bool:
        """Add a file to project favorites."""
        try:
            project_favorites = self.get('favorites.project_favorites', {})
            file_path_str = str(file_path)
            
            if project_name not in project_favorites:
                project_favorites[project_name] = []
            
            if file_path_str not in project_favorites[project_name]:
                project_favorites[project_name].append(file_path_str)
                self.set('favorites.project_favorites', project_favorites, persist=False)
                
                # Save to project config if available
                self._save_project_favorites(project_favorites)
                logger.info(f"Added to project favorites ({project_name}): {file_path_str}")
                return True
            else:
                logger.debug(f"File already in project favorites ({project_name}): {file_path_str}")
                return False
        except Exception as e:
            logger.error(f"Error adding project favorite {file_path} to {project_name}: {e}")
            return False
    
    def remove_project_favorite(self, file_path: str, project_name: str) -> bool:
        """Remove a file from project favorites."""
        try:
            project_favorites = self.get('favorites.project_favorites', {})
            file_path_str = str(file_path)
            
            if project_name in project_favorites and file_path_str in project_favorites[project_name]:
                project_favorites[project_name].remove(file_path_str)
                
                # Clean up empty project entries
                if not project_favorites[project_name]:
                    del project_favorites[project_name]
                
                self.set('favorites.project_favorites', project_favorites, persist=False)
                
                # Save to project config if available
                self._save_project_favorites(project_favorites)
                logger.info(f"Removed from project favorites ({project_name}): {file_path_str}")
                return True
            else:
                logger.debug(f"File not in project favorites ({project_name}): {file_path_str}")
                return False
        except Exception as e:
            logger.error(f"Error removing project favorite {file_path} from {project_name}: {e}")
            return False
    
    def is_project_favorite(self, file_path: str, project_name: str) -> bool:
        """Check if a file is in project favorites."""
        try:
            project_favorites = self.get('favorites.project_favorites', {})
            return (project_name in project_favorites and
                    str(file_path) in project_favorites[project_name])
        except Exception as e:
            logger.error(f"Error checking project favorite {file_path} in {project_name}: {e}")
            return False
    
    def get_user_favorites(self) -> List[str]:
        """Get all user favorites."""
        return self.get('favorites.user_favorites', [])
    
    def get_project_favorites(self, project_name: str) -> List[str]:
        """Get favorites for a specific project."""
        project_favorites = self.get('favorites.project_favorites', {})
        return project_favorites.get(project_name, [])
    
    def _save_project_favorites(self, project_favorites: Dict[str, List[str]]) -> None:
        """Save project favorites to project configuration file."""
        if 'project' not in self._config_paths:
            logger.warning("No project config path available for saving project favorites")
            return
        
        project_config_path = Path(self._config_paths['project'])
        
        try:
            # Ensure project config file exists
            if not project_config_path.exists():
                logger.info(f"Project config file doesn't exist, creating: {project_config_path}")
                self._create_default_project_config(project_config_path)
            
            # Load existing project config
            existing_project_config = self._load_json_config(str(project_config_path))
            
            # Ensure favorites section exists
            if 'favorites' not in existing_project_config:
                existing_project_config['favorites'] = {}
            
            # Update favorites in project config
            existing_project_config['favorites']['project_favorites'] = project_favorites
            
            # Save to file
            project_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(project_config_path, 'w', encoding='utf-8') as f:
                json.dump(existing_project_config, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved project favorites to: {project_config_path}")
            
        except Exception as e:
            logger.error(f"Failed to save project favorites: {e}")
    
    def get_project_config(self) -> Dict[str, Any]:
        """Get the raw project configuration data."""
        if 'project' not in self._config_paths:
            return {}
        
        project_config_path = Path(self._config_paths['project'])
        if not project_config_path.exists():
            return {}
        
        try:
            return self._load_json_config(str(project_config_path))
        except Exception as e:
            logger.warning(f"Failed to load project config for raw access: {e}")
            return {}
    
    def get_user_config(self) -> Dict[str, Any]:
        """Get the raw user configuration data."""
        if 'user' not in self._config_paths:
            return {}
        
        user_config_path = Path(self._config_paths['user'])
        if not user_config_path.exists():
            return {}
        
        try:
            return self._load_json_config(str(user_config_path))
        except Exception as e:
            logger.warning(f"Failed to load user config for raw access: {e}")
            return {}
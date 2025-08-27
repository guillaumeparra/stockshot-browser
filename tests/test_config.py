"""
Tests for configuration management.
"""

import json
import tempfile
from pathlib import Path
import pytest

from stockshot_browser.config.manager import ConfigurationManager
from stockshot_browser.config.schemas import ConfigValidationError


class TestConfigurationManager:
    """Test configuration manager functionality."""
    
    def test_load_default_configuration(self):
        """Test loading default configuration."""
        config_manager = ConfigurationManager()
        config = config_manager.load_configuration()
        
        assert config is not None
        assert config_manager.get('version') == '1.0.0'
        assert config_manager.get('thumbnails.default_resolution') == 128
        assert config_manager.get('ffmpeg.executable_path') == 'ffmpeg'
    
    def test_cascading_configuration(self):
        """Test cascading configuration loading."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test config files
            general_config = {
                "thumbnails": {"default_resolution": 256},
                "ffmpeg": {"executable_path": "/usr/bin/ffmpeg"}
            }
            
            project_config = {
                "project_name": "Test Project",
                "thumbnails": {"default_resolution": 512}  # Override general
            }
            
            user_config = {
                "user_id": "test_user",
                "thumbnails": {"quality": 95}  # Additional setting
            }
            
            # Write config files
            general_path = temp_path / "general.json"
            project_path = temp_path / "project.json"
            user_path = temp_path / "user.json"
            
            with open(general_path, 'w') as f:
                json.dump(general_config, f)
            with open(project_path, 'w') as f:
                json.dump(project_config, f)
            with open(user_path, 'w') as f:
                json.dump(user_config, f)
            
            # Load cascading configuration
            config_manager = ConfigurationManager()
            config_manager.load_configuration(
                general_config_path=str(general_path),
                project_config_path=str(project_path),
                user_config_path=str(user_path)
            )
            
            # Test cascading: user > project > general > default
            assert config_manager.get('thumbnails.default_resolution') == 512  # From project
            assert config_manager.get('thumbnails.quality') == 95  # From user
            assert config_manager.get('ffmpeg.executable_path') == '/usr/bin/ffmpeg'  # From general
    
    def test_get_with_dot_notation(self):
        """Test getting configuration values with dot notation."""
        config_manager = ConfigurationManager()
        config_manager.load_configuration()
        
        # Test existing keys
        assert config_manager.get('thumbnails.default_resolution') == 128
        assert config_manager.get('ui.theme') == 'dark'
        
        # Test non-existing keys
        assert config_manager.get('nonexistent.key') is None
        assert config_manager.get('nonexistent.key', 'default') == 'default'
    
    def test_set_configuration_value(self):
        """Test setting configuration values."""
        config_manager = ConfigurationManager()
        config_manager.load_configuration()
        
        # Set a value
        config_manager.set('test.key', 'test_value', persist=False)
        assert config_manager.get('test.key') == 'test_value'
        
        # Set nested value
        config_manager.set('nested.deep.key', 42, persist=False)
        assert config_manager.get('nested.deep.key') == 42
    
    def test_invalid_configuration(self):
        """Test handling of invalid configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create invalid JSON file
            invalid_path = temp_path / "invalid.json"
            with open(invalid_path, 'w') as f:
                f.write("{ invalid json }")
            
            config_manager = ConfigurationManager()
            
            # Should handle invalid JSON gracefully
            with pytest.raises(ConfigValidationError):
                config_manager.load_configuration(general_config_path=str(invalid_path))
    
    def test_configuration_not_loaded_error(self):
        """Test error when accessing configuration before loading."""
        config_manager = ConfigurationManager()
        
        with pytest.raises(RuntimeError, match="Configuration not loaded"):
            config_manager.get('some.key')
        
        with pytest.raises(RuntimeError, match="Configuration not loaded"):
            config_manager.set('some.key', 'value')
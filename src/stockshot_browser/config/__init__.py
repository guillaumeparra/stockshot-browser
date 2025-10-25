"""
Configuration management module for Stockshot Browser.

This module handles the cascading configuration system:
General Config -> Project Config -> User Config -> Final Settings
"""

from .manager import ConfigurationManager
from .defaults import DEFAULT_CONFIG
from .schemas import ConfigSchema

__all__ = [
    "ConfigurationManager",
    "DEFAULT_CONFIG", 
    "ConfigSchema",
]
"""
Core application components for Stockshot Browser.

This module contains the main application logic, entity management,
metadata handling, and other core functionality.
"""

from .application import StockshotBrowserApp
from .entity_manager import EntityManager, MediaEntity, EntityType
from .metadata_manager import MetadataManager
from .thumbnail_manager import ThumbnailManager
from .context_manager import ContextManager

__all__ = [
    "StockshotBrowserApp",
    "EntityManager",
    "MediaEntity", 
    "EntityType",
    "MetadataManager",
    "ThumbnailManager",
    "ContextManager",
]
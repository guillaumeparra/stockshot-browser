"""
Database module for Stockshot Browser.

This module handles all database operations including models,
connections, and migrations for metadata storage.
"""

from .models import (
    Base,
    Project,
    Entity,
    Metadata,
    Tag,
    Favorite,
    Thumbnail,
    entity_tags,
)
from .connection import DatabaseManager, get_session

__all__ = [
    "Base",
    "Project",
    "Entity",
    "Metadata",
    "Tag",
    "Favorite",
    "Thumbnail",
    "entity_tags",
    "DatabaseManager",
    "get_session",
]
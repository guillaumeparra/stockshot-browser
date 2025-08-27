"""
SQLAlchemy database models for Stockshot Browser.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime,
    ForeignKey, Table, Index, UniqueConstraint, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func


Base = declarative_base()


# Association table for many-to-many relationship between entities and tags
entity_tags = Table(
    'entity_tags',
    Base.metadata,
    Column('entity_id', Integer, ForeignKey('entities.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)


class Project(Base):
    """Project context model."""
    
    __tablename__ = 'projects'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    path = Column(Text, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Configuration stored as JSON
    config = Column(Text)  # JSON string
    
    # Relationships
    entities = relationship("Entity", back_populates="project", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="project", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name='{self.name}')>"
    
    @validates('name')
    def validate_name(self, key: str, name: str) -> str:
        if not name or not name.strip():
            raise ValueError("Project name cannot be empty")
        return name.strip()
    
    def get_config(self) -> Dict[str, Any]:
        """Get project configuration as dictionary."""
        if self.config:
            try:
                return json.loads(self.config)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def set_config(self, config_dict: Dict[str, Any]) -> None:
        """Set project configuration from dictionary."""
        self.config = json.dumps(config_dict, ensure_ascii=False)


class Entity(Base):
    """Media entity model (video files and image sequences)."""
    
    __tablename__ = 'entities'
    
    id = Column(Integer, primary_key=True)
    path = Column(Text, nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)  # 'video' or 'sequence'
    name = Column(String(255), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True, index=True)
    
    # File system metadata
    file_size = Column(Integer)  # Total size in bytes
    file_count = Column(Integer, default=1)  # Number of files (for sequences)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    last_scanned = Column(DateTime, default=func.now())
    last_accessed = Column(DateTime)  # When entity was last accessed/viewed
    
    # Status flags
    is_active = Column(Boolean, default=True, index=True)
    metadata_extracted = Column(Boolean, default=False, index=True)
    thumbnail_generated = Column(Boolean, default=False, index=True)
    
    # Relationships
    project = relationship("Project", back_populates="entities")
    entity_metadata = relationship("Metadata", back_populates="entity", uselist=False, cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=entity_tags, back_populates="entities")
    favorites = relationship("Favorite", back_populates="entity", cascade="all, delete-orphan")
    thumbnails = relationship("Thumbnail", back_populates="entity", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_entity_project_type', 'project_id', 'entity_type'),
        Index('idx_entity_path_hash', 'path'),
        UniqueConstraint('path', 'project_id', name='uq_entity_path_project'),
    )
    
    def __repr__(self) -> str:
        return f"<Entity(id={self.id}, name='{self.name}', type='{self.entity_type}')>"
    
    @validates('entity_type')
    def validate_entity_type(self, key: str, entity_type: str) -> str:
        valid_types = ['video', 'sequence']
        if entity_type not in valid_types:
            raise ValueError(f"Entity type must be one of: {valid_types}")
        return entity_type
    
    @validates('name')
    def validate_name(self, key: str, name: str) -> str:
        if not name or not name.strip():
            raise ValueError("Entity name cannot be empty")
        return name.strip()
    
    def update_last_accessed(self) -> None:
        """Update the last accessed timestamp to current time."""
        self.last_accessed = func.now()
    
    def get_access_status(self) -> str:
        """Get a human-readable access status."""
        if not self.last_accessed:
            return "Never accessed"
        
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        
        if isinstance(self.last_accessed, datetime):
            diff = now - self.last_accessed
        else:
            # Handle cases where last_accessed might be a string or other type
            return "Recently accessed"
        
        if diff < timedelta(hours=1):
            return "Accessed recently"
        elif diff < timedelta(days=1):
            return f"Accessed {diff.seconds // 3600} hours ago"
        elif diff < timedelta(days=7):
            return f"Accessed {diff.days} days ago"
        else:
            return f"Accessed {diff.days} days ago"


class Metadata(Base):
    """Metadata model for media entities."""
    
    __tablename__ = 'metadata'
    
    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey('entities.id'), nullable=False, unique=True, index=True)
    
    # Categorization
    category = Column(String(100), index=True)  # Category for metadata (e.g., 'technical', 'artistic', 'production')
    
    # Video/Image metadata
    duration = Column(Float)  # Duration in seconds
    fps = Column(Float)  # Frames per second
    width = Column(Integer)  # Width in pixels
    height = Column(Integer)  # Height in pixels
    aspect_ratio = Column(Float)  # Calculated aspect ratio
    
    # Format information
    format = Column(String(50))  # Container format (mp4, mov, etc.)
    codec = Column(String(50))  # Video codec
    audio_codec = Column(String(50))  # Audio codec
    colorspace = Column(String(100))  # Color space information
    bit_depth = Column(Integer)  # Bit depth
    
    # Technical metadata
    bitrate = Column(Integer)  # Bitrate in kbps
    frame_count = Column(Integer)  # Total number of frames
    has_audio = Column(Boolean, default=False)
    
    # Custom fields stored as JSON
    custom_fields = Column(Text)  # JSON string for additional metadata
    
    # Timestamps
    extracted_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    entity = relationship("Entity", back_populates="entity_metadata")
    
    def __repr__(self) -> str:
        return f"<Metadata(id={self.id}, entity_id={self.entity_id})>"
    
    def get_custom_fields(self) -> Dict[str, Any]:
        """Get custom fields as dictionary."""
        if self.custom_fields:
            try:
                return json.loads(self.custom_fields)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def set_custom_fields(self, fields_dict: Dict[str, Any]) -> None:
        """Set custom fields from dictionary."""
        self.custom_fields = json.dumps(fields_dict, ensure_ascii=False)
    
    def add_custom_field(self, key: str, value: Any) -> None:
        """Add or update a single custom field."""
        fields = self.get_custom_fields()
        fields[key] = value
        self.set_custom_fields(fields)
    
    def get_resolution_string(self) -> str:
        """Get resolution as formatted string."""
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return "Unknown"
    
    def calculate_aspect_ratio(self) -> Optional[float]:
        """Calculate and return aspect ratio."""
        if self.width and self.height and self.height > 0:
            return round(self.width / self.height, 3)
        return None
    
    @validates('category')
    def validate_category(self, key: str, category: str) -> Optional[str]:
        """Validate metadata category."""
        if category:
            category = category.strip().lower()
            valid_categories = [
                'technical', 'artistic', 'production', 'workflow',
                'quality', 'color', 'audio', 'video', 'general'
            ]
            if category not in valid_categories:
                # Allow any category but normalize it
                pass
            return category
        return category
    
    def set_category(self, category: str) -> None:
        """Set metadata category with validation."""
        self.category = category
    
    def get_category_display(self) -> str:
        """Get display-friendly category name."""
        if not self.category:
            return "General"
        return self.category.title()


class Tag(Base):
    """Tag model for categorizing entities."""
    
    __tablename__ = 'tags'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    color = Column(String(7))  # Hex color code (#RRGGBB)
    description = Column(Text)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    entities = relationship("Entity", secondary=entity_tags, back_populates="tags")
    
    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name='{self.name}')>"
    
    @validates('name')
    def validate_name(self, key: str, name: str) -> str:
        if not name or not name.strip():
            raise ValueError("Tag name cannot be empty")
        return name.strip().lower()
    
    @validates('color')
    def validate_color(self, key: str, color: str) -> Optional[str]:
        if color:
            if not color.startswith('#') or len(color) != 7:
                raise ValueError("Color must be in hex format (#RRGGBB)")
            try:
                int(color[1:], 16)  # Validate hex digits
            except ValueError:
                raise ValueError("Invalid hex color code")
        return color


class Favorite(Base):
    """Favorite model for bookmarking entities."""
    
    __tablename__ = 'favorites'
    
    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey('entities.id'), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True, index=True)  # NULL for user favorites
    user_id = Column(String(100), nullable=True, index=True)  # User identifier
    
    # Optional metadata
    note = Column(Text)  # User note about the favorite
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    entity = relationship("Entity", back_populates="favorites")
    project = relationship("Project", back_populates="favorites")
    
    # Constraints
    __table_args__ = (
        Index('idx_favorite_user_project', 'user_id', 'project_id'),
        UniqueConstraint('entity_id', 'project_id', 'user_id', name='uq_favorite_entity_project_user'),
    )
    
    def __repr__(self) -> str:
        return f"<Favorite(id={self.id}, entity_id={self.entity_id}, user_id='{self.user_id}')>"
    
    def is_project_favorite(self) -> bool:
        """Check if this is a project-specific favorite."""
        return self.project_id is not None
    
    def is_user_favorite(self) -> bool:
        """Check if this is a user personal favorite."""
        return self.project_id is None


class Thumbnail(Base):
    """Thumbnail model for tracking generated thumbnails."""
    
    __tablename__ = 'thumbnails'
    
    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey('entities.id'), nullable=False, index=True)
    path = Column(Text, nullable=False)  # Path to thumbnail file
    resolution = Column(Integer, nullable=False)  # Thumbnail resolution
    file_size = Column(Integer)  # Thumbnail file size in bytes
    
    # Generation metadata
    generated_at = Column(DateTime, default=func.now(), nullable=False)
    generation_time = Column(Float)  # Time taken to generate in seconds
    source_frame = Column(Float)  # Source frame time for videos
    
    # Additional metadata (e.g., animated_path for GIFs)
    extra_data = Column(JSON)  # Store additional metadata like animated thumbnail path
    
    # Status
    is_valid = Column(Boolean, default=True, index=True)
    
    # Relationships
    entity = relationship("Entity", back_populates="thumbnails")
    
    # Constraints
    __table_args__ = (
        Index('idx_thumbnail_entity_resolution', 'entity_id', 'resolution'),
        UniqueConstraint('entity_id', 'resolution', name='uq_thumbnail_entity_resolution'),
    )
    
    def __repr__(self) -> str:
        return f"<Thumbnail(id={self.id}, entity_id={self.entity_id}, resolution={self.resolution})>"
    
    @validates('resolution')
    def validate_resolution(self, key: str, resolution: int) -> int:
        if resolution < 32 or resolution > 1024:
            raise ValueError("Thumbnail resolution must be between 32 and 1024 pixels")
        return resolution
    
    def get_animated_path(self) -> Optional[str]:
        """Get animated thumbnail path from metadata if available."""
        if self.extra_data and isinstance(self.extra_data, dict):
            return self.extra_data.get('animated_path')
        return None
    
    def set_animated_path(self, path: str) -> None:
        """Set animated thumbnail path in metadata."""
        if not self.extra_data:
            self.extra_data = {}
        self.extra_data['animated_path'] = path


# Create indexes for better query performance
def create_additional_indexes(engine):
    """Create additional database indexes for performance."""
    from sqlalchemy import text
    
    with engine.connect() as conn:
        # Create basic performance indexes
        try:
            # Index for entity path searches
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_entities_path_search ON entities (path)
            """))
            
            # Index for entity name searches
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_entities_name_search ON entities (name)
            """))
            
            # Index for metadata searches
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_metadata_resolution ON metadata (width, height)
            """))
            
            conn.commit()
            
        except Exception as e:
            print(f"Warning: Could not create additional indexes: {e}")
"""
Metadata export functionality for Stockshot Browser.
"""

import logging
import json
import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..config.manager import ConfigurationManager
from ..database.connection import DatabaseManager
from ..database.models import Entity, Metadata, Thumbnail, Favorite, Tag

logger = logging.getLogger(__name__)


class MetadataExporter:
    """Export metadata and project data in various formats."""
    
    def __init__(self, database_manager: DatabaseManager, config_manager: ConfigurationManager = None):
        self.database_manager = database_manager
        self.config_manager = config_manager
        
        # Supported export formats
        self.supported_formats = ['json', 'csv', 'xml']
        
        logger.info("MetadataExporter initialized")
    
    def export_project_data(self, output_path: Path, format: str = 'json', 
                           project_name: Optional[str] = None,
                           include_thumbnails: bool = False,
                           include_favorites: bool = True,
                           include_tags: bool = True) -> bool:
        """
        Export complete project data.
        
        Args:
            output_path: Path to output file
            format: Export format ('json', 'csv', 'xml')
            project_name: Specific project to export (None for all)
            include_thumbnails: Include thumbnail information
            include_favorites: Include favorites data
            include_tags: Include tags data
            
        Returns:
            True if export successful, False otherwise
        """
        if format not in self.supported_formats:
            logger.error(f"Unsupported export format: {format}")
            return False
        
        try:
            # Collect data
            data = self._collect_project_data(
                project_name=project_name,
                include_thumbnails=include_thumbnails,
                include_favorites=include_favorites,
                include_tags=include_tags
            )
            
            # Export based on format
            if format == 'json':
                return self._export_json(data, output_path)
            elif format == 'csv':
                return self._export_csv(data, output_path)
            elif format == 'xml':
                return self._export_xml(data, output_path)
            
        except Exception as e:
            logger.error(f"Error exporting project data: {e}")
            return False
        
        return False
    
    def export_entity_list(self, entities: List[Any], output_path: Path, 
                          format: str = 'json') -> bool:
        """
        Export a specific list of entities.
        
        Args:
            entities: List of MediaEntity objects
            output_path: Path to output file
            format: Export format
            
        Returns:
            True if export successful, False otherwise
        """
        try:
            # Convert entities to export format
            entity_data = []
            
            with self.database_manager.get_session() as session:
                for entity in entities:
                    # Find entity in database
                    db_entity = session.query(Entity).filter_by(
                        path=str(entity.path),
                        entity_type=entity.entity_type.value
                    ).first()
                    
                    entity_info = {
                        'name': entity.name,
                        'path': str(entity.path),
                        'type': entity.entity_type.value,
                        'file_size': entity.file_size,
                        'file_count': len(entity.files) if hasattr(entity, 'files') else 1,
                        'frame_range': entity.frame_range if hasattr(entity, 'frame_range') else None,
                        'created_at': datetime.now().isoformat(),
                    }
                    
                    # Add database metadata if available
                    if db_entity:
                        entity_info['id'] = db_entity.id
                        entity_info['thumbnail_generated'] = db_entity.thumbnail_generated
                        entity_info['last_accessed'] = db_entity.last_accessed.isoformat() if db_entity.last_accessed else None
                        
                        # Add metadata
                        metadata_records = session.query(Metadata).filter_by(entity_id=db_entity.id).all()
                        if metadata_records:
                            entity_info['metadata'] = {}
                            for meta in metadata_records:
                                entity_info['metadata'][meta.key] = meta.value
                    
                    entity_data.append(entity_info)
            
            # Create export data structure
            export_data = {
                'export_info': {
                    'timestamp': datetime.now().isoformat(),
                    'format': format,
                    'entity_count': len(entity_data),
                    'exported_by': 'Stockshot Browser'
                },
                'entities': entity_data
            }
            
            # Export based on format
            if format == 'json':
                return self._export_json(export_data, output_path)
            elif format == 'csv':
                return self._export_entities_csv(entity_data, output_path)
            elif format == 'xml':
                return self._export_xml(export_data, output_path)
            
        except Exception as e:
            logger.error(f"Error exporting entity list: {e}")
            return False
        
        return False
    
    def export_entity_metadata(self, entity_id: int) -> Dict[str, Any]:
        """
        Export metadata for a single entity.
        
        Args:
            entity_id: Database ID of the entity
            
        Returns:
            Dictionary containing entity metadata
        """
        try:
            with self.database_manager.get_session() as session:
                from ..database.models import entity_tags
                
                # Get entity
                entity = session.query(Entity).filter_by(id=entity_id).first()
                if not entity:
                    logger.error(f"Entity not found: {entity_id}")
                    return {}
                
                # Build entity data
                entity_data = {
                    'entity_info': {
                        'id': entity.id,
                        'name': entity.name,
                        'path': entity.path,
                        'entity_type': entity.entity_type,
                        'file_size': entity.file_size,
                        'file_count': entity.file_count,
                        'thumbnail_generated': entity.thumbnail_generated,
                        'created_at': entity.created_at.isoformat() if entity.created_at else None,
                        'last_accessed': entity.last_accessed.isoformat() if entity.last_accessed else None,
                    },
                    'metadata': {},
                    'tags': [],
                    'favorites': [],
                    'thumbnails': []
                }
                
                # Get metadata records
                metadata_records = session.query(Metadata).filter_by(entity_id=entity.id).all()
                for meta in metadata_records:
                    category = meta.category or 'general'
                    if category not in entity_data['metadata']:
                        entity_data['metadata'][category] = {}
                    
                    # Try to parse JSON metadata
                    try:
                        if meta.metadata_json:
                            parsed_data = json.loads(meta.metadata_json)
                            entity_data['metadata'][category].update(parsed_data)
                        else:
                            entity_data['metadata'][category][meta.key] = meta.value
                    except json.JSONDecodeError:
                        entity_data['metadata'][category][meta.key] = meta.value
                
                # Get tags
                tags = session.query(Tag).join(entity_tags).filter(
                    entity_tags.c.entity_id == entity.id
                ).all()
                
                for tag in tags:
                    tag_data = {
                        'id': tag.id,
                        'name': tag.name,
                        'color': tag.color,
                        'description': tag.description,
                        'created_at': tag.created_at.isoformat() if tag.created_at else None,
                    }
                    entity_data['tags'].append(tag_data)
                
                # Get favorites
                favorites = session.query(Favorite).filter_by(entity_id=entity.id).all()
                for fav in favorites:
                    favorite_data = {
                        'id': fav.id,
                        'user_id': fav.user_id,
                        'project_id': fav.project_id,
                        'created_at': fav.created_at.isoformat() if fav.created_at else None,
                    }
                    entity_data['favorites'].append(favorite_data)
                
                # Get thumbnails
                thumbnails = session.query(Thumbnail).filter_by(entity_id=entity.id).all()
                for thumb in thumbnails:
                    thumbnail_data = {
                        'id': thumb.id,
                        'path': thumb.path,
                        'resolution': thumb.resolution,
                        'file_size': thumb.file_size,
                        'generation_time': thumb.generation_time,
                        'source_frame': thumb.source_frame,
                        'is_valid': thumb.is_valid,
                        'created_at': thumb.created_at.isoformat() if thumb.created_at else None,
                        'extra_data': thumb.extra_data
                    }
                    entity_data['thumbnails'].append(thumbnail_data)
                
                # Add export timestamp
                entity_data['export_info'] = {
                    'timestamp': datetime.now().isoformat(),
                    'exported_by': 'Stockshot Browser Metadata Viewer'
                }
                
                return entity_data
                
        except Exception as e:
            logger.error(f"Error exporting entity metadata: {e}")
            return {}
    
    def _collect_project_data(self, project_name: Optional[str] = None,
                             include_thumbnails: bool = False,
                             include_favorites: bool = True,
                             include_tags: bool = True) -> Dict[str, Any]:
        """Collect all project data for export."""
        data = {
            'export_info': {
                'timestamp': datetime.now().isoformat(),
                'project_name': project_name or 'All Projects',
                'exported_by': 'Stockshot Browser',
                'version': self.config_manager.get('version', '1.0.0')
            },
            'entities': [],
            'metadata': [],
            'thumbnails': [],
            'favorites': [],
            'tags': []
        }
        
        try:
            with self.database_manager.get_session() as session:
                # Get entities
                entity_query = session.query(Entity)
                if project_name:
                    # Filter by project if specified (would need project association)
                    pass  # Project filtering would be implemented here
                
                entities = entity_query.all()
                
                for entity in entities:
                    entity_data = {
                        'id': entity.id,
                        'path': entity.path,
                        'name': entity.name,
                        'entity_type': entity.entity_type,
                        'file_size': entity.file_size,
                        'file_count': entity.file_count,
                        'thumbnail_generated': entity.thumbnail_generated,
                        'created_at': entity.created_at.isoformat() if entity.created_at else None,
                        'last_accessed': entity.last_accessed.isoformat() if entity.last_accessed else None,
                    }
                    data['entities'].append(entity_data)
                
                # Get metadata
                metadata_records = session.query(Metadata).all()
                for meta in metadata_records:
                    metadata_data = {
                        'id': meta.id,
                        'entity_id': meta.entity_id,
                        'key': meta.key,
                        'value': meta.value,
                        'data_type': meta.data_type,
                        'created_at': meta.created_at.isoformat() if meta.created_at else None,
                    }
                    data['metadata'].append(metadata_data)
                
                # Get thumbnails if requested
                if include_thumbnails:
                    thumbnail_records = session.query(Thumbnail).all()
                    for thumb in thumbnail_records:
                        thumbnail_data = {
                            'id': thumb.id,
                            'entity_id': thumb.entity_id,
                            'path': thumb.path,
                            'resolution': thumb.resolution,
                            'file_size': thumb.file_size,
                            'generation_time': thumb.generation_time,
                            'source_frame': thumb.source_frame,
                            'is_valid': thumb.is_valid,
                            'created_at': thumb.created_at.isoformat() if thumb.created_at else None,
                            'extra_data': thumb.extra_data
                        }
                        data['thumbnails'].append(thumbnail_data)
                
                # Get favorites if requested
                if include_favorites:
                    favorite_records = session.query(Favorite).all()
                    for fav in favorite_records:
                        favorite_data = {
                            'id': fav.id,
                            'entity_id': fav.entity_id,
                            'user_id': fav.user_id,
                            'project_id': fav.project_id,
                            'created_at': fav.created_at.isoformat() if fav.created_at else None,
                        }
                        data['favorites'].append(favorite_data)
                
                # Get tags if requested
                if include_tags:
                    tag_records = session.query(Tag).all()
                    for tag in tag_records:
                        tag_data = {
                            'id': tag.id,
                            'entity_id': tag.entity_id,
                            'name': tag.name,
                            'color': tag.color,
                            'created_at': tag.created_at.isoformat() if tag.created_at else None,
                        }
                        data['tags'].append(tag_data)
                
        except Exception as e:
            logger.error(f"Error collecting project data: {e}")
            raise
        
        return data
    
    def _export_json(self, data: Dict[str, Any], output_path: Path) -> bool:
        """Export data as JSON."""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"JSON export completed: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting JSON: {e}")
            return False
    
    def _export_csv(self, data: Dict[str, Any], output_path: Path) -> bool:
        """Export data as CSV (entities only)."""
        try:
            entities = data.get('entities', [])
            if not entities:
                logger.warning("No entities to export")
                return False
            
            # Create CSV with entity data
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                if entities:
                    fieldnames = entities[0].keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(entities)
            
            logger.info(f"CSV export completed: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting CSV: {e}")
            return False
    
    def _export_entities_csv(self, entities: List[Dict[str, Any]], output_path: Path) -> bool:
        """Export entity list as CSV."""
        try:
            if not entities:
                logger.warning("No entities to export")
                return False
            
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = entities[0].keys()
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(entities)
            
            logger.info(f"Entity CSV export completed: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting entity CSV: {e}")
            return False
    
    def _export_xml(self, data: Dict[str, Any], output_path: Path) -> bool:
        """Export data as XML."""
        try:
            # Create root element
            root = ET.Element('stockshot_export')
            
            # Add export info
            export_info = ET.SubElement(root, 'export_info')
            for key, value in data.get('export_info', {}).items():
                elem = ET.SubElement(export_info, key)
                elem.text = str(value)
            
            # Add entities
            entities_elem = ET.SubElement(root, 'entities')
            for entity in data.get('entities', []):
                entity_elem = ET.SubElement(entities_elem, 'entity')
                for key, value in entity.items():
                    elem = ET.SubElement(entity_elem, key)
                    elem.text = str(value) if value is not None else ''
            
            # Add metadata
            metadata_elem = ET.SubElement(root, 'metadata')
            for meta in data.get('metadata', []):
                meta_elem = ET.SubElement(metadata_elem, 'metadata_record')
                for key, value in meta.items():
                    elem = ET.SubElement(meta_elem, key)
                    elem.text = str(value) if value is not None else ''
            
            # Add thumbnails
            thumbnails_elem = ET.SubElement(root, 'thumbnails')
            for thumb in data.get('thumbnails', []):
                thumb_elem = ET.SubElement(thumbnails_elem, 'thumbnail')
                for key, value in thumb.items():
                    elem = ET.SubElement(thumb_elem, key)
                    elem.text = str(value) if value is not None else ''
            
            # Add favorites
            favorites_elem = ET.SubElement(root, 'favorites')
            for fav in data.get('favorites', []):
                fav_elem = ET.SubElement(favorites_elem, 'favorite')
                for key, value in fav.items():
                    elem = ET.SubElement(fav_elem, key)
                    elem.text = str(value) if value is not None else ''
            
            # Add tags
            tags_elem = ET.SubElement(root, 'tags')
            for tag in data.get('tags', []):
                tag_elem = ET.SubElement(tags_elem, 'tag')
                for key, value in tag.items():
                    elem = ET.SubElement(tag_elem, key)
                    elem.text = str(value) if value is not None else ''
            
            # Write XML file
            tree = ET.ElementTree(root)
            ET.indent(tree, space="  ", level=0)  # Pretty print
            tree.write(output_path, encoding='utf-8', xml_declaration=True)
            
            logger.info(f"XML export completed: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting XML: {e}")
            return False
    
    def get_export_summary(self, project_name: Optional[str] = None) -> Dict[str, int]:
        """Get summary of data available for export."""
        summary = {
            'entities': 0,
            'metadata_records': 0,
            'thumbnails': 0,
            'favorites': 0,
            'tags': 0
        }
        
        try:
            with self.database_manager.get_session() as session:
                summary['entities'] = session.query(Entity).count()
                summary['metadata_records'] = session.query(Metadata).count()
                summary['thumbnails'] = session.query(Thumbnail).count()
                summary['favorites'] = session.query(Favorite).count()
                summary['tags'] = session.query(Tag).count()
                
        except Exception as e:
            logger.error(f"Error getting export summary: {e}")
        
        return summary
    
    def validate_export_path(self, output_path: Path, format: str) -> bool:
        """Validate export path and format."""
        try:
            # Check if directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check format
            if format not in self.supported_formats:
                return False
            
            # Check if we can write to the path
            test_file = output_path.with_suffix('.tmp')
            try:
                test_file.touch()
                test_file.unlink()
                return True
            except (PermissionError, OSError):
                return False
                
        except Exception as e:
            logger.error(f"Error validating export path: {e}")
            return False
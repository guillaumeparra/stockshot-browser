"""
Image sequence detection for Stockshot Browser.
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

logger = logging.getLogger(__name__)


@dataclass
class SequenceInfo:
    """Information about a detected image sequence."""
    name: str
    base_path: Path
    files: List[Path]
    frame_range: Tuple[int, int]
    frame_count: int
    missing_frames: List[int]
    pattern: str


class SequenceDetector:
    """Detects and groups image sequences using configurable patterns."""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        
        # Get patterns from configuration
        self.default_patterns = self.config_manager.get('sequence_detection.default_patterns', [
            r"(.+)\.(\d{4,})\.(exr|png|jpg|jpeg|tiff|tif|dpx)$",
            r"(.+)_(\d{4,})\.(exr|png|jpg|jpeg|tiff|tif|dpx)$",
            r"(.+)\.v\d+\.(\d{4,})\.(exr|png|jpg|jpeg|tiff|tif|dpx)$",
        ])
        
        self.custom_patterns = self.config_manager.get('sequence_detection.custom_patterns', [])
        
        # Combine all patterns
        self.patterns = self.default_patterns + self.custom_patterns
        
        # Configuration
        self.min_sequence_length = self.config_manager.get('sequence_detection.min_sequence_length', 2)
        self.max_gap_frames = self.config_manager.get('sequence_detection.max_gap_frames', 10)
        self.supported_extensions = set(
            ext.lower() for ext in self.config_manager.get('sequence_detection.supported_extensions', [
                '.exr', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.dpx'
            ])
        )
            
    def detect_sequences(self, image_files: List[Path]) -> List[Dict]:
        """
        Detect image sequences from a list of image files.
        
        Args:
            image_files: List of image file paths
            
        Returns:
            List of sequence information dictionaries
        """
        if not image_files:
            return []
                
        # Filter files by supported extensions
        supported_files = [
            f for f in image_files 
            if f.suffix.lower() in self.supported_extensions
        ]
        
        if not supported_files:
            return []
        
        # Group files by sequence patterns
        sequence_groups = self._group_files_by_pattern(supported_files)
        
        # Process each group to create sequence info
        sequences = []
        for group_key, file_info_list in sequence_groups.items():
            sequence_info = self._create_sequence_info(group_key, file_info_list)
            if sequence_info:
                sequences.append(sequence_info)
        
        return sequences
    
    def _group_files_by_pattern(self, files: List[Path]) -> Dict[str, List[Dict]]:
        """Group files by sequence patterns."""
        sequence_groups = defaultdict(list)
        unmatched_files = []
        
        for file_path in files:
            matched = False
            
            for pattern in self.patterns:
                try:
                    match = re.match(pattern, file_path.name, re.IGNORECASE)
                    if match:
                        groups = match.groups()
                        if len(groups) >= 3:  # base_name, frame_number, extension
                            base_name = groups[0]
                            frame_str = groups[1]
                            extension = groups[2]
                            
                            try:
                                frame_number = int(frame_str)
                                padding = len(frame_str)
                                
                                # Create unique key for this sequence
                                sequence_key = f"{base_name}_{extension}_{padding}_{pattern}"
                                
                                sequence_groups[sequence_key].append({
                                    'file_path': file_path,
                                    'base_name': base_name,
                                    'frame_number': frame_number,
                                    'frame_str': frame_str,
                                    'extension': extension,
                                    'padding': padding,
                                    'pattern': pattern
                                })
                                
                                matched = True
                                break
                                
                            except ValueError:
                                continue
                                
                except re.error as e:
                    continue
            
            if not matched:
                unmatched_files.append(file_path)
        
        if unmatched_files:
            logger.debug(f"{len(unmatched_files)} files did not match any sequence pattern")
        
        return sequence_groups
    
    def _create_sequence_info(self, group_key: str, file_info_list: List[Dict]) -> Optional[Dict]:
        """Create sequence information from grouped files."""
        if len(file_info_list) < self.min_sequence_length:
            return None
        
        # Sort by frame number
        file_info_list.sort(key=lambda x: x['frame_number'])
        
        # Get sequence information
        first_file = file_info_list[0]
        last_file = file_info_list[-1]
        
        base_name = first_file['base_name']
        extension = first_file['extension']
        pattern = first_file['pattern']
        padding = first_file['padding']
        
        frame_numbers = [info['frame_number'] for info in file_info_list]
        frame_range = (min(frame_numbers), max(frame_numbers))
        
        # Check for missing frames
        missing_frames = []
        expected_frames = set(range(frame_range[0], frame_range[1] + 1))
        actual_frames = set(frame_numbers)
        missing_frames = sorted(expected_frames - actual_frames)
        
        # Check if gaps are acceptable
        if missing_frames:
            max_gap = self._get_max_gap_size(frame_numbers)
            if max_gap > self.max_gap_frames:
                return None
        
        # Create sequence name
        if padding > 0:
            sequence_name = f"{base_name}.{'#' * padding}.{extension}"
        else:
            sequence_name = f"{base_name}_sequence.{extension}"
        
        # Get base path (directory of first file)
        base_path = first_file['file_path'].parent
        
        return {
            'name': sequence_name,
            'base_path': base_path,
            'files': [info['file_path'] for info in file_info_list],
            'frame_range': frame_range,
            'frame_count': len(file_info_list),
            'missing_frames': missing_frames,
            'pattern': pattern,
            'base_name': base_name,
            'extension': extension,
            'padding': padding
        }
    
    def _get_max_gap_size(self, frame_numbers: List[int]) -> int:
        """Get the maximum gap size in frame sequence."""
        if len(frame_numbers) < 2:
            return 0
        
        max_gap = 0
        for i in range(1, len(frame_numbers)):
            gap = frame_numbers[i] - frame_numbers[i-1] - 1
            max_gap = max(max_gap, gap)
        
        return max_gap
    
    def add_custom_pattern(self, pattern: str) -> bool:
        """
        Add a custom sequence detection pattern.
        
        Args:
            pattern: Regular expression pattern
            
        Returns:
            True if pattern was added successfully
        """
        try:
            # Test the pattern
            re.compile(pattern)
            
            if pattern not in self.patterns:
                self.patterns.append(pattern)
                self.custom_patterns.append(pattern)
                
                # Update configuration
                self.config_manager.set('sequence_detection.custom_patterns', self.custom_patterns, persist=True)
                
                return True
            else:
                return False
                
        except re.error as e:
            return False
    
    def remove_custom_pattern(self, pattern: str) -> bool:
        """
        Remove a custom sequence detection pattern.
        
        Args:
            pattern: Pattern to remove
            
        Returns:
            True if pattern was removed successfully
        """
        if pattern in self.custom_patterns:
            self.custom_patterns.remove(pattern)
            self.patterns.remove(pattern)
            
            # Update configuration
            self.config_manager.set('sequence_detection.custom_patterns', self.custom_patterns, persist=True)
            
            return True
        else:
            return False
    
    def get_patterns(self) -> Dict[str, List[str]]:
        """Get all sequence detection patterns."""
        return {
            'default_patterns': self.default_patterns.copy(),
            'custom_patterns': self.custom_patterns.copy(),
            'all_patterns': self.patterns.copy()
        }
    
    def test_pattern(self, pattern: str, test_files: List[str]) -> Dict:
        """
        Test a pattern against a list of filenames.
        
        Args:
            pattern: Regular expression pattern to test
            test_files: List of filenames to test against
            
        Returns:
            Dictionary with test results
        """
        try:
            compiled_pattern = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return {
                'valid': False,
                'error': str(e),
                'matches': []
            }
        
        matches = []
        for filename in test_files:
            match = compiled_pattern.match(filename)
            if match:
                matches.append({
                    'filename': filename,
                    'groups': match.groups(),
                    'match': True
                })
            else:
                matches.append({
                    'filename': filename,
                    'groups': None,
                    'match': False
                })
        
        return {
            'valid': True,
            'error': None,
            'matches': matches,
            'match_count': sum(1 for m in matches if m['match'])
        }
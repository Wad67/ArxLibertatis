# Copyright 2019-2020 Arx Libertatis Team (see the AUTHORS file)
#
# This file is part of Arx Libertatis.
#
# Arx Libertatis is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Arx Libertatis is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Arx Libertatis. If not, see <http://www.gnu.org/licenses/>.

import os
import logging
from pathlib import Path

class ASLReader:
    """Module for reading ASL (Arx Scripting Language) files with ISO-8559-15 encoding"""
    
    def __init__(self, data_path):
        self.data_path = Path(data_path)
        self.log = logging.getLogger('ASLReader')
        
    def get_asl_file_path(self, entity_ident, object_id=None):
        """Get the ASL file path for a given entity identifier"""
        # If object_id is provided, use it to construct the direct path
        if object_id:
            direct_path = self._construct_direct_path(object_id, entity_ident)
            if direct_path and direct_path.exists():
                return direct_path
            
            # Try root/global script in parent folder if specific numbered version doesn't exist
            root_path = self._construct_root_path(object_id)
            if root_path and root_path.exists():
                return root_path
        
        # No fallback search - return None if specific path not found
        return None
    
    def _construct_direct_path(self, object_id, entity_ident):
        """Construct direct ASL file path from object_id and entity_ident"""
        # object_id is the full path like "npc/human_base" or "items/provisions/bone"
        # The last part is the base name, everything before is the directory structure
        
        object_parts = object_id.split('/')
        if len(object_parts) >= 1:
            base_name = object_parts[-1]  # Last part is the base name (e.g., "bone", "human_base")
            dir_path = '/'.join(object_parts)  # Full directory path (e.g., "items/provisions/bone")
            
            folder_name = f"{base_name}_{entity_ident:04d}"
            asl_filename = f"{base_name}.asl"
            
            # Construct: /build/graph/obj3d/interactive/{full_dir_path}/{base_name}_{entity_ident:04d}/{base_name}.asl
            asl_path = (self.data_path / "graph" / "obj3d" / "interactive" / 
                       dir_path / folder_name / asl_filename)
            
            return asl_path
        
        return None
    
    def _construct_root_path(self, object_id):
        """Construct path to root/global ASL script for entity type"""
        object_parts = object_id.split('/')
        if len(object_parts) >= 1:
            base_name = object_parts[-1]  # Last part is the base name
            dir_path = '/'.join(object_parts)  # Full directory path
            
            # Try root script in base folder: /build/graph/obj3d/interactive/{full_dir_path}/{base_name}.asl
            root_asl_path = (self.data_path / "graph" / "obj3d" / "interactive" / 
                           dir_path / f"{base_name}.asl")
            
            return root_asl_path
        
        return None
    
    def _search_entity_folders(self, entity_ident):
        """Search for ASL files in entity-specific folders"""
        interactive_path = self.data_path / "graph" / "obj3d" / "interactive"
        
        if not interactive_path.exists():
            self.log.warning(f"Interactive path does not exist: {interactive_path}")
            return None
            
        # Search in npc, items, and fix_inter directories
        search_dirs = ["npc", "items", "fix_inter"]
        
        for search_dir in search_dirs:
            base_path = interactive_path / search_dir
            if not base_path.exists():
                continue
                
            # Look for entity folders in format: {entity_type}_{entity_id:04d}
            for entity_dir in base_path.iterdir():
                if not entity_dir.is_dir():
                    continue
                    
                # Check if this directory contains the entity we're looking for
                if self._is_entity_folder(entity_dir, entity_ident):
                    # Look for ASL files in this directory
                    asl_files = list(entity_dir.glob("*.asl"))
                    if asl_files:
                        return asl_files[0]  # Return first ASL file found
        
        return None
    
    def _is_entity_folder(self, entity_dir, entity_ident):
        """Check if a directory contains the entity we're looking for"""
        dir_name = entity_dir.name
        
        # Check if directory name ends with the entity identifier
        entity_suffix = f"_{entity_ident:04d}"
        if dir_name.endswith(entity_suffix):
            return True
            
        # Also check if there's a subdirectory with the entity identifier
        entity_subdir = entity_dir / f"{dir_name}_{entity_ident:04d}"
        if entity_subdir.exists():
            return True
            
        return False
    
    def find_asl_by_name(self, entity_name):
        """Find ASL file by entity name (without specific ID)"""
        interactive_path = self.data_path / "graph" / "obj3d" / "interactive"
        
        if not interactive_path.exists():
            return None
            
        # Search in all interactive subdirectories
        for subdir in interactive_path.iterdir():
            if not subdir.is_dir():
                continue
                
            # Look for entity folders that match the name
            for entity_dir in subdir.iterdir():
                if not entity_dir.is_dir():
                    continue
                    
                # Check if directory name starts with the entity name
                if entity_dir.name.lower().startswith(entity_name.lower()):
                    # Look for ASL files in this directory
                    asl_files = list(entity_dir.glob("*.asl"))
                    if asl_files:
                        return asl_files[0]
                    
                    # Also check subdirectories (for numbered instances)
                    for subdir in entity_dir.iterdir():
                        if subdir.is_dir() and subdir.name.startswith(entity_dir.name + "_"):
                            asl_files = list(subdir.glob("*.asl"))
                            if asl_files:
                                return asl_files[0]
        
        return None
    
    def read_asl_file(self, entity_ident, object_id=None):
        """Read and return the contents of an ASL file for the given entity identifier"""
        asl_path = self.get_asl_file_path(entity_ident, object_id)
        
        if not asl_path:
            self.log.warning(f"ASL file not found for entity {entity_ident:04d}")
            return None
            
        try:
            with open(asl_path, 'r', encoding='iso-8859-15') as f:
                content = f.read()
                self.log.info(f"Successfully read ASL file: {asl_path}")
                return content
        except Exception as e:
            self.log.error(f"Error reading ASL file {asl_path}: {e}")
            return None
    
    def get_asl_file_info(self, entity_ident):
        """Get information about an ASL file without reading its contents"""
        asl_path = self.get_asl_file_path(entity_ident)
        
        if not asl_path:
            return None
            
        try:
            stat = asl_path.stat()
            return {
                'path': str(asl_path),
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'exists': True
            }
        except Exception as e:
            self.log.error(f"Error getting ASL file info {asl_path}: {e}")
            return None
    
    def list_all_asl_files(self):
        """List all ASL files found in the data directory"""
        asl_files = []
        
        try:
            for root, dirs, files in os.walk(self.data_path):
                for file in files:
                    if file.endswith('.asl'):
                        full_path = Path(root) / file
                        # Extract entity ID from filename
                        try:
                            entity_id = int(file[:-4])  # Remove .asl extension
                            asl_files.append({
                                'entity_id': entity_id,
                                'path': str(full_path),
                                'relative_path': str(full_path.relative_to(self.data_path))
                            })
                        except ValueError:
                            # Skip files that don't have numeric names
                            continue
        except Exception as e:
            self.log.error(f"Error listing ASL files: {e}")
            
        return sorted(asl_files, key=lambda x: x['entity_id'])
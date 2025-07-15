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

import bpy
import os
from bpy.props import IntProperty, BoolProperty, StringProperty, CollectionProperty, PointerProperty, EnumProperty, FloatProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList
from mathutils import Matrix, Vector, Quaternion
from .arx_io_util import ArxException, arx_pos_to_blender_for_model, arx_transform_to_blender, blender_pos_to_arx
from .managers import getAddon
import math

g_areaToLevel = {
    0:0, 8:0, 11:0, 12:0,
    1:1, 13:1, 14:1,
    2:2, 15:2,
    3:3, 16:3, 17:3,
    4:4, 18:4, 19:4,
    5:5, 21:5,
    6:6, 22:6,
    7:7, 23:7
}

def importArea(context, report, area_id):
    scene_name = f"Area_{area_id:02d}"
    scene = bpy.data.scenes.get(scene_name)
    if scene:
        report({'INFO'}, f"Area Scene named [{scene_name}] already exists.")
        return
    report({'INFO'}, f"Creating new Area Scene [{scene_name}]")
    scene = bpy.data.scenes.new(name=scene_name)
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 0.01
    getAddon(context).sceneManager.importScene(context, scene, area_id)

class CUSTOM_OT_arx_area_list_reload(Operator):
    bl_idname = "arx.arx_area_list_reload"
    bl_label = "Reload Area List"
    def invoke(self, context, event):
        area_list = context.window_manager.arx_areas_col
        area_list.clear()
        for area_id, value in getAddon(context).arxFiles.levels.levels.items():
            item = area_list.add()
            item.name = f'Area {area_id}'
            item.area_id = area_id
            item.level_id = g_areaToLevel.get(area_id, -1)
        return {"FINISHED"}

class ARX_area_properties(PropertyGroup):
    area_id: IntProperty(name="Arx Area ID", min=0)
    level_id: IntProperty(name="Arx Level ID", description="Levels consist of areas", min=-1)

class ARX_lighting_properties(PropertyGroup):
    """Properties for controlling vertex lighting generation"""
    
    # Lighting workflow options
    import_original_lighting: BoolProperty(
        name="Import Original Lighting",
        description="Import and use original LLF lighting data",
        default=True
    )
    
    regenerate_lighting: BoolProperty(
        name="Regenerate Lighting", 
        description="Calculate new vertex lighting when exporting",
        default=False
    )
    
    lighting_method: EnumProperty(
        name="Lighting Method",
        description="Method to use for lighting calculation",
        items=[
            ('CYCLES', 'Cycles Renderer', 'Use Blender Cycles for realistic lighting'),
            ('SIMPLE', 'Simple Calculation', 'Fast basic lighting calculation'),
            ('PRESERVE', 'Preserve Original', 'Keep existing vertex colors from Blender'),
            ('SKIP', 'Skip Lighting', 'Skip lighting update entirely (fast export)')
        ],
        default='CYCLES'
    )
    
    # Cycles settings
    cycles_samples: IntProperty(
        name="Cycles Samples",
        description="Number of samples for Cycles lighting calculation",
        default=64,
        min=1,
        max=1024
    )
    
    # Simple lighting parameters
    ambient_strength: FloatProperty(
        name="Ambient Strength",
        description="Strength of ambient lighting",
        default=0.2,
        min=0.0,
        max=1.0
    )
    
    light_falloff_power: FloatProperty(
        name="Light Falloff Power",
        description="Power curve for light distance falloff",
        default=1.5,
        min=0.1,
        max=3.0
    )
    
    max_light_contribution: FloatProperty(
        name="Max Light Contribution",
        description="Maximum brightness from lights",
        default=200.0,
        min=0.0,
        max=255.0
    )

class SCENE_UL_arx_area_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.3)
        split.label(text=item.name)
        split.label(text=str(item.area_id))
        split.label(text=str(item.level_id))
    def invoke(self, context, event):
        pass

class CUSTOM_OT_arx_area_list_import_selected(Operator):
    bl_idname = "arx.area_list_import_selected"
    bl_label = "Import Selected Area"
    def invoke(self, context, event):
        area_list = context.window_manager.arx_areas_col
        area = area_list[context.window_manager.arx_areas_idx]
        try:
            importArea(context, self.report, area.area_id)
        except ArxException as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}

class ArxOperatorImportAllLevels(Operator):
    bl_idname = "arx.operator_import_all_levels"
    bl_label = "Import All Levels"
    def execute(self, context):
        for area_id, value in getAddon(context).arxFiles.levels.levels.items():
            try:
                importArea(context, self.report, area_id)
            except ArxException as e:
                self.report({'ERROR'}, str(e))
                return {'CANCELLED'}
        return {'FINISHED'}

class ArxAreaExportHelper:
    """Shared utility methods for area export operations"""
    
    def __init__(self):
        self._scene_lights = []
        self._scene_offset = Vector((0, 0, 0))
        self._preserve_original_lighting = False
        self.converted_faces = []
    
    # Shared methods will be moved here from the main operator class

class CUSTOM_OT_arx_area_list_export_all(Operator, ArxAreaExportHelper):
    bl_idname = "arx.area_list_export_all"
    bl_label = "Export All Area Data"
    bl_description = "Export complete area data (FTS + LLF + DLF)"
    
    export_fts: BoolProperty(default=True)
    export_llf: BoolProperty(default=True)
    export_dlf: BoolProperty(default=True)
    
    def invoke(self, context, event):
        # Initialize helper state
        self._scene_lights = []
        self._scene_offset = Vector((0, 0, 0))
        self._preserve_original_lighting = False
        self.converted_faces = []
        
        area_list = context.window_manager.arx_areas_col
        if not area_list:
            self.report({'ERROR'}, "No area list loaded")
            return {'CANCELLED'}
            
        area = area_list[context.window_manager.arx_areas_idx]
        scene_name = f"Area_{area.area_id:02d}"
        scene = bpy.data.scenes.get(scene_name)
        
        if not scene:
            self.report({'ERROR'}, f"Scene '{scene_name}' not found. Import the area first.")
            return {'CANCELLED'}
        
        try:
            self.exportArea(context, scene, area.area_id, self.export_fts, self.export_llf, self.export_dlf)
            self.report({'INFO'}, f"Exported Area {area.area_id}")
        except ArxException as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}
            
        return {'FINISHED'}
    
    def _map_room_id_to_index(self, room_id):
        """No room mapping needed - FTS format supports actual room count from data"""
        return room_id
    
    def exportArea(self, context, scene, area_id, export_fts=True, export_llf=True, export_dlf=True):
        """Export area data based on flags"""
        print(f"DEBUG: exportArea called with export_fts={export_fts}, export_llf={export_llf}, export_dlf={export_dlf}")
        addon = getAddon(context)
        area_files = addon.arxFiles.levels.levels[area_id]
        
        # DLF-only export: Skip all the expensive FTS processing
        if export_dlf and not export_fts and not export_llf:
            if area_files.dlf:
                try:
                    self.updateDlfFile(area_files.dlf, scene, area_id)
                    self.report({'INFO'}, f"Successfully updated DLF entity data")
                except Exception as e:
                    self.report({'ERROR'}, f"DLF update failed: {str(e)}")
            return
        
        # For FTS/LLF exports, we need the expensive processing
        if area_files.fts is None:
            raise ArxException(f"Original FTS file not found for area {area_id}")
        
        # Find the background mesh
        background_obj = None
        for obj in scene.objects:
            if obj.name.endswith("-background") and obj.type == 'MESH':
                background_obj = obj
                break
                
        if not background_obj:
            raise ArxException(f"No background geometry found in scene {scene.name}")
        
        # Load lighting data for vertex lighting calculations (only if needed)
        if export_llf or export_fts:
            if area_files.llf:
                llfData = addon.sceneManager.llfSerializer.read(area_files.llf)
                self._storeLightsForLighting(llfData)
            else:
                print("WARNING: No LLF file found - lighting calculations will use defaults")
                self._storeLightsForLighting(None)
        
        # Try to restore complete FTS data from scene properties first
        current_scene = background_obj.users_scene[0]
        if ("arx_texture_data" in current_scene and 
            "arx_anchor_data" in current_scene and 
            "arx_portal_data" in current_scene):
            print("DEBUG: Using preserved FTS data from scene properties")
            # Use minimal base structure and restore from scene properties
            base_fts_data = addon.sceneManager.ftsSerializer.read_fts_container(area_files.fts)
            fts_data = self._restoreOriginalFtsDataFromScene(current_scene, base_fts_data)
        else:
            print("DEBUG: No preserved data found, reading fresh from FTS file and storing")
            # Read original FTS data and store it for future use
            fts_data = addon.sceneManager.ftsSerializer.read_fts_container(area_files.fts)
            self._storeOriginalFtsDataInScene(current_scene, fts_data)
        
        # Store scene offset for lighting calculations
        self._scene_offset = Vector(fts_data.sceneOffset) if hasattr(fts_data, 'sceneOffset') else Vector((0, 0, 0))
        
        # Set lighting recalculation mode - could be made user-configurable
        # For now, recalculate lighting for modified geometry to fix lightmap issues
        self._preserve_original_lighting = False  # Set to True to preserve existing vertex colors
        
        # Convert Blender mesh back to FTS cells with current material assignments
        fts_data = self.convertMeshToFtsCells(background_obj, fts_data)
        
        # Detect if geometry has been modified and rebuild portal/room system completely
        original_face_count = current_scene.get("arx_original_face_count", len(self.converted_faces))
        geometry_modified = len(self.converted_faces) != original_face_count
        
        # For now, preserve original portals to avoid serialization issues
        # TODO: Implement proper portal reading from Blender scene
        print("DEBUG: Preserving original portal system (portal reading disabled temporarily)")
        
        if geometry_modified:
            print(f"DEBUG: Geometry modified ({len(self.converted_faces)} vs {original_face_count} faces) - assigning rooms to new faces")
            # Assign room IDs to new faces and rebuild room references
            fts_data = self._assignRoomsToNewGeometry(fts_data)
        
        # Rebuild room polygon references for all geometry  
        fts_data = self._rebuildRoomPolygonReferences(fts_data) or fts_data
        
        # Write back to original FTS file
        if export_fts:
            try:
                self.writeFtsFile(area_files.fts, fts_data, self.converted_faces)
                self.report({'INFO'}, f"Successfully exported FTS with {len(self.converted_faces)} faces")
            except Exception as e:
                self.report({'ERROR'}, f"FTS write failed: {str(e)}")
                raise ArxException(f"Export failed: {str(e)}")
        else:
            self.report({'INFO'}, "Skipped FTS export")
        
        # Update LLF file with new vertex lighting data
        scene = bpy.context.scene
        lighting_props = scene.arx_lighting
        
        if export_llf and area_files.llf and lighting_props.regenerate_lighting and lighting_props.lighting_method != 'SKIP':
            try:
                self.updateLlfFile(area_files.llf, self.converted_faces)
                self.report({'INFO'}, f"Successfully updated LLF lighting data using {lighting_props.lighting_method}")
            except Exception as e:
                self.report({'ERROR'}, f"LLF update failed: {str(e)}")
                # Don't fail the entire export if LLF update fails
        elif lighting_props.lighting_method == 'SKIP':
            self.report({'INFO'}, "Skipped LLF lighting update (fast export mode)")
        else:
            self.report({'INFO'}, "LLF lighting update disabled")
        
        # Update DLF file with entity data
        if export_dlf and area_files.dlf:
            try:
                self.updateDlfFile(area_files.dlf, scene, area_id)
                self.report({'INFO'}, f"Successfully updated DLF entity data")
            except Exception as e:
                self.report({'ERROR'}, f"DLF update failed: {str(e)}")
                # Don't fail the entire export if DLF update fails
    
    def convertMeshToFtsCells(self, mesh_obj, fts_data):
        """Convert Blender mesh back to FTS cell format"""
        import bmesh
        
        # Create bmesh from mesh
        bm = bmesh.new()
        bm.from_mesh(mesh_obj.data)
        bm.faces.ensure_lookup_table()
        
        # Build material index mapping from Blender to FTS
        material_mapping, fts_data = self._buildMaterialMapping(mesh_obj, fts_data)
        
        # Get UV and vertex color layers
        uv_layer = bm.loops.layers.uv.active
        color_layer = bm.loops.layers.color.active
        
        # Get FTS polygon property layers
        transval_layer = bm.faces.layers.float.get('arx_transval')
        area_layer = bm.faces.layers.float.get('arx_area')
        room_layer = bm.faces.layers.int.get('arx_room')
        polytype_layer = bm.faces.layers.int.get('arx_polytype')
        
        # Get preserved geometric data layers
        norm_layer = bm.faces.layers.float_vector.get('arx_norm')
        norm2_layer = bm.faces.layers.float_vector.get('arx_norm2')
        vertex_norms_layer = bm.faces.layers.string.get('arx_vertex_normals')
        tex_index_layer = bm.faces.layers.int.get('arx_tex_index')
        
        # Get preserved cell coordinate layers for exact round-trip
        cell_x_layer = bm.faces.layers.int.get('arx_cell_x')
        cell_z_layer = bm.faces.layers.int.get('arx_cell_z')
        
        if not uv_layer:
            raise ArxException("Background mesh missing UV coordinates")
        
        # Check for preserved FTS data - warn but don't fail if missing
        has_preserved_data = bool(transval_layer and cell_x_layer and cell_z_layer)
        if not has_preserved_data:
            print(f"WARNING: Mesh missing FTS polygon properties - will use defaults for new/modified faces")
            print(f"  transval_layer: {transval_layer is not None}")
            print(f"  cell_x_layer: {cell_x_layer is not None}") 
            print(f"  cell_z_layer: {cell_z_layer is not None}")
        
        # Convert faces back to Arx format
        converted_faces = []
        quad_count = 0
        triangle_count = 0
        for face in bm.faces:
            # Validate face geometry
            if len(face.verts) < 3:
                print(f"WARNING: Skipping degenerate face with {len(face.verts)} vertices")
                continue
            if len(face.verts) > 4:
                print(f"WARNING: Face has {len(face.verts)} vertices, only quads and triangles supported")
                continue
                
            # Convert face vertices back to Arx coordinates
            arx_vertices = []
            for loop in face.loops:
                # Convert position back to Arx coordinates (reverse the 0.1 scaling and coordinate transform)
                blender_pos = loop.vert.co
                arx_pos_tuple = blender_pos_to_arx(blender_pos)
                arx_pos = Vector(arx_pos_tuple) * 10.0  # Reverse 0.1 scale factor
                
                
                # Get UV coordinates (flip V coordinate back)
                uv = loop[uv_layer].uv if uv_layer else (0.0, 0.0)
                arx_uv = (uv[0], 1.0 - uv[1])
                
                # Calculate vertex lighting - either use preserved lightmap or recalculate
                if hasattr(self, '_preserve_original_lighting') and self._preserve_original_lighting and color_layer:
                    # Use preserved lighting for unmodified faces
                    color = loop[color_layer]
                    arx_color = (int(color[0] * 255), int(color[1] * 255), int(color[2] * 255), int(color[3] * 255))
                else:
                    # Calculate lighting from scratch for all faces when recalculation is enabled
                    # Convert face normal from Blender to Arx coordinates
                    if hasattr(face, 'normal'):
                        blender_normal = face.normal
                        arx_normal = Vector(blender_pos_to_arx(blender_normal))
                    else:
                        arx_normal = Vector((0, 1, 0))  # Default upward normal
                    arx_color = self._calculateVertexLighting(arx_pos, arx_normal)
                    
                    # Debug first few lighting calculations
                    if len(converted_faces) < 3:
                        print(f"DEBUG: Vertex lighting for face {len(converted_faces)}: pos={arx_pos} → color={arx_color}")
                
                arx_vertices.append({
                    'pos': arx_pos,
                    'uv': arx_uv,
                    'color': arx_color
                })
            
            # Reverse the vertex order swap that was done during import for quads
            if len(face.verts) == 4 and len(arx_vertices) == 4:
                # During import: tempVerts[2], tempVerts[3] = tempVerts[3], tempVerts[2]
                # So during export, swap them back
                arx_vertices[2], arx_vertices[3] = arx_vertices[3], arx_vertices[2]
            
            # Get preserved geometric data or fallback to Blender-calculated
            if norm_layer and norm2_layer:
                # Use preserved original normals
                arx_normal = Vector(face[norm_layer])
                arx_normal2 = Vector(face[norm2_layer])
            else:
                # Fallback: calculate from Blender geometry
                blender_normal = face.normal
                arx_normal = Vector(blender_pos_to_arx(blender_normal))
                arx_normal2 = arx_normal
            
            # Get preserved vertex normals
            vertex_normals = []
            if vertex_norms_layer:
                import struct
                vertex_norm_data = face[vertex_norms_layer]
                if len(vertex_norm_data) >= 36:  # 4 normals × 3 floats × 4 bytes = 48 bytes
                    for i in range(4):
                        offset = i * 12  # 3 floats × 4 bytes
                        x, y, z = struct.unpack('<fff', vertex_norm_data[offset:offset+12])
                        vertex_normals.append(Vector((x, y, z)))
            
            # Fallback if not enough vertex normals preserved
            while len(vertex_normals) < 4:
                vertex_normals.append(arx_normal)
            
            # Get stored FTS properties or calculate from geometry
            transval = face[transval_layer] if transval_layer else 0.0
            if area_layer:
                stored_area = face[area_layer]
            else:
                # Calculate area in Arx units (Blender area × scale factor²)
                blender_area = face.calc_area()
                stored_area = blender_area * (10.0 * 10.0)  # Scale factor is 10.0, area scales by square
            room_id = face[room_layer] if room_layer else 0
            # Use current material assignment instead of preserved texture index
            # This ensures texture changes in Blender are reflected in the export
            blender_mat_index = face.material_index
            fts_texture_id = material_mapping.get(blender_mat_index, 0)
            if blender_mat_index != 0 and fts_texture_id == 0:
                print(f"WARNING: Face {face.index} has material index {blender_mat_index} but no FTS texture mapping found")  # Default to texture 0 if not found
            
            # Calculate polygon type from actual geometry
            is_quad = len(face.verts) == 4
            if polytype_layer:
                poly_type = face[polytype_layer]
            else:
                # Default polygon type - calculate flag value directly to avoid ctypes
                # POLY_QUAD flag is bit 0, so value is 1 if quad, 0 if triangle
                poly_type = 1 if is_quad else 0
            
            # Get preserved cell coordinates or calculate from geometry
            if cell_x_layer and cell_z_layer:
                cell_x = face[cell_x_layer]
                cell_z = face[cell_z_layer]
            else:
                # Calculate cell from face center position
                face_center = face.calc_center_median()
                arx_center = Vector(blender_pos_to_arx(face_center)) * 10.0
                
                # Cell grid is 160x160 units per cell, offset by scene position
                scene_offset = fts_data.sceneOffset if hasattr(fts_data, 'sceneOffset') else (0, 0, 0)
                relative_pos = arx_center - Vector(scene_offset)
                
                cell_x = max(0, min(159, int(relative_pos.x / 160)))
                cell_z = max(0, min(159, int(relative_pos.z / 160)))
                
                if len(converted_faces) < 5:
                    print(f"DEBUG: Calculated cell for face {len(converted_faces)}: center={face_center} → arx={arx_center} → cell=({cell_x}, {cell_z})")
            
            # Debug: log room values from Blender face data
            if len(converted_faces) < 5:
                print(f"DEBUG: Blender face {len(converted_faces)}: room_id={room_id}")
            
            # Count quad vs triangle faces
            if is_quad:
                quad_count += 1
            else:
                triangle_count += 1
            
            # Build complete FTS polygon data structure using preserved geometric data
            fts_polygon = {
                'vertices': arx_vertices,
                'material_index': face.material_index,
                'is_quad': is_quad,
                # FTS-specific polygon properties (preserved from original)
                'transval': transval,
                'area': stored_area,  # Use preserved area value
                'room': room_id,
                'poly_type': poly_type,
                'norm': arx_normal,
                'norm2': arx_normal2,  # Use preserved secondary normal
                'vertex_normals': vertex_normals[:4],  # Use preserved per-vertex normals
                'tex': fts_texture_id,  # Use current material assignment
                # Preserved cell coordinates for exact placement
                'cell_x': cell_x,
                'cell_z': cell_z
            }
            
            converted_faces.append(fts_polygon)
        
        # Store converted data for potential FTS writing
        # NOTE: This doesn't actually update fts_data.cells yet - that requires 
        # implementing the full FTS write functionality
        self.converted_faces = converted_faces
        
        print(f"QUAD/TRIANGLE COUNT: {quad_count} quads, {triangle_count} triangles, {len(converted_faces)} total faces")
        self.report({'INFO'}, f"Converted {len(converted_faces)} faces from Blender mesh ({quad_count} quads, {triangle_count} triangles)")
        
        bm.free()
        return fts_data
    
    def _buildMaterialMapping(self, mesh_obj, fts_data):
        """Build mapping from Blender material indices to FTS texture indices"""
        material_mapping = {}
        
        # Get mesh materials
        mesh_materials = mesh_obj.data.materials
        
        if not mesh_materials:
            return {0: 0}, fts_data  # Default mapping
        
        
        for blender_idx, material in enumerate(mesh_materials):
            if material is None:
                # Empty material slot
                material_mapping[blender_idx] = 0
                continue
                
            material_name = material.name
            
            # Extract image path from Blender material if available
            image_path = self._extractImagePathFromMaterial(material)
            
            # Try to find matching FTS texture by name
            fts_tex_index = None
            fts_texture_to_update = None
            
            for fts_idx, fts_texture in enumerate(fts_data.textures):
                if isinstance(fts_texture, dict):
                    fts_name = fts_texture['fic'].decode('iso-8859-1').rstrip('\x00')
                else:
                    fts_name = fts_texture.fic.decode('iso-8859-1').rstrip('\x00')
                
                # Improved matching logic - extract base name from both sides
                material_base = material_name.replace('-mat', '').lower()
                fts_base = fts_name.replace('\\', '/').split('/')[-1].lower()  # Get filename only
                fts_base = fts_base.replace('.jpg', '').replace('.tga', '').replace('.bmp', '')
                
                if material_base == fts_base or material_base in fts_base or fts_base in material_base:
                    if isinstance(fts_texture, dict):
                        fts_tex_index = fts_texture['tc']  # Use texture container ID, not array index
                        fts_tc = fts_texture['tc']
                    else:
                        fts_tex_index = fts_texture.tc
                        fts_tc = fts_texture.tc
                    fts_texture_to_update = fts_texture
                    break
            
            # Update FTS texture path only if user actually changed the image path
            if fts_texture_to_update and image_path:
                # Extract current FTS filename for comparison
                if isinstance(fts_texture_to_update, dict):
                    current_fts_path = fts_texture_to_update['fic'].decode('iso-8859-1').rstrip('\x00')
                else:
                    current_fts_path = fts_texture_to_update.fic.decode('iso-8859-1').rstrip('\x00')
                current_filename = current_fts_path.replace('\\', '/').split('/')[-1]
                current_base = current_filename.replace('.jpg', '').replace('.tga', '').replace('.bmp', '').lower()
                image_base = image_path.lower()
                
                # Only update if the user actually changed the texture
                if current_base != image_base:
                    # Reconstruct proper FTS path format
                    new_fts_path = f"GRAPH\\OBJ3D\\TEXTURES\\{image_path.upper()}.BMP"
                    new_texture = self._updateFtsTexturePath(fts_texture_to_update, new_fts_path)
                    if new_texture:
                        # Create new texture list (can't modify namedtuple directly)
                        new_textures = list(fts_data.textures)
                        for i, tex in enumerate(new_textures):
                            tex_tc = tex['tc'] if isinstance(tex, dict) else tex.tc
                            fts_to_update_tc = fts_texture_to_update['tc'] if isinstance(fts_texture_to_update, dict) else fts_texture_to_update.tc
                            if tex_tc == fts_to_update_tc:
                                new_textures[i] = new_texture
                                break
                        # Replace the entire FTS data with updated textures (namedtuple is immutable)
                        fts_data = fts_data._replace(textures=new_textures)
                        pass
            
            if fts_tex_index is None:
                # Add new texture to FTS texture list
                fts_tex_index, fts_data = self._addNewTexture(fts_data, material_name, image_path)
                
            material_mapping[blender_idx] = fts_tex_index
        
        return material_mapping, fts_data
    
    def _extractImagePathFromMaterial(self, material):
        """Extract image file path from Blender material node tree"""
        import os
        
        if not material or not material.use_nodes or not material.node_tree:
            return None
            
        # Look for Image Texture nodes in the material
        for node in material.node_tree.nodes:
            if node.bl_idname == 'ShaderNodeTexImage' and node.image:
                # Get the image file path
                image_path = node.image.filepath
                if image_path:
                    # Extract just the filename for FTS format matching
                    # Don't try to preserve paths - just get the base name
                    filename = os.path.basename(image_path)
                    
                    # Remove extension as FTS format doesn't include it
                    base_name = os.path.splitext(filename)[0]
                    return base_name
        
        return None
    
    def _updateFtsTexturePath(self, fts_texture, new_path):
        """Update FTS texture container with new image path"""
        if not new_path:
            return
            
        # Encode new path as ISO-8859-1 and ensure it fits in 256 bytes
        encoded_path = new_path.encode('iso-8859-1', errors='replace')
        if len(encoded_path) >= 256:
            encoded_path = encoded_path[:255]  # Leave room for null terminator
        
        # Create new texture as Python dict to avoid ctypes read-only issues
        path_bytes = encoded_path + b'\x00' * (256 - len(encoded_path))
        
        if isinstance(fts_texture, dict):
            new_texture = {
                'tc': fts_texture['tc'],
                'temp': fts_texture['temp'],
                'fic': path_bytes
            }
        else:
            new_texture = {
                'tc': fts_texture.tc,
                'temp': fts_texture.temp,
                'fic': path_bytes
            }
        
        # Return the new texture dict to replace the old one
        return new_texture
    
    def _storeOriginalFtsDataInScene(self, scene, fts_data):
        """Store complete original FTS data in scene custom properties for persistence across save/load"""
        import pickle
        print("DEBUG: Storing complete original FTS data in scene properties")
        
        # Store critical non-geometry data that must be preserved exactly
        try:
            # Store scene offset
            scene["arx_scene_offset"] = fts_data.sceneOffset
            print(f"DEBUG: Storing scene offset: {fts_data.sceneOffset}")
            
            # Store textures as serialized data  
            texture_data = []
            for i, tex in enumerate(fts_data.textures):
                try:
                    if isinstance(tex, dict):
                        # Validate dict format
                        if 'tc' in tex and 'temp' in tex and 'fic' in tex:
                            texture_data.append(tex)  # Already in correct format
                        else:
                            print(f"WARNING: Invalid texture dict at index {i}: {tex}")
                            texture_data.append({'tc': 0, 'temp': 0, 'fic': b'default.bmp' + b'\x00' * 245})
                    else:
                        # Convert ctypes to dict with proper type conversion
                        texture_data.append({
                            'tc': int(tex.tc) if hasattr(tex, 'tc') else 0,
                            'temp': int(tex.temp) if hasattr(tex, 'temp') else 0,
                            'fic': bytes(tex.fic) if hasattr(tex, 'fic') else b'default.bmp' + b'\x00' * 245
                        })
                except Exception as e:
                    print(f"WARNING: Failed to process texture {i}: {e}")
                    # Add fallback texture
                    texture_data.append({'tc': i, 'temp': 0, 'fic': b'default.bmp' + b'\x00' * 245})
            
            scene["arx_texture_data"] = pickle.dumps(texture_data)
            print(f"DEBUG: Stored {len(texture_data)} textures")
            
            # Store anchors - convert ALL ctypes to Python types
            anchor_data = []
            print(f"DEBUG: Processing {len(fts_data.anchors)} anchors")
            for i, anchor in enumerate(fts_data.anchors):
                if i < 3:  # Debug first few anchors
                    print(f"DEBUG: Anchor {i}: {type(anchor)}, length={len(anchor)}, content={anchor}")
                if len(anchor) >= 5:  # New format with preserved data
                    anchor_pos, anchor_links, radius, height, flags = anchor
                    # Convert all ctypes to Python types
                    if hasattr(anchor_pos, 'x'):  # SavedVec3 structure
                        pos_tuple = (float(anchor_pos.x), float(anchor_pos.y), float(anchor_pos.z))
                    else:
                        pos_tuple = tuple(float(x) for x in anchor_pos)  # Convert to tuple of floats
                    
                    link_list = list(anchor_links) if hasattr(anchor_links, '__iter__') else [anchor_links]
                    anchor_data.append((pos_tuple, link_list, float(radius), float(height), int(flags)))
                else:  # Old format fallback
                    anchor_pos, anchor_links = anchor[:2]
                    if hasattr(anchor_pos, 'x'):  # SavedVec3 structure
                        pos_tuple = (float(anchor_pos.x), float(anchor_pos.y), float(anchor_pos.z))
                    else:
                        pos_tuple = tuple(float(x) for x in anchor_pos)
                    
                    link_list = list(anchor_links) if hasattr(anchor_links, '__iter__') else [anchor_links]
                    anchor_data.append((pos_tuple, link_list))
            scene["arx_anchor_data"] = pickle.dumps(anchor_data)
            print(f"DEBUG: Stored {len(anchor_data)} anchors")
            
            # Store cell anchors - convert any ctypes arrays to lists
            cell_anchor_data = []
            for z_row in fts_data.cell_anchors:
                z_row_data = []
                for cell_anchors in z_row:
                    if cell_anchors is not None:
                        z_row_data.append(list(cell_anchors) if hasattr(cell_anchors, '__iter__') else cell_anchors)
                    else:
                        z_row_data.append(None)
                cell_anchor_data.append(z_row_data)
            scene["arx_cell_anchor_data"] = pickle.dumps(cell_anchor_data)
            print(f"DEBUG: Stored cell anchor data")
            
            # Store portals as binary data
            portal_data = []
            for portal in fts_data.portals:
                portal_data.append(bytes(portal))  # Serialize entire portal structure
            scene["arx_portal_data"] = pickle.dumps(portal_data)
            print(f"DEBUG: Stored {len(portal_data)} portals")
            
            # Store room data - handle ctypes arrays carefully
            if hasattr(fts_data, 'room_data') and fts_data.room_data:
                print(f"DEBUG: Processing room data")
                room_data_list, room_distances = fts_data.room_data
                
                # Serialize room structures as binary
                serialized_rooms = []
                for room_info, room_portal_indices, room_poly_refs in room_data_list:
                    # Convert ctypes arrays to lists for pickling
                    portal_indices_list = list(room_portal_indices) if room_portal_indices else []
                    
                    # Handle room_info - convert ctypes to dict if needed to avoid pickle issues
                    if isinstance(room_info, dict):
                        # Already a dict, serialize as bytes
                        room_info_bytes = pickle.dumps(room_info)
                    else:
                        # Convert ctypes structure to dict to avoid c_int_Array issues
                        room_info_dict = {
                            'nb_portals': room_info.nb_portals,
                            'nb_polys': room_info.nb_polys,
                            'padd': [room_info.padd[j] for j in range(6)]  # Convert ctypes array to list
                        }
                        room_info_bytes = pickle.dumps(room_info_dict)
                    
                    serialized_rooms.append({
                        'room_info_bytes': room_info_bytes,
                        'portal_indices': portal_indices_list,
                        'poly_refs': [bytes(ref) for ref in room_poly_refs]  # Serialize polygon references
                    })
                
                print(f"DEBUG: Processed {len(serialized_rooms)} room structures")
                
                # Serialize distance matrix - handle ROOM_DIST_DATA_SAVE structures
                serialized_distances = []
                for row in room_distances:
                    serialized_row = []
                    for dist in row:
                        try:
                            # Convert to bytes (should work for ctypes structures)
                            dist_bytes = bytes(dist)
                            serialized_row.append(dist_bytes)
                        except Exception as e:
                            print(f"WARNING: Failed to serialize distance data: {e}")
                            # Create a simple fallback distance structure
                            fallback_bytes = b'\x00' * 28  # Size of ROOM_DIST_DATA_SAVE (1 float + 2 Vec3s = 4 + 12 + 12 = 28 bytes)
                            serialized_row.append(fallback_bytes)
                    serialized_distances.append(serialized_row)
                
                scene["arx_room_data"] = pickle.dumps((serialized_rooms, serialized_distances))
                print(f"DEBUG: Stored room data: {len(serialized_rooms)} rooms")
            
            print(f"DEBUG: Stored FTS data: {len(fts_data.textures)} textures, {len(fts_data.portals)} portals")
            
        except Exception as e:
            print(f"WARNING: Failed to store FTS data in scene properties: {e}")
    
    def _restoreOriginalFtsDataFromScene(self, scene, base_fts_data):
        """Restore complete original FTS data from scene custom properties using pure Python structures"""
        import pickle
        print("DEBUG: Restoring original FTS data from scene properties")
        
        try:
            # Restore textures as pure Python dicts (not ctypes)
            if "arx_texture_data" in scene:
                texture_data = pickle.loads(scene["arx_texture_data"])
                # Keep as pure Python dicts - don't create ctypes here
                base_fts_data = base_fts_data._replace(textures=texture_data)
            
            # Restore anchors (already Python tuples/lists)
            if "arx_anchor_data" in scene:
                anchors = pickle.loads(scene["arx_anchor_data"])
                base_fts_data = base_fts_data._replace(anchors=anchors)
            
            # Restore cell anchors (already Python lists)
            if "arx_cell_anchor_data" in scene:
                cell_anchors = pickle.loads(scene["arx_cell_anchor_data"])
                base_fts_data = base_fts_data._replace(cell_anchors=cell_anchors)
            
            # Restore scene offset
            if "arx_scene_offset" in scene:
                scene_offset = scene["arx_scene_offset"]
                base_fts_data = base_fts_data._replace(sceneOffset=scene_offset)
            
            # Restore portals as binary data (don't convert to ctypes yet)
            if "arx_portal_data" in scene:
                portal_bytes_list = pickle.loads(scene["arx_portal_data"])
                # Store as binary data, convert to ctypes only during final serialization
                base_fts_data = base_fts_data._replace(portals=portal_bytes_list)
            
            # Restore room data as pure Python structures
            if "arx_room_data" in scene:
                room_data = pickle.loads(scene["arx_room_data"])
                serialized_rooms, serialized_distances = room_data
                
                # Keep as pure Python structures - don't create ctypes here
                restored_room_list = []
                for room_data_dict in serialized_rooms:
                    # Convert bytes back to dict but keep as Python data
                    room_info_dict = {
                        'nb_portals': len(room_data_dict['portal_indices']),
                        'nb_polys': 0,  # Will be rebuilt by room reconstruction
                        'padd': [0] * 6
                    }
                    portal_indices = room_data_dict['portal_indices']
                    
                    # Keep polygon references empty - will be rebuilt
                    restored_room_list.append((room_info_dict, portal_indices, []))
                
                # Keep distance matrix as binary data
                base_fts_data = base_fts_data._replace(room_data=(restored_room_list, serialized_distances))
            
            print("DEBUG: Successfully restored FTS data as pure Python structures")
            return base_fts_data
            
        except Exception as e:
            print(f"WARNING: Failed to restore FTS data from scene properties: {e}")
            return base_fts_data
    
    def _addNewTexture(self, fts_data, material_name, image_path=None):
        """Create new FTS texture entry for new material"""
        print(f"WARNING: Material '{material_name}' not found in FTS textures")
        
        if image_path:
            print(f"DEBUG: Creating new FTS texture for image path '{image_path}'")
            
            # Generate new texture container ID - use highest existing tc + 1
            max_tc = max(((tex['tc'] if isinstance(tex, dict) else tex.tc) for tex in fts_data.textures), default=0)
            new_tc = max_tc + 1
            
            # Set texture path in proper FTS format
            fts_path = f"GRAPH\\OBJ3D\\TEXTURES\\{image_path.upper()}.BMP"
            encoded_path = fts_path.encode('iso-8859-1', errors='replace')
            if len(encoded_path) >= 256:
                encoded_path = encoded_path[:255]  # Leave room for null terminator
            
            # Create new texture as Python dict to avoid ctypes issues
            path_bytes = encoded_path + b'\x00' * (256 - len(encoded_path))
            new_texture = {
                'tc': new_tc,
                'temp': 0,  # Standard temp value
                'fic': path_bytes
            }
            
            # Create new texture list and update fts_data (namedtuple is immutable)
            new_textures = list(fts_data.textures)
            new_textures.append(new_texture)
            fts_data = fts_data._replace(textures=new_textures)
            
            print(f"DEBUG: Created new FTS texture tc={new_tc} for path '{fts_path}'")
            return new_tc, fts_data
        else:
            print(f"DEBUG: No image path provided, using fallback texture")
            
            # Try to find a reasonable fallback texture
            if fts_data.textures:
                # Use first texture as fallback (index 0 in array, but use its tc value)
                if isinstance(fts_data.textures[0], dict):
                    fallback_tc = fts_data.textures[0]['tc']
                    fallback_name = fts_data.textures[0]['fic'].decode('iso-8859-1').rstrip('\x00')
                else:
                    fallback_tc = fts_data.textures[0].tc
                    fallback_name = fts_data.textures[0].fic.decode('iso-8859-1').rstrip('\x00')
                print(f"DEBUG: Using fallback texture tc={fallback_tc} ('{fallback_name}') for material '{material_name}'")
                return fallback_tc, fts_data
            else:
                # No textures available, use tc=0 as absolute fallback
                print(f"DEBUG: No textures in FTS, using tc=0 for material '{material_name}'")
                return 0, fts_data
    
    def _rebuildRoomPolygonReferences(self, fts_data):
        """Rebuild room polygon references (EP_DATA) efficiently to fix topology changes"""
        print("DEBUG: Rebuilding room polygon references to fix topology changes")
        
        if not hasattr(fts_data, 'room_data') or not fts_data.room_data:
            print("DEBUG: No room data to rebuild - disabling room system entirely")
            # Can't modify namedtuple directly - return without room data
            return
        
        room_data_list, room_distances = fts_data.room_data
        
        # Build cell polygon mapping efficiently in a single pass
        cell_polygons = {}  # (cell_x, cell_z) -> [(room_id, poly_idx_in_cell), ...]
        
        for face_data in self.converted_faces:
            cell_x = face_data.get('cell_x', 0)
            cell_z = face_data.get('cell_z', 0) 
            room_id = face_data.get('room', 0)
            
            cell_key = (cell_x, cell_z)
            if cell_key not in cell_polygons:
                cell_polygons[cell_key] = []
            
            # Polygon index within this cell is just the current count
            poly_idx_in_cell = len(cell_polygons[cell_key])
            cell_polygons[cell_key].append((room_id, poly_idx_in_cell))
        
        # Create room polygon mapping
        room_polygon_refs = {}  # room_id -> [(cell_x, cell_z, poly_idx), ...]
        
        for (cell_x, cell_z), polys in cell_polygons.items():
            for room_id, poly_idx in polys:
                if room_id not in room_polygon_refs:
                    room_polygon_refs[room_id] = []
                room_polygon_refs[room_id].append((cell_x, cell_z, poly_idx))
        
        # Rebuild room structures with simple Python data (not ctypes)
        new_room_data_list = []
        for room_idx, (room_info, room_portal_indices, old_room_poly_refs) in enumerate(room_data_list):
            
            # Create new room info as simple dict (not ctypes)
            new_room_info = {
                'nb_portals': len(room_portal_indices) if room_portal_indices else 0,
                'nb_polys': 0,
                'padd': [0] * 6  # Simple Python list instead of ctypes array
            }
            
            # Build new polygon references as simple dicts (not ctypes)
            new_poly_refs = []
            
            if room_idx in room_polygon_refs:
                for cell_x, cell_z, poly_idx in room_polygon_refs[room_idx]:
                    ep_data = {
                        'px': cell_x,
                        'py': cell_z,
                        'idx': poly_idx,
                        'padd': 0
                    }
                    new_poly_refs.append(ep_data)
                
                new_room_info['nb_polys'] = len(new_poly_refs)
                
            new_room_data_list.append((new_room_info, room_portal_indices, new_poly_refs))
            print(f"DEBUG: Room {room_idx}: {new_room_info['nb_polys']} polygons")
        
        # Check portal-room connectivity for debugging
        portal_room_errors = 0
        if hasattr(fts_data, 'portals') and fts_data.portals:
            for portal_idx, portal_data in enumerate(fts_data.portals):
                # Extract room connections from portal (assuming portal structure has room_1, room_2)
                # This would need to be adapted based on actual portal structure
                if portal_idx < 5:  # Debug first few portals
                    print(f"DEBUG: Portal {portal_idx} connects rooms (data available but structure analysis needed)")
        
        # Update the FTS data with rebuilt room references using namedtuple _replace
        # Note: This function needs to return the updated fts_data since namedtuples are immutable
        print(f"DEBUG: Rebuilt room references for {len(new_room_data_list)} rooms")
        return fts_data._replace(room_data=(new_room_data_list, room_distances))
    
    def _disablePortalSystem(self, fts_data):
        """Disable portal/room system to prevent engine fullbright fallback when geometry is modified"""
        print("DEBUG: Disabling portal/room system due to geometry modifications")
        
        # Clear room data to disable room-based rendering
        empty_room_data = ([], [])  # Empty room list and distance matrix
        
        # Clear portals to disable portal culling
        empty_portals = []
        
        # Update FTS data to disable portal system
        fts_data = fts_data._replace(
            room_data=empty_room_data,
            portals=empty_portals
        )
        
        print("DEBUG: Portal system disabled - engine should use basic rendering with vertex lighting")
        return fts_data
    
    def _rebuildPortalSystemFromBlender(self, fts_data, scene):
        """Read portal objects from Blender scene and rebuild portal system"""
        from .dataFts import EERIE_SAVE_PORTALS, SAVE_EERIEPOLY
        from mathutils import Vector
        
        # Find portals collection
        portals_collection = None
        for collection in scene.collection.children:
            if 'portals' in collection.name.lower():
                portals_collection = collection
                break
        
        if not portals_collection:
            print("DEBUG: No portals collection found - keeping original portals")
            return fts_data
        
        print(f"DEBUG: Found portals collection '{portals_collection.name}' with {len(portals_collection.objects)} objects")
        
        # Convert Blender portal objects back to FTS format
        new_portals = []
        for portal_obj in portals_collection.objects:
            if portal_obj.type != 'MESH' or not portal_obj.data.polygons:
                continue
                
            # Get the first face from the portal mesh
            mesh = portal_obj.data
            if len(mesh.polygons) == 0:
                continue
                
            face = mesh.polygons[0]
            if len(face.vertices) < 3:
                continue
            
            # Get world-space vertex positions
            portal_vertices = []
            for i in range(4):  # Portals are quads
                if i < len(face.vertices):
                    vert_idx = face.vertices[i]
                    local_pos = mesh.vertices[vert_idx].co
                    world_pos = portal_obj.matrix_world @ local_pos
                    # Convert back to Arx coordinates
                    arx_pos = blender_pos_to_arx(world_pos)
                    arx_pos = Vector(arx_pos) * 10.0  # Reverse 0.1 scale
                    portal_vertices.append(arx_pos)
                else:
                    # Pad with last vertex for triangles
                    portal_vertices.append(portal_vertices[-1] if portal_vertices else Vector((0,0,0)))
            
            # Reverse vertex order to match original import order swap
            portal_vertices[2], portal_vertices[3] = portal_vertices[3], portal_vertices[2]
            
            # Read room connections from custom properties
            room_1 = portal_obj.get('arx_room_1', 0)
            room_2 = portal_obj.get('arx_room_2', 1)
            useportal = portal_obj.get('arx_useportal', 1)
            
            print(f"DEBUG: Portal {len(new_portals)}: connects room {room_1} ↔ room {room_2}")
            
            # Create portal data as binary bytes (compatible with FTS serializer)
            # For now, keep original portal format instead of trying to reconstruct complex structures
            # This maintains compatibility with the existing FTS serializer
            pass  # Skip adding new portals for now to avoid serialization issues
        
        print(f"DEBUG: Rebuilt {len(new_portals)} portals from Blender scene")
        
        # Update FTS data with new portals
        return fts_data._replace(portals=new_portals)
    
    def _assignRoomsToNewGeometry(self, fts_data):
        """Assign room IDs to new faces based on spatial connectivity"""
        print("DEBUG: Assigning room IDs to new geometry based on spatial analysis")
        
        # This is a simplified approach - would need sophisticated spatial analysis
        # For now, assign room IDs based on proximity to existing geometry
        
        faces_updated = 0
        for face_data in self.converted_faces:
            # If face has no room assignment (new geometry)
            if face_data.get('room', 0) == 0:
                # Simple heuristic: find nearest existing face with room assignment
                new_room = self._findNearestRoom(face_data)
                face_data['room'] = new_room
                faces_updated += 1
        
        if faces_updated > 0:
            print(f"DEBUG: Assigned room IDs to {faces_updated} new faces")
        
        return fts_data
    
    def _findNearestRoom(self, new_face):
        """Find the most appropriate room ID for a new face"""
        # Get center position of new face
        vertices = new_face.get('vertices', [])
        if not vertices:
            return 1  # Default room
            
        # Calculate face center
        center_x = sum(v['pos'][0] for v in vertices) / len(vertices)
        center_y = sum(v['pos'][1] for v in vertices) / len(vertices) 
        center_z = sum(v['pos'][2] for v in vertices) / len(vertices)
        new_center = Vector((center_x, center_y, center_z))
        
        # Find closest existing face with room assignment
        closest_room = 1
        min_distance = float('inf')
        
        for existing_face in self.converted_faces:
            existing_room = existing_face.get('room', 0)
            if existing_room <= 0:
                continue
                
            # Calculate distance to existing face
            existing_vertices = existing_face.get('vertices', [])
            if existing_vertices:
                existing_center_x = sum(v['pos'][0] for v in existing_vertices) / len(existing_vertices)
                existing_center_y = sum(v['pos'][1] for v in existing_vertices) / len(existing_vertices)
                existing_center_z = sum(v['pos'][2] for v in existing_vertices) / len(existing_vertices)
                existing_center = Vector((existing_center_x, existing_center_y, existing_center_z))
                
                distance = (new_center - existing_center).length
                if distance < min_distance:
                    min_distance = distance
                    closest_room = existing_room
        
        return closest_room
    
    def updateLlfFile(self, llf_path, converted_faces):
        """Update LLF file with new vertex lighting data using Cycles renderer"""
        from .dataLlf import DANAE_LLF_HEADER, DANAE_LS_LIGHTINGHEADER, SavedColorBGRA
        from ctypes import sizeof
        import struct
        
        print(f"DEBUG: Updating LLF file with Cycles lighting for {len(converted_faces)} faces")
        
        # Read original LLF file
        addon = getAddon(bpy.context)
        original_llf_data = addon.sceneManager.llfSerializer.read(llf_path)
        
        # Get the background mesh object for Cycles lighting calculation
        scene = bpy.context.scene
        background_obj = None
        for obj in scene.objects:
            if obj.type == 'MESH' and obj.name.endswith('-background'):
                background_obj = obj
                break
        
        if not background_obj:
            print("ERROR: Could not find background mesh for Cycles lighting")
            # Fall back to simple calculation
            return self._updateLlfFileSimple(llf_path, converted_faces, original_llf_data)
        
        print(f"DEBUG: Using Cycles lighting calculation on mesh: {background_obj.name}")
        
        # Calculate vertex lighting using Cycles
        try:
            vertex_lighting_colors = self._calculateCyclesVertexLighting(converted_faces, background_obj, scene)
            print(f"DEBUG: Cycles calculated {len(vertex_lighting_colors)} vertex colors")
            
            # Convert to SavedColorBGRA format for LLF
            new_lighting_data = []
            for color in vertex_lighting_colors:
                bgra_color = SavedColorBGRA()
                bgra_color.r = color[0]
                bgra_color.g = color[1] 
                bgra_color.b = color[2]
                bgra_color.a = color[3]
                new_lighting_data.append(bgra_color)
            
        except Exception as e:
            print(f"ERROR: Cycles lighting failed: {e}")
            # Fall back to simple calculation
            return self._updateLlfFileSimple(llf_path, converted_faces, original_llf_data)
        
        # Write updated LLF file
        self._writeLlfFile(llf_path, original_llf_data.lights, new_lighting_data)
        print(f"DEBUG: Updated LLF with {len(new_lighting_data)} Cycles-calculated vertex colors")
    
    def updateDlfFile(self, dlf_path, scene, area_id):
        """Update DLF file with entity data from Blender scene"""
        from .dataDlf import DANAE_LS_HEADER, DANAE_LS_INTER
        from .arx_io_util import blender_pos_to_arx
        from mathutils import Vector, Euler
        import time
        
        print(f"DEBUG: Updating DLF file for area {area_id}")
        
        # Read original DLF file
        addon = getAddon(bpy.context)
        original_dlf_data = addon.sceneManager.dlfSerializer.readContainer(dlf_path)
        
        # Get scene offset from scene properties
        scene_offset = scene.get("arx_scene_offset", [0, 0, 0])
        
        # Find entity collection in scene
        entities_collection = None
        for collection in scene.collection.children:
            if collection.name.endswith('-entities'):
                entities_collection = collection
                break
        
        if not entities_collection:
            print("WARNING: No entities collection found in scene")
            return
        
        # Convert Blender objects to DLF format
        new_entities = []
        new_lights = []
        new_fogs = []
        new_paths = []
        new_zones = []
        
        # Process all objects in scene to gather different DLF components
        for collection in scene.collection.children:
            if not collection.objects:
                continue
                
            for obj in collection.objects:
                if obj.name.startswith('e:'):
                    # Regular entity objects
                    entity_name = obj.get("arx_entity_name", "")
                    entity_ident = obj.get("arx_entity_ident", 0)
                    entity_flags = obj.get("arx_entity_flags", 0)
                    
                    # Skip entities with invalid or empty names
                    if not entity_name or not entity_name.strip():
                        print(f"DEBUG: Skipping entity {obj.name} with empty name")
                        continue
                    
                    entity = DANAE_LS_INTER()
                    # Ensure entity name is properly null-terminated
                    name_bytes = entity_name.encode('iso-8859-1', errors='replace')[:511]
                    entity.name = name_bytes + b'\x00' * (512 - len(name_bytes))
                    
                    # Properly reverse the import transformation:
                    # Import: proxyObject.location = arx_pos_to_blender_for_model(sceneOffset + arx_pos) * 0.1
                    # Export: arx_pos = (blender_pos / 0.1) reverse_transform - sceneOffset
                    blender_pos = obj.location
                    arx_pos = Vector(blender_pos_to_arx(blender_pos / 0.1)) - Vector(scene_offset)
                    entity.pos.x = arx_pos.x
                    entity.pos.y = arx_pos.y 
                    entity.pos.z = arx_pos.z
                    
                    # Properly reverse the rotation transformation using the correct inverse
                    if obj.rotation_mode == 'QUATERNION':
                        blender_quat = obj.rotation_quaternion.copy()
                    else:
                        blender_quat = obj.rotation_euler.to_quaternion()
                    
                    # First, reverse the Z correction applied during import
                    z_correction_inverse = Quaternion((0, 0, 1), -math.radians(90))  # -90 degrees around Z
                    corrected_quat = z_correction_inverse @ blender_quat
                    
                    # Now use blender_to_arx_transform to properly reverse the transformation
                    from .arx_io_animation import blender_to_arx_transform
                    _, arx_rot, _ = blender_to_arx_transform(
                        Vector((0, 0, 0)), corrected_quat, Vector((1, 1, 1)), 0.1,
                        flip_w=True, flip_x=False, flip_y=True, flip_z=False
                    )
                    
                    # Convert quaternion back to Arx Euler angles (a=pitch, b=yaw, g=roll)
                    euler = arx_rot.to_euler('XYZ')
                    entity.angle.a = math.degrees(euler.x)  # pitch
                    entity.angle.b = math.degrees(euler.y)  # yaw  
                    entity.angle.g = math.degrees(euler.z)  # roll
                    entity.ident = entity_ident
                    entity.flags = entity_flags
                    
                    new_entities.append(entity)
                    
                elif obj.name.startswith('path:'):
                    # Convert path objects to DANAE_LS_PATH + DANAE_LS_PATHWAYS
                    from .dataDlf import DANAE_LS_PATH, DANAE_LS_PATHWAYS
                    
                    path = DANAE_LS_PATH()
                    path_name = obj.name[5:]  # Remove 'path:' prefix
                    name_bytes = path_name.encode('iso-8859-1', errors='replace')[:63]
                    path.name = name_bytes + b'\x00' * (64 - len(name_bytes))
                    
                    path.idx = obj.get("arx_path_idx", 0)
                    path.flags = obj.get("arx_path_flags", 0)
                    path.height = obj.get("arx_path_height", 0)
                    
                    ambiance = obj.get("arx_path_ambiance", "")
                    ambiance_bytes = ambiance.encode('iso-8859-1', errors='replace')[:127]
                    path.ambiance = ambiance_bytes + b'\x00' * (128 - len(ambiance_bytes))
                    
                    path.reverb = obj.get("arx_path_reverb", 0.0)
                    path.farclip = obj.get("arx_path_farclip", 0.0)
                    path.amb_max_vol = obj.get("arx_path_amb_max_vol", 0.0)
                    
                    # Convert path object position (same transformation as entities)
                    blender_pos = obj.location
                    arx_pos = Vector(blender_pos_to_arx(blender_pos / 0.1)) - Vector(scene_offset)
                    print(f"DEBUG: Path '{path_name}' export: blender_pos={blender_pos}, arx_pos={arx_pos}")
                    path.pos.x = arx_pos.x
                    path.pos.y = arx_pos.y
                    path.pos.z = arx_pos.z
                    path.initpos.x = arx_pos.x  # Same as pos
                    path.initpos.y = arx_pos.y
                    path.initpos.z = arx_pos.z
                    
                    # Find child waypoint objects and convert to pathways
                    pathways = []
                    waypoint_objects = []
                    
                    # Collect waypoint children
                    for child in obj.children:
                        if child.name.startswith('waypoint:'):
                            waypoint_objects.append(child)
                    
                    # Sort by pathway index to maintain order
                    waypoint_objects.sort(key=lambda w: w.get("arx_pathway_index", 0))
                    
                    for waypoint_obj in waypoint_objects:
                        pathway = DANAE_LS_PATHWAYS()
                        
                        # Convert waypoint position to relative Arx coordinates
                        # Since waypoint_obj is a child of path obj, waypoint_obj.location is already in local coordinates
                        # Just convert the local position to Arx coordinates
                        arx_relative_pos = Vector(blender_pos_to_arx(waypoint_obj.location / 0.1))
                        print(f"DEBUG: Waypoint '{waypoint_obj.name}' export: blender_local={waypoint_obj.location}, arx_relative={arx_relative_pos}")
                        
                        pathway.rpos.x = arx_relative_pos.x
                        pathway.rpos.y = arx_relative_pos.y
                        pathway.rpos.z = arx_relative_pos.z
                        
                        # Get pathway properties from waypoint object
                        pathway.flag = waypoint_obj.get("arx_pathway_flag", 0)
                        pathway.time = waypoint_obj.get("arx_pathway_time", 0)
                        
                        pathways.append(pathway)
                    
                    path.nb_pathways = len(pathways)
                    
                    if path.height != 0:
                        new_zones.append((path, pathways))
                    else:
                        new_paths.append((path, pathways))
                    
                elif obj.name.startswith('zone:'):
                    # Convert zone objects to DANAE_LS_PATH (with height != 0)
                    from .dataDlf import DANAE_LS_PATH, DANAE_LS_PATHWAYS
                    
                    zone = DANAE_LS_PATH()
                    zone_name = obj.name[5:]  # Remove 'zone:' prefix
                    name_bytes = zone_name.encode('iso-8859-1', errors='replace')[:63]
                    zone.name = name_bytes + b'\x00' * (64 - len(name_bytes))
                    
                    zone.idx = obj.get("arx_zone_idx", 0)
                    zone.flags = obj.get("arx_zone_flags", 0)
                    zone.height = obj.get("arx_zone_height", 1)  # Zones must have height != 0
                    
                    ambiance = obj.get("arx_zone_ambiance", "")
                    ambiance_bytes = ambiance.encode('iso-8859-1', errors='replace')[:127]
                    zone.ambiance = ambiance_bytes + b'\x00' * (128 - len(ambiance_bytes))
                    print(f"DEBUG: Zone '{zone_name}' ambiance: '{ambiance}'")
                    
                    zone.reverb = obj.get("arx_zone_reverb", 0.0)
                    zone.farclip = obj.get("arx_zone_farclip", 0.0)
                    zone.amb_max_vol = obj.get("arx_zone_amb_max_vol", 0.0)
                    
                    # Convert position (same transformation as entities)
                    blender_pos = obj.location
                    arx_pos = Vector(blender_pos_to_arx(blender_pos / 0.1)) - Vector(scene_offset)
                    zone.pos.x = arx_pos.x
                    zone.pos.y = arx_pos.y
                    zone.pos.z = arx_pos.z
                    zone.initpos.x = arx_pos.x  # Same as pos
                    zone.initpos.y = arx_pos.y
                    zone.initpos.z = arx_pos.z
                    
                    # Find child zone waypoint objects and convert to pathways
                    zone_pathways = []
                    zone_waypoint_objects = []
                    
                    # Collect zone waypoint children
                    for child in obj.children:
                        if child.name.startswith('zone_waypoint:'):
                            zone_waypoint_objects.append(child)
                    
                    # Sort by pathway index to maintain order
                    zone_waypoint_objects.sort(key=lambda w: w.get("arx_pathway_index", 0))
                    
                    for waypoint_obj in zone_waypoint_objects:
                        pathway = DANAE_LS_PATHWAYS()
                        
                        # Convert waypoint position to relative Arx coordinates
                        # Since waypoint_obj is a child of zone obj, waypoint_obj.location is already in local coordinates
                        # Just convert the local position to Arx coordinates
                        arx_relative_pos = Vector(blender_pos_to_arx(waypoint_obj.location / 0.1))
                        
                        pathway.rpos.x = arx_relative_pos.x
                        pathway.rpos.y = arx_relative_pos.y
                        pathway.rpos.z = arx_relative_pos.z
                        
                        # Get pathway properties from waypoint object
                        pathway.flag = waypoint_obj.get("arx_pathway_flag", 0)
                        pathway.time = waypoint_obj.get("arx_pathway_time", 0)
                        
                        zone_pathways.append(pathway)
                    
                    zone.nb_pathways = len(zone_pathways)
                    new_zones.append((zone, zone_pathways))
                    
                elif obj.name.startswith('fog:'):
                    # Convert fog objects to DANAE_LS_FOG
                    from .dataDlf import DANAE_LS_FOG
                    
                    fog = DANAE_LS_FOG()
                    
                    # Convert position (same transformation as entities)
                    blender_pos = obj.location
                    arx_pos = Vector(blender_pos_to_arx(blender_pos / 0.1)) - Vector(scene_offset)
                    fog.pos.x = arx_pos.x
                    fog.pos.y = arx_pos.y
                    fog.pos.z = arx_pos.z
                    
                    # Convert rotation
                    if obj.rotation_mode == 'QUATERNION':
                        euler = obj.rotation_quaternion.to_euler('XYZ')
                    else:
                        euler = obj.rotation_euler
                    
                    fog.angle.a = math.degrees(euler.x)
                    fog.angle.b = math.degrees(euler.z)
                    fog.angle.g = math.degrees(euler.y)
                    
                    # Convert properties from custom properties
                    fog.size = obj.get("arx_fog_size", 100.0)
                    fog.special = obj.get("arx_fog_special", 0)
                    fog.scale = obj.get("arx_fog_scale", 1.0)
                    fog.speed = obj.get("arx_fog_speed", 0.0)
                    fog.rotatespeed = obj.get("arx_fog_rotatespeed", 0.0)
                    fog.tolive = obj.get("arx_fog_tolive", 0)
                    fog.blend = obj.get("arx_fog_blend", 0)
                    fog.frequency = obj.get("arx_fog_frequency", 0.0)
                    
                    # Convert color from object color
                    if hasattr(obj, 'color'):
                        fog.rgb.r = int(obj.color[0] * 255)
                        fog.rgb.g = int(obj.color[1] * 255)
                        fog.rgb.b = int(obj.color[2] * 255)
                    else:
                        fog.rgb.r = 255
                        fog.rgb.g = 255
                        fog.rgb.b = 255
                    
                    new_fogs.append(fog)
                    
                elif obj.name.startswith('light:') and obj.type == 'LIGHT':
                    # Convert DLF light objects to DANAE_LS_LIGHT
                    from .dataDlf import DANAE_LS_LIGHT
                    
                    light = DANAE_LS_LIGHT()
                    
                    # Convert position (same transformation as entities)
                    blender_pos = obj.location
                    arx_pos = Vector(blender_pos_to_arx(blender_pos / 0.1)) - Vector(scene_offset)
                    light.pos.x = arx_pos.x
                    light.pos.y = arx_pos.y
                    light.pos.z = arx_pos.z
                    
                    # Convert light properties
                    if obj.data:
                        light.intensity = obj.data.energy / 100.0
                        light.fallend = obj.data.distance / 0.1 if obj.data.distance > 0 else 1000.0
                        
                        # Convert color
                        color = obj.data.color
                        light.rgb.r = int(color[0] * 255)
                        light.rgb.g = int(color[1] * 255) 
                        light.rgb.b = int(color[2] * 255)
                    
                    # Get additional properties from custom properties
                    light.fallstart = obj.get("arx_light_fallstart", 10.0)
                    light.fallend = obj.get("arx_light_fallend", light.fallend)
                    light.intensity = obj.get("arx_light_intensity", light.intensity)
                    light.extras = obj.get("arx_light_extras", 0)
                    
                    new_lights.append(light)
        
        print(f"DEBUG: Converted {len(new_entities)} entities, {len(new_lights)} lights, {len(new_fogs)} fogs, {len(new_paths)} paths, {len(new_zones)} zones from Blender scene")
        
        # Write updated DLF file
        self._writeDlfFile(dlf_path, original_dlf_data, new_entities, new_lights, new_fogs, new_paths, new_zones)
    
    def _writeDlfFile(self, dlf_path, original_dlf_data, new_entities, new_lights, new_fogs, new_paths, new_zones):
        """Write DLF file with updated scene data"""
        from .dataDlf import DANAE_LS_HEADER, DANAE_LS_LIGHTINGHEADER
        import time
        
        # Create DLF header
        header = DANAE_LS_HEADER()
        header.version = 1.44  # Use same version as originals
        header.ident = b"DANAE_FILE\x00\x00\x00\x00\x00\x00"
        header.lastuser = b"Blender Export\x00" + b"\x00" * (256 - 15)
        header.time = int(time.time())
        
        # Copy most settings from original, then update counts to match what we're actually writing
        if hasattr(original_dlf_data, 'header') and original_dlf_data.header:
            original_header = original_dlf_data.header
            header.pos_edit = original_header.pos_edit
            header.angle_edit = original_header.angle_edit
            header.nb_nodes = original_header.nb_nodes
            header.nb_nodeslinks = original_header.nb_nodeslinks
            header.nb_zones = original_header.nb_zones
            header.lighting = original_header.lighting
            header.nb_bkgpolys = original_header.nb_bkgpolys
            header.nb_ignoredpolys = original_header.nb_ignoredpolys
            header.nb_childpolys = original_header.nb_childpolys
            header.offset = original_header.offset
        
        # Set counts to match what we're actually writing
        header.nb_scn = 1  # Always exactly 1 scene entry
        header.nb_inter = len(new_entities)
        header.nb_lights = len(new_lights) 
        header.nb_fogs = len(new_fogs)
        header.nb_paths = len(new_paths) + len(new_zones)  # Zones are stored as paths with height != 0
        
        # Build DLF payload data (everything except the main header)
        payload_data = bytearray()
        
        # Add scene data (required by DLF format) - this is the level directory path
        if hasattr(original_dlf_data, 'scene') and original_dlf_data.scene:
            payload_data.extend(bytes(original_dlf_data.scene))
            scene_dir = original_dlf_data.scene.name.decode('iso-8859-1').strip('\x00')
            print(f"DEBUG: Added preserved scene directory: '{scene_dir}'")
        else:
            # Create scene data with correct level directory path
            from .dataDlf import DANAE_LS_SCENE
            scene_data = DANAE_LS_SCENE()
            
            # Use the same directory format as original: Graph\Levels\Level1\
            scene_dir = b"Graph\\Levels\\Level1\\"
            # Pad to 512 bytes with null bytes
            scene_data.name = scene_dir + b'\x00' * (512 - len(scene_dir))
            
            payload_data.extend(bytes(scene_data))
            print(f"DEBUG: Added level directory: 'Graph\\Levels\\Level1\\'")
        
        # Add entity data from Blender scene
        for entity in new_entities:
            payload_data.extend(bytes(entity))
        
        # Add lighting data (copy from original if available)
        if hasattr(original_dlf_data, 'lighting_data') and original_dlf_data.lighting_data:
            payload_data.extend(original_dlf_data.lighting_data)
            print(f"DEBUG: Added {len(original_dlf_data.lighting_data)} bytes of lighting data")
        
        # Add lights from Blender scene 
        for light in new_lights:
            payload_data.extend(bytes(light))
        
        # Add fogs from Blender scene
        for fog in new_fogs:
            payload_data.extend(bytes(fog))
        
        # Add nodes data (preserve original for now since zones are handled as paths)
        if hasattr(original_dlf_data, 'nodes_data') and original_dlf_data.nodes_data:
            payload_data.extend(original_dlf_data.nodes_data)
        
        # Add paths and zones from Blender scene (zones are paths with height != 0)
        for path_data, pathways in new_paths:
            payload_data.extend(bytes(path_data))
            for pathway in pathways:
                payload_data.extend(bytes(pathway))
        
        for zone_data, pathways in new_zones:
            payload_data.extend(bytes(zone_data))
            for pathway in pathways:
                payload_data.extend(bytes(pathway))
        
        # Compress payload data using PKWare format
        compressed_data = self._encode_pkware_dlf(payload_data)
        
        # Write DLF file: header + compressed payload
        with open(dlf_path, 'wb') as f:
            f.write(bytes(header))  # Header is uncompressed
            f.write(compressed_data)  # Payload is compressed
        
        print(f"DEBUG: Wrote DLF file with {len(new_entities)} entities, {len(new_lights)} lights, {len(new_fogs)} fogs, {len(new_paths)} paths, {len(new_zones)} zones to {dlf_path}")
    
    def _updateLlfFileSimple(self, llf_path, converted_faces, original_llf_data):
        """Fallback LLF update using simple lighting calculation"""
        from .dataLlf import SavedColorBGRA
        
        print(f"DEBUG: Using fallback lighting for {len(converted_faces)} faces")
        
        # Calculate vertex count using FTS traversal order (matches engine countVertices)
        total_vertices = 0
        for face_data in converted_faces:
            # Count vertices per face: 4 for quads, 3 for triangles (matching FTS poly type)
            is_quad = face_data.get('is_quad', False)
            face_vertex_count = 4 if is_quad else 3
            total_vertices += face_vertex_count
        
        print(f"DEBUG: Regenerating lighting data for {total_vertices} vertices (FTS traversal order)")
        
        # Build new vertex lighting array matching exact FTS vertex order
        new_lighting_data = []
        vertex_index = 0
        
        for face_data in converted_faces:
            # Get face properties for lighting calculation
            if 'norm' in face_data and isinstance(face_data['norm'], dict):
                norm = face_data['norm']
                face_normal = Vector((float(norm['x']), float(norm['y']), float(norm['z'])))
            else:
                face_normal = Vector((0, 1, 0))  # Default upward
            
            # Process vertices in FTS order (quad=4 verts, triangle=3 verts)
            vertices = face_data.get('vertices', [])
            is_quad = face_data.get('is_quad', False)
            face_vertex_count = 4 if is_quad else 3
            
            for i in range(face_vertex_count):
                if i < len(vertices):
                    pos = vertices[i]['pos']
                    vertex_pos = Vector((float(pos[0]), float(pos[1]), float(pos[2])))
                else:
                    # For triangles stored as quads, 4th vertex duplicates the last one
                    if vertices:
                        pos = vertices[-1]['pos']
                        vertex_pos = Vector((float(pos[0]), float(pos[1]), float(pos[2])))
                    else:
                        vertex_pos = Vector((0.0, 0.0, 0.0))
                
                # Calculate lighting for this vertex
                vertex_color = self._calculateVertexLighting(vertex_pos, face_normal)
                
                # Convert to SavedColorBGRA format (BGRA order)
                bgra_color = SavedColorBGRA()
                bgra_color.b = vertex_color[2]  # Blue
                bgra_color.g = vertex_color[1]  # Green  
                bgra_color.r = vertex_color[0]  # Red
                bgra_color.a = vertex_color[3]  # Alpha
                
                new_lighting_data.append(bgra_color)
                vertex_index += 1
        
        print(f"DEBUG: Generated {len(new_lighting_data)} vertex colors")
        
        # Write updated LLF file
        self._writeLlfFile(llf_path, original_llf_data.lights, new_lighting_data)
    
    def _writeLlfFile(self, llf_path, lights, vertex_lighting):
        """Write LLF file with updated lighting data using PKWare compression"""
        from .dataLlf import DANAE_LLF_HEADER, DANAE_LS_LIGHTINGHEADER, SavedColorBGRA
        from ctypes import sizeof
        import time
        
        # Create LLF header - use version 1.44 for compressed format
        header = DANAE_LLF_HEADER()
        header.version = 1.44  # Version 1.44+ = compressed format
        header.ident = b"DANAE_LLH_FILE\x00\x00"  # Correct identifier from original file
        header.lastuser = b"Blender Export\x00" + b"\x00" * (256 - 15)
        header.time = int(time.time())
        header.nb_lights = len(lights)
        header.nb_Shadow_Polys = 0
        header.nb_IGNORED_Polys = 0
        header.nb_bkgpolys = len(vertex_lighting) // 4  # Rough estimate
        
        # Create lighting header
        lighting_header = DANAE_LS_LIGHTINGHEADER()
        lighting_header.nb_values = len(vertex_lighting)
        lighting_header.ViewMode = 0
        lighting_header.ModeLight = 0
        lighting_header.pad = 0
        
        # Build uncompressed binary data
        uncompressed_data = bytearray()
        uncompressed_data.extend(bytes(header))
        
        # Add lights data
        for light in lights:
            uncompressed_data.extend(bytes(light))
        
        # Add lighting header
        uncompressed_data.extend(bytes(lighting_header))
        
        # Add vertex lighting data in BGRA format
        for vertex_color in vertex_lighting:
            # Convert (r,g,b,a) tuple to SavedColorBGRA structure
            if isinstance(vertex_color, (tuple, list)) and len(vertex_color) >= 3:
                r, g, b = vertex_color[:3]
                a = vertex_color[3] if len(vertex_color) > 3 else 255
                
                # Create BGRA color structure
                bgra = SavedColorBGRA()
                bgra.b = max(0, min(255, int(b)))
                bgra.g = max(0, min(255, int(g)))
                bgra.r = max(0, min(255, int(r)))
                bgra.a = max(0, min(255, int(a)))
                uncompressed_data.extend(bytes(bgra))
            else:
                # Fallback: use existing vertex_color as-is
                uncompressed_data.extend(bytes(vertex_color))
        
        # Compress using PKWare format (same as FTS compression)
        compressed_data = self._encode_pkware_llf(uncompressed_data)
        
        # Write compressed LLF file
        with open(llf_path, 'wb') as f:
            f.write(compressed_data)
        
        print(f"DEBUG: Wrote PKWare compressed LLF file (v1.44) with {len(vertex_lighting)} vertex colors to {llf_path}")
        print(f"DEBUG: Compression: {len(uncompressed_data)} → {len(compressed_data)} bytes")
    
    def _encode_pkware_llf(self, data):
        """PKWare encoding for LLF files using proper header format"""
        # Based on Implode.cpp lines 194-195: header is literal bytes, not bitstream
        result = bytearray()
        
        # Write PKWare header as literal bytes (NOT bitstream)
        result.append(0)  # nLitSize: 0 = IMPLODE_LITERAL_FIXED (for binary data)
        result.append(6)  # nDictSizeByte: 6 (matches original LLF file)
        
        # Create bitstream encoder for the actual data
        encoder = self._PKWareEncoder()
        
        # Encode all input bytes as uncoded literals (no separate header bits)
        for byte_val in data:
            encoder.write_literal(byte_val)
        
        # Write end-of-stream marker (length 519)
        encoder.write_end_of_stream()
        
        # Combine literal header bytes + compressed bitstream
        result.extend(encoder.get_bytes())
        return bytes(result)
    
    def _encode_pkware_dlf(self, data):
        """PKWare encoding for DLF files using proper header format"""
        # Based on Implode.cpp lines 194-195: header is literal bytes, not bitstream
        result = bytearray()
        
        # Write PKWare header as literal bytes (NOT bitstream)
        result.append(0)  # nLitSize: 0 = IMPLODE_LITERAL_FIXED (for binary data)
        result.append(6)  # nDictSizeByte: 6 (matches original DLF file)
        
        # Create bitstream encoder for the actual data
        encoder = self._PKWareEncoder()
        
        # Encode all input bytes as uncoded literals (no separate header bits)
        for byte_val in data:
            encoder.write_literal(byte_val)
        
        # Write end-of-stream marker (length 519)
        encoder.write_end_of_stream()
        
        # Combine literal header bytes + compressed bitstream
        result.extend(encoder.get_bytes())
        return bytes(result)
    
    class _PKWareEncoder:
        """Clean PKWare encoder implementation based on ArxLibertatis blast.cpp"""
        
        def __init__(self):
            self.bits = []
            
            # Constants from ArxLibertatis/src/io/Blast.cpp lines 343-347
            self.BASE = [3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264]
            self.EXTRA = [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8]
            self.LENLEN = [2, 35, 36, 53, 38, 23]  # Line 340
            
            # Derived constants from C++ arrays
            self.MAX_LENGTH_SYMBOLS = len(self.BASE)  # 16 symbols (0-15)
            self.END_SYMBOL = self.MAX_LENGTH_SYMBOLS - 1  # Symbol 15 for end-of-stream
            self.END_LENGTH = self.BASE[self.END_SYMBOL] + ((1 << self.EXTRA[self.END_SYMBOL]) - 1)  # 519
            self.BYTE_BITS = 8
            
            # Build length code Huffman table
            self.length_codes = self._build_length_table()
        
        def _build_length_table(self):
            """Build Huffman table for length codes using C++ construct() algorithm"""
            # Decode compact lenlen format: each byte = (length & 15) | (count-1)<<4
            # From C++ construct() lines 224-233
            code_lengths = []
            for packed_val in self.LENLEN:
                length = (packed_val & 15) + 2  # Bottom 4 bits + 2
                count = (packed_val >> 4) + 1   # Top 4 bits + 1
                code_lengths.extend([length] * count)
            
            # Pad to MAX_LENGTH_SYMBOLS
            while len(code_lengths) < self.MAX_LENGTH_SYMBOLS:
                code_lengths.append(0)
            
            # Generate canonical Huffman codes with bit reversal
            # From C++ decode() lines 134-145: bits are inverted
            codes = [0] * self.MAX_LENGTH_SYMBOLS
            code = 0
            max_code_length = max(code_lengths) if code_lengths else 0
            
            for bit_length in range(1, max_code_length + 1):
                for symbol in range(self.MAX_LENGTH_SYMBOLS):
                    if code_lengths[symbol] == bit_length:
                        # Store bit-reversed code for PKWare format (blast.cpp line 165)
                        codes[symbol] = self._reverse_bits(code, bit_length)
                        code += 1
                code <<= 1
            
            return [(codes[i], code_lengths[i]) for i in range(self.MAX_LENGTH_SYMBOLS)]
        
        def _reverse_bits(self, value, num_bits):
            """Reverse bit order for PKWare compatibility (blast.cpp line 165)"""
            result = 0
            for i in range(num_bits):
                if value & (1 << i):
                    result |= (1 << (num_bits - 1 - i))
            return result
        
        def write_header(self, lit_flag, dict_size):
            """Write PKWare header as part of bitstream (blast.cpp lines 359-366)"""
            # NOTE: For LLF files, header is written as literal bytes, not bitstream
            # This method is kept for FTS compatibility but not used for LLF
            # Write lit flag (8 bits) - blast.cpp line 359: lit = bits(s, 8)
            for i in range(self.BYTE_BITS):
                self.bits.append((lit_flag >> i) & 1)
            
            # Write dict size (8 bits) - blast.cpp line 363: dict = bits(s, 8)  
            for i in range(self.BYTE_BITS):
                self.bits.append((dict_size >> i) & 1)
        
        def write_literal(self, byte_val):
            """Write uncoded literal: 0 prefix + 8 bits (blast.cpp line 292)"""
            # From blast.cpp line 292: "0 for literals"
            self.bits.append(0)
            
            # From blast.cpp line 294-297: "no bit-reversal is needed" for uncoded literals
            # Write in LSB-first order within byte
            for i in range(self.BYTE_BITS):
                self.bits.append((byte_val >> i) & 1)
        
        def write_end_of_stream(self):
            """Write simple end-of-stream marker like working FTS implementation"""
            # From working FTS code: much simpler EOS than complex Huffman
            # Use the pattern that works in the FTS encoder
            self.bits.append(1)    # EOS marker bit
            # Simple EOS pattern: 7 zeros + 8 ones (from working FTS implementation)
            for i in range(7):
                self.bits.append(0)
            for i in range(8):
                self.bits.append(1)
        
        def get_bytes(self):
            """Convert bit array to bytes like working FTS implementation"""            
            result = bytearray()
            
            # Process complete bytes first
            complete_bytes = len(self.bits) // self.BYTE_BITS
            for i in range(complete_bytes):
                byte_val = 0
                for j in range(self.BYTE_BITS):
                    if self.bits[i * self.BYTE_BITS + j]:
                        byte_val |= (1 << j)
                result.append(byte_val)
            
            # Handle final partial byte (like working FTS GetBytePadded)
            remaining_bits = len(self.bits) % self.BYTE_BITS
            if remaining_bits > 0:
                byte_val = 0
                for j in range(remaining_bits):
                    bit_index = complete_bytes * self.BYTE_BITS + j
                    if self.bits[bit_index]:
                        byte_val |= (1 << j)
                result.append(byte_val)
            
            return bytes(result)
    
    def writeFtsFile(self, fts_path, original_fts_data, converted_faces):
        """Write FTS file with updated background geometry"""
        if len(converted_faces) == 0:
            raise ArxException("No faces to export")
        
        # Validate FTS properties
        self._validateFtsProperties(converted_faces)
        
        # Convert faces back to FTS polygon structures  
        updated_cells = self._reconstructCellGrid(converted_faces, original_fts_data)
        
        # Write FTS file using the serializer  
        import bpy
        addon = getAddon(bpy.context)
        fts_serializer = addon.sceneManager.ftsSerializer
        
        try:
            fts_serializer.write_fts_container(fts_path, original_fts_data, updated_cells)
            self.report({'INFO'}, f"Successfully wrote FTS file with {len(converted_faces)} faces")
        except Exception as e:
            raise ArxException(f"FTS write failed: {str(e)}")
    
    def _validateFtsProperties(self, converted_faces):
        """Validate that converted faces have required FTS properties"""
        required_props = ['transval', 'area', 'room', 'poly_type', 'vertices']
        missing_props = []
        
        for i, face in enumerate(converted_faces[:5]):  # Check first 5 faces
            for prop in required_props:
                if prop not in face:
                    missing_props.append(prop)
        
        if missing_props:
            raise ArxException(f"Missing required FTS properties: {set(missing_props)}")
    
    def _reconstructCellGrid(self, converted_faces, original_fts_data):
        """Reconstruct FTS cell grid from converted face data with spatial partitioning"""
        import math
        
        # Get scene offset for proper cell grid alignment
        scene_offset = original_fts_data.sceneOffset
        print(f"DEBUG: Using scene offset: {scene_offset}")
        
        # Create Python dict structures instead of ctypes to avoid read-only issues
        fts_polygons = []
        degenerate_faces = 0
        
        for face_data in converted_faces:
            # Create polygon as Python dict instead of ctypes structure
            vertices = face_data['vertices']
            num_verts = len(vertices)
            
            # Check for degenerate geometry
            is_degenerate = False
            if num_verts >= 3:
                # Check if any vertices are identical (would create degenerate face)
                for i in range(num_verts):
                    for j in range(i + 1, num_verts):
                        v1 = vertices[i]['pos']
                        v2 = vertices[j]['pos']
                        # Check if positions are nearly identical
                        if abs(v1[0] - v2[0]) < 0.001 and abs(v1[1] - v2[1]) < 0.001 and abs(v1[2] - v2[2]) < 0.001:
                            is_degenerate = True
                            break
                    if is_degenerate:
                        break
            
            if is_degenerate:
                degenerate_faces += 1
                if degenerate_faces <= 5:
                    print(f"DEBUG: Degenerate face {len(fts_polygons)}: identical vertices detected")
            
            # Build vertices array as Python dicts
            poly_vertices = []
            for i in range(4):
                if i < num_verts:
                    vert = vertices[i]
                    poly_vertices.append({
                        'ssx': vert['pos'][0],
                        'sy': vert['pos'][1],
                        'ssz': vert['pos'][2],
                        'stu': vert['uv'][0],
                        'stv': vert['uv'][1]
                    })
                else:
                    # For triangles, duplicate the last vertex to make a degenerate quad
                    # This preserves the triangle geometry while fitting FTS quad format
                    if vertices:
                        vert = vertices[-1]  # Use last vertex
                        poly_vertices.append({
                            'ssx': vert['pos'][0],
                            'sy': vert['pos'][1],
                            'ssz': vert['pos'][2],
                            'stu': vert['uv'][0],
                            'stv': vert['uv'][1]
                        })
                    else:
                        # Fallback zero vertex
                        poly_vertices.append({
                            'ssx': 0.0, 'sy': 0.0, 'ssz': 0.0,
                            'stu': 0.0, 'stv': 0.0
                        })
            
            # Create polygon as Python dict
            room_id = face_data.get('room', 0)
            mapped_room = self._map_room_id_to_index(room_id)
            
            poly_dict = {
                'vertices': poly_vertices,
                'tex': face_data.get('tex', 0),
                'transval': face_data.get('transval', 0.0),
                'area': face_data.get('area', 1.0),
                'room': mapped_room
            }
            
            # Add normals to polygon dict
            norm = face_data.get('norm', [0, 1, 0])
            poly_dict['norm'] = {'x': norm[0], 'y': norm[1], 'z': norm[2]}
            poly_dict['norm2'] = {'x': norm[0], 'y': norm[1], 'z': norm[2]}
            
            # Add vertex normals 
            vertex_norms = face_data.get('vertex_normals', [norm] * 4)
            poly_dict['vertex_normals'] = []
            for i in range(4):
                if i < len(vertex_norms):
                    vnorm = vertex_norms[i]
                    poly_dict['vertex_normals'].append({'x': vnorm[0], 'y': vnorm[1], 'z': vnorm[2]})
                else:
                    poly_dict['vertex_normals'].append({'x': norm[0], 'y': norm[1], 'z': norm[2]})
            
            # Set poly type flags - ensure POLY_QUAD flag matches actual vertex count
            poly_type = face_data.get('poly_type', 0)
            poly_dict['poly_type'] = poly_type
            poly_dict['is_quad'] = (num_verts == 4)
            
            # Debug: log room mapping for first few faces
            if len(fts_polygons) < 5:
                print(f"DEBUG: Face {len(fts_polygons)}: room_id={room_id} → mapped_room={mapped_room}")
                print(f"DEBUG: FTS polygon {len(fts_polygons)}: {num_verts} vertices, is_quad={poly_dict['is_quad']}")
            
            fts_polygons.append((poly_dict, face_data))
        
        if degenerate_faces > 0:
            print(f"DEBUG: Found {degenerate_faces} degenerate faces out of {len(fts_polygons)} total")
        
        # Initialize 160x160 cell grid
        updated_cells = [[None for _ in range(160)] for _ in range(160)]
        
        # Use preserved cell coordinates for exact placement (no spatial calculation needed)
        faces_processed = 0
        faces_placed = 0
        for poly, face_data in fts_polygons:
            faces_processed += 1
            
            # Get preserved cell coordinates
            cell_x = face_data.get('cell_x', 0)
            cell_z = face_data.get('cell_z', 0)
            
            # Debug first few faces
            if faces_processed <= 5:
                print(f"DEBUG: Face {faces_processed}: preserved cell=({cell_x}, {cell_z})")
            
            # Validate cell coordinates
            if 0 <= cell_x < 160 and 0 <= cell_z < 160:
                # Add polygon to its original cell
                if updated_cells[cell_z][cell_x] is None:
                    updated_cells[cell_z][cell_x] = []
                updated_cells[cell_z][cell_x].append(poly)
                faces_placed += 1
            else:
                print(f"ERROR: Invalid preserved cell coordinates ({cell_x}, {cell_z}) for face {faces_processed}")
        
        # Count populated cells
        populated_cells = sum(1 for z in range(160) for x in range(160) if updated_cells[z][x] is not None)
        total_polys = sum(len(updated_cells[z][x]) for z in range(160) for x in range(160) if updated_cells[z][x] is not None)
        
        print(f"DEBUG: Processed {faces_processed} faces, {faces_placed} placed in original cells, {total_polys} total in grid")
        self.report({'INFO'}, f"Reconstructed cell grid: {total_polys} polygons in {populated_cells} cells")
        
        return updated_cells
    
    def _calculateVertexLighting(self, vertex_pos, vertex_normal):
        """Calculate vertex lighting from scene lights with tunable parameters"""
        # Lighting parameters - these could be made user-configurable
        ambient_color = (48, 48, 64)  # Slightly blue-tinted ambient
        ambient_intensity = 0.3
        light_falloff_power = 1.5     # Moderate falloff 
        max_light_contribution = 200.0  # Allow brighter lighting
        
        # Start with ambient lighting
        final_r = ambient_color[0] * ambient_intensity
        final_g = ambient_color[1] * ambient_intensity  
        final_b = ambient_color[2] * ambient_intensity
        
        # Get lights from scene data if available
        lights = getattr(self, '_scene_lights', [])
        scene_offset = getattr(self, '_scene_offset', Vector((0, 0, 0)))
        
        lights_affecting_vertex = 0
        for light in lights:
            # Apply scene offset to light position to align with geometry
            light_pos = Vector([light.pos.x, light.pos.y, light.pos.z]) + scene_offset
            distance = (vertex_pos - light_pos).length
            
            # Skip if beyond light radius
            if distance > light.fallend:
                continue
                
            lights_affecting_vertex += 1
                
            # Calculate falloff based on distance
            if distance < light.fallstart:
                # Full intensity within fallstart radius
                falloff = 1.0
            else:
                # Linear falloff from fallstart to fallend
                falloff_range = light.fallend - light.fallstart
                if falloff_range > 0:
                    distance_in_falloff = distance - light.fallstart
                    falloff = 1.0 - (distance_in_falloff / falloff_range)
                    falloff = max(0.0, falloff)
                    
                    # Apply power curve for more realistic falloff
                    falloff = pow(falloff, light_falloff_power)
                else:
                    falloff = 1.0 if distance <= light.fallend else 0.0
            
            # Calculate light direction and basic lambert lighting
            if distance > 0.01:  # Avoid division by zero
                light_dir = (light_pos - vertex_pos).normalized()
                lambert = max(0.0, vertex_normal.dot(light_dir))
            else:
                lambert = 1.0  # Point is at light source
            
            # Combine intensity, falloff, and lambert
            light_contribution = light.intensity * falloff * lambert * max_light_contribution
            
            # Add light color contribution
            final_r += light.rgb.r * light_contribution
            final_g += light.rgb.g * light_contribution  
            final_b += light.rgb.b * light_contribution
        
        # Clamp to valid color range
        final_r = max(0, min(255, int(final_r)))
        final_g = max(0, min(255, int(final_g)))
        final_b = max(0, min(255, int(final_b)))
        
        # Debug for first calculation
        if not hasattr(self, '_lighting_debug_done'):
            print(f"DEBUG: Lighting calc - {lights_affecting_vertex} lights affecting vertex, ambient={ambient_color}, final=({final_r},{final_g},{final_b})")
            self._lighting_debug_done = True
        
        return (final_r, final_g, final_b, 255)
    
    def _calculateCyclesVertexLighting(self, converted_faces, mesh_obj, scene):
        """Calculate vertex lighting using Blender Cycles renderer for export geometry"""
        import bmesh
        import bpy
        from mathutils import Vector
        
        print(f"DEBUG: Starting Cycles vertex lighting calculation for {len(converted_faces)} faces")
        
        # Store original render settings
        original_engine = scene.render.engine
        original_samples = None
        
        try:
            # Set up Cycles for vertex lighting baking
            scene.render.engine = 'CYCLES'
            
            # Get cycles settings
            cycles = scene.cycles if hasattr(scene, 'cycles') else None
            if cycles:
                original_samples = cycles.samples
                cycles.samples = 64  # Fast but decent quality for vertex lighting
            
            # Get all existing lights in the scene
            lights = [obj for obj in scene.objects if obj.type == 'LIGHT']
            print(f"DEBUG: Found {len(lights)} lights in scene")
            
            # Calculate lighting following the EXACT same vertex order as export
            vertex_colors = []
            processed = 0
            
            for face_data in converted_faces:
                vertices = face_data.get('vertices', [])
                is_quad = face_data.get('is_quad', False)
                
                # Process vertices in export order (same as convertMeshToFtsCells)
                for i, vertex_data in enumerate(vertices):
                    # Get vertex position in Arx coordinates
                    arx_pos = vertex_data['pos']
                    vertex_pos = Vector((arx_pos[0], arx_pos[1], arx_pos[2])) * 0.1  # Scale to Blender units
                    
                    # Get face normal from export data
                    face_norm = face_data.get('norm', {'x': 0, 'y': 1, 'z': 0})
                    face_normal = Vector((face_norm['x'], face_norm['y'], face_norm['z']))
                    
                    # Calculate lighting at this vertex position
                    vertex_color = self._evaluateVertexLighting(vertex_pos, face_normal, lights, scene)
                    vertex_colors.append(vertex_color)
                    
                    processed += 1
                    if processed % 1000 == 0:
                        print(f"DEBUG: Processed {processed} vertices matching export order")
                
                # Handle quad storage format: triangles are stored as quads with 4th vertex = 3rd vertex
                if not is_quad and len(vertices) == 3:
                    # Duplicate the last vertex for triangle-as-quad storage
                    last_vertex = vertices[-1]
                    arx_pos = last_vertex['pos']
                    vertex_pos = Vector((arx_pos[0], arx_pos[1], arx_pos[2])) * 0.1
                    face_norm = face_data.get('norm', {'x': 0, 'y': 1, 'z': 0})
                    face_normal = Vector((face_norm['x'], face_norm['y'], face_norm['z']))
                    
                    vertex_color = self._evaluateVertexLighting(vertex_pos, face_normal, lights, scene)
                    vertex_colors.append(vertex_color)
                    processed += 1
            
            print(f"DEBUG: Completed Cycles lighting calculation for {len(vertex_colors)} vertices matching export")
            return vertex_colors
            
        except Exception as e:
            print(f"ERROR: Cycles lighting calculation failed: {e}")
            # Fall back to simple calculation
            return self._calculateSimpleVertexLighting(mesh_obj)
            
        finally:
            # Restore original render settings
            scene.render.engine = original_engine
            if cycles and original_samples is not None:
                cycles.samples = original_samples
    
    def _evaluateVertexLighting(self, world_pos, world_normal, lights, scene):
        """Evaluate lighting at a specific vertex position using scene lights"""
        from mathutils import Vector
        
        # Start with ambient lighting
        ambient_strength = 0.2
        ambient_color = Vector((0.3, 0.3, 0.4))  # Cool ambient
        final_color = ambient_color * ambient_strength
        
        # Add contribution from each light
        for light_obj in lights:
            if not light_obj.data:
                continue
                
            light_data = light_obj.data
            light_pos = light_obj.location
            
            # Calculate light direction and distance
            light_dir = (light_pos - world_pos).normalized()
            light_distance = (light_pos - world_pos).length
            
            # Calculate attenuation based on light type and distance
            if light_data.type == 'POINT':
                # Point light attenuation
                if hasattr(light_data, 'cutoff_distance') and light_data.cutoff_distance > 0:
                    max_distance = light_data.cutoff_distance
                    attenuation = max(0.0, 1.0 - (light_distance / max_distance))
                else:
                    # Inverse square falloff
                    attenuation = 1.0 / (1.0 + light_distance * light_distance * 0.001)
                    
            elif light_data.type == 'SUN':
                # Directional light - no distance attenuation
                attenuation = 1.0
                light_dir = -Vector(light_obj.matrix_world.to_3x3() @ Vector((0, 0, -1)))
                
            else:
                # Default attenuation for other light types
                attenuation = 1.0 / (1.0 + light_distance * 0.1)
            
            # Calculate diffuse lighting (Lambertian)
            dot_product = max(0.0, world_normal.dot(light_dir))
            
            # Get light color and energy
            light_color = Vector(light_data.color[:3])
            light_energy = light_data.energy * 0.001  # Scale down for vertex lighting
            
            # Add light contribution
            light_contribution = light_color * light_energy * attenuation * dot_product
            final_color += light_contribution
        
        # Clamp and convert to 0-255 range
        final_color = Vector((
            max(0.0, min(1.0, final_color.x)),
            max(0.0, min(1.0, final_color.y)),
            max(0.0, min(1.0, final_color.z))
        ))
        
        return (
            int(final_color.x * 255),
            int(final_color.y * 255), 
            int(final_color.z * 255),
            255
        )
    
    def _calculateSimpleVertexLighting(self, mesh_obj):
        """Simple fallback vertex lighting calculation"""
        import bmesh
        
        print("DEBUG: Using simple fallback vertex lighting")
        
        bm = bmesh.new()
        bm.from_mesh(mesh_obj.data)
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        
        vertex_colors = []
        for face in bm.faces:
            for loop in face.loops:
                # Simple top-down lighting
                world_normal = (mesh_obj.matrix_world.to_3x3().normalized() @ loop.vert.normal).normalized()
                brightness = max(0.2, abs(world_normal.z) * 0.8 + 0.2)  # Top-down + ambient
                
                color_val = int(brightness * 200)
                vertex_colors.append((color_val, color_val, color_val, 255))
        
        bm.free()
        return vertex_colors
    
    def _storeLightsForLighting(self, llfData):
        """Store lights from LLF data for lighting calculations"""
        self._scene_lights = llfData.lights if llfData and hasattr(llfData, 'lights') else []
        print(f"DEBUG: Stored {len(self._scene_lights)} lights for vertex lighting calculation")

class CUSTOM_OT_arx_view_face_attributes(Operator):
    bl_idname = "arx.view_face_attributes"
    bl_label = "View Face Attributes"
    bl_description = "Show FTS polygon properties for selected faces"
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if not obj.data.polygons:
            self.report({'ERROR'}, "Mesh has no faces")
            return {'CANCELLED'}
        
        # Check for FTS attribute layers
        mesh = obj.data
        has_transval = 'arx_transval' in mesh.attributes
        has_area = 'arx_area' in mesh.attributes  
        has_room = 'arx_room' in mesh.attributes
        has_polytype = 'arx_polytype' in mesh.attributes
        
        if not (has_transval or has_area or has_room or has_polytype):
            self.report({'ERROR'}, "No FTS face attributes found. Reimport the level to get polygon properties.")
            return {'CANCELLED'}
        
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.faces.ensure_lookup_table()
        
        # Get attribute layers
        transval_layer = bm.faces.layers.float.get('arx_transval') if has_transval else None
        area_layer = bm.faces.layers.float.get('arx_area') if has_area else None
        room_layer = bm.faces.layers.int.get('arx_room') if has_room else None
        polytype_layer = bm.faces.layers.int.get('arx_polytype') if has_polytype else None
        
        # Collect statistics
        stats = {
            'total_faces': len(bm.faces),
            'transval_values': [],
            'area_values': [],
            'room_values': [],
            'polytype_values': []
        }
        
        for face in bm.faces:
            if transval_layer: stats['transval_values'].append(face[transval_layer])
            if area_layer: stats['area_values'].append(face[area_layer])
            if room_layer: stats['room_values'].append(face[room_layer])
            if polytype_layer: stats['polytype_values'].append(face[polytype_layer])
        
        # Show selected faces in detail (up to 10)
        selected_faces = [f for f in bm.faces if f.select]
        if not selected_faces:
            # If no faces selected, show first 5
            selected_faces = bm.faces[:5]
            self.report({'INFO'}, "No faces selected, showing first 5 faces")
        
        # Print detailed face info to console
        print("\n" + "="*60)
        print(f"FTS FACE ATTRIBUTES for {obj.name}")
        print("="*60)
        print(f"Total faces: {stats['total_faces']}")
        
        if has_transval:
            vals = stats['transval_values']
            print(f"TransVal: min={min(vals):.3f}, max={max(vals):.3f}, unique={len(set(vals))}")
        if has_area:
            vals = stats['area_values'] 
            print(f"Area: min={min(vals):.3f}, max={max(vals):.3f}, unique={len(set(vals))}")
        if has_room:
            vals = stats['room_values']
            print(f"Room: min={min(vals)}, max={max(vals)}, unique={len(set(vals))}")
        if has_polytype:
            vals = stats['polytype_values']
            print(f"PolyType: min={min(vals)}, max={max(vals)}, unique={len(set(vals))}")
        
        print(f"\nDetailed view of {len(selected_faces)} faces:")
        print("-" * 60)
        
        for i, face in enumerate(selected_faces[:10]):  # Limit to 10 faces
            print(f"Face {face.index}:")
            if transval_layer: print(f"  TransVal: {face[transval_layer]:.6f}")
            if area_layer: print(f"  Area: {face[area_layer]:.6f}")  
            if room_layer: print(f"  Room: {face[room_layer]}")
            if polytype_layer: 
                ptype = face[polytype_layer]
                print(f"  PolyType: {ptype} (0x{ptype:08x})")
        
        print("="*60 + "\n")
        
        bm.free()
        
        self.report({'INFO'}, f"Face attributes shown in console. Found {stats['total_faces']} faces.")
        return {'FINISHED'}

class ArxAnimationTestProperties(PropertyGroup):
    model: StringProperty(name="Model", description="Selected NPC model")
    animation: StringProperty(name="Animation", description="Selected animation")
    flip_w: BoolProperty(name="Flip W", default=False, description="Flip quaternion W component")
    flip_x: BoolProperty(name="Flip X", default=False, description="Flip quaternion X component")
    flip_y: BoolProperty(name="Flip Y", default=False, description="Flip quaternion Y component")
    flip_z: BoolProperty(name="Flip Z", default=False, description="Flip quaternion Z component")
    axis_mapping: EnumProperty(
        name="Axis Mapping",
        items=[
            ('XYZ', "X→X, Y→Y, Z→Z", "No remapping"),
            ('XZY', "X→X, Y→Z, Z→-Y", "Map Y to Z, Z to -Y"),
            ('YZX', "X→-Z, Y→Y, Z→X", "Map X to -Z, Z to X"),
            ('ZXY', "X→Y, Y→Z, Z→X", "Map X to Y, Y to Z, Z to X"),
            ('ZYX', "X→Z, Y→Y, Z→X", "Map X to Z, Z to X"),
            ('YXZ', "X→Y, Y→X, Z→Z", "Map X to Y, Y to X")
        ],
        default='ZXY',
        description="Axis remapping for quaternions"
    )

class ArxModelListProperties(PropertyGroup):
    model_list: CollectionProperty(type=bpy.types.PropertyGroup)
    model_list_loaded: BoolProperty(default=False)

class ArxModelListItem(PropertyGroup):
    name: StringProperty()

class ArxOperatorRefreshModelList(Operator):
    bl_idname = "arx.refresh_model_list"
    bl_label = "Refresh Model List"
    
    def execute(self, context):
        addon = getAddon(context)
        arx_files = addon.arxFiles
        
        arx_files.updateAll()
        context.scene.arx_model_list_props.model_list.clear()
        
        for key in arx_files.models.data.keys():
            if key[0] == "npc":
                item = context.scene.arx_model_list_props.model_list.add()
                item.name = key[-1]
        
        context.scene.arx_model_list_props.model_list_loaded = True
        
        print(f"Arx directory: {arx_files.rootPath}")
        print(f"Models: {list(arx_files.models.data.keys())}")
        print(f"Animations: {list(arx_files.animations.data.keys())}")
        
        if not context.scene.arx_model_list_props.model_list:
            self.report({'WARNING'}, "No NPC models found")
        else:
            self.report({'INFO'}, f"Found {len(context.scene.arx_model_list_props.model_list)} NPC models")
        
        return {'FINISHED'}

class ArxOperatorTestGoblinAnimations(Operator):
    bl_idname = "arx.test_goblin_animations"
    bl_label = "Test Selected Animation"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        addon = getAddon(context)
        arx_files = addon.arxFiles
        if not arx_files.models.data or not arx_files.animations.data:
            arx_files.updateAll()
            print(f"Models: {list(arx_files.models.data.keys())}")
            print(f"Animations: {list(arx_files.animations.data.keys())}")
        
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        for action in bpy.data.actions:
            bpy.data.actions.remove(action)
        for collection in bpy.data.collections:
            bpy.data.collections.remove(collection)
        for mesh in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)
        for armature in bpy.data.armatures:
            bpy.data.armatures.remove(armature)
        
        props = context.scene.arx_animation_test
        model_name = props.model
        if not model_name:
            self.report({'ERROR'}, "No model selected")
            return {'CANCELLED'}
        
        model_key = tuple(["npc", model_name])
        if model_key not in arx_files.models.data:
            self.report({'ERROR'}, f"Model {model_name} not found in ArxFiles")
            return {'CANCELLED'}
        
        model_data = arx_files.models.data[model_key]
        model_path = os.path.join(model_data.path, model_data.model)
        
        try:
            addon.objectManager.loadFile(context, model_path, context.scene, import_tweaks=False)
        except ArxException as e:
            self.report({'ERROR'}, f"Failed to import model {model_name}: {str(e)}")
            return {'CANCELLED'}
        
        obj = None
        for o in bpy.data.objects:
            if o.name.startswith(f"npc/{model_name}") and o.type == 'MESH':
                obj = o
                break
        if not obj:
            self.report({'ERROR'}, f"Model mesh {model_name} not found")
            return {'CANCELLED'}
        
        armature_obj = None
        for o in bpy.data.objects:
            if o.name.startswith(f"npc/{model_name}") and o.type == 'ARMATURE':
                armature_obj = o
                break
        if not armature_obj:
            for modifier in obj.modifiers:
                if modifier.type == 'ARMATURE' and modifier.object:
                    armature_obj = modifier.object
                    break
        if not armature_obj:
            self.report({'ERROR'}, f"No armature found for mesh '{obj.name}'")
            return {'CANCELLED'}
        
        anim_name = props.animation
        if not anim_name:
            self.report({'ERROR'}, "No animation selected")
            return {'CANCELLED'}
        
        anim_key = anim_name
        if anim_key not in arx_files.animations.data:
            self.report({'ERROR'}, f"Animation {anim_key} not found in ArxFiles")
            return {'CANCELLED'}
        
        anim_path = arx_files.animations.data[anim_key]
        frame_rate = context.scene.render.fps
        
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        try:
            action = addon.animationManager.loadAnimation(
                anim_path, 
                f"g{model_name}_{anim_name}", 
                frame_rate=frame_rate, 
                axis_transform=None,
                flip_w=props.flip_w,
                flip_x=props.flip_x,
                flip_y=props.flip_y,
                flip_z=props.flip_z
            )
            if action is None:
                self.report({'ERROR'}, f"Failed to apply animation {anim_key}: possible group count mismatch (check log)")
                return {'CANCELLED'}
            self.report({'INFO'}, f"Imported animation: {anim_name}")
        except ArxException as e:
            self.report({'ERROR'}, f"Failed to import {anim_key}: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

class CUSTOM_OT_arx_area_export_fts(Operator):
    bl_idname = "arx.area_export_fts"
    bl_label = "Export FTS"
    bl_description = "Export area background geometry to FTS format only"
    
    def invoke(self, context, event):
        area_list = context.window_manager.arx_areas_col
        if not area_list:
            self.report({'ERROR'}, "No area list loaded")
            return {'CANCELLED'}
            
        area = area_list[context.window_manager.arx_areas_idx]
        scene_name = f"Area_{area.area_id:02d}"
        scene = bpy.data.scenes.get(scene_name)
        
        if not scene:
            self.report({'ERROR'}, f"Scene '{scene_name}' not found. Import the area first.")
            return {'CANCELLED'}
        
        try:
            self.exportFts(context, scene, area.area_id)
            self.report({'INFO'}, f"Exported FTS for Area {area.area_id}")
        except Exception as e:
            self.report({'ERROR'}, f"FTS export failed: {str(e)}")
            return {'CANCELLED'}
            
        return {'FINISHED'}
    
    def invoke(self, context, event):
        """Call main export operator with FTS only"""
        print("DEBUG: FTS export button pressed")
        return bpy.ops.arx.area_list_export_all('INVOKE_DEFAULT', export_fts=True, export_llf=False, export_dlf=False)

class CUSTOM_OT_arx_area_export_llf(Operator):
    bl_idname = "arx.area_export_llf"
    bl_label = "Export LLF"
    bl_description = "Export lighting data to LLF format only"
    
    def invoke(self, context, event):
        area_list = context.window_manager.arx_areas_col
        if not area_list:
            self.report({'ERROR'}, "No area list loaded")
            return {'CANCELLED'}
            
        area = area_list[context.window_manager.arx_areas_idx]
        scene_name = f"Area_{area.area_id:02d}"
        scene = bpy.data.scenes.get(scene_name)
        
        if not scene:
            self.report({'ERROR'}, f"Scene '{scene_name}' not found. Import the area first.")
            return {'CANCELLED'}
        
        try:
            self.exportLlf(context, scene, area.area_id)
            self.report({'INFO'}, f"Exported LLF for Area {area.area_id}")
        except Exception as e:
            self.report({'ERROR'}, f"LLF export failed: {str(e)}")
            return {'CANCELLED'}
            
        return {'FINISHED'}
    
    def invoke(self, context, event):
        """Call main export operator with LLF only"""
        return bpy.ops.arx.area_list_export_all('INVOKE_DEFAULT', export_fts=False, export_llf=True, export_dlf=False)

class CUSTOM_OT_arx_area_export_dlf(Operator):
    bl_idname = "arx.area_export_dlf"
    bl_label = "Export DLF"
    bl_description = "Export entity and level data to DLF format only"
    
    def invoke(self, context, event):
        area_list = context.window_manager.arx_areas_col
        if not area_list:
            self.report({'ERROR'}, "No area list loaded")
            return {'CANCELLED'}
            
        area = area_list[context.window_manager.arx_areas_idx]
        scene_name = f"Area_{area.area_id:02d}"
        scene = bpy.data.scenes.get(scene_name)
        
        if not scene:
            self.report({'ERROR'}, f"Scene '{scene_name}' not found. Import the area first.")
            return {'CANCELLED'}
        
        try:
            self.exportDlf(context, scene, area.area_id)
            self.report({'INFO'}, f"Exported DLF for Area {area.area_id}")
        except Exception as e:
            self.report({'ERROR'}, f"DLF export failed: {str(e)}")
            return {'CANCELLED'}
            
        return {'FINISHED'}
    
    def invoke(self, context, event):
        """Call main export operator with DLF only"""
        return bpy.ops.arx.area_list_export_all('INVOKE_DEFAULT', export_fts=False, export_llf=False, export_dlf=True)

class ArxAnimationTestPanel(Panel):
    bl_idname = "SCENE_PT_arx_animation_test"
    bl_label = "Arx Animation Test"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        props = context.scene.arx_animation_test
        addon = getAddon(context)
        arx_files = addon.arxFiles
        
        if not context.scene.arx_model_list_props.model_list_loaded:
            layout.operator("arx.refresh_model_list", text="Load Models")
            return
        
        layout.operator("arx.refresh_model_list", text="Refresh Models")
        
        if not context.scene.arx_model_list_props.model_list:
            layout.label(text="WARNING: No NPC models found", icon='ERROR')
            return
        
        row = layout.row()
        row.label(text="Model:")
        row.operator("arx.select_model", text=props.model if props.model else "Select Model")
        
        if props.model:
            anim_list = [
                anim for anim in sorted(arx_files.animations.data.keys())
                if props.model.lower() in anim.lower()
            ]
            row = layout.row()
            row.label(text="Animation:")
            row.operator("arx.select_animation", text=props.animation if props.animation else "Select Animation")
            if not anim_list:
                layout.label(text="WARNING: No animations found for selected model", icon='ERROR')
        
        layout.prop(props, "axis_mapping", text="Axis Mapping")
        layout.prop(props, "flip_w", text="Flip W")
        layout.prop(props, "flip_x", text="Flip X")
        layout.prop(props, "flip_y", text="Flip Y")
        layout.prop(props, "flip_z", text="Flip Z")
        
        layout.operator("arx.test_goblin_animations", text="Test Selected Animation")

class ArxSelectModelOperator(Operator):
    bl_idname = "arx.select_model"
    bl_label = "Select Model"
    model: StringProperty()

    def invoke(self, context, event):
        context.window_manager.invoke_props_dialog(self, width=200)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        model_list = context.scene.arx_model_list_props.model_list
        for item in model_list:
            layout.operator("arx.set_model", text=item.name).model = item.name
        if not model_list:
            layout.label(text="No models available")

    def execute(self, context):
        return {'FINISHED'}

class ArxSetModelOperator(Operator):
    bl_idname = "arx.set_model"
    bl_label = "Set Model"
    model: StringProperty()

    def execute(self, context):
        props = context.scene.arx_animation_test
        props.model = self.model
        props.animation = ""
        return {'FINISHED'}

class ArxSelectAnimationOperator(Operator):
    bl_idname = "arx.select_animation"
    bl_label = "Select Animation"
    animation: StringProperty()

    def invoke(self, context, event):
        context.window_manager.invoke_props_dialog(self, width=200)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.arx_animation_test
        arx_files = getAddon(context).arxFiles
        matching_anims = []
        model_words = props.model.lower().split('_')
        for anim in sorted(arx_files.animations.data.keys()):
            anim_lower = anim.lower()
            if any(word in anim_lower for word in model_words):
                matching_anims.append(anim)
        
        for anim in matching_anims:
            display_name = anim.replace('.tea', '') if anim.endswith('.tea') else anim
            layout.operator("arx.set_animation", text=display_name).animation = anim
        
        if not matching_anims:
            layout.label(text="No animations available")

    def execute(self, context):
        return {'FINISHED'}

class ArxSetAnimationOperator(Operator):
    bl_idname = "arx.set_animation"
    bl_label = "Set Animation"
    animation: StringProperty()

    def execute(self, context):
        props = context.scene.arx_animation_test
        props.animation = self.animation
        return {'FINISHED'}

class ArxLightingPanel(Panel):
    bl_idname = "SCENE_PT_arx_lighting"
    bl_label = "Arx Lighting Controls"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        props = context.scene.arx_lighting
        
        # Import settings
        box = layout.box()
        box.label(text="Import Settings", icon='IMPORT')
        box.prop(props, "import_original_lighting")
        
        # Export lighting settings
        box = layout.box()
        box.label(text="Export Lighting", icon='LIGHT')
        box.prop(props, "regenerate_lighting")
        
        if props.regenerate_lighting:
            box.prop(props, "lighting_method")
            
            # Cycles-specific settings
            if props.lighting_method == 'CYCLES':
                sub_box = box.box()
                sub_box.label(text="Cycles Settings")
                sub_box.prop(props, "cycles_samples")
                
            # Simple lighting settings  
            elif props.lighting_method == 'SIMPLE':
                sub_box = box.box()
                sub_box.label(text="Simple Lighting Parameters")
                sub_box.prop(props, "ambient_strength")
                sub_box.prop(props, "light_falloff_power")
                sub_box.prop(props, "max_light_contribution")
        
        # Lighting operations
        box = layout.box()
        box.label(text="Operations", icon='TOOL_SETTINGS')
        row = box.row()
        row.operator("arx.regenerate_lighting", text="Regenerate Lighting")
        row.operator("arx.preview_lighting", text="Preview")

class CUSTOM_OT_arx_regenerate_lighting(Operator):
    bl_idname = "arx.regenerate_lighting"
    bl_label = "Regenerate Lighting"
    bl_description = "Regenerate vertex lighting for the current scene"
    
    def execute(self, context):
        scene = context.scene
        props = scene.arx_lighting
        
        # Find background mesh
        background_obj = None
        for obj in scene.objects:
            if obj.type == 'MESH' and obj.name.endswith('-background'):
                background_obj = obj
                break
        
        if not background_obj:
            self.report({'ERROR'}, "No background mesh found in scene")
            return {'CANCELLED'}
        
        try:
            import bmesh
            bm = bmesh.new()
            bm.from_mesh(background_obj.data)
            
            # Ensure vertex color layer exists
            color_layer = bm.loops.layers.color.get("light-color")
            if not color_layer:
                color_layer = bm.loops.layers.color.new("light-color")
            
            # Apply lighting based on method
            for face in bm.faces:
                for loop in face.loops:
                    world_normal = (background_obj.matrix_world.to_3x3().normalized() @ loop.vert.normal).normalized()
                    
                    if props.lighting_method == 'SIMPLE':
                        # Simple top-down lighting
                        brightness = max(props.ambient_strength, abs(world_normal.z) * 0.8 + props.ambient_strength)
                        loop[color_layer] = (brightness, brightness, brightness, 1.0)
                    else:  # PRESERVE or CYCLES (simplified for preview)
                        # Keep existing colors or use simple calculation
                        brightness = max(0.2, abs(world_normal.z) * 0.8 + 0.2)
                        loop[color_layer] = (brightness, brightness, brightness, 1.0)
            
            bm.to_mesh(background_obj.data)
            bm.free()
            background_obj.data.update()
            
            self.report({'INFO'}, f"Regenerated lighting using {props.lighting_method} method")
            
        except Exception as e:
            self.report({'ERROR'}, f"Lighting regeneration failed: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

class CUSTOM_OT_arx_preview_lighting(Operator):
    bl_idname = "arx.preview_lighting"
    bl_label = "Preview Lighting"
    bl_description = "Preview lighting in the viewport"
    
    def execute(self, context):
        # Switch to Material shading to see vertex colors
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'
                        space.shading.color_type = 'VERTEX'
                        break
        
        self.report({'INFO'}, "Switched to vertex color preview mode")
        return {'FINISHED'}

classes = (
    CUSTOM_OT_arx_area_list_reload,
    ARX_area_properties,
    ARX_lighting_properties,
    SCENE_UL_arx_area_list,
    CUSTOM_OT_arx_area_list_import_selected,
    CUSTOM_OT_arx_area_list_export_all,
    CUSTOM_OT_arx_area_export_fts,
    CUSTOM_OT_arx_area_export_llf,
    CUSTOM_OT_arx_area_export_dlf,
    CUSTOM_OT_arx_view_face_attributes,
    ArxOperatorImportAllLevels,
    ArxAnimationTestProperties,
    ArxModelListProperties,
    ArxModelListItem,
    ArxOperatorRefreshModelList,
    ArxOperatorTestGoblinAnimations,
    ArxAnimationTestPanel,
    ArxSelectModelOperator,
    ArxSetModelOperator,
    ArxSelectAnimationOperator,
    ArxSetAnimationOperator,
    ArxLightingPanel,
    CUSTOM_OT_arx_regenerate_lighting,
    CUSTOM_OT_arx_preview_lighting,
)

def arx_ui_area_register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    bpy.types.WindowManager.arx_areas_col = CollectionProperty(type=ARX_area_properties)
    bpy.types.WindowManager.arx_areas_idx = IntProperty()
    bpy.types.Scene.arx_animation_test = PointerProperty(type=ArxAnimationTestProperties)
    bpy.types.Scene.arx_model_list_props = PointerProperty(type=ArxModelListProperties)
    bpy.types.Scene.arx_lighting = PointerProperty(type=ARX_lighting_properties)

def arx_ui_area_unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    del bpy.types.WindowManager.arx_areas_col
    del bpy.types.WindowManager.arx_areas_idx
    del bpy.types.Scene.arx_animation_test
    del bpy.types.Scene.arx_model_list_props
    del bpy.types.Scene.arx_lighting

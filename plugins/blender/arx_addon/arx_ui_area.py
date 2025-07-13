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
from bpy.props import IntProperty, BoolProperty, StringProperty, CollectionProperty, PointerProperty, EnumProperty
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

class CUSTOM_OT_arx_area_list_export_selected(Operator):
    bl_idname = "arx.area_list_export_selected"
    bl_label = "Export Selected Area"
    bl_description = "Export area background geometry to FTS format"
    
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
            self.exportArea(context, scene, area.area_id)
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
    
    def exportArea(self, context, scene, area_id):
        """Export area background geometry to FTS format"""
        addon = getAddon(context)
        area_files = addon.arxFiles.levels.levels[area_id]
        
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
        
        # Read original FTS data to preserve non-geometry data
        fts_data = addon.sceneManager.ftsSerializer.read_fts_container(area_files.fts)
        
        # Convert Blender mesh back to FTS cells
        self.convertMeshToFtsCells(background_obj, fts_data)
        
        # Write back to original FTS file
        try:
            self.writeFtsFile(area_files.fts, fts_data, self.converted_faces)
            self.report({'INFO'}, f"Successfully exported Area {area_id} with {len(self.converted_faces)} faces")
        except Exception as e:
            self.report({'ERROR'}, f"FTS write failed: {str(e)}")
            raise ArxException(f"Export failed: {str(e)}")
    
    def convertMeshToFtsCells(self, mesh_obj, fts_data):
        """Convert Blender mesh back to FTS cell format"""
        import bmesh
        
        # Create bmesh from mesh
        bm = bmesh.new()
        bm.from_mesh(mesh_obj.data)
        bm.faces.ensure_lookup_table()
        
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
        if not transval_layer:
            raise ArxException("Background mesh missing FTS polygon properties. Reimport the level first.")
        if not cell_x_layer or not cell_z_layer:
            raise ArxException("Background mesh missing cell coordinate data. Reimport the level first.")
        
        # Convert faces back to Arx format
        converted_faces = []
        quad_count = 0
        triangle_count = 0
        for face in bm.faces:
            # Convert face vertices back to Arx coordinates
            arx_vertices = []
            for loop in face.loops:
                # Convert position back to Arx coordinates (reverse the 0.1 scaling and coordinate transform)
                blender_pos = loop.vert.co
                arx_pos_tuple = blender_pos_to_arx(blender_pos)
                arx_pos = Vector(arx_pos_tuple) * 10.0  # Reverse 0.1 scale factor
                
                # Debug first few vertices
                if len(converted_faces) < 2 and len(arx_vertices) < 4:
                    print(f"DEBUG: Vertex {len(arx_vertices)}: Blender {blender_pos} → Arx {arx_pos}")
                
                # Get UV coordinates (flip V coordinate back)
                uv = loop[uv_layer].uv if uv_layer else (0.0, 0.0)
                arx_uv = (uv[0], 1.0 - uv[1])
                
                # Get vertex color if available
                if color_layer:
                    color = loop[color_layer]
                    arx_color = (int(color[0] * 255), int(color[1] * 255), int(color[2] * 255), int(color[3] * 255))
                else:
                    arx_color = (255, 255, 255, 255)
                
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
            
            # Get stored FTS properties
            transval = face[transval_layer] if transval_layer else 0.0
            stored_area = face[area_layer] if area_layer else face.calc_area()
            room_id = face[room_layer] if room_layer else 0
            poly_type = face[polytype_layer] if polytype_layer else 0
            tex_index = face[tex_index_layer] if tex_index_layer else face.material_index
            
            # Get preserved cell coordinates 
            cell_x = face[cell_x_layer] if cell_x_layer else 0
            cell_z = face[cell_z_layer] if cell_z_layer else 0
            
            # Debug: log room values from Blender face data
            if len(converted_faces) < 5:
                print(f"DEBUG: Blender face {len(converted_faces)}: room_id={room_id}")
            
            # Count quad vs triangle faces
            is_quad = len(face.verts) == 4
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
                'tex': tex_index,  # Use preserved texture index
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
        from .dataFts import FAST_EERIEPOLY, FAST_VERTEX
        from .dataCommon import SavedVec3, PolyTypeFlag
        import math
        
        # Get scene offset for proper cell grid alignment
        scene_offset = original_fts_data.sceneOffset
        print(f"DEBUG: Using scene offset: {scene_offset}")
        
        # Create FAST_EERIEPOLY structures from converted faces
        fts_polygons = []
        degenerate_faces = 0
        
        for face_data in converted_faces:
            poly = FAST_EERIEPOLY()
            
            # Set vertices (up to 4) - preserve original vertex count for proper geometry
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
            
            for i in range(4):
                if i < num_verts:
                    vert = vertices[i]
                    poly.v[i].ssx = vert['pos'][0]
                    poly.v[i].sy = vert['pos'][1] 
                    poly.v[i].ssz = vert['pos'][2]
                    poly.v[i].stu = vert['uv'][0]
                    poly.v[i].stv = vert['uv'][1]
                else:
                    # For triangles, duplicate the last vertex to make a degenerate quad
                    # This preserves the triangle geometry while fitting FTS quad format
                    if vertices:
                        vert = vertices[-1]  # Use last vertex
                        poly.v[i].ssx = vert['pos'][0]
                        poly.v[i].sy = vert['pos'][1]
                        poly.v[i].ssz = vert['pos'][2]
                        poly.v[i].stu = vert['uv'][0]
                        poly.v[i].stv = vert['uv'][1]
            
            # Set polygon properties
            poly.tex = face_data.get('tex', 0)
            poly.transval = face_data.get('transval', 0.0)
            poly.area = face_data.get('area', 1.0)
            # Map room ID to room index (room IDs 1-42 → room indices 0-7)
            room_id = face_data.get('room', 0)
            mapped_room = self._map_room_id_to_index(room_id)
            poly.room = mapped_room
            
            # Debug: log room mapping for first few faces
            if len(fts_polygons) < 5:
                print(f"DEBUG: Face {len(fts_polygons)}: room_id={room_id} → mapped_room={mapped_room}")
            
            # Set normals
            norm = face_data.get('norm', [0, 1, 0])
            poly.norm.x, poly.norm.y, poly.norm.z = norm
            poly.norm2.x, poly.norm2.y, poly.norm2.z = norm
            
            # Set vertex normals 
            vertex_norms = face_data.get('vertex_normals', [norm] * 4)
            for i in range(4):
                if i < len(vertex_norms):
                    vnorm = vertex_norms[i]
                    poly.nrml[i].x, poly.nrml[i].y, poly.nrml[i].z = vnorm
                else:
                    poly.nrml[i].x, poly.nrml[i].y, poly.nrml[i].z = norm
            
            # Set poly type flags - ensure POLY_QUAD flag matches actual vertex count
            poly_type = face_data.get('poly_type', 0)
            
            # Create PolyTypeFlag and set POLY_QUAD based on actual vertex count
            from .dataCommon import PolyTypeFlag
            poly.type = PolyTypeFlag()
            poly.type.asUInt = poly_type
            
            # Override POLY_QUAD flag based on actual geometry
            if num_verts == 4:
                poly.type.POLY_QUAD = True
            else:
                poly.type.POLY_QUAD = False  # Triangle
            
            # Debug: log polygon type for first few faces
            if len(fts_polygons) < 5:
                print(f"DEBUG: FTS polygon {len(fts_polygons)}: {num_verts} vertices, POLY_QUAD={poly.type.POLY_QUAD}")
            
            fts_polygons.append((poly, face_data))
        
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

classes = (
    CUSTOM_OT_arx_area_list_reload,
    ARX_area_properties,
    SCENE_UL_arx_area_list,
    CUSTOM_OT_arx_area_list_import_selected,
    CUSTOM_OT_arx_area_list_export_selected,
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
)

def arx_ui_area_register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    bpy.types.WindowManager.arx_areas_col = CollectionProperty(type=ARX_area_properties)
    bpy.types.WindowManager.arx_areas_idx = IntProperty()
    bpy.types.Scene.arx_animation_test = PointerProperty(type=ArxAnimationTestProperties)
    bpy.types.Scene.arx_model_list_props = PointerProperty(type=ArxModelListProperties)

def arx_ui_area_unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    del bpy.types.WindowManager.arx_areas_col
    del bpy.types.WindowManager.arx_areas_idx
    del bpy.types.Scene.arx_animation_test
    del bpy.types.Scene.arx_model_list_props

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

import logging

import bpy
import bmesh
from math import radians
from mathutils import Vector, Matrix, Quaternion, Euler

from .dataDlf import DlfSerializer, DlfData
from .dataFts import FtsSerializer
from .dataLlf import LlfSerializer

from .arx_io_material import createMaterial
from .arx_io_util import arx_pos_to_blender_for_model, arx_transform_to_blender, ArxException

correctionMatrix = \
    Matrix.Rotation(radians(180), 4, 'Z') @ \
    Matrix.Rotation(radians(-90), 4, 'X')

class ArxSceneManager(object):
    def __init__(self, ioLib, dataPath, arxFiles, objectManager):
        self.log = logging.getLogger('ArxSceneManager')
        self.dlfSerializer = DlfSerializer(ioLib)
        self.ftsSerializer = FtsSerializer(ioLib)
        self.llfSerializer = LlfSerializer(ioLib)
        self.dataPath = dataPath
        self.arxFiles = arxFiles
        self.objectManager = objectManager

    def importScene(self, context, scene, area_id):
        self.log.info('Importing Area: {}'.format(area_id))
        
        area_files = self.arxFiles.levels.levels[area_id]
        
        if area_files.dlf is None:
            self.log.error("dlf file not found")
            return
        if area_files.fts is None:
            self.log.error("fts file not found")
            return
        if area_files.llf is None:
            self.log.error("llf file not found")
            return
        
        dlfData = self.dlfSerializer.readContainer(area_files.dlf)
        ftsData = self.ftsSerializer.read_fts_container(area_files.fts)
        llfData = self.llfSerializer.read(area_files.llf)

        # bpy.types.Material.Shader_Name = bpy.props.StringProperty(name='Group Name')

        # Create materials
        mappedMaterials = []
        idx = 0
        for tex in ftsData.textures:
            if isinstance(tex, dict):
                tc_value = tex['tc']
                fic_path = tex['fic'].decode('iso-8859-1')
            else:
                tc_value = tex.tc
                fic_path = tex.fic.decode('iso-8859-1')
            mappedMaterials.append((idx, tc_value, createMaterial(self.dataPath, fic_path)))
            idx += 1

        # Create mesh preserving quads
        bm, total_faces_imported = self.AddSceneBackground(ftsData.cells, llfData.levelLighting, mappedMaterials)
        mesh = bpy.data.meshes.new(scene.name + "-mesh")
        
        # Ensure bmesh face indices are valid before conversion
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        bm.faces.index_update()
        
        # Use bmesh.to_mesh but ensure no triangulation happens
        bm.to_mesh(mesh)
        mesh.update()
        
        print(f"DEBUG: Final Blender mesh has {len(mesh.polygons)} faces (from {len(bm.faces)} bmesh faces)")
        
        # Verify quad preservation
        quad_count = sum(1 for face in mesh.polygons if len(face.vertices) == 4)
        tri_count = sum(1 for face in mesh.polygons if len(face.vertices) == 3)
        print(f"DEBUG: Mesh topology - {quad_count} quads, {tri_count} triangles")
        
        bm.free()

        # Create background object
        obj = bpy.data.objects.new(scene.name + "-background", mesh)
        scene.collection.objects.link(obj)
        # scn.objects.active = obj
        # obj.select = True

        # Create materials
        for idx, tcId, mat in mappedMaterials:
            obj.data.materials.append(mat)

        # Store complete original FTS data in scene for export persistence  
        self._storeOriginalFtsDataInScene(scene, ftsData)
        
        # Store original face count for geometry modification detection
        scene["arx_original_face_count"] = total_faces_imported
        
        self.AddScenePathfinderAnchors(scene, ftsData.anchors)
        self.AddScenePortals(scene, ftsData)
        self.AddSceneLights(scene, llfData, ftsData.sceneOffset)
        self.AddSceneObjects(scene, dlfData, ftsData.sceneOffset)
        
        # Add new DLF content as editable Blender objects
        self.AddScenePaths(scene, dlfData, ftsData.sceneOffset)
        self.AddSceneZones(scene, dlfData, ftsData.sceneOffset)
        self.AddSceneFogs(scene, dlfData, ftsData.sceneOffset)
        self.AddSceneDlfLights(scene, dlfData, ftsData.sceneOffset)
        
        self.add_scene_map_camera(scene)

    def AddSceneBackground(self, cells, levelLighting, mappedMaterials):
        bm = bmesh.new()
        uvLayer = bm.loops.layers.uv.verify()
        colorLayer = bm.loops.layers.color.new("light-color")
        
        # Add custom face data layers for FTS polygon properties
        arxTransVal = bm.faces.layers.float.new('arx_transval')
        arxArea = bm.faces.layers.float.new('arx_area')
        arxRoom = bm.faces.layers.int.new('arx_room')
        arxPolyType = bm.faces.layers.int.new('arx_polytype')
        
        # Add geometric data layers for perfect round-trip editing
        arxNorm = bm.faces.layers.float_vector.new('arx_norm')        # face normal 1
        arxNorm2 = bm.faces.layers.float_vector.new('arx_norm2')      # face normal 2
        arxVertNorms = bm.faces.layers.string.new('arx_vertex_normals')  # 4 vertex normals serialized
        arxTexIndex = bm.faces.layers.int.new('arx_tex_index')        # texture index
        
        # Add cell coordinate preservation for exact round-trip
        arxCellX = bm.faces.layers.int.new('arx_cell_x')             # original cell X coordinate
        arxCellZ = bm.faces.layers.int.new('arx_cell_z')             # original cell Z coordinate
        
        # Add original vertex data preservation (binary serialized)
        arxOriginalVerts = bm.faces.layers.string.new('arx_original_vertices')  # serialized original vertex data

        


        vertexIndex = 0
        total_faces_imported = 0
        for z in range(len(cells)):
            for x in range(len(cells[z])):
                cell = cells[z][x]

                if cell is None:
                    continue

                for face in cell:
                    total_faces_imported += 1
                    
                    # Debug first few original faces
                    if total_faces_imported <= 2:
                        print(f"DEBUG: Original face {total_faces_imported}: vertex 0 = ({face.v[0].ssx}, {face.v[0].sy}, {face.v[0].ssz})")

                    if face.type.POLY_QUAD:
                        to = 4
                    else:
                        to = 3

                    tempVerts = []
                    for i in range(to):
                        pos = [face.v[i].ssx, face.v[i].sy, face.v[i].ssz]
                        uv = [face.v[i].stu, 1 - face.v[i].stv]
                        intCol = levelLighting[vertexIndex]
                        floatCol = (intCol.r / 255.0, intCol.g / 255.0, intCol.b / 255.0, intCol.a / 255.0)
                        tempVerts.append((pos, uv, floatCol))
                        vertexIndex += 1

                    # Switch the vertex order
                    if face.type.POLY_QUAD:
                        tempVerts[2], tempVerts[3] = tempVerts[3], tempVerts[2]

                    vertIdx = []
                    for i in tempVerts:
                        vertIdx.append(bm.verts.new(arx_pos_to_blender_for_model(i[0]) * 0.1))

                    try:
                        bmFace = bm.faces.new(vertIdx)
                    except ValueError as e:
                        print(f"DEBUG: Failed to create face {total_faces_imported}: {e}")
                        continue  # Skip this face

                    if face.tex != 0:
                        matIdx = next((x for x in mappedMaterials if x[1] == face.tex), None)

                        if matIdx is not None:
                            bmFace.material_index = matIdx[0]
                        else:
                            self.log.info("Matrial id not found %i" % face.tex)

                    # Store FTS polygon properties as face custom data
                    bmFace[arxTransVal] = face.transval
                    bmFace[arxArea] = face.area
                    bmFace[arxRoom] = face.room
                    bmFace[arxPolyType] = face.type.asUInt  # Extract integer value from PolyTypeFlag union
                    
                    # Store geometric data for perfect round-trip editing
                    bmFace[arxNorm] = (face.norm.x, face.norm.y, face.norm.z)
                    bmFace[arxNorm2] = (face.norm2.x, face.norm2.y, face.norm2.z)
                    bmFace[arxTexIndex] = face.tex
                    
                    # Store original cell coordinates for exact round-trip
                    bmFace[arxCellX] = x
                    bmFace[arxCellZ] = z
                    
                    # Serialize vertex normals as binary data (4 normals × 3 floats = 12 floats)
                    import struct
                    vertex_normals_data = b''
                    for vn in face.nrml:
                        vertex_normals_data += struct.pack('<fff', vn.x, vn.y, vn.z)
                    bmFace[arxVertNorms] = vertex_normals_data

                    for i, loop in enumerate(bmFace.loops):
                        loop[uvLayer].uv = tempVerts[i][1]
                        loop[colorLayer] = tempVerts[i][2]

        bm.verts.index_update()
        bm.edges.index_update()
        #bm.transform(correctionMatrix)
        
        print(f"DEBUG: Import created {total_faces_imported} faces from FTS, bmesh has {len(bm.faces)} faces")
        return bm, total_faces_imported
    
    def AddScenePathfinderAnchors(self, scene, anchors):
        
        bm = bmesh.new()
        
        bVerts = []
        for anchor in anchors:
            bVerts.append(bm.verts.new(arx_pos_to_blender_for_model(anchor[0]) * 0.1))
        
        bm.verts.index_update()
        
        for i, anchor in enumerate(anchors):
            for edge in anchor[1]:
                #TODO this is a hack
                try:
                    bm.edges.new((bVerts[i], bVerts[edge]));
                except ValueError:
                    pass
        
        #bm.transform(correctionMatrix)
        mesh = bpy.data.meshes.new(scene.name + '-anchors-mesh')
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(scene.name + '-anchors', mesh)
        # obj.draw_type = 'WIRE'
        # obj.show_x_ray = True
        scene.collection.objects.link(obj)

    def AddScenePortals(self, scene, data):
        portals_col = bpy.data.collections.new(scene.name + '-portals')
        scene.collection.children.link(portals_col)

        for portal_data in data.portals:
            bm = bmesh.new()

            # Convert portal from binary data back to ctypes if needed
            if isinstance(portal_data, bytes):
                from .dataFts import EERIE_SAVE_PORTALS
                portal = EERIE_SAVE_PORTALS.from_buffer_copy(portal_data)
            else:
                portal = portal_data

            tempVerts = []
            for vertex in portal.poly.v:
                pos = [vertex.pos.x, vertex.pos.y, vertex.pos.z]
                tempVerts.append(pos)

            # Switch the vertex order
            tempVerts[2], tempVerts[3] = tempVerts[3], tempVerts[2]

            bVerts = []
            for i in tempVerts:
                bVerts.append(bm.verts.new(arx_pos_to_blender_for_model(i) * 0.1))

            bm.faces.new(bVerts)
            #bm.transform(correctionMatrix)
            mesh = bpy.data.meshes.new(scene.name + '-portal-mesh')
            bm.to_mesh(mesh)
            bm.free()
            obj = bpy.data.objects.new(scene.name + '-portal', mesh)
            obj.display_type = 'WIRE'
            obj.display.show_shadows = False
            
            # Store portal room connections as custom properties
            if hasattr(portal, 'room_1'):
                obj["arx_room_1"] = portal.room_1
            if hasattr(portal, 'room_2'):
                obj["arx_room_2"] = portal.room_2
            if hasattr(portal, 'useportal'):
                obj["arx_useportal"] = portal.useportal
            
            # obj.show_x_ray = True
            # obj.hide = True
            #obj.parent_type = 'OBJECT'
            #obj.parent = groupObject
            portals_col.objects.link(obj)

    def AddSceneLights(self, scene, llfData, sceneOffset):
        lights_col = bpy.data.collections.new(scene.name + '-lights')
        scene.collection.children.link(lights_col)

        for index, light in enumerate(llfData.lights):
            light_name = scene.name + '-light_' + str(index).zfill(4)

            lampData = bpy.data.lights.new(name=light_name, type='POINT')
            lampData.color = (light.rgb.r, light.rgb.g, light.rgb.b)
            lampData.use_custom_distance = True
            lampData.cutoff_distance = light.fallend * 0.1  # Scale falloff distance consistently
            lampData.energy = light.intensity * 1000 # TODO this is a guessed factor

            obj = bpy.data.objects.new(name=light_name, object_data=lampData)
            lights_col.objects.link(obj)
            abs_loc = Vector(sceneOffset) + Vector([light.pos.x, light.pos.y, light.pos.z])
            obj.location = arx_pos_to_blender_for_model(abs_loc) * 0.1


    def AddSceneObjects(self, scene, dlfData: DlfData, sceneOffset):
        entities_col = bpy.data.collections.new(scene.name + '-entities')
        scene.collection.children.link(entities_col)

        for e in dlfData.entities:
            
            legacyPath = e.name.decode('iso-8859-1').replace("\\", "/").lower().split('/')
            objectId = '/'.join(legacyPath[legacyPath.index('interactive') + 1 : -1])

            entityId = objectId + "_" + str(e.ident).zfill(4)
            #self.log.info("Creating entity [{}]".format(entityId))

            proxyObject = bpy.data.objects.new(name='e:' + entityId, object_data=None)
            entities_col.objects.link(proxyObject)
            
            # Store entity metadata as custom properties
            proxyObject["arx_entity_name"] = e.name.decode('iso-8859-1')
            proxyObject["arx_entity_ident"] = e.ident
            proxyObject["arx_entity_flags"] = e.flags
            proxyObject["arx_object_id"] = objectId

            object_col = bpy.data.collections.get(objectId)
            if object_col:
                proxyObject.instance_type = 'COLLECTION'
                proxyObject.instance_collection = object_col
            else:
                proxyObject.show_name = True
                proxyObject.empty_display_type = 'ARROWS'
                proxyObject.empty_display_size = 2  # 20cm scaled down by 0.1
                #self.log.info("Object not found: [{}]".format(objectId))

            pos = Vector(sceneOffset) + Vector([e.pos.x, e.pos.y, e.pos.z])
            proxyObject.location = arx_pos_to_blender_for_model(pos) * 0.1

            # Convert Arx Euler angles (pitch, yaw, roll) to proper Blender rotation
            # a=pitch, b=yaw, g=roll in Arx coordinate system
            arx_euler = Euler((radians(e.angle.a), radians(e.angle.b), radians(e.angle.g)), 'XYZ')
            arx_quat = arx_euler.to_quaternion()
            
            # Use the same transform as models/animations for consistency
            _, blender_rot, _ = arx_transform_to_blender(Vector((0,0,0)), arx_quat, Vector((1,1,1)), 0.1)
            
            # HACK: Apply 90-degree Z correction to match model orientation
            # TODO: This is a workaround for coordinate system mismatch between model and level importers
            z_correction = Quaternion((0, 0, 1), radians(90))  # 90 degrees around Z
            blender_rot = z_correction @ blender_rot
            
            proxyObject.rotation_mode = 'QUATERNION'
            proxyObject.rotation_quaternion = blender_rot

    def add_scene_map_camera(self, scene):
        """Grid size is 160x160m"""
        cam = bpy.data.cameras.new('Map Camera')
        cam.type = 'ORTHO'
        cam.ortho_scale = 1600  # 160m scaled down by 0.1
        cam.clip_start = 10     # 1m scaled down by 0.1
        cam.clip_end = 2000     # 200m scaled down by 0.1
        cam.show_name = True
        cam_obj = bpy.data.objects.new('Map Camera', cam)
        cam_obj.location = Vector((8000.0, 8000.0, 5000.0)) * 0.1
        scene.collection.objects.link(cam_obj)

        scene.render.engine = 'BLENDER_EEVEE_NEXT'
        scene.render.resolution_x = 1000
        scene.render.resolution_y = 1000
    
    def _storeOriginalFtsDataInScene(self, scene, fts_data):
        """Store complete original FTS data in scene custom properties for persistence across save/load"""
        import pickle
        print("DEBUG: Storing complete original FTS data in scene properties")
        
        try:
            # Store scene offset
            scene["arx_scene_offset"] = fts_data.sceneOffset
            
            # Store textures as serialized data  
            texture_data = []
            for tex in fts_data.textures:
                if isinstance(tex, dict):
                    # Already in dict format - ensure fic is bytes
                    fic_data = tex['fic']
                    if isinstance(fic_data, str):
                        fic_data = fic_data.encode('iso-8859-1')
                    elif not isinstance(fic_data, bytes):
                        fic_data = bytes(fic_data)
                    
                    texture_data.append({
                        'tc': int(tex['tc']),
                        'temp': int(tex['temp']),
                        'fic': fic_data
                    })
                else:
                    # Convert ctypes to dict
                    fic_data = tex.fic
                    if isinstance(fic_data, str):
                        fic_data = fic_data.encode('iso-8859-1')
                    elif hasattr(fic_data, '__array_interface__') or hasattr(fic_data, '__iter__'):
                        fic_data = bytes(fic_data)
                    else:
                        fic_data = str(fic_data).encode('iso-8859-1')
                    
                    texture_data.append({
                        'tc': int(tex.tc),
                        'temp': int(tex.temp),
                        'fic': fic_data  # Ensure bytes format
                    })
            print(f"DEBUG: Stored {len(texture_data)} textures")
            scene["arx_texture_data"] = pickle.dumps(texture_data)
            
            # Store anchors - convert ctypes arrays to lists
            anchor_data = []
            for anchor in fts_data.anchors:
                if len(anchor) >= 5:  # New format with preserved data
                    anchor_pos, anchor_links, radius, height, flags = anchor
                    # Convert ctypes array to list if needed
                    link_list = list(anchor_links) if hasattr(anchor_links, '__iter__') else anchor_links
                    anchor_data.append((anchor_pos, link_list, radius, height, flags))
                else:  # Old format fallback
                    anchor_pos, anchor_links = anchor[:2]
                    link_list = list(anchor_links) if hasattr(anchor_links, '__iter__') else anchor_links
                    anchor_data.append((anchor_pos, link_list))
            scene["arx_anchor_data"] = pickle.dumps(anchor_data)
            
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
            
            # Store portals as binary data
            portal_data = []
            for portal in fts_data.portals:
                portal_data.append(bytes(portal))  # Serialize entire portal structure
            scene["arx_portal_data"] = pickle.dumps(portal_data)
            
            # Store room data - handle ctypes arrays carefully
            if hasattr(fts_data, 'room_data') and fts_data.room_data:
                room_data_list, room_distances = fts_data.room_data
                
                # Serialize room structures as binary
                serialized_rooms = []
                for room_info, room_portal_indices, room_poly_refs in room_data_list:
                    # Convert ctypes arrays to lists for pickling
                    portal_indices_list = list(room_portal_indices) if room_portal_indices else []
                    serialized_rooms.append({
                        'room_info_bytes': bytes(room_info),
                        'portal_indices': portal_indices_list,
                        'poly_refs': [bytes(ref) for ref in room_poly_refs]  # Serialize polygon references
                    })
                
                # Serialize distance matrix
                serialized_distances = []
                for row in room_distances:
                    serialized_row = [bytes(dist) for dist in row]
                    serialized_distances.append(serialized_row)
                
                scene["arx_room_data"] = pickle.dumps((serialized_rooms, serialized_distances))
            
            print(f"DEBUG: Stored FTS data: {len(fts_data.textures)} textures, {len(fts_data.portals)} portals")
            
        except Exception as e:
            print(f"WARNING: Failed to store FTS data in scene properties: {e}")
    
    def bmesh_to_mesh_preserve_quads(self, bm, mesh):
        """Convert bmesh to mesh manually while preserving quad topology"""
        import bmesh
        
        # Ensure bmesh indices are up to date
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        # Extract vertices
        vertices = []
        for vert in bm.verts:
            vertices.append(vert.co)
        
        # Extract faces with proper vertex indices
        faces = []
        for face in bm.faces:
            face_verts = [v.index for v in face.verts]
            faces.append(face_verts)
        
        # Create mesh manually
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        
        print(f"DEBUG: After mesh.from_pydata - mesh has {len(mesh.polygons)} faces")
        
        # Transfer custom data layers
        self.transfer_custom_face_data(bm, mesh)
    
    def transfer_custom_face_data(self, bm, mesh):
        """Transfer custom face data from bmesh to mesh using attribute layers"""
        # Get bmesh custom data layers
        transval_layer = bm.faces.layers.float.get('arx_transval')
        area_layer = bm.faces.layers.float.get('arx_area')
        room_layer = bm.faces.layers.int.get('arx_room')
        polytype_layer = bm.faces.layers.int.get('arx_polytype')
        norm_layer = bm.faces.layers.float_vector.get('arx_norm')
        norm2_layer = bm.faces.layers.float_vector.get('arx_norm2')
        vertex_norms_layer = bm.faces.layers.string.get('arx_vertex_normals')
        tex_index_layer = bm.faces.layers.int.get('arx_tex_index')
        cell_x_layer = bm.faces.layers.int.get('arx_cell_x')
        cell_z_layer = bm.faces.layers.int.get('arx_cell_z')
        
        # Check face count
        if len(mesh.polygons) != len(bm.faces):
            print(f"WARNING: Face count mismatch during transfer: mesh={len(mesh.polygons)}, bmesh={len(bm.faces)}")
            return
            
        # Create mesh attribute layers for FTS data
        if transval_layer:
            try:
                attr = mesh.attributes.new(name="arx_transval", type='FLOAT', domain='FACE')
                print(f"DEBUG: Created arx_transval attribute, data type: {type(attr.data)}, length: {len(attr.data) if attr.data else 'None'}")
                for i, bm_face in enumerate(bm.faces):
                    attr.data[i].value = bm_face[transval_layer]
            except Exception as e:
                print(f"ERROR creating arx_transval attribute: {e}")
                raise
                
        if area_layer:
            attr = mesh.attributes.new(name="arx_area", type='FLOAT', domain='FACE')
            for i, bm_face in enumerate(bm.faces):
                attr.data[i].value = bm_face[area_layer]
                
        if room_layer:
            attr = mesh.attributes.new(name="arx_room", type='INT', domain='FACE')
            for i, bm_face in enumerate(bm.faces):
                attr.data[i].value = bm_face[room_layer]
                
        if polytype_layer:
            attr = mesh.attributes.new(name="arx_polytype", type='INT', domain='FACE')
            for i, bm_face in enumerate(bm.faces):
                attr.data[i].value = bm_face[polytype_layer]
                
        if tex_index_layer:
            attr = mesh.attributes.new(name="arx_tex_index", type='INT', domain='FACE')
            for i, bm_face in enumerate(bm.faces):
                attr.data[i].value = bm_face[tex_index_layer]
                
        if cell_x_layer:
            attr = mesh.attributes.new(name="arx_cell_x", type='INT', domain='FACE')
            for i, bm_face in enumerate(bm.faces):
                attr.data[i].value = bm_face[cell_x_layer]
                
        if cell_z_layer:
            attr = mesh.attributes.new(name="arx_cell_z", type='INT', domain='FACE')
            for i, bm_face in enumerate(bm.faces):
                attr.data[i].value = bm_face[cell_z_layer]
                
        # Store vector and binary data as float arrays and byte colors
        if norm_layer:
            attr = mesh.attributes.new(name="arx_norm", type='FLOAT_VECTOR', domain='FACE')
            for i, bm_face in enumerate(bm.faces):
                norm = bm_face[norm_layer]
                attr.data[i].vector = (norm.x, norm.y, norm.z)
                
        if norm2_layer:
            attr = mesh.attributes.new(name="arx_norm2", type='FLOAT_VECTOR', domain='FACE')
            for i, bm_face in enumerate(bm.faces):
                norm2 = bm_face[norm2_layer]
                attr.data[i].vector = (norm2.x, norm2.y, norm2.z)
                
        if vertex_norms_layer:
            attr = mesh.attributes.new(name="arx_vertex_normals", type='BYTE_COLOR', domain='FACE')
            for i, bm_face in enumerate(bm.faces):
                # Store binary data as color (limited but better than nothing)
                data = bm_face[vertex_norms_layer]
                if len(data) >= 4:
                    attr.data[i].color = (data[0]/255.0, data[1]/255.0, data[2]/255.0, data[3]/255.0)
                else:
                    attr.data[i].color = (1.0, 1.0, 1.0, 1.0)
                
        # Transfer UV and vertex color data 
        self.transfer_uv_and_color_data(bm, mesh)
    
    def transfer_uv_and_color_data(self, bm, mesh):
        """Transfer UV coordinates and vertex colors from bmesh to mesh"""
        # Get bmesh layers
        uv_layer = bm.loops.layers.uv.active
        color_layer = bm.loops.layers.color.active
        
        if not uv_layer and not color_layer:
            return
            
        # Create UV layer in mesh if needed
        if uv_layer and not mesh.uv_layers:
            mesh.uv_layers.new(name="UVMap")
        
        # Create vertex color layer in mesh if needed
        if color_layer and not mesh.vertex_colors:
            mesh.vertex_colors.new(name="light-color")
        
        # Transfer UV and color data
        if uv_layer or color_layer:
            for bm_face, mesh_face in zip(bm.faces, mesh.polygons):
                for i, loop_index in enumerate(mesh_face.loop_indices):
                    bm_loop = bm_face.loops[i]
                    
                    # Transfer UV
                    if uv_layer and mesh.uv_layers.active:
                        uv = bm_loop[uv_layer].uv
                        mesh.uv_layers.active.data[loop_index].uv = uv
                    
                    # Transfer vertex color
                    if color_layer and mesh.vertex_colors.active:
                        color = bm_loop[color_layer]
                        mesh.vertex_colors.active.data[loop_index].color = color

    def AddScenePaths(self, scene, dlfData: DlfData, sceneOffset):
        """Create Blender curve objects for DLF paths"""
        if not dlfData.paths:
            return
            
        paths_col = bpy.data.collections.new(scene.name + '-paths')
        scene.collection.children.link(paths_col)
        
        for path_data, pathways in dlfData.paths:
            path_name = path_data.name.decode('iso-8859-1').strip('\x00')
            if not path_name:
                path_name = f"path_{path_data.idx}"
            
            # Create empty object for path center
            path_obj = bpy.data.objects.new(f'path:{path_name}', None)
            path_obj.empty_display_type = 'ARROWS'
            path_obj.empty_display_size = 1.0
            
            # Store path properties as custom properties
            path_obj["arx_path_idx"] = path_data.idx
            path_obj["arx_path_flags"] = path_data.flags
            path_obj["arx_path_height"] = path_data.height
            path_obj["arx_path_ambiance"] = path_data.ambiance.decode('iso-8859-1').strip('\x00')
            path_obj["arx_path_reverb"] = path_data.reverb
            path_obj["arx_path_farclip"] = path_data.farclip
            path_obj["arx_path_amb_max_vol"] = path_data.amb_max_vol
            
            # Position the path object itself
            path_abs_pos = Vector(sceneOffset) + Vector([path_data.pos.x, path_data.pos.y, path_data.pos.z])
            path_obj.location = arx_pos_to_blender_for_model(path_abs_pos) * 0.1
            
            # Create child empty objects for each pathway waypoint (discrete points)
            if pathways:
                for i, pathway in enumerate(pathways):
                    waypoint_name = f"{path_name}_waypoint_{i:03d}"
                    waypoint_obj = bpy.data.objects.new(f'waypoint:{waypoint_name}', None)
                    waypoint_obj.empty_display_type = 'SPHERE'
                    waypoint_obj.empty_display_size = 0.5
                    
                    # Position waypoint in local coordinates relative to path object
                    # pathway.rpos is relative to path.pos, so convert directly to Blender coordinates
                    local_pos = arx_pos_to_blender_for_model(Vector([pathway.rpos.x, pathway.rpos.y, pathway.rpos.z])) * 0.1
                    waypoint_obj.location = local_pos
                    
                    # Store pathway properties as custom properties
                    waypoint_obj["arx_pathway_flag"] = pathway.flag
                    waypoint_obj["arx_pathway_time"] = int(pathway.time)
                    waypoint_obj["arx_pathway_index"] = i
                    
                    # Parent waypoint to path for organization (sets local coordinate space)
                    waypoint_obj.parent = path_obj
                    
                    paths_col.objects.link(waypoint_obj)
            
            paths_col.objects.link(path_obj)
            print(f"DEBUG: Created path '{path_name}' with {len(pathways)} discrete waypoints")

    def AddSceneZones(self, scene, dlfData: DlfData, sceneOffset):
        """Create Blender objects for DLF zones (paths with height != 0)"""
        if not dlfData.zones:
            return
            
        zones_col = bpy.data.collections.new(scene.name + '-zones')
        scene.collection.children.link(zones_col)
        
        for zone_data, pathways in dlfData.zones:
            zone_name = zone_data.name.decode('iso-8859-1').strip('\x00')
            if not zone_name:
                zone_name = f"zone_{zone_data.idx}"
            
            # Create empty object for zone center
            zone_obj = bpy.data.objects.new(f'zone:{zone_name}', None)
            zone_obj.empty_display_type = 'CUBE'
            zone_obj.empty_display_size = 2.0
            
            # Position zone at center
            zone_abs_pos = Vector(sceneOffset) + Vector([zone_data.pos.x, zone_data.pos.y, zone_data.pos.z])
            zone_obj.location = arx_pos_to_blender_for_model(zone_abs_pos) * 0.1
            
            # Create child empty objects for zone boundary waypoints (discrete points)
            if pathways:
                for i, pathway in enumerate(pathways):
                    waypoint_name = f"{zone_name}_waypoint_{i:03d}"
                    waypoint_obj = bpy.data.objects.new(f'zone_waypoint:{waypoint_name}', None)
                    waypoint_obj.empty_display_type = 'CONE'
                    waypoint_obj.empty_display_size = 0.5
                    
                    # Position waypoint in local coordinates relative to zone object
                    # pathway.rpos is relative to zone.pos, so convert directly to Blender coordinates
                    local_pos = arx_pos_to_blender_for_model(Vector([pathway.rpos.x, pathway.rpos.y, pathway.rpos.z])) * 0.1
                    waypoint_obj.location = local_pos
                    
                    # Store pathway properties as custom properties
                    waypoint_obj["arx_pathway_flag"] = pathway.flag
                    waypoint_obj["arx_pathway_time"] = int(pathway.time)
                    waypoint_obj["arx_pathway_index"] = i
                    
                    # Parent waypoint to zone for organization (sets local coordinate space)
                    waypoint_obj.parent = zone_obj
                    
                    zones_col.objects.link(waypoint_obj)
            
            # Store zone properties as custom properties
            zone_obj["arx_zone_idx"] = zone_data.idx
            zone_obj["arx_zone_flags"] = zone_data.flags
            zone_obj["arx_zone_height"] = zone_data.height
            zone_obj["arx_zone_ambiance"] = zone_data.ambiance.decode('iso-8859-1').strip('\x00')
            zone_obj["arx_zone_reverb"] = zone_data.reverb
            zone_obj["arx_zone_farclip"] = zone_data.farclip
            zone_obj["arx_zone_amb_max_vol"] = zone_data.amb_max_vol
            
            zones_col.objects.link(zone_obj)
            pathway_count = len(pathways) if pathways else 0
            print(f"DEBUG: Created zone '{zone_name}' at {zone_obj.location} with {pathway_count} discrete waypoints")

    def AddSceneFogs(self, scene, dlfData: DlfData, sceneOffset):
        """Create Blender objects for DLF fogs"""
        if not dlfData.fogs:
            return
            
        fogs_col = bpy.data.collections.new(scene.name + '-fogs')
        scene.collection.children.link(fogs_col)
        
        for i, fog in enumerate(dlfData.fogs):
            fog_name = f"fog_{i:03d}"
            
            # Create empty object for fog
            fog_obj = bpy.data.objects.new(f'fog:{fog_name}', None)
            fog_obj.empty_display_type = 'SPHERE'
            fog_obj.empty_display_size = fog.size * 0.01  # Scale to Blender units
            
            # Store fog properties as custom properties
            fog_obj["arx_fog_size"] = fog.size
            fog_obj["arx_fog_special"] = fog.special
            fog_obj["arx_fog_scale"] = fog.scale
            fog_obj["arx_fog_speed"] = fog.speed
            fog_obj["arx_fog_rotatespeed"] = fog.rotatespeed
            fog_obj["arx_fog_tolive"] = fog.tolive
            fog_obj["arx_fog_blend"] = fog.blend
            fog_obj["arx_fog_frequency"] = fog.frequency
            
            # Convert position
            abs_pos = Vector(sceneOffset) + Vector([fog.pos.x, fog.pos.y, fog.pos.z])
            fog_obj.location = arx_pos_to_blender_for_model(abs_pos) * 0.1
            
            # Convert rotation
            fog_obj.rotation_euler = (radians(fog.angle.a), radians(fog.angle.b), radians(fog.angle.g))
            
            # Set color (use fog RGB for display)
            fog_obj.color = (fog.rgb.r / 255.0, fog.rgb.g / 255.0, fog.rgb.b / 255.0, 1.0)
            
            fogs_col.objects.link(fog_obj)
            print(f"DEBUG: Created fog '{fog_name}' at {fog_obj.location}")

    def AddSceneDlfLights(self, scene, dlfData: DlfData, sceneOffset):
        """Create Blender light objects for DLF lights"""
        if not dlfData.lights:
            return
            
        lights_col = bpy.data.collections.new(scene.name + '-dlf-lights')
        scene.collection.children.link(lights_col)
        
        for i, light in enumerate(dlfData.lights):
            light_name = f"dlf_light_{i:03d}"
            
            # Create light object
            light_data = bpy.data.lights.new(light_name, 'POINT')
            light_obj = bpy.data.objects.new(f'light:{light_name}', light_data)
            
            # Convert light properties
            light_data.energy = light.intensity * 100.0  # Scale for Blender
            light_data.color = (light.rgb.r / 255.0, light.rgb.g / 255.0, light.rgb.b / 255.0)
            if light.fallend > 0:
                light_data.distance = light.fallend * 0.1  # Scale to Blender units
            
            # Store additional properties
            light_obj["arx_light_fallstart"] = light.fallstart
            light_obj["arx_light_fallend"] = light.fallend
            light_obj["arx_light_intensity"] = light.intensity
            light_obj["arx_light_extras"] = light.extras
            
            # Convert position
            abs_pos = Vector(sceneOffset) + Vector([light.pos.x, light.pos.y, light.pos.z])
            light_obj.location = arx_pos_to_blender_for_model(abs_pos) * 0.1
            
            lights_col.objects.link(light_obj)
            print(f"DEBUG: Created DLF light '{light_name}' at {light_obj.location}")

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
            mappedMaterials.append((idx, tex.tc, createMaterial(self.dataPath, tex.fic.decode('iso-8859-1'))))
            idx += 1

        # Create mesh preserving quads
        bm = self.AddSceneBackground(ftsData.cells, llfData.levelLighting, mappedMaterials)
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

        self.AddScenePathfinderAnchors(scene, ftsData.anchors)
        self.AddScenePortals(scene, ftsData)
        self.AddSceneLights(scene, llfData, ftsData.sceneOffset)
        self.AddSceneObjects(scene, dlfData, ftsData.sceneOffset)
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
        return bm
    
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

        for portal in data.portals:
            bm = bmesh.new()

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
            self.log.info("Creating entity [{}]".format(entityId))

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
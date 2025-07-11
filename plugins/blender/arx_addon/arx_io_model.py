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
import itertools
import logging
import math
import bpy
import bmesh
from mathutils import Vector

from .arx_io_material import createMaterial
from .arx_io_util import arx_pos_to_blender_for_model, blender_pos_to_arx, ArxException
from .files import splitPath
from .dataFtl import FtlMetadata, FtlVertex, FtlFace, FtlGroup, FtlSelection, FtlAction, FtlData, FtlSerializer

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class ArxObjectManager(object):
    def __init__(self, ioLib, dataPath):
        self.log = logging.getLogger(__name__)
        self.ioLib = ioLib
        self.dataPath = dataPath
        self.ftlSerializer = FtlSerializer()

    def validateAssetDirectory(self):
        if not os.path.isdir(self.dataPath):
            raise ArxException("Arx assert directory path [" + self.dataPath + "] is not a directory")
        if not os.path.exists(self.dataPath):
            raise ArxException("Arx assert directory path [" + self.dataPath + "] does not exist")

    def validateObjectName(self, name):
        if len(name.encode('utf-8')) > 63:
            raise ArxException("Name ["+name+"] too long to be used as blender object name")

    def analyzeFaceData(self, faceData):
        facesToDrop = []
        seenFaceVerts = {}
        for i, face in enumerate(faceData):
            for foo in itertools.permutations(face.vids):
                if foo in seenFaceVerts:
                    seen = seenFaceVerts[foo]
                    facesToDrop.append(seen)
                    break
            seenFaceVerts[face.vids] = i
        if len(facesToDrop) > 0:
            self.log.debug("Dropping faces: " + str(facesToDrop))
        return facesToDrop

    def createBmesh(self, context, vertData, faceData) -> bmesh.types.BMesh:
        facesToDrop = self.analyzeFaceData(faceData)
        bm = bmesh.new()
        arxFaceType = bm.faces.layers.int.new('arx_facetype')
        arxTransVal = bm.faces.layers.float.new('arx_transval')
        uvData = bm.loops.layers.uv.verify()
        scale_factor = 0.1  # Normalize model size to Blender units
        for i, v in enumerate(vertData):
            vertex = bm.verts.new(arx_pos_to_blender_for_model(v.xyz) * scale_factor)
            vertex.normal = v.n
            vertex.index = i
        bm.verts.ensure_lookup_table()
        for i, f in enumerate(faceData):
            if i in facesToDrop:
                continue
            faceVerts = [bm.verts[v] for v in f.vids]
            try:
                face = bm.faces.new(faceVerts)
                face.index = i
            except ValueError:
                self.log.debug("Extra face")
            face.normal = Vector(f.normal)
            if f.texid >= 0:
                face.material_index = f.texid  # Set material index for face
            else:
                face.material_index = 0  # Default to first material
            face[arxFaceType] = f.facetype
            face[arxTransVal] = f.transval
            for j, loop in enumerate(face.loops):
                u, v = f.uvs[j]
                loop[uvData].uv = u, 1.0 - v
        bm.faces.ensure_lookup_table()
        bm.edges.index_update()
        bm.edges.ensure_lookup_table()
        return bm

    def createArmature(self, canonicalId, bm, groups) -> bpy.types.Object:
        amtname = "/".join(canonicalId) + "-amt"
        amt = bpy.data.armatures.new(amtname)
        amt.display_type = 'WIRE'
        amtobject = bpy.data.objects.new(amtname, amt)
        amtobject.location = (0, 0, 0)
        bpy.context.scene.collection.objects.link(amtobject)
        bpy.context.view_layer.objects.active = amtobject
        amtobject.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        edit_bones = amt.edit_bones
        scale_factor = 1  # Match model scale
        edit_bones_array = []  # Store bones for parenting
        
        # First pass: Create all bones with proper positioning
        for i, group in enumerate(groups):
            bGrpName = "grp:" + str(i).zfill(2) + ":" + group.name
            bone = edit_bones.new(bGrpName)
            
            # Set bone head
            if group.origin >= 0 and group.origin < len(bm.verts):
                bone.head = bm.verts[group.origin].co * scale_factor
            else:
                self.log.warning("Invalid origin index %d for group '%s', using (0,0,0)", group.origin, bGrpName)
                bone.head = Vector((0, 0, 0))
            
            # Set bone tail with improved logic
            tail_set = False
            children = [j for j, child_group in enumerate(groups) if child_group.parentIndex == i]
            
            if children:
                # Point towards first child
                child_group = groups[children[0]]
                if child_group.origin >= 0 and child_group.origin < len(bm.verts):
                    bone.tail = bm.verts[child_group.origin].co * scale_factor
                    tail_set = True
            
            if not tail_set:
                # For leaf bones, use parent direction or default to local bone orientation
                if group.parentIndex >= 0 and group.parentIndex < len(groups):
                    parent_group = groups[group.parentIndex]
                    if parent_group.origin >= 0 and parent_group.origin < len(bm.verts):
                        parent_pos = bm.verts[parent_group.origin].co * scale_factor
                        direction = bone.head - parent_pos
                        if direction.length > 0.001:
                            bone.tail = bone.head + direction.normalized() * (0.1 * scale_factor)
                        else:
                            bone.tail = bone.head + Vector((0, 0, 0.1 * scale_factor))  # Z-axis fallback
                    else:
                        bone.tail = bone.head + Vector((0, 0, 0.1 * scale_factor))
                else:
                    # Root bone: Use group’s default orientation if available
                    bone.tail = bone.head + Vector((0, 0, 0.1 * scale_factor))
            
            # Ensure non-zero length
            if (bone.tail - bone.head).length < 0.001 * scale_factor:
                bone.tail = bone.head + Vector((0, 0, 0.1 * scale_factor))
            
            bone["OriginVertex"] = group.origin
            edit_bones_array.append(bone)
            self.log.debug("Created bone '%s' at head=%s, tail=%s", bGrpName, bone.head, bone.tail)
        
        # Second pass: Set hierarchical parenting
        for i, group in enumerate(groups):
            if group.parentIndex >= 0 and group.parentIndex < len(groups):
                bone = edit_bones_array[i]
                bone.parent = edit_bones_array[group.parentIndex]
                self.log.debug("Set parent of bone '%s' to '%s'", bone.name, edit_bones_array[group.parentIndex].name)
        
        bpy.ops.object.mode_set(mode='OBJECT')
        return amtobject

    def createObject(self, context, bm, data: FtlData, canonicalId, collection) -> bpy.types.Object:
        idString = "/".join(canonicalId)
        self.validateObjectName(idString)
        mesh = bpy.data.meshes.new(idString)
        bm.to_mesh(mesh)
        armatureObj = self.createArmature(canonicalId, bm, data.groups)
        bm.free()
        if bpy.context.active_object:
            bpy.ops.object.mode_set(mode='OBJECT')
        obj = bpy.data.objects.new(name=mesh.name, object_data=mesh)
        obj['arx.ftl.name'] = data.metadata.name
        obj['arx.ftl.org'] = data.metadata.org
        # Link mesh to collection first
        collection.objects.link(obj)
        # Assign exclusive weights to vertex groups, prioritizing smaller groups
        vertex_to_group = {}
        # Iterate groups in reverse to prioritize smaller, discrete groups
        for i in reversed(range(len(data.groups))):
            group = data.groups[i]
            grp = obj.vertex_groups.new(name="grp:" + str(i).zfill(2) + ":" + group.name)
            if not group.indices or len(group.indices) == 0:
                self.log.warning("Vertex group '%s' is empty, no vertices assigned", grp.name)
                continue
            valid_indices = [v for v in group.indices if v >= 0 and v < len(mesh.vertices)]
            if len(valid_indices) < len(group.indices):
                self.log.warning("Group '%s' has %d invalid vertex indices", grp.name, len(group.indices) - len(valid_indices))
            for v in valid_indices:
                # Assign vertex to the first group it appears in (later groups take precedence)
                if v not in vertex_to_group:
                    vertex_to_group[v] = grp
                    self.log.debug("Assigned vertex %d to group '%s' with weight 1.0", v, grp.name)
        # Apply weights to vertex groups
        for v, grp in vertex_to_group.items():
            grp.add([v], 1.0, 'REPLACE')
        for i, s in enumerate(data.sels):
            grp = obj.vertex_groups.new(name="sel:" + str(i).zfill(2) + ":" + s.name)
            valid_indices = [v for v in s.indices if v >= 0 and v < len(mesh.vertices)]
            if valid_indices:
                grp.add(valid_indices, 1.0, 'REPLACE')
        for a in data.actions:
            action = bpy.data.objects.new(a.name, None)
            action.parent = obj
            action.parent_type = 'VERTEX'
            action.parent_vertices = [a.vidx, 0, 0]
            action.show_name = True
            collection.objects.link(action)
            if a.name.lower().startswith("hit_"):
                radius = int(a.name[4:])
                action.empty_display_type = 'SPHERE'
                action.empty_display_size = radius
                action.lock_rotation = [True, True, True]
                action.lock_scale = [True, True, True]
            else:
                action.scale = [3, 3, 3]
        # Bind armature to mesh
        armatureModifier = obj.modifiers.new(type='ARMATURE', name="Skeleton")
        armatureModifier.object = armatureObj
        # Assign materials to mesh
        for m in data.mats:
            mat = createMaterial(self.dataPath, m)
            obj.data.materials.append(mat)
        # Make armature a child of the mesh
        armatureObj.parent = obj
        # Link armature to collection and update scene
        collection.objects.link(armatureObj)
        bpy.context.view_layer.update()
        return obj

    def loadFile_data(self, filePath) -> FtlData:
        self.validateAssetDirectory()
        self.log.debug("Loading file: %s" % filePath)
        with open(filePath, "rb") as f:
            data = f.read()
            if data[:3] == b"FTL":
                unpacked = data
                self.log.debug("Loaded %i unpacked bytes from file %s" % (len(data), filePath))
            else:
                unpacked = self.ioLib.unpack(data)
                with open(filePath + ".unpack", "wb") as f:
                    f.write(unpacked)
                    self.log.debug("Written unpacked ftl")
                self.log.debug("Loaded %i packed bytes from file %s" % (len(data), filePath))
        ftlData = self.ftlSerializer.read(unpacked)
        for i, group in enumerate(ftlData.groups):
            father = self.getFatherIndex(ftlData.groups, i)
            self.log.debug("group %d with father %d" % (i, father))
            group.parentIndex = father
        return ftlData

    def getFatherIndex(self, groups, index):
        return groups[index].parentIndex

    def loadFile(self, context, filePath, scene, import_tweaks: bool) -> bpy.types.Object:
        ftlData = self.loadFile_data(filePath)
        objPath = os.path.join(self.dataPath, "game/graph/obj3d/interactive")
        relPath = os.path.relpath(filePath, objPath)
        split = splitPath(relPath)
        canonicalId = split[:-1]
        parent_collection = context.scene.collection
        idLen = len(canonicalId)
        for i in range(1, idLen + 1):
            prefix_str = "/".join(canonicalId[:i])
            if prefix_str in bpy.data.collections:
                parent_collection = bpy.data.collections[prefix_str]
            else:
                col = bpy.data.collections.new(prefix_str)
                parent_collection.children.link(col)
                parent_collection = col
        object_id_string = "/".join(canonicalId)
        self.log.debug("Canonical ID: %s" % object_id_string)
        bm = self.createBmesh(context, ftlData.verts, ftlData.faces)
        obj = self.createObject(context, bm, ftlData, canonicalId, parent_collection)
        if import_tweaks:
            file_dir = os.path.dirname(filePath)
            tweak_dir = os.path.join(file_dir, 'tweaks')
            if os.path.isdir(tweak_dir):
                for rel_tweak_file in os.listdir(tweak_dir):
                    abs_tweak_file = os.path.join(tweak_dir, rel_tweak_file)
                    tweak_data = self.loadFile_data(abs_tweak_file)
                    tweak_mesh = self.createBmesh(context, tweak_data.verts, tweak_data.faces)
                    tweak_obj_id = canonicalId.copy()
                    tweak_obj_id.append(os.path.splitext(rel_tweak_file)[0])
                    tweak_obj = self.createObject(context, tweak_mesh, tweak_data, tweak_obj_id, parent_collection)
                    tweak_obj.parent = obj
        return obj

    def toFtlData(self, obj) -> FtlData:

        #objs = [o for o in bpy.data.objects if o.type == 'MESH' and not o.hide]

        #if not objs:
        #    self.log.info("Nothing to export")

        #obj = objs[0]

        canonicalId = obj.name.split("/")
        self.log.debug("Exporting Canonical Id: %s" % str(canonicalId))

        # obj.update_from_editmode()

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.normal_update()

        arxFaceType = bm.faces.layers.int.get('arx_facetype')
        if not arxFaceType:
            raise ArxException("Mesh is missing arx specific data layer: " + 'arx_facetype')
        
        arxTransVal = bm.faces.layers.float.get('arx_transval')
        if not arxTransVal:
            raise ArxException("Mesh is missing arx specific data layer: " + 'arx_transval')
        
        if not (math.isclose(obj.location[0], 0.0) and math.isclose(obj.location[1], 0.0) and math.isclose(obj.location[2], 0.0)):
            raise ArxException("Object is moved, please apply the location to the vertex positions")
        
        if not (math.isclose(obj.rotation_euler[0], 0.0) and math.isclose(obj.rotation_euler[1], 0.0) and math.isclose(obj.rotation_euler[2], 0.0)):
            raise ArxException("Object is rotated, please apply the rotation to the vertex positions")
        
        if not (math.isclose(obj.scale[0], 1.0) and math.isclose(obj.scale[1], 1.0) and math.isclose(obj.scale[2], 1.0)):
            raise ArxException("Object is scaled, please apply the scale to the vertex positions")
        

        for f in bm.faces:
            if len(f.loops) > 3:
                raise ArxException("Face with more than 3 vertices found")

        for o in bpy.data.objects:
            for ms in o.material_slots:
                if not ms.material.name.endswith('-mat'):
                    raise ArxException("Material slot names must end with: " + '-mat')
                    
        
        # Validate child empties representing action points
        for child in bpy.data.objects:
            if child.type == 'EMPTY' and child.parent == obj:
                nameParts = child.name.split(".")
                name = nameParts[0].lower()
                print(nameParts)
                if name.startswith("hit_"):
                    pass
                elif name == "view_attach":
                    pass
                elif name == "primary_attach":
                    pass
                elif name == "left_attach":
                    pass
                elif name == "weapon_attach":
                    pass
                elif name == "secondary_attach":
                    pass
                elif name == "fire":
                    pass
                else:
                    self.log.warn("Unexpected child empty: {}".format(nameParts))
                    
        
        # TODO validate the mesh

        verts = []
        
        # First add all mesh vertices
        # Reverse the 0.1 scale factor that was applied during import
        scale_factor = 0.1
        for v in bm.verts:
            vertexNormals = [sc.normal for sc in bm.verts if sc.co == v.co]
            normal = Vector((0.0, 0.0, 0.0))
            for n in vertexNormals:
                normal += v.normal
            normal.normalize()
            # Scale vertex coordinates back up to original Arx size
            scaled_co = [coord / scale_factor for coord in v.co[:]]
            verts.append(FtlVertex(
                blender_pos_to_arx(scaled_co),
                blender_pos_to_arx(normal)
            ))
        
        originVertexIndex = -1
        for index, vert in enumerate(verts):
            if vert.xyz == (0.0, 0.0, 0.0):
                #self.log.info("Origin vertex found at index {}".format(index))
                originVertexIndex = index
        
        if originVertexIndex == -1:
            self.log.info("Origin vertex not found, adding new one")
            originVertexIndex = len(verts)
            verts.append(FtlVertex((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))
        
        metadata = FtlMetadata(name=obj.get('arx.ftl.name', ''), org=originVertexIndex)
        
        # Add action point vertices
        actions = []
        for o in bpy.data.objects:
            if o.type == 'EMPTY' and o.parent == obj:
                nameParts = o.name.split(".")
                name = nameParts[0]
                if o.parent_type == 'VERTEX':
                    actionVertexIndex = o.parent_vertices[0]
                    actions.append(FtlAction(name, actionVertexIndex))
                elif o.parent_type == 'OBJECT':
                    actionVertexIndex = len(verts)
                    # Scale action point coordinates back up to original Arx size
                    scaled_location = [coord / scale_factor for coord in o.location]
                    verts.append(FtlVertex(tuple(scaled_location), (0.0, 0.0, 0.0)))
                    actions.append(FtlAction(name, actionVertexIndex))
                else:
                    self.log.warn("Unhandled empty parent type {}".format(o.parent_type))

        uvData = bm.loops.layers.uv.verify()

        allXYZ = [v.xyz for v in verts]
        faces = []

        for f in bm.faces:
            vertexIndices = []
            vertexUvs = []
            vertexNormals = []
            for c in f.loops:
                # Apply the same scaling as used for vertex creation to match allXYZ
                scaled_co = [coord / scale_factor for coord in c.vert.co[:]]
                vertexIndices.append(allXYZ.index(blender_pos_to_arx(scaled_co)))
                vertexUvs.append((c[uvData].uv[0], 1 - c[uvData].uv[1]))
                vertexNormals.append((c.vert.normal[0], c.vert.normal[1], c.vert.normal[2]))
            mat = f.material_index

            faceType = f[arxFaceType]
            transval = f[arxTransVal]

            faces.append(FtlFace(
                vids=tuple(vertexIndices),
                uvs=vertexUvs,
                texid=mat,
                facetype=faceType,
                transval=transval,
                normal=vertexNormals
            ))

        grps = []
        sels = []

        dvert_lay = bm.verts.layers.deform.active

        for grp in obj.vertex_groups:
            v = []
            if dvert_lay is not None:
                for vert in bm.verts:
                    dvert = vert[dvert_lay]
                    if grp.index in dvert:
                        v.append(vert.index)

            s = grp.name.split(":")
            if s[0] == "grp":
                armature = bpy.data.armatures.get("/".join(canonicalId))
                if armature:
                    origin = armature.bones[grp.name]["OriginVertex"]
                else:
                    # TODO hardcoded use of mesh vertex at index 0
                    origin = 0
                
                # TODO get the real data from armature
                parentIndex = -1
                grps.append(FtlGroup(s[2], origin, v, parentIndex))
            else:
                sels.append(FtlSelection(s[2], v))

        matNames = []
        for o in bpy.data.objects:
            for ms in o.material_slots:
                mat = ms.material
                # strip -mat suffix and decorate with bullshit
                matNames.append('GRAPH\\OBJ3D\\TEXTURES\\' + mat.name[:-4] + ".FOO")

        bm.free()

        return FtlData(
            metadata=metadata,
            verts=verts,
            faces=faces,
            mats=matNames,
            groups=grps,
            actions=actions,
            sels=sels
        )

    def saveFile(self, path):
        # Get the active object from the current scene
        obj = bpy.context.active_object
        if obj is None or obj.type != 'MESH':
            raise ArxException("No active mesh object to export")

        data = self.toFtlData(obj)

        binData = self.ftlSerializer.write(data)

        with open(path, 'wb') as f:
            f.write(binData)

        self.log.debug("Written %i bytes to file %s" % (len(binData), path))

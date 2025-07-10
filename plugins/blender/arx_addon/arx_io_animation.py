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
import re
from mathutils import Vector, Quaternion, Matrix
from .arx_io_util import arx_pos_to_blender_for_model, blender_pos_to_arx, ArxException
from .dataTea import TeaSerializer

def arx_transform_to_blender(location, rotation, scale, scale_factor=0.1):
    loc = arx_pos_to_blender_for_model(location) * scale_factor
    rot = Quaternion((rotation.w, rotation.x, rotation.y, rotation.z))
    scl = Vector((1.0, 1.0, 1.0)) if scale.length == 0 else Vector((scale.x, scale.z, scale.y))
    return loc, rot, scl

def parse_group_index(name):
    """
    Parse the group index from vertex group or bone names.
    Handles formats like 'grp:23:toe4', 'grp:00:all', etc.
    Returns the numeric index or None if not found.
    """
    # Try to match pattern like 'grp:XX:name'
    match = re.match(r'grp:(\d+):', name)
    if match:
        return int(match.group(1))
    
    # Try to match pattern like 'group_XX' or similar
    match = re.search(r'(\d+)', name)
    if match:
        return int(match.group(1))
    
    return None

class ArxAnimationManager(object):
    def __init__(self):
        self.log = logging.getLogger('ArxAnimationManager')
        self.teaSerializer = TeaSerializer()

    def build_bone_index_map(self, armature_obj):
        """
        Build a mapping from group indices to bone objects.
        """
        bone_map = {}
        for bone in armature_obj.pose.bones:
            group_index = parse_group_index(bone.name)
            if group_index is not None:
                bone_map[group_index] = bone
                self.log.debug("Mapped bone '%s' to group index %d", bone.name, group_index)
            else:
                self.log.warning("Could not parse group index from bone name: %s", bone.name)
        
        return bone_map

    def build_vertex_group_index_map(self, obj):
        """
        Build a mapping from group indices to vertex group names.
        """
        vg_map = {}
        for vg in obj.vertex_groups:
            group_index = parse_group_index(vg.name)
            if group_index is not None:
                vg_map[group_index] = vg.name
                self.log.debug("Mapped vertex group '%s' to group index %d", vg.name, group_index)
            else:
                self.log.warning("Could not parse group index from vertex group name: %s", vg.name)
        
        return vg_map

    def loadAnimation(self, path, action_name=None, frame_rate=24.0, scale_factor=0.1, axis_transform=None):
        data = self.teaSerializer.read(path)
        if not data:
            self.log.error("No animation data loaded from file: {}".format(path))
            return None

        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            self.log.error("No mesh object selected for animation import")
            return None

        # Find the armature
        armature_obj = None
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object:
                armature_obj = modifier.object
                break

        if not armature_obj:
            self.log.error("No armature found for mesh '%s'", obj.name)
            return None

        # Build index mappings
        bone_map = self.build_bone_index_map(armature_obj)
        vg_map = self.build_vertex_group_index_map(obj)

        self.log.info("Mesh '%s' has %d vertex groups, %d with parseable indices", 
                      obj.name, len(obj.vertex_groups), len(vg_map))
        self.log.info("Armature '%s' has %d bones, %d with parseable indices", 
                      armature_obj.name, len(armature_obj.pose.bones), len(bone_map))

        num_groups = len(data[0].groups)
        self.log.info("Animation has %d groups per frame", num_groups)

        # Check what indices we can actually animate
        animatable_indices = set(bone_map.keys()) & set(range(num_groups))
        self.log.info("Can animate %d groups (indices: %s)", 
                      len(animatable_indices), sorted(animatable_indices))

        if not animatable_indices:
            self.log.error("No matching bone indices found for animation groups")
            return None

        # Create or update animation action
        if not armature_obj.animation_data:
            armature_obj.animation_data_create()

        action_name = action_name or f"{armature_obj.name}_{path.split('/')[-1].replace('.tea', '')}"
        
        # Clear existing action if it exists
        for action in bpy.data.actions:
            if action.name == action_name:
                bpy.data.actions.remove(action)

        action = bpy.data.actions.new(action_name)
        armature_obj.animation_data.action = action

        # Set up for animation
        bpy.context.scene.frame_set(1)
        total_time = 0.0

        for frame_index, frame in enumerate(data):
            self.log.debug("Processing frame %d: duration=%s, groups=%d", 
                          frame_index, frame.duration, len(frame.groups))

            # Handle global transforms (if needed)
            if frame.translation:
                self.log.debug("Frame %d: Global translation=%s (skipping)", 
                              frame_index, frame.translation)
            if frame.rotation:
                self.log.debug("Frame %d: Global rotation=%s (skipping)", 
                              frame_index, frame.rotation)

            # Set armature to pose mode
            bpy.context.view_layer.objects.active = armature_obj
            bpy.ops.object.mode_set(mode='POSE')

            # Process each animation group
            for group_index in range(min(num_groups, len(frame.groups))):
                if group_index not in bone_map:
                    continue  # Skip groups that don't have corresponding bones

                group = frame.groups[group_index]
                bone = bone_map[group_index]

                # Skip inactive groups
                if group.key_group == -1:
                    continue

                self.log.debug("Frame %d, Group %d, Bone %s: translate=%s, Quaternion=%s, zoom=%s",
                               frame_index, group_index, bone.name, 
                               group.translate, group.Quaternion, group.zoom)

                # Extract transform data
                location = Vector((group.translate.x, group.translate.y, group.translate.z))
                rotation = Quaternion((group.Quaternion.w, group.Quaternion.x, 
                                      group.Quaternion.y, group.Quaternion.z))
                scale = Vector((group.zoom.x, group.zoom.y, group.zoom.z))

                # Apply coordinate system transform
                if axis_transform:
                    loc, rot, scl = axis_transform(location, rotation, scale, scale_factor)
                else:
                    loc, rot, scl = arx_transform_to_blender(location, rotation, scale, scale_factor)

                # Apply transforms to bone
                bone.location = loc
                bone.rotation_mode = 'QUATERNION'
                bone.rotation_quaternion = rot
                bone.scale = scl

                # Insert keyframes
                bone.keyframe_insert(data_path="location")
                bone.keyframe_insert(data_path="rotation_quaternion")
                bone.keyframe_insert(data_path="scale")

                self.log.debug("Frame %d, Group %d, Bone %s: Applied loc=%s, rot=%s, scl=%s",
                               frame_index, group_index, bone.name, loc, rot, scl)

            # Return to object mode
            bpy.ops.object.mode_set(mode='OBJECT')

            # Calculate frame timing
            duration_ms = frame.duration
            duration_frames = max(1, int(duration_ms / 1000.0 * frame_rate))
            total_time += duration_ms / 1000.0

            # Advance to next frame
            bpy.context.scene.frame_set(bpy.context.scene.frame_current + duration_frames)

        # Set animation end frame
        bpy.context.scene.frame_end = bpy.context.scene.frame_current

        self.log.info("Animation loaded successfully: %d frames, %d animated bones, total time %.2f s",
                      len(data), len(animatable_indices), total_time)

        return action

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

from mathutils import Vector, Matrix, Quaternion

class ArxException(Exception):
    """Common exception thrown by this addon"""
    pass

class InconsistentStateException(Exception):
    """Thrown if data supposed to be added to existing data does not match"""
    pass

def arx_pos_to_blender_for_model(pos):
    """x=>x; y=>-z; z=>y"""
    return Vector((pos[0], pos[2], -pos[1]))

def blender_pos_to_arx(pos):
    return (pos[0], -pos[2], pos[1])


def arx_transform_to_blender(location, rotation, scale, scale_factor=0.1, flip_w=True, flip_x=False, flip_y=True, flip_z=False):
    # Transform location
    loc = arx_pos_to_blender_for_model(location) * scale_factor
    
    # Transform quaternion
    rot = Quaternion((rotation.w, rotation.x, rotation.y, rotation.z))
    # Apply flips
    w, x, y, z = rot
    rot = Quaternion((
        -w if flip_w else w,
        -x if flip_x else x,
        -y if flip_y else y,
        -z if flip_z else z
    ))
    # Apply coordinate system transformation
    rot_matrix = rot.to_matrix().to_4x4()
    transform_matrix = Matrix([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])  # x=>x, y=>-z, z=>y
    transformed_matrix = transform_matrix @ rot_matrix @ transform_matrix.inverted()
    rot = transformed_matrix.to_quaternion()
    
    # Transform scale
    scl = Vector((1.0, 1.0, 1.0)) if scale.length == 0 else Vector((scale.x, scale.z, scale.y))
    
    return loc, rot, scl



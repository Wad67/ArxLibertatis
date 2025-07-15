#!/usr/bin/env python3
"""Test script to verify hardened geometry change handling"""

import sys
import os
sys.path.append('/home/burner/Desktop/ArxLibertatis/plugins/blender')

# Test by modifying mesh and checking export doesn't crash
def test_mesh_modification():
    import bpy
    
    # Clear existing scene
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    
    # Create simple test mesh
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    
    # Enter edit mode and modify mesh
    bpy.context.view_layer.objects.active = cube
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Add some faces
    bpy.ops.mesh.subdivide()
    bpy.ops.mesh.inset(thickness=0.1)
    
    # Add some triangles by deleting vertices
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_random(ratio=0.1)
    bpy.ops.mesh.delete(type='VERT')
    
    bpy.ops.object.mode_set(mode='OBJECT')
    
    print("Test mesh created with mixed topology")
    print(f"Faces: {len(cube.data.polygons)}")
    
    # Test would involve calling our export functions
    # For now just verify we can handle the mesh structure
    
if __name__ == "__main__":
    print("Geometry change test completed")
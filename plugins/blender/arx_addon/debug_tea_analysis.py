#!/usr/bin/env python3
"""
Debug script to analyze TEA animation data and find patterns in problematic animations.
"""

import sys
import os
import json

# Fix relative imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataTea import TeaSerializer

def analyze_tea_file(tea_path):
    """Analyze a TEA file and extract key metrics"""
    serializer = TeaSerializer()
    try:
        data = serializer.read(tea_path)
        if not data:
            return None
            
        analysis = {
            'file': os.path.basename(tea_path),
            'num_frames': len(data),
            'num_groups': len(data[0].groups) if data else 0,
            'frame_analysis': [],
            'group_analysis': {}
        }
        
        # Analyze each frame
        for frame_idx, frame in enumerate(data):
            frame_info = {
                'frame': frame_idx,
                'has_translation': frame.translation is not None,
                'has_rotation': frame.rotation is not None,
                'groups_with_data': []
            }
            
            # Analyze each group in the frame
            for group_idx, group in enumerate(frame.groups):
                if group.key_group != -1:  # Has animation data
                    group_info = {
                        'group_idx': group_idx,
                        'translate': {
                            'x': getattr(group.translate, 'x', 0),
                            'y': getattr(group.translate, 'y', 0), 
                            'z': getattr(group.translate, 'z', 0)
                        },
                        'rotation': {
                            'w': getattr(group.Quaternion, 'w', 1),
                            'x': getattr(group.Quaternion, 'x', 0),
                            'y': getattr(group.Quaternion, 'y', 0),
                            'z': getattr(group.Quaternion, 'z', 0)
                        },
                        'scale': {
                            'x': getattr(group.zoom, 'x', 1),
                            'y': getattr(group.zoom, 'y', 1),
                            'z': getattr(group.zoom, 'z', 1)
                        }
                    }
                    frame_info['groups_with_data'].append(group_info)
                    
                    # Track per-group statistics
                    if group_idx not in analysis['group_analysis']:
                        analysis['group_analysis'][group_idx] = {
                            'active_frames': 0,
                            'translate_ranges': {'x': [], 'y': [], 'z': []},
                            'rotation_ranges': {'w': [], 'x': [], 'y': [], 'z': []},
                            'scale_ranges': {'x': [], 'y': [], 'z': []}
                        }
                    
                    group_stats = analysis['group_analysis'][group_idx]
                    group_stats['active_frames'] += 1
                    
                    # Track value ranges
                    for axis in ['x', 'y', 'z']:
                        group_stats['translate_ranges'][axis].append(getattr(group.translate, axis, 0))
                        group_stats['scale_ranges'][axis].append(getattr(group.zoom, axis, 1))
                    
                    for axis in ['w', 'x', 'y', 'z']:
                        group_stats['rotation_ranges'][axis].append(getattr(group.Quaternion, axis, 1 if axis == 'w' else 0))
            
            analysis['frame_analysis'].append(frame_info)
        
        # Calculate summary statistics
        for group_idx, stats in analysis['group_analysis'].items():
            for transform_type in ['translate_ranges', 'rotation_ranges', 'scale_ranges']:
                for axis, values in stats[transform_type].items():
                    if values:
                        stats[transform_type][axis] = {
                            'min': min(values),
                            'max': max(values),
                            'avg': sum(values) / len(values),
                            'count': len(values)
                        }
                    else:
                        stats[transform_type][axis] = {'min': 0, 'max': 0, 'avg': 0, 'count': 0}
        
        return analysis
        
    except Exception as e:
        print(f"Error analyzing {tea_path}: {e}")
        return None

def compare_animations(working_tea_path, problematic_tea_path):
    """Compare two animations to find differences"""
    working = analyze_tea_file(working_tea_path)
    problematic = analyze_tea_file(problematic_tea_path)
    
    if not working or not problematic:
        print("Failed to analyze one or both files")
        return
    
    print(f"Comparing {working['file']} (working) vs {problematic['file']} (problematic)")
    print(f"Working: {working['num_frames']} frames, {working['num_groups']} groups")
    print(f"Problematic: {problematic['num_frames']} frames, {problematic['num_groups']} groups")
    
    # Find groups that exist in both animations
    common_groups = set(working['group_analysis'].keys()) & set(problematic['group_analysis'].keys())
    
    print(f"\nCommon groups: {sorted(common_groups)}")
    
    # Look for significant differences in group behavior
    for group_idx in sorted(common_groups):
        w_group = working['group_analysis'][group_idx]
        p_group = problematic['group_analysis'][group_idx]
        
        print(f"\nGroup {group_idx}:")
        print(f"  Working active frames: {w_group['active_frames']}")
        print(f"  Problematic active frames: {p_group['active_frames']}")
        
        # Check for significant differences in rotation ranges
        for axis in ['w', 'x', 'y', 'z']:
            w_rot = w_group['rotation_ranges'][axis]
            p_rot = p_group['rotation_ranges'][axis]
            
            if w_rot['count'] > 0 and p_rot['count'] > 0:
                diff = abs(w_rot['avg'] - p_rot['avg'])
                if diff > 0.1:  # Significant difference
                    print(f"    Rotation {axis}: working_avg={w_rot['avg']:.3f}, problematic_avg={p_rot['avg']:.3f}, diff={diff:.3f}")
        
        # Check for significant differences in translation ranges
        for axis in ['x', 'y', 'z']:
            w_trans = w_group['translate_ranges'][axis]
            p_trans = p_group['translate_ranges'][axis]
            
            if w_trans['count'] > 0 and p_trans['count'] > 0:
                diff = abs(w_trans['avg'] - p_trans['avg'])
                if diff > 0.01:  # Significant difference
                    print(f"    Translation {axis}: working_avg={w_trans['avg']:.3f}, problematic_avg={p_trans['avg']:.3f}, diff={diff:.3f}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_tea_analysis.py <tea_file1> [tea_file2]")
        print("  With one file: analyze the file")
        print("  With two files: compare them")
        return
    
    tea_file1 = sys.argv[1]
    
    if len(sys.argv) == 2:
        # Single file analysis
        result = analyze_tea_file(tea_file1)
        if result:
            print(json.dumps(result, indent=2))
    else:
        # Compare two files
        tea_file2 = sys.argv[2]
        compare_animations(tea_file1, tea_file2)

if __name__ == "__main__":
    main()
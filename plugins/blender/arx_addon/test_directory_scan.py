#!/usr/bin/env python3
"""
Test script for directory scanning to find actual FTL and TEA files.
This will help understand the real file structure and naming patterns.
"""

import os
import glob
from pathlib import Path

def scan_for_files(root_path, show_samples=True):
    """Scan directory for FTL and TEA files and analyze patterns"""
    
    print(f"Scanning: {root_path}")
    print("=" * 60)
    
    if not os.path.exists(root_path):
        print(f"ERROR: Directory does not exist: {root_path}")
        return
    
    # Find all FTL files
    ftl_files = glob.glob(f"{root_path}/**/*.ftl", recursive=True)
    tea_files = glob.glob(f"{root_path}/**/*.tea", recursive=True)
    
    print(f"Found {len(ftl_files)} FTL files")
    print(f"Found {len(tea_files)} TEA files")
    
    if len(ftl_files) == 0 and len(tea_files) == 0:
        print("No FTL or TEA files found.")
        print("Make sure you're pointing to the correct Arx data directory.")
        return
    
    # Analyze FTL files
    if ftl_files:
        print(f"\n--- FTL FILES (Models) ---")
        
        # Group by directory
        ftl_by_dir = {}
        for ftl_path in ftl_files:
            dir_name = os.path.dirname(ftl_path)
            if dir_name not in ftl_by_dir:
                ftl_by_dir[dir_name] = []
            ftl_by_dir[dir_name].append(os.path.basename(ftl_path))
        
        # Show directory structure
        for dir_path in sorted(ftl_by_dir.keys()):
            rel_path = os.path.relpath(dir_path, root_path)
            files = ftl_by_dir[dir_path]
            print(f"\n{rel_path}/ ({len(files)} files)")
            
            if show_samples:
                for file_name in sorted(files)[:5]:  # Show first 5
                    print(f"  {file_name}")
                if len(files) > 5:
                    print(f"  ... and {len(files) - 5} more")
        
        # Look for patterns in FTL names
        print(f"\n--- FTL NAME PATTERNS ---")
        base_models = [f for f in ftl_files if 'base' in os.path.basename(f).lower()]
        player_models = [f for f in ftl_files if 'player' in os.path.basename(f).lower()]
        human_models = [f for f in ftl_files if 'human' in os.path.basename(f).lower()]
        
        print(f"Models with 'base': {len(base_models)}")
        for model in base_models[:10]:
            print(f"  {os.path.basename(model)}")
        
        print(f"Models with 'player': {len(player_models)}")
        for model in player_models[:5]:
            print(f"  {os.path.basename(model)}")
        
        print(f"Models with 'human': {len(human_models)}")
        for model in human_models[:5]:
            print(f"  {os.path.basename(model)}")
    
    # Analyze TEA files
    if tea_files:
        print(f"\n--- TEA FILES (Animations) ---")
        
        # Group by directory
        tea_by_dir = {}
        for tea_path in tea_files:
            dir_name = os.path.dirname(tea_path)
            if dir_name not in tea_by_dir:
                tea_by_dir[dir_name] = []
            tea_by_dir[dir_name].append(os.path.basename(tea_path))
        
        # Show directory structure
        for dir_path in sorted(tea_by_dir.keys()):
            rel_path = os.path.relpath(dir_path, root_path)
            files = tea_by_dir[dir_path]
            print(f"\n{rel_path}/ ({len(files)} files)")
            
            if show_samples:
                for file_name in sorted(files)[:5]:  # Show first 5
                    print(f"  {file_name}")
                if len(files) > 5:
                    print(f"  ... and {len(files) - 5} more")
        
        # Look for animation patterns
        print(f"\n--- ANIMATION NAME PATTERNS ---")
        
        animation_patterns = {
            'walk': [f for f in tea_files if 'walk' in os.path.basename(f).lower()],
            'attack': [f for f in tea_files if 'attack' in os.path.basename(f).lower()],
            'cast': [f for f in tea_files if 'cast' in os.path.basename(f).lower()],
            'idle/wait': [f for f in tea_files if any(x in os.path.basename(f).lower() for x in ['idle', 'wait'])],
            'human': [f for f in tea_files if 'human' in os.path.basename(f).lower()],
            'problem': [f for f in tea_files if 'problem' in os.path.basename(f).lower()],
        }
        
        for pattern_name, matching_files in animation_patterns.items():
            print(f"\nAnimations with '{pattern_name}': {len(matching_files)}")
            for anim in matching_files[:5]:
                print(f"  {os.path.basename(anim)}")
            if len(matching_files) > 5:
                print(f"  ... and {len(matching_files) - 5} more")

def test_matching_logic(root_path):
    """Test the matching logic on real files"""
    
    print(f"\n\n--- TESTING MATCHING LOGIC ---")
    
    ftl_files = glob.glob(f"{root_path}/**/*.ftl", recursive=True)
    tea_files = glob.glob(f"{root_path}/**/*.tea", recursive=True)
    
    if not ftl_files or not tea_files:
        print("Not enough files to test matching logic.")
        return
    
    # Extract actor names from FTL files
    def extract_actor_name(file_path):
        basename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(basename)[0].lower()
        
        # Remove common suffixes
        suffixes = ['_base', '_tweaks', '_lod', '_low', '_high']
        for suffix in suffixes:
            if name_without_ext.endswith(suffix):
                name_without_ext = name_without_ext[:-len(suffix)]
                break
        
        return name_without_ext
    
    # Test matching for a few actors
    actors = {}
    for ftl_path in ftl_files[:10]:  # Test first 10 FTL files
        actor_name = extract_actor_name(ftl_path)
        actors[actor_name] = {'ftl': ftl_path, 'animations': []}
    
    # Try to match animations
    def animation_matches_actor(tea_path, actor_name):
        tea_basename = os.path.basename(tea_path).lower()
        tea_name = os.path.splitext(tea_basename)[0]
        
        if actor_name in tea_name:
            return True
        
        # Check directory
        tea_dir = os.path.dirname(tea_path).lower()
        if actor_name in tea_dir:
            return True
        
        return False
    
    print("Testing animation matching for discovered actors:")
    
    for actor_name, actor_data in actors.items():
        print(f"\nActor: {actor_name}")
        print(f"  FTL: {os.path.basename(actor_data['ftl'])}")
        
        matched_animations = []
        for tea_path in tea_files:
            if animation_matches_actor(tea_path, actor_name):
                matched_animations.append(tea_path)
        
        print(f"  Matched animations: {len(matched_animations)}")
        for anim in matched_animations[:3]:  # Show first 3
            print(f"    {os.path.basename(anim)}")
        if len(matched_animations) > 3:
            print(f"    ... and {len(matched_animations) - 3} more")

def suggest_directories():
    """Suggest common locations where Arx data might be found"""
    
    print("\n--- SUGGESTED DIRECTORIES TO SCAN ---")
    
    possible_paths = [
        "/home/burner/Desktop/ArxLibertatis",
        "/home/burner/Desktop/ArxLibertatis/data", 
        "/home/burner/Desktop/ArxLibertatis/game",
        "/home/burner/Desktop/ArxLibertatis/plugins/blender/arx_addon",
        ".",  # Current directory
        "../",  # Parent directory
        "../../",  # Grandparent directory
    ]
    
    print("Try running this script with one of these paths:")
    for path in possible_paths:
        if os.path.exists(path):
            ftl_count = len(glob.glob(f"{path}/**/*.ftl", recursive=True))
            tea_count = len(glob.glob(f"{path}/**/*.tea", recursive=True))
            status = f"({ftl_count} FTL, {tea_count} TEA)" if ftl_count > 0 or tea_count > 0 else "(no files found)"
            print(f"  python3 test_directory_scan.py \"{path}\" {status}")
        else:
            print(f"  python3 test_directory_scan.py \"{path}\" (does not exist)")

def main():
    import sys
    
    if len(sys.argv) > 1:
        root_path = sys.argv[1]
        scan_for_files(root_path)
        test_matching_logic(root_path)
    else:
        print("Usage: python3 test_directory_scan.py <directory_path>")
        suggest_directories()

if __name__ == "__main__":
    main()
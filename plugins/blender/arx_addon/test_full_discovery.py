#!/usr/bin/env python3
"""
Test script for full actor discovery using the actual Arx Fatalis directory structure.
"""

import os
import sys
from test_actor_discovery import discover_actors, analyze_actors, save_results

def discover_arx_actors(arx_root_path):
    """
    Discover actors using the actual Arx Fatalis directory structure.
    
    Args:
        arx_root_path: Path to the Arx Fatalis root directory
    """
    
    print(f"Discovering Arx actors in: {arx_root_path}")
    
    # Key paths in Arx Fatalis structure
    npc_model_path = os.path.join(arx_root_path, "game", "graph", "obj3d", "interactive", "npc")
    npc_anim_path = os.path.join(arx_root_path, "graph", "obj3d", "anims", "npc")
    
    print(f"NPC Models: {npc_model_path}")
    print(f"NPC Animations: {npc_anim_path}")
    
    # Check if paths exist
    if not os.path.exists(npc_model_path):
        print(f"ERROR: NPC model path does not exist: {npc_model_path}")
        return None, None
    
    if not os.path.exists(npc_anim_path):
        print(f"ERROR: NPC animation path does not exist: {npc_anim_path}")
        return None, None
    
    # Create a combined search directory structure
    # We'll search both directories as if they were one
    combined_paths = [npc_model_path, npc_anim_path]
    
    all_actors = {}
    all_unmatched = []
    
    # First, discover actors from models
    print("\n=== DISCOVERING ACTORS FROM MODELS ===")
    model_actors, model_unmatched = discover_actors(npc_model_path)
    all_actors.update(model_actors)
    all_unmatched.extend(model_unmatched)
    
    # Then, try to match animations to discovered actors
    print("\n=== MATCHING ANIMATIONS TO ACTORS ===")
    import glob
    
    tea_files = glob.glob(f"{npc_anim_path}/**/*.tea", recursive=True)
    print(f"Found {len(tea_files)} animation files")
    
    # Improved matching logic
    matched_count = 0
    unmatched_anims = []
    
    for tea_path in tea_files:
        tea_basename = os.path.basename(tea_path)
        anim_name = os.path.splitext(tea_basename)[0]
        
        matched = False
        
        # Try to match with each actor
        for actor_name, actor in all_actors.items():
            if match_animation_to_actor(anim_name, actor_name):
                # Classify animation
                from test_actor_discovery import classify_animation_type
                anim_type, layer = classify_animation_type(anim_name)
                
                actor.add_animation(anim_name, tea_path, anim_type, layer)
                print(f"  ✓ {actor_name}: {anim_name} (type: {anim_type}, layer: {layer})")
                matched = True
                matched_count += 1
                break
        
        if not matched:
            unmatched_anims.append(tea_path)
    
    print(f"\nAnimation matching results:")
    print(f"  Total animations: {len(tea_files)}")
    print(f"  Matched: {matched_count}")
    print(f"  Unmatched: {len(unmatched_anims)}")
    
    # Show some unmatched animations for debugging
    if unmatched_anims:
        print(f"\nSample unmatched animations:")
        for anim_path in unmatched_anims[:10]:
            print(f"  {os.path.basename(anim_path)}")
        if len(unmatched_anims) > 10:
            print(f"  ... and {len(unmatched_anims) - 10} more")
    
    all_unmatched.extend(unmatched_anims)
    
    return all_actors, all_unmatched

def match_animation_to_actor(anim_name, actor_name):
    """
    Enhanced matching logic for animations to actors.
    """
    anim_lower = anim_name.lower()
    actor_lower = actor_name.lower()
    
    # Direct match
    if actor_lower in anim_lower:
        return True
    
    # Handle base actor names
    if actor_lower.endswith('_base'):
        base_name = actor_lower[:-5]  # Remove '_base'
        if base_name in anim_lower:
            return True
    
    # Handle common patterns
    actor_patterns = {
        'human': ['human', 'player', 'npc'],
        'goblin': ['goblin', 'gob'],
        'rat': ['rat', 'wrat'],
        'spider': ['spider'],
        'troll': ['troll'],
        'dog': ['dog'],
        'chicken': ['chicken'],
        'undead': ['undead', 'mummy', 'liche'],
        'dragon': ['dragon'],
        'golem': ['golem'],
        'demon': ['demon'],
        'snake_woman': ['snake'],
    }
    
    # Check if this actor has known patterns
    for pattern_actor, patterns in actor_patterns.items():
        if pattern_actor in actor_lower:
            for pattern in patterns:
                if pattern in anim_lower:
                    return True
    
    # Check individual word matches
    actor_words = actor_lower.split('_')
    for word in actor_words:
        if len(word) > 3 and word in anim_lower:  # Only match meaningful words
            return True
    
    return False

def analyze_base_actors(actors):
    """
    Analyze which actors are 'base' actors with the most animations.
    """
    print(f"\n=== BASE ACTOR ANALYSIS ===")
    
    # Find actors with 'base' in their path or name
    base_actors = {}
    variant_actors = {}
    
    for name, actor in actors.items():
        if 'base' in name.lower() or 'base' in actor.base_path.lower():
            base_actors[name] = actor
        else:
            variant_actors[name] = actor
    
    print(f"Found {len(base_actors)} base actors:")
    base_by_anim_count = sorted(base_actors.items(), key=lambda x: len(x[1].animations), reverse=True)
    
    for actor_name, actor in base_by_anim_count:
        anim_count = len(actor.animations)
        if anim_count > 0:
            print(f"  ✓ {actor_name}: {anim_count} animations")
            
            # Show animation types
            layer_counts = {}
            for anim_data in actor.animations.values():
                layer = anim_data['layer']
                layer_counts[layer] = layer_counts.get(layer, 0) + 1
            
            print(f"    Layer distribution: {layer_counts}")
        else:
            print(f"  - {actor_name}: 0 animations")
    
    print(f"\nVariant actors: {len(variant_actors)}")
    
    # Show most animated actors overall
    print(f"\n=== TOP ANIMATED ACTORS ===")
    all_by_anim_count = sorted(actors.items(), key=lambda x: len(x[1].animations), reverse=True)
    
    for actor_name, actor in all_by_anim_count[:10]:
        anim_count = len(actor.animations)
        if anim_count > 0:
            print(f"  {actor_name}: {anim_count} animations")

def main():
    if len(sys.argv) > 1:
        arx_root_path = sys.argv[1]
    else:
        arx_root_path = "/home/burner/.steam/debian-installation/steamapps/common/Arx Fatalis"
    
    print(f"Using Arx root path: {arx_root_path}")
    
    if not os.path.exists(arx_root_path):
        print(f"ERROR: Arx root path does not exist: {arx_root_path}")
        return
    
    try:
        actors, unmatched = discover_arx_actors(arx_root_path)
        
        if actors:
            analyze_actors(actors)
            analyze_base_actors(actors)
            save_results(actors, unmatched, "full_arx_discovery.json")
            
            print(f"\n=== SUMMARY ===")
            print(f"Total actors discovered: {len(actors)}")
            print(f"Total animations matched: {sum(len(actor.animations) for actor in actors.values())}")
            print(f"Total unmatched files: {len(unmatched)}")
            
        else:
            print("No actors discovered.")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
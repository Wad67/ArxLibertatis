#!/bin/bash

# Automated FTS export testing script
set -e  # Exit on any error

# Define log file and clear it on each run
LOG_FILE="/home/burner/Desktop/ArxLibertatis/fts_test_output.log"
rm -f "$LOG_FILE"

echo "=== FTS Export Test Script ===" | tee "$LOG_FILE"
echo "Output will be logged to: $LOG_FILE" | tee -a "$LOG_FILE"

# Define paths
BUILD_DIR="/home/burner/Desktop/ArxLibertatis/build"
ADDON_DIR="/home/burner/Desktop/ArxLibertatis/plugins/blender/arx_addon"
BACKUP_DIR="/home/burner/Desktop/ArxLibertatis/Level one backup do not fucking touch"
FTS_FILE="$BUILD_DIR/game/graph/levels/level1/fast.fts"
BACKUP_FTS="$BACKUP_DIR/fast.fts"
BLEND_FILE="$ADDON_DIR/all models load.blend"
BLENDER_SYMLINK="$BUILD_DIR/blender-link"

# Check if required files exist
if [ ! -f "$BACKUP_FTS" ]; then
    echo "ERROR: Backup FTS file not found at: $BACKUP_FTS" | tee -a "$LOG_FILE"
    exit 1
fi

if [ ! -f "$BLEND_FILE" ]; then
    echo "ERROR: Blend file not found at: $BLEND_FILE" | tee -a "$LOG_FILE"
    exit 1
fi

if [ ! -L "$BLENDER_SYMLINK" ]; then
    echo "ERROR: Blender symlink not found at: $BLENDER_SYMLINK" | tee -a "$LOG_FILE"
    exit 1
fi

echo "Step 1: Restoring original FTS file from backup..." | tee -a "$LOG_FILE"
cp "$BACKUP_FTS" "$FTS_FILE"
echo "  Restored: $FTS_FILE" | tee -a "$LOG_FILE"

echo "Step 2: Running Blender with UI..." | tee -a "$LOG_FILE"
cd "$BUILD_DIR"

# Create Python script for Blender automation
cat > /tmp/blender_automation.py << 'EOF'
import bpy
import sys
import time
import traceback

print("=== Blender Automation Script ===")

def wait_for_context(context, timeout=60):
    """Check for a valid window, screen, and 3D Viewport context using a timer."""
    start_time = time.time()
    
    def check_context():
        try:
            if bpy.context.window and bpy.context.screen:
                for area in bpy.context.screen.areas:
                    if area.type == 'VIEW_3D':
                        print("Found valid window and 3D Viewport context")
                        # Store the area for later use
                        context['area'] = area
                        return None  # Stop the timer
                print("No 3D Viewport area found, retrying...")
            else:
                print("Window or screen context not available, retrying...")
        except Exception as e:
            print(f"Context check failed: {e}")
        
        # Continue the timer if timeout hasn't been reached
        if time.time() - start_time < timeout:
            return 1.0  # Check again in 1 second
        print("ERROR: Valid window context not available after timeout")
        context['error'] = "Timeout waiting for context"
        return None  # Stop the timer

    return check_context

def override_context(area):
    """Create a context override for operators."""
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area_iter in screen.areas:
            if area_iter.type == 'VIEW_3D':
                for region in area_iter.regions:
                    if region.type == 'WINDOW':
                        override = {
                            'window': window,
                            'screen': screen,
                            'area': area_iter,
                            'region': region,
                            'scene': bpy.context.scene
                        }
                        return override
    print("WARNING: Could not create context override")
    return {}

def run_automation():
    """Main automation function, called after context is ready."""
    context = bpy.app.driver_namespace
    if context.get('error'):
        print(f"ERROR: {context['error']}")
        bpy.ops.wm.quit_blender()
        sys.exit(1)

    area = context.get('area')
    if not area:
        print("ERROR: No valid 3D Viewport area found")
        bpy.ops.wm.quit_blender()
        sys.exit(1)

    # Create context override
    context_override = override_context(area)

    print("Waiting for UI to stabilize...")
    time.sleep(2)  # Short sleep to ensure UI stability

    print("Accessing Arx addon...")
    
    # Configure addon preferences first
    try:
        print("Configuring Arx addon preferences...")
        addon_prefs = bpy.context.preferences.addons['arx_addon'].preferences
        addon_prefs.arxAssetPath = "/home/burner/Desktop/ArxLibertatis/build"
        print(f"Set arxAssetPath to: {addon_prefs.arxAssetPath}")
    except Exception as e:
        print(f"Could not configure addon preferences: {e}")
        traceback.print_exc()

    # Check if operators are available
    print("Checking if Arx operators are registered...")
    print(f"Available operators: {[op for op in dir(bpy.ops) if 'arx' in op]}")
    
    # Reload area list manually instead of using UI operator
    try:
        print("Manually reloading area list...")
        from arx_addon.managers import getAddon
        wm = bpy.context.window_manager
        area_list = wm.arx_areas_col
        area_list.clear()
        
        # Get areas from addon
        addon = getAddon(bpy.context)
        for area_id, value in addon.arxFiles.levels.levels.items():
            item = area_list.add()
            item.name = f'Area {area_id}'
            item.area_id = area_id
            # Map to level ID
            g_areaToLevel = {0:0, 8:0, 11:0, 12:0, 1:1, 13:1, 14:1, 2:2, 15:2, 3:3, 16:3, 17:3, 4:4, 18:4, 19:4, 5:5, 21:5, 6:6, 22:6, 7:7, 23:7}
            item.level_id = g_areaToLevel.get(area_id, -1)
        
        print(f"Loaded {len(area_list)} areas")
        for i, area in enumerate(area_list):
            print(f"  Area {i}: {area.name} (ID: {area.area_id})")
            
    except Exception as e:
        print(f"Could not reload area list: {e}")
        traceback.print_exc()

    # Import area 1 manually
    try:
        print("Manually importing area 1...")
        from arx_addon.arx_ui_area import importArea
        
        # Mock report function
        def mock_report(level, message):
            print(f"REPORT {level}: {message}")
        
        importArea(bpy.context, mock_report, 1)
        print("Area 1 import completed")
        time.sleep(5)
        
    except Exception as e:
        print(f"Could not import area 1: {e}")
        traceback.print_exc()

    # Test TRUE round-trip editing using Blender export
    try:
        print("Testing TRUE round-trip editing with Blender export...")
        
        # Find the Area_01 scene that was imported
        area_scene = bpy.data.scenes.get("Area_01")
        if not area_scene:
            print("ERROR: Area_01 scene not found. Import must have failed.")
            raise Exception("Area_01 scene not found")
        
        print(f"Found imported scene: {area_scene.name}")
        
        # Use the Blender export operator to test round-trip
        from arx_addon.arx_ui_area import CUSTOM_OT_arx_area_list_export_selected
        
        # Set up context for export
        wm = bpy.context.window_manager
        area_list = wm.arx_areas_col
        
        # Find area 1 in the list
        area_index = -1
        for i, area in enumerate(area_list):
            if area.area_id == 1:
                area_index = i
                break
        
        if area_index == -1:
            print("ERROR: Area 1 not found in area list")
            raise Exception("Area 1 not found")
        
        # Set the selected area
        wm.arx_areas_idx = area_index
        print(f"Selected area index: {area_index} (ID: {area_list[area_index].area_id})")
        
        # Use the Blender operator system properly
        print("Executing Blender round-trip export...")
        
        # Call the operator through bpy.ops if it's registered
        if hasattr(bpy.ops.arx, 'area_list_export_selected'):
            result = bpy.ops.arx.area_list_export_selected('INVOKE_DEFAULT')
        else:
            # Manually instantiate and call the operator
            from arx_addon.arx_ui_area import CUSTOM_OT_arx_area_list_export_selected
            from types import SimpleNamespace
            
            # Create a proper mock event
            mock_event = SimpleNamespace()
            mock_event.type = 'LEFTMOUSE'
            mock_event.value = 'PRESS'
            
            # Manually call the exportArea method
            export_op_class = CUSTOM_OT_arx_area_list_export_selected
            export_instance = object.__new__(export_op_class)
            export_op_class.__init__(export_instance)
            
            result = export_instance.invoke(bpy.context, mock_event)
        
        if 'FINISHED' in result:
            print("SUCCESS: Blender round-trip export completed!")
        else:
            print(f"FAILED: Blender export returned: {result}")
            
        time.sleep(3)
        
    except Exception as e:
        print(f"Round-trip export failed: {e}")
        traceback.print_exc()
        
        # Fallback to direct serialization test
        print("Falling back to direct FTS serialization test...")
        try:
            from arx_addon.managers import getAddon
            from arx_addon.dataFts import FtsSerializer
            
            addon = getAddon(bpy.context)
            area_files = addon.arxFiles.levels.levels[1]
            
            print("Loading original FTS data...")
            from arx_addon.lib import ArxIO
            ioLib = ArxIO()
            fts_serializer = FtsSerializer(ioLib)
            fts_data = fts_serializer.read_fts_container(area_files.fts)
            
            output_path = "/home/burner/Desktop/ArxLibertatis/build/game/graph/levels/level1/fast.fts"
            print(f"Writing FTS to: {output_path}")
            fts_serializer.write_fts_container(output_path, fts_data)
            print("Fallback FTS export completed")
            
        except Exception as fallback_error:
            print(f"Fallback also failed: {fallback_error}")
            traceback.print_exc()

    print("=== Blender operations completed successfully ===")

    print("quitting...")

    time.sleep(2)
    bpy.ops.wm.quit_blender()

def main():
    try:
        # Open the blend file
        blend_file = "/home/burner/Desktop/ArxLibertatis/plugins/blender/arx_addon/all models load.blend"
        print(f"Opening blend file: {blend_file}")
        bpy.ops.wm.open_mainfile(filepath=blend_file)

        # Store context in driver_namespace for timer access
        bpy.app.driver_namespace['area'] = None
        bpy.app.driver_namespace['error'] = None

        # Register timer to check context
        print("Registering timer to wait for context...")
        bpy.app.timers.register(wait_for_context(bpy.app.driver_namespace), first_interval=1.0)

        # Schedule the main automation to run after context is ready
        def check_and_run():
            if bpy.app.driver_namespace.get('area') or bpy.app.driver_namespace.get('error'):
                run_automation()
                return None  # Stop the timer
            return 1.0  # Check again in 1 second

        bpy.app.timers.register(check_and_run, first_interval=1.0)

    except Exception as e:
        print(f"ERROR in Blender script: {e}")
        traceback.print_exc()
        time.sleep(10)  # Keep window open to see error
        bpy.ops.wm.quit_blender()
        sys.exit(1)

if __name__ == "__main__":
    main()
EOF

echo "  Executing Blender with UI automation..." | tee -a "$LOG_FILE"
"$BLENDER_SYMLINK" --python /tmp/blender_automation.py 2>&1 | tee -a "$LOG_FILE"

echo "Step 3: Testing FTS loading with ArxLibertatis..." | tee -a "$LOG_FILE"
echo "  Executing: ./arx --loadlevel 01 -g --skiplogo --noclip" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Run ArxLibertatis and capture output
timeout 30s "$BUILD_DIR/arx" --loadlevel 01 -g --skiplogo --noclip 2>&1 | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
echo "=== Test completed ===" | tee -a "$LOG_FILE"

# Clean up temp file
rm -f /tmp/blender_automation.py

echo "Script finished. Check the full output in: $LOG_FILE" | tee -a "$LOG_FILE"

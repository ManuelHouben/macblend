# -*- coding: utf-8 -*-
# <pep8 compliant>

import sys
print(f"DEBUG: Module name is: {__name__}")
print(f"DEBUG: Module file is: {__file__}")

# --- Imports ---
import bpy
from bpy_extras import object_utils
import math
import traceback
import sys
import json
import os
import mathutils
import subprocess
import importlib
from bpy_extras.io_utils import ExportHelper

from . import core

# Import property types directly for Blender 4.x compatibility
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    FloatVectorProperty,
    PointerProperty,
    EnumProperty
)

# --- Constants ---
MACBETH_PATCH_NAMES = ["dark skin", "light skin", "blue sky", "foliage", "blue flower", "bluish green", "orange", "purplish blue", "moderate red", "purple", "yellow green", "orange yellow", "blue", "green", "red", "yellow", "magenta", "cyan", "white 9.5", "neutral 8", "neutral 6.5", "neutral 5", "neutral 3.5", "black 2"]
NEUTRAL_5_INDEX = 21

def srgb_eotf_inverse(c):
    """Applies the inverse sRGB EOTF to linearize."""
    if c <= 0.040449936:
        return c / 12.92
    else:
        return ((c + 0.055) / 1.055) ** 2.4

def linearize_color(rgb_tuple):
    """Applies inverse sRGB EOTF to an entire (R, G, B) tuple."""
    return (
        srgb_eotf_inverse(rgb_tuple[0]),
        srgb_eotf_inverse(rgb_tuple[1]),
        srgb_eotf_inverse(rgb_tuple[2])
    )

def load_json_data(context):
    """Loads colorspace transform data from JSON specified in preferences, or defaults to bundled file."""
    prefs = context.preferences.addons[__package__].preferences
    if hasattr(prefs, 'get_effective_json_path'):
        json_path = prefs.get_effective_json_path()
    else:
        json_path = getattr(prefs, 'json_file_path', None)
    if not json_path or not os.path.exists(json_path):
        print(f"JSON Error: Path not set or file not found: '{json_path}'")
        return None
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        print(f"Successfully loaded JSON data from: '{json_path}'")
        required_keys = ["sRGB_to_XYZ_matrix", "XYZ_to_RGB_matrices", "whitepoints", "CAT_matrices"]
        if not all(key in data for key in required_keys):
            print("JSON Warning: File is missing one or more required keys:", required_keys)
        return data
    except Exception as e:
        print(f"Error loading JSON '{json_path}': {e}")
        return None

def get_projected_coords(context, camera, obj):
    """Projects a 3D point to normalized 2D camera coordinates."""
    if not context or not camera or not obj or not obj.matrix_world or not camera.data:
        return None
    try:
        co_ndc = object_utils.world_to_camera_view(context.scene, camera, obj.matrix_world.translation)
        return co_ndc
    except Exception as e:
        print(f"Error in world_to_camera_view for '{obj.name}': {e}")
        return None

def get_pixel_coords(norm_coords, image_width, image_height):
    """Converts normalized 2D camera coordinates to pixel coordinates."""
    if norm_coords is None or not hasattr(norm_coords, 'x') or not hasattr(norm_coords, 'y'):
        return None
    try:
        if image_width <= 0 or image_height <= 0:
            return None
        px = norm_coords.x * image_width
        # The console output shows a perfect vertical flip. The only place a Y-flip
        # occurs is here. Based on the sampling results, we should not be flipping
        # the Y-coordinate.
        py = norm_coords.y * image_height
        px_clamped = max(0, min(image_width - 1, px))
        py_clamped = max(0, min(image_height - 1, py))
        return int(round(px_clamped)), int(round(py_clamped))
    except Exception as e:
        print(f"Error converting NDC to pixel coordinates: {e}")
        return None

def load_and_get_nodegroup(group_name="ColorMatrix"):
    """
    Appends a node group from the bundled 'colormatrix.blend' file if it doesn't already exist.
    """
    # If the group already exists in the current file, just return it.
    if group_name in bpy.data.node_groups:
        print(f"Node group '{group_name}' already exists.")
        return bpy.data.node_groups[group_name]

    # Construct the path to the bundled .blend file
    addon_dir = os.path.dirname(os.path.abspath(__file__))
    blend_file_path = os.path.join(addon_dir, "colormatrix.blend")

    if not os.path.exists(blend_file_path):
        print(f"ERROR: Bundled file 'colormatrix.blend' not found at '{blend_file_path}'")
        return None

    # Append the node group from the .blend file.
    try:
        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
            if group_name in data_from.node_groups:
                data_to.node_groups = [group_name]
            else:
                print(f"ERROR: Node group '{group_name}' not found inside '{blend_file_path}'")
                return None
    except Exception as e:
        print(f"ERROR: Failed to load library from '{blend_file_path}': {e}")
        return None

    # The appended group should now be in bpy.data.node_groups
    appended_group = bpy.data.node_groups.get(group_name)
    if appended_group:
        print(f"Successfully appended node group '{group_name}'.")
    else:
        print(f"ERROR: Failed to append node group '{group_name}' for an unknown reason.")

    return appended_group

# --- UI and Logic Functions ---
def update_marker_geometry(scene):
    """
    Updates the geometry of the shared marker curve based on the 'sample_size'
    percentage and the current dimensions and rotation of the control rig.
    """
    if not scene or not hasattr(scene, 'macbeth_calibrator_settings'):
        return

    settings = scene.macbeth_calibrator_settings
    
    marker_curve = bpy.data.curves.get("MB_Sample_Marker_Curve")
    if not marker_curve or not marker_curve.splines:
        return

    corner_tl = settings.corner_tl
    corner_tr = settings.corner_tr
    corner_bl = settings.corner_bl
    corner_br = settings.corner_br
    if not all((corner_tl, corner_tr, corner_bl, corner_br)):
        return

    p_tl = corner_tl.matrix_world.translation
    p_tr = corner_tr.matrix_world.translation
    p_bl = corner_bl.matrix_world.translation
    p_br = corner_br.matrix_world.translation

    # Calculate edge vectors and average lengths
    top_vec = p_tr - p_tl
    left_vec = p_bl - p_tl
    
    avg_width = (top_vec.length + (p_br - p_bl).length) / 2.0
    avg_height = (left_vec.length + (p_br - p_tr).length) / 2.0

    cell_width = avg_width / 6.0
    cell_height = avg_height / 4.0
    
    max_radius = 0.5 * min(cell_width, cell_height)
    half_side = max_radius * (settings.sample_size / 100.0)

    # Construct a rotation matrix from the rig's edge vectors
    x_axis = top_vec.normalized()
    y_axis = left_vec.normalized()
    z_axis = x_axis.cross(y_axis).normalized()
    # Create a new y_axis perpendicular to x and z for a clean orthonormal matrix
    y_axis_perp = z_axis.cross(x_axis).normalized()
    
    # Final rotation matrix for the rig
    rot_matrix = mathutils.Matrix((x_axis, y_axis_perp, z_axis)).transposed()

    # Define vertices for an axis-aligned square
    points_co_local = [
        mathutils.Vector((-half_side, -half_side, 0)),
        mathutils.Vector(( half_side, -half_side, 0)),
        mathutils.Vector(( half_side,  half_side, 0)),
        mathutils.Vector((-half_side,  half_side, 0)),
    ]
    
    # Rotate the local square vertices by the rig's rotation matrix
    points_co_rotated = [rot_matrix @ p for p in points_co_local]
    
    spline = marker_curve.splines[0]
    
    # Set the coordinates and handle types for each point to form a rotated square
    for i, p in enumerate(spline.bezier_points):
        p.co = points_co_rotated[i]
        p.handle_left = points_co_rotated[i]
        p.handle_right = points_co_rotated[i]
        p.handle_left_type = 'VECTOR'
        p.handle_right_type = 'VECTOR'

def update_marker_positions(scene):
    """
    Calculates and sets the positions of the 24 sample markers based on the
    locations of the four corner controller objects using bilinear interpolation.
    """
    if not scene or not hasattr(scene, 'macbeth_calibrator_settings'):
        return

    settings = scene.macbeth_calibrator_settings
    
    # Retrieve the four corner controller objects from the settings
    corner_tl = settings.corner_tl
    corner_tr = settings.corner_tr
    corner_bl = settings.corner_bl
    corner_br = settings.corner_br
    
    # Exit if any of the corner controllers are not assigned
    if not all((corner_tl, corner_tr, corner_bl, corner_br)):
        return

    # Find the collection containing the markers
    marker_collection = bpy.data.collections.get(settings.marker_collection_name)
    if not marker_collection:
        return

    # Get the sample markers and sort them numerically to ensure correct order.
    markers = [obj for obj in marker_collection.objects if obj.name.startswith("MB_Sample_")]
    if len(markers) != 24:
        return
    try:
        markers.sort(key=lambda obj: int(obj.name.split('_')[2]))
    except (IndexError, ValueError):
        # This can happen if the rig is cleared and this function runs before it's fully rebuilt.
        return


    # Get the world-space locations of the corner controllers
    p_tl = corner_tl.matrix_world.translation
    p_tr = corner_tr.matrix_world.translation
    p_bl = corner_bl.matrix_world.translation
    p_br = corner_br.matrix_world.translation

    num_cols = 6
    num_rows = 4
    patch_index = 0

    # Iterate through each row and column of the grid.
    # The corner controllers are expected to be on the outer corners of the chart.
    # The interpolation is adjusted to find the center of each patch.
    for r in range(num_rows):
        # Calculate v to find the vertical center of the current row's area.
        v = (r + 0.5) / num_rows
        
        # Interpolate the left and right edges of the current row.
        p_left = p_tl.lerp(p_bl, v)
        p_right = p_tr.lerp(p_br, v)

        for c in range(num_cols):
            # Calculate u to find the horizontal center of the current column's area.
            u = (c + 0.5) / num_cols
            
            # Interpolate across the row to find the marker's final position at the patch center.
            pos = p_left.lerp(p_right, u)

            if patch_index < len(markers):
                # Use a non-blocking check to avoid infinite loops with the handler
                if (markers[patch_index].location - pos).length > 1e-6:
                    markers[patch_index].location = pos
            
            patch_index += 1

# This flag is used to prevent the handler from running recursively
_handler_is_running = False

def macbeth_depsgraph_handler(scene, depsgraph):
    """
    An application handler that runs after the dependency graph is updated.
    It checks if one of the control corners was moved and, if so,
    triggers an update of the sample marker positions.
    """
    global _handler_is_running
    if _handler_is_running:
        return

    if not hasattr(scene, 'macbeth_calibrator_settings'):
        return
        
    settings = scene.macbeth_calibrator_settings
    controllers = [settings.corner_tl, settings.corner_tr, settings.corner_bl, settings.corner_br]
    
    # Don't run if the rig is not fully set up
    if not all(controllers):
        return

    controller_names = {c.name for c in controllers}
    
    # Check if any of the updated objects are one of our controllers
    needs_update = False
    for update in depsgraph.updates:
        if update.id.name in controller_names and update.is_updated_transform:
            needs_update = True
            break
    
    if needs_update:
        # Set the flag to prevent recursion and run the update
        _handler_is_running = True
        try:
            update_marker_positions(scene)
            update_marker_geometry(scene)
        finally:
            _handler_is_running = False

# --- Enum Callback ---
_enum_cache = None
_enum_cache_path = None

def get_target_colorspace_items(self, context):
    """Dynamically populates the target colorspace EnumProperty."""
    global _enum_cache, _enum_cache_path
    items = [("LINEAR_SRGB_D65", "Linear sRGB D65 (Internal)", "Use the internal Linear sRGB D65 reference values")]

    if context is None:
        return items

    json_path = None
    try:
        prefs_addon = context.preferences.addons.get(__package__)
        if prefs_addon:
            addon_prefs = prefs_addon.preferences
            if addon_prefs:
                if hasattr(addon_prefs, 'get_effective_json_path'):
                    json_path = addon_prefs.get_effective_json_path()
                else:
                    json_path = getattr(addon_prefs, 'json_file_path', None)

        if _enum_cache and _enum_cache_path == json_path:
            return _enum_cache

        if not json_path or not os.path.exists(json_path):
            _enum_cache = items
            _enum_cache_path = json_path
            return items

        with open(json_path, 'r') as f:
            json_data = json.load(f)

        if "XYZ_to_RGB_matrices" in json_data:
            sorted_keys = sorted(json_data["XYZ_to_RGB_matrices"].keys())
            for key in sorted_keys:
                items.append((key, key, f"Target {key} colorspace from JSON"))

        _enum_cache = items
        _enum_cache_path = json_path
        return items

    except Exception as e:
        print(f"ERROR (Enum Callback): {e}")
        traceback.print_exc()
        return items

# --- Classes ---
class MacbethCalibratorPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    
    json_file_path: StringProperty(
        name="Colorspace JSON File",
        description="Path to the JSON file containing colorspace transform data. If left empty, the default bundled file will be used.",
        subtype='FILE_PATH',
        default=""
    )

    def get_effective_json_path(self):
        user_path = self.json_file_path
        if user_path and os.path.exists(user_path):
            return user_path
        addon_dir = os.path.dirname(os.path.abspath(__file__))
        bundled_path = os.path.join(addon_dir, "mmColorTarget_colorspace_transforms.json")
        if os.path.exists(bundled_path):
            return bundled_path
        return None

    def draw(self, context):
        layout = self.layout
        layout.label(text="Specify the path to the colorspace transforms JSON file.")
        layout.label(text="If left blank, a bundled default file will be used.")
        layout.prop(self, "json_file_path")

        effective_path = self.get_effective_json_path()
        if effective_path:
            box = layout.box()
            box.label(text=f"Effective Path: {effective_path}", icon='INFO')
        else:
            box = layout.box()
            box.label(text="Warning: No valid JSON file found.", icon='ERROR')

class MacbethCalibratorSettings(bpy.types.PropertyGroup):
    cam: PointerProperty(
        name="Camera",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'CAMERA'
    )
    image: PointerProperty(
        name="Input Image",
        type=bpy.types.Image
    )
    sample_size: FloatProperty(
        name="Marker Size",
        description="Size of the sample markers as a percentage of the available space for each patch",
        subtype='PERCENTAGE',
        default=50.0,
        min=1.0,
        max=100.0,
        update=lambda self, context: update_marker_geometry(context.scene)
    )
    chroma_only: BoolProperty(
        name="Normalize Luminance",
        description="Adjust source samples to match TARGET grey luminance before matrix calculation",
        default=True
    )
    target_colorspace: EnumProperty(
        name="Target Colorspace",
        description="Select the target colorspace reference values",
        items=get_target_colorspace_items,
    )
    calculated_matrix: FloatVectorProperty(
        name="Calculated Matrix (Raw)",
        description="Internal storage of the calculated 3x3 matrix (row-major)",
        size=9,
        subtype='MATRIX',
        default=[1,0,0, 0,1,0, 0,0,1]
    )
    calculation_done: BoolProperty(
        name="Calculation Done Flag",
        description="Indicates if a matrix has been successfully calculated",
        default=False
    )
    matrix_display_string: StringProperty(
        name="Formatted Matrix",
        description="User-friendly display of the calculated matrix",
        default="Matrix not calculated."
    )
    node_name: StringProperty(
        name="Node Name",
        description="Name for the Color Balance node in the compositor",
        default="MacbethCalibration"
    )
    marker_collection_name: StringProperty(
        name="Rig Collection",
        description="Name of the collection holding the sample markers and controllers",
        default="Macbeth Control Rig"
    )
    # --- Corner Controllers for the Rig ---
    corner_tl: PointerProperty(
        name="Top-Left Corner",
        type=bpy.types.Object
    )
    corner_tr: PointerProperty(
        name="Top-Right Corner",
        type=bpy.types.Object
    )
    corner_bl: PointerProperty(
        name="Bottom-Left Corner",
        type=bpy.types.Object
    )
    corner_br: PointerProperty(
        name="Bottom-Right Corner",
        type=bpy.types.Object
    )

# --- Operators ---
class MB_OT_SetupSampleMarkers(bpy.types.Operator):
    """Creates or replaces a controllable grid of 24 markers and 4 corner empties"""
    bl_idname = "mbcalib.setup_sample_markers"
    bl_label = "Setup Control Rig"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: StringProperty(name="Rig Collection Name", default="Macbeth Control Rig")
    controller_size: FloatProperty(name="Controller Size", default=0.1, min=0.01)

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        scene = context.scene
        view_layer = context.view_layer
        settings = scene.macbeth_calibrator_settings
        
        base_name = "Macbeth Control Rig"
        image_name_part = ""
        if settings.image and settings.image.name:
            image_name_part = f" ({settings.image.name})"
        
        final_collection_name = f"{base_name}{image_name_part}"
        settings.marker_collection_name = final_collection_name

        rig_collection = bpy.data.collections.get(final_collection_name)
        if not rig_collection:
            rig_collection = bpy.data.collections.new(final_collection_name)
            scene.collection.children.link(rig_collection)
            print(f"Created collection: '{final_collection_name}'")
        else:
            print(f"Found existing collection: '{final_collection_name}'")
            objects_to_delete = [obj for obj in rig_collection.objects]
            for obj in objects_to_delete:
                    bpy.data.objects.remove(obj, do_unlink=True)
            print(f"Cleared {len(objects_to_delete)} objects from rig collection.")

        # Cleanup old data-blocks to prevent file bloat
        for old_data in [bpy.data.meshes.get("MB_Sample_Marker_Mesh"), bpy.data.curves.get("MB_Sample_Marker_Curve")]:
            if old_data:
                try:
                    bpy.data.curves.remove(old_data)
                except TypeError: # It might be a mesh
                    try:
                        bpy.data.meshes.remove(old_data)
                    except:
                        pass # Fails if users exist, which is fine.

        original_active = view_layer.objects.active
        original_selected = context.selected_objects[:]
        bpy.ops.object.select_all(action='DESELECT')

        try:
            cursor_loc = scene.cursor.location
            
            # --- Create Corner Controllers ---
            width, height = 1.2, 0.8
            corner_locations = {
                "TL": cursor_loc + mathutils.Vector((-width/2, height/2, 0)),
                "TR": cursor_loc + mathutils.Vector((width/2, height/2, 0)),
                "BL": cursor_loc + mathutils.Vector((-width/2, -height/2, 0)),
                "BR": cursor_loc + mathutils.Vector((width/2, -height/2, 0)),
            }

            def create_empty(name, location, size, collection):
                obj = bpy.data.objects.new(name, None)
                obj.location = location
                obj.empty_display_size = size
                obj.empty_display_type = 'SPHERE'
                collection.objects.link(obj)
                return obj

            settings.corner_tl = create_empty("MB_Corner_TL", corner_locations["TL"], self.controller_size, rig_collection)
            settings.corner_tr = create_empty("MB_Corner_TR", corner_locations["TR"], self.controller_size, rig_collection)
            settings.corner_bl = create_empty("MB_Corner_BL", corner_locations["BL"], self.controller_size, rig_collection)
            settings.corner_br = create_empty("MB_Corner_BR", corner_locations["BR"], self.controller_size, rig_collection)
            print("Created 4 corner controllers.")
            
            # FORCE an update of the dependency graph so the new objects have their matrices.
            context.view_layer.update()
            print("Forced depsgraph update after creating controllers.")

            # --- Create Sample Markers using CURVE objects ---
            marker_curve = bpy.data.curves.new("MB_Sample_Marker_Curve", type='CURVE')
            marker_curve.dimensions = '2D'
            spline = marker_curve.splines.new('BEZIER')
            spline.bezier_points.add(3) # A new bezier spline has 1 point, add 3 more for a total of 4
            spline.use_cyclic_u = True


            for i in range(24):
                patch_name = MACBETH_PATCH_NAMES[i]
                obj_name_suffix = patch_name.replace(" ", "_").replace(".", "").replace("(", "").replace(")", "")
                marker_obj_name = f"MB_Sample_{i + 1:02d}_{obj_name_suffix}"
                
                marker_obj = bpy.data.objects.new(marker_obj_name, marker_curve)
                marker_obj.show_name = False
                rig_collection.objects.link(marker_obj)
            print("Created 24 sample markers (curve objects).")

            # Run the update function to set initial positions and geometry
            update_marker_positions(scene)
            update_marker_geometry(scene)

        finally:
            # Restore original selection and active object
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selected:
                if obj and obj.name in view_layer.objects:
                    obj.select_set(True)
            if original_active and original_active.name in view_layer.objects:
                view_layer.objects.active = original_active

        self.report({'INFO'}, f"Created control rig in collection '{final_collection_name}'.")
        return {'FINISHED'}

class MB_OT_SetBackground(bpy.types.Operator):
    """Sets the selected image as the background for the selected camera"""
    bl_idname = "mbcalib.set_background"
    bl_label = "Set Camera Background"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not context or not context.scene or not hasattr(context.scene, 'macbeth_calibrator_settings'):
            return False
        settings = context.scene.macbeth_calibrator_settings
        if settings is None:
            return False
        if not hasattr(settings, "cam") or settings.cam is None:
            return False
        if not hasattr(settings, "image") or settings.image is None:
            return False
        return True

    def execute(self, context):
        settings = context.scene.macbeth_calibrator_settings
        cam = settings.cam
        img = settings.image
        if not cam or cam.type != 'CAMERA':
            self.report({'ERROR'}, "No valid Camera selected.")
            return {'CANCELLED'}
        if not img:
            self.report({'ERROR'}, "No Input Image selected.")
            return {'CANCELLED'}
        try:
            cam_data = cam.data
            
            if hasattr(cam_data, 'show_background_images'):
                cam_data.show_background_images = True
            else:
                self.report({'WARNING'}, "Camera data missing 'show_background_images'.")

            if not hasattr(cam_data, 'background_images'):
                self.report({'ERROR'}, "Camera data missing 'background_images'.")
                return {'CANCELLED'}

            # Clear all existing background images to ensure a clean slate
            cam_data.background_images.clear()
            print("Cleared all existing background images.")
            
            # Add the new background image
            if hasattr(cam_data.background_images, 'new'):
                bg_image_entry = cam_data.background_images.new()
                bg_image_entry.image = img
                print(f"Added new BG for '{img.name}'.")
            else:
                self.report({'ERROR'}, "Cannot add new BG entry.")
                return {'CANCELLED'}

            # Configure the new background image
            if bg_image_entry:
                bg_image_entry.alpha = 1.0
                if hasattr(bg_image_entry, 'display_depth'):
                    bg_image_entry.display_depth = 'BACK'
                else:
                    self.report({'WARNING'}, "BG entry missing 'display_depth'.")
                self.report({'INFO'}, f"Set '{img.name}' as the only background image for camera '{cam.name}'.")
            else:
                self.report({'ERROR'}, "Failed get/create BG entry.")
                return {'CANCELLED'}

        except AttributeError as ae:
            self.report({'ERROR'}, f"Camera data attribute error: {ae}.")
            traceback.print_exc()
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to set background image: {e}")
            traceback.print_exc()
            return {'CANCELLED'}
        return {'FINISHED'}

class MB_OT_CalculateMatrix(bpy.types.Operator):
    """Samples colors from the image using markers and calculates the calibration matrix"""
    bl_idname = "mbcalib.calculate_matrix"
    bl_label = "Calculate Color Matrix"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not context or not context.scene or not hasattr(context.scene, 'macbeth_calibrator_settings'):
            return False
        settings = context.scene.macbeth_calibrator_settings
        if settings is None or type(settings).__name__ == '_PropertyDeferred':
            return False
        cam_val = getattr(settings, "cam", None)
        if cam_val is None or type(cam_val).__name__ == '_PropertyDeferred':
            return False
        if cam_val.type != 'CAMERA':
            return False
        image_val = getattr(settings, "image", None)
        if image_val is None or type(image_val).__name__ == '_PropertyDeferred':
            return False
        has_valid_image = False
        try:
            if image_val.has_data:
                has_valid_image = True
        except:
            pass
        if not has_valid_image:
            return False
        if not hasattr(settings, "marker_collection_name"):
            return False
        collection_name = getattr(settings, "marker_collection_name", None)
        if collection_name is None or type(collection_name).__name__ == '_PropertyDeferred':
            return False
        marker_collection = bpy.data.collections.get(collection_name)
        if not marker_collection:
            return False
        
        # Only count the actual sample markers, not the controllers
        markers = [o for o in marker_collection.objects if o.name.startswith("MB_Sample_")]
        if len(markers) < 24:
            return False
        return True

    def execute(self, context):
        # This dictionary passes non-numpy-dependent helper functions and data
        # to the core module to avoid circular imports.
        helpers = {
            'bpy': bpy,
            'traceback': traceback,
            'load_json_data': load_json_data,
            'get_projected_coords': get_projected_coords,
            'get_pixel_coords': get_pixel_coords,
            'linearize_color': linearize_color,
            'MACBETH_PATCH_NAMES': MACBETH_PATCH_NAMES,
            'NEUTRAL_5_INDEX': NEUTRAL_5_INDEX
        }
        
        return core.run_calculation(context, self, helpers)

class MB_OT_ApplyToCompositor(bpy.types.Operator):
    """Applies the calculated matrix to a Color Balance node in the compositor"""
    bl_idname = "mbcalib.apply_to_compositor"
    bl_label = "Apply Matrix to Compositor"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return scene and scene.use_nodes and hasattr(scene, 'macbeth_calibrator_settings')

    def _create_or_update_matrix_node(self, context, tree, node_name, matrix, location, group_definition):
        """Helper to create or update a single ColorMatrix node group instance."""
        # Flatten matrix for node inputs
        matrix_values = [item for row in matrix for item in row]

        node = tree.nodes.get(node_name)
        if node and node.bl_idname != 'CompositorNodeGroup':
            tree.nodes.remove(node)
            node = None
        
        if not node:
            node = tree.nodes.new(type='CompositorNodeGroup')
            node.name = node_name
            node.label = node_name
            node.location = location
        
        node.node_tree = group_definition
        
        context.view_layer.update()
        
        try:
            if 'Output Red' in node.inputs:
                node.inputs['Output Red'].default_value = (matrix_values[0], matrix_values[3], matrix_values[6])
            if 'Output Green' in node.inputs:
                node.inputs['Output Green'].default_value = (matrix_values[1], matrix_values[4], matrix_values[7])
            if 'Output Blue' in node.inputs:
                node.inputs['Output Blue'].default_value = (matrix_values[2], matrix_values[5], matrix_values[8])
        except Exception as e:
            self.report({'ERROR'}, f"Failed to set matrix on '{node.name}': {e}")
            traceback.print_exc()


    def execute(self, context):
        settings = context.scene.macbeth_calibrator_settings
        scene = context.scene
        if not settings:
            self.report({'ERROR'}, "Addon settings not found.")
            return {'CANCELLED'}
        
        if not scene.use_nodes:
            scene.use_nodes = True
            self.report({'INFO'}, "Compositor Nodes enabled.")
        
        if not scene.node_tree:
            self.report({'ERROR'}, "Scene has no compositor node tree.")
            return {'CANCELLED'}

        # Get the base and inverse node names from settings
        forward_node_name = settings.node_name
        inverse_node_name = f"{forward_node_name}_Inverse"

        forward_matrix = mathutils.Matrix.Identity(3)
        inverse_matrix = mathutils.Matrix.Identity(3)

        if not settings.calculation_done:
            self.report({'WARNING'}, "Matrix not calculated. Applying identity matrices.")
        else:
            forward_matrix = settings.calculated_matrix.copy()
            inverse_matrix = forward_matrix.copy()
            try:
                inverse_matrix.invert()
            except ValueError:
                self.report({'WARNING'}, "Matrix is not invertible. Using identity for inverse.")
                inverse_matrix = mathutils.Matrix.Identity(3)

        tree = scene.node_tree
        
        color_matrix_group = load_and_get_nodegroup()
        if not color_matrix_group:
            self.report({'ERROR'}, "Failed to load 'ColorMatrix' node group. Check console.")
            return {'CANCELLED'}
        
        # Determine node locations
        render_layers = tree.nodes.get('Render Layers')
        if render_layers:
            base_location = (render_layers.location.x + 350, render_layers.location.y)
        else:
            base_location = (200, 400)
        
        inverse_location = (base_location[0], base_location[1] - 200)

        # Create/update the forward and inverse nodes
        self._create_or_update_matrix_node(context, tree, forward_node_name, forward_matrix, base_location, color_matrix_group)
        self._create_or_update_matrix_node(context, tree, inverse_node_name, inverse_matrix, inverse_location, color_matrix_group)

        self.report({'INFO'}, f"Set matrix for '{forward_node_name}' and '{inverse_node_name}'.")
        return {'FINISHED'}

class MB_OT_ExportCLF(bpy.types.Operator, ExportHelper):
    """Exports the calculated matrix to a Common LUT Format (.clf) file"""
    bl_idname = "mbcalib.export_clf"
    bl_label = "Export Matrix as CLF"
    bl_options = {'REGISTER'}

    filename_ext = ".clf"
    filter_glob: StringProperty(
        default="*.clf",
        options={'HIDDEN'},
        maxlen=255,
    )

    @classmethod
    def poll(cls, context):
        if not context or not context.scene or not hasattr(context.scene, 'macbeth_calibrator_settings'):
            return False
        settings = context.scene.macbeth_calibrator_settings
        return settings and settings.calculation_done

    def execute(self, context):
        settings = context.scene.macbeth_calibrator_settings
        
        # The FloatVectorProperty with subtype='MATRIX' returns a mathutils.Matrix object.
        # We must flatten this 3x3 matrix into a single list of 9 floats
        # for the f-string formatting to work correctly.
        matrix = settings.calculated_matrix
        m_flat = [value for row in matrix for value in row]
        
        process_id = settings.node_name if settings.node_name else "MacbethCalibratorExport"

        # The core logic assumes input is the scene-linear space, which in a default
        # Blender setup is Linear sRGB (with Rec.709 primaries). The CLF file
        # must accurately describe this transform.
        input_desc = "Linear Rec.709 (sRGB)"
        output_desc = settings.target_colorspace
        if output_desc == 'LINEAR_SRGB_D65':
             output_desc = "Linear Rec.709 (sRGB)"

        clf_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ProcessList id="{process_id}" compCLFversion="3.0">
    <Description>Color matrix calculated by Macbeth Calibrator 3D. Transforms from {input_desc} to {output_desc}.</Description>
    <InputDescriptor>{input_desc}</InputDescriptor>
    <OutputDescriptor>{output_desc}</OutputDescriptor>
    <Matrix inBitDepth="32f" outBitDepth="32f">
        <Array dim="3 3">
            {m_flat[0]:.9f} {m_flat[1]:.9f} {m_flat[2]:.9f}
            {m_flat[3]:.9f} {m_flat[4]:.9f} {m_flat[5]:.9f}
            {m_flat[6]:.9f} {m_flat[7]:.9f} {m_flat[8]:.9f}
        </Array>
    </Matrix>
</ProcessList>
"""
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                f.write(clf_content)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to write file: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Exported CLF matrix to {self.filepath}")
        return {'FINISHED'}

# --- UI Panel ---
class MB_PT_CalibratorPanel(bpy.types.Panel):
    """Creates the UI Panel in the 3D View Sidebar"""
    bl_label = "Macbeth Calibrator"
    bl_idname = "MB_PT_CalibratorPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Macbeth'

    def draw(self, context):
        layout = self.layout
        settings = None
        try:
            scene = context.scene
            if not hasattr(scene, 'macbeth_calibrator_settings'):
                layout.label(text="Error: Settings property missing.", icon='ERROR')
                return
            settings = scene.macbeth_calibrator_settings
            if settings is None:
                layout.label(text="Error: Settings property is None.", icon='ERROR')
                return
        except Exception as e:
            layout.label(text=f"Panel Draw Error: {e}", icon='ERROR')
            return

        layout.label(text="1. Input Setup:")
        box_input = layout.box()
        col_input = box_input.column()

        col_input.prop(settings, "cam", text="Camera")
        col_input.prop(settings, "image", text="Image")

        row_buttons = col_input.row(align=True)
        set_bg_layout = row_buttons.row(align=True)
        set_bg_layout.operator(MB_OT_SetBackground.bl_idname, text="Set BG")
        row_buttons.operator(MB_OT_SetupSampleMarkers.bl_idname, text="Setup Control Rig")
        col_input.prop(settings, "marker_collection_name", text="Rig Collection")

        layout.separator()
        layout.label(text="2. Calibration Settings:")
        box_settings = layout.box()
        col_settings = box_settings.column()
        col_settings.prop(settings, "target_colorspace", text="Target")
        col_settings.separator()
        col_settings.prop(settings, "sample_size")
        col_settings.prop(settings, "chroma_only")

        layout.separator()
        layout.label(text="3. Calculate & Apply:")
        box_calc = layout.box()
        col_calc = box_calc.column()
        col_calc.operator(MB_OT_CalculateMatrix.bl_idname, text="Calculate Matrix", icon='RENDER_ANIMATION')
        col_calc.separator()
        col_calc.label(text="Apply to Compositor Node:")
        row_apply = col_calc.row(align=True)
        row_apply.prop(settings, "node_name", text="")
        apply_op_layout = row_apply.row(align=True)
        apply_op_layout.active = getattr(context.scene, 'use_nodes', False)
        apply_op_layout.operator(MB_OT_ApplyToCompositor.bl_idname, text="Apply", icon='FORWARD')

        col_calc.separator()
        if settings.calculation_done:
            col_calc.label(text="Calculated Matrix:")
        else:
            col_calc.label(text="Matrix (Current/Not Calculated):")
        box_matrix_display = col_calc.box()
        col_matrix_lines = box_matrix_display.column(align=True)
        
        matrix_lines = settings.matrix_display_string.split('\n')
        for line in matrix_lines:
            row_mat_line = col_matrix_lines.row()
            row_mat_line.label(text=line)
        
        export_op_layout = col_matrix_lines.row(align=True)
        export_op_layout.active = settings.calculation_done
        export_op_layout.operator(MB_OT_ExportCLF.bl_idname, text="Export .clf", icon='EXPORT')

# --- Registration ---
classes = (
    MacbethCalibratorPreferences,
    MacbethCalibratorSettings,
    MB_OT_SetupSampleMarkers,
    MB_OT_SetBackground,
    MB_OT_CalculateMatrix,
    MB_OT_ApplyToCompositor,
    MB_OT_ExportCLF,
    MB_PT_CalibratorPanel,
)

def register():
    """Registers all addon classes and adds properties."""
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.macbeth_calibrator_settings = PointerProperty(type=MacbethCalibratorSettings)
    
    # Add the handler to Blender's application handlers
    if macbeth_depsgraph_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(macbeth_depsgraph_handler)

def unregister():
    """Unregisters all addon classes and removes properties."""
    # Remove the handler safely
    for handler in bpy.app.handlers.depsgraph_update_post:
        if handler.__name__ == "macbeth_depsgraph_handler":
            bpy.app.handlers.depsgraph_update_post.remove(handler)
            
    try:
        del bpy.types.Scene.macbeth_calibrator_settings
    except (AttributeError, RuntimeError):
        pass

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except (RuntimeError):
            pass

if __name__ == "__main__":
    try:
        unregister()
    except Exception as e:
        print(f"Error during auto-unregister: {e}")
    register()
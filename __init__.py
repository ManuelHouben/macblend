# -*- coding: utf-8 -*-
# <pep8 compliant>

import json
import os

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    PointerProperty,
    StringProperty,
)

from . import calibration
from . import sampling


_enum_cache = None
_enum_cache_path = None


def clamp_sample_region(image_size, center_x, center_y, patch_size):
    """Return a bounded sample rect that stays inside the image pixel bounds.

    The old image-sampling logic in the CCC variant sampled an unbounded box around
    the patch center. If the overlay was slightly misaligned or the sample center was
    near an edge, the resulting slice could expand beyond the image bounds and trigger
    an expensive full-frame average, which locks Blender. Clamping the rect to the
    image bounds keeps the operation bounded and predictable.
    """
    width, height = image_size
    if width <= 0 or height <= 0:
        return None

    sample_size = max(1, int(patch_size))
    if sample_size > max(width, height):
        sample_size = max(width, height)

    half = sample_size // 2
    x = int(round(center_x))
    y = int(round(center_y))

    x0 = max(0, x - half)
    x1 = min(width, x + half + (sample_size % 2))
    y0 = max(0, y - half)
    y1 = min(height, y + half + (sample_size % 2))

    if x0 >= x1:
        x = max(0, min(width - 1, x))
        return (x, x + 1, y, y + 1)
    if y0 >= y1:
        y = max(0, min(height - 1, y))
        return (x0, x1, y, y + 1)

    return (x0, x1, y0, y1)


def get_image_colorspace_name(image):
    if not image or not getattr(image, 'colorspace_settings', None):
        return "Unknown"
    return image.colorspace_settings.name


def get_image_sampling_guidance(image):
    if not image:
        return []

    colorspace_name = get_image_colorspace_name(image)
    normalized_name = colorspace_name.strip().lower()
    file_name = (image.filepath or image.name or "").lower()
    guidance = [
        "Sampling reads Blender's decoded image buffer.",
        "Display/View Transform affects viewing, not sampled values.",
    ]

    if normalized_name == 'non-color':
        guidance.append("Use Non-Color only for data or intentional transform bypass.")
        if file_name.endswith('.exr'):
            guidance.append("EXR plates usually need their true source colorspace, not Non-Color.")
    elif 'acescg' in normalized_name:
        guidance.append("ACEScg tagging is correct only if the file is actually ACEScg scene-linear.")
    elif 'linear' in normalized_name:
        guidance.append("Linear tagging is appropriate only when the file is already scene-linear in that gamut.")
    else:
        guidance.append("Non-linear image tagging will change sampled values before calibration.")

    return guidance


def get_target_colorspace_items(self, context):
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
    except Exception:
        return items


class MacbethCalibratorPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    json_file_path: StringProperty(
        name="Colorspace JSON File",
        description="Path to the JSON file containing colorspace transform data. If left empty, the default bundled file will be used.",
        subtype='FILE_PATH',
        default="",
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
    sample_source_image: PointerProperty(
        name="Source Image",
        description="Saved Macbeth chart calibration data to use when creating the transform",
        type=bpy.types.Image,
        poll=lambda self, obj: obj is not None and getattr(obj, 'mb_sample_data', None) is not None and obj.mb_sample_data.is_saved,
    )
    create_exposure_node: BoolProperty(
        name="Create Exposure Node",
        description="Normalize the matrix and insert a matching exposure/scale node when checked; leave the raw matrix when unchecked.",
        default=True,
    )
    normalization_factor: FloatProperty(
        name="Normalization Factor",
        description="Stored luminance compensation factor from the last matrix calculation",
        default=1.0,
        min=0.0,
    )
    debug_parity_logging: BoolProperty(
        name="Debug Parity Logging",
        description="Print sampled input patches and additional parity diagnostics to the console for comparison.",
        default=False,
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
        default=[1, 0, 0, 0, 1, 0, 0, 0, 1],
    )
    calculation_done: BoolProperty(
        name="Calculation Done Flag",
        description="Indicates if a matrix has been successfully calculated",
        default=False,
    )
    matrix_display_string: StringProperty(
        name="Formatted Matrix",
        description="User-friendly display of the calculated matrix",
        default="Matrix not calculated.",
    )
    node_name: StringProperty(
        name="Node Name",
        description="Base name for the generated forward and inverse matrix nodes",
        default="MacbethCalibration",
    )


classes = (
    MacbethCalibratorPreferences,
    MacbethCalibratorSettings,
    sampling.MB_ColorSample,
    sampling.MB_ImageSampleData,
    sampling.MB_GT_OverlaySquare,
    sampling.MB_GT_CornerCross,
    sampling.MB_GGT_ImageEditorOverlay,
    sampling.MB_OT_AdjustOverlayCorner,
    sampling.MB_OT_SaveSampleData,
    sampling.MB_OT_SampleImageColors,
    sampling.MB_OT_ClearSampleData,
    sampling.MB_PT_ImageEditorSamplePanel,
    calibration.MB_OT_CreateTransform,
    calibration.MB_PT_CalibrationPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.macbeth_calibrator_settings = PointerProperty(type=MacbethCalibratorSettings)
    bpy.types.Image.macbeth_sample_data = PointerProperty(type=sampling.MB_ImageSampleData)
    bpy.types.Image.mb_sample_data = PointerProperty(type=sampling.MB_ImageSampleData)
    sampling.MB_Messagebus_Init()
    sampling.MB_ImageEditor_Changed()

    if sampling.MB_Messagebus_LoadPost not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(sampling.MB_Messagebus_LoadPost)


def unregister():
    sampling.MB_Messagebus_Remove()

    if sampling.MB_Messagebus_LoadPost in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(sampling.MB_Messagebus_LoadPost)

    try:
        del bpy.types.Scene.macbeth_calibrator_settings
    except (AttributeError, RuntimeError):
        pass

    for prop_name in ('macbeth_sample_data', 'mb_sample_data'):
        try:
            delattr(bpy.types.Image, prop_name)
        except (AttributeError, RuntimeError):
            pass

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

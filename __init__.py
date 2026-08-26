# -*- coding: utf-8 -*-
# <pep8 compliant>
# Acknowledgements: This add-on owes much to Marco Meyer's mmColorTarget and
# Jed Smith's (jedypod) CalibrateMacbeth for Nuke, with inspiration from
# Paul Schlichter's Colour Chart Camera Matcher add-on.

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
from . import colorspaces
from . import sampling


_enum_cache = None
_enum_cache_key = None


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
    global _enum_cache, _enum_cache_key
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

        cache_key = colorspaces.json_cache_key(json_path)
        if _enum_cache and _enum_cache_key == cache_key:
            return _enum_cache

        if not json_path:
            _enum_cache = items
            _enum_cache_key = None
            return items

        json_data = colorspaces.load_colorspace_data(json_path)

        if "XYZ_to_RGB_matrices" in json_data:
            sorted_keys = sorted(json_data["XYZ_to_RGB_matrices"].keys())
            for key in sorted_keys:
                items.append((key, key, f"Target {key} colorspace from JSON"))

        _enum_cache = items
        _enum_cache_key = cache_key
        return items
    except (OSError, colorspaces.ColorspaceDataError) as exc:
        print(f"[MacBlend] {exc}")
        return items


class MacBlendCalibratorPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    json_file_path: StringProperty(
        name="Colorspace JSON File",
        description="Path to the JSON file containing colorspace transform data. If left empty, the default bundled file will be used.",
        subtype='FILE_PATH',
        default="",
    )
    debug_logging: BoolProperty(
        name="Debug Logging",
        description="Print sampling and calibration diagnostics to the console",
        default=False,
    )

    def get_effective_json_path(self):
        return colorspaces.effective_json_path(self.json_file_path)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Specify the path to the colorspace transforms JSON file.")
        layout.label(text="If left blank, a bundled default file will be used.")
        layout.prop(self, "json_file_path")
        layout.prop(self, "debug_logging")

        effective_path = self.get_effective_json_path()
        if effective_path:
            box = layout.box()
            try:
                colorspaces.load_colorspace_data(effective_path)
                box.label(text=f"Effective Path: {effective_path}", icon='INFO')
            except colorspaces.ColorspaceDataError as exc:
                box.label(text=str(exc), icon='ERROR')
        else:
            box = layout.box()
            box.label(text="Warning: No valid JSON file found.", icon='ERROR')


class MacBlendCalibratorSettings(bpy.types.PropertyGroup):
    sample_source_image: PointerProperty(
        name="Source Image",
        description="Macbeth chart calibration data to use when creating the transform",
        type=bpy.types.Image,
        poll=lambda self, obj: sampling.image_has_sample_values(obj),
    )
    sample_target_image: PointerProperty(
        name="Target Image",
        description="Macbeth chart calibration data to use as the target values",
        type=bpy.types.Image,
        poll=lambda self, obj: sampling.image_has_sample_values(obj),
    )
    use_reference_target: BoolProperty(
        name="Use reference values as target",
        description="Use the selected colorspace reference values instead of sampled target image values",
        default=True,
    )
    normalize_calibration: BoolProperty(
        name="Normalize",
        description="Pre-scaling source samples to the mid-grey patch before solving the calibration matrix.",
        default=True,
    )
    create_exposure_node: BoolProperty(
        name="Create Exposure Node",
        description="Insert a matching exposure/scale node after the calculated matrix. This is optional and independent from the normalization solve itself.",
        default=True,
    )
    normalization_factor: FloatProperty(
        name="Normalization Factor",
        description="Stored luminance compensation factor from the last matrix calculation",
        default=1.0,
        min=0.0,
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
        default="MacBlendCalibration",
    )


classes = (
    MacBlendCalibratorPreferences,
    MacBlendCalibratorSettings,
    sampling.MB_ColorSample,
    sampling.MB_ChartPatchCenter,
    sampling.MB_ImageSampleData,
    sampling.MB_SamplingUIState,
    sampling.MB_UL_SampledImages,
    sampling.MB_GT_OverlaySquare,
    sampling.MB_GT_CornerCross,
    sampling.MB_GT_FlipArrow,
    sampling.MB_GGT_ImageEditorOverlay,
    sampling.MB_OT_AdjustOverlayCorner,
    sampling.MB_OT_FlipOverlayHorizontal,
    sampling.MB_OT_FlipOverlayVertical,
    sampling.MB_OT_CenterOverlayChart,
    sampling.MB_OT_SampleImageColors,
    sampling.MB_OT_ClearSampleData,
    sampling.MB_PT_ImageEditorSamplePanel,
    calibration.MB_OT_MatchTransform,
    calibration.MB_OT_NeutralizeTransform,
    calibration.MB_OT_ExportLuts,
    calibration.MB_OT_ConfirmLutOverwrite,
    calibration.MB_PT_CalibrationPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.macblend_calibrator_settings = PointerProperty(type=MacBlendCalibratorSettings)
    bpy.types.Scene.macblend_sampling_ui = PointerProperty(type=sampling.MB_SamplingUIState)
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
        del bpy.types.Scene.macblend_calibrator_settings
    except (AttributeError, RuntimeError):
        pass

    try:
        del bpy.types.Scene.macblend_sampling_ui
    except (AttributeError, RuntimeError):
        pass

    try:
        del bpy.types.Image.mb_sample_data
    except (AttributeError, RuntimeError):
        pass

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

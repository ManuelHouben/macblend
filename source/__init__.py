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
    IntProperty,
    PointerProperty,
    StringProperty,
)

from . import calibration
from . import core
from . import manual
from . import sampling


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
    return [
        (
            identifier,
            label,
            f"Reference values in the {label} linear gamut",
        )
        for identifier, label, _matrix in core.REFERENCE_GAMUTS
    ]


def _invalidate_calibration_result(settings, _context=None):
    settings.calculation_done = False
    settings.matrix_display_string = "Matrix not calculated."


def _update_calibration_source_image(settings, _context):
    _invalidate_calibration_result(settings)
    if settings.sample_source_image is None:
        settings.auto_detected_target = ''
        return
    detected_target = calibration.detect_working_space_gamut()
    settings.auto_detected_target = detected_target or ''
    settings.target_colorspace = detected_target or 'REC709'


def _preference_value(name, fallback):
    addon = bpy.context.preferences.addons.get(__package__)
    return getattr(addon.preferences, name, fallback) if addon else fallback


def _get_normalize_calibration(settings):
    return bool(settings.get(
        'normalize_calibration',
        _preference_value('default_normalize_calibration', True),
    ))


def _set_normalize_calibration(settings, value):
    settings['normalize_calibration'] = bool(value)
    _invalidate_calibration_result(settings)


def _get_create_exposure_node(settings):
    return bool(settings.get(
        'create_exposure_node',
        _preference_value('default_create_exposure_node', False),
    ))


def _set_create_exposure_node(settings, value):
    settings['create_exposure_node'] = bool(value)


def _update_gizmo_scale(_preferences, _context):
    sampling._tag_image_editor_redraw()


class MacBlendCalibratorPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    default_patch_size: IntProperty(
        name="Patch Size",
        description="Default Macbeth patch sample size in image pixels",
        default=sampling.MB_INITIAL_PATCH_SIZE,
        min=1,
        max=200,
    )
    default_overlay_opacity: FloatProperty(
        name="Overlay Opacity",
        description="Default opacity of the Macbeth chart overlay",
        default=0.5,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )
    gizmo_scale: FloatProperty(
        name="Gizmo Scale",
        description="Scale corner crosses and flip controls in the Image Editor",
        default=1.0,
        min=0.25,
        max=4.0,
        soft_max=2.0,
        update=_update_gizmo_scale,
    )
    default_normalize_calibration: BoolProperty(
        name="Normalization",
        description="Enable calibration normalization by default",
        default=True,
    )
    default_create_exposure_node: BoolProperty(
        name="Exposure Node Creation",
        description="Create a separate exposure node by default",
        default=False,
    )
    default_lut_size: EnumProperty(
        name="LUT Size",
        description="Default exported 3D LUT size",
        items=(('17', "17", "17x17x17"), ('33', "33", "33x33x33"), ('65', "65", "65x65x65")),
        default='33',
    )
    default_lut_clamp: BoolProperty(
        name="LUT Clamping",
        description="Clamp exported LUT values to the 0-1 range by default",
        default=False,
    )

    debug_logging: BoolProperty(
        name="Debug Logging",
        description="Print sampling and calibration diagnostics to the console",
        default=False,
    )

    def draw(self, context):
        layout = self.layout

        primary_defaults = layout.row()
        primary_defaults.alignment = 'LEFT'

        sampling_defaults = primary_defaults.column(align=True)
        sampling_defaults.ui_units_x = 15
        sampling_defaults.label(text="Sampling")
        sampling_defaults.prop(self, "default_patch_size", slider=True)
        sampling_defaults.prop(self, "default_overlay_opacity", slider=True)
        sampling_defaults.prop(self, "gizmo_scale")

        calibration_defaults = primary_defaults.column(align=True)
        calibration_defaults.label(text="Calibration")
        calibration_defaults.prop(self, "default_normalize_calibration")
        calibration_defaults.prop(self, "default_create_exposure_node")

        lut_defaults = layout.column(align=True)
        lut_defaults.ui_units_x = 15
        lut_defaults.label(text="LUT Export")
        lut_size_row = lut_defaults.row()
        lut_size_row.alignment = 'LEFT'
        lut_size_row.label(text="LUT Size:")
        lut_size_row.separator(factor=5)
        lut_size_dropdown = lut_size_row.row()
        lut_size_dropdown.prop(self, "default_lut_size", text="")
        lut_defaults.prop(self, "default_lut_clamp")

        layout.separator()
        layout.prop(self, "debug_logging")


class MacBlendCalibratorSettings(bpy.types.PropertyGroup):
    sample_source_image: PointerProperty(
        name="Source Image",
        description="Macbeth chart calibration data to use when creating the transform",
        type=bpy.types.Image,
        poll=lambda self, obj: sampling.image_has_sample_values(obj),
        update=_update_calibration_source_image,
    )
    sample_target_image: PointerProperty(
        name="Target Image",
        description="Macbeth chart calibration data to use as the target values",
        type=bpy.types.Image,
        poll=lambda self, obj: sampling.image_has_sample_values(obj),
        update=_invalidate_calibration_result,
    )
    use_reference_target: BoolProperty(
        name="Use reference values as target",
        description="Use the selected colorspace reference values instead of sampled target image values",
        default=True,
        update=_invalidate_calibration_result,
    )
    normalize_calibration: BoolProperty(
        name="Normalize",
        description="Pre-scaling source samples to the mid-grey patch before solving the calibration matrix.",
        get=_get_normalize_calibration,
        set=_set_normalize_calibration,
    )
    create_exposure_node: BoolProperty(
        name="Create Exposure Node",
        description="Insert a matching exposure/scale node after the calculated matrix. This is optional and independent from the normalization solve itself.",
        get=_get_create_exposure_node,
        set=_set_create_exposure_node,
    )
    normalization_factor: FloatProperty(
        name="Normalization Factor",
        description="Stored luminance compensation factor from the last matrix calculation",
        default=1.0,
        min=0.0,
    )
    target_colorspace: EnumProperty(
        name="Target Gamut",
        description="Select the target working gamut",
        items=get_target_colorspace_items,
        update=_invalidate_calibration_result,
    )
    auto_detected_target: StringProperty(
        name="Auto-detected Target",
        description="Working-space gamut detected when the calibration source image was selected",
        options={'HIDDEN'},
        default="",
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
    sampling.MB_GT_CornerCross,
    sampling.MB_GT_FlipArrow,
    sampling.MB_GGT_ImageEditorOverlay,
    sampling.MB_OT_AdjustOverlayCorner,
    sampling.MB_OT_FlipOverlayHorizontal,
    sampling.MB_OT_FlipOverlayVertical,
    sampling.MB_OT_CenterOverlayChart,
    sampling.MB_OT_ResetOverlayChart,
    sampling.MB_OT_ConfirmSamplingSanityChecks,
    sampling.MB_OT_OpenPanoramaChartView,
    sampling.MB_OT_SampleImageColors,
    sampling.MB_OT_ClearSampleData,
    sampling.MB_PT_ImageEditorSamplePanel,
    calibration.MB_OT_ForwardTransform,
    calibration.MB_OT_InverseTransform,
    calibration.MB_OT_ConfirmTransform,
    calibration.MB_OT_ExportLuts,
    calibration.MB_OT_ConfirmLutOverwrite,
    calibration.MB_PT_CalibrationPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    manual.register()

    bpy.types.Scene.macblend_calibrator_settings = PointerProperty(type=MacBlendCalibratorSettings)
    bpy.types.Scene.macblend_sampling_ui = PointerProperty(type=sampling.MB_SamplingUIState)
    bpy.types.Image.mb_sample_data = PointerProperty(type=sampling.MB_ImageSampleData)
    sampling.MB_Messagebus_Init()
    sampling.MB_ImageEditor_Changed()

    if sampling.MB_Messagebus_LoadPost not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(sampling.MB_Messagebus_LoadPost)


def unregister():
    sampling.MB_Messagebus_Remove()
    manual.unregister()

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

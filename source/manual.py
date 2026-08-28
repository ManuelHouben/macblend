import bpy


MANUAL_URL = "https://manuelhouben.github.io/macblend/"
MANUAL_MAPPING = (
    ("bpy.ops.macblend.adjust_overlay_corner", "sampling/index.html"),
    ("bpy.ops.macblend.center_overlay_chart", "sampling/index.html"),
    ("bpy.ops.macblend.flip_overlay_horizontal", "sampling/index.html"),
    ("bpy.ops.macblend.flip_overlay_vertical", "sampling/index.html"),
    ("bpy.ops.macblend.sample_image_colors", "sampling/index.html"),
    ("bpy.ops.macblend.clear_sample_data", "sampling/index.html"),
    ("bpy.ops.macblend.forward_transform", "calibration/index.html"),
    ("bpy.ops.macblend.inverse_transform", "calibration/index.html"),
    ("bpy.ops.macblend.export_luts", "export/index.html"),
)


def manual_map():
    return MANUAL_URL, MANUAL_MAPPING


def register():
    bpy.utils.register_manual_map(manual_map)


def unregister():
    bpy.utils.unregister_manual_map(manual_map)

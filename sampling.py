import numpy as np
import bpy
from .core import sample_image_color
from mathutils import Vector
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)


class MB_TempData:
    current_image = None


MB_TEMP = MB_TempData()
MB_MSGBUS_OWNER = object()
MB_OVERLAY_RENDER_ALPHA_MAX = 0.999
MB_FLIP_BUTTON_SCALE = 48.0
MB_FLIP_BUTTON_LINE_WIDTH = 10
MB_CHART_ASPECT_RATIO = 28.0 / 21.0
MB_CHART_AREA_FRACTION = 0.25

MB_MACBETH_REFERENCE_SRGB = (
    (116 / 255.0, 81 / 255.0, 67 / 255.0),
    (199 / 255.0, 147 / 255.0, 129 / 255.0),
    (91 / 255.0, 122 / 255.0, 156 / 255.0),
    (90 / 255.0, 108 / 255.0, 64 / 255.0),
    (130 / 255.0, 128 / 255.0, 176 / 255.0),
    (92 / 255.0, 190 / 255.0, 172 / 255.0),
    (224 / 255.0, 124 / 255.0, 47 / 255.0),
    (68 / 255.0, 91 / 255.0, 170 / 255.0),
    (198 / 255.0, 82 / 255.0, 97 / 255.0),
    (94 / 255.0, 58 / 255.0, 106 / 255.0),
    (159 / 255.0, 189 / 255.0, 63 / 255.0),
    (230 / 255.0, 162 / 255.0, 39 / 255.0),
    (35 / 255.0, 63 / 255.0, 147 / 255.0),
    (67 / 255.0, 149 / 255.0, 74 / 255.0),
    (180 / 255.0, 49 / 255.0, 57 / 255.0),
    (238 / 255.0, 198 / 255.0, 20 / 255.0),
    (193 / 255.0, 84 / 255.0, 151 / 255.0),
    (0 / 255.0, 136 / 255.0, 170 / 255.0),
    (245 / 255.0, 245 / 255.0, 243 / 255.0),
    (200 / 255.0, 202 / 255.0, 202 / 255.0),
    (161 / 255.0, 163 / 255.0, 163 / 255.0),
    (121 / 255.0, 121 / 255.0, 122 / 255.0),
    (82 / 255.0, 84 / 255.0, 86 / 255.0),
    (49 / 255.0, 49 / 255.0, 51 / 255.0),
)


def _debug_logging_enabled(context):
    addon = context.preferences.addons.get(__package__)
    return bool(addon and getattr(addon.preferences, 'debug_logging', False))

# Logical Macbeth order is top-to-bottom, left-to-right, matching the chart layout
# used by the color-reference arrays and by the Nuke tools.
# ccmaster: canonical Macbeth patch ordering used as the ground truth for all chart logic.
MB_MACBETH_PATCH_NAMES = (
    'Dark Skin',
    'Light Skin',
    'Blue Sky',
    'Foliage',
    'Blue Flower',
    'Bluish Green',
    'Orange',
    'Purplish Blue',
    'Moderate Red',
    'Purple',
    'Yellow Green',
    'Orange Yellow',
    'Blue',
    'Green',
    'Red',
    'Yellow',
    'Magenta',
    'Cyan',
    'White 9.5',
    'Neutral 8',
    'Neutral 6.5',
    'Neutral 5',
    'Neutral 3.5',
    'Black 2',
)
MB_CCMASTER = tuple((slot, name) for slot, name in enumerate(MB_MACBETH_PATCH_NAMES))

MB_SAMPLE_PROPERTY_NAMES = tuple(f"sample_patch_{index + 1:02d}" for index in range(24))


def _lerp_2d(point_a, point_b, factor):
    return (
        point_a[0] + (point_b[0] - point_a[0]) * factor,
        point_a[1] + (point_b[1] - point_a[1]) * factor,
    )


def _grid_point(corners, u, v):
    top = _lerp_2d(corners[0], corners[1], u)
    bottom = _lerp_2d(corners[3], corners[2], u)
    return _lerp_2d(bottom, top, v)


def _get_overlay_corners(data, image):
    return (
        tuple(data.corner_tl),
        tuple(data.corner_tr),
        tuple(data.corner_br),
        tuple(data.corner_bl),
    )


def _corner_target_point(corners, corner_idx):
    return corners[corner_idx]


def _region_point(context, point):
    region = context.region
    if region is None:
        return None
    return region.view2d.view_to_region(point[0], point[1], clip=False)


def _tag_image_editor_redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.tag_redraw()


def _safe_sample_patch_bounds(width, height, center_x, center_y, patch_size):
    from . import clamp_sample_region

    return clamp_sample_region((width, height), center_x, center_y, patch_size)


def _set_sample_patch_value(data, sample_idx, rgb_value):
    if 0 <= sample_idx < len(MB_SAMPLE_PROPERTY_NAMES):
        setattr(data, MB_SAMPLE_PROPERTY_NAMES[sample_idx], tuple(rgb_value))


def _ccmaster_patch_uv(slot, flip_horizontal=False, flip_vertical=False):
    row = slot // 6
    col = slot % 6
    u = (col + 0.5) / 6.0
    v = 1.0 - (row + 0.5) / 4.0
    if flip_horizontal:
        u = 1.0 - u
    if flip_vertical:
        v = 1.0 - v
    return u, v


def _build_ccmaster_patch_centers(data, corners):
    data.patch_centers.clear()
    for slot, patch_name in MB_CCMASTER:
        u, v = _ccmaster_patch_uv(slot, bool(data.chart_hflip), bool(data.chart_vflip))
        center_x, center_y = _grid_point(corners, u, v)
        patch = data.patch_centers.add()
        patch.slot = slot
        patch.patch_name = patch_name
        patch.x = center_x
        patch.y = center_y

    return data.patch_centers


def _center_overlay_corners(data, image_width, image_height, chart_aspect_ratio=MB_CHART_ASPECT_RATIO, area_fraction=MB_CHART_AREA_FRACTION):
    if image_width <= 0 or image_height <= 0:
        return

    target_area = float(area_fraction) * float(image_width) * float(image_height)
    ratio = max(float(chart_aspect_ratio), 1e-6)

    chart_width_px = (target_area * ratio) ** 0.5
    chart_height_px = chart_width_px / ratio

    # Keep the whole chart visible even on very wide/tall images.
    fit_scale = min(float(image_width) / max(chart_width_px, 1e-6), float(image_height) / max(chart_height_px, 1e-6), 1.0)
    chart_width_px *= fit_scale
    chart_height_px *= fit_scale

    width_norm = chart_width_px / float(image_width)
    height_norm = chart_height_px / float(image_height)

    center_x = 0.5
    center_y = 0.5
    half_width = width_norm * 0.5
    half_height = height_norm * 0.5

    data.corner_tl = (center_x - half_width, center_y + half_height)
    data.corner_tr = (center_x + half_width, center_y + half_height)
    data.corner_br = (center_x + half_width, center_y - half_height)
    data.corner_bl = (center_x - half_width, center_y - half_height)


def _linear_to_srgb_channel(channel):
    channel = max(0.0, min(1.0, float(channel)))
    if channel <= 0.0031308:
        return 12.92 * channel
    return 1.055 * (channel ** (1.0 / 2.4)) - 0.055


def _linear_to_srgb(rgb_value):
    return tuple(_linear_to_srgb_channel(channel) for channel in rgb_value[:3])


def _reset_sample_patch_values(data):
    for sample_idx, prop_name in enumerate(MB_SAMPLE_PROPERTY_NAMES):
        setattr(data, prop_name, MB_MACBETH_REFERENCE_SRGB[sample_idx])


def _initialize_overlay_defaults(image):
    if image is None:
        return

    data = getattr(image, 'mb_sample_data', None)
    if data is None or data.overlay_defaults_initialized:
        return

    if getattr(image, 'source', None) == 'VIEWER':
        data.show_overlay = False
        data.show_overlay_corners = False

    data.overlay_defaults_initialized = True


def _init_current_image():
    current_image = None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'IMAGE_EDITOR' and area.spaces.active.image is not None:
                current_image = area.spaces.active.image
                break
        if current_image is not None:
            break

    MB_TEMP.current_image = current_image
    _initialize_overlay_defaults(current_image)


@persistent
def MB_Messagebus_Init(*args):
    bpy.msgbus.clear_by_owner(MB_MSGBUS_OWNER)
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.SpaceImageEditor, 'image'),
        owner=MB_MSGBUS_OWNER,
        args=(),
        notify=MB_ImageEditor_Changed,
    )


def MB_ImageEditor_Changed():
    _init_current_image()
    _tag_image_editor_redraw()


def MB_Messagebus_Remove():
    bpy.msgbus.clear_by_owner(MB_MSGBUS_OWNER)


class MB_GT_OverlaySquare(bpy.types.Gizmo):
    style: IntProperty(default=0, options={'SKIP_SAVE'})

    def setup(self):
        self.outline_shape = self.new_custom_shape(
            'LINES',
            (
                (0.0, 0.0), (0.0, 1.0),
                (0.0, 1.0), (1.0, 1.0),
                (1.0, 1.0), (1.0, 0.0),
                (1.0, 0.0), (0.0, 0.0),
            ),
        )
        self.fill_shape = self.new_custom_shape(
            'TRIS',
            (
                (0.0, 0.0), (0.0, 1.0), (1.0, 1.0),
                (0.0, 0.0), (1.0, 1.0), (1.0, 0.0),
            ),
        )

    def draw(self, context):
        if self.style == 0:
            self.draw_custom_shape(self.outline_shape)
        else:
            self.draw_custom_shape(self.fill_shape)


class MB_GT_CornerCross(bpy.types.Gizmo):
    def setup(self):
        self.shape = self.new_custom_shape(
            'LINES',
            (
                (-0.5, 0.0), (0.5, 0.0),
                (0.0, -0.5), (0.0, 0.5),
            ),
        )

    def draw(self, context):
        if getattr(self, 'is_modal', False):
            self.color = (1.0, 1.0, 1.0)
            self.alpha = 1.0
        else:
            self.color = self.color_highlight if getattr(self, 'is_highlight', False) else (0.75, 0.75, 0.75)
            self.alpha = self.alpha_highlight if getattr(self, 'is_highlight', False) else 0.9
        self.draw_custom_shape(self.shape)

    def test_select(self, context, co):
        corners = [
            self.matrix_world @ Vector((-0.6, -0.6, 0, 1)),
            self.matrix_world @ Vector((-0.6, 0.6, 0, 1)),
            self.matrix_world @ Vector((0.6, -0.6, 0, 1)),
            self.matrix_world @ Vector((0.6, 0.6, 0, 1)),
        ]
        min_x = min(point[0] for point in corners)
        max_x = max(point[0] for point in corners)
        min_y = min(point[1] for point in corners)
        max_y = max(point[1] for point in corners)
        if min_x <= co[0] <= max_x and min_y <= co[1] <= max_y:
            return 0
        return -1


class MB_GT_FlipArrow(bpy.types.Gizmo):
    def setup(self):
        self.shape = self.new_custom_shape(
            'TRIS',
            (
                # Shaft
                (-0.45, -0.06), (-0.45, 0.06), (0.45, 0.06),
                (-0.45, -0.06), (0.45, 0.06), (0.45, -0.06),
                # Left arrow head
                (-0.45, 0.2), (-0.45, -0.2), (-0.78, 0.0),
                # Right arrow head
                (0.45, 0.2), (0.78, 0.0), (0.45, -0.2),
            ),
        )
    def draw(self, context):
        if getattr(self, 'is_modal', False):
            self.color = (1.0, 1.0, 1.0)
            self.alpha = 1.0
        else:
            self.color = (0.35, 0.35, 0.35) if getattr(self, 'is_highlight', False) else (0.75, 0.75, 0.75)
            self.alpha = 1.0 if getattr(self, 'is_highlight', False) else 0.9
        self.draw_custom_shape(self.shape)

    def test_select(self, context, co):
        corners = [
            self.matrix_world @ Vector((-0.9, -0.9, 0, 1)),
            self.matrix_world @ Vector((-0.9, 0.9, 0, 1)),
            self.matrix_world @ Vector((0.9, -0.9, 0, 1)),
            self.matrix_world @ Vector((0.9, 0.9, 0, 1)),
        ]
        min_x = min(point[0] for point in corners)
        max_x = max(point[0] for point in corners)
        min_y = min(point[1] for point in corners)
        max_y = max(point[1] for point in corners)
        if min_x <= co[0] <= max_x and min_y <= co[1] <= max_y:
            return 0
        return -1


class MB_GGT_ImageEditorOverlay(bpy.types.GizmoGroup):
    bl_idname = "MB_GGT_image_editor_overlay"
    bl_label = "Macbeth Chart Overlay"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SHOW_MODAL_ALL', 'SCALE'}

    @classmethod
    def poll(cls, context):
        image = getattr(getattr(context, 'space_data', None), 'image', None) or MB_TEMP.current_image
        return image is not None and getattr(image, 'mb_sample_data', None) is not None and image.mb_sample_data.show_overlay

    def setup(self, context):
        self.outlines = []
        self.fills = []
        self.corners = []
        self.flip_buttons = []

        for _ in range(24):
            outline = self.gizmos.new('MB_GT_OverlaySquare')
            outline.style = 0
            outline.color = outline.color_highlight = (1.0, 1.0, 1.0)
            outline.alpha = outline.alpha_highlight = 1.0
            outline.use_draw_modal = True
            self.outlines.append(outline)

            fill = self.gizmos.new('MB_GT_OverlaySquare')
            fill.style = 1
            fill.color = fill.color_highlight = (0.2, 0.95, 0.35)
            fill.alpha = fill.alpha_highlight = 0.35
            fill.use_draw_modal = True
            self.fills.append(fill)

        for corner_idx in range(4):
            corner = self.gizmos.new('MB_GT_CornerCross')
            corner.color = (0.75, 0.75, 0.75)
            corner.color_highlight = (0.35, 0.35, 0.35)
            corner.alpha = 0.9
            corner.alpha_highlight = 1.0
            corner.line_width = 3
            corner.use_draw_modal = True
            operator = corner.target_set_operator('macblend.adjust_overlay_corner')
            operator.corner_idx = corner_idx
            self.corners.append(corner)

        self._ensure_flip_buttons()

    def _ensure_flip_buttons(self):
        if len(self.flip_buttons) >= 2:
            return

        for operator_id in (
            'macblend.flip_overlay_horizontal',
            'macblend.flip_overlay_vertical',
        ):
            if len(self.flip_buttons) >= 2:
                break
            button = self.gizmos.new('MB_GT_FlipArrow')
            button.color = (0.75, 0.75, 0.75)
            button.color_highlight = (0.35, 0.35, 0.35)
            button.alpha = 0.95
            button.alpha_highlight = 1.0
            button.line_width = MB_FLIP_BUTTON_LINE_WIDTH
            button.use_draw_modal = True
            button.target_set_operator(operator_id)
            self.flip_buttons.append(button)

    def _set_box(self, gizmo, context, points):
        region_points = [_region_point(context, point) for point in points]
        if any(point is None for point in region_points):
            gizmo.hide = True
            return

        min_x = min(point[0] for point in region_points)
        max_x = max(point[0] for point in region_points)
        min_y = min(point[1] for point in region_points)
        max_y = max(point[1] for point in region_points)

        gizmo.hide = False
        gizmo.matrix_basis.identity()
        gizmo.matrix_basis[0][0] = max(1.0, max_x - min_x)
        gizmo.matrix_basis[1][1] = max(1.0, max_y - min_y)
        gizmo.matrix_basis[0][3] = min_x
        gizmo.matrix_basis[1][3] = min_y

    def _set_cross(self, gizmo, context, point):
        region_point = _region_point(context, point)
        if region_point is None:
            gizmo.hide = True
            return

        gizmo.hide = False
        gizmo.matrix_basis.identity()
        gizmo.matrix_basis[0][0] = 14.0
        gizmo.matrix_basis[1][1] = 14.0
        gizmo.matrix_basis[0][3] = region_point[0]
        gizmo.matrix_basis[1][3] = region_point[1]

    def _set_flip_button(self, gizmo, context, point, axis_start, axis_end):
        region_point = _region_point(context, point)
        axis_start_region = _region_point(context, axis_start)
        axis_end_region = _region_point(context, axis_end)
        if region_point is None or axis_start_region is None or axis_end_region is None:
            gizmo.hide = True
            return

        axis = (
            axis_end_region[0] - axis_start_region[0],
            axis_end_region[1] - axis_start_region[1],
        )
        axis_len = max((axis[0] ** 2 + axis[1] ** 2) ** 0.5, 1e-6)
        x_axis = (axis[0] / axis_len, axis[1] / axis_len)
        y_axis = (-x_axis[1], x_axis[0])
        scale = MB_FLIP_BUTTON_SCALE

        gizmo.hide = False
        gizmo.matrix_basis.identity()
        gizmo.matrix_basis[0][0] = x_axis[0] * scale
        gizmo.matrix_basis[1][0] = x_axis[1] * scale
        gizmo.matrix_basis[0][1] = y_axis[0] * scale
        gizmo.matrix_basis[1][1] = y_axis[1] * scale
        gizmo.matrix_basis[0][3] = region_point[0]
        gizmo.matrix_basis[1][3] = region_point[1]

    def _offset_from_chart(self, corners, base_point):
        center = _grid_point(corners, 0.5, 0.5)
        direction = (base_point[0] - center[0], base_point[1] - center[1])
        length = max((direction[0] ** 2 + direction[1] ** 2) ** 0.5, 1e-6)
        scale = 0.04
        return (
            base_point[0] + (direction[0] / length) * scale,
            base_point[1] + (direction[1] / length) * scale,
        )

    def draw_prepare(self, context):
        if not hasattr(self, 'flip_buttons'):
            self.flip_buttons = []
        self._ensure_flip_buttons()

        image = getattr(getattr(context, 'space_data', None), 'image', None) or MB_TEMP.current_image
        if image is None or not getattr(image, 'mb_sample_data', None) or not image.mb_sample_data.show_overlay:
            for gizmo in self.outlines + self.fills + self.corners + self.flip_buttons:
                gizmo.hide = True
            return

        width, height = image.size
        if width <= 0 or height <= 0:
            for gizmo in self.outlines + self.fills + self.corners + self.flip_buttons:
                gizmo.hide = True
            return

        corners = _get_overlay_corners(image.mb_sample_data, image)
        # Blender gizmo triangle fills can show internal seams at exactly 1.0 alpha.
        # Keep render alpha infinitesimally below opaque to avoid the artifact.
        overlay_alpha = min(float(image.mb_sample_data.overlay_opacity), MB_OVERLAY_RENDER_ALPHA_MAX)
        patch_size = max(1, int(image.mb_sample_data.patch_size))
        half_width = (patch_size * 0.5) / width
        half_height = (patch_size * 0.5) / height

        samples_by_slot = {
            int(sample.patch_index): sample
            for sample in image.mb_sample_data.samples
            if 0 <= int(sample.patch_index) < len(MB_CCMASTER)
        }
        for index in range(len(MB_CCMASTER)):
            u, v = _ccmaster_patch_uv(
                index,
                bool(image.mb_sample_data.chart_hflip),
                bool(image.mb_sample_data.chart_vflip),
            )
            center = _grid_point(corners, u, v)
            cell_points = (
                (center[0] - half_width, center[1] - half_height),
                (center[0] + half_width, center[1] - half_height),
                (center[0] + half_width, center[1] + half_height),
                (center[0] - half_width, center[1] + half_height),
            )

            self._set_box(self.outlines[index], context, cell_points)
            self._set_box(self.fills[index], context, cell_points)
            self.outlines[index].color = self.outlines[index].color_highlight = MB_MACBETH_REFERENCE_SRGB[index]

            if index in samples_by_slot:
                patch_color = samples_by_slot[index].rgb
                patch_color = _linear_to_srgb(patch_color)
                self.fills[index].color = self.fills[index].color_highlight = patch_color
            else:
                self.fills[index].color = self.fills[index].color_highlight = MB_MACBETH_REFERENCE_SRGB[index]
            self.fills[index].alpha = self.fills[index].alpha_highlight = overlay_alpha

        for corner_idx in range(4):
            corner_gizmo = self.corners[corner_idx]
            corner_point = _corner_target_point(corners, corner_idx)
            self._set_cross(corner_gizmo, context, corner_point)

        tl, tr, br, bl = corners

        horizontal_base = _lerp_2d(tl, tr, 0.5)
        horizontal_point = self._offset_from_chart(corners, horizontal_base)
        self._set_flip_button(self.flip_buttons[0], context, horizontal_point, tl, tr)

        vertical_base = _lerp_2d(tl, bl, 0.5)
        vertical_point = self._offset_from_chart(corners, vertical_base)
        self._set_flip_button(self.flip_buttons[1], context, vertical_point, tl, bl)



class MB_OT_AdjustOverlayCorner(bpy.types.Operator):
    bl_idname = 'macblend.adjust_overlay_corner'
    bl_label = 'Adjust Overlay Corner'
    bl_options = {'GRAB_CURSOR', 'BLOCKING', 'UNDO'}

    corner_idx: IntProperty(default=0, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        image = getattr(context.space_data, 'image', None) or MB_TEMP.current_image
        if image is None or not getattr(image, 'mb_sample_data', None):
            return {'CANCELLED'}

        self.image = image
        self.data = image.mb_sample_data
        corner_name = ('corner_tl', 'corner_tr', 'corner_br', 'corner_bl')[self.corner_idx]
        self.start_value = tuple(getattr(self.data, corner_name))
        self.start_mouse_coords = tuple(context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y))

        context.window.cursor_modal_set('HAND_CLOSED')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        corner_name = ('corner_tl', 'corner_tr', 'corner_br', 'corner_bl')[self.corner_idx]

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            setattr(self.data, corner_name, self.start_value)
            context.window.cursor_modal_restore()
            _tag_image_editor_redraw()
            return {'CANCELLED'}

        if event.type == 'MOUSEMOVE':
            current_mouse_coords = tuple(context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y))
            delta = (
                current_mouse_coords[0] - self.start_mouse_coords[0],
                current_mouse_coords[1] - self.start_mouse_coords[1],
            )
            new_value = (
                self.start_value[0] + delta[0],
                self.start_value[1] + delta[1],
            )
            setattr(self.data, corner_name, new_value)
            _tag_image_editor_redraw()

        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            context.window.cursor_modal_restore()
            _tag_image_editor_redraw()
            return {'FINISHED'}

        return {'RUNNING_MODAL'}


class MB_OT_FlipOverlayHorizontal(bpy.types.Operator):
    bl_idname = 'macblend.flip_overlay_horizontal'
    bl_label = 'Flip Overlay Horizontal'
    bl_description = 'Mirror the Macbeth patch orientation horizontally inside the aligned corners'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        image = getattr(getattr(context, 'space_data', None), 'image', None) or MB_TEMP.current_image
        if image is None or not getattr(image, 'mb_sample_data', None):
            self.report({'ERROR'}, 'No image with Macbeth overlay data available.')
            return {'CANCELLED'}

        data = image.mb_sample_data
        data.chart_hflip = not data.chart_hflip

        _tag_image_editor_redraw()
        return {'FINISHED'}


class MB_OT_FlipOverlayVertical(bpy.types.Operator):
    bl_idname = 'macblend.flip_overlay_vertical'
    bl_label = 'Flip Overlay Vertical'
    bl_description = 'Mirror the Macbeth patch orientation vertically inside the aligned corners'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        image = getattr(getattr(context, 'space_data', None), 'image', None) or MB_TEMP.current_image
        if image is None or not getattr(image, 'mb_sample_data', None):
            self.report({'ERROR'}, 'No image with Macbeth overlay data available.')
            return {'CANCELLED'}

        data = image.mb_sample_data
        data.chart_vflip = not data.chart_vflip

        _tag_image_editor_redraw()
        return {'FINISHED'}


class MB_OT_CenterOverlayChart(bpy.types.Operator):
    bl_idname = 'macblend.center_overlay_chart'
    bl_label = 'Center Overlay'
    bl_description = 'Center the Macbeth chart overlay at 25% image area with a fixed 28:21 aspect ratio'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        image = getattr(getattr(context, 'space_data', None), 'image', None) or MB_TEMP.current_image
        if image is None or not getattr(image, 'mb_sample_data', None):
            self.report({'ERROR'}, 'No image with Macbeth overlay data available.')
            return {'CANCELLED'}

        width, height = image.size
        if width <= 0 or height <= 0:
            self.report({'ERROR'}, 'Selected image has no valid pixel resolution.')
            return {'CANCELLED'}

        _center_overlay_corners(image.mb_sample_data, width, height)
        _tag_image_editor_redraw()
        self.report({'INFO'}, 'Centered overlay at 25% image area (28:21 ratio).')
        return {'FINISHED'}


@persistent
def MB_Messagebus_LoadPost(*args):
    MB_Messagebus_Init()
    MB_ImageEditor_Changed()


class MB_ColorSample(bpy.types.PropertyGroup):
    patch_index: IntProperty(
        name="Patch Index",
        description="Logical Macbeth patch slot this sample belongs to",
        default=-1,
        min=-1,
        max=23,
    )
    rgb: FloatVectorProperty(
        name="RGB",
        description="Sampled Macbeth patch value",
        size=3,
        subtype='COLOR',
        default=(0.0, 0.0, 0.0),
    )


class MB_ChartPatchCenter(bpy.types.PropertyGroup):
    slot: IntProperty(name="Slot", default=-1, min=-1, max=23)
    patch_name: StringProperty(name="Patch Name", default="")
    x: FloatProperty(name="X", default=0.0)
    y: FloatProperty(name="Y", default=0.0)


class MB_ImageSampleData(bpy.types.PropertyGroup):
    samples: CollectionProperty(type=MB_ColorSample)
    patch_centers: CollectionProperty(type=MB_ChartPatchCenter)
    has_preview: BoolProperty(name="Preview Available", default=False)
    is_saved: BoolProperty(name="Saved in Blend", default=False)
    overlay_defaults_initialized: BoolProperty(name="Overlay Defaults Initialized", default=False)
    patch_size: IntProperty(name="Patch Size", default=30, min=1, max=200)
    overlay_opacity: FloatProperty(name="Overlay Opacity", default=0.5, min=0.0, max=1.0, subtype='FACTOR')
    source_name: StringProperty(name="Source Name", default="")
    show_overlay: BoolProperty(name="Show Overlay", default=True)
    show_overlay_corners: BoolProperty(name="Overlay Corners", default=False)
    chart_hflip: BoolProperty(name="Horizontal Flip", default=False)
    chart_vflip: BoolProperty(name="Vertical Flip", default=False)
    corner_tl: FloatVectorProperty(name="Top Left", size=2, default=(0.25, 0.82))
    corner_tr: FloatVectorProperty(name="Top Right", size=2, default=(0.75, 0.82))
    corner_br: FloatVectorProperty(name="Bottom Right", size=2, default=(0.75, 0.18))
    corner_bl: FloatVectorProperty(name="Bottom Left", size=2, default=(0.25, 0.18))


if not hasattr(MB_ImageSampleData, '__annotations__'):
    MB_ImageSampleData.__annotations__ = {}

for sample_idx, prop_name in enumerate(MB_SAMPLE_PROPERTY_NAMES):
    MB_ImageSampleData.__annotations__[prop_name] = FloatVectorProperty(
        name=MB_MACBETH_PATCH_NAMES[sample_idx],
        description=f"Sampled color for patch: {MB_MACBETH_PATCH_NAMES[sample_idx]}",
        size=3,
        subtype='COLOR',
        default=MB_MACBETH_REFERENCE_SRGB[sample_idx],
    )


class MB_OT_SampleImageColors(bpy.types.Operator):
    bl_idname = "macblend.sample_image_colors"
    bl_label = "Sample Chart"
    bl_description = "Sample the 24 Macbeth patch values from the active image"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        image = getattr(context.space_data, 'image', None)
        if image is None:
            self.report({'ERROR'}, "No image selected in the Image Editor.")
            return {'CANCELLED'}

        data = image.mb_sample_data
        data.samples.clear()
        data.patch_centers.clear()
        _reset_sample_patch_values(data)

        width, height = image.size
        if width <= 0 or height <= 0:
            self.report({'ERROR'}, "Selected image has no valid pixel resolution.")
            return {'CANCELLED'}

        pixels = np.asarray(image.pixels, dtype=np.float32).reshape((height, width, image.channels))
        overlay_corners = _get_overlay_corners(data, image)
        debug_logging = _debug_logging_enabled(context)
        if debug_logging:
            print(f"[MacBlend] User overlay state: h={bool(data.chart_hflip)} v={bool(data.chart_vflip)}", flush=True)
        _build_ccmaster_patch_centers(data, overlay_corners)
        sample_size = max(1, min(int(data.patch_size), max(width, height)))
        if debug_logging:
            print("[MacBlend] Sample Chart debug:", flush=True)

        for patch in data.patch_centers:
            slot = int(patch.slot)
            patch_name = patch.patch_name or MB_MACBETH_PATCH_NAMES[slot] if slot < len(MB_MACBETH_PATCH_NAMES) else f"slot_{slot}"
            x = max(0, min(width - 1, int(round(float(patch.x) * width))))
            y = max(0, min(height - 1, int(round(float(patch.y) * height))))

            sample_rgb = sample_image_color(pixels, width, height, x, y, sample_size)
            sample = data.samples.add()
            sample.patch_index = slot
            sample.rgb = sample_rgb
            _set_sample_patch_value(data, slot, sample.rgb)
            if debug_logging:
                print(f"  slot[{slot}] {patch_name} -> {tuple(float(v) for v in sample_rgb)}", flush=True)

        data.has_preview = True
        data.is_saved = False
        _tag_image_editor_redraw()
        self.report({'INFO'}, f"Sampled {len(data.samples)} values from '{image.name}'.")
        return {'FINISHED'}


class MB_OT_SaveSampleData(bpy.types.Operator):
    bl_idname = "macblend.save_sample_data"
    bl_label = "Save Sampled Values"
    bl_description = "Persist the sampled Macbeth values on the image datablock"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        image = getattr(context.space_data, 'image', None)
        if image is None:
            self.report({'ERROR'}, "No image selected in the Image Editor.")
            return {'CANCELLED'}

        data = image.mb_sample_data
        if not data.has_preview or len(data.samples) == 0:
            self.report({'WARNING'}, "There are no sampled values to save.")
            return {'CANCELLED'}

        data.is_saved = True
        data.source_name = image.name
        data.corner_tl = tuple(data.corner_tl)
        data.corner_tr = tuple(data.corner_tr)
        data.corner_br = tuple(data.corner_br)
        data.corner_bl = tuple(data.corner_bl)
        if data.show_overlay:
            data.show_overlay = False
            data.show_overlay_corners = False
            _tag_image_editor_redraw()
        self.report({'INFO'}, f"Saved Macbeth values for '{image.name}'.")
        return {'FINISHED'}


class MB_OT_ClearSampleData(bpy.types.Operator):
    bl_idname = "macblend.clear_sample_data"
    bl_label = "Clear Sample Data"
    bl_description = "Clear the saved preview and saved state for an image"
    bl_options = {'REGISTER', 'UNDO'}

    image_name: StringProperty(default="")

    def execute(self, context):
        image = bpy.data.images.get(self.image_name)
        if image is None:
            return {'CANCELLED'}

        data = image.mb_sample_data
        data.samples.clear()
        _reset_sample_patch_values(data)
        data.has_preview = False
        data.is_saved = False
        data.source_name = ""
        self.report({'INFO'}, f"Cleared sample data for '{image.name}'.")
        return {'FINISHED'}


class MB_PT_ImageEditorSamplePanel(bpy.types.Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_label = 'MacBlend'
    bl_category = 'MacBlend'

    def draw(self, context):
        layout = self.layout
        image = getattr(context.space_data, 'image', None)
        if image is None:
            layout.label(text="Select an image")
            return

        data = image.mb_sample_data
        layout.label(text=f"Image: {image.name}")
        layout.prop(data, 'patch_size')
        overlay_row = layout.row(align=True)
        overlay_row.prop(data, 'show_overlay')
        overlay_row.prop(data, 'overlay_opacity', slider=True)

        corners_header = layout.row(align=True)
        corners_icon = 'TRIA_DOWN' if data.show_overlay_corners else 'TRIA_RIGHT'
        corners_header.prop(data, 'show_overlay_corners', text='Overlay Corners', icon=corners_icon, emboss=False)

        if not data.show_overlay_corners:
            center_row = layout.row(align=True)
            center_row.enabled = not data.is_saved
            center_row.operator('macblend.center_overlay_chart', text='Center Overlay')

        if data.show_overlay_corners:
            box = layout.box()
            box.prop(data, 'corner_tl', text='Top Left')
            box.prop(data, 'corner_tr', text='Top Right')
            box.prop(data, 'corner_br', text='Bottom Right')
            box.prop(data, 'corner_bl', text='Bottom Left')
            flip_row = box.row(align=True)
            flip_row.operator('macblend.flip_overlay_horizontal', text='Flip Horizontal', depress=data.chart_hflip)
            flip_row.operator('macblend.flip_overlay_vertical', text='Flip Vertical', depress=data.chart_vflip)
            center_row = box.row(align=True)
            center_row.enabled = not data.is_saved
            center_row.operator('macblend.center_overlay_chart', text='Center Overlay')

        row = layout.row(align=True)
        row.operator('macblend.sample_image_colors', text='Sample Chart')
        save_row = row.row(align=True)
        save_row.enabled = data.has_preview
        save_row.operator('macblend.save_sample_data', text='Save Values')

        if data.has_preview and len(data.samples) > 0:
            box = layout.box()
            box.label(text='Sampled Values')
            samples_col = box.column(align=True)
            for display_row in range(4):
                ui_row = samples_col.row(align=True)
                for col_idx in range(6):
                    sample_idx = display_row * 6 + col_idx
                    cell = ui_row.column(align=True)
                    cell.prop(data, MB_SAMPLE_PROPERTY_NAMES[sample_idx], text='')

        saved_images = [img for img in bpy.data.images if getattr(img, 'mb_sample_data', None) and img.mb_sample_data.is_saved]
        if saved_images:
            box = layout.box()
            box.label(text='Saved Images')
            for img in saved_images:
                row = box.row()
                row.label(text=img.name)
                row.operator('macblend.clear_sample_data', text='Clear', icon='X').image_name = img.name


classes = (
    MB_ColorSample,
    MB_ChartPatchCenter,
    MB_ImageSampleData,
    MB_GT_OverlaySquare,
    MB_GT_CornerCross,
    MB_GT_FlipArrow,
    MB_GGT_ImageEditorOverlay,
    MB_OT_AdjustOverlayCorner,
    MB_OT_FlipOverlayHorizontal,
    MB_OT_FlipOverlayVertical,
    MB_OT_CenterOverlayChart,
    MB_OT_SampleImageColors,
    MB_OT_SaveSampleData,
    MB_OT_ClearSampleData,
    MB_PT_ImageEditorSamplePanel,
)

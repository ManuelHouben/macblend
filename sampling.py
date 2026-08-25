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
    PointerProperty,
    StringProperty,
)


class MB_TempData:
    current_image = None


MB_TEMP = MB_TempData()
MB_MSGBUS_OWNER = object()
MB_CORNER_TARGET_INSET = 0.01

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


def _corner_target_point(corners, corner_idx, inset=MB_CORNER_TARGET_INSET):
    tl, tr, br, bl = corners
    if corner_idx == 0:
        return (
            tl[0] + (tr[0] - tl[0]) * inset + (bl[0] - tl[0]) * inset,
            tl[1] + (tr[1] - tl[1]) * inset + (bl[1] - tl[1]) * inset,
        )
    if corner_idx == 1:
        return (
            tr[0] + (tl[0] - tr[0]) * inset + (br[0] - tr[0]) * inset,
            tr[1] + (tl[1] - tr[1]) * inset + (br[1] - tr[1]) * inset,
        )
    if corner_idx == 2:
        return (
            br[0] + (tr[0] - br[0]) * inset + (bl[0] - br[0]) * inset,
            br[1] + (tr[1] - br[1]) * inset + (bl[1] - br[1]) * inset,
        )
    return (
        bl[0] + (tl[0] - bl[0]) * inset + (br[0] - bl[0]) * inset,
        bl[1] + (tl[1] - bl[1]) * inset + (br[1] - bl[1]) * inset,
    )


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
        self.draw_custom_shape(self.shape)

    def test_select(self, context, co):
        left_top_corner = self.matrix_world @ Vector((-0.5, 0.5, 0, 1))
        right_bottom_corner = self.matrix_world @ Vector((0.5, -0.5, 0, 1))
        if (left_top_corner[0] <= co[0] <= right_bottom_corner[0]) and (right_bottom_corner[1] <= co[1] <= left_top_corner[1]):
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
            corner.color = corner.color_highlight = (1.0, 1.0, 1.0)
            corner.alpha = corner.alpha_highlight = 0.75
            corner.line_width = 3
            corner.use_draw_modal = True
            operator = corner.target_set_operator('mbcalib.adjust_overlay_corner')
            operator.corner_idx = corner_idx
            self.corners.append(corner)

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

    def draw_prepare(self, context):
        image = getattr(getattr(context, 'space_data', None), 'image', None) or MB_TEMP.current_image
        if image is None or not getattr(image, 'mb_sample_data', None) or not image.mb_sample_data.show_overlay:
            for gizmo in self.outlines + self.fills + self.corners:
                gizmo.hide = True
            return

        width, height = image.size
        if width <= 0 or height <= 0:
            for gizmo in self.outlines + self.fills + self.corners:
                gizmo.hide = True
            return

        corners = _get_overlay_corners(image.mb_sample_data, image)
        overlay_alpha = float(image.mb_sample_data.overlay_opacity)
        patch_size = max(1, int(image.mb_sample_data.patch_size))
        half_width = (patch_size * 0.5) / width
        half_height = (patch_size * 0.5) / height

        for row in range(4):
            v0 = row / 4.0
            v1 = (row + 1) / 4.0
            for col in range(6):
                u0 = col / 6.0
                u1 = (col + 1) / 6.0
                index = row * 6 + col
                center = _grid_point(corners, (u0 + u1) * 0.5, (v0 + v1) * 0.5)
                cell_points = (
                    (center[0] - half_width, center[1] - half_height),
                    (center[0] + half_width, center[1] - half_height),
                    (center[0] + half_width, center[1] + half_height),
                    (center[0] - half_width, center[1] + half_height),
                )

                self._set_box(self.outlines[index], context, cell_points)
                self._set_box(self.fills[index], context, cell_points)

                if len(image.mb_sample_data.samples) > index:
                    patch_color = image.mb_sample_data.samples[index].rgb
                    self.fills[index].color = self.fills[index].color_highlight = tuple(patch_color)
                else:
                    self.fills[index].color = self.fills[index].color_highlight = MB_MACBETH_REFERENCE_SRGB[index]
                self.fills[index].alpha = self.fills[index].alpha_highlight = overlay_alpha

        for corner_idx, corner_name in enumerate(('corner_tl', 'corner_tr', 'corner_br', 'corner_bl')):
            corner_gizmo = self.corners[corner_idx]
            corner_point = _corner_target_point(corners, corner_idx)
            self._set_cross(corner_gizmo, context, corner_point)



class MB_OT_AdjustOverlayCorner(bpy.types.Operator):
    bl_idname = 'mbcalib.adjust_overlay_corner'
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


@persistent
def MB_Messagebus_LoadPost(*args):
    MB_Messagebus_Init()
    MB_ImageEditor_Changed()


class MB_ColorSample(bpy.types.PropertyGroup):
    rgb: FloatVectorProperty(
        name="RGB",
        description="Sampled Macbeth patch value",
        size=3,
        subtype='COLOR',
        default=(0.0, 0.0, 0.0),
    )


class MB_ImageSampleData(bpy.types.PropertyGroup):
    samples: CollectionProperty(type=MB_ColorSample)
    has_preview: BoolProperty(name="Preview Available", default=False)
    is_saved: BoolProperty(name="Saved in Blend", default=False)
    patch_size: IntProperty(name="Patch Size", default=30, min=1, max=200)
    overlay_opacity: FloatProperty(name="Overlay Opacity", default=0.5, min=0.0, max=1.0, subtype='FACTOR')
    source_name: StringProperty(name="Source Name", default="")
    show_overlay: BoolProperty(name="Show Overlay", default=True)
    corner_tl: FloatVectorProperty(name="Top Left", size=2, default=(0.25, 0.82))
    corner_tr: FloatVectorProperty(name="Top Right", size=2, default=(0.75, 0.82))
    corner_br: FloatVectorProperty(name="Bottom Right", size=2, default=(0.75, 0.18))
    corner_bl: FloatVectorProperty(name="Bottom Left", size=2, default=(0.25, 0.18))


class MB_OT_SampleImageColors(bpy.types.Operator):
    bl_idname = "mbcalib.sample_image_colors"
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

        width, height = image.size
        if width <= 0 or height <= 0:
            self.report({'ERROR'}, "Selected image has no valid pixel resolution.")
            return {'CANCELLED'}

        pixels = np.asarray(image.pixels, dtype=np.float32).reshape((height, width, image.channels))
        overlay_corners = _get_overlay_corners(data, image)
        sample_size = max(1, min(int(data.patch_size), max(width, height)))

        for row in range(4):
            for col in range(6):
                u = (col + 0.5) / 6.0
                v = (row + 0.5) / 4.0
                center_x, center_y = _grid_point(overlay_corners, u, v)
                x = max(0, min(width - 1, int(round(center_x * width))))
                y = max(0, min(height - 1, int(round(center_y * height))))

                sample = data.samples.add()
                sample.rgb = sample_image_color(pixels, width, height, x, y, sample_size)

        data.has_preview = True
        data.is_saved = False
        self.report({'INFO'}, f"Sampled {len(data.samples)} values from '{image.name}'.")
        return {'FINISHED'}


class MB_OT_SaveSampleData(bpy.types.Operator):
    bl_idname = "mbcalib.save_sample_data"
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
        self.report({'INFO'}, f"Saved Macbeth values for '{image.name}'.")
        return {'FINISHED'}


class MB_OT_ClearSampleData(bpy.types.Operator):
    bl_idname = "mbcalib.clear_sample_data"
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
        data.has_preview = False
        data.is_saved = False
        data.source_name = ""
        self.report({'INFO'}, f"Cleared sample data for '{image.name}'.")
        return {'FINISHED'}


class MB_PT_ImageEditorSamplePanel(bpy.types.Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_label = 'Macbeth'
    bl_category = 'Macbeth'

    def draw(self, context):
        layout = self.layout
        image = getattr(context.space_data, 'image', None)
        if image is None:
            layout.label(text="Select an image")
            return

        data = image.mb_sample_data
        layout.label(text=f"Image: {image.name}")
        layout.prop(data, 'patch_size')
        row = layout.row(align=True)
        row.prop(data, 'show_overlay')
        row.prop(data, 'overlay_opacity', slider=True)

        box = layout.box()
        box.label(text='Overlay Corners')
        box.prop(data, 'corner_tl', text='Top Left')
        box.prop(data, 'corner_tr', text='Top Right')
        box.prop(data, 'corner_br', text='Bottom Right')
        box.prop(data, 'corner_bl', text='Bottom Left')

        row = layout.row(align=True)
        row.operator('mbcalib.sample_image_colors', text='Sample Chart')
        save_row = row.row(align=True)
        save_row.enabled = data.has_preview
        save_row.operator('mbcalib.save_sample_data', text='Save Values')

        if data.has_preview and len(data.samples) > 0:
            box = layout.box()
            box.label(text='Sampled Values')
            grid = box.grid_flow(columns=6, even_columns=True, even_rows=True)
            for i in range(min(len(data.samples), 24)):
                swatch = grid.row()
                swatch.label(text=str(i + 1))
                swatch.prop(data.samples[i], 'rgb', text='')

        saved_images = [img for img in bpy.data.images if getattr(img, 'mb_sample_data', None) and img.mb_sample_data.is_saved]
        if saved_images:
            box = layout.box()
            box.label(text='Saved Images')
            for img in saved_images:
                row = box.row()
                row.label(text=img.name)
                row.operator('mbcalib.clear_sample_data', text='Clear', icon='X').image_name = img.name


classes = (
    MB_ColorSample,
    MB_ImageSampleData,
    MB_GT_OverlaySquare,
    MB_GT_CornerCross,
    MB_GGT_ImageEditorOverlay,
    MB_OT_AdjustOverlayCorner,
    MB_OT_SampleImageColors,
    MB_OT_SaveSampleData,
    MB_OT_ClearSampleData,
    MB_PT_ImageEditorSamplePanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Image.mb_sample_data = PointerProperty(type=MB_ImageSampleData)
    bpy.types.Image.macbeth_sample_data = PointerProperty(type=MB_ImageSampleData)


def unregister():
    for prop_name in ('mb_sample_data', 'macbeth_sample_data'):
        try:
            delattr(bpy.types.Image, prop_name)
        except AttributeError:
            pass

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

import numpy as np
import bpy
import gpu
import textwrap
from . import core
from math import cos, sin
from mathutils import Vector
from time import perf_counter
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from gpu_extras.batch import batch_for_shader


MB_MSGBUS_OWNER = object()
MB_OVERLAY_RENDER_ALPHA_MAX = 0.999
MB_FLIP_BUTTON_SCALE = 48.0
MB_FLIP_BUTTON_LINE_WIDTH = 10
MB_CORNER_CROSS_OUTLINE_COLOR = (0.45, 0.32, 0.02)
MB_CORNER_CROSS_CORE_COLOR = (1.0, 1.0, 1.0)
MB_CORNER_CROSS_CORE_LENGTH = 25.0
MB_CORNER_CROSS_CORE_WIDTH = 3.0
MB_CORNER_CROSS_OUTLINE_WIDTH = 2.0
MB_CORNER_CROSS_SCALE = MB_CORNER_CROSS_CORE_LENGTH + (2.0 * MB_CORNER_CROSS_OUTLINE_WIDTH)
MB_CHART_ASPECT_RATIO = core.CHART_COLUMNS / core.CHART_ROWS
MB_CHART_AREA_FRACTION = 0.10
MB_INITIAL_PATCH_SIZE = 40
MB_INITIAL_CELL_SIZE = MB_INITIAL_PATCH_SIZE / core.CHART_PATCH_CELL_RATIO
MB_INITIAL_CHART_SIZE = (
    MB_INITIAL_CELL_SIZE * core.CHART_COLUMNS,
    MB_INITIAL_CELL_SIZE * core.CHART_ROWS,
)
MB_OVERLAY_INITIALIZED_KEY = 'macblend_overlay_initialized'
MB_PANORAMA_VIEW_SIZE = (1024, 768)
MB_PANORAMA_CHART_VIEW_FRACTION = 0.5
MB_PANORAMA_VIEW_MARKER = 'macblend_panorama_chart_view'
MB_PRECISION_DRAG_FACTOR = 0.1
MB_WHEEL_SCALE_FACTOR = 1.05
MB_ROTATE_RADIANS_PER_PIXEL = 0.01
MB_CHART_MIN_CORNER_ANGLE = 60.0
MB_CHART_MAX_CORNER_ANGLE = 120.0
MB_PANORAMA_FOV_WARNING_DEGREES = 120.0
MB_SANITY_ACTION_PROJECTION = 'PROJECTION'
MB_SANITY_ACTION_SAMPLE = 'SAMPLE'
MB_SANITY_ACTION_LEAVE_PROJECTION = 'LEAVE_PROJECTION'

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


def _preference_value(name, fallback):
    addon = bpy.context.preferences.addons.get(__package__)
    return getattr(addon.preferences, name, fallback) if addon else fallback


def _gizmo_display_scale():
    return float(_preference_value('gizmo_scale', 1.0))


def _set_drag_cursor(window):
    try:
        window.cursor_modal_set('HAND_CLOSED')
    except TypeError:
        window.cursor_modal_set('HAND')

# Logical Macbeth order is top-to-bottom, left-to-right, matching the chart layout
# used by the color-reference arrays.
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
_MB_SYNCING_SAMPLE_SELECTION = False
_MB_SYNCING_SAMPLE_VALUES = False
_MB_PANORAMA_PIXEL_CACHE = {}
_MB_UPDATING_PROJECTED_CORNERS = False
_MB_IMAGE_EDITOR_OVERLAY_HANDLER = None


def _grid_point(corners, u, v, homography=None):
    if homography is None:
        homography = core.build_chart_homography(corners)
    return core.map_chart_point(homography, u, v)


def _get_overlay_corners(data, image):
    return (
        tuple(data.corner_tl),
        tuple(data.corner_tr),
        tuple(data.corner_br),
        tuple(data.corner_bl),
    )


def _corner_target_point(corners, corner_idx):
    return corners[corner_idx]


def _flip_arrow_geometry(homography):
    first_patch_u, first_patch_v = core.chart_patch_uv(0)
    horizontal_v = 2.0 - first_patch_v
    vertical_u = -first_patch_u
    mapped = core.map_chart_points(
        homography,
        (
            (0.5, horizontal_v),
            (0.0, horizontal_v),
            (1.0, horizontal_v),
            (vertical_u, 0.5),
            (vertical_u, 1.0),
            (vertical_u, 0.0),
        ),
    )
    return (
        (mapped[0], mapped[1], mapped[2]),
        (mapped[3], mapped[4], mapped[5]),
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


def _draw_image_editor_overlay():
    context = bpy.context
    image = getattr(getattr(context, 'space_data', None), 'image', None)
    region = getattr(context, 'region', None)
    if image is None or region is None or not getattr(image, 'mb_sample_data', None):
        return

    data = image.mb_sample_data
    if not data.show_overlay:
        return

    width, height = image.size
    if width <= 0 or height <= 0:
        return

    try:
        corners = _get_overlay_corners(data, image)
        homography = core.build_chart_homography(corners)
        chart_size, patch_size = _chart_sample_geometry(corners, (width, height), data.patch_size)
    except ValueError:
        return

    samples_by_slot = {
        int(sample.patch_index): sample
        for sample in data.samples
        if 0 <= int(sample.patch_index) < len(MB_CCMASTER)
    }
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    overlay_alpha = min(float(data.overlay_opacity), MB_OVERLAY_RENDER_ALPHA_MAX)
    gpu.state.blend_set('ALPHA')
    try:
        for index in range(len(MB_CCMASTER)):
            footprint = core.chart_patch_footprint(
                homography,
                index,
                patch_size,
                chart_size=chart_size,
            )
            region_points = [_region_point(context, point) for point in footprint]
            if any(point is None for point in region_points):
                continue

            if index in samples_by_slot:
                fill_color = _linear_to_srgb(samples_by_slot[index].rgb)
            else:
                fill_color = MB_MACBETH_REFERENCE_SRGB[index]
            shader.uniform_float('color', (*fill_color, overlay_alpha))
            batch_for_shader(
                shader,
                'TRIS',
                {'pos': (region_points[0], region_points[1], region_points[2], region_points[0], region_points[2], region_points[3])},
            ).draw(shader)

            shader.uniform_float('color', (*MB_MACBETH_REFERENCE_SRGB[index], 1.0))
            batch_for_shader(
                shader,
                'LINES',
                {'pos': (region_points[0], region_points[1], region_points[1], region_points[2], region_points[2], region_points[3], region_points[3], region_points[0])},
            ).draw(shader)
    finally:
        gpu.state.blend_set('NONE')


def _add_image_editor_overlay_handler():
    global _MB_IMAGE_EDITOR_OVERLAY_HANDLER
    if _MB_IMAGE_EDITOR_OVERLAY_HANDLER is None:
        _MB_IMAGE_EDITOR_OVERLAY_HANDLER = bpy.types.SpaceImageEditor.draw_handler_add(
            _draw_image_editor_overlay,
            (),
            'WINDOW',
            'POST_PIXEL',
        )


def _remove_image_editor_overlay_handler():
    global _MB_IMAGE_EDITOR_OVERLAY_HANDLER
    if _MB_IMAGE_EDITOR_OVERLAY_HANDLER is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(_MB_IMAGE_EDITOR_OVERLAY_HANDLER, 'WINDOW')
        _MB_IMAGE_EDITOR_OVERLAY_HANDLER = None


def _fit_image_in_editor(context):
    area = getattr(context, 'area', None)
    if area is None or area.type != 'IMAGE_EDITOR':
        return

    window_region = next(
        (region for region in area.regions if region.type == 'WINDOW'),
        None,
    )
    if window_region is None:
        return

    try:
        with context.temp_override(
            area=area,
            region=window_region,
        ):
            bpy.ops.image.view_all(fit_view=True)
    except (RuntimeError, TypeError):
        pass


def _set_sample_patch_value(data, sample_idx, rgb_value):
    global _MB_SYNCING_SAMPLE_VALUES
    if 0 <= sample_idx < len(MB_SAMPLE_PROPERTY_NAMES):
        _MB_SYNCING_SAMPLE_VALUES = True
        try:
            setattr(data, MB_SAMPLE_PROPERTY_NAMES[sample_idx], tuple(rgb_value))
        finally:
            _MB_SYNCING_SAMPLE_VALUES = False


def _invalidate_calibrations_for_image(image):
    if image is None:
        return
    for scene in bpy.data.scenes:
        settings = getattr(scene, 'macblend_calibrator_settings', None)
        if settings is None:
            continue
        if settings.sample_source_image == image or settings.sample_target_image == image:
            settings.calculation_done = False
            settings.matrix_display_string = "Matrix not calculated."


def _sample_patch_value_changed(sample_idx):
    def update(data, _context):
        if _MB_SYNCING_SAMPLE_VALUES:
            return
        sample = next(
            (
                candidate
                for candidate in data.samples
                if int(getattr(candidate, 'patch_index', -1)) == sample_idx
            ),
            None,
        )
        if sample is None:
            return
        sample.rgb = tuple(getattr(data, MB_SAMPLE_PROPERTY_NAMES[sample_idx]))
        _invalidate_calibrations_for_image(getattr(data, 'id_data', None))
        _tag_image_editor_redraw()

    return update


def image_has_sample_values(image):
    data = getattr(image, 'mb_sample_data', None)
    if data is None or len(data.samples) != len(MB_CCMASTER):
        return False

    patch_indices = {int(getattr(sample, 'patch_index', -1)) for sample in data.samples}
    return patch_indices == set(range(len(MB_CCMASTER)))


def _image_index(image):
    if image is None:
        return -1
    return next((index for index, candidate in enumerate(bpy.data.images) if candidate == image), -1)


def _selected_sample_image(scene):
    ui_state = getattr(scene, 'macblend_sampling_ui', None)
    if ui_state is None:
        return None

    image = ui_state.selected_image
    if image is not None and image_has_sample_values(image):
        index = _image_index(image)
        if index != ui_state.active_image_index:
            global _MB_SYNCING_SAMPLE_SELECTION
            _MB_SYNCING_SAMPLE_SELECTION = True
            try:
                ui_state.active_image_index = index
            finally:
                _MB_SYNCING_SAMPLE_SELECTION = False
        return image

    if ui_state.active_image_index != -1 or image is not None:
        _set_selected_sample_image(scene, None)
    return None


def _peek_selected_sample_image(scene):
    ui_state = getattr(scene, 'macblend_sampling_ui', None)
    if ui_state is None:
        return None
    image = ui_state.selected_image
    return image if image is not None and image_has_sample_values(image) else None


def _set_selected_sample_image(scene, image):
    global _MB_SYNCING_SAMPLE_SELECTION
    ui_state = getattr(scene, 'macblend_sampling_ui', None)
    if ui_state is None:
        return

    index = _image_index(image) if image_has_sample_values(image) else -1
    _MB_SYNCING_SAMPLE_SELECTION = True
    try:
        ui_state.selected_image = image if index >= 0 else None
        ui_state.active_image_index = index
    finally:
        _MB_SYNCING_SAMPLE_SELECTION = False


def _active_sample_image_changed(ui_state, context):
    if _MB_SYNCING_SAMPLE_SELECTION:
        return

    index = int(ui_state.active_image_index)
    image = bpy.data.images[index] if 0 <= index < len(bpy.data.images) else None
    if not image_has_sample_values(image):
        image = None
    _set_selected_sample_image(context.scene, image)
    if image is None:
        _tag_image_editor_redraw()
        return

    space_data = getattr(context, 'space_data', None)
    if getattr(space_data, 'type', None) == 'IMAGE_EDITOR':
        space_data.image = image
    _tag_image_editor_redraw()


def _ccmaster_patch_uv(slot):
    row = slot // 6
    col = slot % 6
    u = (col + 0.5) / 6.0
    v = 1.0 - (row + 0.5) / 4.0
    return u, v


def _calculate_ccmaster_patch_centers(corners):
    homography = core.build_chart_homography(corners)
    centers = []
    for slot, patch_name in MB_CCMASTER:
        u, v = _ccmaster_patch_uv(slot)
        center_x, center_y = core.map_chart_point(homography, u, v)
        centers.append((slot, patch_name, center_x, center_y))
    return centers


def _chart_sample_geometry(corners, image_size, patch_size):
    chart_size = core.chart_rectified_size(corners, image_size)
    sample_size = core.effective_patch_size(patch_size, image_size)
    return chart_size, sample_size


def _store_patch_centers(data, centers):
    data.patch_centers.clear()
    for slot, patch_name, center_x, center_y in centers:
        patch = data.patch_centers.add()
        patch.slot = slot
        patch.patch_name = patch_name
        patch.x = center_x
        patch.y = center_y


def _replace_sample_data(data, centers, sampled_values):
    data.samples.clear()
    _reset_sample_patch_values(data)
    _store_patch_centers(data, centers)
    for slot, _patch_name, sample_rgb in sampled_values:
        sample = data.samples.add()
        sample.patch_index = slot
        sample.rgb = sample_rgb
        _set_sample_patch_value(data, slot, sample.rgb)
    _invalidate_calibrations_for_image(getattr(data, 'id_data', None))


def _load_image_pixel_buffer(image):
    width, height = image.size
    channels = int(image.channels)
    if channels not in {1, 2, 3, 4}:
        raise ValueError(f"Unsupported image channel count: {channels}.")
    if width <= 0 or height <= 0:
        raise ValueError("Image has no sampleable pixel area.")

    expected_values = int(width) * int(height) * channels
    actual_values = len(image.pixels)
    if actual_values != expected_values:
        raise ValueError(
            f"Image pixel buffer has {actual_values} values; expected {expected_values}."
        )

    byte_count = expected_values * np.dtype(np.float32).itemsize
    try:
        pixels = np.empty(expected_values, dtype=np.float32)
    except MemoryError as exc:
        required_mib = byte_count / (1024.0 * 1024.0)
        raise MemoryError(
            f"Could not allocate {required_mib:.1f} MiB for the image pixel buffer."
        ) from exc

    try:
        image.pixels.foreach_get(pixels)
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ValueError(f"Could not transfer Blender image pixels: {exc}") from exc
    return pixels.reshape((height, width, channels))


def _cached_panorama_pixel_buffer(image):
    width, height = image.size
    signature = (int(width), int(height), int(image.channels), len(image.pixels))
    cache_key = int(image.as_pointer())
    cached = _MB_PANORAMA_PIXEL_CACHE.get(cache_key)
    if cached is None or cached[0] != signature:
        cached = (signature, _load_image_pixel_buffer(image))
        _MB_PANORAMA_PIXEL_CACHE[cache_key] = cached
    return cached[1]


def _clear_panorama_pixel_cache(image=None):
    if image is None:
        _MB_PANORAMA_PIXEL_CACHE.clear()
    else:
        _MB_PANORAMA_PIXEL_CACHE.pop(int(image.as_pointer()), None)


def _panorama_projection(data):
    return {
        'heading': float(data.panorama_heading),
        'elevation': float(data.panorama_elevation),
        'roll': float(data.panorama_roll),
        'horizontal_fov': float(data.panorama_fov),
    }


def _panorama_source(image):
    data = getattr(image, 'mb_sample_data', None)
    return getattr(data, 'panorama_source_image', None) if data is not None else None


def _find_panorama_view(source_image):
    return next(
        (
            image
            for image in bpy.data.images
            if image.get(MB_PANORAMA_VIEW_MARKER) and _panorama_source(image) == source_image
        ),
        None,
    )


def _refresh_panorama_view(source_image, view_image, *, current_pixels=False):
    if current_pixels:
        _clear_panorama_pixel_cache(source_image)
    source_pixels = _cached_panorama_pixel_buffer(source_image)
    view_pixels = core.render_rectilinear_view(
        source_pixels,
        MB_PANORAMA_VIEW_SIZE,
        **_panorama_projection(source_image.mb_sample_data),
    )
    rgba_pixels = np.empty((*view_pixels.shape[:2], 4), dtype=np.float32)
    rgba_pixels[..., :3] = view_pixels
    rgba_pixels[..., 3] = 1.0
    view_image.pixels.foreach_set(rgba_pixels.ravel())
    view_image.update()


def _panorama_projection_changed(data, context):
    if data.projection_mode != 'EQUIRECTANGULAR':
        return
    source_image = getattr(data, 'id_data', None)
    view_image = _find_panorama_view(source_image) if source_image is not None else None
    if view_image is None:
        return
    try:
        _refresh_panorama_view(source_image, view_image, current_pixels=True)
    except (ValueError, MemoryError, RuntimeError) as exc:
        print(f'[MacBlend] Could not refresh panorama chart view: {exc}')


def _panorama_angles_from_overlay(corners, horizontal_fov, aspect_ratio):
    corner_array = np.asarray(corners, dtype=np.float64)
    longitude_angles = corner_array[:, 0] * (2.0 * np.pi)
    mean_sin = float(np.mean(np.sin(longitude_angles)))
    mean_cos = float(np.mean(np.cos(longitude_angles)))
    if np.hypot(mean_sin, mean_cos) < 1e-8:
        longitude_reference = float(np.mean(corner_array[:, 0]))
    else:
        longitude_reference = float(np.mod(np.arctan2(mean_sin, mean_cos) / (2.0 * np.pi), 1.0))

    unwrapped_corners = corner_array.copy()
    unwrapped_corners[:, 0] = longitude_reference + np.mod(
        corner_array[:, 0] - longitude_reference + 0.5,
        1.0,
    ) - 0.5
    homography = core.build_chart_homography(unwrapped_corners)
    middle_left = core.map_chart_point(homography, 0.0, 0.5)
    middle_right = core.map_chart_point(homography, 1.0, 0.5)
    middle_points = np.asarray((middle_left, middle_right), dtype=np.float64)
    longitude = (middle_points[:, 0] - 0.5) * (2.0 * np.pi)
    latitude = (middle_points[:, 1] - 0.5) * np.pi
    cos_latitude = np.cos(latitude)
    directions = np.stack(
        (
            np.sin(longitude) * cos_latitude,
            np.sin(latitude),
            np.cos(longitude) * cos_latitude,
        ),
        axis=-1,
    )
    forward = directions[0] + directions[1]
    forward_length = float(np.linalg.norm(forward))
    if forward_length <= 1e-8:
        raise ValueError("Chart middle spans opposing panorama directions.")
    forward /= forward_length
    heading = float(np.arctan2(forward[0], forward[2]))
    elevation = float(np.arcsin(np.clip(forward[1], -1.0, 1.0)))

    middle_u, middle_v = core.equirectangular_to_rectilinear_uv(
        np.mod((middle_left[0], middle_right[0]), 1.0),
        (middle_left[1], middle_right[1]),
        heading=heading,
        elevation=elevation,
        roll=0.0,
        horizontal_fov=horizontal_fov,
        aspect_ratio=aspect_ratio,
    )
    roll = float(np.arctan2(
        (middle_v[1] - middle_v[0]) / aspect_ratio,
        middle_u[1] - middle_u[0],
    ))
    return heading, elevation, roll


def _panorama_fov_for_chart(corners, heading, elevation, roll, aspect_ratio):
    reference_fov = np.deg2rad(60.0)
    corner_u = np.mod(
        np.asarray([corner[0] for corner in corners], dtype=np.float64),
        1.0,
    )
    corner_v = np.asarray([corner[1] for corner in corners], dtype=np.float64)
    view_u, view_v = core.equirectangular_to_rectilinear_uv(
        corner_u,
        corner_v,
        heading=heading,
        elevation=elevation,
        roll=roll,
        horizontal_fov=reference_fov,
        aspect_ratio=aspect_ratio,
    )
    required_scale = max(float(np.ptp(view_u)), float(np.ptp(view_v)))
    return float(2.0 * np.arctan(
        np.tan(reference_fov * 0.5)
        * required_scale
        / MB_PANORAMA_CHART_VIEW_FRACTION
    ))


def _chart_sanity_check_findings(image, data, action):
    corners = _get_overlay_corners(data, image)
    homography = core.build_chart_homography(corners)
    findings = []
    if core.chart_signed_area(corners) >= 0.0:
        findings.append(
            'Patch order is reversed. Reset Chart, then use Flip Horizontal and/or '
            'Flip Vertical to match the physical chart orientation.'
        )

    corner_angles = core.chart_corner_angles(corners, image.size)
    smallest_angle = float(np.min(corner_angles))
    largest_angle = float(np.max(corner_angles))
    if smallest_angle < MB_CHART_MIN_CORNER_ANGLE or largest_angle > MB_CHART_MAX_CORNER_ANGLE:
        findings.append(
            'Your chart appears to be strongly distorted - samples may be inaccurate. Avoid extreme angles while shooting as they can introduce unwanted glare and Fresnel reflections.'
        )

    if action == MB_SANITY_ACTION_PROJECTION:
        angular_width = core.panorama_chart_angular_width(corners)
        angular_width_degrees = float(np.rad2deg(angular_width))
        illustration_width = core.angular_size_at_distance(angular_width, 2.0)
        illustration = (
            f' If the chart is at 2 m from the camera, this suggests it is '
            f'{illustration_width:.2f} m wide, which is kind of big for a ColorChecker.'
            if illustration_width is not None
            else ' The implied chart width at 2 m is unavailable at this extreme angle.'
        )
        try:
            heading, elevation, roll = _panorama_angles_from_overlay(
                corners,
                float(data.panorama_fov),
                MB_PANORAMA_VIEW_SIZE[0] / MB_PANORAMA_VIEW_SIZE[1],
            )
            required_fov = _panorama_fov_for_chart(
                corners,
                heading,
                elevation,
                roll,
                MB_PANORAMA_VIEW_SIZE[0] / MB_PANORAMA_VIEW_SIZE[1],
            )
        except ValueError:
            raise ValueError(
                f'The alignment spans {angular_width_degrees:.0f} degrees of the panorama and cannot '
                'be represented by one rectilinear chart view. Reset Chart and align tightly around '
                'one physical ColorChecker.'
            )
        required_fov_degrees = float(np.rad2deg(required_fov))
        if required_fov_degrees > MB_PANORAMA_FOV_WARNING_DEGREES:
            findings.append(
                f'The chart spans {angular_width_degrees:.0f} degrees and needs a {required_fov_degrees:.0f} '
                f'degree rectilinear view, which can be strongly distorted.{illustration} Align tightly '
                'around one physical ColorChecker for more reliable results.'
            )

    if action == MB_SANITY_ACTION_SAMPLE:
        chart_size, patch_size = _chart_sample_geometry(corners, image.size, data.patch_size)
        out_of_bounds = 0
        for slot in range(len(MB_CCMASTER)):
            footprint = core.chart_patch_footprint(homography, slot, patch_size, chart_size=chart_size)
            if np.any(footprint < 0.0) or np.any(footprint > 1.0):
                out_of_bounds += 1
        if out_of_bounds:
            findings.append(
                f'{out_of_bounds} sample regions extend outside the image and will be clipped. Reduce '
                'Patch Size or realign the chart before sampling.'
            )
    return findings


def _invoke_sanity_checks(operator, context, image, data, action):
    try:
        findings = _chart_sanity_check_findings(image, data, action)
    except ValueError as exc:
        operator.report({'ERROR'}, f'Chart alignment needs correction: {exc}')
        return {'CANCELLED'}
    if not findings:
        return operator.execute(context)
    bpy.ops.macblend.confirm_sampling_sanity_checks(
        'INVOKE_DEFAULT',
        action=action,
        findings='\n'.join(findings),
    )
    return {'FINISHED'}


def _store_projected_corners_on_source(source_data, projected_corners, view_size):
    global _MB_UPDATING_PROJECTED_CORNERS
    width, height = view_size
    view_u = np.asarray([corner[0] for corner in projected_corners], dtype=np.float64)
    view_v = np.asarray([corner[1] for corner in projected_corners], dtype=np.float64)
    source_u, source_v = core.rectilinear_to_equirectangular_uv(
        view_u,
        view_v,
        aspect_ratio=width / height,
        **_panorama_projection(source_data),
    )
    source_corners = tuple(
        (float(u), float(v))
        for u, v in zip(source_u, source_v)
    )

    _MB_UPDATING_PROJECTED_CORNERS = True
    try:
        for property_name, corner in zip(
            ('corner_tl', 'corner_tr', 'corner_br', 'corner_bl'),
            source_corners,
        ):
            setattr(source_data, property_name, corner)
    finally:
        _MB_UPDATING_PROJECTED_CORNERS = False


def _store_source_corners_on_projected_view(source_data, view_data, view_size):
    width, height = view_size
    source_corners = _get_overlay_corners(source_data, source_data.id_data)
    source_u = np.asarray([corner[0] for corner in source_corners], dtype=np.float64)
    source_v = np.asarray([corner[1] for corner in source_corners], dtype=np.float64)
    view_u, view_v = core.equirectangular_to_rectilinear_uv(
        source_u,
        source_v,
        aspect_ratio=width / height,
        **_panorama_projection(source_data),
    )
    for property_name, u, v in zip(
        ('corner_tl', 'corner_tr', 'corner_br', 'corner_bl'),
        view_u,
        view_v,
    ):
        setattr(view_data, property_name, (float(u), float(v)))


def _overlay_corner_changed(data, context):
    if _MB_UPDATING_PROJECTED_CORNERS or getattr(data, 'panorama_source_image', None) is not None:
        return
    source_image = getattr(data, 'id_data', None)
    if source_image is not None:
        _clear_panorama_pixel_cache(source_image)
    data.projection_mode = 'FLAT'
    data.panorama_heading = 0.0
    data.panorama_elevation = 0.0
    data.panorama_roll = 0.0
    data.panorama_fov = np.deg2rad(60.0)


def _center_overlay_corners(
    data,
    image_width,
    image_height,
    center=(0.5, 0.5),
    view_size=(1.0, 1.0),
    chart_aspect_ratio=MB_CHART_ASPECT_RATIO,
    area_fraction=MB_CHART_AREA_FRACTION,
):
    if image_width <= 0 or image_height <= 0:
        return

    view_width_px = abs(float(view_size[0])) * float(image_width)
    view_height_px = abs(float(view_size[1])) * float(image_height)
    if view_width_px <= 0 or view_height_px <= 0:
        return

    target_area = float(area_fraction) * view_width_px * view_height_px
    ratio = max(float(chart_aspect_ratio), 1e-6)

    chart_width_px = (target_area * ratio) ** 0.5
    chart_height_px = chart_width_px / ratio

    fit_scale = min(view_width_px / max(chart_width_px, 1e-6), view_height_px / max(chart_height_px, 1e-6), 1.0)
    chart_width_px *= fit_scale
    chart_height_px *= fit_scale

    width_norm = chart_width_px / float(image_width)
    height_norm = chart_height_px / float(image_height)

    center_x, center_y = center
    half_width = width_norm * 0.5
    half_height = height_norm * 0.5

    data.corner_tl = (center_x - half_width, center_y + half_height)
    data.corner_tr = (center_x + half_width, center_y + half_height)
    data.corner_br = (center_x + half_width, center_y - half_height)
    data.corner_bl = (center_x - half_width, center_y - half_height)
    data.patch_size = core.chart_patch_size((chart_width_px, chart_height_px))


def _initialize_overlay(data, image, patch_size=MB_INITIAL_PATCH_SIZE):
    width, height = image.size
    if width <= 0 or height <= 0:
        return

    cell_size = float(patch_size) / core.CHART_PATCH_CELL_RATIO
    chart_width = cell_size * core.CHART_COLUMNS
    chart_height = cell_size * core.CHART_ROWS
    fit_scale = min(1.0, width / chart_width, height / chart_height)
    chart_width *= fit_scale
    chart_height *= fit_scale
    data[MB_OVERLAY_INITIALIZED_KEY] = True
    _center_overlay_corners(
        data,
        width,
        height,
        view_size=(chart_width / width, chart_height / height),
        area_fraction=1.0,
    )


def _image_editor_view_geometry(context):
    area = getattr(context, 'area', None)
    if area is None or area.type != 'IMAGE_EDITOR':
        return None

    window_region = next(
        (region for region in area.regions if region.type == 'WINDOW'),
        None,
    )
    if window_region is None:
        return None

    view_min = tuple(window_region.view2d.region_to_view(0, 0))
    view_max = tuple(window_region.view2d.region_to_view(
        window_region.width,
        window_region.height,
    ))
    view_size = (
        abs(view_max[0] - view_min[0]),
        abs(view_max[1] - view_min[1]),
    )
    if view_size[0] <= 0 or view_size[1] <= 0:
        return None

    center = (
        (view_min[0] + view_max[0]) * 0.5,
        (view_min[1] + view_max[1]) * 0.5,
    )
    return center, view_size


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


def _get_patch_size(data):
    return int(data.get(
        'patch_size',
        _preference_value('default_patch_size', MB_INITIAL_PATCH_SIZE),
    ))


def _set_patch_size(data, value):
    data['patch_size'] = int(value)


def _get_overlay_opacity(data):
    return float(data.get(
        'overlay_opacity',
        _preference_value('default_overlay_opacity', 0.5),
    ))


def _set_overlay_opacity(data, value):
    data['overlay_opacity'] = float(value)


def _ensure_overlay_initialized(data, image):
    if data.get(MB_OVERLAY_INITIALIZED_KEY, False):
        return

    corner_names = ('corner_tl', 'corner_tr', 'corner_br', 'corner_bl')
    if all(data.get(name) is not None for name in corner_names):
        data[MB_OVERLAY_INITIALIZED_KEY] = True
    elif image is not None and getattr(data, 'panorama_source_image', None) is None:
        _initialize_overlay(data, image, data.patch_size)
    else:
        data[MB_OVERLAY_INITIALIZED_KEY] = True


def _get_show_overlay(data):
    stored_value = data.get('show_overlay')
    if stored_value is not None:
        return bool(stored_value)
    return False


def _set_show_overlay(data, value):
    if value and not data.get(MB_OVERLAY_INITIALIZED_KEY, False):
        _ensure_overlay_initialized(data, getattr(data, 'id_data', None))
    data['show_overlay'] = bool(value)


@persistent
def MB_Messagebus_Init(*args):
    _add_image_editor_overlay_handler()
    bpy.msgbus.clear_by_owner(MB_MSGBUS_OWNER)
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.SpaceImageEditor, 'image'),
        owner=MB_MSGBUS_OWNER,
        args=(),
        notify=MB_ImageEditor_Changed,
    )
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.ColorManagedInputColorspaceSettings, 'name'),
        owner=MB_MSGBUS_OWNER,
        args=(),
        notify=MB_ImageColorspace_Changed,
    )


def MB_ImageEditor_Changed():
    scene = getattr(bpy.context, 'scene', None)
    space_data = getattr(bpy.context, 'space_data', None)
    if scene is not None and getattr(space_data, 'type', None) == 'IMAGE_EDITOR':
        _set_selected_sample_image(scene, getattr(space_data, 'image', None))
    _tag_image_editor_redraw()


def MB_ImageColorspace_Changed():
    projection_views = {}
    for image in bpy.data.images:
        source_image = _panorama_source(image)
        if source_image is not None:
            source_key = int(source_image.as_pointer())
            projection_views.setdefault(source_key, (source_image, []))[1].append(image)

    for source_image, view_images in projection_views.values():
        _clear_panorama_pixel_cache(source_image)
        for view_image in view_images:
            try:
                _refresh_panorama_view(source_image, view_image)
            except (ValueError, MemoryError, RuntimeError) as exc:
                print(f'[MacBlend] Could not refresh panorama chart view after color-space change: {exc}')
    _tag_image_editor_redraw()


def MB_Messagebus_Remove():
    bpy.msgbus.clear_by_owner(MB_MSGBUS_OWNER)
    _remove_image_editor_overlay_handler()
    _clear_panorama_pixel_cache()


def _cross_triangles(length, width):
    half_length = length / (2.0 * MB_CORNER_CROSS_SCALE)
    half_width = width / (2.0 * MB_CORNER_CROSS_SCALE)
    return (
        (-half_length, -half_width), (half_length, -half_width), (half_length, half_width),
        (-half_length, -half_width), (half_length, half_width), (-half_length, half_width),
        (-half_width, half_width), (half_width, half_width), (half_width, half_length),
        (-half_width, half_width), (half_width, half_length), (-half_width, half_length),
        (-half_width, -half_length), (half_width, -half_length), (half_width, -half_width),
        (-half_width, -half_length), (half_width, -half_width), (-half_width, -half_width),
    )


class MB_GT_CornerCross(bpy.types.Gizmo):
    def setup(self):
        self.outline_shape = self.new_custom_shape(
            'TRIS',
            _cross_triangles(
                MB_CORNER_CROSS_CORE_LENGTH + (2.0 * MB_CORNER_CROSS_OUTLINE_WIDTH),
                MB_CORNER_CROSS_CORE_WIDTH + (2.0 * MB_CORNER_CROSS_OUTLINE_WIDTH),
            ),
        )
        self.foreground_shape = self.new_custom_shape(
            'TRIS',
            _cross_triangles(MB_CORNER_CROSS_CORE_LENGTH, MB_CORNER_CROSS_CORE_WIDTH),
        )

    def draw(self, context):
        self.color = MB_CORNER_CROSS_OUTLINE_COLOR
        self.alpha = 1.0
        self.draw_custom_shape(self.outline_shape)

        self.color = MB_CORNER_CROSS_CORE_COLOR
        self.alpha = 1.0
        self.draw_custom_shape(self.foreground_shape)

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
        image = getattr(getattr(context, 'space_data', None), 'image', None)
        return image is not None and getattr(image, 'mb_sample_data', None) is not None and image.mb_sample_data.show_overlay

    def setup(self, context):
        self.corners = []
        self.flip_buttons = []

        for corner_idx in range(4):
            corner = self.gizmos.new('MB_GT_CornerCross')
            corner.color = (0.75, 0.75, 0.75)
            corner.color_highlight = (0.35, 0.35, 0.35)
            corner.alpha = 0.9
            corner.alpha_highlight = 1.0
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

    def _set_cross(self, gizmo, context, point):
        region_point = _region_point(context, point)
        if region_point is None:
            gizmo.hide = True
            return

        gizmo.hide = False
        gizmo.matrix_basis.identity()
        scale = MB_CORNER_CROSS_SCALE * _gizmo_display_scale()
        gizmo.matrix_basis[0][0] = scale
        gizmo.matrix_basis[1][1] = scale
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
        scale = MB_FLIP_BUTTON_SCALE * _gizmo_display_scale()

        gizmo.hide = False
        gizmo.matrix_basis.identity()
        gizmo.matrix_basis[0][0] = x_axis[0] * scale
        gizmo.matrix_basis[1][0] = x_axis[1] * scale
        gizmo.matrix_basis[0][1] = y_axis[0] * scale
        gizmo.matrix_basis[1][1] = y_axis[1] * scale
        gizmo.matrix_basis[0][3] = region_point[0]
        gizmo.matrix_basis[1][3] = region_point[1]

    def draw_prepare(self, context):
        if not hasattr(self, 'flip_buttons'):
            self.flip_buttons = []
        self._ensure_flip_buttons()

        image = getattr(getattr(context, 'space_data', None), 'image', None)
        if image is None or not getattr(image, 'mb_sample_data', None) or not image.mb_sample_data.show_overlay:
            for gizmo in self.corners + self.flip_buttons:
                gizmo.hide = True
            return

        width, height = image.size
        if width <= 0 or height <= 0:
            for gizmo in self.corners + self.flip_buttons:
                gizmo.hide = True
            return

        corners = _get_overlay_corners(image.mb_sample_data, image)
        try:
            homography = core.build_chart_homography(corners)
        except ValueError:
            for gizmo in self.flip_buttons:
                gizmo.hide = True
            for corner_idx, corner_gizmo in enumerate(self.corners):
                self._set_cross(corner_gizmo, context, corners[corner_idx])
            return

        for corner_idx in range(4):
            corner_gizmo = self.corners[corner_idx]
            corner_point = _corner_target_point(corners, corner_idx)
            self._set_cross(corner_gizmo, context, corner_point)

        horizontal_arrow, vertical_arrow = _flip_arrow_geometry(homography)
        self._set_flip_button(self.flip_buttons[0], context, *horizontal_arrow)
        self._set_flip_button(self.flip_buttons[1], context, *vertical_arrow)



class MB_OT_AdjustOverlayCorner(bpy.types.Operator):
    bl_idname = 'macblend.adjust_overlay_corner'
    bl_label = 'Adjust Overlay Corner'
    bl_options = {'GRAB_CURSOR', 'BLOCKING', 'UNDO'}

    corner_idx: IntProperty(default=0, options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        corner_labels = ('Top Left', 'Top Right', 'Bottom Right', 'Bottom Left')
        corner_idx = int(getattr(properties, 'corner_idx', -1))
        if 0 <= corner_idx < len(corner_labels):
            return (
                f"Adjust the {corner_labels[corner_idx]} corner of the Macbeth chart overlay; "
                "hold Ctrl to move the entire chart, Ctrl+Alt to rotate around this corner, "
                "Shift for precision, or scroll to scale"
            )
        return cls.bl_label

    def invoke(self, context, event):
        image = getattr(getattr(context, 'space_data', None), 'image', None)
        if image is None or not getattr(image, 'mb_sample_data', None):
            return {'CANCELLED'}

        self.image = image
        self.data = image.mb_sample_data
        self.start_corners = {
            name: tuple(getattr(self.data, name))
            for name in ('corner_tl', 'corner_tr', 'corner_br', 'corner_bl')
        }
        self.previous_mouse_coords = tuple(
            context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        )
        self.previous_mouse_region_x = event.mouse_region_x

        _set_drag_cursor(context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        corner_name = ('corner_tl', 'corner_tr', 'corner_br', 'corner_bl')[self.corner_idx]

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            for name, start_value in self.start_corners.items():
                setattr(self.data, name, start_value)
            context.window.cursor_modal_restore()
            _tag_image_editor_redraw()
            return {'CANCELLED'}

        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            scale_factor = MB_WHEEL_SCALE_FACTOR
            if event.type == 'WHEELDOWNMOUSE':
                scale_factor = 1.0 / scale_factor

            pivot = tuple(getattr(self.data, corner_name))
            for name in self.start_corners:
                if name == corner_name:
                    continue
                current_value = tuple(getattr(self.data, name))
                setattr(
                    self.data,
                    name,
                    (
                        pivot[0] + (current_value[0] - pivot[0]) * scale_factor,
                        pivot[1] + (current_value[1] - pivot[1]) * scale_factor,
                    ),
                )
            _tag_image_editor_redraw()

        if event.type == 'MOUSEMOVE':
            current_mouse_coords = tuple(context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y))
            delta = (
                current_mouse_coords[0] - self.previous_mouse_coords[0],
                current_mouse_coords[1] - self.previous_mouse_coords[1],
            )
            horizontal_mouse_delta = event.mouse_region_x - self.previous_mouse_region_x
            self.previous_mouse_coords = current_mouse_coords
            self.previous_mouse_region_x = event.mouse_region_x
            if event.shift:
                delta = tuple(component * MB_PRECISION_DRAG_FACTOR for component in delta)
                horizontal_mouse_delta *= MB_PRECISION_DRAG_FACTOR

            if event.ctrl and event.alt:
                angle = horizontal_mouse_delta * MB_ROTATE_RADIANS_PER_PIXEL
                angle_cos = cos(angle)
                angle_sin = sin(angle)
                pivot = tuple(getattr(self.data, corner_name))
                image_width, image_height = self.image.size
                for name in self.start_corners:
                    if name == corner_name:
                        continue
                    current_value = tuple(getattr(self.data, name))
                    offset_x = (current_value[0] - pivot[0]) * image_width
                    offset_y = (current_value[1] - pivot[1]) * image_height
                    setattr(
                        self.data,
                        name,
                        (
                            pivot[0] + (offset_x * angle_cos - offset_y * angle_sin) / image_width,
                            pivot[1] + (offset_x * angle_sin + offset_y * angle_cos) / image_height,
                        ),
                    )
            elif event.ctrl:
                for name in self.start_corners:
                    current_value = tuple(getattr(self.data, name))
                    setattr(
                        self.data,
                        name,
                        (current_value[0] + delta[0], current_value[1] + delta[1]),
                    )
            else:
                current_value = tuple(getattr(self.data, corner_name))
                setattr(
                    self.data,
                    corner_name,
                    (current_value[0] + delta[0], current_value[1] + delta[1]),
                )
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
        image = getattr(getattr(context, 'space_data', None), 'image', None)
        if image is None or not getattr(image, 'mb_sample_data', None):
            self.report({'ERROR'}, 'No image with Macbeth overlay data available.')
            return {'CANCELLED'}

        data = image.mb_sample_data
        corner_tl = tuple(data.corner_tl)
        corner_tr = tuple(data.corner_tr)
        corner_br = tuple(data.corner_br)
        corner_bl = tuple(data.corner_bl)
        data.corner_tl = corner_tr
        data.corner_tr = corner_tl
        data.corner_br = corner_bl
        data.corner_bl = corner_br

        _tag_image_editor_redraw()
        return {'FINISHED'}


class MB_OT_FlipOverlayVertical(bpy.types.Operator):
    bl_idname = 'macblend.flip_overlay_vertical'
    bl_label = 'Flip Overlay Vertical'
    bl_description = 'Mirror the Macbeth patch orientation vertically inside the aligned corners'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        image = getattr(getattr(context, 'space_data', None), 'image', None)
        if image is None or not getattr(image, 'mb_sample_data', None):
            self.report({'ERROR'}, 'No image with Macbeth overlay data available.')
            return {'CANCELLED'}

        data = image.mb_sample_data
        corner_tl = tuple(data.corner_tl)
        corner_tr = tuple(data.corner_tr)
        corner_br = tuple(data.corner_br)
        corner_bl = tuple(data.corner_bl)
        data.corner_tl = corner_bl
        data.corner_tr = corner_br
        data.corner_br = corner_tr
        data.corner_bl = corner_tl

        _tag_image_editor_redraw()
        return {'FINISHED'}


class MB_OT_CenterOverlayChart(bpy.types.Operator):
    bl_idname = 'macblend.center_overlay_chart'
    bl_label = 'Center Overlay'
    bl_description = 'Center a Macbeth chart in the visible Image Editor view and fit Patch Size to its cells'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        image = getattr(getattr(context, 'space_data', None), 'image', None)
        if image is None or not getattr(image, 'mb_sample_data', None):
            self.report({'ERROR'}, 'No image with Macbeth overlay data available.')
            return {'CANCELLED'}

        width, height = image.size
        if width <= 0 or height <= 0:
            self.report({'ERROR'}, 'Selected image has no valid pixel resolution.')
            return {'CANCELLED'}

        view_geometry = _image_editor_view_geometry(context)
        if view_geometry is None:
            self.report({'ERROR'}, 'Could not determine the Image Editor viewer bounds.')
            return {'CANCELLED'}

        viewer_center, view_size = view_geometry
        _center_overlay_corners(
            image.mb_sample_data,
            width,
            height,
            center=viewer_center,
            view_size=view_size,
        )
        image.mb_sample_data[MB_OVERLAY_INITIALIZED_KEY] = True
        _tag_image_editor_redraw()
        self.report(
            {'INFO'},
            f'Centered overlay with {image.mb_sample_data.patch_size}px patches.',
        )
        return {'FINISHED'}


class MB_OT_ResetOverlayChart(bpy.types.Operator):
    bl_idname = 'macblend.reset_overlay_chart'
    bl_label = 'Reset Chart'
    bl_description = 'Reset chart position and Patch Size to the initial overlay layout'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        image = getattr(getattr(context, 'space_data', None), 'image', None)
        if image is None or not getattr(image, 'mb_sample_data', None):
            self.report({'ERROR'}, 'No image with Macbeth overlay data available.')
            return {'CANCELLED'}

        width, height = image.size
        if width <= 0 or height <= 0:
            self.report({'ERROR'}, 'Selected image has no valid pixel resolution.')
            return {'CANCELLED'}

        _initialize_overlay(
            image.mb_sample_data,
            image,
            _preference_value('default_patch_size', MB_INITIAL_PATCH_SIZE),
        )
        _tag_image_editor_redraw()
        self.report(
            {'INFO'},
            f'Reset chart with {image.mb_sample_data.patch_size}px patches.',
        )
        return {'FINISHED'}


class MB_OT_ConfirmSamplingSanityChecks(bpy.types.Operator):
    bl_idname = 'macblend.confirm_sampling_sanity_checks'
    bl_label = 'Check Chart Alignment'

    action: EnumProperty(
        options={'HIDDEN'},
        items=(
            (MB_SANITY_ACTION_PROJECTION, 'Lat-Long Projection', ''),
            (MB_SANITY_ACTION_SAMPLE, 'Sample Chart', ''),
            (MB_SANITY_ACTION_LEAVE_PROJECTION, 'Leave Lat-Long Projection', ''),
        ),
    )
    findings: StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            width=520,
            title='Check Chart Alignment',
            confirm_text='I Understand, Continue Anyway',
        )

    def draw(self, context):
        layout = self.layout
        layout.label(text='Chart alignment needs attention', icon='ERROR')
        findings = self.findings.splitlines()
        if findings:
            layout.separator(factor=0.35)
        for index, finding in enumerate(findings):
            finding_column = layout.column(align=True)
            finding_column.scale_y = 0.9
            for line in textwrap.wrap(
                finding,
                width=74,
                break_long_words=False,
                break_on_hyphens=False,
            ):
                finding_column.label(text=line)
            if index < len(findings) - 1:
                layout.separator(factor=0.8)
        layout.separator(factor=0.8)
        tip_column = layout.column(align=True)
        tip_column.label(text='Tip', icon='LIGHT')
        for line in textwrap.wrap(
            'For a quick alignment, move the image until the ColorChecker is centered in the '
            'Image Editor, zoom until it fills about one third of the panel, then click Center Overlay.',
            width=74,
            break_long_words=False,
            break_on_hyphens=False,
        ):
            tip_column.label(text=line)

    def execute(self, context):
        if self.action in {MB_SANITY_ACTION_PROJECTION, MB_SANITY_ACTION_LEAVE_PROJECTION}:
            return bpy.ops.macblend.open_panorama_chart_view(
                'EXEC_DEFAULT',
                skip_sanity_checks=True,
            )
        if self.action == MB_SANITY_ACTION_SAMPLE:
            return bpy.ops.macblend.sample_image_colors(
                'EXEC_DEFAULT',
                skip_sanity_checks=True,
            )
        self.report({'ERROR'}, 'Unknown chart alignment action.')
        return {'CANCELLED'}


class MB_OT_OpenPanoramaChartView(bpy.types.Operator):
    bl_idname = 'macblend.open_panorama_chart_view'
    bl_label = 'Toggle Lat-Long Chart View'
    bl_description = 'Enter or exit the undistorted lat-long chart view'
    bl_options = {'REGISTER'}

    skip_sanity_checks: BoolProperty(options={'HIDDEN'}, default=False)

    def invoke(self, context, event):
        if self.skip_sanity_checks:
            return self.execute(context)
        active_image = getattr(getattr(context, 'space_data', None), 'image', None)
        source_image = _panorama_source(active_image)
        if source_image is not None:
            return _invoke_sanity_checks(
                self,
                context,
                active_image,
                active_image.mb_sample_data,
                MB_SANITY_ACTION_LEAVE_PROJECTION,
            )
        if active_image is None or not getattr(active_image, 'mb_sample_data', None):
            return self.execute(context)
        _ensure_overlay_initialized(active_image.mb_sample_data, active_image)
        return _invoke_sanity_checks(
            self,
            context,
            active_image,
            active_image.mb_sample_data,
            MB_SANITY_ACTION_PROJECTION,
        )

    def execute(self, context):
        active_image = getattr(getattr(context, 'space_data', None), 'image', None)
        source_image = _panorama_source(active_image)
        if source_image is not None:
            context.space_data.image = source_image
            _fit_image_in_editor(context)
            _clear_panorama_pixel_cache(source_image)
            bpy.data.images.remove(active_image)
            _tag_image_editor_redraw()
            self.report({'INFO'}, f"Returned to lat-long image '{source_image.name}'.")
            return {'FINISHED'}

        source_image = active_image
        if source_image is None or not getattr(source_image, 'mb_sample_data', None):
            self.report({'ERROR'}, 'No panorama image is selected.')
            return {'CANCELLED'}

        source_data = source_image.mb_sample_data
        _ensure_overlay_initialized(source_data, source_image)
        if source_data.projection_mode != 'EQUIRECTANGULAR':
            corners = _get_overlay_corners(source_data, source_image)
            aspect_ratio = MB_PANORAMA_VIEW_SIZE[0] / MB_PANORAMA_VIEW_SIZE[1]
            try:
                heading, elevation, roll = _panorama_angles_from_overlay(
                    corners,
                    float(source_data.panorama_fov),
                    aspect_ratio,
                )
                horizontal_fov = _panorama_fov_for_chart(
                    corners,
                    heading,
                    elevation,
                    roll,
                    aspect_ratio,
                )
            except ValueError as exc:
                self.report({'ERROR'}, f'Could not project chart alignment: {exc}')
                return {'CANCELLED'}
            source_data.panorama_heading = heading
            source_data.panorama_elevation = elevation
            source_data.panorama_roll = roll
            source_data.panorama_fov = horizontal_fov
            source_data.projection_mode = 'EQUIRECTANGULAR'

        view_image = _find_panorama_view(source_image)
        is_new = view_image is None
        if is_new:
            view_image = bpy.data.images.new(
                f'{source_image.name} - MacBlend Chart View',
                width=MB_PANORAMA_VIEW_SIZE[0],
                height=MB_PANORAMA_VIEW_SIZE[1],
                alpha=True,
                float_buffer=True,
            )
            view_image[MB_PANORAMA_VIEW_MARKER] = True
            view_image.mb_sample_data.panorama_source_image = source_image
            view_image.mb_sample_data.patch_size = int(source_data.patch_size)

        try:
            _store_source_corners_on_projected_view(
                source_data,
                view_image.mb_sample_data,
                MB_PANORAMA_VIEW_SIZE,
            )
            _refresh_panorama_view(source_image, view_image, current_pixels=True)
        except (ValueError, MemoryError, RuntimeError) as exc:
            _clear_panorama_pixel_cache(source_image)
            if is_new:
                bpy.data.images.remove(view_image)
            self.report({'ERROR'}, f'Could not create chart view: {exc}')
            return {'CANCELLED'}

        view_image.mb_sample_data.show_overlay = True
        context.space_data.image = view_image
        _fit_image_in_editor(context)
        _tag_image_editor_redraw()
        self.report({'INFO'}, f"{'Created' if is_new else 'Updated'} chart view for '{source_image.name}'.")
        return {'FINISHED'}


@persistent
def MB_Messagebus_LoadPost(*args):
    _clear_panorama_pixel_cache()
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
        soft_min=0.0,
        soft_max=1.0,
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
    patch_size: IntProperty(
        name="Patch Size",
        description="Approximate colored-patch width and height in image pixels",
        min=1,
        max=200,
        get=_get_patch_size,
        set=_set_patch_size,
    )
    overlay_opacity: FloatProperty(
        name="Overlay Opacity",
        min=0.0,
        max=1.0,
        subtype='FACTOR',
        get=_get_overlay_opacity,
        set=_set_overlay_opacity,
    )
    show_overlay: BoolProperty(name="Show Overlay", get=_get_show_overlay, set=_set_show_overlay)
    show_overlay_corners: BoolProperty(name="Corner Positions", default=False)
    show_projection_settings: BoolProperty(name="Projection Settings", default=False)
    corner_tl: FloatVectorProperty(name="Top Left", size=2, default=(0.25, 0.82), update=_overlay_corner_changed)
    corner_tr: FloatVectorProperty(name="Top Right", size=2, default=(0.75, 0.82), update=_overlay_corner_changed)
    corner_br: FloatVectorProperty(name="Bottom Right", size=2, default=(0.75, 0.18), update=_overlay_corner_changed)
    corner_bl: FloatVectorProperty(name="Bottom Left", size=2, default=(0.25, 0.18), update=_overlay_corner_changed)
    projection_mode: EnumProperty(
        name="Projection",
        items=(
            ('FLAT', "Flat Image", "Align directly on a regular image"),
            ('EQUIRECTANGULAR', "360° Lat-Long", "Align in an undistorted panorama chart view"),
        ),
        default='FLAT',
    )
    panorama_heading: FloatProperty(
        name="Heading",
        subtype='ANGLE',
        default=0.0,
        update=_panorama_projection_changed,
    )
    panorama_elevation: FloatProperty(
        name="Elevation",
        subtype='ANGLE',
        default=0.0,
        min=-np.pi * 0.5,
        max=np.pi * 0.5,
        update=_panorama_projection_changed,
    )
    panorama_roll: FloatProperty(
        name="Roll",
        subtype='ANGLE',
        default=0.0,
        update=_panorama_projection_changed,
    )
    panorama_fov: FloatProperty(
        name="Field of View",
        subtype='ANGLE',
        default=np.deg2rad(60.0),
        min=np.deg2rad(0.1),
        max=np.deg2rad(179.0),
        update=_panorama_projection_changed,
    )
    panorama_source_image: PointerProperty(type=bpy.types.Image)


if not hasattr(MB_ImageSampleData, '__annotations__'):
    MB_ImageSampleData.__annotations__ = {}

for sample_idx, prop_name in enumerate(MB_SAMPLE_PROPERTY_NAMES):
    MB_ImageSampleData.__annotations__[prop_name] = FloatVectorProperty(
        name=MB_MACBETH_PATCH_NAMES[sample_idx],
        description=f"Sampled color for patch: {MB_MACBETH_PATCH_NAMES[sample_idx]}",
        size=3,
        subtype='COLOR',
        soft_min=0.0,
        soft_max=1.0,
        default=MB_MACBETH_REFERENCE_SRGB[sample_idx],
        update=_sample_patch_value_changed(sample_idx),
    )


class MB_SamplingUIState(bpy.types.PropertyGroup):
    selected_image: PointerProperty(type=bpy.types.Image, options={'HIDDEN'})
    active_image_index: IntProperty(
        name="Active Sampled Image",
        default=-1,
        min=-1,
        update=_active_sample_image_changed,
    )


if not hasattr(MB_SamplingUIState, '__annotations__'):
    MB_SamplingUIState.__annotations__ = {}

for sample_idx, prop_name in enumerate(MB_SAMPLE_PROPERTY_NAMES):
    MB_SamplingUIState.__annotations__[prop_name] = FloatVectorProperty(
        name=MB_MACBETH_PATCH_NAMES[sample_idx],
        description=f"Reference sRGB color for patch: {MB_MACBETH_PATCH_NAMES[sample_idx]}",
        size=3,
        subtype='COLOR',
        soft_min=0.0,
        soft_max=1.0,
        default=MB_MACBETH_REFERENCE_SRGB[sample_idx],
    )


class MB_UL_SampledImages(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.name, icon='IMAGE_DATA')

    def filter_items(self, context, data, property_name):
        images = getattr(data, property_name)
        flags = [self.bitflag_filter_item if image_has_sample_values(image) else 0 for image in images]
        return flags, []


class MB_OT_SampleImageColors(bpy.types.Operator):
    bl_idname = "macblend.sample_image_colors"
    bl_label = "Sample Chart"
    bl_description = "Sample the 24 Macbeth patch values from the active image"
    bl_options = {'REGISTER', 'UNDO'}

    skip_sanity_checks: BoolProperty(options={'HIDDEN'}, default=False)

    def invoke(self, context, event):
        if self.skip_sanity_checks:
            return self.execute(context)
        image = getattr(context.space_data, 'image', None)
        if image is None:
            return self.execute(context)
        if _panorama_source(image) is None:
            _ensure_overlay_initialized(image.mb_sample_data, image)
        return _invoke_sanity_checks(
            self,
            context,
            image,
            image.mb_sample_data,
            MB_SANITY_ACTION_SAMPLE,
        )

    def execute(self, context):
        image = getattr(context.space_data, 'image', None)
        if image is None:
            self.report({'ERROR'}, "No image selected in the Image Editor.")
            return {'CANCELLED'}

        width, height = image.size
        if width <= 0 or height <= 0:
            self.report({'ERROR'}, "Selected image has no valid pixel resolution.")
            return {'CANCELLED'}

        data = image.mb_sample_data
        source_image = _panorama_source(image)
        storage_image = source_image or image
        storage_data = storage_image.mb_sample_data
        overlay_corners = _get_overlay_corners(data, image)
        debug_logging = _debug_logging_enabled(context)
        if debug_logging:
            print(f"[MacBlend] User overlay corners: {overlay_corners}", flush=True)
        chart_size, sample_size = _chart_sample_geometry(
            overlay_corners,
            (width, height),
            data.patch_size,
        )
        if debug_logging:
            print("[MacBlend] Sample Chart debug:", flush=True)

        try:
            centers = _calculate_ccmaster_patch_centers(overlay_corners)
            homography = core.build_chart_homography(overlay_corners)
            transfer_started = perf_counter()
            pixel_buffer = _load_image_pixel_buffer(storage_image)
            transfer_seconds = perf_counter() - transfer_started
            averaging_started = perf_counter()
            sampled_values = []
            panorama_projection = (
                {
                    **_panorama_projection(storage_data),
                    'aspect_ratio': MB_PANORAMA_VIEW_SIZE[0] / MB_PANORAMA_VIEW_SIZE[1],
                }
                if source_image is not None
                else None
            )
            for slot, patch_name, _center_x, _center_y in centers:
                sample_rgb = core.sample_warped_chart_patch(
                    pixel_buffer,
                    homography,
                    slot,
                    sample_size,
                    chart_size=chart_size,
                    panorama_projection=panorama_projection,
                )
                sampled_values.append((slot, patch_name, sample_rgb))
                if debug_logging:
                    print(f"  slot[{slot}] {patch_name} -> {tuple(float(v) for v in sample_rgb)}", flush=True)
            averaging_seconds = perf_counter() - averaging_started
            if debug_logging:
                buffer_mib = pixel_buffer.nbytes / (1024.0 * 1024.0)
                print(
                    f"[MacBlend] Bulk pixel transfer: {transfer_seconds:.4f}s "
                    f"({buffer_mib:.1f} MiB); 24 patch averages: {averaging_seconds:.4f}s",
                    flush=True,
                )
        except (ValueError, MemoryError) as exc:
            self.report({'ERROR'}, f"Could not sample chart: {exc}")
            return {'CANCELLED'}

        _replace_sample_data(storage_data, centers, sampled_values)
        if source_image is not None:
            storage_data.patch_size = int(data.patch_size)
            _store_projected_corners_on_source(storage_data, overlay_corners, (width, height))
        data.show_overlay = False
        data.show_overlay_corners = False
        _set_selected_sample_image(context.scene, storage_image)
        _tag_image_editor_redraw()
        self.report({'INFO'}, f"Sampled {len(storage_data.samples)} values from '{storage_image.name}'.")
        return {'FINISHED'}


class MB_OT_ClearSampleData(bpy.types.Operator):
    bl_idname = "macblend.clear_sample_data"
    bl_label = "Delete Sample Values"
    bl_description = "Delete the sampled Macbeth values from the highlighted image"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _selected_sample_image(context.scene) is not None

    def execute(self, context):
        image = _selected_sample_image(context.scene)
        if image is None:
            return {'CANCELLED'}

        data = image.mb_sample_data
        data.samples.clear()
        data.patch_centers.clear()
        _reset_sample_patch_values(data)
        _invalidate_calibrations_for_image(image)
        settings = getattr(context.scene, 'macblend_calibrator_settings', None)
        if settings is not None:
            if settings.sample_source_image == image:
                settings.sample_source_image = None
            if settings.sample_target_image == image:
                settings.sample_target_image = None
        _set_selected_sample_image(context.scene, None)
        _tag_image_editor_redraw()
        self.report({'INFO'}, f"Cleared sample data for '{image.name}'.")
        return {'FINISHED'}


class MB_PT_ImageEditorSamplePanel(bpy.types.Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_label = 'MacBlend'
    bl_category = 'MacBlend'

    def draw(self, context):
        layout = self.layout
        layout.template_ID(context.space_data, 'image', new='image.new', open='image.open')
        image = getattr(context.space_data, 'image', None)
        if image is None:
            layout.label(text="Select an image")
        else:
            data = image.mb_sample_data
            source_image = _panorama_source(image)
            projection_data = source_image.mb_sample_data if source_image is not None else data
            colorspace_image = source_image or image
            layout.prop(colorspace_image.colorspace_settings, 'name', text='Color Space')
            layout.prop(data, 'patch_size')
            overlay_row = layout.row(align=True)
            overlay_row.prop(data, 'show_overlay')
            overlay_row.prop(data, 'overlay_opacity', slider=True)
            layout.operator(
                'macblend.open_panorama_chart_view',
                text='Disable Lat/Long Projection' if source_image is not None else 'Lat/Long Projection',
                icon='LOOP_BACK' if source_image is not None else 'WORLD_DATA',
            )

            alignment_box = layout.box()
            alignment_box.label(text='Chart Alignment')
            alignment_row = alignment_box.row(align=True)
            alignment_row.scale_y = 1.6
            alignment_row.operator('macblend.center_overlay_chart', text='Center Overlay')
            alignment_row.operator('macblend.reset_overlay_chart', text='Reset Chart')
            flip_row = alignment_box.row(align=True)
            flip_row.operator('macblend.flip_overlay_horizontal', text='Flip Horizontal')
            flip_row.operator('macblend.flip_overlay_vertical', text='Flip Vertical')

            if projection_data.projection_mode == 'EQUIRECTANGULAR':
                projection_header = alignment_box.row(align=True)
                projection_icon = 'TRIA_DOWN' if projection_data.show_projection_settings else 'TRIA_RIGHT'
                projection_header.prop(
                    projection_data,
                    'show_projection_settings',
                    text='Projection Settings',
                    icon=projection_icon,
                    emboss=False,
                )
                if projection_data.show_projection_settings:
                    panorama_column = alignment_box.column(align=True)
                    panorama_column.prop(projection_data, 'panorama_heading')
                    panorama_column.prop(projection_data, 'panorama_elevation')
                    panorama_column.prop(projection_data, 'panorama_roll')
                    panorama_column.prop(projection_data, 'panorama_fov')

            corners_header = alignment_box.row(align=True)
            corners_icon = 'TRIA_DOWN' if data.show_overlay_corners else 'TRIA_RIGHT'
            corners_header.prop(data, 'show_overlay_corners', text='Corner Positions', icon=corners_icon, emboss=False)

            if data.show_overlay_corners:
                corners_column = alignment_box.column(align=True)
                corners_column.prop(data, 'corner_tl', text='Top Left')
                corners_column.prop(data, 'corner_tr', text='Top Right')
                corners_column.prop(data, 'corner_br', text='Bottom Right')
                corners_column.prop(data, 'corner_bl', text='Bottom Left')

            sample_row = layout.row()
            sample_row.scale_y = 1.6
            sample_row.operator('macblend.sample_image_colors', text='Sample Chart', icon='IMPORT')

        ui_state = context.scene.macblend_sampling_ui
        layout.label(text='Sampled Images')
        list_row = layout.row()
        list_row.template_list(
            'MB_UL_SampledImages',
            '',
            bpy.data,
            'images',
            ui_state,
            'active_image_index',
            rows=3,
        )
        delete_column = list_row.column(align=True)
        delete_column.enabled = _peek_selected_sample_image(context.scene) is not None
        delete_column.operator('macblend.clear_sample_data', text='', icon='TRASH')

        selected_image = _peek_selected_sample_image(context.scene)
        display_data = selected_image.mb_sample_data if selected_image is not None else ui_state
        box = layout.box()
        box.label(text='Sampled Values')
        samples_col = box.column(align=True)
        samples_col.enabled = selected_image is not None
        for display_row in range(4):
            ui_row = samples_col.row(align=True)
            for col_idx in range(6):
                sample_idx = display_row * 6 + col_idx
                cell = ui_row.column(align=True)
                cell.prop(display_data, MB_SAMPLE_PROPERTY_NAMES[sample_idx], text='')


classes = (
    MB_ColorSample,
    MB_ChartPatchCenter,
    MB_ImageSampleData,
    MB_SamplingUIState,
    MB_UL_SampledImages,
    MB_GT_CornerCross,
    MB_GT_FlipArrow,
    MB_GGT_ImageEditorOverlay,
    MB_OT_AdjustOverlayCorner,
    MB_OT_FlipOverlayHorizontal,
    MB_OT_FlipOverlayVertical,
    MB_OT_CenterOverlayChart,
    MB_OT_OpenPanoramaChartView,
    MB_OT_SampleImageColors,
    MB_OT_ClearSampleData,
    MB_PT_ImageEditorSamplePanel,
)

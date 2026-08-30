import importlib.util
from pathlib import Path
import sys
import tempfile

import bpy
import numpy as np


addon_dir = Path(__file__).parents[1] / "source"
spec = importlib.util.spec_from_file_location(
    "macblend",
    addon_dir / "__init__.py",
    submodule_search_locations=[str(addon_dir)],
)
macblend = importlib.util.module_from_spec(spec)
sys.modules["macblend"] = macblend
spec.loader.exec_module(macblend)
from macblend import calibration, manual, sampling


assert calibration.MB_OT_ForwardTransform.bl_description == (
    "Create a transform from the sampled source colors to the selected target colors"
)
assert calibration.MB_OT_InverseTransform.bl_description == (
    "Create a transform from the selected target colors back to the sampled source colors"
)

manual_url, manual_mapping = manual.manual_map()
assert manual_url == "https://manuelhouben.github.io/macblend/"
assert ("bpy.ops.macblend.sample_image_colors", "sampling/index.html") in manual_mapping
assert ("bpy.ops.macblend.inverse_transform", "calibration/index.html") in manual_mapping
assert ("bpy.ops.macblend.forward_transform", "calibration/index.html") in manual_mapping
assert ("bpy.ops.macblend.export_luts", "export/index.html") in manual_mapping


class CursorWindow:
    def __init__(self, supports_closed_hand):
        self.supports_closed_hand = supports_closed_hand
        self.cursors = []

    def cursor_modal_set(self, cursor):
        self.cursors.append(cursor)
        if cursor == 'HAND_CLOSED' and not self.supports_closed_hand:
            raise TypeError('unsupported cursor')


def assert_link(source_node, target_socket):
    assert any(link.from_node == source_node for link in target_socket.links)


new_cursor_window = CursorWindow(supports_closed_hand=True)
sampling._set_drag_cursor(new_cursor_window)
assert new_cursor_window.cursors == ['HAND_CLOSED']

legacy_cursor_window = CursorWindow(supports_closed_hand=False)
sampling._set_drag_cursor(legacy_cursor_window)
assert legacy_cursor_window.cursors == ['HAND_CLOSED', 'HAND']

top_left = (10.0, 80.0)
top_right = (90.0, 60.0)
first_row_center = (47.0, 52.0)
horizontal_flip_point = sampling._opposite_line_midpoint(
    top_left,
    top_right,
    first_row_center,
)
top_midpoint = np.mean((top_left, top_right), axis=0)
top_axis = np.subtract(top_right, top_left)
top_normal = np.asarray((-top_axis[1], top_axis[0])) / np.linalg.norm(top_axis)
first_row_distance = np.dot(np.subtract(first_row_center, top_midpoint), top_normal)
flip_distance = np.dot(np.subtract(horizontal_flip_point, top_midpoint), top_normal)
np.testing.assert_allclose(
    horizontal_flip_point,
    top_midpoint - first_row_distance * top_normal,
)
np.testing.assert_allclose(flip_distance, -first_row_distance)

bottom_left = (18.0, 12.0)
first_column_center = (31.0, 43.0)
vertical_flip_point = sampling._opposite_line_midpoint(
    top_left,
    bottom_left,
    first_column_center,
)
left_midpoint = np.mean((top_left, bottom_left), axis=0)
left_axis = np.subtract(bottom_left, top_left)
left_normal = np.asarray((-left_axis[1], left_axis[0])) / np.linalg.norm(left_axis)
first_column_distance = np.dot(np.subtract(first_column_center, left_midpoint), left_normal)
vertical_flip_distance = np.dot(np.subtract(vertical_flip_point, left_midpoint), left_normal)
np.testing.assert_allclose(
    vertical_flip_point,
    left_midpoint - first_column_distance * left_normal,
)
np.testing.assert_allclose(vertical_flip_distance, -first_column_distance)

macblend.register()
try:
    assert hasattr(bpy.types.Scene, 'macblend_calibrator_settings')
    assert hasattr(bpy.types, 'MACBLEND_OT_forward_transform')
    assert hasattr(bpy.types, 'MACBLEND_OT_inverse_transform')
    assert not hasattr(bpy.types, 'MACBLEND_OT_match_transform')
    assert not hasattr(bpy.types, 'MACBLEND_OT_neutralize_transform')
    assert hasattr(bpy.ops.macblend, 'export_luts')
    assert hasattr(bpy.ops.macblend, 'confirm_lut_overwrite')
    assert hasattr(bpy.ops.macblend, 'open_panorama_chart_view')
    assert hasattr(bpy.types.Scene, 'macblend_sampling_ui')
    assert not hasattr(bpy.types.Scene, 'macbeth_calibrator_settings')
    assert hasattr(bpy.types.Image, 'mb_sample_data')
    assert not hasattr(bpy.types.Image, 'macblend_sample_data')
    assert not hasattr(bpy.types.Image, 'macbeth_sample_data')

    image = bpy.data.images.new("MacBlend Sample", width=4, height=4, alpha=True, float_buffer=True)
    assert image.mb_sample_data.show_overlay_corners is False
    assert image.mb_sample_data.projection_mode == 'FLAT'
    viewer_center = (0.25, 0.75)
    viewer_size = (0.8, 0.6)
    fake_window_region = type(
        "WindowRegion",
        (),
        {
            "type": 'WINDOW',
            "width": 800,
            "height": 600,
            "view2d": type(
                "View2D",
                (),
                {
                    "region_to_view": lambda self, x, y: (
                        viewer_center[0] + (x / 800.0 - 0.5) * viewer_size[0],
                        viewer_center[1] + (y / 600.0 - 0.5) * viewer_size[1],
                    ),
                },
            )(),
        },
    )()
    fake_context = type(
        "ImageEditorContext",
        (),
        {
            "area": type("ImageEditorArea", (), {"type": 'IMAGE_EDITOR', "regions": [fake_window_region]})(),
            "space_data": type("ImageEditorSpace", (), {"image": image})(),
        },
    )()
    center_reports = []
    center_operator = type(
        "CenterReporter",
        (),
        {"report": lambda self, levels, message: center_reports.append((levels, message))},
    )()
    assert sampling.MB_OT_CenterOverlayChart.execute(center_operator, fake_context) == {'FINISHED'}
    centered_corners = sampling._get_overlay_corners(image.mb_sample_data, image)
    np.testing.assert_allclose(
        np.mean(np.asarray(centered_corners), axis=0),
        viewer_center,
    )
    chart_width_px = (centered_corners[1][0] - centered_corners[0][0]) * image.size[0]
    chart_height_px = (centered_corners[0][1] - centered_corners[3][1]) * image.size[1]
    viewer_area_px = (
        viewer_size[0] * image.size[0]
        * viewer_size[1] * image.size[1]
    )
    np.testing.assert_allclose(
        chart_width_px * chart_height_px / viewer_area_px,
        sampling.MB_CHART_AREA_FRACTION,
        atol=1e-6,
    )
    np.testing.assert_allclose(
        chart_width_px / chart_height_px,
        sampling.MB_CHART_ASPECT_RATIO,
        atol=1e-6,
    )
    assert center_reports[-1][0] == {'INFO'}
    incomplete_image = bpy.data.images.new("MacBlend Incomplete", width=1, height=1)
    incomplete_image.mb_sample_data.samples.add().patch_index = 0
    assert not sampling.image_has_sample_values(incomplete_image)

    ui_state = bpy.context.scene.macblend_sampling_ui
    assert ui_state.active_image_index == -1
    for index, property_name in enumerate(sampling.MB_SAMPLE_PROPERTY_NAMES):
        np.testing.assert_allclose(
            getattr(ui_state, property_name),
            sampling.MB_MACBETH_REFERENCE_SRGB[index],
        )

    centers = [
        (slot, patch_name, (slot % 6 + 0.5) / 6.0, 1.0 - (slot // 6 + 0.5) / 4.0)
        for slot, patch_name in sampling.MB_CCMASTER
    ]
    first_values = [
        (slot, patch_name, (slot / 100.0, slot / 200.0, slot / 300.0))
        for slot, patch_name in sampling.MB_CCMASTER
    ]
    second_values = [
        (slot, patch_name, ((slot + 1) / 100.0, (slot + 1) / 200.0, (slot + 1) / 300.0))
        for slot, patch_name in sampling.MB_CCMASTER
    ]
    sampling._replace_sample_data(image.mb_sample_data, centers, first_values)
    assert sampling.image_has_sample_values(image)
    list_flags, list_order = sampling.MB_UL_SampledImages.filter_items(
        type("FilterState", (), {"bitflag_filter_item": 1})(),
        bpy.context,
        bpy.data,
        'images',
    )
    assert list_order == []
    assert list_flags[sampling._image_index(image)] == 1
    assert list_flags[sampling._image_index(incomplete_image)] == 0
    sampling._replace_sample_data(image.mb_sample_data, centers, second_values)
    assert len(image.mb_sample_data.samples) == 24
    np.testing.assert_allclose(image.mb_sample_data.samples[0].rgb, second_values[0][2])

    sampling._set_selected_sample_image(bpy.context.scene, image)
    assert sampling._selected_sample_image(bpy.context.scene) == image
    assert ui_state.active_image_index == sampling._image_index(image)

    settings = bpy.context.scene.macblend_calibrator_settings
    settings.sample_source_image = image
    target_image = bpy.data.images.new("MacBlend Export Target", width=1, height=1)
    settings.sample_target_image = target_image
    settings.use_reference_target = False
    target_values = [
        (slot, patch_name, sampling.MB_MACBETH_REFERENCE_SRGB[slot])
        for slot, patch_name in sampling.MB_CCMASTER
    ]
    source_values = [
        (slot, patch_name, np.asarray(sampling.MB_MACBETH_REFERENCE_SRGB[slot]) * 0.5)
        for slot, patch_name in sampling.MB_CCMASTER
    ]
    sampling._replace_sample_data(image.mb_sample_data, centers, source_values)
    sampling._replace_sample_data(target_image.mb_sample_data, centers, target_values)
    assert calibration._ordered_image_samples(image).shape == (24, 3)

    reports = []
    operator = type("ExportReporter", (), {"report": lambda self, levels, message: reports.append((levels, message))})()
    working_space, _used_fallback = calibration._scene_linear_working_space(bpy.context.scene)
    assert working_space
    node_group_count = len(bpy.data.node_groups)
    node_count = sum(len(group.nodes) for group in bpy.data.node_groups)
    settings.normalize_calibration = False
    unnormalized_exports = calibration._build_lut_exports(operator, bpy.context, size=17, clamp=False)
    settings.normalize_calibration = True
    exports = calibration._build_lut_exports(operator, bpy.context, size=17, clamp=False)
    assert len(exports) == 2
    assert [contents for _filename, contents in exports] != [
        contents for _filename, contents in unnormalized_exports
    ]
    unnormalized_forward = next(
        contents for filename, contents in unnormalized_exports if filename.endswith('_Forward.cube')
    )
    normalized_forward = next(
        contents for filename, contents in exports if filename.endswith('_Forward.cube')
    )
    unnormalized_white = tuple(float(value) for value in unnormalized_forward.splitlines()[-1].split())
    normalized_white = tuple(float(value) for value in normalized_forward.splitlines()[-1].split())
    assert all(normalized < unnormalized for normalized, unnormalized in zip(normalized_white, unnormalized_white))
    assert {filename.rsplit('_', 1)[-1] for filename, _contents in exports} == {
        'Forward.cube',
        'Inverse.cube',
    }
    assert len(bpy.data.node_groups) == node_group_count
    assert sum(len(group.nodes) for group in bpy.data.node_groups) == node_count
    with tempfile.TemporaryDirectory() as export_directory:
        calibration._write_lut_exports(export_directory, exports)
        exported_paths = list(Path(export_directory).glob('*.cube'))
        assert len(exported_paths) == 2
        assert all('LUT_3D_SIZE 17' in path.read_text(encoding='utf-8') for path in exported_paths)

    settings.sample_target_image = image
    sampling._set_selected_sample_image(bpy.context.scene, image)
    assert bpy.ops.macblend.clear_sample_data() == {'FINISHED'}
    assert not sampling.image_has_sample_values(image)
    assert len(image.mb_sample_data.patch_centers) == 0
    assert ui_state.active_image_index == -1
    assert settings.sample_source_image is None
    assert settings.sample_target_image is None

    assert image.mb_sample_data.get('show_overlay') is None
    assert image.mb_sample_data.show_overlay is True
    assert image.mb_sample_data.get('show_overlay') is None
    image.mb_sample_data.show_overlay = False
    assert image.mb_sample_data.get('show_overlay') is False
    pixels = np.arange(4 * 4 * 4, dtype=np.float32).reshape((4, 4, 4)) / 100.0
    pixels[:, :, 3] = 0.1
    image.pixels.foreach_set(pixels.ravel())

    pixel_buffer = sampling._load_image_pixel_buffer(image)
    assert pixel_buffer.shape == (4, 4, 4)
    np.testing.assert_allclose(pixel_buffer, pixels)
    np.testing.assert_allclose(
        sampling.core.sample_pixel_buffer(pixel_buffer, 2, 2, 3),
        np.mean(pixels[1:4, 1:4, :3], axis=(0, 1), dtype=np.float64),
    )
    np.testing.assert_allclose(
        sampling.core.sample_pixel_buffer(pixel_buffer, 0, 0, 3),
        np.mean(pixels[0:2, 0:2, :3], axis=(0, 1), dtype=np.float64),
    )

    panorama = bpy.data.images.new("MacBlend Panorama", width=8, height=4, alpha=True, float_buffer=True)
    panorama_pixels = np.zeros((4, 8, 4), dtype=np.float32)
    panorama_pixels[..., 0] = np.linspace(0.0, 1.0, 8)
    panorama_pixels[..., 2] = np.linspace(1.0, 0.0, 8)
    panorama_pixels[..., 3] = 1.0
    panorama.pixels.foreach_set(panorama_pixels.ravel())
    panorama.mb_sample_data.corner_tl = (0.94, 0.72)
    panorama.mb_sample_data.corner_tr = (0.06, 0.62)
    panorama.mb_sample_data.corner_br = (0.07, 0.34)
    panorama.mb_sample_data.corner_bl = (0.95, 0.40)

    panorama_space = type("PanoramaSpace", (), {"image": panorama})()
    panorama_context = type(
        "PanoramaContext",
        (),
        {
            "space_data": panorama_space,
            "scene": bpy.context.scene,
            "preferences": bpy.context.preferences,
        },
    )()
    panorama_reports = []
    panorama_operator = type(
        "PanoramaReporter",
        (),
        {"report": lambda self, levels, message: panorama_reports.append((levels, message))},
    )()
    assert sampling.MB_OT_OpenPanoramaChartView.execute(panorama_operator, panorama_context) == {'FINISHED'}
    assert panorama.mb_sample_data.projection_mode == 'EQUIRECTANGULAR'
    assert abs(panorama.mb_sample_data.panorama_heading) > np.deg2rad(170.0)
    assert not np.isclose(panorama.mb_sample_data.panorama_roll, 0.0, atol=1e-6)
    chart_view = panorama_space.image
    assert chart_view.get(sampling.MB_PANORAMA_VIEW_MARKER)
    assert chart_view.mb_sample_data.panorama_source_image == panorama
    assert tuple(chart_view.size) == sampling.MB_PANORAMA_VIEW_SIZE
    expected_view_u, expected_view_v = sampling.core.equirectangular_to_rectilinear_uv(
        np.asarray((0.94, 0.06, 0.07, 0.95)),
        np.asarray((0.72, 0.62, 0.34, 0.40)),
        aspect_ratio=chart_view.size[0] / chart_view.size[1],
        **sampling._panorama_projection(panorama.mb_sample_data),
    )
    np.testing.assert_allclose(
        sampling._get_overlay_corners(chart_view.mb_sample_data, chart_view),
        tuple(zip(expected_view_u, expected_view_v)),
        atol=1e-6,
    )
    source_homography = sampling.core.build_chart_homography(
        ((0.94, 0.72), (1.06, 0.62), (1.07, 0.34), (0.95, 0.40))
    )
    source_middle_left = sampling.core.map_chart_point(source_homography, 0.0, 0.5)
    source_middle_right = sampling.core.map_chart_point(source_homography, 1.0, 0.5)
    projected_middle_u, projected_middle_v = sampling.core.equirectangular_to_rectilinear_uv(
        np.mod((source_middle_left[0], source_middle_right[0]), 1.0),
        (source_middle_left[1], source_middle_right[1]),
        aspect_ratio=chart_view.size[0] / chart_view.size[1],
        **sampling._panorama_projection(panorama.mb_sample_data),
    )
    assert projected_middle_u[0] < projected_middle_u[1]
    np.testing.assert_allclose(
        projected_middle_v,
        (0.5, 0.5),
        atol=1e-6,
    )
    panorama_cache_key = int(panorama.as_pointer())
    cached_panorama_pixels = sampling._MB_PANORAMA_PIXEL_CACHE[panorama_cache_key][1]
    initial_view_center = np.asarray(chart_view.pixels[4 * ((384 * 1024) + 512):4 * ((384 * 1024) + 512) + 3])
    changed_panorama_pixels = panorama_pixels.copy()
    changed_panorama_pixels[..., 0] *= 0.5
    changed_panorama_pixels[..., 2] *= 0.75
    panorama.pixels.foreach_set(changed_panorama_pixels.ravel())
    sampling.MB_ImageColorspace_Changed()
    refreshed_panorama_pixels = sampling._MB_PANORAMA_PIXEL_CACHE[panorama_cache_key][1]
    assert refreshed_panorama_pixels is not cached_panorama_pixels
    colorspace_refreshed_center = np.asarray(
        chart_view.pixels[4 * ((384 * 1024) + 512):4 * ((384 * 1024) + 512) + 3]
    )
    assert not np.allclose(initial_view_center, colorspace_refreshed_center)
    cached_panorama_pixels = refreshed_panorama_pixels
    initial_view_center = colorspace_refreshed_center
    stored_projection = (0.7, -0.2, 0.1, np.deg2rad(75.0))
    panorama.mb_sample_data.panorama_heading = stored_projection[0]
    panorama.mb_sample_data.panorama_elevation = stored_projection[1]
    panorama.mb_sample_data.panorama_roll = stored_projection[2]
    panorama.mb_sample_data.panorama_fov = stored_projection[3]
    assert sampling._MB_PANORAMA_PIXEL_CACHE[panorama_cache_key][1] is cached_panorama_pixels
    refreshed_view_center = np.asarray(chart_view.pixels[4 * ((384 * 1024) + 512):4 * ((384 * 1024) + 512) + 3])
    assert not np.allclose(initial_view_center, refreshed_view_center)
    projected_corners = sampling._get_overlay_corners(chart_view.mb_sample_data, chart_view)
    expected_source_u, expected_source_v = sampling.core.rectilinear_to_equirectangular_uv(
        np.asarray([corner[0] for corner in projected_corners]),
        np.asarray([corner[1] for corner in projected_corners]),
        aspect_ratio=chart_view.size[0] / chart_view.size[1],
        **sampling._panorama_projection(panorama.mb_sample_data),
    )
    chart_view.mb_sample_data.patch_size = 1
    assert sampling.MB_OT_SampleImageColors.execute(panorama_operator, panorama_context) == {'FINISHED'}
    assert sampling.image_has_sample_values(panorama)
    assert not sampling.image_has_sample_values(chart_view)
    assert panorama.mb_sample_data.patch_size == 1
    np.testing.assert_allclose(
        sampling._get_overlay_corners(panorama.mb_sample_data, panorama),
        tuple(zip(expected_source_u, expected_source_v)),
        atol=1e-6,
    )
    assert panorama.mb_sample_data.projection_mode == 'EQUIRECTANGULAR'
    np.testing.assert_allclose(
        (
            panorama.mb_sample_data.panorama_heading,
            panorama.mb_sample_data.panorama_elevation,
            panorama.mb_sample_data.panorama_roll,
            panorama.mb_sample_data.panorama_fov,
        ),
        stored_projection,
    )
    chart_view_name = chart_view.name
    assert sampling.MB_OT_OpenPanoramaChartView.execute(panorama_operator, panorama_context) == {'FINISHED'}
    assert panorama_space.image == panorama
    assert bpy.data.images.get(chart_view_name) is None
    assert panorama_cache_key not in sampling._MB_PANORAMA_PIXEL_CACHE
    assert sampling.MB_OT_OpenPanoramaChartView.execute(panorama_operator, panorama_context) == {'FINISHED'}
    chart_view = panorama_space.image
    assert chart_view.get(sampling.MB_PANORAMA_VIEW_MARKER)
    assert chart_view.mb_sample_data.patch_size == 1
    np.testing.assert_allclose(
        sampling._get_overlay_corners(chart_view.mb_sample_data, chart_view),
        projected_corners,
        atol=1e-6,
    )
    np.testing.assert_allclose(
        (
            panorama.mb_sample_data.panorama_heading,
            panorama.mb_sample_data.panorama_elevation,
            panorama.mb_sample_data.panorama_roll,
            panorama.mb_sample_data.panorama_fov,
        ),
        stored_projection,
    )
    chart_view_name = chart_view.name
    assert sampling.MB_OT_OpenPanoramaChartView.execute(panorama_operator, panorama_context) == {'FINISHED'}
    assert panorama_space.image == panorama
    assert bpy.data.images.get(chart_view_name) is None
    panorama.mb_sample_data.corner_tl = (0.3, 0.7)
    panorama.mb_sample_data.corner_tr = (0.7, 0.7)
    panorama.mb_sample_data.corner_br = (0.7, 0.3)
    panorama.mb_sample_data.corner_bl = (0.3, 0.3)
    assert panorama.mb_sample_data.projection_mode == 'FLAT'
    np.testing.assert_allclose(
        (
            panorama.mb_sample_data.panorama_heading,
            panorama.mb_sample_data.panorama_elevation,
            panorama.mb_sample_data.panorama_roll,
            panorama.mb_sample_data.panorama_fov,
        ),
        (0.0, 0.0, 0.0, np.deg2rad(60.0)),
    )
    assert sampling.MB_OT_OpenPanoramaChartView.execute(panorama_operator, panorama_context) == {'FINISHED'}
    chart_view = panorama_space.image
    assert chart_view.get(sampling.MB_PANORAMA_VIEW_MARKER)
    np.testing.assert_allclose(
        (
            panorama.mb_sample_data.panorama_heading,
            panorama.mb_sample_data.panorama_elevation,
            panorama.mb_sample_data.panorama_roll,
            panorama.mb_sample_data.panorama_fov,
        ),
        (0.0, 0.0, 0.0, np.deg2rad(60.0)),
        atol=1e-6,
    )
    chart_view_name = chart_view.name
    assert sampling.MB_OT_OpenPanoramaChartView.execute(panorama_operator, panorama_context) == {'FINISHED'}
    assert panorama_space.image == panorama
    assert bpy.data.images.get(chart_view_name) is None
    sampling._set_selected_sample_image(bpy.context.scene, None)
    bpy.data.images.remove(panorama)

    unowned_group = bpy.data.node_groups.new("MB ColorMatrix (Shader)", "ShaderNodeTree")
    shader_group = calibration.build_matrix_node_group('SHADER')
    assert shader_group != unowned_group
    assert shader_group.get(calibration.MB_OWNER_KEY)
    assert calibration.build_matrix_node_group('SHADER') == shader_group

    compositor_group = calibration.build_matrix_node_group('COMPOSITOR')
    assert compositor_group.get(calibration.MB_OWNER_KEY)
    assert calibration.build_matrix_node_group('COMPOSITOR') == compositor_group
    separate_color = next(
        node for node in compositor_group.nodes if node.bl_idname == 'CompositorNodeSeparateColor'
    )
    combine_color = next(
        node for node in compositor_group.nodes if node.bl_idname == 'CompositorNodeCombineColor'
    )
    assert any(link.from_node == separate_color for link in combine_color.inputs['Alpha'].links)

    material = bpy.data.materials.new("MacBlend Smoke")
    material.use_nodes = True
    tree = material.node_tree
    unowned_node = tree.nodes.new('ShaderNodeValue')
    requested_name = "MacBlendCalibrationForward"
    unowned_node.name = requested_name

    matrix_node = calibration._create_matrix_node(
        tree,
        'SHADER',
        requested_name,
        np.eye(3, dtype=np.float32),
        label_text='Forward',
        location=(0, 0),
    )
    assert matrix_node != unowned_node
    assert tree.nodes.get(requested_name) == unowned_node
    assert matrix_node.get(calibration.MB_OWNER_KEY)

    output = next(node for node in tree.nodes if node.bl_idname == 'ShaderNodeOutputMaterial')
    surface = output.inputs['Surface']
    tree.links.new(matrix_node.outputs[0], surface)

    exposure = calibration._sync_exposure_node(tree, 'SHADER', matrix_node, 2.0, True)
    assert exposure is not None
    assert_link(matrix_node, exposure.inputs[0])
    assert_link(exposure, surface)

    exposure_name = exposure.name
    calibration._sync_exposure_node(tree, 'SHADER', matrix_node, 1.0, False)
    assert exposure_name not in tree.nodes
    assert_link(matrix_node, surface)

    malformed_exposure = tree.nodes.new('ShaderNodeValue')
    exposure_key = f"{matrix_node.get(calibration.MB_GENERATED_KEY)}:exposure"
    calibration._mark_owned(malformed_exposure, 'exposure', exposure_key)
    tree.links.new(malformed_exposure.outputs[0], surface)
    repaired_exposure = calibration._sync_exposure_node(tree, 'SHADER', matrix_node, 2.0, True)
    assert repaired_exposure.bl_idname == 'ShaderNodeVectorMath'
    assert_link(repaired_exposure, surface)
finally:
    macblend.unregister()

assert not hasattr(bpy.types.Scene, 'macblend_sampling_ui')
assert not hasattr(bpy.types.Image, 'mb_sample_data')

macblend.register()
macblend.unregister()

print("MacBlend Blender smoke tests passed.")
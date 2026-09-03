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
from macblend import calibration, core, manual, sampling


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

arrow_corners = ((0.1, 0.9), (0.85, 0.72), (0.7, 0.08), (0.18, 0.2))
arrow_homography = core.build_chart_homography(arrow_corners)
horizontal_arrow, vertical_arrow = sampling._flip_arrow_geometry(arrow_homography)
first_patch_u, first_patch_v = core.chart_patch_uv(0)
np.testing.assert_allclose(
    horizontal_arrow,
    core.map_chart_points(
        arrow_homography,
        ((0.5, 2.0 - first_patch_v), (0.0, 2.0 - first_patch_v), (1.0, 2.0 - first_patch_v)),
    ),
)
np.testing.assert_allclose(
    vertical_arrow,
    core.map_chart_points(
        arrow_homography,
        ((-first_patch_u, 0.5), (-first_patch_u, 1.0), (-first_patch_u, 0.0)),
    ),
)
assert not np.allclose(
    np.subtract(horizontal_arrow[2], horizontal_arrow[1]),
    np.subtract(arrow_corners[1], arrow_corners[0]),
)

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
    assert hasattr(bpy.ops.macblend, 'reset_overlay_chart')
    assert hasattr(bpy.types.Scene, 'macblend_sampling_ui')
    assert not hasattr(bpy.types.Scene, 'macbeth_calibrator_settings')
    assert hasattr(bpy.types.Image, 'mb_sample_data')
    assert not hasattr(bpy.types.Image, 'macblend_sample_data')
    assert not hasattr(bpy.types.Image, 'macbeth_sample_data')

    settings = bpy.context.scene.macblend_calibrator_settings
    target_items = macblend.get_target_colorspace_items(settings, bpy.context)
    assert [item[0] for item in target_items] == [
        identifier for identifier, _label, _matrix in core.REFERENCE_GAMUTS
    ]
    assert all('(auto-detect)' not in item[1] for item in target_items)
    assert settings.auto_detected_target == ''
    settings.target_colorspace = 'ACESCG'
    assert settings.target_colorspace == 'ACESCG'

    preference_properties = macblend.MacBlendCalibratorPreferences.bl_rna.properties
    assert preference_properties['default_patch_size'].default == sampling.MB_INITIAL_PATCH_SIZE
    assert np.isclose(preference_properties['default_overlay_opacity'].default, 0.5)
    assert preference_properties['default_normalize_calibration'].default is True
    assert preference_properties['default_create_exposure_node'].default is False
    assert preference_properties['default_lut_size'].default == '33'
    assert preference_properties['default_lut_clamp'].default is False

    original_settings_preference = macblend._preference_value
    original_sampling_preference = sampling._preference_value
    try:
        settings_defaults = {
            'default_normalize_calibration': False,
            'default_create_exposure_node': True,
        }
        image_defaults = {
            'default_patch_size': 31,
            'default_overlay_opacity': 0.25,
        }
        macblend._preference_value = lambda name, fallback: settings_defaults.get(name, fallback)
        sampling._preference_value = lambda name, fallback: image_defaults.get(name, fallback)

        preference_scene = bpy.data.scenes.new("MacBlend Preference Defaults")
        preference_image = bpy.data.images.new("MacBlend Preference Defaults", width=1000, height=800)
        assert preference_scene.macblend_calibrator_settings.normalize_calibration is False
        assert preference_scene.macblend_calibrator_settings.create_exposure_node is True
        assert preference_image.mb_sample_data.patch_size == 31
        assert np.isclose(preference_image.mb_sample_data.overlay_opacity, 0.25)

        preference_scene.macblend_calibrator_settings.normalize_calibration = True
        preference_image.mb_sample_data.patch_size = 19
        settings_defaults['default_normalize_calibration'] = False
        image_defaults['default_patch_size'] = 47
        assert preference_scene.macblend_calibrator_settings.normalize_calibration is True
        assert preference_image.mb_sample_data.patch_size == 19
    finally:
        macblend._preference_value = original_settings_preference
        sampling._preference_value = original_sampling_preference
        bpy.data.scenes.remove(preference_scene)
        bpy.data.images.remove(preference_image)

    selected_for_export = []
    export_operator = type(
        "PreferenceExportOperator",
        (),
        {
            "directory": "existing",
            "lut_size": '17',
            "clamp_output": False,
        },
    )()
    export_context = type(
        "PreferenceExportContext",
        (),
        {
            "preferences": bpy.context.preferences,
            "window_manager": type(
                "PreferenceWindowManager",
                (),
                {"fileselect_add": lambda self, operator: selected_for_export.append(operator)},
            )(),
        },
    )()
    original_export_preference = calibration._preference_value
    try:
        export_defaults = {'default_lut_size': '65', 'default_lut_clamp': True}
        calibration._preference_value = lambda context, name, fallback: export_defaults.get(name, fallback)
        assert calibration.MB_OT_ExportLuts.invoke(export_operator, export_context, None) == {'RUNNING_MODAL'}
        assert export_operator.lut_size == '65'
        assert export_operator.clamp_output is True
        assert selected_for_export == [export_operator]
    finally:
        calibration._preference_value = original_export_preference

    layout_image = bpy.data.images.new("MacBlend Layout", width=1000, height=800, alpha=True, float_buffer=True)
    assert layout_image.mb_sample_data.patch_size == sampling.MB_INITIAL_PATCH_SIZE
    layout_image.mb_sample_data.show_overlay = True
    initial_corners = sampling._get_overlay_corners(layout_image.mb_sample_data, layout_image)
    np.testing.assert_allclose(
        (
            (initial_corners[1][0] - initial_corners[0][0]) * layout_image.size[0],
            (initial_corners[0][1] - initial_corners[3][1]) * layout_image.size[1],
        ),
        sampling.MB_INITIAL_CHART_SIZE,
    )
    assert layout_image.mb_sample_data.patch_size == 40
    layout_image.mb_sample_data.patch_size = 27
    layout_image.mb_sample_data.show_overlay = False
    layout_image.mb_sample_data.show_overlay = True
    assert layout_image.mb_sample_data.patch_size == 27
    np.testing.assert_allclose(
        sampling._get_overlay_corners(layout_image.mb_sample_data, layout_image),
        initial_corners,
    )

    sized_image = bpy.data.images.new("MacBlend Sized Layout", width=1000, height=800)
    sized_data = sized_image.mb_sample_data
    sized_data.patch_size = 27
    sized_data.show_overlay = False
    sized_data.show_overlay = True
    sized_corners = sampling._get_overlay_corners(sized_data, sized_image)
    expected_cell_size = 27 / core.CHART_PATCH_CELL_RATIO
    np.testing.assert_allclose(
        (
            (sized_corners[1][0] - sized_corners[0][0]) * sized_image.size[0],
            (sized_corners[0][1] - sized_corners[3][1]) * sized_image.size[1],
        ),
        (
            expected_cell_size * core.CHART_COLUMNS,
            expected_cell_size * core.CHART_ROWS,
        ),
        atol=2e-5,
    )
    assert sized_data.patch_size == 27

    layout_image.mb_sample_data.corner_tl = (0.05, 0.95)
    layout_image.mb_sample_data.patch_size = 19
    reset_reports = []
    reset_operator = type(
        "ResetReporter",
        (),
        {"report": lambda self, levels, message: reset_reports.append((levels, message))},
    )()
    reset_context = type(
        "ResetContext",
        (),
        {"space_data": type("ResetSpace", (), {"image": layout_image})()},
    )()
    assert sampling.MB_OT_ResetOverlayChart.execute(reset_operator, reset_context) == {'FINISHED'}
    np.testing.assert_allclose(
        sampling._get_overlay_corners(layout_image.mb_sample_data, layout_image),
        initial_corners,
    )
    assert layout_image.mb_sample_data.patch_size == 40
    assert reset_reports[-1][0] == {'INFO'}

    legacy_image = bpy.data.images.new("MacBlend Legacy Layout", width=1000, height=800)
    legacy_data = legacy_image.mb_sample_data
    legacy_corners = ((0.1, 0.7), (0.6, 0.7), (0.6, 0.2), (0.1, 0.2))
    legacy_data.corner_tl, legacy_data.corner_tr, legacy_data.corner_br, legacy_data.corner_bl = legacy_corners
    legacy_data.patch_size = 23
    legacy_data['show_overlay'] = False
    legacy_data.show_overlay = True
    np.testing.assert_allclose(sampling._get_overlay_corners(legacy_data, legacy_image), legacy_corners)
    assert legacy_data.patch_size == 23

    image = bpy.data.images.new("MacBlend Sample", width=4, height=4, alpha=True, float_buffer=True)
    assert image.mb_sample_data.show_overlay_corners is False
    assert image.mb_sample_data.show_projection_settings is False
    assert image.mb_sample_data.projection_mode == 'FLAT'
    viewer_geometry = {'center': (0.25, 0.75), 'size': (0.8, 0.6)}
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
                        viewer_geometry['center'][0] + (x / 800.0 - 0.5) * viewer_geometry['size'][0],
                        viewer_geometry['center'][1] + (y / 600.0 - 0.5) * viewer_geometry['size'][1],
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
            "space_data": type("ImageEditorSpace", (), {"image": layout_image})(),
        },
    )()
    center_reports = []
    center_operator = type(
        "CenterReporter",
        (),
        {"report": lambda self, levels, message: center_reports.append((levels, message))},
    )()
    assert sampling.MB_OT_CenterOverlayChart.execute(center_operator, fake_context) == {'FINISHED'}
    centered_corners = sampling._get_overlay_corners(layout_image.mb_sample_data, layout_image)
    np.testing.assert_allclose(
        np.mean(np.asarray(centered_corners), axis=0),
        viewer_geometry['center'],
    )
    chart_width_px = (centered_corners[1][0] - centered_corners[0][0]) * layout_image.size[0]
    chart_height_px = (centered_corners[0][1] - centered_corners[3][1]) * layout_image.size[1]
    viewer_area_px = (
        viewer_geometry['size'][0] * layout_image.size[0]
        * viewer_geometry['size'][1] * layout_image.size[1]
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
    assert layout_image.mb_sample_data.patch_size == 32
    viewer_geometry['size'] = (0.4, 0.3)
    assert sampling.MB_OT_CenterOverlayChart.execute(center_operator, fake_context) == {'FINISHED'}
    assert layout_image.mb_sample_data.patch_size == 16
    assert center_reports[-1][0] == {'INFO'}
    incomplete_image = bpy.data.images.new("MacBlend Incomplete", width=1, height=1)
    incomplete_image.mb_sample_data.samples.add().patch_index = 0
    assert not sampling.image_has_sample_values(incomplete_image)

    ui_state = bpy.context.scene.macblend_sampling_ui
    assert ui_state.active_image_index == -1
    stored_rgb_property = sampling.MB_ColorSample.bl_rna.properties['rgb']
    assert stored_rgb_property.soft_min == 0.0
    assert stored_rgb_property.soft_max == 1.0
    for index, property_name in enumerate(sampling.MB_SAMPLE_PROPERTY_NAMES):
        image_property = sampling.MB_ImageSampleData.bl_rna.properties[property_name]
        ui_property = sampling.MB_SamplingUIState.bl_rna.properties[property_name]
        assert image_property.soft_min == 0.0
        assert image_property.soft_max == 1.0
        assert ui_property.soft_min == 0.0
        assert ui_property.soft_max == 1.0
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

    settings.sample_source_image = image
    settings.calculation_done = True
    edited_patch = (0.31, 0.27, 0.19)
    setattr(image.mb_sample_data, sampling.MB_SAMPLE_PROPERTY_NAMES[1], edited_patch)
    np.testing.assert_allclose(image.mb_sample_data.samples[1].rgb, edited_patch)
    assert settings.calculation_done is False
    assert settings.matrix_display_string == "Matrix not calculated."

    settings.calculation_done = True
    settings.normalize_calibration = not settings.normalize_calibration
    assert settings.calculation_done is False

    stable_selection_image = bpy.data.images.new("MacBlend Stable Selection", width=1, height=1)
    sampling._replace_sample_data(stable_selection_image.mb_sample_data, centers, second_values)
    sampling._set_selected_sample_image(bpy.context.scene, stable_selection_image)
    selected_index = sampling._image_index(stable_selection_image)
    earlier_image = bpy.data.images[selected_index - 1]
    if earlier_image not in {image, stable_selection_image}:
        bpy.data.images.remove(earlier_image)
        assert sampling._selected_sample_image(bpy.context.scene) == stable_selection_image
        assert ui_state.active_image_index == sampling._image_index(stable_selection_image)
    sampling._set_selected_sample_image(bpy.context.scene, image)
    bpy.data.images.remove(stable_selection_image)

    original_working_space_resolver = calibration._scene_linear_working_space
    try:
        calibration._scene_linear_working_space = lambda: 'ACEScg'
        settings.sample_source_image = image
        assert settings.auto_detected_target == 'ACESCG'
        assert settings.target_colorspace == 'ACESCG'

        settings.sample_source_image = None
        assert settings.auto_detected_target == ''

        calibration._scene_linear_working_space = lambda: 'Unsupported Gamut'
        settings.sample_source_image = image
        assert settings.auto_detected_target == ''
        assert settings.target_colorspace == 'REC709'

        def unavailable_working_space():
            raise ValueError("Working space unavailable")

        settings.sample_source_image = None
        calibration._scene_linear_working_space = unavailable_working_space
        settings.sample_source_image = image
        assert settings.auto_detected_target == ''
        assert settings.target_colorspace == 'REC709'
    finally:
        settings.sample_source_image = None
        calibration._scene_linear_working_space = original_working_space_resolver
        settings.sample_source_image = image

    assert settings.auto_detected_target == 'REC709'
    assert settings.target_colorspace == settings.auto_detected_target
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

    prepare_reports = []
    prepare_reporter = type(
        "PrepareReporter",
        (),
        {"report": lambda self, levels, message: prepare_reports.append((levels, message))},
    )()
    settings.normalize_calibration = True
    invalid_target_values = list(target_values)
    invalid_target_values[21] = (21, sampling.MB_CCMASTER[21][1], (0.0, 0.0, 0.0))
    sampling._replace_sample_data(target_image.mb_sample_data, centers, invalid_target_values)
    assert calibration._prepare_calibration_data(
        prepare_reporter,
        bpy.context,
        require_editor=False,
    ) == (None, None, None, None, None)
    assert prepare_reports[-1] == (
        {'ERROR'},
        "Target Neutral 5 luminance must be finite and greater than zero for normalization.",
    )
    sampling._replace_sample_data(target_image.mb_sample_data, centers, target_values)

    sampled_data = calibration._prepare_calibration_data(
        prepare_reporter,
        bpy.context,
        require_editor=False,
        normalize_matrix_input=False,
    )
    expected_sampled_matrix = core.calculate_matrix_result(
        np.asarray([value[2] for value in source_values]),
        np.asarray([value[2] for value in target_values]),
    ).matrix
    np.testing.assert_allclose(sampled_data[3], expected_sampled_matrix, atol=1e-6)
    settings.use_reference_target = True
    settings.target_colorspace = 'REC709'
    reference_data = calibration._prepare_calibration_data(
        prepare_reporter,
        bpy.context,
        require_editor=False,
        normalize_matrix_input=False,
    )
    expected_reference_matrix = core.calculate_matrix_result(
        np.asarray([value[2] for value in source_values]),
        core.build_reference_values('REC709'),
    ).matrix
    np.testing.assert_allclose(reference_data[3], expected_reference_matrix, atol=1e-6)
    settings.use_reference_target = False

    reports = []
    operator = type("ExportReporter", (), {"report": lambda self, levels, message: reports.append((levels, message))})()
    working_space = calibration._scene_linear_working_space()
    assert working_space
    blend_colorspace = getattr(bpy.data, 'colorspace', None)
    if blend_colorspace is not None:
        assert working_space == blend_colorspace.working_space
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

        original_contents = {path: f"old {path.name}" for path in exported_paths}
        for path, contents in original_contents.items():
            path.write_text(contents, encoding='utf-8')
        original_replace = calibration.os.replace
        install_count = [0]

        def fail_second_install(source, destination):
            if str(source).endswith('.tmp'):
                install_count[0] += 1
                if install_count[0] == 2:
                    raise OSError("simulated second LUT install failure")
            return original_replace(source, destination)

        calibration.os.replace = fail_second_install
        try:
            try:
                calibration._write_lut_exports(export_directory, exports)
                raise AssertionError("Expected LUT transaction failure")
            except OSError as exc:
                assert "simulated second LUT install failure" in str(exc)
        finally:
            calibration.os.replace = original_replace
        assert all(path.read_text(encoding='utf-8') == contents for path, contents in original_contents.items())
        assert not list(Path(export_directory).glob('.*.tmp'))
        assert not list(Path(export_directory).glob('.*.bak'))

    settings.sample_target_image = image
    sampling._set_selected_sample_image(bpy.context.scene, image)
    assert bpy.ops.macblend.clear_sample_data() == {'FINISHED'}
    assert not sampling.image_has_sample_values(image)
    assert len(image.mb_sample_data.patch_centers) == 0
    assert ui_state.active_image_index == -1
    assert settings.sample_source_image is None
    assert settings.sample_target_image is None
    assert settings.auto_detected_target == ''

    assert image.mb_sample_data.get('show_overlay') is None
    assert image.mb_sample_data.show_overlay is False
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

    perspective_image = bpy.data.images.new(
        "MacBlend Perspective Sample",
        width=64,
        height=64,
        alpha=True,
        float_buffer=True,
    )
    perspective_pixels = np.zeros((64, 64, 4), dtype=np.float32)
    pixel_x = (np.arange(64, dtype=np.float32) + 0.5) / 64.0
    pixel_y = (np.arange(64, dtype=np.float32) + 0.5) / 64.0
    grid_x, grid_y = np.meshgrid(pixel_x, pixel_y)
    perspective_pixels[..., 0] = grid_x ** 2
    perspective_pixels[..., 1] = grid_y ** 2
    perspective_pixels[..., 2] = grid_x * grid_y
    perspective_pixels[..., 3] = 1.0
    perspective_image.pixels.foreach_set(perspective_pixels.ravel())
    perspective_corners = ((0.1, 0.9), (0.9, 0.7), (0.7, 0.1), (0.2, 0.2))
    perspective_image.mb_sample_data.corner_tl = perspective_corners[0]
    perspective_image.mb_sample_data.corner_tr = perspective_corners[1]
    perspective_image.mb_sample_data.corner_br = perspective_corners[2]
    perspective_image.mb_sample_data.corner_bl = perspective_corners[3]
    perspective_image.mb_sample_data.patch_size = 30
    perspective_context = type(
        "PerspectiveContext",
        (),
        {
            "space_data": type("PerspectiveSpace", (), {"image": perspective_image})(),
            "scene": bpy.context.scene,
            "preferences": bpy.context.preferences,
        },
    )()
    perspective_reporter = type(
        "PerspectiveReporter",
        (),
        {"report": lambda self, levels, message: None},
    )()
    perspective_homography = core.build_chart_homography(perspective_corners)
    perspective_chart_size = core.chart_rectified_size(perspective_corners, (64, 64))
    expected_perspective_sample = core.sample_warped_chart_patch(
        perspective_pixels,
        perspective_homography,
        0,
        30,
        chart_size=perspective_chart_size,
    )
    old_center = core.map_chart_point(perspective_homography, *core.chart_patch_uv(0))
    old_axis_aligned_sample = core.sample_pixel_buffer(
        perspective_pixels,
        old_center[0] * 64,
        old_center[1] * 64,
        30,
    )
    assert not np.allclose(expected_perspective_sample, old_axis_aligned_sample, atol=1e-4)
    assert sampling.MB_OT_SampleImageColors.execute(
        perspective_reporter,
        perspective_context,
    ) == {'FINISHED'}
    np.testing.assert_allclose(
        perspective_image.mb_sample_data.samples[0].rgb,
        expected_perspective_sample,
        atol=1e-6,
    )

    fresh_panorama = bpy.data.images.new("MacBlend Fresh Panorama", width=1000, height=500, alpha=True, float_buffer=True)
    fresh_space = type("FreshPanoramaSpace", (), {"image": fresh_panorama})()
    fresh_context = type(
        "FreshPanoramaContext",
        (),
        {
            "space_data": fresh_space,
            "scene": bpy.context.scene,
            "preferences": bpy.context.preferences,
        },
    )()
    fresh_reports = []
    fresh_operator = type(
        "FreshPanoramaReporter",
        (),
        {"report": lambda self, levels, message: fresh_reports.append((levels, message))},
    )()
    assert fresh_panorama.mb_sample_data.get(sampling.MB_OVERLAY_INITIALIZED_KEY) is None
    assert sampling.MB_OT_OpenPanoramaChartView.execute(fresh_operator, fresh_context) == {'FINISHED'}
    fresh_corners = sampling._get_overlay_corners(fresh_panorama.mb_sample_data, fresh_panorama)
    assert fresh_panorama.mb_sample_data.get(sampling.MB_OVERLAY_INITIALIZED_KEY)
    assert fresh_corners[1][0] - fresh_corners[0][0] < 0.5
    assert fresh_panorama.mb_sample_data.projection_mode == 'EQUIRECTANGULAR'
    assert fresh_space.image.mb_sample_data.panorama_source_image == fresh_panorama
    assert not fresh_reports or fresh_reports[-1][0] != {'ERROR'}
    assert sampling.MB_OT_OpenPanoramaChartView.execute(fresh_operator, fresh_context) == {'FINISHED'}
    assert fresh_space.image == fresh_panorama
    bpy.data.images.remove(fresh_panorama)

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
    assert np.isclose(
        max(float(np.ptp(expected_view_u)), float(np.ptp(expected_view_v))),
        sampling.MB_PANORAMA_CHART_VIEW_FRACTION,
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
    latest_panorama_pixels = changed_panorama_pixels.copy()
    latest_panorama_pixels[..., 1] = 0.4
    panorama.pixels.foreach_set(latest_panorama_pixels.ravel())
    stored_projection = (0.7, -0.2, 0.1, np.deg2rad(75.0))
    panorama.mb_sample_data.panorama_heading = stored_projection[0]
    panorama.mb_sample_data.panorama_elevation = stored_projection[1]
    panorama.mb_sample_data.panorama_roll = stored_projection[2]
    panorama.mb_sample_data.panorama_fov = stored_projection[3]
    current_panorama_pixels = sampling._MB_PANORAMA_PIXEL_CACHE[panorama_cache_key][1]
    assert current_panorama_pixels is not cached_panorama_pixels
    np.testing.assert_allclose(current_panorama_pixels, latest_panorama_pixels)
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
    expected_fov = sampling._panorama_fov_for_chart(
        ((0.3, 0.7), (0.7, 0.7), (0.7, 0.3), (0.3, 0.3)),
        0.0,
        0.0,
        0.0,
        chart_view.size[0] / chart_view.size[1],
    )
    np.testing.assert_allclose(
        (
            panorama.mb_sample_data.panorama_heading,
            panorama.mb_sample_data.panorama_elevation,
            panorama.mb_sample_data.panorama_roll,
            panorama.mb_sample_data.panorama_fov,
        ),
        (0.0, 0.0, 0.0, expected_fov),
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
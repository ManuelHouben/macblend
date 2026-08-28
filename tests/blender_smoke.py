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

macblend.register()
try:
    assert hasattr(bpy.types.Scene, 'macblend_calibrator_settings')
    assert hasattr(bpy.types, 'MACBLEND_OT_forward_transform')
    assert hasattr(bpy.types, 'MACBLEND_OT_inverse_transform')
    assert not hasattr(bpy.types, 'MACBLEND_OT_match_transform')
    assert not hasattr(bpy.types, 'MACBLEND_OT_neutralize_transform')
    assert hasattr(bpy.ops.macblend, 'export_luts')
    assert hasattr(bpy.ops.macblend, 'confirm_lut_overwrite')
    assert hasattr(bpy.types.Scene, 'macblend_sampling_ui')
    assert not hasattr(bpy.types.Scene, 'macbeth_calibrator_settings')
    assert hasattr(bpy.types.Image, 'mb_sample_data')
    assert not hasattr(bpy.types.Image, 'macblend_sample_data')
    assert not hasattr(bpy.types.Image, 'macbeth_sample_data')

    image = bpy.data.images.new("MacBlend Sample", width=4, height=4, alpha=True, float_buffer=True)
    assert image.mb_sample_data.show_overlay_corners is False
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
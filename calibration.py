import math
import importlib
import os
import tempfile

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import colorspaces, core, lut_writer, sampling


MB_OWNER_KEY = "macblend_owner"
MB_ROLE_KEY = "macblend_role"
MB_GENERATED_KEY = "macblend_generated_key"
MB_SCHEMA_KEY = "macblend_schema"
MB_SCHEMA_VERSION = 2


def _mark_owned(data_block, role, generated_key):
    data_block[MB_OWNER_KEY] = True
    data_block[MB_ROLE_KEY] = role
    data_block[MB_GENERATED_KEY] = generated_key
    data_block[MB_SCHEMA_KEY] = MB_SCHEMA_VERSION


def _is_owned(data_block, role=None, generated_key=None):
    if not bool(data_block.get(MB_OWNER_KEY, False)):
        return False
    if role is not None and data_block.get(MB_ROLE_KEY) != role:
        return False
    if generated_key is not None and data_block.get(MB_GENERATED_KEY) != generated_key:
        return False
    return True


def _find_owned_node(tree, role, generated_key):
    return next(
        (node for node in tree.nodes if _is_owned(node, role, generated_key)),
        None,
    )


def _debug_logging_enabled(context):
    addon = context.preferences.addons.get(__package__)
    return bool(addon and getattr(addon.preferences, 'debug_logging', False))


def _get_editor_kind(space_data):
    if space_data is None:
        return None

    tree_type = getattr(space_data, 'tree_type', '')
    if tree_type in {'ShaderNodeTree', 'SHADER'}:
        return 'SHADER'
    if tree_type in {'CompositorNodeTree', 'COMPOSITOR'}:
        return 'COMPOSITOR'
    return None


def _add_group_socket(group, *, in_out, socket_type, name):
    # Blender 4.x node groups use the interface API; older builds may still expose inputs/outputs.
    interface = getattr(group, 'interface', None)
    if interface is not None and hasattr(interface, 'new_socket'):
        try:
            return interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
        except TypeError:
            return interface.new_socket(name, in_out, socket_type)

    if in_out == 'INPUT':
        return group.inputs.new(type=socket_type, name=name)
    return group.outputs.new(type=socket_type, name=name)


def _group_is_usable(group):
    required_inputs = {'Image', 'Output Red', 'Output Green', 'Output Blue'}

    input_node = None
    output_node = None
    for node in group.nodes:
        if node.bl_idname == 'NodeGroupInput':
            input_node = node
        elif node.bl_idname == 'NodeGroupOutput':
            output_node = node

    if input_node is None or output_node is None:
        return False

    input_names = {socket.name for socket in input_node.outputs}
    output_names = {socket.name for socket in output_node.inputs}
    if not (required_inputs.issubset(input_names) and 'Image' in output_names):
        return False

    # Ensure matrix rows are vectors so existing stale groups get rebuilt.
    row_socket_names = ('Output Red', 'Output Green', 'Output Blue')
    for socket_name in row_socket_names:
        socket = input_node.outputs.get(socket_name)
        if socket is None or getattr(socket, 'type', None) != 'VECTOR':
            return False

    separate_xyz_types = {'CompositorNodeSeparateXYZ', 'CompositorNodeSepXYZ', 'ShaderNodeSeparateXYZ'}
    combine_xyz_types = {'CompositorNodeCombineXYZ', 'CompositorNodeCombXYZ', 'ShaderNodeCombineXYZ'}
    separate_xyz_count = sum(node.bl_idname in separate_xyz_types for node in group.nodes)
    required_separate_count = 4 if group.bl_idname == 'ShaderNodeTree' else 3
    if separate_xyz_count < required_separate_count:
        return False
    if group.bl_idname == 'ShaderNodeTree' and not any(
        node.bl_idname in combine_xyz_types for node in group.nodes
    ):
        return False

    if group.bl_idname == 'CompositorNodeTree':
        separate_color = next(
            (node for node in group.nodes if node.bl_idname == 'CompositorNodeSeparateColor'),
            None,
        )
        combine_color = next(
            (node for node in group.nodes if node.bl_idname == 'CompositorNodeCombineColor'),
            None,
        )
        if separate_color is None or combine_color is None:
            return False
        alpha_input = combine_color.inputs.get('Alpha')
        if alpha_input is None or not any(link.from_node == separate_color for link in alpha_input.links):
            return False

    return True


def _new_xyz_separate_node(group, tree_type):
    node_types = ('ShaderNodeSeparateXYZ',) if tree_type == 'SHADER' else (
        'CompositorNodeSeparateXYZ',
        'CompositorNodeSepXYZ',
        'ShaderNodeSeparateXYZ',
    )
    for node_type in node_types:
        try:
            node = group.nodes.new(type=node_type)
            return node
        except RuntimeError:
            continue

    raise RuntimeError(f"Could not create a compatible {tree_type.lower()} Separate XYZ node.")


def _new_xyz_combine_node(group, tree_type):
    node_types = ('ShaderNodeCombineXYZ',) if tree_type == 'SHADER' else (
        'CompositorNodeCombineXYZ',
        'CompositorNodeCombXYZ',
        'ShaderNodeCombineXYZ',
    )
    for node_type in node_types:
        try:
            node = group.nodes.new(type=node_type)
            return node
        except RuntimeError:
            continue

    raise RuntimeError(f"Could not create a compatible {tree_type.lower()} Combine XYZ node.")


def _new_math_node(group, tree_type, operation):
    node_types = ('ShaderNodeMath',) if tree_type == 'SHADER' else (
        'CompositorNodeMath',
        'FunctionNodeMath',
        'ShaderNodeMath',
    )
    node = None
    for node_type in node_types:
        try:
            node = group.nodes.new(type=node_type)
            break
        except RuntimeError:
            continue
    if node is None:
        raise RuntimeError("Could not create a compatible math node for this node tree.")
    node.operation = operation
    return node


def _set_vector_math_scale_value(node, value):
    node.operation = 'SCALE'
    scalar = float(value)

    # Preferred path: Blender labels the scalar socket as "Scale".
    socket = node.inputs.get('Scale')
    if socket is not None:
        socket.default_value = scalar
        return

    # Fallback: locate the first value socket and set it.
    for input_socket in node.inputs:
        if getattr(input_socket, 'type', None) == 'VALUE':
            input_socket.default_value = scalar
            return

    raise RuntimeError("Could not find scalar SCALE socket on ShaderNodeVectorMath.")


def _load_json_data(context):
    prefs_addon = context.preferences.addons.get(__package__)
    if prefs_addon is None:
        return None

    addon_prefs = getattr(prefs_addon, 'preferences', None)
    if addon_prefs is None:
        return None

    json_path = colorspaces.effective_json_path(getattr(addon_prefs, 'json_file_path', None))
    return colorspaces.load_colorspace_data(json_path)


def _build_reference_samples(context, selected_target):
    if selected_target == "LINEAR_SRGB_D65":
        return core.MACBETH_LINEAR_SRGB_D65_BASE.copy()

    try:
        json_data = _load_json_data(context)
    except colorspaces.ColorspaceDataError as exc:
        raise ValueError(str(exc)) from exc
    if json_data is None:
        raise ValueError(
            f"Cannot generate reference for '{selected_target}', JSON data is unavailable."
        )

    try:
        srgb_to_xyz_m = np.array(json_data["sRGB_to_XYZ_matrix"], dtype=np.float32)
        base_xyz_d65 = np.dot(core.MACBETH_LINEAR_SRGB_D65_BASE, srgb_to_xyz_m.T)

        xyz_to_target_m = np.array(json_data["XYZ_to_RGB_matrices"][selected_target], dtype=np.float32)
        target_whitepoint = json_data.get("whitepoints", {}).get(selected_target, 'D65')

        cat_matrix = np.identity(3, dtype=np.float32)
        if target_whitepoint != 'D65':
            cat_key = f"D65_to_{target_whitepoint}"
            if cat_key in json_data.get("CAT_matrices", {}):
                cat_matrix = np.array(json_data["CAT_matrices"][cat_key], dtype=np.float32)

        xyz_adapted = np.dot(base_xyz_d65, cat_matrix.T)
        ref_samples = np.dot(xyz_adapted, xyz_to_target_m.T)
        ref_samples = np.maximum(0.0, ref_samples).astype(np.float32)
        return ref_samples
    except KeyError as exc:
        raise ValueError(f"Missing transform data for target '{selected_target}': {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Failed to build target reference '{selected_target}': {exc}") from exc


def _ordered_image_samples(image):
    if not sampling.image_has_sample_values(image):
        return None

    data = image.mb_sample_data
    ordered_samples = [None] * 24
    for sample in data.samples:
        patch_index = int(getattr(sample, 'patch_index', -1))
        if 0 <= patch_index < 24:
            ordered_samples[patch_index] = tuple(float(channel) for channel in sample.rgb)

    samples = np.array([value for value in ordered_samples if value is not None], dtype=np.float32)
    return samples if samples.shape == (24, 3) else None


def _target_is_selected(context):
    settings = getattr(context.scene, 'macblend_calibrator_settings', None)
    return bool(settings and (settings.use_reference_target or settings.sample_target_image is not None))


def build_matrix_node_group(tree_type):
    group_name = "MB ColorMatrix (Shader)" if tree_type == 'SHADER' else "MB ColorMatrix (Compositor)"
    group_key = f"matrix_group:{tree_type.lower()}"
    for group in bpy.data.node_groups:
        if not _is_owned(group, 'matrix_group', group_key):
            continue
        if group.get(MB_SCHEMA_KEY) == MB_SCHEMA_VERSION and _group_is_usable(group):
            return group

    if tree_type == 'SHADER':
        group = bpy.data.node_groups.new(name=group_name, type='ShaderNodeTree')
    else:
        group = bpy.data.node_groups.new(name=group_name, type='CompositorNodeTree')
    _mark_owned(group, 'matrix_group', group_key)

    _add_group_socket(group, in_out='INPUT', socket_type='NodeSocketColor', name='Image')
    _add_group_socket(group, in_out='INPUT', socket_type='NodeSocketVector', name='Output Red')
    _add_group_socket(group, in_out='INPUT', socket_type='NodeSocketVector', name='Output Green')
    _add_group_socket(group, in_out='INPUT', socket_type='NodeSocketVector', name='Output Blue')
    _add_group_socket(group, in_out='OUTPUT', socket_type='NodeSocketColor', name='Image')

    in_node = group.nodes.new(type='NodeGroupInput')
    out_node = group.nodes.new(type='NodeGroupOutput')
    if tree_type == 'COMPOSITOR':
        sep_img = group.nodes.new(type='CompositorNodeSeparateColor')
        combine = group.nodes.new(type='CompositorNodeCombineColor')
    else:
        sep_img = _new_xyz_separate_node(group, tree_type)
        combine = _new_xyz_combine_node(group, tree_type)
    sep_m_r = _new_xyz_separate_node(group, tree_type)
    sep_m_g = _new_xyz_separate_node(group, tree_type)
    sep_m_b = _new_xyz_separate_node(group, tree_type)

    group.links.new(in_node.outputs['Image'], sep_img.inputs[0])
    group.links.new(in_node.outputs['Output Red'], sep_m_r.inputs[0])
    group.links.new(in_node.outputs['Output Green'], sep_m_g.inputs[0])
    group.links.new(in_node.outputs['Output Blue'], sep_m_b.inputs[0])

    row_specs = [
        ('R', sep_m_r, 320),
        ('G', sep_m_g, 0),
        ('B', sep_m_b, -320),
    ]
    final_nodes = []

    for row_name, row_sep, y_base in row_specs:
        mult0 = _new_math_node(group, tree_type, 'MULTIPLY')
        mult1 = _new_math_node(group, tree_type, 'MULTIPLY')
        mult2 = _new_math_node(group, tree_type, 'MULTIPLY')
        add01 = _new_math_node(group, tree_type, 'ADD')
        addf = _new_math_node(group, tree_type, 'ADD')

        mult0.label = f"Mult_{row_name}0"
        mult1.label = f"Mult_{row_name}1"
        mult2.label = f"Mult_{row_name}2"
        add01.label = f"Add_{row_name}01"
        addf.label = f"Add_{row_name}_Final"

        mult0.location = (-120, y_base + 120)
        mult1.location = (-120, y_base + 40)
        mult2.location = (-120, y_base - 40)
        add01.location = (100, y_base + 80)
        addf.location = (300, y_base + 20)

        group.links.new(sep_img.outputs[0], mult0.inputs[0])
        group.links.new(sep_img.outputs[1], mult1.inputs[0])
        group.links.new(sep_img.outputs[2], mult2.inputs[0])
        group.links.new(row_sep.outputs[0], mult0.inputs[1])
        group.links.new(row_sep.outputs[1], mult1.inputs[1])
        group.links.new(row_sep.outputs[2], mult2.inputs[1])
        group.links.new(mult0.outputs[0], add01.inputs[0])
        group.links.new(mult1.outputs[0], add01.inputs[1])
        group.links.new(add01.outputs[0], addf.inputs[0])
        group.links.new(mult2.outputs[0], addf.inputs[1])

        final_nodes.append(addf)

    group.links.new(final_nodes[0].outputs[0], combine.inputs[0])
    group.links.new(final_nodes[1].outputs[0], combine.inputs[1])
    group.links.new(final_nodes[2].outputs[0], combine.inputs[2])
    if tree_type == 'COMPOSITOR':
        group.links.new(sep_img.outputs['Alpha'], combine.inputs['Alpha'])
    group.links.new(combine.outputs[0], out_node.inputs['Image'])

    in_node.location = (-300, 0)
    out_node.location = (300, 0)
    sep_img.location = (-520, 360)
    sep_m_r.location = (-520, 120)
    sep_m_g.location = (-520, -120)
    sep_m_b.location = (-520, -360)
    combine.location = (520, 0)
    return group


def _prepare_calibration_data(
    self,
    context,
    *,
    require_editor=True,
    normalize_matrix_input=True,
):
    settings = getattr(context.scene, 'macblend_calibrator_settings', None)
    if settings is None:
        return None, None, None, None, None

    image = settings.sample_source_image
    if image is None or not getattr(image, 'mb_sample_data', None):
        self.report({'ERROR'}, "No valid saved source image selected.")
        return None, None, None, None, None

    editor_kind = None
    tree = None
    if require_editor:
        editor_kind = _get_editor_kind(getattr(context, 'space_data', None))
        if editor_kind is None:
            self.report({'ERROR'}, "This operator only works in Shader or Compositor Node Editor.")
            return None, None, None, None, None

        tree = getattr(context.space_data, 'edit_tree', None)
        if tree is None:
            self.report({'ERROR'}, "This panel only works in the Shader or Compositor editor.")
            return None, None, None, None, None

    source_samples = _ordered_image_samples(image)
    if source_samples is None:
        self.report({'ERROR'}, "The image samples do not form a complete 24-patch Macbeth set.")
        return None, None, None, None, None

    if settings.use_reference_target:
        selected_target = settings.target_colorspace or "LINEAR_SRGB_D65"
        try:
            target_samples = _build_reference_samples(context, selected_target)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return None, None, None, None, None
        target_description = f"reference '{selected_target}'"
    else:
        target_image = settings.sample_target_image
        if target_image is None:
            self.report({'ERROR'}, "No saved target image selected.")
            return None, None, None, None, None
        target_samples = _ordered_image_samples(target_image)
        if target_samples is None:
            self.report({'ERROR'}, "The target image samples do not form a complete 24-patch Macbeth set.")
            return None, None, None, None, None
        target_description = f"image '{target_image.name}'"

    standard_patch_names = (
        "Dark Skin", "Light Skin", "Blue Sky", "Foliage", "Blue Flower", "Bluish Green",
        "Orange", "Purplish Blue", "Moderate Red", "Purple", "Yellow Green", "Orange Yellow",
        "Blue", "Green", "Red", "Yellow", "Magenta", "Cyan",
        "White 9.5", "Neutral 8", "Neutral 6.5", "Neutral 5", "Neutral 3.5", "Black 2",
    )
    debug_logging = _debug_logging_enabled(context)

    if debug_logging:
        print("[MacBlend] Source samples in Macbeth slot order:", flush=True)
        for idx, value in enumerate(source_samples):
            patch_name = standard_patch_names[idx] if idx < len(standard_patch_names) else f"slot_{idx}"
            print(f"  slot[{idx}] ({patch_name}) = {tuple(float(v) for v in value)}", flush=True)
        print(f"[MacBlend] Target samples from {target_description} (standard Macbeth order):", flush=True)
        for idx, value in enumerate(target_samples):
            print(f"  target[{idx}] ({standard_patch_names[idx]}) = {tuple(float(v) for v in value)}", flush=True)

        print("[MacBlend] Raw scan-order samples with assigned patch slots:", flush=True)
        for sample in image.mb_sample_data.samples:
            patch_index = int(getattr(sample, 'patch_index', -1))
            if 0 <= patch_index < 24:
                print(f"  scan[{sample.name if hasattr(sample, 'name') else patch_index}] -> slot[{patch_index}] ({standard_patch_names[patch_index]}) = {tuple(float(v) for v in sample.rgb)}", flush=True)

    normalization_factor = 1.0
    matrix_input = source_samples.copy()

    if settings.normalize_calibration:
        neutral_idx = 21
        if neutral_idx >= len(source_samples) or neutral_idx >= len(target_samples):
            self.report({'ERROR'}, "Neutral patch index is out of bounds for normalization.")
            return None, None, None, None, None

        src_grey = source_samples[neutral_idx]
        ref_grey = target_samples[neutral_idx]
        src_luma = float(np.dot(src_grey, core.LUMA_COEFFS_REC709))
        ref_luma = float(np.dot(ref_grey, core.LUMA_COEFFS_REC709))

        if debug_logging:
            print(f"[MacBlend] Neutral patch idx={neutral_idx} src_grey={tuple(float(v) for v in src_grey)} src_luma={src_luma}", flush=True)
            print(f"[MacBlend] Neutral patch idx={neutral_idx} ref_grey={tuple(float(v) for v in ref_grey)} ref_luma={ref_luma}", flush=True)

        if src_luma > 1e-7:
            normalization_factor = ref_luma / src_luma
            if normalize_matrix_input:
                matrix_input = source_samples * normalization_factor
            if debug_logging:
                print(f"[MacBlend] Normalization factor = {normalization_factor}", flush=True)
        else:
            normalization_factor = 1.0

    if debug_logging:
        print("[MacBlend] Matrix input samples after normalization:", flush=True)
        for idx, value in enumerate(matrix_input):
            print(f"  matrix_input[{idx}] = {tuple(float(v) for v in value)}", flush=True)

    try:
        matrix_result = core.calculate_matrix_result(matrix_input, target_samples, debug=debug_logging)
    except core.CalibrationError as exc:
        self.report({'ERROR'}, str(exc))
        return None, None, None, None, None

    matrix_3x3 = matrix_result.matrix
    if matrix_result.condition_number > 1e4:
        self.report(
            {'WARNING'},
            f"Source samples are poorly conditioned ({matrix_result.condition_number:.2e}); verify chart alignment.",
        )
    settings.calculated_matrix = matrix_3x3.flatten()
    settings.calculation_done = True
    settings.normalization_factor = float(normalization_factor)
    settings.matrix_display_string = (
        f"[{matrix_3x3[0,0]:>9.6f} {matrix_3x3[0,1]:>9.6f} {matrix_3x3[0,2]:>9.6f}]\n"
        f"[{matrix_3x3[1,0]:>9.6f} {matrix_3x3[1,1]:>9.6f} {matrix_3x3[1,2]:>9.6f}]\n"
        f"[{matrix_3x3[2,0]:>9.6f} {matrix_3x3[2,1]:>9.6f} {matrix_3x3[2,2]:>9.6f}]"
    )

    return settings, editor_kind, tree, matrix_3x3, normalization_factor


def _scene_linear_working_space(scene):
    try:
        ocio = importlib.import_module('PyOpenColorIO')
        name = ocio.GetCurrentConfig().getRoleColorSpace('scene_linear')
        if name:
            return name, False
    except (ImportError, AttributeError, RuntimeError):
        pass

    sequencer_settings = getattr(scene, 'sequencer_colorspace_settings', None)
    name = getattr(sequencer_settings, 'name', '')
    if name:
        return name, True
    raise ValueError("Could not resolve Blender's scene-linear working colorspace.")


def _lut_target_name(settings):
    if settings.use_reference_target:
        return settings.target_colorspace or "LINEAR_SRGB_D65"
    return lut_writer.image_name_token(settings.sample_target_image.name)


def _build_lut_exports(operator, context, *, size, clamp):
    settings, _editor_kind, _tree, matrix_3x3, normalization_factor = _prepare_calibration_data(
        operator,
        context,
        require_editor=False,
        normalize_matrix_input=False,
    )
    if settings is None:
        return None

    try:
        working_space, used_fallback = _scene_linear_working_space(context.scene)
        neutralize_matrix, match_matrix = lut_writer.compose_export_matrices(
            matrix_3x3,
            normalization_factor,
        )
    except ValueError as exc:
        operator.report({'ERROR'}, str(exc))
        return None

    if used_fallback:
        operator.report({'WARNING'}, "Using Blender's sequencer colorspace as the working-space name.")

    source_name = lut_writer.image_name_token(settings.sample_source_image.name)
    target_name = _lut_target_name(settings)
    normalized = bool(settings.normalize_calibration)
    exports = []
    for mode, matrix in (("Match", match_matrix), ("Neutralize", neutralize_matrix)):
        filename = lut_writer.build_lut_filename(
            working_space,
            source_name,
            target_name,
            normalized=normalized,
            mode=mode,
        )
        lines = lut_writer.generate_cube_lut(matrix, size=size, title=filename[:-5], clamp=clamp)
        exports.append((filename, "\n".join(lines) + "\n"))
    return exports


def _write_lut_exports(directory, exports):
    staged_paths = []
    try:
        for filename, contents in exports:
            descriptor, staged_path = tempfile.mkstemp(
                prefix=f".{filename}.",
                suffix='.tmp',
                dir=directory,
                text=True,
            )
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output_file:
                output_file.write(contents)
            staged_paths.append((staged_path, os.path.join(directory, filename)))

        for staged_path, final_path in staged_paths:
            os.replace(staged_path, final_path)
    finally:
        for staged_path, _final_path in staged_paths:
            if os.path.exists(staged_path):
                os.remove(staged_path)


def _execute_lut_export(operator, context, *, directory, size, clamp, overwrite):
    directory = bpy.path.abspath(directory)
    if not os.path.isdir(directory):
        operator.report({'ERROR'}, "Select an existing export directory.")
        return {'CANCELLED'}

    exports = _build_lut_exports(operator, context, size=size, clamp=clamp)
    if exports is None:
        return {'CANCELLED'}

    final_paths = [os.path.join(directory, filename) for filename, _contents in exports]
    collisions = [path for path in final_paths if os.path.exists(path)]
    if collisions and not overwrite:
        bpy.ops.macblend.confirm_lut_overwrite(
            'INVOKE_DEFAULT',
            directory=directory,
            lut_size=str(size),
            clamp_output=clamp,
            existing_files='\n'.join(os.path.basename(path) for path in collisions),
        )
        return {'FINISHED'}

    try:
        _write_lut_exports(directory, exports)
    except OSError as exc:
        operator.report({'ERROR'}, f"Could not write LUT files: {exc}")
        return {'CANCELLED'}

    operator.report({'INFO'}, f"Exported Match and Neutralize LUTs to '{directory}'.")
    return {'FINISHED'}


def _create_matrix_node(tree, editor_kind, node_name, matrix_3x3, *, label_text, location):
    group = build_matrix_node_group(editor_kind)
    node = _find_owned_node(tree, 'matrix', node_name)
    expected_types = {'ShaderNodeGroup', 'CompositorNodeGroup'}
    if node is not None and node.bl_idname not in expected_types:
        tree.nodes.remove(node)
        node = None
    if node is None:
        node = tree.nodes.new(type='ShaderNodeGroup' if editor_kind == 'SHADER' else 'CompositorNodeGroup')
        node.name = node_name
        _mark_owned(node, 'matrix', node_name)
    node.node_tree = group
    node.label = f"{node_name} ({label_text})"
    node.location = location

    row_values = [
        (float(matrix_3x3[0, 0]), float(matrix_3x3[0, 1]), float(matrix_3x3[0, 2])),
        (float(matrix_3x3[1, 0]), float(matrix_3x3[1, 1]), float(matrix_3x3[1, 2])),
        (float(matrix_3x3[2, 0]), float(matrix_3x3[2, 1]), float(matrix_3x3[2, 2])),
    ]

    if 'Output Red' in node.inputs:
        node.inputs['Output Red'].default_value = row_values[0]
    if 'Output Green' in node.inputs:
        node.inputs['Output Green'].default_value = row_values[1]
    if 'Output Blue' in node.inputs:
        node.inputs['Output Blue'].default_value = row_values[2]

    return node


def _mode_node_name(base_name, mode):
    return f"{base_name}{mode}"


def _sync_exposure_node(tree, editor_kind, matrix_node, scale_value, enabled):
    matrix_key = matrix_node.get(MB_GENERATED_KEY, matrix_node.name)
    exposure_key = f"{matrix_key}:exposure"
    exp_node = _find_owned_node(tree, 'exposure', exposure_key)

    if not enabled:
        if exp_node is None:
            return None
        downstream = [(link.to_node, link.to_socket) for link in tuple(exp_node.outputs[0].links)]
        tree.nodes.remove(exp_node)
        for _to_node, to_socket in downstream:
            tree.links.new(matrix_node.outputs[0], to_socket)
        return None

    expected_type = 'CompositorNodeExposure' if editor_kind == 'COMPOSITOR' else 'ShaderNodeVectorMath'
    repaired_downstream = []
    if exp_node is not None and exp_node.bl_idname != expected_type:
        repaired_downstream = [link.to_socket for link in tuple(exp_node.outputs[0].links)]
        tree.nodes.remove(exp_node)
        exp_node = None
    if exp_node is None:
        exp_node = tree.nodes.new(type=expected_type)
        exp_node.name = f"{matrix_node.name}Exposure"
        _mark_owned(exp_node, 'exposure', exposure_key)

    exp_node.label = f"{matrix_node.label} Exposure"
    exp_node.location = (matrix_node.location[0] + 300, matrix_node.location[1])
    if editor_kind == 'COMPOSITOR':
        exp_node.inputs[1].default_value = math.log2(max(float(scale_value), 1e-8))
    else:
        _set_vector_math_scale_value(exp_node, scale_value)

    for link in tuple(exp_node.inputs[0].links):
        if link.from_node != matrix_node:
            tree.links.remove(link)
    if not any(link.from_node == matrix_node for link in exp_node.inputs[0].links):
        tree.links.new(matrix_node.outputs[0], exp_node.inputs[0])

    for to_socket in repaired_downstream:
        tree.links.new(exp_node.outputs[0], to_socket)

    direct_downstream = [
        (link.to_node, link.to_socket)
        for link in tuple(matrix_node.outputs[0].links)
        if link.to_node != exp_node
    ]
    for to_node, to_socket in direct_downstream:
        for link in tuple(matrix_node.outputs[0].links):
            if link.to_node == to_node and link.to_socket == to_socket:
                tree.links.remove(link)
        tree.links.new(exp_node.outputs[0], to_socket)
    return exp_node


class MB_OT_MatchTransform(bpy.types.Operator):
    bl_idname = "macblend.match_transform"
    bl_label = "Match"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _target_is_selected(context)

    def execute(self, context):
        settings, editor_kind, tree, matrix_3x3, normalization_factor = _prepare_calibration_data(self, context)
        if settings is None:
            return {'CANCELLED'}

        try:
            match_matrix = np.linalg.inv(matrix_3x3)
        except np.linalg.LinAlgError:
            self.report({'ERROR'}, "Calculated matrix is singular and cannot be inverted.")
            return {'CANCELLED'}

        match_name = _mode_node_name(settings.node_name, 'Match')
        match_node = _create_matrix_node(tree, editor_kind, match_name, match_matrix, label_text='Inverse', location=(300, 150))
        match_factor = 1.0 / max(float(settings.normalization_factor), 1e-8)
        _sync_exposure_node(tree, editor_kind, match_node, match_factor, settings.create_exposure_node)

        self.report({'INFO'}, f"Created inverse matrix '{match_name}' with optional exposure scaling.")
        return {'FINISHED'}


class MB_OT_NeutralizeTransform(bpy.types.Operator):
    bl_idname = "macblend.neutralize_transform"
    bl_label = "Neutralize"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _target_is_selected(context)

    def execute(self, context):
        settings, editor_kind, tree, matrix_3x3, normalization_factor = _prepare_calibration_data(self, context)
        if settings is None:
            return {'CANCELLED'}

        neutralize_name = _mode_node_name(settings.node_name, 'Neutralize')
        neutralize_node = _create_matrix_node(tree, editor_kind, neutralize_name, matrix_3x3, label_text='Forward', location=(300, -150))
        _sync_exposure_node(
            tree,
            editor_kind,
            neutralize_node,
            settings.normalization_factor,
            settings.create_exposure_node,
        )

        self.report({'INFO'}, f"Created forward matrix '{neutralize_name}' with optional exposure scaling.")
        return {'FINISHED'}


class MB_OT_ExportLuts(bpy.types.Operator):
    bl_idname = "macblend.export_luts"
    bl_label = "Export LUTs"
    bl_description = (
        "Export Match and Neutralize LUTs named "
        "WorkingSpace_InputImage_Target[_normalized]_Mode.cube"
    )
    bl_options = {'REGISTER'}

    directory: StringProperty(name="Export Directory", subtype='DIR_PATH')
    lut_size: EnumProperty(
        name="LUT Size",
        items=(('17', "17", "17x17x17"), ('33', "33", "33x33x33"), ('65', "65", "65x65x65")),
        default='33',
    )
    clamp_output: BoolProperty(
        name="Clamp to 0-1",
        description="Clamp LUT output values for broad application compatibility",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return _target_is_selected(context)

    def invoke(self, context, event):
        if not self.directory:
            self.directory = bpy.path.abspath('//') if bpy.data.filepath else os.path.expanduser('~')
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return _execute_lut_export(
            self,
            context,
            directory=self.directory,
            size=int(self.lut_size),
            clamp=self.clamp_output,
            overwrite=False,
        )


class MB_OT_ConfirmLutOverwrite(bpy.types.Operator):
    bl_idname = "macblend.confirm_lut_overwrite"
    bl_label = "Replace Existing LUT Files?"

    directory: StringProperty(options={'HIDDEN'}, subtype='DIR_PATH')
    lut_size: EnumProperty(
        options={'HIDDEN'},
        items=(('17', "17", ""), ('33', "33", ""), ('65', "65", "")),
        default='33',
    )
    clamp_output: BoolProperty(options={'HIDDEN'}, default=False)
    existing_files: StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        layout = self.layout
        layout.label(text="The following LUT files already exist:", icon='ERROR')
        for filename in self.existing_files.splitlines():
            layout.label(text=filename)
        layout.label(text="Both Match and Neutralize LUTs will be exported.")

    def execute(self, context):
        return _execute_lut_export(
            self,
            context,
            directory=self.directory,
            size=int(self.lut_size),
            clamp=self.clamp_output,
            overwrite=True,
        )


class MB_PT_CalibrationPanel(bpy.types.Panel):
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_label = 'MacBlend'
    bl_category = 'MacBlend'

    @classmethod
    def poll(cls, context):
        return _get_editor_kind(getattr(context, 'space_data', None)) is not None

    def draw(self, context):
        layout = self.layout
        settings = getattr(context.scene, 'macblend_calibrator_settings', None)
        layout.prop(settings, 'sample_source_image', text='Image')
        layout.prop(settings, 'use_reference_target')
        if settings.use_reference_target:
            layout.prop(settings, 'target_colorspace', text='Target')
        else:
            layout.prop(settings, 'sample_target_image', text='Target')
        layout.prop(settings, 'normalize_calibration', text='Normalize')
        layout.prop(settings, 'create_exposure_node', text='Create Exposure Node')
        layout.prop(settings, 'node_name', text='Node Name')
        row = layout.row(align=True)
        row.operator('macblend.match_transform', text='Match')
        row.operator('macblend.neutralize_transform', text='Neutralize')
        layout.operator('macblend.export_luts', text='Export LUTs', icon='EXPORT')
        if settings.calculation_done:
            box = layout.box()
            box.label(text='Matrix:')
            for line in settings.matrix_display_string.split('\n'):
                box.label(text=line)


classes = (
    MB_OT_MatchTransform,
    MB_OT_NeutralizeTransform,
    MB_OT_ExportLuts,
    MB_OT_ConfirmLutOverwrite,
    MB_PT_CalibrationPanel,
)

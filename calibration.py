import bpy
import math
import json
import os
import numpy as np

from . import core, sampling


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
    if separate_xyz_count < 4 or not any(node.bl_idname in combine_xyz_types for node in group.nodes):
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

    json_path = None
    if hasattr(addon_prefs, 'get_effective_json_path'):
        json_path = addon_prefs.get_effective_json_path()
    else:
        json_path = getattr(addon_prefs, 'json_file_path', None)

    if not json_path:
        addon_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(addon_dir, "mmColorTarget_colorspace_transforms.json")

    if not os.path.exists(json_path):
        return None

    try:
        with open(json_path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    except Exception:
        return None


def _build_reference_samples(context, selected_target):
    if selected_target == "LINEAR_SRGB_D65":
        return core.MACBETH_LINEAR_SRGB_D65_BASE.copy()

    json_data = _load_json_data(context)
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


def build_matrix_node_group(tree_type):
    group_name = "MB ColorMatrix (Shader)" if tree_type == 'SHADER' else "MB ColorMatrix (Compositor)"
    group = bpy.data.node_groups.get(group_name)
    if group is not None:
        if _group_is_usable(group):
            return group
        try:
            bpy.data.node_groups.remove(group, do_unlink=True)
        except TypeError:
            bpy.data.node_groups.remove(group)
        group = None

    if tree_type == 'SHADER':
        group = bpy.data.node_groups.new(name=group_name, type='ShaderNodeTree')
    else:
        group = bpy.data.node_groups.new(name=group_name, type='CompositorNodeTree')

    _add_group_socket(group, in_out='INPUT', socket_type='NodeSocketColor', name='Image')
    _add_group_socket(group, in_out='INPUT', socket_type='NodeSocketVector', name='Output Red')
    _add_group_socket(group, in_out='INPUT', socket_type='NodeSocketVector', name='Output Green')
    _add_group_socket(group, in_out='INPUT', socket_type='NodeSocketVector', name='Output Blue')
    _add_group_socket(group, in_out='OUTPUT', socket_type='NodeSocketColor', name='Image')

    in_node = group.nodes.new(type='NodeGroupInput')
    out_node = group.nodes.new(type='NodeGroupOutput')
    sep_img = _new_xyz_separate_node(group, tree_type)
    sep_m_r = _new_xyz_separate_node(group, tree_type)
    sep_m_g = _new_xyz_separate_node(group, tree_type)
    sep_m_b = _new_xyz_separate_node(group, tree_type)
    combine = _new_xyz_combine_node(group, tree_type)

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
    group.links.new(combine.outputs[0], out_node.inputs['Image'])

    in_node.location = (-300, 0)
    out_node.location = (300, 0)
    sep_img.location = (-520, 360)
    sep_m_r.location = (-520, 120)
    sep_m_g.location = (-520, -120)
    sep_m_b.location = (-520, -360)
    combine.location = (520, 0)
    return group


def _prepare_calibration_data(self, context):
    settings = getattr(context.scene, 'macblend_calibrator_settings', None)
    if settings is None:
        settings = getattr(context.scene, 'macbeth_calibrator_settings', None)
    if settings is None:
        return None, None, None, None, None

    image = settings.sample_source_image
    if image is None or not getattr(image, 'mb_sample_data', None):
        self.report({'ERROR'}, "No valid saved source image selected.")
        return None, None, None, None, None

    data = image.mb_sample_data
    if not data.is_saved or len(data.samples) == 0:
        self.report({'ERROR'}, "The selected image has no saved Macbeth data.")
        return None, None, None, None, None

    editor_kind = _get_editor_kind(getattr(context, 'space_data', None))
    if editor_kind is None:
        self.report({'ERROR'}, "This operator only works in Shader or Compositor Node Editor.")
        return None, None, None, None, None

    tree = getattr(context.space_data, 'edit_tree', None)
    if tree is None:
        self.report({'ERROR'}, "This panel only works in the Shader or Compositor editor.")
        return None, None, None, None, None

    ordered_samples = [None] * 24
    for sample in data.samples:
        if not hasattr(sample, 'patch_index'):
            continue
        patch_index = int(getattr(sample, 'patch_index', -1))
        if 0 <= patch_index < 24:
            ordered_samples[patch_index] = tuple(float(channel) for channel in sample.rgb)

    source_samples = np.array([value for value in ordered_samples if value is not None], dtype=np.float32)
    if source_samples.shape != (24, 3):
        self.report({'ERROR'}, "The image samples do not form a complete 24-patch Macbeth set.")
        return None, None, None, None, None

    selected_target = settings.target_colorspace or "LINEAR_SRGB_D65"
    try:
        ref = _build_reference_samples(context, selected_target)
    except ValueError as exc:
        self.report({'ERROR'}, str(exc))
        return None, None, None, None, None

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
        print("[MacBlend] Reference samples (standard Macbeth order):", flush=True)
        for idx, value in enumerate(ref):
            print(f"  ref[{idx}] ({standard_patch_names[idx]}) = {tuple(float(v) for v in value)}", flush=True)

        print("[MacBlend] Raw scan-order samples with assigned patch slots:", flush=True)
        for sample in data.samples:
            patch_index = int(getattr(sample, 'patch_index', -1))
            if 0 <= patch_index < 24:
                print(f"  scan[{sample.name if hasattr(sample, 'name') else patch_index}] -> slot[{patch_index}] ({standard_patch_names[patch_index]}) = {tuple(float(v) for v in sample.rgb)}", flush=True)

    normalization_factor = 1.0
    matrix_input = source_samples.copy()

    if settings.normalize_calibration:
        neutral_idx = 21
        if neutral_idx >= len(source_samples) or neutral_idx >= len(ref):
            self.report({'ERROR'}, "Neutral patch index is out of bounds for normalization.")
            return None, None, None, None, None

        src_grey = source_samples[neutral_idx]
        ref_grey = ref[neutral_idx]
        src_luma = float(np.dot(src_grey, core.LUMA_COEFFS_REC709))
        ref_luma = float(np.dot(ref_grey, core.LUMA_COEFFS_REC709))

        if debug_logging:
            print(f"[MacBlend] Neutral patch idx={neutral_idx} src_grey={tuple(float(v) for v in src_grey)} src_luma={src_luma}", flush=True)
            print(f"[MacBlend] Neutral patch idx={neutral_idx} ref_grey={tuple(float(v) for v in ref_grey)} ref_luma={ref_luma}", flush=True)

        if src_luma > 1e-7:
            normalization_factor = ref_luma / src_luma
            matrix_input = source_samples * normalization_factor
            if debug_logging:
                print(f"[MacBlend] Normalization factor = {normalization_factor}", flush=True)
        else:
            normalization_factor = 1.0

    if debug_logging:
        print("[MacBlend] Matrix input samples after normalization:", flush=True)
        for idx, value in enumerate(matrix_input):
            print(f"  matrix_input[{idx}] = {tuple(float(v) for v in value)}", flush=True)

    matrix_3x3 = core.calculate_matrix(matrix_input, ref, debug=debug_logging)
    if matrix_3x3 is None:
        self.report({'ERROR'}, "Matrix calculation failed.")
        return None, None, None, None, None

    matrix_3x3 = np.asarray(matrix_3x3, dtype=np.float32)
    settings.calculated_matrix = matrix_3x3.flatten()
    settings.calculation_done = True
    settings.normalization_factor = float(normalization_factor)
    settings.matrix_display_string = (
        f"[{matrix_3x3[0,0]:>9.6f} {matrix_3x3[0,1]:>9.6f} {matrix_3x3[0,2]:>9.6f}]\n"
        f"[{matrix_3x3[1,0]:>9.6f} {matrix_3x3[1,1]:>9.6f} {matrix_3x3[1,2]:>9.6f}]\n"
        f"[{matrix_3x3[2,0]:>9.6f} {matrix_3x3[2,1]:>9.6f} {matrix_3x3[2,2]:>9.6f}]"
    )

    return settings, editor_kind, tree, matrix_3x3, normalization_factor


def _create_matrix_node(tree, editor_kind, settings, node_name, matrix_3x3, *, label_text, location):
    group = build_matrix_node_group(editor_kind)
    node = tree.nodes.get(node_name)
    if node and node.bl_idname != 'ShaderNodeGroup' and node.bl_idname != 'CompositorNodeGroup':
        tree.nodes.remove(node)
        node = None
    if node is None:
        node = tree.nodes.new(type='ShaderNodeGroup' if editor_kind == 'SHADER' else 'CompositorNodeGroup')
        node.name = node_name
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


def _create_exposure_node(tree, editor_kind, node, scale_value, *, label_text):
    node_name = node.name
    exp_name = f"{node_name}Exposure"
    if editor_kind == 'COMPOSITOR':
        exp_node = tree.nodes.get(exp_name)
        if exp_node is None:
            exp_node = tree.nodes.new(type='CompositorNodeExposure')
            exp_node.name = exp_name
        exp_node.label = exp_name
        exp_node.location = (node.location[0] + 300, node.location[1])
        exp_node.inputs[1].default_value = math.log2(max(float(scale_value), 1e-8))
        if not node.outputs[0].is_linked or not exp_node.inputs[0].is_linked:
            if exp_node.inputs[0].is_linked is False:
                tree.links.new(node.outputs[0], exp_node.inputs[0])
        return exp_node

    exp_node = tree.nodes.get(exp_name)
    if exp_node is None:
        exp_node = tree.nodes.new(type='ShaderNodeVectorMath')
        exp_node.name = exp_name
    exp_node.label = exp_name
    exp_node.location = (node.location[0] + 300, node.location[1])
    _set_vector_math_scale_value(exp_node, scale_value)
    if not node.outputs[0].is_linked or not exp_node.inputs[0].is_linked:
        if exp_node.inputs[0].is_linked is False:
            tree.links.new(node.outputs[0], exp_node.inputs[0])
    return exp_node


class MB_OT_MatchTransform(bpy.types.Operator):
    bl_idname = "macblend.match_transform"
    bl_label = "Match"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings, editor_kind, tree, matrix_3x3, normalization_factor = _prepare_calibration_data(self, context)
        if settings is None:
            return {'CANCELLED'}

        try:
            match_matrix = np.linalg.inv(matrix_3x3)
        except np.linalg.LinAlgError:
            match_matrix = np.eye(3, dtype=np.float32)

        match_name = _mode_node_name(settings.node_name, 'Match')
        match_node = _create_matrix_node(tree, editor_kind, settings, match_name, match_matrix, label_text='Inverse', location=(300, 150))

        if settings.create_exposure_node:
            match_factor = 1.0 / max(float(settings.normalization_factor), 1e-8)
            _create_exposure_node(tree, editor_kind, match_node, match_factor, label_text='Inverse Exposure')

        self.report({'INFO'}, f"Created inverse matrix '{match_name}' with optional exposure scaling.")
        return {'FINISHED'}


class MB_OT_NeutralizeTransform(bpy.types.Operator):
    bl_idname = "macblend.neutralize_transform"
    bl_label = "Neutralize"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings, editor_kind, tree, matrix_3x3, normalization_factor = _prepare_calibration_data(self, context)
        if settings is None:
            return {'CANCELLED'}

        neutralize_name = _mode_node_name(settings.node_name, 'Neutralize')
        neutralize_node = _create_matrix_node(tree, editor_kind, settings, neutralize_name, matrix_3x3, label_text='Forward', location=(300, -150))

        if settings.create_exposure_node:
            _create_exposure_node(tree, editor_kind, neutralize_node, settings.normalization_factor, label_text='Forward Exposure')

        self.report({'INFO'}, f"Created forward matrix '{neutralize_name}' with optional exposure scaling.")
        return {'FINISHED'}


class MB_OT_CreateTransform(bpy.types.Operator):
    bl_idname = "macblend.create_transform"
    bl_label = "Create Transform"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return bpy.ops.macblend.match_transform('INVOKE_DEFAULT')


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
        if settings is None:
            settings = getattr(context.scene, 'macbeth_calibrator_settings', None)
        layout.prop(settings, 'sample_source_image', text='Image')
        layout.prop(settings, 'target_colorspace', text='Target')
        layout.prop(settings, 'normalize_calibration', text='Normalize to Mid Grey')
        layout.prop(settings, 'create_exposure_node', text='Create Exposure Node')
        layout.prop(settings, 'node_name', text='Node Name')
        row = layout.row(align=True)
        row.operator('macblend.match_transform', text='Match')
        row.operator('macblend.neutralize_transform', text='Neutralize')
        if settings.calculation_done:
            box = layout.box()
            box.label(text='Matrix:')
            for line in settings.matrix_display_string.split('\n'):
                box.label(text=line)


classes = (
    MB_OT_MatchTransform,
    MB_OT_NeutralizeTransform,
    MB_OT_CreateTransform,
    MB_PT_CalibrationPanel,
)

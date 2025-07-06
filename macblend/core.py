import numpy as np
import sys
import mathutils

# --- Constants ---
MACBETH_LINEAR_SRGB_D65_BASE = np.array([
    [0.17355167, 0.07874029, 0.05326058], [0.55946176, 0.27734355, 0.21194777], [0.10509124, 0.18955202, 0.32693865],
    [0.10506442, 0.15021316, 0.05221047], [0.22885963, 0.21350031, 0.42346758], [0.11449231, 0.50663347, 0.41229432],
    [0.74499115, 0.20172072, 0.0325174 ], [0.0606182 , 0.10259253, 0.38373146], [0.56055825, 0.08072134, 0.11432307],
    [0.10983077, 0.04254067, 0.13682661], [0.32967574, 0.49495612, 0.04886544], [0.7689789 , 0.35655545, 0.02534346],
    [0.0225082 , 0.04870543, 0.28081679], [0.0444356 , 0.29068277, 0.06458335], [0.44636923, 0.03676343, 0.0406788 ],
    [0.83803037, 0.57175305, 0.01273052], [0.52392518, 0.07924915, 0.28656418], [0.0       , 0.23415773, 0.37506175],
    [0.87919095, 0.88476747, 0.8349529 ], [0.58443959, 0.59212352, 0.58458201], [0.35767777, 0.36706043, 0.36528718],
    [0.19008669, 0.19086038, 0.1898278 ], [0.08593528, 0.08873843, 0.08978779], [0.03135966, 0.03149993, 0.03231098]
], dtype=np.float32)

LUMA_COEFFS_ACES = np.array([0.27222872, 0.67408177, 0.05368952], dtype=np.float32)

def sample_image_color(image, px, py, sample_size):
    """Samples average RGB from image.pixels at (px, py) over a box."""
    fallback_color = (0.0, 0.0, 0.0)
    if not image or not image.has_data:
        return fallback_color
    try:
        width, height = image.size
    except Exception as e:
        print(f"Error: Cannot get dimensions for image '{image.name}': {e}")
        return fallback_color
    if not (0 <= px < width and 0 <= py < height):
        return fallback_color
    if sample_size <= 0:
        sample_size = 1
    try:
        image_pixels_sequence = image.pixels[:]
        if not image_pixels_sequence:
            return fallback_color
        pixels_np = np.fromiter(image_pixels_sequence, dtype=np.float32)
        expected_len = width * height * 4
        if pixels_np.size != expected_len:
            return fallback_color
        pixels_np = pixels_np.reshape((height, width, 4))
    except Exception as e:
        print(f"Error accessing image pixels for '{image.name}': {e}")
        return fallback_color

    half_size = sample_size // 2
    y_start = max(0, py - half_size)
    y_end = min(height, py + half_size + (sample_size % 2))
    x_start = max(0, px - half_size)
    x_end = min(width, px + half_size + (sample_size % 2))

    if y_start >= y_end or x_start >= x_end:
        try:
            safe_py = max(0, min(height - 1, py))
            safe_px = max(0, min(width - 1, px))
            return tuple(pixels_np[safe_py, safe_px, :3])
        except IndexError:
            return fallback_color
    try:
        sample_region = pixels_np[y_start:y_end, x_start:x_end, :3]
        if sample_region.size > 0:
            average_color = np.mean(sample_region, axis=(0, 1))
            average_color_clamped = np.maximum(0.0, average_color)
            return tuple(average_color_clamped)
        else:
            safe_py = max(0, min(height - 1, py))
            safe_px = max(0, min(width - 1, px))
            return tuple(np.maximum(0.0, pixels_np[safe_py, safe_px, :3]))
    except Exception as e:
        print(f"Error sampling region at ({px},{py}): {e}")
        return fallback_color

def calculate_matrix(input_samples, ref_samples):
    """Calculates the 3x3 calibration matrix using numpy least squares."""
    print("      Calculating matrix...")
    if not isinstance(input_samples, np.ndarray) or input_samples.shape != (24, 3):
        print(f"      Err: Invalid input samples. Shape: {input_samples.shape if isinstance(input_samples, np.ndarray) else type(input_samples)}")
        return None
    if not isinstance(ref_samples, np.ndarray) or ref_samples.shape != (24, 3):
        print(f"      Err: Invalid ref samples. Shape: {ref_samples.shape if isinstance(ref_samples, np.ndarray) else type(ref_samples)}")
        return None
    if np.any(np.isnan(input_samples)) or np.any(np.isinf(input_samples)):
        print("      Err: Input samples contain NaN or Inf values.")
        return None
    if np.any(np.isnan(ref_samples)) or np.any(np.isinf(ref_samples)):
        print("      Err: Reference samples contain NaN or Inf values.")
        return None
    try:
        rcond_val = sys.float_info.epsilon * max(input_samples.shape)
        result_x, residuals, rank, s = np.linalg.lstsq(input_samples, ref_samples, rcond=rcond_val)
        matrix_calculated = result_x
        print(f"        lstsq residuals: {residuals}")
        print(f"        lstsq rank: {rank}, singular values: {s[:5]}...")
    except np.linalg.LinAlgError as e:
        print(f"      LinAlgError during least squares calculation: {e}")
        return None
    except Exception as e:
        print(f"      Unexpected error during least squares calculation: {e}")
        return None
    if matrix_calculated.shape != (3, 3):
        print(f"      Err: Resulting matrix shape is incorrect: {matrix_calculated.shape}")
        return None
    matrix_final = matrix_calculated.T
    print("        Matrix calculation successful.")
    return matrix_final.tolist()

def run_calculation(context, operator, helpers):
    """
    The main entry point for the matrix calculation logic.
    This function contains the core logic originally in the MB_OT_CalculateMatrix operator.
    'helpers' is an object/dict containing functions passed from the __init__ module
    to avoid circular dependencies.
    """
    print("\n>>> Core Calculation Logic Starting...")
    
    settings = context.scene.macbeth_calibrator_settings

    json_data = helpers['load_json_data'](context)
    if json_data is None:
        operator.report({'WARNING'}, "Failed to load JSON data. Only 'Linear sRGB D65' target is available.")

    selected_target = settings.target_colorspace
    print(f"--- Selected Target Colorspace: {selected_target} ---")

    try:
        if settings is None:
            raise ValueError("Addon settings instance is None.")
        img = settings.image
        cam = settings.cam
        collection_name = settings.marker_collection_name
        marker_collection = helpers['bpy'].data.collections.get(collection_name)
        if not marker_collection:
            raise ValueError(f"Marker collection '{collection_name}' not found.")
        markers = sorted([o for o in marker_collection.objects if o.name.startswith("MB_Sample_")], key=lambda obj: obj.name)
        if len(markers) < 24:
            raise ValueError(f"Expected 24 markers, found {len(markers)}.")
        markers = markers[:24]
        if not img or not img.has_data:
            raise ValueError("Input Image not set or has no data.")
        if not cam or cam.type != 'CAMERA':
            raise ValueError("Camera not set or invalid.")
        if not all(markers) or not all(m.type == 'CURVE' for m in markers):
            raise ValueError("Markers invalid (expected CURVE).")
        img_w, img_h = img.size
        if img_w <= 0 or img_h <= 0:
            raise ValueError(f"Invalid image dimensions: {img_w}x{img_h}")
        print("      Initial checks OK.")
    except Exception as e_setup:
        print(f"      ERROR during initial setup: {e_setup}")
        helpers['traceback'].print_exc()
        operator.report({'ERROR'}, f"Initial setup error: {e_setup}")
        if settings:
            settings.matrix_display_string = f"Setup Error: {e_setup}"
        return {'CANCELLED'}

    print("      Forcing dependency graph update to get latest marker positions...")
    context.view_layer.update()
    print("      Update complete.")
    
    raw_set_successfully = False
    pixel_coords_list = []
    original_view_transform = None
    input_samples_raw = None

    try:
        print("      Block: Projecting sample markers...")
        ndc_coords = [helpers['get_projected_coords'](context, cam, m) for m in markers]
        if not all(ndc is not None for ndc in ndc_coords):
            raise ValueError("Marker projection failed.")
        pixel_coords_list = [helpers['get_pixel_coords'](ndc, img_w, img_h) for ndc in ndc_coords]
        if not all(p is not None for p in pixel_coords_list):
            raise ValueError("Pixel coordinate conversion failed.")
        print(f"        Projected {len(pixel_coords_list)} marker centers.")

        print("      Block: Calculating Sample Size in Pixels...")
        try:
            corners = [settings.corner_tl, settings.corner_tr, settings.corner_br, settings.corner_bl]
            corner_ndc = [helpers['get_projected_coords'](context, cam, c) for c in corners]
            if not all(corner_ndc):
                raise ValueError("Could not project all rig corners.")
            
            corner_px = [helpers['get_pixel_coords'](ndc, img_w, img_h) for ndc in corner_ndc]
            tl_px, tr_px, br_px, bl_px = [mathutils.Vector(p) for p in corner_px]

            top_w = (tr_px - tl_px).length
            bot_w = (br_px - bl_px).length
            cell_w_px = ((top_w + bot_w) / 2) / 6

            left_h = (bl_px - tl_px).length
            right_h = (br_px - tr_px).length
            cell_h_px = ((left_h + right_h) / 2) / 4
            
            max_diameter_px = min(cell_w_px, cell_h_px)
            current_sample_size = int(max_diameter_px * (settings.sample_size / 100.0))
            current_sample_size = max(1, current_sample_size) # Ensure it's at least 1px
            print(f"        Calculated pixel sample size: {current_sample_size}px")
        except Exception as e_ss:
            print(f"        WARNING: Could not calculate dynamic pixel sample size ({e_ss}). Falling back to 10px.")
            current_sample_size = 10

        print("      Block: Setting up Color Management and Sampling...")
        try:
            original_view_transform = context.scene.view_settings.view_transform
            print(f"        Original View Transform: '{original_view_transform}'")
            TARGET_VIEW = 'Raw'
            print(f"        Attempting to set View Transform to '{TARGET_VIEW}'...")
            context.scene.view_settings.view_transform = TARGET_VIEW
            helpers['bpy'].context.view_layer.update()
            if context.scene.view_settings.view_transform == TARGET_VIEW:
                print(f"        Successfully set View Transform to '{TARGET_VIEW}'.")
                raw_set_successfully = True
            else:
                print(f"        WARNING: Failed set View Transform to '{TARGET_VIEW}'.")
                operator.report({'WARNING'}, f"Failed set View Transform to '{TARGET_VIEW}'.")
        except Exception as e_cm_set:
            print(f"      ERROR setting View Transform: {e_cm_set}")
            operator.report({'ERROR'}, f"CM Setup Error: {e_cm_set}")

        print(f"        Sampling {len(markers)} patches with size {current_sample_size}...")
        input_samples_list = []
        if not img.has_data:
            raise ValueError("Image data lost before sampling loop.")
        if pixel_coords_list is None:
            raise ValueError("Pixel coordinates list is None before sampling loop.")

        print("\n        --- Sampled Patch Values (Scene Linear) ---")
        for i, coords in enumerate(pixel_coords_list):
            if coords is None or not isinstance(coords, (tuple, list)) or len(coords) != 2:
                print(f"        --> WARNING: Invalid pixel coordinates for patch {i + 1}.")
                linear_color_rgb = (0.0, 0.0, 0.0)
            else:
                px, py = coords
                sampled_color_rgb = sample_image_color(img, px, py, current_sample_size)
                if sampled_color_rgb is None or not isinstance(sampled_color_rgb, (tuple, list)) or len(sampled_color_rgb) != 3:
                    print(f"        --> WARNING: Invalid sample patch {i + 1}.")
                    linear_color_rgb = (0.0, 0.0, 0.0)
                else:
                    if raw_set_successfully:
                        linear_color_rgb = tuple(max(0.0, val) for val in sampled_color_rgb)
                    else:
                        try:
                            clamped_color = tuple(max(0.0, min(1.0, val)) for val in sampled_color_rgb)
                            linear_color_rgb = helpers['linearize_color'](clamped_color)
                        except Exception as e_lin:
                            print(f"        --> ERROR linearizing patch {i + 1}: {e_lin}.")
                            linear_color_rgb = (0.0, 0.0, 0.0)
            
            input_samples_list.append(linear_color_rgb)
            patch_name = helpers['MACBETH_PATCH_NAMES'][i]
            print(f"        {i+1:>2d}: {patch_name:<16} R={linear_color_rgb[0]:.6f} G={linear_color_rgb[1]:.6f} B={linear_color_rgb[2]:.6f}")
        print("        -------------------------------------------\n")

        print(f"        Finished sampling. Collected {len(input_samples_list)} samples.")
        if len(input_samples_list) != 24:
            raise ValueError(f"Expected 24 samples, got {len(input_samples_list)}.")

        input_samples_raw = np.array(input_samples_list, dtype=np.float32)
        if input_samples_raw.shape != (24, 3):
            raise ValueError(f"Input samples shape incorrect: {input_samples_raw.shape}")
        print("      Sampling OK (Result is in Scene Linear Color Space - assumed ACEScg).")

    except Exception as e_sampling:
        print(f"      ERROR during sampling/projection/linearization: {e_sampling}")
        helpers['traceback'].print_exc()
        operator.report({'ERROR'}, f"Sampling error: {e_sampling}")
        input_samples_raw = None
        if settings:
            settings.calculation_done = False
            settings.calculated_matrix = [1,0,0, 0,1,0, 0,0,1]
            settings.matrix_display_string = f"Sampling Error: {e_sampling}"
    finally:
        if original_view_transform is not None and hasattr(context.scene, 'view_settings') and context.scene.view_settings.view_transform != original_view_transform:
            print(f"        Attempting to restore View Transform to '{original_view_transform}'...")
            try:
                context.scene.view_settings.view_transform = original_view_transform
                helpers['bpy'].context.view_layer.update()
                print(f"        Successfully restored View Transform.")
            except Exception as e_cm_restore:
                print(f"      ERROR restoring original view transform '{original_view_transform}': {e_cm_restore}")
                operator.report({'ERROR'}, f"CM Restore Error: {e_cm_restore}")
        elif original_view_transform is not None:
            print(f"        View Transform was not changed from original ('{original_view_transform}'). No restore needed.")

    if input_samples_raw is not None:
        print("--- Entering Calculation Block ---")
        input_samples_normalized = None
        try:
            print(f"      Block: Generating reference chart for '{selected_target}'...")
            if selected_target == "LINEAR_SRGB_D65":
                ref_samples = MACBETH_LINEAR_SRGB_D65_BASE.copy()
            else:
                if json_data is None:
                    raise ValueError(f"Cannot generate reference for '{selected_target}', JSON data is missing.")
                print(f"Generating reference: Converting Linear sRGB D65 base to '{selected_target}'...")
                try:
                    srgb_to_xyz_m = np.array(json_data["sRGB_to_XYZ_matrix"], dtype=np.float32)
                    base_xyz_d65 = np.dot(MACBETH_LINEAR_SRGB_D65_BASE, srgb_to_xyz_m.T)
                    xyz_to_target_m = np.array(json_data["XYZ_to_RGB_matrices"][selected_target], dtype=np.float32)
                    target_whitepoint = json_data["whitepoints"].get(selected_target, 'D65')
                    print(f"  Target whitepoint: {target_whitepoint}")

                    cat_matrix = np.identity(3, dtype=np.float32)
                    if target_whitepoint != 'D65':
                        cat_key = f"D65_to_{target_whitepoint}"
                        if cat_key in json_data["CAT_matrices"]:
                            cat_matrix = np.array(json_data["CAT_matrices"][cat_key], dtype=np.float32)
                            print(f"  Applying CAT: {cat_key}")
                        else:
                            print(f"  Warning: CAT matrix '{cat_key}' not found in JSON. Skipping CAT.")

                    xyz_adapted = np.dot(base_xyz_d65, cat_matrix.T)
                    ref_samples = np.dot(xyz_adapted, xyz_to_target_m.T)
                    ref_samples = np.maximum(0.0, ref_samples).astype(np.float32)
                    print(f"  Successfully generated reference values for '{selected_target}'.")
                except Exception as e:
                    print(f"Reference Error: Failed during matrix multiplication for '{selected_target}': {e}")
                    helpers['traceback'].print_exc()
                    raise ValueError(f"Failed to generate reference for '{selected_target}'")

            print("      Reference Chart Generated OK.")

            print("\n        --- Reference Patch Values ---")
            for i, p_ref in enumerate(ref_samples):
                patch_name = helpers['MACBETH_PATCH_NAMES'][i]
                print(f"        {i+1:>2d}: {patch_name:<16} R={p_ref[0]:.6f} G={p_ref[1]:.6f} B={p_ref[2]:.6f}")
            print("        ------------------------------\n")

            print("      Block: Normalization...")
            input_samples_normalized = input_samples_raw.copy()
            if settings.chroma_only:
                print("        Normalize Luminance enabled.")
                neutral_idx = helpers['NEUTRAL_5_INDEX']
                if neutral_idx >= len(input_samples_normalized) or neutral_idx >= len(ref_samples):
                    raise IndexError("Neutral patch index out of bounds.")
                i_grey = input_samples_normalized[neutral_idx]
                r_grey = ref_samples[neutral_idx]
                print(f"          Input Grey (ACEScg): {np.round(i_grey, 4)}")
                print(f"          Ref Grey ({selected_target}): {np.round(r_grey, 4)}")

                i_lum = np.dot(i_grey, LUMA_COEFFS_ACES)
                r_lum = np.dot(r_grey, LUMA_COEFFS_ACES)

                print(f"          Input Lum (ACES): {i_lum:.6f}, Ref Lum ({selected_target}, ACES): {r_lum:.6f}")
                if i_lum > 1e-7:
                    norm_factor = r_lum / i_lum
                    print(f"          Norm Factor: {norm_factor:.6f}")
                    if abs(norm_factor - 1.0) > 1e-6:
                        input_samples_normalized = input_samples_normalized * norm_factor
                        print("          Applied normalization.")
                    else:
                        print("          Norm factor close to 1.0, no change.")
                else:
                    print("          Input grey lum near zero. Skipping norm.")
            else:
                print("        Normalize Luminance disabled.")
            print("      Normalization OK.")

            print("      Block: Calculating Matrix...")
            if input_samples_normalized is None:
                raise ValueError("Normalized samples None before calc.")
            matrix = calculate_matrix(input_samples_normalized, ref_samples)

            if matrix:
                matrix_np = np.array(matrix)
                settings.calculated_matrix = matrix_np.flatten()
                settings.calculation_done = True
                display_str = f"[{matrix_np[0,0]:>9.6f} {matrix_np[0,1]:>9.6f} {matrix_np[0,2]:>9.6f}]\n" + f"[{matrix_np[1,0]:>9.6f} {matrix_np[1,1]:>9.6f} {matrix_np[1,2]:>9.6f}]\n" + f"[{matrix_np[2,0]:>9.6f} {matrix_np[2,1]:>9.6f} {matrix_np[2,2]:>9.6f}]"
                settings.matrix_display_string = display_str
                print("        Calculated Matrix (Stored):")
                for row in matrix_np:
                    print(f"          [{row[0]:>9.6f} {row[1]:>9.6f} {row[2]:>9.6f}]")
                operator.report({'INFO'}, "Calculated matrix successfully.")
                print("      Matrix Calculation OK.")
            else:
                settings.matrix_display_string = "Matrix calculation failed (returned None)."
                settings.calculation_done = False
                settings.calculated_matrix = [1,0,0, 0,1,0, 0,0,1]
                operator.report({'ERROR'}, "Matrix calculation failed.")
        except Exception as e_calc:
            print(f"      ERROR during calculation block: {e_calc}")
            helpers['traceback'].print_exc()
            operator.report({'ERROR'}, f"Calculation error: {e_calc}")
            if settings:
                settings.calculation_done = False
                settings.calculated_matrix = [1,0,0, 0,1,0, 0,0,1]
                settings.matrix_display_string = f"Calculation Error: {e_calc}"
    else:
        print("--- Skipping Calculation Block (Sampling Failed) ---")

    print("      Attempting UI redraw...")
    try:
        if context.area:
            context.area.tag_redraw()
        print("      Tagged UI for redraw.")
    except Exception as e_redraw:
        print(f"      ERROR during UI redraw: {e_redraw}")

    print(f">>> Core Calculation Logic Finished.")
    return {'FINISHED'} 
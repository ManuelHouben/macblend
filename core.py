import numpy as np

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

# Legacy CalibrateMacbeth.nk behavior uses Rec.709 luminance coefficients for chroma-only normalization.
LUMA_COEFFS_REC709 = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

def sample_image_color(pixel_buffer, width, height, px, py, sample_size):
    """Samples average RGB from a NumPy pixel array at (px, py) over a box."""
    fallback_color = (0.0, 0.0, 0.0)

    if not (0 <= px < width and 0 <= py < height):
        return fallback_color

    if sample_size <= 0:
        sample_size = 1

    if isinstance(pixel_buffer, np.ndarray) and pixel_buffer.ndim == 1:
        pixels_np = pixel_buffer.reshape((height, width, -1))
    elif isinstance(pixel_buffer, np.ndarray) and pixel_buffer.ndim == 3:
        pixels_np = pixel_buffer
    else:
        try:
            pixels_np = np.asarray(pixel_buffer, dtype=np.float32).reshape((height, width, -1))
        except Exception:
            return fallback_color

    half_size = sample_size // 2
    y_start = max(0, py - half_size)
    y_end = min(height, py + half_size + (sample_size % 2))
    x_start = max(0, px - half_size)
    x_end = min(width, px + half_size + (sample_size % 2))

    if y_start >= y_end or x_start >= x_end:
        safe_py = max(0, min(height - 1, py))
        safe_px = max(0, min(width - 1, px))
        return tuple(pixels_np[safe_py, safe_px, :3])

    try:
        sample_region = pixels_np[y_start:y_end, x_start:x_end, :3]
        if sample_region.size > 0:
            average_color = np.mean(sample_region, axis=(0, 1))
            return tuple(average_color)

        safe_py = max(0, min(height - 1, py))
        safe_px = max(0, min(width - 1, px))
        return tuple(pixels_np[safe_py, safe_px, :3])
    except Exception as e:
        print(f"Error sampling region at ({px},{py}): {e}")
        return fallback_color

def calculate_matrix(input_samples, ref_samples):
    """Calculates the 3x3 calibration matrix using numpy least squares."""
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
    if not np.any(input_samples) or not np.any(ref_samples):
        print("      Err: Input or reference samples are all zeros.")
        return None
    try:
        # Match the Nuke tools' legacy least-squares behavior: solve A x = B and
        # transpose the result before flattening / storing it.
        result_x, residuals, rank, s = np.linalg.lstsq(input_samples, ref_samples, rcond=-1)
        matrix_calculated = result_x
        print(f"        lstsq rank: {rank}, residuals: {residuals}")
        print("        Raw lstsq matrix:")
        for row in matrix_calculated:
            print(f"          [{row[0]:>9.6f} {row[1]:>9.6f} {row[2]:>9.6f}]")
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
    print("        Nuke-style transposed matrix:")
    for row in matrix_final:
        print(f"          [{row[0]:>9.6f} {row[1]:>9.6f} {row[2]:>9.6f}]")
    return matrix_final.tolist()

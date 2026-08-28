import math
import re
from pathlib import Path

import numpy as np


LUT_SIZES = (17, 33, 65)
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _validated_matrix(matrix):
    validated = np.asarray(matrix, dtype=np.float64)
    if validated.shape not in {(3, 3), (3, 4)}:
        raise ValueError("LUT matrix must be a finite 3x3 or 3x4 matrix.")
    if not np.all(np.isfinite(validated)):
        raise ValueError("LUT matrix must be a finite 3x3 or 3x4 matrix.")
    return validated


def generate_cube_lut(matrix, *, size=33, title=None, clamp=True):
    matrix = _validated_matrix(matrix)
    if isinstance(size, bool) or not isinstance(size, int) or size < 2:
        raise ValueError("LUT size must be an integer greater than or equal to 2.")

    lines = []
    if title:
        escaped_title = str(title).replace('"', "'")
        lines.append(f'TITLE "{escaped_title}"')
    lines.extend((
        f"LUT_3D_SIZE {size}",
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
    ))

    linear = matrix[:, :3]
    offset = matrix[:, 3] if matrix.shape[1] == 4 else np.zeros(3)
    denominator = size - 1
    for blue_index in range(size):
        blue = blue_index / denominator
        for green_index in range(size):
            green = green_index / denominator
            for red_index in range(size):
                red = red_index / denominator
                output = linear @ np.array((red, green, blue)) + offset
                if clamp:
                    output = np.clip(output, 0.0, 1.0)
                lines.append(f"{output[0]:.6f} {output[1]:.6f} {output[2]:.6f}")
    return lines


def compose_export_matrices(forward_matrix, normalization_factor=1.0):
    forward_matrix = _validated_matrix(forward_matrix)
    if forward_matrix.shape != (3, 3):
        raise ValueError("Calibration export requires a finite 3x3 matrix.")
    normalization_factor = float(normalization_factor)
    if not math.isfinite(normalization_factor) or normalization_factor <= 0.0:
        raise ValueError("Normalization factor must be finite and greater than zero.")

    try:
        inverse_matrix = np.linalg.inv(forward_matrix)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Calibration matrix is singular and cannot be inverted.") from exc
    forward_export_matrix = forward_matrix / normalization_factor
    inverse_export_matrix = inverse_matrix * normalization_factor
    return forward_export_matrix, inverse_export_matrix


def image_name_token(image_name):
    return Path(str(image_name)).stem


def sanitize_filename_token(value):
    token = _INVALID_FILENAME_CHARS.sub('_', str(value)).strip().rstrip('. ')
    return token or "unnamed"


def build_lut_filename(working_space, source_name, target_name, *, normalized, mode):
    if mode not in {"Forward", "Inverse"}:
        raise ValueError("LUT mode must be 'Forward' or 'Inverse'.")
    working_space = sanitize_filename_token(working_space)
    source_name = sanitize_filename_token(source_name)
    target_name = sanitize_filename_token(target_name)
    normalization_token = "_normalized" if normalized else ""
    return f"{working_space}_{source_name}_{target_name}{normalization_token}_{mode}.cube"
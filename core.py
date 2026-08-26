from dataclasses import dataclass

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


class CalibrationError(ValueError):
    pass


@dataclass(frozen=True)
class MatrixResult:
    matrix: np.ndarray
    rank: int
    singular_values: np.ndarray
    condition_number: float


def clamp_sample_region(image_size, center_x, center_y, patch_size):
    width, height = image_size
    if width <= 0 or height <= 0:
        return None

    sample_size = max(1, min(int(patch_size), max(width, height)))
    half_size = sample_size // 2
    x = max(0, min(width - 1, int(round(center_x))))
    y = max(0, min(height - 1, int(round(center_y))))

    x_start = max(0, x - half_size)
    x_end = min(width, x + half_size + (sample_size % 2))
    y_start = max(0, y - half_size)
    y_end = min(height, y + half_size + (sample_size % 2))
    return (x_start, x_end, y_start, y_end)


def normalize_rgb_channels(values):
    channels = np.asarray(values, dtype=np.float32)
    if channels.ndim == 0 or channels.shape[-1] == 0:
        raise ValueError("Pixel data must contain at least one channel.")
    if channels.shape[-1] in {1, 2}:
        return np.repeat(channels[..., :1], 3, axis=-1)
    return channels[..., :3]


def sample_pixel_buffer(pixel_buffer, center_x, center_y, patch_size):
    pixels = np.asarray(pixel_buffer, dtype=np.float32)
    if pixels.ndim != 3 or pixels.shape[2] not in {1, 2, 3, 4}:
        raise ValueError("Pixel buffer must have shape (height, width, channels) with 1 to 4 channels.")

    height, width, _channels = pixels.shape
    bounds = clamp_sample_region((width, height), center_x, center_y, patch_size)
    if bounds is None:
        raise ValueError("Image has no sampleable pixel area.")
    x_start, x_end, y_start, y_end = bounds

    region = pixels[y_start:y_end, x_start:x_end]
    if region.size == 0:
        raise ValueError("Sample region contains no pixels.")
    rgb_region = normalize_rgb_channels(region)
    return tuple(np.mean(rgb_region, axis=(0, 1), dtype=np.float64).astype(np.float32))


def _validate_quad(corners):
    points = np.asarray(corners, dtype=np.float64)
    if points.shape != (4, 2) or not np.all(np.isfinite(points)):
        raise ValueError("Chart corners must be four finite 2D points.")

    edges = np.roll(points, -1, axis=0) - points
    next_edges = np.roll(edges, -1, axis=0)
    cross_products = edges[:, 0] * next_edges[:, 1] - edges[:, 1] * next_edges[:, 0]
    if np.any(np.abs(cross_products) < 1e-10) or not (
        np.all(cross_products > 0.0) or np.all(cross_products < 0.0)
    ):
        raise ValueError("Chart corners must form a non-degenerate convex quadrilateral.")
    return points


def build_chart_homography(corners):
    """Build a transform from chart UV coordinates to aligned image coordinates."""
    destination = _validate_quad(corners)
    source = np.array(((0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)))
    coefficients = []
    values = []
    for (u, v), (x, y) in zip(source, destination):
        coefficients.append((u, v, 1.0, 0.0, 0.0, 0.0, -u * x, -v * x))
        coefficients.append((0.0, 0.0, 0.0, u, v, 1.0, -u * y, -v * y))
        values.extend((x, y))

    try:
        solution = np.linalg.solve(np.asarray(coefficients), np.asarray(values))
    except np.linalg.LinAlgError as exc:
        raise ValueError("Chart corners do not define a usable perspective transform.") from exc
    return np.append(solution, 1.0).reshape((3, 3))


def map_chart_point(homography, u, v):
    mapped = np.asarray(homography, dtype=np.float64) @ np.array((u, v, 1.0))
    if abs(mapped[2]) < 1e-12:
        raise ValueError("Chart point maps to infinity.")
    return (float(mapped[0] / mapped[2]), float(mapped[1] / mapped[2]))

def calculate_matrix_result(input_samples, ref_samples, *, debug=False):
    input_samples = np.asarray(input_samples, dtype=np.float64)
    ref_samples = np.asarray(ref_samples, dtype=np.float64)
    if input_samples.shape != (24, 3) or ref_samples.shape != (24, 3):
        raise CalibrationError("Calibration requires two 24x3 sample arrays.")
    if not np.all(np.isfinite(input_samples)) or not np.all(np.isfinite(ref_samples)):
        raise CalibrationError("Calibration samples contain non-finite values.")
    if not np.any(input_samples) or not np.any(ref_samples):
        raise CalibrationError("Calibration samples cannot be all zero.")
    try:
        # Match the Nuke tools' legacy least-squares behavior: solve A x = B and
        # transpose the result before flattening / storing it.
        result_x, residuals, rank, s = np.linalg.lstsq(input_samples, ref_samples, rcond=-1)
        matrix_calculated = result_x
        if debug:
            print(f"        lstsq rank: {rank}, residuals: {residuals}")
            print("        Raw lstsq matrix:")
            for row in matrix_calculated:
                print(f"          [{row[0]:>9.6f} {row[1]:>9.6f} {row[2]:>9.6f}]")
    except np.linalg.LinAlgError as exc:
        raise CalibrationError(f"Least-squares calculation failed: {exc}") from exc
    if rank < 3:
        raise CalibrationError("Source samples are rank-deficient and cannot define a 3x3 transform.")
    if matrix_calculated.shape != (3, 3) or not np.all(np.isfinite(matrix_calculated)):
        raise CalibrationError("Calibration produced an invalid 3x3 matrix.")
    matrix_final = matrix_calculated.T
    matrix_singular_values = np.linalg.svd(matrix_final, compute_uv=False)
    if np.linalg.matrix_rank(matrix_final) < 3 or matrix_singular_values[-1] <= 0.0:
        raise CalibrationError("Calibration produced a singular 3x3 transform.")
    if debug:
        print("        Nuke-style transposed matrix:")
        for row in matrix_final:
            print(f"          [{row[0]:>9.6f} {row[1]:>9.6f} {row[2]:>9.6f}]")
    condition_number = float(matrix_singular_values[0] / matrix_singular_values[-1])
    return MatrixResult(matrix_final.astype(np.float32), int(rank), s, condition_number)


def calculate_matrix(input_samples, ref_samples, *, debug=False):
    """Compatibility wrapper returning the legacy nested-list matrix or None."""
    try:
        return calculate_matrix_result(input_samples, ref_samples, debug=debug).matrix.tolist()
    except CalibrationError as exc:
        print(f"      Err: {exc}")
        return None

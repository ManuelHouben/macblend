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


def rectilinear_to_equirectangular_uv(
    view_u,
    view_v,
    *,
    heading,
    elevation,
    roll,
    horizontal_fov,
    aspect_ratio,
):
    """Map normalized rectilinear view coordinates to wrapped panorama UVs."""
    if not 0.0 < horizontal_fov < np.pi:
        raise ValueError("Horizontal field of view must be between 0 and pi radians.")
    if aspect_ratio <= 0.0:
        raise ValueError("View aspect ratio must be positive.")

    view_u, view_v = np.broadcast_arrays(
        np.asarray(view_u, dtype=np.float64),
        np.asarray(view_v, dtype=np.float64),
    )
    tangent_x = np.tan(horizontal_fov * 0.5)
    local_x = (2.0 * view_u - 1.0) * tangent_x
    local_y = (2.0 * view_v - 1.0) * tangent_x / aspect_ratio

    cos_roll = np.cos(roll)
    sin_roll = np.sin(roll)
    rolled_x = local_x * cos_roll - local_y * sin_roll
    rolled_y = local_x * sin_roll + local_y * cos_roll

    sin_heading = np.sin(heading)
    cos_heading = np.cos(heading)
    sin_elevation = np.sin(elevation)
    cos_elevation = np.cos(elevation)
    forward = np.array((sin_heading * cos_elevation, sin_elevation, cos_heading * cos_elevation))
    right = np.array((cos_heading, 0.0, -sin_heading))
    up = np.array((-sin_heading * sin_elevation, cos_elevation, -cos_heading * sin_elevation))

    direction = (
        forward
        + rolled_x[..., np.newaxis] * right
        + rolled_y[..., np.newaxis] * up
    )
    direction /= np.linalg.norm(direction, axis=-1, keepdims=True)
    panorama_u = np.mod(np.arctan2(direction[..., 0], direction[..., 2]) / (2.0 * np.pi) + 0.5, 1.0)
    panorama_v = np.arcsin(np.clip(direction[..., 1], -1.0, 1.0)) / np.pi + 0.5
    return panorama_u, panorama_v


def equirectangular_to_rectilinear_uv(
    panorama_u,
    panorama_v,
    *,
    heading,
    elevation,
    roll,
    horizontal_fov,
    aspect_ratio,
):
    """Map normalized panorama coordinates into a rectilinear view."""
    if not 0.0 < horizontal_fov < np.pi:
        raise ValueError("Horizontal field of view must be between 0 and pi radians.")
    if aspect_ratio <= 0.0:
        raise ValueError("View aspect ratio must be positive.")

    panorama_u, panorama_v = np.broadcast_arrays(
        np.asarray(panorama_u, dtype=np.float64),
        np.asarray(panorama_v, dtype=np.float64),
    )
    longitude = (panorama_u - 0.5) * (2.0 * np.pi)
    latitude = (panorama_v - 0.5) * np.pi
    cos_latitude = np.cos(latitude)
    direction = np.stack(
        (
            np.sin(longitude) * cos_latitude,
            np.sin(latitude),
            np.cos(longitude) * cos_latitude,
        ),
        axis=-1,
    )

    sin_heading = np.sin(heading)
    cos_heading = np.cos(heading)
    sin_elevation = np.sin(elevation)
    cos_elevation = np.cos(elevation)
    forward = np.array((sin_heading * cos_elevation, sin_elevation, cos_heading * cos_elevation))
    right = np.array((cos_heading, 0.0, -sin_heading))
    up = np.array((-sin_heading * sin_elevation, cos_elevation, -cos_heading * sin_elevation))
    forward_depth = direction @ forward
    if np.any(forward_depth <= 1e-8):
        raise ValueError("Panorama point lies outside the forward rectilinear hemisphere.")

    rolled_x = (direction @ right) / forward_depth
    rolled_y = (direction @ up) / forward_depth
    cos_roll = np.cos(roll)
    sin_roll = np.sin(roll)
    local_x = rolled_x * cos_roll + rolled_y * sin_roll
    local_y = -rolled_x * sin_roll + rolled_y * cos_roll
    tangent_x = np.tan(horizontal_fov * 0.5)
    view_u = (local_x / tangent_x + 1.0) * 0.5
    view_v = (local_y * aspect_ratio / tangent_x + 1.0) * 0.5
    return view_u, view_v


def bilinear_sample_equirectangular(pixel_buffer, panorama_u, panorama_v):
    """Sample panorama UVs, wrapping horizontally and clamping vertically."""
    pixels = normalize_rgb_channels(np.asarray(pixel_buffer, dtype=np.float32))
    if pixels.ndim != 3:
        raise ValueError("Pixel buffer must have shape (height, width, channels).")

    height, width, _channels = pixels.shape
    if width <= 0 or height <= 0:
        raise ValueError("Image has no sampleable pixel area.")

    panorama_u, panorama_v = np.broadcast_arrays(
        np.asarray(panorama_u, dtype=np.float64),
        np.asarray(panorama_v, dtype=np.float64),
    )
    pixel_x = np.mod(panorama_u, 1.0) * width - 0.5
    pixel_y = np.clip(panorama_v, 0.0, 1.0) * height - 0.5
    x0 = np.floor(pixel_x).astype(np.int64)
    y0 = np.floor(pixel_y).astype(np.int64)
    x1 = np.mod(x0 + 1, width)
    y1 = np.clip(y0 + 1, 0, height - 1)
    x0 = np.mod(x0, width)
    y0 = np.clip(y0, 0, height - 1)
    weight_x = (pixel_x - np.floor(pixel_x))[..., np.newaxis]
    weight_y = (pixel_y - np.floor(pixel_y))[..., np.newaxis]

    top = pixels[y0, x0] * (1.0 - weight_x) + pixels[y0, x1] * weight_x
    bottom = pixels[y1, x0] * (1.0 - weight_x) + pixels[y1, x1] * weight_x
    return top * (1.0 - weight_y) + bottom * weight_y


def render_rectilinear_view(pixel_buffer, view_size, **projection):
    width, height = view_size
    if width <= 0 or height <= 0:
        raise ValueError("View dimensions must be positive.")
    view_u = (np.arange(width, dtype=np.float64) + 0.5) / width
    view_v = (np.arange(height, dtype=np.float64) + 0.5) / height
    grid_u, grid_v = np.meshgrid(view_u, view_v)
    panorama_u, panorama_v = rectilinear_to_equirectangular_uv(
        grid_u,
        grid_v,
        aspect_ratio=width / height,
        **projection,
    )
    return bilinear_sample_equirectangular(pixel_buffer, panorama_u, panorama_v).astype(np.float32)


def sample_rectilinear_patch(pixel_buffer, view_size, center_x, center_y, patch_size, **projection):
    width, height = view_size
    bounds = clamp_sample_region(view_size, center_x, center_y, patch_size)
    if bounds is None:
        raise ValueError("View has no sampleable pixel area.")
    x_start, x_end, y_start, y_end = bounds
    view_u = (np.arange(x_start, x_end, dtype=np.float64) + 0.5) / width
    view_v = (np.arange(y_start, y_end, dtype=np.float64) + 0.5) / height
    grid_u, grid_v = np.meshgrid(view_u, view_v)
    panorama_u, panorama_v = rectilinear_to_equirectangular_uv(
        grid_u,
        grid_v,
        aspect_ratio=width / height,
        **projection,
    )
    samples = bilinear_sample_equirectangular(pixel_buffer, panorama_u, panorama_v)
    return tuple(np.mean(samples, axis=(0, 1), dtype=np.float64).astype(np.float32))


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

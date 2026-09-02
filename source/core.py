from dataclasses import dataclass

import numpy as np

# --- Constants ---
CHART_SIZE = (838, 562)
CHART_COLUMNS = 6
CHART_ROWS = 4
CHART_PATCH_CELL_RATIO = 0.8
MACBETH_XYZ_D50 = np.array([
    [0.1136398927, 0.09832436105, 0.047793811],
    [0.3811104477, 0.336202304, 0.1852590702],
    [0.1652470004, 0.1785519348, 0.2546024121],
    [0.1114392339, 0.1346792679, 0.05239320311],
    [0.2419823988, 0.2287175998, 0.3282104382],
    [0.30451114, 0.4143554688, 0.344352688],
    [0.4073691399, 0.3126416159, 0.05130591012],
    [0.1200518326, 0.1091090233, 0.2874447494],
    [0.2915036416, 0.188999956, 0.09736350318],
    [0.08353888545, 0.06276662955, 0.1042075686],
    [0.3427379502, 0.4331759409, 0.08330791241],
    [0.4769723742, 0.4293377578, 0.06005041429],
    [0.06809095613, 0.05596214063, 0.2077405936],
    [0.1413517689, 0.2233437582, 0.07287461742],
    [0.2143728424, 0.127800835, 0.03868150726],
    [0.5888922356, 0.5992976803, 0.07077420003],
    [0.299122798, 0.1895114577, 0.2213469194],
    [0.1247966941, 0.180609913, 0.2913392383],
    [0.8436985288, 0.8806903203, 0.6936778752],
    [0.5665335579, 0.5899709702, 0.4828473821],
    [0.3495921991, 0.3648652066, 0.3013565492],
    [0.1835495863, 0.1906228754, 0.1566717383],
    [0.08448968042, 0.08817234828, 0.07391630753],
    [0.03042544265, 0.03151319431, 0.02656724434],
], dtype=np.float64)

MACBETH_D50_TO_D65_CAT02 = np.array([
    [0.9598786831, -0.0293238461, 0.06578332186],
    [-0.02120095305, 0.9988456964, 0.02618063986],
    [0.001372883562, 0.004445131868, 1.313236713],
], dtype=np.float64)

REFERENCE_GAMUTS = (
    ('ACES', 'ACES', (
        (1.062366107, 0.008406953654, -0.01665578963),
        (-0.4939413716, 1.371109525, 0.09031658697),
        (-0.0003346685774, -0.001037458272, 0.9194696473),
    )),
    ('ACESCG', 'ACEScg', (
        (1.658854308, -0.3118569754, -0.2431560071),
        (-0.6622832871, 1.612199571, 0.0158591266),
        (0.01148056646, -0.009236324924, 0.9166865134),
    )),
    ('P3D65', 'P3D65', (
        (2.493496912, -0.9313836179, -0.4027107845),
        (-0.8294889696, 1.76266406, 0.02362468584),
        (0.03584583024, -0.07617238927, 0.956884524),
    )),
    ('REC2020', 'Rec.2020', (
        (1.716651188, -0.3556707838, -0.2533662814),
        (-0.6666843518, 1.616481237, 0.01576854581),
        (0.01763985745, -0.04277061326, 0.9421031212),
    )),
    ('REC709', 'Linear Rec. 709', (
        (3.240969942, -1.537383178, -0.4986107603),
        (-0.9692436363, 1.875967502, 0.04155505741),
        (0.0556300797, -0.2039769589, 1.056971514),
    )),
    ('ARRI_WIDE_GAMUT_3', 'Arri WideGamut 3', (
        (1.789065551, -0.4825338638, -0.2000757929),
        (-0.6398486599, 1.396399957, 0.1944322918),
        (-0.04153154585, 0.08233537355, 0.8788684803),
    )),
    ('ARRI_WIDE_GAMUT_4', 'Arri WideGamut 4', (
        (1.509215472, -0.2505973452, -0.1688114753),
        (-0.4915454517, 1.361245546, 0.09728294201),
        (0.0, 0.0, 0.9182249512),
    )),
    ('RED_WIDE_GAMUT_RGB', 'Red WideGamut RGB', (
        (1.41280648, -0.177523201, -0.151770732),
        (-0.4862032769, 1.290696427, 0.1574006147),
        (-0.03713901085, 0.2863759998, 0.6876797789),
    )),
    ('SONY_SGAMUT3', 'Sony SGamut3', (
        (1.507399899, -0.2458221374, -0.1716116808),
        (-0.5181517271, 1.355391241, 0.1258786682),
        (0.01551169816, -0.007872771427, 0.9119163656),
    )),
    ('SONY_SGAMUT3_CINE', 'Sony SGamut3.Cine', (
        (1.846778969, -0.525986123, -0.2105452114),
        (-0.4441532629, 1.259442903, 0.1493999729),
        (0.0408554212, 0.01564088931, 0.8682072487),
    )),
    ('PANASONIC_V_GAMUT', 'Panasonic V-Gamut', (
        (1.589011774, -0.3132044845, -0.1809648515),
        (-0.5340529104, 1.396011433, 0.102457671),
        (0.01117944884, 0.003194128241, 0.9055353563),
    )),
    ('BLACKMAGIC_WIDE_GAMUT', 'Blackmagic Wide Gamut', (
        (1.866357736, -0.5183905088, -0.2346067165),
        (-0.6003298545, 1.378119951, 0.1767281098),
        (0.002451481064, 0.08638160934, 0.8367677153),
    )),
    ('FILMLIGHT_E_GAMUT', 'Filmlight E-Gamut', (
        (1.52505277, -0.3159135109, -0.1226582646),
        (-0.50915256, 1.333327409, 0.1382843651),
        (0.09571534531, 0.05089744385, 0.7879557703),
    )),
    ('DAVINCI_WIDE_GAMUT', 'DaVinci Wide Gamut', (
        (1.516672042, -0.2814780479, -0.1469636332),
        (-0.4649171012, 1.251423776, 0.1748846089),
        (0.06484904707, 0.1091393437, 0.7614146215),
    )),
)

REFERENCE_GAMUT_MATRICES = {
    identifier: np.asarray(matrix, dtype=np.float64)
    for identifier, _label, matrix in REFERENCE_GAMUTS
}


def build_reference_values(gamut):
    try:
        xyz_to_rgb = REFERENCE_GAMUT_MATRICES[gamut]
    except KeyError as exc:
        raise ValueError(f"Unknown reference gamut: {gamut}") from exc
    xyz_d65 = MACBETH_XYZ_D50 @ MACBETH_D50_TO_D65_CAT02.T
    return xyz_d65 @ xyz_to_rgb.T


LUMA_COEFFS_REC709 = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


class CalibrationError(ValueError):
    pass


@dataclass(frozen=True)
class MatrixResult:
    matrix: np.ndarray
    rank: int
    singular_values: np.ndarray
    transform_condition_number: float


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


def map_chart_points(homography, chart_points):
    points = np.asarray(chart_points, dtype=np.float64)
    if points.shape[-1] != 2:
        raise ValueError("Chart points must end with two coordinates.")
    homogeneous = np.concatenate(
        (points.reshape((-1, 2)), np.ones((points.size // 2, 1))),
        axis=1,
    )
    mapped = homogeneous @ np.asarray(homography, dtype=np.float64).T
    if np.any(np.abs(mapped[:, 2]) < 1e-12):
        raise ValueError("Chart point maps to infinity.")
    mapped = mapped[:, :2] / mapped[:, 2:3]
    return mapped.reshape(points.shape)


def chart_rectified_size(corners, image_size):
    points = _validate_quad(corners).copy()
    image_width, image_height = image_size
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image dimensions must be positive.")
    points[:, 0] *= image_width
    points[:, 1] *= image_height
    top, right, bottom, left = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
    return ((top + bottom) * 0.5, (right + left) * 0.5)


def chart_patch_size(chart_size, *, maximum=200):
    chart_width, chart_height = chart_size
    if chart_width <= 0 or chart_height <= 0:
        raise ValueError("Rectified chart dimensions must be positive.")
    nominal_cell_size = min(chart_width / CHART_COLUMNS, chart_height / CHART_ROWS)
    return max(1, min(int(maximum), int(round(nominal_cell_size * CHART_PATCH_CELL_RATIO))))


def effective_patch_size(patch_size, image_size, *, maximum=200):
    image_width, image_height = image_size
    return max(1, min(int(patch_size), int(maximum), int(max(image_width, image_height))))


def chart_patch_uv(slot):
    if not 0 <= int(slot) < 24:
        raise ValueError("Macbeth patch slot must be between 0 and 23.")
    row, column = divmod(int(slot), CHART_COLUMNS)
    return (
        (column + 0.5) / CHART_COLUMNS,
        1.0 - (row + 0.5) / CHART_ROWS,
    )


def chart_patch_footprint(homography, slot, patch_size, chart_size=CHART_SIZE):
    chart_width, chart_height = chart_size
    if chart_width <= 0 or chart_height <= 0:
        raise ValueError("Rectified chart dimensions must be positive.")
    sample_size = max(1, int(patch_size))
    center_u, center_v = chart_patch_uv(slot)
    half_u = sample_size / (2.0 * chart_width)
    half_v = sample_size / (2.0 * chart_height)
    chart_corners = np.array((
        (center_u - half_u, center_v - half_v),
        (center_u + half_u, center_v - half_v),
        (center_u + half_u, center_v + half_v),
        (center_u - half_u, center_v + half_v),
    ))
    return map_chart_points(homography, chart_corners)


def bilinear_sample_image_uv(pixel_buffer, image_u, image_v):
    pixels = normalize_rgb_channels(np.asarray(pixel_buffer, dtype=np.float32))
    if pixels.ndim != 3:
        raise ValueError("Pixel buffer must have shape (height, width, channels).")
    height, width, _channels = pixels.shape
    if width <= 0 or height <= 0:
        raise ValueError("Image has no sampleable pixel area.")

    image_u, image_v = np.broadcast_arrays(
        np.asarray(image_u, dtype=np.float64),
        np.asarray(image_v, dtype=np.float64),
    )
    pixel_x = np.clip(image_u * width - 0.5, 0.0, width - 1.0)
    pixel_y = np.clip(image_v * height - 0.5, 0.0, height - 1.0)
    x0 = np.floor(pixel_x).astype(np.int64)
    y0 = np.floor(pixel_y).astype(np.int64)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    weight_x = (pixel_x - x0)[..., np.newaxis]
    weight_y = (pixel_y - y0)[..., np.newaxis]
    top = pixels[y0, x0] * (1.0 - weight_x) + pixels[y0, x1] * weight_x
    bottom = pixels[y1, x0] * (1.0 - weight_x) + pixels[y1, x1] * weight_x
    return top * (1.0 - weight_y) + bottom * weight_y


def sample_warped_chart_patch(
    pixel_buffer,
    homography,
    slot,
    patch_size,
    *,
    chart_size=CHART_SIZE,
    panorama_projection=None,
):
    chart_width, chart_height = chart_size
    sample_size = max(1, int(patch_size))
    center_u, center_v = chart_patch_uv(slot)
    offsets = np.arange(sample_size, dtype=np.float64) + 0.5 - sample_size * 0.5
    grid_u, grid_v = np.meshgrid(
        center_u + offsets / chart_width,
        center_v + offsets / chart_height,
    )
    image_points = map_chart_points(homography, np.stack((grid_u, grid_v), axis=-1))
    if panorama_projection is None:
        samples = bilinear_sample_image_uv(
            pixel_buffer,
            image_points[..., 0],
            image_points[..., 1],
        )
    else:
        panorama_u, panorama_v = rectilinear_to_equirectangular_uv(
            image_points[..., 0],
            image_points[..., 1],
            **panorama_projection,
        )
        samples = bilinear_sample_equirectangular(pixel_buffer, panorama_u, panorama_v)
    return tuple(np.mean(samples, axis=(0, 1), dtype=np.float64).astype(np.float32))

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
        # Solve A x = B and transpose the result for the RGB matrix convention.
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
        print("        Transposed RGB matrix:")
        for row in matrix_final:
            print(f"          [{row[0]:>9.6f} {row[1]:>9.6f} {row[2]:>9.6f}]")
    transform_condition_number = float(matrix_singular_values[0] / matrix_singular_values[-1])
    return MatrixResult(matrix_final.astype(np.float32), int(rank), s, transform_condition_number)


def calculate_matrix(input_samples, ref_samples, *, debug=False):
    """Compatibility wrapper returning the legacy nested-list matrix or None."""
    try:
        return calculate_matrix_result(input_samples, ref_samples, debug=debug).matrix.tolist()
    except CalibrationError as exc:
        print(f"      Err: {exc}")
        return None

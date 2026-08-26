import json
import os

import numpy as np


DEFAULT_JSON_NAME = "mmColorTarget_colorspace_transforms.json"


class ColorspaceDataError(ValueError):
    pass


def bundled_json_path():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_JSON_NAME)
    return path if os.path.isfile(path) else None


def effective_json_path(user_path=None):
    if user_path:
        return os.path.abspath(os.path.expanduser(user_path))
    return bundled_json_path()


def json_cache_key(path):
    if not path:
        return None
    stat = os.stat(path)
    return (os.path.abspath(path), stat.st_mtime_ns, stat.st_size)


def _matrix3(value, description):
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ColorspaceDataError(f"{description} must be a finite 3x3 matrix.")


def validate_colorspace_data(data):
    if not isinstance(data, dict):
        raise ColorspaceDataError("Colorspace JSON root must be an object.")
    if "sRGB_to_XYZ_matrix" not in data:
        raise ColorspaceDataError("Colorspace JSON is missing 'sRGB_to_XYZ_matrix'.")
    _matrix3(data["sRGB_to_XYZ_matrix"], "sRGB_to_XYZ_matrix")

    target_matrices = data.get("XYZ_to_RGB_matrices")
    if not isinstance(target_matrices, dict) or not target_matrices:
        raise ColorspaceDataError("Colorspace JSON must contain target XYZ-to-RGB matrices.")
    for name, matrix in target_matrices.items():
        _matrix3(matrix, f"XYZ_to_RGB_matrices[{name!r}]")

    cat_matrices = data.get("CAT_matrices", {})
    if not isinstance(cat_matrices, dict):
        raise ColorspaceDataError("CAT_matrices must be an object when present.")
    for name, matrix in cat_matrices.items():
        _matrix3(matrix, f"CAT_matrices[{name!r}]")
    return data


def load_colorspace_data(path):
    if not path:
        raise ColorspaceDataError("No colorspace JSON file is available.")
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ColorspaceDataError(f"Could not read colorspace JSON: {exc}") from exc
    return validate_colorspace_data(data)
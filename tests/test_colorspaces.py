import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "source" / "colorspaces.py"
SPEC = importlib.util.spec_from_file_location("macblend_colorspaces", MODULE_PATH)
colorspaces = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(colorspaces)


class ColorspaceDataTests(unittest.TestCase):
    def test_bundled_data_is_valid(self):
        path = colorspaces.bundled_json_path()
        data = colorspaces.load_colorspace_data(path)
        self.assertIn("XYZ_to_RGB_matrices", data)

    def test_cache_key_changes_when_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text("{}", encoding="utf-8")
            first_key = colorspaces.json_cache_key(path)
            path.write_text('{"changed": true}', encoding="utf-8")
            self.assertNotEqual(first_key, colorspaces.json_cache_key(path))

    def test_rejects_invalid_matrix_shape(self):
        data = {
            "sRGB_to_XYZ_matrix": [[1, 0], [0, 1]],
            "XYZ_to_RGB_matrices": {"target": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(colorspaces.ColorspaceDataError):
                colorspaces.load_colorspace_data(path)

    def test_missing_explicit_path_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "missing.json"
            self.assertEqual(colorspaces.effective_json_path(missing_path), str(missing_path))
            with self.assertRaises(colorspaces.ColorspaceDataError):
                colorspaces.load_colorspace_data(missing_path)


if __name__ == "__main__":
    unittest.main()
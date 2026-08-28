import importlib.util
from pathlib import Path
import unittest

import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "source" / "lut_writer.py"
SPEC = importlib.util.spec_from_file_location("macblend_lut_writer", MODULE_PATH)
lut_writer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lut_writer)


class CubeGenerationTests(unittest.TestCase):
    def test_identity_size_two_uses_red_fastest_order(self):
        lines = lut_writer.generate_cube_lut(np.eye(3), size=2, title="Identity")
        self.assertEqual(lines[:4], [
            'TITLE "Identity"',
            "LUT_3D_SIZE 2",
            "DOMAIN_MIN 0.0 0.0 0.0",
            "DOMAIN_MAX 1.0 1.0 1.0",
        ])
        self.assertEqual(lines[4:], [
            "0.000000 0.000000 0.000000",
            "1.000000 0.000000 0.000000",
            "0.000000 1.000000 0.000000",
            "1.000000 1.000000 0.000000",
            "0.000000 0.000000 1.000000",
            "1.000000 0.000000 1.000000",
            "0.000000 1.000000 1.000000",
            "1.000000 1.000000 1.000000",
        ])

    def test_affine_offset_and_clamp(self):
        matrix = ((2, 0, 0, -0.25), (0, 1, 0, 0.1), (0, 0, 1, 0))
        clamped = lut_writer.generate_cube_lut(matrix, size=2)
        extended = lut_writer.generate_cube_lut(matrix, size=2, clamp=False)
        self.assertEqual(clamped[3], "0.000000 0.100000 0.000000")
        self.assertEqual(clamped[4], "1.000000 0.100000 0.000000")
        self.assertEqual(extended[3], "-0.250000 0.100000 0.000000")
        self.assertEqual(extended[4], "1.750000 0.100000 0.000000")

    def test_rejects_invalid_inputs(self):
        for matrix in (np.eye(2), np.full((3, 3), np.nan)):
            with self.subTest(matrix=matrix):
                with self.assertRaises(ValueError):
                    lut_writer.generate_cube_lut(matrix, size=2)
        for size in (1, 2.5, True):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    lut_writer.generate_cube_lut(np.eye(3), size=size)


class ExportMatrixTests(unittest.TestCase):
    def test_normalized_matrices_are_inverses(self):
        forward = np.array(((1.1, 0.1, 0), (0, 0.9, 0.1), (0.1, 0, 1.2)))
        forward_export, inverse_export = lut_writer.compose_export_matrices(forward, 1.25)
        np.testing.assert_allclose(forward_export, forward / 1.25)
        np.testing.assert_allclose(inverse_export, np.linalg.inv(forward) * 1.25)
        np.testing.assert_allclose(inverse_export @ forward_export, np.eye(3), atol=1e-12)

    def test_rejects_non_positive_normalization(self):
        with self.assertRaises(ValueError):
            lut_writer.compose_export_matrices(np.eye(3), 0.0)


class FilenameTests(unittest.TestCase):
    def test_builds_image_and_reference_names(self):
        source = lut_writer.image_name_token("source.chart.exr")
        target = lut_writer.image_name_token("target.png")
        self.assertEqual(source, "source.chart")
        self.assertEqual(
            lut_writer.build_lut_filename(
                "ACEScg", source, target, normalized=True, mode="Inverse"
            ),
            "ACEScg_source.chart_target_normalized_Inverse.cube",
        )
        unnormalized_filename = lut_writer.build_lut_filename(
            "Linear Rec.709", source, "LINEAR_SRGB_D65", normalized=False, mode="Forward"
        )
        self.assertEqual(
            unnormalized_filename,
            "Linear Rec.709_source.chart_LINEAR_SRGB_D65_Forward.cube",
        )
        self.assertNotIn("__", unnormalized_filename)

    def test_sanitizes_invalid_filename_characters(self):
        filename = lut_writer.build_lut_filename(
            "ACES/cg", "source:one", "target*two. ", normalized=False, mode="Inverse"
        )
        self.assertEqual(filename, "ACES_cg_source_one_target_two_Inverse.cube")


if __name__ == "__main__":
    unittest.main()
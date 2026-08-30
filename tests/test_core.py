import importlib.util
from pathlib import Path
import unittest

import numpy as np


CORE_PATH = Path(__file__).parents[1] / "source" / "core.py"
SPEC = importlib.util.spec_from_file_location("macblend_core", CORE_PATH)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class SampleBoundsTests(unittest.TestCase):
    def test_even_and_odd_regions_have_requested_size(self):
        self.assertEqual(core.clamp_sample_region((100, 100), 50, 50, 4), (48, 52, 48, 52))
        self.assertEqual(core.clamp_sample_region((100, 100), 50, 50, 5), (48, 53, 48, 53))

    def test_region_is_clipped_at_image_edge(self):
        self.assertEqual(core.clamp_sample_region((10, 8), 0, 0, 5), (0, 3, 0, 3))


class ChannelTests(unittest.TestCase):
    def test_grayscale_and_gray_alpha_expand_to_rgb(self):
        np.testing.assert_array_equal(core.normalize_rgb_channels([0.25]), [0.25, 0.25, 0.25])
        np.testing.assert_array_equal(core.normalize_rgb_channels([0.25, 0.9]), [0.25, 0.25, 0.25])

    def test_rgba_ignores_alpha(self):
        np.testing.assert_allclose(core.normalize_rgb_channels([0.1, 0.2, 0.3, 0.9]), [0.1, 0.2, 0.3])


class PixelBufferSamplingTests(unittest.TestCase):
    def test_rgb_and_rgba_match_reference_mean(self):
        rgb = np.arange(5 * 6 * 3, dtype=np.float32).reshape((5, 6, 3)) / 100.0
        rgba = np.concatenate((rgb, np.full((5, 6, 1), 0.25, dtype=np.float32)), axis=2)
        expected = np.mean(rgb[1:4, 2:5], axis=(0, 1), dtype=np.float64)

        np.testing.assert_allclose(core.sample_pixel_buffer(rgb, 3, 2, 3), expected)
        np.testing.assert_allclose(core.sample_pixel_buffer(rgba, 3, 2, 3), expected)

    def test_grayscale_and_gray_alpha_expand_to_rgb(self):
        grayscale = np.arange(16, dtype=np.float32).reshape((4, 4, 1))
        gray_alpha = np.concatenate(
            (grayscale, np.full((4, 4, 1), 0.75, dtype=np.float32)),
            axis=2,
        )
        expected = np.repeat(np.mean(grayscale[1:3, 1:3]), 3)

        np.testing.assert_allclose(core.sample_pixel_buffer(grayscale, 2, 2, 2), expected)
        np.testing.assert_allclose(core.sample_pixel_buffer(gray_alpha, 2, 2, 2), expected)

    def test_even_odd_and_edge_regions_use_clamped_bounds(self):
        pixels = np.arange(5 * 5 * 3, dtype=np.float32).reshape((5, 5, 3))

        even_expected = np.mean(pixels[1:5, 1:5], axis=(0, 1), dtype=np.float64)
        odd_edge_expected = np.mean(pixels[0:3, 0:3], axis=(0, 1), dtype=np.float64)

        np.testing.assert_allclose(core.sample_pixel_buffer(pixels, 3, 3, 4), even_expected)
        np.testing.assert_allclose(core.sample_pixel_buffer(pixels, 0, 0, 5), odd_edge_expected)

    def test_rejects_invalid_buffer_shape(self):
        with self.assertRaises(ValueError):
            core.sample_pixel_buffer(np.zeros((4, 4), dtype=np.float32), 2, 2, 3)


class PanoramaSamplingTests(unittest.TestCase):
    def test_center_sample_wraps_across_panorama_seam(self):
        pixels = np.zeros((3, 4, 3), dtype=np.float32)
        pixels[:, 0] = (1.0, 0.0, 0.0)
        pixels[:, -1] = (0.0, 0.0, 1.0)

        sample = core.sample_rectilinear_patch(
            pixels,
            (3, 3),
            1.0,
            1.0,
            1,
            heading=np.pi,
            elevation=0.0,
            roll=0.0,
            horizontal_fov=np.deg2rad(60.0),
        )

        np.testing.assert_allclose(sample, (0.5, 0.0, 0.5), atol=1e-6)

    def test_view_center_maps_to_heading_and_elevation(self):
        panorama_u, panorama_v = core.rectilinear_to_equirectangular_uv(
            0.5,
            0.5,
            heading=np.deg2rad(90.0),
            elevation=np.deg2rad(30.0),
            roll=0.0,
            horizontal_fov=np.deg2rad(60.0),
            aspect_ratio=1.0,
        )

        np.testing.assert_allclose((panorama_u, panorama_v), (0.75, 2.0 / 3.0), atol=1e-6)

    def test_rectilinear_projection_round_trip_near_panorama_seam(self):
        projection = {
            'heading': np.pi,
            'elevation': np.deg2rad(10.0),
            'roll': np.deg2rad(5.0),
            'horizontal_fov': np.deg2rad(70.0),
            'aspect_ratio': 4.0 / 3.0,
        }
        view_u = np.array((0.2, 0.8, 0.75, 0.25))
        view_v = np.array((0.8, 0.8, 0.2, 0.2))
        panorama_u, panorama_v = core.rectilinear_to_equirectangular_uv(
            view_u,
            view_v,
            **projection,
        )

        restored_u, restored_v = core.equirectangular_to_rectilinear_uv(
            panorama_u,
            panorama_v,
            **projection,
        )

        np.testing.assert_allclose(restored_u, view_u, atol=1e-6)
        np.testing.assert_allclose(restored_v, view_v, atol=1e-6)


class HomographyTests(unittest.TestCase):
    def test_identity_quad_maps_uv_directly(self):
        transform = core.build_chart_homography(((0, 1), (1, 1), (1, 0), (0, 0)))
        np.testing.assert_allclose(core.map_chart_point(transform, 0.25, 0.75), (0.25, 0.75))

    def test_transform_maps_all_four_corners(self):
        corners = ((0.1, 0.9), (0.85, 0.75), (0.7, 0.1), (0.2, 0.2))
        transform = core.build_chart_homography(corners)
        chart_corners = ((0, 1), (1, 1), (1, 0), (0, 0))
        for uv, expected in zip(chart_corners, corners):
            np.testing.assert_allclose(core.map_chart_point(transform, *uv), expected)

    def test_rejects_self_intersecting_quad(self):
        with self.assertRaises(ValueError):
            core.build_chart_homography(((0, 1), (1, 0), (1, 1), (0, 0)))


class MatrixTests(unittest.TestCase):
    def test_identity_samples_produce_identity_matrix(self):
        samples = np.tile(np.eye(3), (8, 1)).astype(np.float32)
        result = core.calculate_matrix_result(samples, samples)
        np.testing.assert_allclose(result.matrix, np.eye(3), atol=1e-6)
        self.assertEqual(result.rank, 3)

    def test_rank_deficient_samples_are_rejected(self):
        samples = np.ones((24, 3), dtype=np.float32)
        with self.assertRaises(core.CalibrationError):
            core.calculate_matrix_result(samples, samples)

    def test_singular_solved_matrix_is_rejected(self):
        samples = np.tile(np.eye(3), (8, 1)).astype(np.float32)
        singular_target = samples.copy()
        singular_target[:, 2] = 0.0
        with self.assertRaises(core.CalibrationError):
            core.calculate_matrix_result(samples, singular_target)


if __name__ == "__main__":
    unittest.main()
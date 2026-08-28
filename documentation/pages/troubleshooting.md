# Troubleshooting

## An image cannot be selected

Only images with a complete set of 24 sampled values appear in source and sampled-target selectors. Return to the [Image Editor](https://docs.blender.org/manual/en/4.2/editors/image/index.html), align the overlay, and select **Sample Chart**.

## Results look too dark, bright, or strongly tinted

Verify the input [**Color Space**](https://docs.blender.org/manual/en/4.2/editors/image/image_settings.html#bpy-types-colormanagedinputcolorspacesettings-name) on every sampled image. MacBlend reads Blender's decoded values, so an incorrect input transform directly changes the solve. Also verify chart orientation, patch alignment, clipping, uneven lighting, reflections, and whether **Normalize** and **Create Exposure Node** are appropriate for the workflow.

## Reference color spaces are missing

MacBlend includes linear sRGB D65 reference values and loads additional transforms from `mmColorTarget_colorspace_transforms.json`. In the extension preferences, clear the custom path to use the bundled file. If a custom file is selected, confirm that it exists and contains valid 3-by-3 matrices.

## Sampling fails or uses too much memory

The image must have a valid pixel resolution and a supported channel count. Reduce image dimensions when memory is constrained. A larger **Patch Size** increases averaging work only modestly, but the full decoded image buffer must still fit in memory.

Enable **Debug Logging** in the MacBlend extension preferences to print pixel-transfer, patch-average, and calibration diagnostics to Blender's console.

## An Inverse transform cannot be created

Inverse requires the fitted matrix to be invertible. Check for missing, uniform, clipped, or incorrectly ordered samples. Resample the chart after correcting the image and overlay.

## Reporting a problem

Open a [GitHub bug report](https://github.com/ManuelHouben/macblend/issues/new?template=bug_report.md) and include Blender and MacBlend versions, operating system, exact steps, image color-space settings, relevant console output, and screenshots or redistributable sample files.

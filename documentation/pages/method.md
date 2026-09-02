# Method and Limitations

## Color Management

The image [**Color Space**](https://docs.blender.org/manual/en/latest/editors/image/image_settings.html#bpy-types-colormanagedinputcolorspacesettings-name) is its input transform, often called an IDT. It converts stored values into the scene-linear working values used by the calibration. For example, Panasonic V-Log/V-Gamut footage requires the corresponding input transform from Blender's active color configuration.

The [display transform](https://docs.blender.org/manual/en/latest/render/color_management.html#display-transforms) changes the preview without changing sampled values. **Non-Color** bypasses input conversion and is only appropriate for data intentionally encoded that way.

See [Color Spaces](https://docs.blender.org/manual/en/latest/render/color_management/color_spaces.html) in the Blender Manual.

## Sampling Model

**Patch Size** determines how large the ColorChecker overlay is drawn. A value of 40 results in patches that are 40 × 40 pixels. Moving the corners introduces perspective, so the visible patch sizes change with the shape of the chart.

## Target Data

The target can be another sampled chart or MacBlend's built-in ColorChecker values. The built-in values are based on published [ColorChecker reference data](https://colour.readthedocs.io/en/develop/generated/colour.CCS_COLOURCHECKERS.html).

With **Use reference values as target** enabled, **Target Gamut** converts those reference values to the selected linear color space. MacBlend initially matches Blender's **File Color Space** setting when possible; see Blender's [Color Management](https://docs.blender.org/manual/en/latest/render/color_management.html) documentation. If no match is found, MacBlend reports the problem and uses **Linear Rec. 709** as a fallback.

```{note}
For use in the current scene, **Target Gamut** should match the gamut selected under **File Color Space**.
```

## Transform Direction

**Forward**
: Transforms the sampled source toward the target.

**Inverse**
: Transforms the target back toward the sampled source.

LUT exports contain both directions.

## Normalization

**Normalize** separates a broad brightness difference before fitting the color matrix. The Neutral 5 patch and Rec. 709 luminance coefficients determine the scale.

**Create Exposure Node** represents that scale as an adjustable node after the matrix.

## Limitations

A single RGB matrix cannot reliably repair an incorrect gamma, display rendering, clipped channels, local or selective grading, uneven lighting, glare, shadows, or chart damage. Built-in references assume D65 conditions; unusual illumination reduces the accuracy of a reference-based result.

```{important}
Check the result on both the chart and the rest of the image. Even when MacBlend completes the calculation, poor lighting, glare, clipped colors, or an incorrect image **Color Space** can produce a bad result.
```

## See Also

- [Hitchhiker's Guide to Digital Colour](https://hg2dc.com/)
- Chris Brejon, [CG Cinematography](https://chrisbrejon.com/cg-cinematography/)
- [ACES Overview](https://docs.acescentral.com/background/overview/)

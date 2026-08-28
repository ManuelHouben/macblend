# Calibration transforms

Open the [Compositor](https://docs.blender.org/manual/en/4.2/editors/compositor.html) or [Shader Editor](https://docs.blender.org/manual/en/4.2/editors/shader_editor.html) and select the **MacBlend** sidebar tab after sampling the source image.

## Configure the solve

Start by selecting the sampled source under **Image**. The other settings default to a reference-based, normalized calibration:

- **Use reference values as target** is enabled.
- **Target** is **Linear sRGB D65 (Internal)**.
- **Normalize** and **Create Exposure Node** are enabled.
- **Node Name** is `MacBlendCalibration`.

When using reference values, change **Target** to the gamut in which the source was recorded when appropriate, such as **V-Gamut** for Panasonic V-Gamut footage. The image's IDT must also be set correctly in the [Image Editor](https://docs.blender.org/manual/en/4.2/editors/image/index.html) before sampling. To match one sampled chart image to another instead, disable **Use reference values as target** and select the second image under **Target**.

With the default normalization, MacBlend uses the Neutral 5 patch and Rec.709 luminance coefficients to separate a broad brightness difference before fitting the matrix. **Create Exposure Node** represents that separated scale as an adjustable node after the matrix. Disable **Normalize** when the solve should include the brightness difference in the matrix; disable **Create Exposure Node** when the separate node is not wanted.

Change **Node Name** only when generated node groups need a different base name.

## Match

**Match** creates the inverse of the fitted calibration matrix. Use it to transform material or compositor data toward the selected target appearance. When exposure-node creation is enabled, MacBlend adds the reciprocal normalization scale after the matrix.

## Neutralize

**Neutralize** creates the forward fitted matrix. Use it for the opposite transform direction. When enabled, the exposure node receives the stored normalization scale.

Both commands require a valid source and target and a supported node editor. A singular fitted matrix cannot be inverted for Match.

## Matrix result

After a successful solve, the panel displays the fitted matrix. The generated node group applies the RGB matrix while preserving alpha in compositor workflows.

Always inspect the result on representative imagery. A chart fit can be numerically valid while still reflecting poor lighting, clipped patches, incorrect input color spaces, or a chart overlay aligned in the wrong orientation.

See [Method and limitations](../method.md) for a plain-language explanation of the workflow, its limits, and links to the deeper technical resources.

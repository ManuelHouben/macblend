# Method and limitations

MacBlend adapts the chart-matching workflow used by Marco Meyer's [mmColorTarget](https://www.marcomeyer-vfx.de/posts/mmcolortarget-nuke-gizmo/) and Jed Smith's [CalibrateMacbeth](https://gist.github.com/jedypod/798b365ea64e8121999e7036ae7e0217).

## Before you start

In the [Image Editor](https://docs.blender.org/manual/en/4.2/editors/image/index.html) sidebar, [**Color Space**](https://docs.blender.org/manual/en/4.2/editors/image/image_settings.html#bpy-types-colormanagedinputcolorspacesettings-name) selects the image input transform, often called an IDT. It turns the file's stored values into the scene-linear working values required by the calculation. For example, Panasonic V-Log/V-Gamut footage should use the matching Panasonic input transform available in your Blender color configuration.

[Find out more about color spaces and transforms in Blender.](https://docs.blender.org/manual/en/latest/render/color_management/color_spaces.html)

The [display/view transform](https://docs.blender.org/manual/en/4.2/render/color_management.html#display-transforms) changes how the image looks on screen. It does not change the values MacBlend samples. Do not choose [**Non-Color**](https://docs.blender.org/manual/en/4.2/render/color_management.html#image-color-spaces) just to change the preview; use it only when the image data is deliberately meant to bypass color conversion.

When **Use reference values as target** is enabled, choose the gamut in which the source was recorded. For example, use **V-Gamut** for a Panasonic V-Gamut image. This tells MacBlend which known chart values to compare against. It does not select a creative look or delivery color space.

## What happens when you sample

First, align the four overlay corners with the four corners of the chart. MacBlend then finds the center of every patch and averages a small square of pixels there. Keep that square inside the colored part of a patch, away from borders, glare, shadows, and reflections.

You can either sample a second chart image as the target, useful for matching camera A to camera B, or use MacBlend's built-in chart references. The built-in references start from D65 values and are converted for the recorded gamut you choose.

## What Match and Neutralize mean

**Neutralize** creates the correction that moves the sampled source chart toward the selected target. **Match** creates the reverse direction. Both are written when you export LUTs.

**Normalize** handles a broad brightness difference before the color correction is calculated. **Create Exposure Node** keeps that brightness adjustment visible as its own node after the color transform. Leave it enabled when you want to inspect or adjust that exposure change separately.

## What it cannot do

A single color correction cannot fix everything. It will not reliably repair gamma errors, display rendering, clipped highlights, a local grade, a selective hue adjustment, uneven lighting, glare, shadows, or a damaged chart.

Use a clean, evenly lit, properly exposed chart and minimally processed imagery. The built-in chart references assume D65 conditions, so unusual lighting can make a reference-based result less accurate. Always check the transformed chart and representative shot content before relying on the result.

## Learn more

These resources continue from approachable introductions through practical guidance to technical background and the original Nuke implementations:

- [Hitchhiker's Guide to Digital Colour](https://hg2dc.com/)
- Chris Brejon, [CG Cinematography](https://chrisbrejon.com/cg-cinematography/)
- [ACES Overview](https://docs.acescentral.com/background/overview/)
- Marco Meyer, [mmColorTarget - Nuke Gizmo](https://www.marcomeyer-vfx.de/posts/mmcolortarget-nuke-gizmo/)
- Jed Smith, [CalibrateMacbeth](https://gist.github.com/jedypod/798b365ea64e8121999e7036ae7e0217)
- Colour Developers, [Colour-Nuke](https://github.com/colour-science/colour-nuke), the source of the bundled color-space transform data

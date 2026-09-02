# Troubleshooting

## Image Is Not Available

Source and target selectors only include images with all 24 sampled values. In the [Image Editor](https://docs.blender.org/manual/en/latest/editors/image/index.html), align the overlay and use **Sample Chart**.

## Incorrect Brightness or Color

Verify the input [**Color Space**](https://docs.blender.org/manual/en/latest/editors/image/image_settings.html#bpy-types-colormanagedinputcolorspacesettings-name) on every sampled image. An incorrect input transform changes the values used by the fit.

Other common causes are reversed chart orientation, inaccurate corner alignment, clipped patches, uneven lighting, reflections, and an unsuitable **Normalize** or **Create Exposure Node** setting.

## Incorrect Target Gamut

MacBlend supports 14 target gamuts. It matches explicit aliases for Blender's blend-file working space, or the OCIO `scene_linear` role on older Blender versions, and shows **Auto-detected** when it finds one. Otherwise, it shows **Couldn't detect target gamut from scene** and keeps **Linear Rec. 709** selected as a fallback. Select the actual scene-linear working gamut manually when a custom OCIO configuration uses another name.

## Sampling Fails or Uses Too Much Memory

The image requires a valid resolution and supported channel count. Its full decoded pixel buffer must fit in memory; reduce the image dimensions when memory is constrained. **Patch Size** has comparatively little effect on peak memory.

Enable **Debug Logging** in the MacBlend extension preferences to print pixel-transfer, patch-average, and calibration diagnostics to Blender's console.

## Inverse Is Unavailable

**Inverse** requires an invertible fitted matrix. Missing, uniform, clipped, or incorrectly ordered samples can produce a singular result. Correct the image or overlay and sample the chart again.

## Reporting a Problem

Open a [GitHub bug report](https://github.com/ManuelHouben/macblend/issues/new?template=bug_report.md) with the Blender and MacBlend versions, operating system, reproduction steps, image color-space settings, relevant console output, and screenshots or redistributable sample files.

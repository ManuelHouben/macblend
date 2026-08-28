# Sampling a chart

Sampling is performed in the [Image Editor](https://docs.blender.org/manual/en/4.2/editors/image/index.html) from the **MacBlend** sidebar tab.

## Prepare the image

1. Open the chart image in Blender's Image Editor.
2. Set the image's input [**Color Space**](https://docs.blender.org/manual/en/4.2/editors/image/image_settings.html#bpy-types-colormanagedinputcolorspacesettings-name) to match the file.
3. Open the sidebar and select the **MacBlend** tab.
4. Set **Patch Size** to an area that remains inside each colored patch.

Patch Size is measured in image pixels. Larger values average more pixels but can cross patch borders on a small or strongly skewed chart.

## Align the overlay

Enable **Show Overlay**, then drag each corner handle onto the corresponding outer corner of the chart.
Use **Flip Horizontal** or **Flip Vertical** when the patch order does not match the image orientation.

Use **Center Overlay** to reset the overlay to a centered 28:21 rectangle occupying approximately 25 percent of the image.

Expand **Corner Positions** when numeric corner coordinates are more convenient than dragging.

## Sample patches

Select **Sample Chart** after alignment. MacBlend reads the decoded pixel buffer once, averages the configured region around every patch center, stores 24 RGB values on the image, and hides the overlay.

Successfully sampled images appear in **Sampled Images**. Select an entry to inspect its 24 color swatches. The trash button clears that image's samples and removes it from any active source or target selection.

## Sampling guidance

- Keep every sample region inside its patch and away from borders, glare, shadows, and chart damage.
- Use source imagery without clipped channels when possible.
- Sampling the same image twice replaces its previous values.
- The [display/view transform](https://docs.blender.org/manual/en/4.2/render/color_management.html#display-transforms) does not alter sampled values.
- Changing the image input color space does alter sampled values; resample after changing it.

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

While dragging a corner, use the mouse wheel to scale the chart around that corner. Scroll up to enlarge the chart or down to shrink it. Hold **Ctrl** to move all four corners together, or hold **Ctrl** and **Alt** and drag horizontally to rotate the chart around the selected corner. Hold **Shift** for precision movement or rotation. These modifiers can be pressed or released after the drag has started.

Use **Center Overlay** to reset the overlay to a 28:21 rectangle centered in the visible viewer and occupying approximately 10 percent of the viewer area.

Expand **Corner Positions** when numeric corner coordinates are more convenient than dragging.

### Lat-long panoramas

For an equirectangular HDRI, first align the overlay roughly around the chart in the original lat-long image, then select **Lat/Long Projection** below the overlay controls. MacBlend centers the undistorted rectilinear view on the chart's middle axis and automatically adjusts roll so that axis forms the horizon, then projects the existing corners into the view so the alignment remains consistent. The calculations wrap horizontally, so this also works when the chart is split across the left and right image edges.

Align and sample precisely in the projected view as usual; MacBlend reads the corresponding wrapped pixels from the original HDRI. Select **Disable Lat/Long Projection** to return to the original image using the same button. The temporary projected image is removed when leaving the view.

Heading, Elevation, Roll, Field of View, and the final Patch Size are stored with the sampled colors on the original image. Projection controls update the projected image immediately, and sampling maps the final chart corners back to normalized positions on the original flat image. Reopening the projected view reuses these settings until the overlay is moved in the flat image view; moving it discards the stored projection and recalculates from the new alignment on the next activation.

## Sample patches

Select **Sample Chart** after alignment. MacBlend reads the decoded pixel buffer once, averages the configured region around every patch center, stores 24 RGB values on the image, and hides the overlay.

Successfully sampled images appear in **Sampled Images**. Select an entry to inspect its 24 color swatches. The trash button clears that image's samples and removes it from any active source or target selection.

## Sampling guidance

- Keep every sample region inside its patch and away from borders, glare, shadows, and chart damage.
- Use source imagery without clipped channels when possible.
- Sampling the same image twice replaces its previous values.
- The [display/view transform](https://docs.blender.org/manual/en/4.2/render/color_management.html#display-transforms) does not alter sampled values.
- Changing the image input color space does alter sampled values; resample after changing it.

# Sampling

## Context

[Image Editor](https://docs.blender.org/manual/en/latest/editors/image/index.html) > Sidebar > **MacBlend**

MacBlend samples the 24 patches of a 6-by-4 Macbeth ColorChecker from Blender's decoded, scene-linear image data. The image [**Color Space**](https://docs.blender.org/manual/en/latest/editors/image/image_settings.html#bpy-types-colormanagedinputcolorspacesettings-name) must therefore describe the source file correctly.

## Chart Overlay

<!-- Replacement image: Blender Image Editor showing a photographed Macbeth ColorChecker. The MacBlend sidebar is open, Show Overlay is enabled, all four corner handles touch the chart corners, and every colored sample square remains inside its patch. -->
```{figure} ../.images/sampling-overlay.jpg
:alt: Placeholder for the aligned MacBlend chart overlay in the Image Editor
:align: center

Chart overlay aligned to the outer corners of a Macbeth ColorChecker.
```

**Show Overlay**
: Shows the Macbeth chart overlay in the Image Editor. It is initialized in the center of the image with a patch size of 40 by 40 pixels. Later toggles preserve edits.

**Patch Size**
: Sets the size of the patches used for sampling, in image pixels. When **Sample Chart** is used, MacBlend averages the pixels inside each patch. Larger patches average more pixels, but must remain inside the chart's colored areas.

**Overlay Opacity**
: Controls the opacity of the color swatches shown inside the chart overlay. Before the image has been sampled, the swatches show built-in sRGB reference colors; afterward, they show the stored sampled colors. This setting affects only the overlay display, not the sampled values.

**Flip Horizontal**, **Flip Vertical**
: Reverses the patch order to match the chart orientation.

**Center Overlay**
: Re-initializes the chart overlay at a size that fills approximately one tenth of the viewer area. **Patch Size** is recalculated as a result.

**Reset Chart**
: Restores the initial image-space position and patch size.

**Corner Positions**
: Exposes image-space coordinates for the four handles.

### Mouse Controls

Dragging a handle moves one corner. The following modifiers remain available after the drag has started:

{kbd}`Wheel`
: Scales the chart around the active corner.

{kbd}`Ctrl`
: Moves all four corners together.

{kbd}`Ctrl-Alt` and horizontal drag
: Rotates the chart around the active corner.

{kbd}`Shift`
: Enables precision movement or rotation.

```{note}
Keep every visible sample region away from patch borders, glare, shadows, reflections, and chart damage.
```

## Lat-Long Projection

<!-- Replacement image: Blender Image Editor in MacBlend's rectilinear projection view of an equirectangular HDRI. The chart is centered and level, the overlay is precisely aligned, and Heading, Elevation, Roll, Field of View, and Patch Size controls are visible. -->
```{figure} ../.images/lat-long-projection.jpg
:alt: Placeholder for a ColorChecker aligned in the lat-long projection view
:align: center

Rectilinear chart view projected from an equirectangular image.
```

**Lat/Long Projection** creates an undistorted rectilinear view centered on the chart's middle axis.

**Heading**, **Elevation**, **Roll**, **Field of View**
: Adjust the projected view.

**Disable Lat/Long Projection**
: Returns to the original image and removes the temporary projection.

Projection settings and the final **Patch Size** are stored with the samples on the original image.

```{important}
Moving the overlay in the flat image resets the sampling area. Sample a lat-long image's chart in the projected lat-long view to avoid sampling incorrect areas.
```

## Sample Chart

**Sample Chart** averages each projected sample region, stores 24 RGB values on the image, and hides the overlay. Sampling the same image again replaces its previous values.

<!-- Replacement image: MacBlend's Sampled Images panel showing one selected image and a 6-by-4 grid of the 24 measured color swatches, with the remove button visible beside the image entry. -->
```{figure} ../.images/sampled-images.jpg
:alt: Placeholder for the Sampled Images panel and its 24 color swatches
:align: center

Measured patches for the selected sampled image.
```

Sampled images become available as calibration sources and targets. Removing an entry clears its samples and any active source or target selection that uses it.

```{important}
The [display transform](https://docs.blender.org/manual/en/latest/render/color_management.html#display-transforms) does not affect sampled values. Changing the image input **Color Space** does; sample the chart again after changing it.
```

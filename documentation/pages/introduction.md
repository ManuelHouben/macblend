# Introduction

MacBlend calibrates images from a photographed Macbeth ColorChecker. It compares the chart's 24 measured patches with reference values or a second sampled chart, then fits a single RGB matrix that brings the source closer to the target.

The transform can be created as compositor or shader nodes, or exported in both directions as `.cube` LUTs.

## Requirements

- Blender 4.2 or newer
- A source image containing a visible 6-by-4 Macbeth chart
- Knowledge of how each image was recorded or exported

## Installation

MacBlend is available from the [Blender Extensions platform](https://extensions.blender.org/add-ons/macblend/). Release archives are also published on [GitHub](https://github.com/ManuelHouben/macblend/releases).

See [Installing Extensions](https://docs.blender.org/manual/en/latest/editors/preferences/extensions.html#installing-extensions) in the Blender Manual.

## Preferences

Open **Edit > Preferences > Add-ons > MacBlend** to configure the initial values used by MacBlend. Patch Size and Overlay Opacity apply to new image sampling data. Normalization and Exposure Node Creation apply to new calibration settings. LUT Size and LUT Clamping initialize the options shown each time the LUT export browser opens.

Changing a default does not replace a value already customized on an image or scene.

## Editors

MacBlend adds a sidebar tab to the following editors:

[Image Editor](https://docs.blender.org/manual/en/latest/editors/image/index.html)
: Chart alignment, sampling, and the list of sampled images.

[Compositor](https://docs.blender.org/manual/en/latest/editors/compositor.html)
: Calibration nodes and LUT export.

[Shader Editor](https://docs.blender.org/manual/en/latest/editors/shader_editor.html)
: Calibration nodes and LUT export.

## Color management

The image [**Color Space**](https://docs.blender.org/manual/en/latest/glossary/index.html#term-Color-Space) determines how Blender decodes stored RGB values. MacBlend samples those decoded values; an incorrect input transform therefore produces an incorrect calibration.

```{important}
The source image's **Color Space** must match the transform used to record or export the file.
```

## Workflow

The Blender workflow has two parts:

[Sampling](sampling/index.md)
: Align a perspective overlay and measure the 24 chart patches. A second sampled chart can serve as the target.

[Calibration](calibration/index.md)
: Fit a Forward or Inverse matrix and create nodes in a supported node editor.

The resulting transform can optionally be written as paired Forward and Inverse `.cube` files. See [LUT Export](export/index.md).

See [Method and Limitations](method.md) for the calculation, transform directions, and capture assumptions.

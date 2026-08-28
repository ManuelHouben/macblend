# Introduction

Think of a Macbeth ColorChecker as a known set of paint swatches. MacBlend compares all 24 swatches in your image with a target, then builds one broad correction that brings them closer. It can create the correction as compositor or shader nodes and export it in both directions as `.cube` LUTs.

It brings the chart-matching workflows documented by Marco Meyer in [mmColorTarget](https://www.marcomeyer-vfx.de/posts/mmcolortarget-nuke-gizmo/) and Jed Smith in [CalibrateMacbeth](https://gist.github.com/jedypod/798b365ea64e8121999e7036ae7e0217) into Blender.

## Requirements

- Blender 4.2 or newer
- A source image containing a visible 6-by-4 Macbeth chart
- Knowledge of how each image was recorded or exported

## Installation

Install MacBlend from the [Blender Extensions platform](https://extensions.blender.org/add-ons/macblend/).

When the Extensions platform is unavailable, download an extension ZIP from [GitHub releases](https://github.com/ManuelHouben/macblend/releases).

See Blender's [Installing Extensions](https://docs.blender.org/manual/en/4.2/editors/preferences/extensions.html#installing-extensions) documentation for installation instructions.

MacBlend adds a **MacBlend** tab to the [Image Editor](https://docs.blender.org/manual/en/4.2/editors/image/index.html) sidebar and to the sidebar of supported [Compositor](https://docs.blender.org/manual/en/4.2/editors/compositor.html) and [Shader Editor](https://docs.blender.org/manual/en/4.2/editors/shader_editor.html) node editors.

## Color management

Color management tells Blender how to interpret the RGB values in an image. Set the image's [**Color Space**](https://docs.blender.org/manual/en/latest/glossary/index.html#term-Color-Space) to match how it was recorded or exported so MacBlend receives the right colors; if Blender starts with the wrong colors, the correction will also be wrong.

The [Method and limitations](method.md#before-you-start) page explains the setup and the color science behind it.

## Workflow

1. Load and correctly tag the source image.
2. Align the chart overlay and sample its 24 patches.
3. Optionally sample a target image.
4. Open a supported node editor and configure the calibration.
5. Create Forward or Inverse nodes, or export both LUT directions.

See [Method and limitations](method.md) for the calculation, normalization behavior, transform directions, and assumptions.

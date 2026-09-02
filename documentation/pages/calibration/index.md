# Calibration

## Context

[Compositor](https://docs.blender.org/manual/en/latest/editors/compositor.html) or [Shader Editor](https://docs.blender.org/manual/en/latest/editors/shader_editor.html) > Sidebar > **MacBlend**

Calibration fits a 3-by-3 RGB matrix between a sampled source and either a built-in chart reference or another sampled image.

<!-- Replacement image: MacBlend calibration panel in Blender's Compositor. A sampled source image is selected, Use reference values as target is enabled, Target shows an Auto-detected status, Normalize and Create Exposure Node are enabled, and the Forward and Inverse operators are visible. -->
```{figure} ../.images/calibration-panel.jpg
:alt: Placeholder for the MacBlend calibration panel in a node editor
:align: center

Reference-based calibration with an automatically detected target gamut.
```

## Settings

**Image**
: The sampled source. Only images containing all 24 patch values are available.

**Use reference values as target**
: Uses the built-in chart measurements. When disabled, **Target** selects a second sampled image.

**Target**
: Selects the linear gamut of the built-in target values. MacBlend initializes it from Blender's **File Color Space** when the source is selected.

- ✅ **Auto-detected** means the target matches the file color space.
- **Target overridden** means another target was selected manually.
- ❌ **Couldn't detect target gamut from scene** means MacBlend could not find a match and selected **Linear Rec. 709** as a fallback.

**Normalize**
: Removes brightness changes from the matrix calculation so the matrix captures only color shifts.

**Create Exposure Node**
: Creates a separate brightness adjustment node that matches the target brightness.

**Node Name**
: Base name for generated Forward and Inverse matrix nodes. The default is `MacBlendCalibration`.

```{important}
The **Target** setting's [gamut](https://docs.blender.org/manual/en/latest/glossary/index.html#term-Color-Gamut) should match the **Color Space** setting of your file. A gamut is the range of colors that a color space can represent.
```

## Operators

**Forward**
: Creates nodes that transform the sampled source toward the selected target.

**Inverse**
: Creates nodes that transform the selected target toward the sampled source.

## Matrix Result

The fitted matrix appears in the panel after a successful solve. A valid matrix does not guarantee a useful calibration; poor illumination, clipping, an incorrect input transform, or reversed chart orientation can all bias the result.

See [Method and Limitations](../method.md) for the calculation and capture assumptions.

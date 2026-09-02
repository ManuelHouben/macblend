# LUT Export

## Context

[Compositor](https://docs.blender.org/manual/en/latest/editors/compositor.html) or [Shader Editor](https://docs.blender.org/manual/en/latest/editors/shader_editor.html) > Sidebar > **MacBlend**

**Export LUTs** writes paired Forward and Inverse LUTs in `.cube` format.

## Settings

**LUT Size**
: Selects a $17^3$, $33^3$, or $65^3$ lattice. The initial size comes from the MacBlend add-on preferences; $33^3$ is suitable for general use. A larger lattice increases file size and processing cost without improving the fitted matrix.

**Clamp to 0-1**
: Restricts every output channel to the unit range. This supports applications that reject extended values, but discards negative values and values above one.

## Files

Filenames use `{working space}_{source}_{target}[_normalized]_{direction}.cube`. The first token identifies Blender's scene-linear working space. A reference target uses the selected targets' name; an image target uses the target image name.

Every export creates one `_Forward.cube` and one `_Inverse.cube` file. Existing destinations are listed for confirmation before replacement.

```{note}
When **Normalize** is enabled, exported LUTs correct color shifts only; they do not match the target brightness. To create LUTs that correct both color and brightness, disable **Normalize** before exporting.
```

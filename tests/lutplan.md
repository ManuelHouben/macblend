# Dev Guide: Export a 3×3 Color Matrix as a 3D LUT (Blender 5.2 Extension)

## 1. Goal

Given a 3×3 (optionally 3×4 with an offset column) color matrix, generate a
`.cube` 3D LUT file that reproduces the same transform when loaded into
DaVinci Resolve, Premiere Pro, After Effects, or Nuke. Ship this as an
`bpy.types.Operator` inside a Blender extension (manifest-based, not legacy
`bl_info` addon).

## 2. Inputs / Outputs

- **Input:** `matrix: list[list[float]]`, shape 3×3 (pure linear) or 3×4
  (linear + offset column, for exposure/white-point shifts). Assume it
  operates on RGB values normalized to `[0, 1]`.
- **Output:** a single `.cube` file (Adobe/Iridas 3D LUT format) — the most
  broadly compatible LUT format across NLE/compositing tools.

## 3. `.cube` format — follow this exactly

```
TITLE "My Calibration Matrix"
LUT_3D_SIZE 33
DOMAIN_MIN 0.0 0.0 0.0
DOMAIN_MAX 1.0 1.0 1.0
0.000000 0.000000 0.000000
0.031250 0.002100 0.001800
...
```

Rules:
- `LUT_3D_SIZE N` is required; `TITLE`/`DOMAIN_MIN`/`DOMAIN_MAX` are optional
  (omit domain lines if using default `[0,1]`).
- Exactly `N³` data rows follow the header, each `R G B` (space-separated
  floats).
- **Row order: red increments fastest, then green, then blue** (blue is the
  outermost loop). Getting this order wrong silently produces a broken LUT —
  it will load without error but grade incorrectly.
- Use `.` as decimal separator regardless of system locale — never use
  Python's plain `str(float)`/locale-aware formatting; use an explicit
  `f"{v:.6f}"`.

## 4. Core algorithm

```python
def generate_cube_lut(matrix, size=33, title=None, clamp=True):
    """
    matrix: 3x3 or 3x4 nested list/tuple of floats.
    size:   LUT_3D_SIZE (17/33/65 are the common choices; 33 is a good default).
    clamp:  clip output to [0,1] (recommended for broad compatibility;
            set False + emit DOMAIN_MAX > 1 only if you know the target
            app supports extended-range LUTs).
    Returns: list[str] lines ready to write to a .cube file.
    """
    has_offset = len(matrix[0]) == 4
    lines = []
    if title:
        lines.append(f'TITLE "{title}"')
    lines.append(f"LUT_3D_SIZE {size}")
    lines.append("")

    denom = size - 1  # size must be >= 2
    for bi in range(size):          # blue: slowest-varying
        b = bi / denom
        for gi in range(size):      # green: middle
            g = gi / denom
            for ri in range(size):  # red: fastest-varying
                r = ri / denom
                out = []
                for row in matrix:
                    v = row[0]*r + row[1]*g + row[2]*b
                    if has_offset:
                        v += row[3]
                    if clamp:
                        v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
                    out.append(v)
                lines.append(f"{out[0]:.6f} {out[1]:.6f} {out[2]:.6f}")
    return lines
```

Notes for the implementing LLM:
- No `numpy` dependency required — the matrix multiply is 3×3, pure Python
  is fast enough even at `size=65` (274,625 rows, well under a second).
  If numpy is already imported elsewhere in the extension, vectorizing is a
  fine optional optimization, but don't add it as a hard dependency (extra
  wheels in `blender_manifest.toml` add review/packaging overhead).
- Validate `size >= 2` and matrix shape before generating.
- Keep the writer a pure function (matrix in, lines out) so it's unit
  testable without touching `bpy`.

## 5. Blender extension integration

### File layout
```
my_lut_export/
├─ blender_manifest.toml
├─ __init__.py
├─ lut_writer.py      # pure logic from §4, no bpy import
└─ operators.py        # bpy.types.Operator wrapping lut_writer
```

### `blender_manifest.toml` (essentials)
```toml
schema_version = "1.0.0"
id = "matrix_to_cube_lut"
version = "1.0.0"
name = "Matrix to Cube LUT"
tagline = "Export a color matrix as a 3D LUT"
maintainer = "Your Name <you@example.com>"
type = "add-on"
blender_version_min = "5.2.0"
license = ["SPDX:GPL-3.0-or-later"]
```
No special `permissions` entry is needed — writing to a user-chosen path via
the file browser is standard operator behavior, not restricted filesystem
access.

### Operator skeleton (`operators.py`)
```python
import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, IntProperty, BoolProperty
from .lut_writer import generate_cube_lut

class EXPORT_OT_matrix_cube_lut(bpy.types.Operator, ExportHelper):
    bl_idname = "export_color.matrix_cube_lut"
    bl_label = "Export Matrix as 3D LUT (.cube)"
    bl_options = {'REGISTER'}

    filename_ext = ".cube"
    filter_glob: StringProperty(default="*.cube", options={'HIDDEN'})

    lut_size: IntProperty(name="LUT Size", default=33, min=2, max=65)
    clamp_output: BoolProperty(name="Clamp to 0-1", default=True)

    def execute(self, context):
        matrix = get_matrix_from_wherever(context)  # your own source
        lines = generate_cube_lut(
            matrix, size=self.lut_size, clamp=self.clamp_output
        )
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.report({'INFO'}, f"LUT written: {self.filepath}")
        return {'FINISHED'}

def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_matrix_cube_lut.bl_idname, text="Color Matrix (.cube)")

classes = (EXPORT_OT_matrix_cube_lut,)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
```

`__init__.py` just imports and calls `operators.register()` /
`operators.unregister()`.

## 6. UI options worth exposing

- `lut_size`: dropdown/enum of 17 / 33 / 65 rather than a free int (safer,
  matches what grading tools expect).
- `clamp_output`: on by default; document that turning it off only makes
  sense if the target app supports extended-range LUTs.
- Optional `title` string → written to `TITLE`.
- If the matrix source supports a 3×4 affine form (matrix + offset), surface
  that as a separate "include exposure/offset" checkbox rather than always
  assuming pure 3×3.

## 7. Edge cases to handle

- Reject/validate matrix shape before generating (must be 3×3 or 3×4).
- `size` must be ≥ 2 (avoid divide-by-zero in `denom`).
- Always write floats with explicit `.` decimal separator (locale bug is the
  most common real-world break here).
- Overwrite confirmation is handled automatically by `ExportHelper`; no
  extra code needed.
- If exposing this via a non-export-dialog UI (e.g., a panel button that
  writes to a fixed path), still route through the same `filepath` handling
  so relative/`//` Blender paths get resolved with `bpy.path.abspath()`.

## 8. Testing checklist

- **Identity matrix** (`[[1,0,0],[0,1,0],[0,0,1]]`) → every output row
  should equal its input `r g b` within float rounding.
- **Known matrix** → hand-compute 2–3 corner/mid points and diff against
  generated rows.
- **Round-trip in a real app**: load the `.cube` in DaVinci Resolve (Color
  page → apply as node LUT) or After Effects (Apply Color LUT) with a
  ramp/gradient test image and confirm it matches applying the matrix
  directly.
- Confirm row count is exactly `size**3` and file has no trailing/missing
  header blank line issues (some apps are strict parsers).
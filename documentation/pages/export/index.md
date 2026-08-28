# LUT export

**Export LUTs** calculates the configured transform and writes both Forward and Inverse LUTs in Adobe/Iridas `.cube` format.

## Export options

**LUT Size** selects a $17^3$, $33^3$, or $65^3$ lattice. A size of 33 is the default and is a practical general-purpose choice. Larger LUTs require more storage and processing but do not improve the underlying fitted matrix.

**Clamp to 0-1** restricts output channels to the standard unit range. Leave it disabled when the destination supports extended-range LUT values and preserving highlights or negative values matters. Enable it for applications that reject values outside zero to one.

Choose an output directory and confirm the export. If either destination filename already exists, MacBlend lists the conflicts and asks before replacing the files.

## Files

Filenames describe the working space, input image, target, normalization state, and transform direction. Every export produces one filename ending in `_Forward.cube` and one ending in `_Inverse.cube`.

The files include a title, lattice size, domain minimum and maximum, and RGB values with red changing fastest. Test exported LUTs in the destination application because LUT interpretation and out-of-range handling vary between hosts.

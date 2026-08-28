MacBlend Documentation
======================

.. image:: .images/icon.png
   :alt: MacBlend ColorChecker and pipette icon
   :width: 128px

Calibrate images containing a Macbeth ColorChecker directly in Blender. MacBlend samples all 24 chart patches, calculates forward and inverse color transforms, creates compositor or shader nodes, and exports paired ``.cube`` LUTs.

MacBlend is hosted on `GitHub <https://github.com/ManuelHouben/macblend>`_. Report bugs and request features through the `issue tracker <https://github.com/ManuelHouben/macblend/issues>`_.

The workflow adapts Marco Meyer's `mmColorTarget <https://www.marcomeyer-vfx.de/posts/mmcolortarget-nuke-gizmo/>`_ and Jed Smith's `CalibrateMacbeth <https://gist.github.com/jedypod/798b365ea64e8121999e7036ae7e0217>`_. Read :doc:`method` before evaluating a transform: scene-linear data, correct IDTs, and capture conditions are part of the method.

.. toctree::
   :maxdepth: 2
   :caption: Table of Contents
   :hidden:

   Introduction <introduction>
   Method and limitations <method>
   Sampling a chart <sampling/index>
   Calibration transforms <calibration/index>
   LUT export <export/index>
   Troubleshooting <troubleshooting>

MacBlend
========

.. image:: .images/icon.png
   :alt: MacBlend ColorChecker and pipette icon
   :width: 128px

MacBlend calibrates images containing a Macbeth ColorChecker directly in Blender. It samples all 24 chart patches, calculates forward and inverse color transforms, creates compositor or shader nodes, and exports paired ``.cube`` LUTs.

MacBlend is hosted on `GitHub <https://github.com/ManuelHouben/macblend>`_. Report bugs and request features through the `issue tracker <https://github.com/ManuelHouben/macblend/issues>`_.

Scene-linear data, the correct input transform, and suitable capture conditions are essential to the :doc:`method`.

.. toctree::
   :maxdepth: 2
   :caption: Sections
   :hidden:

   Introduction <introduction>
   Method and Limitations <method>
   Sampling <sampling/index>
   Calibration <calibration/index>
   LUT Export <export/index>
   Troubleshooting <troubleshooting>

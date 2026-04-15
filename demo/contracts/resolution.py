"""Compatibility shim for the resolution contract.

The implementation now lives in ``power_atlas.contracts.resolution``. This
legacy module remains so existing demo imports continue to work during the
staged migration.
"""

from power_atlas.contracts.resolution import ALIGNMENT_VERSION

__all__ = ["ALIGNMENT_VERSION"]

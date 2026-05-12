"""Transitional compatibility alias for public backend router helpers.

Keep this module until external callers migrate to ``power_atlas.api``.
New callers should import router helpers from ``power_atlas.api`` directly.
"""

from power_atlas.api import backend_router, build_backend_router

__all__ = ["backend_router", "build_backend_router"]
"""Transitional compatibility alias for public backend router helpers.

Keep this module until external callers migrate to ``power_atlas.api``.
New callers should import router helpers from ``power_atlas.api`` directly.
"""

import warnings


warnings.warn(
	"power_atlas.interfaces.api.backend_routes is deprecated; import backend "
	"router helpers from power_atlas.api instead. This compatibility alias "
	"will be kept only until external callers are migrated.",
	DeprecationWarning,
	stacklevel=2,
)

from power_atlas.api import backend_router, build_backend_router

__all__ = ["backend_router", "build_backend_router"]
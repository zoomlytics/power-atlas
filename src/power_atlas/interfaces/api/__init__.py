"""Transitional compatibility alias for the public backend facade.

Keep this module until external callers migrate to ``power_atlas.api``.
New callers should import the backend surface from ``power_atlas.api`` directly.
"""

import warnings


warnings.warn(
	"power_atlas.interfaces.api is deprecated; import backend helpers from "
	"power_atlas.api instead. This compatibility alias will be kept only until "
	"external callers are migrated.",
	DeprecationWarning,
	stacklevel=2,
)

from power_atlas.api import BackendAppOptions, backend_router, build_backend_router, create_backend_app

__all__ = [
	"BackendAppOptions",
	"backend_router",
	"build_backend_router",
	"create_backend_app",
]
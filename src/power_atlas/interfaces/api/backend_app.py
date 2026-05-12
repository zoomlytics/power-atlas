"""Transitional compatibility alias for public backend app helpers.

Keep this module until external callers migrate to ``power_atlas.api``.
New callers should import these helpers from ``power_atlas.api`` directly.
"""

import warnings


warnings.warn(
	"power_atlas.interfaces.api.backend_app is deprecated; import backend app "
	"helpers from power_atlas.api instead. This compatibility alias will be "
	"kept only until external callers are migrated.",
	DeprecationWarning,
	stacklevel=2,
)

from power_atlas.api import BackendAppOptions, create_backend_app, lifespan

__all__ = ["BackendAppOptions", "create_backend_app", "lifespan"]
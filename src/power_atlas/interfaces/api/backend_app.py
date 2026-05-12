"""Transitional compatibility alias for public backend app helpers.

Keep this module until external callers migrate to ``power_atlas.api``.
New callers should import these helpers from ``power_atlas.api`` directly.
"""

from power_atlas.api import BackendAppOptions, create_backend_app, lifespan

__all__ = ["BackendAppOptions", "create_backend_app", "lifespan"]
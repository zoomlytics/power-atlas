from __future__ import annotations

import importlib
import sys
import warnings


def test_interfaces_api_aliases_public_api_facade() -> None:
    api_module = importlib.import_module("power_atlas.api")

    for module_name in (
        "power_atlas.interfaces.api.backend_routes",
        "power_atlas.interfaces.api.backend_app",
        "power_atlas.interfaces.api",
    ):
        sys.modules.pop(module_name, None)

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        interfaces_api_module = importlib.import_module("power_atlas.interfaces.api")
        interfaces_backend_app_module = importlib.import_module(
            "power_atlas.interfaces.api.backend_app"
        )
        interfaces_backend_routes_module = importlib.import_module(
            "power_atlas.interfaces.api.backend_routes"
        )

    assert interfaces_api_module.BackendAppOptions is api_module.BackendAppOptions
    assert interfaces_api_module.backend_router is api_module.backend_router
    assert interfaces_api_module.build_backend_router is api_module.build_backend_router
    assert interfaces_api_module.create_backend_app is api_module.create_backend_app

    assert interfaces_backend_app_module.BackendAppOptions is api_module.BackendAppOptions
    assert interfaces_backend_app_module.create_backend_app is api_module.create_backend_app
    assert interfaces_backend_app_module.lifespan is api_module.lifespan

    assert interfaces_backend_routes_module.backend_router is api_module.backend_router
    assert (
        interfaces_backend_routes_module.build_backend_router
        is api_module.build_backend_router
    )

    warning_messages = [str(item.message) for item in caught_warnings]
    assert len(warning_messages) == 3
    assert warning_messages[0].startswith("power_atlas.interfaces.api is deprecated")
    assert warning_messages[1].startswith(
        "power_atlas.interfaces.api.backend_app is deprecated"
    )
    assert warning_messages[2].startswith(
        "power_atlas.interfaces.api.backend_routes is deprecated"
    )
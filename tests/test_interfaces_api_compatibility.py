from __future__ import annotations

import importlib


def test_interfaces_api_aliases_public_api_facade() -> None:
    api_module = importlib.import_module("power_atlas.api")
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
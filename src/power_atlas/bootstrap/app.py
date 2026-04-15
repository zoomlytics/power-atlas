from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from power_atlas.settings import AppSettings


@dataclass(frozen=True)
class AppBootstrap:
    settings: AppSettings


def build_settings(environ: Mapping[str, str] | None = None) -> AppSettings:
    return AppSettings.from_env(environ=environ)


def bootstrap_app(environ: Mapping[str, str] | None = None) -> AppBootstrap:
    return AppBootstrap(settings=build_settings(environ=environ))


__all__ = ["AppBootstrap", "bootstrap_app", "build_settings"]

from __future__ import annotations

import importlib
import pkgutil
from importlib import metadata
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .backends import EngineBackend, EngineConfig
from .config import ConfigError
from .logging import get_logger

logger = get_logger(__name__)


def _discover_backends() -> dict[str, EngineBackend]:
    import takopi.runners as runners_pkg

    backends: dict[str, EngineBackend] = {}
    try:
        entry_points = metadata.entry_points().select(group="takopi.backends")
    except Exception as exc:
        logger.warning(
            "backends.entry_points_failed",
            error=str(exc),
            error_type=exc.__class__.__name__,
        )
        entry_points = []

    for ep in entry_points:
        try:
            obj = ep.load()
        except Exception as exc:
            logger.warning(
                "backends.load_failed",
                entry_point=ep.name,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            continue
        backend = obj
        if callable(obj) and not isinstance(obj, EngineBackend):
            try:
                backend = obj()
            except Exception as exc:
                logger.warning(
                    "backends.factory_failed",
                    entry_point=ep.name,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                continue
        if not isinstance(backend, EngineBackend):
            logger.warning(
                "backends.invalid",
                entry_point=ep.name,
                value=repr(obj),
            )
            continue
        if backend.id in backends:
            logger.warning("backends.duplicate", backend_id=backend.id)
            continue
        backends[backend.id] = backend
    prefix = runners_pkg.__name__ + "."

    for module_info in pkgutil.iter_modules(runners_pkg.__path__, prefix):
        module_name = module_info.name
        mod = importlib.import_module(module_name)

        backend = getattr(mod, "BACKEND", None)
        if backend is None:
            continue
        if not isinstance(backend, EngineBackend):
            raise RuntimeError(f"{module_name}.BACKEND is not an EngineBackend")
        if backend.id in backends:
            logger.warning("backends.duplicate", backend_id=backend.id)
            continue
        backends[backend.id] = backend

    return backends


@cache
def _backends() -> Mapping[str, EngineBackend]:
    backends = _discover_backends()
    return MappingProxyType(backends)


def get_backend(engine_id: str) -> EngineBackend:
    backends = _backends()
    try:
        return backends[engine_id]
    except KeyError as exc:
        available = ", ".join(sorted(backends))
        raise ConfigError(
            f"Unknown engine {engine_id!r}. Available: {available}."
        ) from exc


def list_backends() -> list[EngineBackend]:
    backends = _backends()
    return [backends[key] for key in sorted(backends)]


def list_backend_ids() -> list[str]:
    return sorted(_backends())


def get_engine_config(
    config: dict[str, Any], engine_id: str, config_path: Path
) -> EngineConfig:
    engine_cfg = config.get(engine_id) or {}
    if not isinstance(engine_cfg, dict):
        raise ConfigError(
            f"Invalid `{engine_id}` config in {config_path}; expected a table."
        )
    return engine_cfg

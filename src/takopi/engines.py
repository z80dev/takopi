from __future__ import annotations

import importlib
import pkgutil
from importlib import metadata
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .backends import EngineBackend, EngineConfig
from .config import ConfigError
from .logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EngineSpec:
    engine: str
    backend: EngineBackend
    config: EngineConfig
    derived_from: str | None = None


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


def resolve_engine_specs(
    *, config: dict[str, Any], config_path: Path, backends: list[EngineBackend]
) -> list[EngineSpec]:
    backends_by_id = {backend.id: backend for backend in backends}
    engine_tables: dict[str, dict[str, Any]] = {}

    for key, value in config.items():
        if key in backends_by_id:
            if not isinstance(value, dict):
                raise ConfigError(
                    f"Invalid `{key}` config in {config_path}; expected a table."
                )
            engine_tables[key] = value

    for key, value in config.items():
        if not isinstance(value, dict):
            continue
        if "derives-from" not in value:
            continue
        if key in backends_by_id:
            raise ConfigError(
                f"Invalid `{key}` config in {config_path}; "
                "`derives-from` is only allowed for derived runners."
            )
        engine_tables[key] = value

    resolved: dict[str, EngineSpec] = {}
    resolving: set[str] = set()

    def resolve_engine(engine_id: str) -> EngineSpec:
        if engine_id in resolved:
            return resolved[engine_id]
        if engine_id in resolving:
            raise ConfigError(
                f"Circular `derives-from` reference for engine {engine_id!r} in "
                f"{config_path}."
            )
        resolving.add(engine_id)
        cfg = engine_tables.get(engine_id)
        if cfg is None:
            backend = backends_by_id.get(engine_id)
            if backend is None:
                raise ConfigError(
                    f"Unknown engine {engine_id!r} in {config_path}."
                )
            spec = EngineSpec(engine=engine_id, backend=backend, config={})
            resolved[engine_id] = spec
            resolving.remove(engine_id)
            return spec

        derived_from = cfg.get("derives-from")
        if derived_from is None:
            backend = backends_by_id.get(engine_id)
            if backend is None:
                raise ConfigError(
                    f"Unknown engine {engine_id!r} in {config_path}."
                )
            spec = EngineSpec(engine=engine_id, backend=backend, config=dict(cfg))
            resolved[engine_id] = spec
            resolving.remove(engine_id)
            return spec

        if not isinstance(derived_from, str) or not derived_from.strip():
            raise ConfigError(
                f"Invalid `derives-from` for {engine_id!r} in {config_path}; "
                "expected a non-empty string."
            )
        derived_from = derived_from.strip()
        base_spec = resolve_engine(derived_from)
        overrides = {key: value for key, value in cfg.items() if key != "derives-from"}
        merged = {**base_spec.config, **overrides}
        spec = EngineSpec(
            engine=engine_id,
            backend=base_spec.backend,
            config=merged,
            derived_from=derived_from,
        )
        resolved[engine_id] = spec
        resolving.remove(engine_id)
        return spec

    for backend in backends:
        resolve_engine(backend.id)

    for key, value in engine_tables.items():
        if "derives-from" in value:
            resolve_engine(key)

    return [resolved[key] for key in sorted(resolved)]

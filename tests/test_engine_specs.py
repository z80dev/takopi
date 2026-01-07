from pathlib import Path

import pytest

from takopi.backends import EngineBackend
from takopi.config import ConfigError
from takopi.engines import resolve_engine_specs
from takopi.runners.mock import Return, ScriptRunner


def _backend(engine_id: str) -> EngineBackend:
    return EngineBackend(
        id=engine_id,
        build_runner=lambda _cfg, _path: ScriptRunner(
            [Return(answer="ok")], engine=engine_id
        ),
    )


def test_resolve_engine_specs_base_config() -> None:
    backends = [_backend("codex")]
    config = {"codex": {"profile": "default"}}
    specs = resolve_engine_specs(
        config=config, config_path=Path("takopi.toml"), backends=backends
    )
    assert len(specs) == 1
    assert specs[0].engine == "codex"
    assert specs[0].config == {"profile": "default"}


def test_resolve_engine_specs_derived() -> None:
    backends = [_backend("codex")]
    config = {
        "codex": {"profile": "base", "temp": 0.1},
        "codex-fast": {"derives-from": "codex", "temp": 0.9},
    }
    specs = resolve_engine_specs(
        config=config, config_path=Path("takopi.toml"), backends=backends
    )
    derived = {spec.engine: spec for spec in specs}["codex-fast"]
    assert derived.backend.id == "codex"
    assert derived.config == {"profile": "base", "temp": 0.9}
    assert derived.derived_from == "codex"


def test_resolve_engine_specs_rejects_non_table() -> None:
    backends = [_backend("codex")]
    with pytest.raises(ConfigError):
        resolve_engine_specs(
            config={"codex": "bad"},
            config_path=Path("takopi.toml"),
            backends=backends,
        )


def test_resolve_engine_specs_rejects_backend_with_derives_from() -> None:
    backends = [_backend("codex")]
    with pytest.raises(ConfigError):
        resolve_engine_specs(
            config={"codex": {"derives-from": "other"}},
            config_path=Path("takopi.toml"),
            backends=backends,
        )


def test_resolve_engine_specs_rejects_empty_derives_from() -> None:
    backends = [_backend("codex")]
    with pytest.raises(ConfigError):
        resolve_engine_specs(
            config={"codex-fast": {"derives-from": " "}},
            config_path=Path("takopi.toml"),
            backends=backends,
        )


def test_resolve_engine_specs_rejects_circular_derivation() -> None:
    backends = [_backend("codex")]
    config = {
        "codex": {},
        "a": {"derives-from": "b"},
        "b": {"derives-from": "a"},
    }
    with pytest.raises(ConfigError):
        resolve_engine_specs(
            config=config,
            config_path=Path("takopi.toml"),
            backends=backends,
        )

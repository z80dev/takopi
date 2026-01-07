from typing import cast
from pathlib import Path

import click
import typer
import pytest

from takopi import cli, engines
from takopi.backends import EngineBackend
from takopi.runners.mock import Return, ScriptRunner


def test_engine_discovery_skips_non_backend() -> None:
    ids = engines.list_backend_ids()
    assert "codex" in ids
    assert "claude" in ids
    assert "mock" not in ids


def test_cli_registers_engine_commands_sorted() -> None:
    command_names = [cmd.name for cmd in cli.app.registered_commands]
    engine_ids = engines.list_backend_ids()
    assert set(engine_ids) <= set(command_names)
    engine_commands = [name for name in command_names if name in engine_ids]
    assert engine_commands == engine_ids


def test_engine_commands_do_not_expose_engine_id_option() -> None:
    group = cast(click.Group, typer.main.get_command(cli.app))
    engine_ids = engines.list_backend_ids()

    ctx = group.make_context("takopi", [])

    for engine_id in engine_ids:
        command = group.get_command(ctx, engine_id)
        assert command is not None
        options: set[str] = set()
        for param in command.params:
            options.update(getattr(param, "opts", []))
            options.update(getattr(param, "secondary_opts", []))
        assert "--final-notify" in options
        assert "--debug" in options
        assert not any(opt.lstrip("-") == "engine-id" for opt in options)


def test_entry_point_backends_are_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeEntryPoint:
        def __init__(self, name: str) -> None:
            self.name = name

        def load(self) -> EngineBackend:
            return EngineBackend(
                id="epengine",
                build_runner=lambda _cfg, _path: ScriptRunner(
                    [Return(answer="ok")], engine="epengine"
                ),
            )

    class _FakeEntryPoints(list):
        def select(self, *, group: str) -> list:
            if group == "takopi.backends":
                return self
            return []

    monkeypatch.setattr(
        "takopi.engines.metadata.entry_points",
        lambda: _FakeEntryPoints([_FakeEntryPoint("epengine")]),
    )
    engines._backends.cache_clear()
    assert "epengine" in engines.list_backend_ids()
    engines._backends.cache_clear()


def test_build_router_skips_path_check_for_python_backends() -> None:
    backend = EngineBackend(
        id="pyonly",
        build_runner=lambda _cfg, _path: ScriptRunner(
            [Return(answer="ok")], engine="pyonly"
        ),
        cli_cmd=None,
        install_cmd=None,
    )
    spec = engines.EngineSpec(engine="pyonly", backend=backend, config={})
    router = cli._build_router(
        config_path=Path("takopi.toml"),
        engine_specs=[spec],
        default_engine="pyonly",
    )
    entry = router.entries[0]
    assert entry.available is True
    assert entry.issue is None

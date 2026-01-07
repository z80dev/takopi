from pathlib import Path

import anyio
import pytest

from takopi.plugins.api import MessagePreprocessContext, PluginContext, PluginRegistry
from takopi.plugins.manager import PluginDefinition, load_plugins
from takopi.plugins.api import TelegramCommand
from takopi.router import AutoRouter, RunnerEntry
from takopi.runners.mock import Return, ScriptRunner


class _SimplePlugin:
    id = "alpha"
    api_version = 1

    def register(self, registry: PluginRegistry, ctx: PluginContext) -> None:
        registry.add_telegram_command_provider(
            lambda: [TelegramCommand(command="alpha", description="alpha")]
        )


class _SecondPlugin:
    id = "bravo"
    api_version = 1

    def register(self, registry: PluginRegistry, ctx: PluginContext) -> None:
        registry.add_telegram_command_provider(
            lambda: [TelegramCommand(command="bravo", description="bravo")]
        )


class _BadRegisterPlugin:
    id = "bad"
    api_version = 1

    def register(self, registry: PluginRegistry, ctx: PluginContext) -> None:
        raise RuntimeError("boom")


class _BadPreprocessPlugin:
    id = "oops"
    api_version = 1

    def register(self, registry: PluginRegistry, ctx: PluginContext) -> None:
        async def preprocessor(_ctx: MessagePreprocessContext) -> tuple[str, str | None]:
            raise RuntimeError("nope")

        registry.add_message_preprocessor(preprocessor)


class _DistNamedPlugin:
    id = "ping"
    api_version = 1

    def register(self, registry: PluginRegistry, ctx: PluginContext) -> None:
        registry.add_telegram_command_provider(
            lambda: [TelegramCommand(command="ping", description="ping")]
        )


def _make_router() -> AutoRouter:
    runner = ScriptRunner([Return(answer="ok")], engine="codex")
    return AutoRouter(
        entries=[RunnerEntry(engine=runner.engine, runner=runner)],
        default_engine=runner.engine,
    )


def _plugin_map() -> dict[str, PluginDefinition]:
    return {
        "alpha": PluginDefinition(
            plugin_id="alpha", factory=_SimplePlugin, dist_name="alpha", source="test"
        ),
        "bravo": PluginDefinition(
            plugin_id="bravo", factory=_SecondPlugin, dist_name="bravo", source="test"
        ),
        "ping": PluginDefinition(
            plugin_id="ping",
            factory=_DistNamedPlugin,
            dist_name="takopi-plugin-ping",
            source="test",
        ),
        "bad": PluginDefinition(
            plugin_id="bad", factory=_BadRegisterPlugin, dist_name="bad", source="test"
        ),
        "oops": PluginDefinition(
            plugin_id="oops",
            factory=_BadPreprocessPlugin,
            dist_name="oops",
            source="test",
        ),
    }


def test_plugin_enablement_and_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "takopi.plugins.manager._discover_plugins", lambda: _plugin_map()
    )
    config = {"plugins": {"enabled": ["bravo", "alpha"]}}
    manager = load_plugins(
        config=config,
        config_path=Path("takopi.toml"),
        router=_make_router(),
        default_enabled=(),
    )
    assert manager.plugin_ids() == ("bravo", "alpha")


def test_plugin_disablement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "takopi.plugins.manager._discover_plugins", lambda: _plugin_map()
    )
    config = {"plugins": {"enabled": ["alpha", "bravo"], "disabled": ["bravo"]}}
    manager = load_plugins(
        config=config,
        config_path=Path("takopi.toml"),
        router=_make_router(),
        default_enabled=(),
    )
    assert manager.plugin_ids() == ("alpha",)


def test_plugin_pypi_and_github_specs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "takopi.plugins.manager._discover_plugins", lambda: _plugin_map()
    )
    config = {"plugins": {"enabled": ["pypi:alpha", "gh:org/bravo@main"]}}
    manager = load_plugins(
        config=config,
        config_path=Path("takopi.toml"),
        router=_make_router(),
        default_enabled=(),
    )
    assert manager.plugin_ids() == ("alpha", "bravo")


def test_plugin_bare_dist_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "takopi.plugins.manager._discover_plugins", lambda: _plugin_map()
    )
    config = {"plugins": {"enabled": ["takopi-plugin-ping"]}}
    manager = load_plugins(
        config=config,
        config_path=Path("takopi.toml"),
        router=_make_router(),
        default_enabled=(),
    )
    assert manager.plugin_ids() == ("ping",)


def test_plugin_register_failure_does_not_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "takopi.plugins.manager._discover_plugins", lambda: _plugin_map()
    )
    config = {"plugins": {"enabled": ["bad", "alpha"]}}
    manager = load_plugins(
        config=config,
        config_path=Path("takopi.toml"),
        router=_make_router(),
        default_enabled=(),
    )
    assert manager.plugin_ids() == ("alpha",)


def test_preprocessor_failure_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "takopi.plugins.manager._discover_plugins", lambda: _plugin_map()
    )
    config = {"plugins": {"enabled": ["oops"]}}
    manager = load_plugins(
        config=config,
        config_path=Path("takopi.toml"),
        router=_make_router(),
        default_enabled=(),
    )

    async def run() -> tuple[str, str | None]:
        return await manager.preprocess_message(
            text="hello",
            engine_override=None,
            reply_text=None,
            meta={},
        )

    result = anyio.run(run)
    assert result == ("hello", None)

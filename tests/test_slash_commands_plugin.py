from pathlib import Path

import anyio

from takopi.model import EngineId
from takopi.plugins.api import MessagePreprocessContext, PluginContext, PluginRegistry
from takopi.plugins.slash_commands import SlashCommandsPlugin
from takopi.router import AutoRouter, RunnerEntry
from takopi.runners.mock import Return, ScriptRunner


def _make_context(tmp_path: Path) -> PluginContext:
    runner = ScriptRunner([Return(answer="ok")], engine=EngineId("codex"))
    router = AutoRouter(
        entries=[RunnerEntry(engine=runner.engine, runner=runner)],
        default_engine=runner.engine,
    )
    return PluginContext(
        config={},
        config_path=tmp_path / "takopi.toml",
        router=router,
        plugin_id="slash_commands",
        plugin_config={"command_dirs": [str(tmp_path)]},
    )


def _register_plugin(tmp_path: Path) -> tuple[SlashCommandsPlugin, list, list]:
    plugin = SlashCommandsPlugin()
    message_preprocessors: list = []
    command_providers: list = []
    registry = PluginRegistry(
        plugin_id=plugin.id,
        message_preprocessors=message_preprocessors,
        telegram_command_providers=command_providers,
    )
    plugin.register(registry, _make_context(tmp_path))
    return plugin, message_preprocessors, command_providers


def test_slash_commands_plugin_registers_commands(tmp_path: Path) -> None:
    (tmp_path / "alpha.md").write_text("# Alpha\nAlpha prompt")
    (tmp_path / "beta.md").write_text("# Beta\nBeta prompt")

    _, _, command_providers = _register_plugin(tmp_path)
    assert command_providers
    commands = list(command_providers[0][1]())

    assert [cmd.command for cmd in commands] == ["alpha", "beta"]
    assert commands[0].description == "Alpha"


def test_slash_commands_plugin_rewrites_text(tmp_path: Path) -> None:
    (tmp_path / "review.md").write_text("# Review\nReview this.")

    _, message_preprocessors, _ = _register_plugin(tmp_path)
    preprocessor = message_preprocessors[0][1]

    async def run() -> tuple[str, EngineId | None]:
        ctx = MessagePreprocessContext(
            text="/review the code",
            engine_override=None,
            reply_text=None,
            meta={},
        )
        return await preprocessor(ctx)

    result = anyio.run(run)
    assert result[0] == "Review this.\n\nthe code"


def test_slash_commands_plugin_runner_override(tmp_path: Path) -> None:
    (tmp_path / "review.md").write_text(
        "---\nrunner: claude\n---\n# Review\nReview this."
    )

    _, message_preprocessors, _ = _register_plugin(tmp_path)
    preprocessor = message_preprocessors[0][1]

    async def run() -> tuple[str, EngineId | None]:
        ctx = MessagePreprocessContext(
            text="/review the code",
            engine_override=None,
            reply_text=None,
            meta={},
        )
        return await preprocessor(ctx)

    result = anyio.run(run)
    assert result[1] == "claude"

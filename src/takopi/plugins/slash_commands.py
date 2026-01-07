from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..commands import (
    CommandCatalog,
    build_command_prompt,
    load_commands_from_dirs,
    normalize_command,
    parse_command_dirs,
    strip_command,
)
from ..logging import get_logger
from ..model import EngineId
from .api import (
    MessagePreprocessContext,
    PluginContext,
    PluginRegistry,
    TakopiPlugin,
    TelegramCommand,
)

logger = get_logger(__name__)


@dataclass
class _SlashCommandsState:
    catalog: CommandCatalog


class SlashCommandsPlugin(TakopiPlugin):
    id = "slash_commands"
    api_version = 1

    def __init__(self) -> None:
        self._state = _SlashCommandsState(catalog=CommandCatalog.empty())

    def register(self, registry: PluginRegistry, ctx: PluginContext) -> None:
        catalog = self._load_catalog(ctx)
        self._state = _SlashCommandsState(catalog=catalog)

        registry.add_message_preprocessor(self._preprocess_message)
        registry.add_telegram_command_provider(self._telegram_commands)

    def _load_catalog(self, ctx: PluginContext) -> CommandCatalog:
        command_dirs = _resolve_command_dirs(ctx.config, ctx.plugin_config)
        catalog = load_commands_from_dirs(command_dirs)
        if catalog.commands:
            logger.info(
                "commands.loaded",
                count=len(catalog.commands),
                names=[command.name for command in catalog.commands],
            )
        return catalog

    async def _preprocess_message(
        self, ctx: MessagePreprocessContext
    ) -> tuple[str, EngineId | None]:
        args_text, command = strip_command(ctx.text, commands=self._state.catalog)
        if command is None:
            return ctx.text, ctx.engine_override
        text = build_command_prompt(command, args_text)
        engine_override = ctx.engine_override
        if engine_override is None and command.runner:
            engine_override = EngineId(command.runner)
        return text, engine_override

    def _telegram_commands(self) -> list[TelegramCommand]:
        commands: list[TelegramCommand] = []
        for command in self._state.catalog.commands:
            cmd = normalize_command(command.name)
            if not cmd:
                continue
            commands.append(
                TelegramCommand(
                    command=cmd,
                    description=command.description,
                    help=command.description,
                )
            )
        return commands


def _resolve_command_dirs(
    config: dict[str, Any], plugin_config: dict[str, Any]
) -> list[Path]:
    if "command_dirs" in plugin_config:
        return parse_command_dirs({"command_dirs": plugin_config.get("command_dirs")})
    return parse_command_dirs(config)

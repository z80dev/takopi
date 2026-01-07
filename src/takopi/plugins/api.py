from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..model import EngineId
from ..router import AutoRouter


@dataclass(frozen=True, slots=True)
class TelegramCommand:
    command: str
    description: str
    help: str | None = None
    sort_key: str | None = None


@dataclass(frozen=True, slots=True)
class MessagePreprocessContext:
    text: str
    engine_override: EngineId | None
    reply_text: str | None
    meta: dict[str, Any]


MessagePreprocessor = Callable[
    [MessagePreprocessContext], Awaitable[tuple[str, EngineId | None]]
]
TelegramCommandProvider = Callable[[], Iterable[TelegramCommand]]


@dataclass(frozen=True, slots=True)
class PluginContext:
    config: dict[str, Any]
    config_path: Path
    router: AutoRouter
    plugin_id: str
    plugin_config: dict[str, Any]


class PluginRegistry:
    def __init__(
        self,
        *,
        plugin_id: str,
        message_preprocessors: list[tuple[str, MessagePreprocessor]],
        telegram_command_providers: list[tuple[str, TelegramCommandProvider]],
    ) -> None:
        self._plugin_id = plugin_id
        self._message_preprocessors = message_preprocessors
        self._telegram_command_providers = telegram_command_providers

    def add_message_preprocessor(self, fn: MessagePreprocessor) -> None:
        self._message_preprocessors.append((self._plugin_id, fn))

    def add_telegram_command_provider(self, fn: TelegramCommandProvider) -> None:
        self._telegram_command_providers.append((self._plugin_id, fn))


class TakopiPlugin(Protocol):
    id: str
    api_version: int

    def register(self, registry: PluginRegistry, ctx: PluginContext) -> None: ...

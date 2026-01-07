from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Callable

from ..logging import get_logger
from ..router import AutoRouter
from .api import (
    MessagePreprocessContext,
    MessagePreprocessor,
    PluginContext,
    PluginRegistry,
    TakopiPlugin,
    TelegramCommand,
    TelegramCommandProvider,
)

logger = get_logger(__name__)

DEFAULT_ENABLED_PLUGINS = ("slash_commands",)


@dataclass(frozen=True, slots=True)
class PluginSpec:
    raw: str
    kind: str
    name: str
    ref: str | None


@dataclass(frozen=True, slots=True)
class PluginDefinition:
    plugin_id: str
    factory: Callable[[], TakopiPlugin]
    dist_name: str | None
    source: str


def _parse_plugin_spec(raw: str) -> PluginSpec:
    value = raw.strip()
    lower = value.lower()
    if lower.startswith("gh:") or lower.startswith("github:"):
        _, remainder = value.split(":", 1)
        name, ref = _split_repo_ref(remainder)
        return PluginSpec(raw=value, kind="github", name=name, ref=ref)
    if lower.startswith("pypi:"):
        _, remainder = value.split(":", 1)
        return PluginSpec(raw=value, kind="pypi", name=remainder.strip(), ref=None)
    if "/" in value and not value.startswith("http"):
        name, ref = _split_repo_ref(value)
        return PluginSpec(raw=value, kind="github", name=name, ref=ref)
    return PluginSpec(raw=value, kind="id", name=value, ref=None)


def _split_repo_ref(value: str) -> tuple[str, str | None]:
    value = value.strip()
    if "@" not in value:
        return value, None
    repo, ref = value.split("@", 1)
    return repo.strip(), ref.strip() or None


def _parse_plugin_list(
    value: object, *, label: str, config_path: Path
) -> list[PluginSpec]:
    if value is None:
        return []
    items: list[str] = []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                items.append(item)
            else:
                logger.warning(
                    "plugins.invalid_entry",
                    label=label,
                    config_path=str(config_path),
                    value=repr(item),
                )
    else:
        logger.warning(
            "plugins.invalid_list",
            label=label,
            config_path=str(config_path),
            value=repr(value),
        )
        return []
    return [_parse_plugin_spec(item) for item in items if item.strip()]


def _entry_point_dist_name(ep: metadata.EntryPoint) -> str | None:
    dist = getattr(ep, "dist", None)
    if dist is None:
        return None
    name = dist.metadata.get("Name")
    return name or getattr(dist, "name", None)


def _normalize_repo_name(value: str) -> str:
    return value.strip().rstrip("/").split("/")[-1].lower()


def _match_plugin_spec(
    spec: PluginSpec, plugins: dict[str, PluginDefinition]
) -> list[str]:
    if spec.kind == "id":
        if spec.name in plugins:
            return [spec.name]
        matches = [
            plugin_id
            for plugin_id, plugin in plugins.items()
            if (plugin.dist_name or "").lower() == spec.name.lower()
        ]
        return sorted(matches)
    matches: list[str] = []
    if spec.kind in {"pypi", "github"}:
        target = spec.name.lower()
        repo_target = _normalize_repo_name(spec.name) if spec.kind == "github" else None
        for plugin_id, plugin in plugins.items():
            dist_name = (plugin.dist_name or "").lower()
            if dist_name and dist_name == target:
                matches.append(plugin_id)
                continue
            if repo_target and dist_name == repo_target:
                matches.append(plugin_id)
        return sorted(matches)
    return []


def _install_hint(spec: PluginSpec) -> str | None:
    if spec.kind == "github":
        suffix = f"@{spec.ref}" if spec.ref else ""
        return f"pip install 'git+https://github.com/{spec.name}.git{suffix}'"
    if spec.kind in {"pypi", "id"}:
        if spec.name:
            return f"pip install {spec.name}"
    return None


def _discover_plugins() -> dict[str, PluginDefinition]:
    plugins: dict[str, PluginDefinition] = {}

    def register(defn: PluginDefinition) -> None:
        if defn.plugin_id in plugins:
            logger.warning(
                "plugins.duplicate",
                plugin_id=defn.plugin_id,
                source=defn.source,
            )
            return
        plugins[defn.plugin_id] = defn

    from .slash_commands import SlashCommandsPlugin

    register(
        PluginDefinition(
            plugin_id=SlashCommandsPlugin.id,
            factory=SlashCommandsPlugin,
            dist_name=None,
            source="builtin",
        )
    )

    try:
        entry_points = metadata.entry_points().select(group="takopi.plugins")
    except Exception as exc:
        logger.warning(
            "plugins.entry_points_failed",
            error=str(exc),
            error_type=exc.__class__.__name__,
        )
        return plugins

    for ep in entry_points:
        try:
            loaded = ep.load()
        except Exception as exc:
            logger.warning(
                "plugins.load_failed",
                entry_point=ep.name,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            continue
        plugin = _coerce_plugin(loaded, ep.name)
        if plugin is None:
            logger.warning(
                "plugins.invalid",
                entry_point=ep.name,
                value=repr(loaded),
            )
            continue
        register(
            PluginDefinition(
                plugin_id=plugin.id,
                factory=lambda plugin=plugin: plugin,
                dist_name=_entry_point_dist_name(ep),
                source="entry_point",
            )
        )
    return plugins


def _coerce_plugin(obj: object, name: str) -> TakopiPlugin | None:
    plugin: TakopiPlugin | None
    if hasattr(obj, "register") and hasattr(obj, "id") and hasattr(obj, "api_version"):
        if isinstance(obj, type):
            try:
                plugin = obj()
            except Exception as exc:
                logger.warning(
                    "plugins.init_failed",
                    entry_point=name,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                return None
        else:
            plugin = obj  # type: ignore[assignment]
        return plugin
    if callable(obj):
        try:
            plugin = obj()  # type: ignore[call-arg]
        except Exception as exc:
            logger.warning(
                "plugins.factory_failed",
                entry_point=name,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            return None
        if (
            hasattr(plugin, "register")
            and hasattr(plugin, "id")
            and hasattr(plugin, "api_version")
        ):
            return plugin
    return None


def load_plugins(
    *,
    config: dict[str, Any],
    config_path: Path,
    router: AutoRouter,
    default_enabled: Iterable[str] = DEFAULT_ENABLED_PLUGINS,
) -> PluginManager:
    plugins_cfg = config.get("plugins") or {}
    if plugins_cfg is None:
        plugins_cfg = {}
    if not isinstance(plugins_cfg, dict):
        logger.warning(
            "plugins.invalid_config",
            config_path=str(config_path),
            value=repr(plugins_cfg),
        )
        plugins_cfg = {}

    enabled_specs = _parse_plugin_list(
        plugins_cfg.get("enabled"), label="enabled", config_path=config_path
    )
    disabled_specs = _parse_plugin_list(
        plugins_cfg.get("disabled"), label="disabled", config_path=config_path
    )

    available = _discover_plugins()
    disabled_ids: set[str] = set()
    for spec in disabled_specs:
        disabled_ids.update(_match_plugin_spec(spec, available))

    ordered_ids: list[str] = []

    def add_plugin(plugin_id: str) -> None:
        if plugin_id in ordered_ids or plugin_id in disabled_ids:
            return
        ordered_ids.append(plugin_id)

    for spec in enabled_specs:
        matches = _match_plugin_spec(spec, available)
        if not matches:
            hint = _install_hint(spec)
            logger.warning(
                "plugins.missing",
                plugin=spec.raw,
                hint=hint,
            )
        for plugin_id in matches:
            add_plugin(plugin_id)

    for plugin_id in default_enabled:
        add_plugin(plugin_id)

    return PluginManager.from_ids(
        plugin_ids=ordered_ids,
        plugins=available,
        config=config,
        config_path=config_path,
        router=router,
    )


@dataclass(frozen=True, slots=True)
class _LoadedPlugin:
    plugin_id: str
    plugin: TakopiPlugin


class PluginManager:
    def __init__(
        self,
        *,
        plugins: list[_LoadedPlugin],
        message_preprocessors: list[tuple[str, MessagePreprocessor]],
        telegram_command_providers: list[tuple[str, TelegramCommandProvider]],
    ) -> None:
        self._plugins = plugins
        self._message_preprocessors = message_preprocessors
        self._telegram_command_providers = telegram_command_providers

    @classmethod
    def empty(cls) -> PluginManager:
        return cls(plugins=[], message_preprocessors=[], telegram_command_providers=[])

    @classmethod
    def from_ids(
        cls,
        *,
        plugin_ids: Iterable[str],
        plugins: dict[str, PluginDefinition],
        config: dict[str, Any],
        config_path: Path,
        router: AutoRouter,
    ) -> PluginManager:
        loaded: list[_LoadedPlugin] = []
        message_preprocessors: list[tuple[str, MessagePreprocessor]] = []
        telegram_command_providers: list[tuple[str, TelegramCommandProvider]] = []
        for plugin_id in plugin_ids:
            plugin_def = plugins.get(plugin_id)
            if plugin_def is None:
                logger.warning("plugins.unavailable", plugin_id=plugin_id)
                continue
            try:
                plugin = plugin_def.factory()
            except Exception as exc:
                logger.warning(
                    "plugins.init_failed",
                    plugin_id=plugin_id,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                continue
            plugin_cfg = {}
            plugins_table = config.get("plugins")
            if isinstance(plugins_table, dict):
                value = plugins_table.get(plugin_id)
                if value is None:
                    plugin_cfg = {}
                elif isinstance(value, dict):
                    plugin_cfg = value
                else:
                    logger.warning(
                        "plugins.invalid_plugin_config",
                        plugin_id=plugin_id,
                        config_path=str(config_path),
                        value=repr(value),
                    )
            registry = PluginRegistry(
                plugin_id=plugin_id,
                message_preprocessors=message_preprocessors,
                telegram_command_providers=telegram_command_providers,
            )
            ctx = PluginContext(
                config=config,
                config_path=config_path,
                router=router,
                plugin_id=plugin_id,
                plugin_config=plugin_cfg,
            )
            try:
                plugin.register(registry, ctx)
            except Exception as exc:
                logger.warning(
                    "plugins.register_failed",
                    plugin_id=plugin_id,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                continue
            loaded.append(_LoadedPlugin(plugin_id=plugin_id, plugin=plugin))
        return cls(
            plugins=loaded,
            message_preprocessors=message_preprocessors,
            telegram_command_providers=telegram_command_providers,
        )

    def plugin_ids(self) -> tuple[str, ...]:
        return tuple(plugin.plugin_id for plugin in self._plugins)

    async def preprocess_message(
        self,
        *,
        text: str,
        engine_override: str | None,
        reply_text: str | None,
        meta: dict[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        current_text = text
        current_engine = engine_override
        meta = meta or {}
        for plugin_id, preprocessor in self._message_preprocessors:
            ctx = MessagePreprocessContext(
                text=current_text,
                engine_override=current_engine,
                reply_text=reply_text,
                meta=meta,
            )
            try:
                result = await preprocessor(ctx)
            except Exception as exc:
                logger.warning(
                    "plugins.preprocess_failed",
                    plugin_id=plugin_id,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                continue
            if not isinstance(result, tuple) or len(result) != 2:
                logger.warning(
                    "plugins.preprocess_invalid",
                    plugin_id=plugin_id,
                    value=repr(result),
                )
                continue
            current_text, current_engine = result
        return current_text, current_engine

    def iter_telegram_commands(self) -> Iterable[tuple[str, TelegramCommand]]:
        for plugin_id, provider in self._telegram_command_providers:
            try:
                commands = provider()
            except Exception as exc:
                logger.warning(
                    "plugins.commands_failed",
                    plugin_id=plugin_id,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                continue
            if not commands:
                continue
            for command in commands:
                yield plugin_id, command

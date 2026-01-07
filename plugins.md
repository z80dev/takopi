Below is a PR-by-PR plan that keeps `main` green at every step, preserves existing behavior until the migration PR, and ends with:

* **Feature plugins** discovered via Python entry points (`takopi.plugins`)
* Plugins can **register Telegram commands** that show up:

  * in Telegram’s `/` command picker (via `setMyCommands`)
  * in a new **`/help`** command response
* **Slash commands** moved out of `telegram/bridge.py` into an **external plugin**
* **Runners/backends** discoverable as plugins via entry points (`takopi.backends`)

I’m basing this on the current repo layout (notably `src/takopi/telegram/bridge.py`, `src/takopi/commands.py`, `src/takopi/engines.py`, `src/takopi/cli.py`, and existing tests in `tests/test_telegram_bridge.py`, `tests/test_engine_discovery.py`).

---

## PR 1 — Add plugin core (API + manager + config semantics) with no integration

### Goals

* Introduce a small, stable plugin surface area without changing runtime behavior.
* Define how plugins are discovered, enabled/disabled, and how they register hooks.

### Changes

**New package**

* `src/takopi/plugins/__init__.py`
* `src/takopi/plugins/api.py`
* `src/takopi/plugins/manager.py`

**Plugin API (v1)**

* `TakopiPlugin` protocol: `id`, `api_version`, `register(registry, ctx)`
* `PluginContext`: includes `config`, `config_path`, and access to `router` (for plugins that need engine info)
* `PluginRegistry` methods (start minimal):

  * `add_message_preprocessor(fn, priority=...)`
  * `add_telegram_command_provider(fn, priority=...)`

**Telegram command model**
Create a single command type that can serve both:

* Telegram command menu (`setMyCommands`)
* `/help` rendering

Example (in `plugins/api.py`):

```py
@dataclass(frozen=True, slots=True)
class TelegramCommand:
    command: str            # no leading "/"
    description: str        # short; trimmed for Telegram menu
    help: str | None = None # optional longer text for /help
    sort_key: str | None = None
```

**Config semantics (just parsing + docs in this PR)**

* `[plugins] enabled = [...]` allowlist (auto-install on startup by default)
* `[plugins] disabled = [...]` denylist
* `[plugins] auto_install = true|false` controls auto-install into `~/.takopi/plugins/venv`
* `[plugins.<plugin_id>] ...` namespaced config table

No behavioral impact yet.

### Tests

Add `tests/test_plugins_manager.py` covering:

* enabling/disabling by config
* priority ordering
* robust handling of plugin exceptions (don’t crash core)

### Acceptance criteria

* All existing tests pass.
* New plugin tests pass.
* No production code uses plugins yet.

---

## PR 2 — Telegram command aggregation layer + `/help` command (still using existing slash command core)

### Goals

* Centralize “what commands exist” into one function.
* Add `/help` support in the Telegram bridge.
* Ensure `/help` includes *all* registered commands (for now: engines + cancel + existing `CommandCatalog`).

### Changes

**In `src/takopi/telegram/bridge.py`**

* Introduce a single internal aggregator that returns a **normalized** list of `TelegramCommand` (or dicts) from:

  1. router engines (`cfg.router.available_entries`)
  2. core commands: `cancel`, `help`
  3. existing custom slash commands from `cfg.commands` (current behavior)

Example shape:

```py
def _collect_telegram_commands(cfg: TelegramBridgeConfig) -> list[TelegramCommand]:
    ...
```

* Update `_set_command_menu` to use `_collect_telegram_commands()` and map them to Telegram’s `{command, description}` dict list.

**Add `/help` handling**

* Add `_is_help_command(text)` similar to `_is_cancel_command`.
* Add `_handle_help(cfg, msg)` that replies with a help message listing commands + descriptions.

Hook it into the main loop *before* engine stripping and runner execution:

```py
if _is_help_command(text):
    tg.start_soon(_handle_help, cfg, msg)
    continue
```

**Add `/help` to command menu**
So it appears in the `/` picker.

### Tests

Extend `tests/test_telegram_bridge.py`:

* Verify command menu includes `"help"` and `"cancel"` and engine commands.
* Add a new async test that runs `run_main_loop` with a poller yielding a `/help` message and asserts:

  * the bot replies
  * reply contains entries for `/help`, `/cancel`, and at least one engine command
  * reply contains custom commands from `cfg.commands` (existing slash command catalog)

### Acceptance criteria

* Telegram now supports `/help`.
* `/help` output includes the same custom slash commands that currently appear in `setMyCommands`.

---

## PR 3 — Wire plugin manager into Telegram bridge for command menu + `/help` (still not migrating slash command execution)

### Goals

* Plugins can contribute Telegram commands that appear:

  * in the `/` picker
  * in `/help`
* No changes yet to slash command execution (still the old `_strip_command` path).

### Changes

**Config object**

* Extend `TelegramBridgeConfig` to include a plugin manager:

```py
@dataclass(frozen=True)
class TelegramBridgeConfig:
    ...
    plugins: PluginManager = field(default_factory=PluginManager.empty)
```

**CLI startup**
In `src/takopi/cli.py::_parse_bridge_config`, instantiate the plugin manager from config:

```py
plugins = load_plugins(config=config, config_path=config_path, router=router)
...
return TelegramBridgeConfig(..., plugins=plugins, commands=commands)
```

**Command aggregation**
Update `_collect_telegram_commands(cfg)` to include plugin contributions:

* `cfg.plugins.telegram_commands()` returns `list[TelegramCommand]`
* merge + dedupe by `command` with precedence rules:

  1. core (`help`, `cancel`)
  2. engine commands (router)
  3. plugin commands
  4. legacy `cfg.commands` commands (until PR 4 removes it) or flip (your choice) — I recommend plugin before legacy, because PR 4 migrates legacy into a plugin.

**Dedupe policy**

* If a plugin tries to register `codex`, `cancel`, or `help`, skip + log warning.
* If two plugins collide, keep the earlier one by `(priority, plugin_id)` and skip later.

### Tests

* Add a fake plugin (in tests) that contributes `TelegramCommand("ping", "ping takopi")`
* Assert:

  * `set_my_commands` includes `"ping"`
  * `/help` includes `/ping`

### Acceptance criteria

* A plugin can add commands that show up in Telegram UI and in `/help`.
* Existing behavior unchanged for slash command execution.

---

## PR 4 — Migrate slash command support into an external plugin (removes slash command logic from Telegram core)

This is the “real” migration PR that turns your example (“slash commands as plugin”) into reality.

### Goals

* Move custom slash command loading + parsing + prompt rewrite out of `telegram/bridge.py`.
* Keep feature parity:

  * Markdown commands loaded from configured directories (`command_dirs`)
  * Commands appear in Telegram `/` picker and in `/help`
  * Runner override via frontmatter `runner:` still works

### Changes

**New external plugin repo**

* `takopi-slash-commands/src/takopi_slash_commands/plugin.py`

It uses existing `src/takopi/commands.py` utilities:

* `parse_command_dirs`
* `load_commands_from_dirs`
* `normalize_command`
* `build_command_prompt`

Plugin registers two things:

1. `add_message_preprocessor(...)` that implements current `_strip_command` + rewrite logic.
2. `add_telegram_command_provider(...)` that returns a `TelegramCommand` per loaded command file.

**Enable by default**
To preserve existing behavior even if users don’t add `[plugins]` to config:

* Ensure docs/config include `slash_commands` in the enabled list.
* Third-party plugins still require explicit enablement.

**Telegram bridge main loop**
Replace:

* the inline “Check for custom slash commands” block that calls `_strip_command(...)`
  with:
* a call into plugin manager preprocess pipeline:

```py
text, engine_override = await cfg.plugins.preprocess_message(
    text=text,
    engine_override=engine_override,
    reply_text=(msg.get("reply_to_message") or {}).get("text"),
    meta={"telegram_message": msg},
)
```

**Remove legacy command catalog from config**

* Remove `commands: CommandCatalog` from `TelegramBridgeConfig`
* Remove loading in `cli._parse_bridge_config`:

  * delete `command_dirs = parse_command_dirs(config)`
  * delete `commands = load_commands_from_dirs(...)`
* Plugin will load commands itself and log `commands.loaded` like CLI currently does.

**Config compatibility**

* Keep supporting existing top-level `command_dirs = [...]` (so old configs work)
* Add preferred namespaced config:

```toml
[plugins.slash_commands]
command_dirs = ["~/.takopi/commands", "~/.claude/commands"]
```

### Tests

Update `tests/test_telegram_bridge.py`:

* Tests that directly import `_strip_command` will need to move to plugin tests, OR you keep `_strip_command` as a helper in `takopi.commands` and test it there.
* Update command menu tests:

  * instead of passing `commands=catalog` into `_build_bot_commands`, you now assert that plugin-contributed commands appear when plugin manager is loaded with a catalog.

Add `takopi-slash-commands/tests/test_slash_commands_plugin.py`:

* Given temp dirs with `*.md` commands:

  * plugin provides `TelegramCommand`s sorted
  * preprocessor rewrites `/review args` correctly
  * runner override sets `engine_override`

### Acceptance criteria

* `telegram/bridge.py` no longer knows about markdown slash commands at all.
* Slash commands still show up in Telegram’s `/` picker and in `/help`.
* Slash commands still execute exactly as before (prompt rewrite + optional runner override).

---

## PR 5 — Make runners/backends pluggable via entry points (`takopi.backends`)

### Goals

* Third parties can ship a runner backend as an installable package.
* Takopi discovers installed backends without modifying `takopi.runners`.
* Built-in backends still work (backwards compatible).

### Changes

**Backend discovery update**
In `src/takopi/engines.py`, change `_discover_backends()` to merge:

1. Entry points group: `takopi.backends`
2. Existing module scan of `takopi.runners` as fallback

Pseudo-implementation:

```py
from importlib import metadata

def _discover_backends() -> dict[str, EngineBackend]:
    backends: dict[str, EngineBackend] = {}

    for ep in metadata.entry_points().select(group="takopi.backends"):
        obj = ep.load()
        backend = obj() if callable(obj) and not isinstance(obj, EngineBackend) else obj
        if not isinstance(backend, EngineBackend):
            continue
        backends[backend.id] = backend

    # fallback to current takopi.runners scan (existing behavior)
    backends |= _discover_builtin_runner_modules()
    return backends
```

**Fix PATH checking for non-CLI backends**
Update `_build_router` in `cli.py` to avoid warning on pure-Python backends:

* Only run `shutil.which(...)` if `backend.cli_cmd is not None` **or** `backend.install_cmd is not None`

This lets plugin backends omit CLI fields entirely without being treated as “not installed”.

### Tests

Add/extend `tests/test_engine_discovery.py`:

* Monkeypatch `importlib.metadata.entry_points()` to return a fake backend entry point.
* Assert `engines.list_backend_ids()` contains it.
* Assert CLI registers a Typer command for it (since `register_engine_commands()` uses `list_backends()`).

Add unit test for PATH-check behavior:

* Create an `EngineBackend(id="pyonly", build_runner=..., cli_cmd=None, install_cmd=None)`
* Ensure `_build_router` doesn’t mark it unavailable just because there’s no CLI on PATH.

### Docs

Update `docs/adding-a-runner.md` with a “runner plugin” section:

* Provide `pyproject.toml` entry point example:

```toml
[project.entry-points."takopi.backends"]
myengine = "takopi_backend_myengine:BACKEND"
```

### Acceptance criteria

* Installing a package that exposes `takopi.backends` adds a new engine id that:

  * appears in CLI (`takopi myengine`)
  * appears in Telegram command menu as `/myengine` (because router sees it)
  * works with existing config conventions (`[myengine] ...`)

---

## PR 6 — Docs + examples + ergonomics (plugin author experience)

### Goals

* Make it *obvious* how to build and share plugins.
* Provide a small “hello plugin” example for feature plugins and backend plugins.

### Changes

**Docs**

* `docs/plugins.md`:

  * plugin structure
  * config (`[plugins] enabled/disabled`, `[plugins.<id>]`)
  * entry points (`takopi.plugins`)
  * command registration semantics (menu + `/help`)
  * command collision rules

* Update README to mention:

  * plugin support
  * runner/backends plugins

**Example packages (in docs or `examples/`)**

* Feature plugin example: adds `/ping` command (shows in menu + /help) and rewrites `/ping` into a prompt (“Respond with pong”).
* Backend plugin example: adds `myengine` `EngineBackend` that runs a mock runner.

### Acceptance criteria

* A new user can copy-paste an example `pyproject.toml` and publish a plugin to PyPI with minimal friction.

---

## A couple of “don’t regret later” implementation details (worth baking into PRs 1–4)

### 1) Keep plugin API transport-light

Even though these are “Telegram commands”, keep the plugin API as generic as possible:

* plugin registers `TelegramCommand` metadata (name/desc/help)
* plugin preprocesses message text/engine override
* the Telegram bridge remains responsible for:

  * calling `setMyCommands`
  * rendering `/help`
  * deciding when to invoke preprocessors

That keeps plugins portable if you add a Slack/Discord transport later.

### 2) One source of truth for command lists

Make `/help` and `setMyCommands` use the **same aggregator** so they never drift.

### 3) Explicit enablement for third-party plugins

Default enablement only for explicitly configured plugins:

* installed ≠ enabled
* avoids “dependency installs execute code” surprises

---

If you want, I can also outline the *exact* function signatures and the dedupe/sort logic for the command aggregator (including how to keep the existing `tests/test_telegram_bridge.py` expectations mostly intact while you transition).

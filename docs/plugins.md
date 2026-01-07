# Plugins

Takopi supports two plugin types:

- **Feature plugins** (Telegram command providers, message preprocessors)
- **Backend plugins** (engine runners)

Plugins are discovered via Python entry points and must be installed in the same
environment as Takopi.

---

## Feature plugins

### Entry point

Expose a plugin in `pyproject.toml`:

```toml
[project.entry-points."takopi.plugins"]
myplugin = "takopi_plugin_myplugin:PLUGIN"
```

`PLUGIN` should be an object that implements:

- `id: str`
- `api_version: int` (currently `1`)
- `register(registry, ctx)` method

### API surface (v1)

Plugins can:

- register message preprocessors (rewrite text, set engine override)
- register Telegram commands (for `/` menu and `/help`)

Takopi keeps the transport logic in core. Plugins only provide metadata and text
rewrites, so they can remain portable to future transports.

### Config

Feature plugins are enabled explicitly and ordered in config:

```toml
[plugins]
enabled = [
  "gh:z80dev/takopi-slash-commands@main",
  "pypi:takopi-plugin-ping",
  "gh:acme/takopi-plugin-foo@v1.2.0",
]
disabled = ["experimental-plugin"]
auto_install = true

[plugins.slash_commands]
command_dirs = ["~/.takopi/commands", "~/.claude/commands"]

[plugins.ping]
response = "pong"
```

Notes:

- **Ordering matters**: the `enabled` list defines plugin order.
- Takopi auto-installs enabled plugins into `~/.takopi/plugins/venv` on startup.
- Set `[plugins].auto_install = false` to disable auto-install.
- `enabled` entries may be:
  - plugin ids (entry point names)
  - PyPI distribution names (`pypi:...` or bare names)
  - GitHub shorthand (`gh:owner/repo@ref` or `owner/repo@ref`)
- GitHub shorthand accepts branch, tag, or commit in `@ref`.

### Command semantics

Commands contributed by plugins:

- appear in Telegram's `/` command menu
- appear in `/help`

Collisions:

- `help` and `cancel` are reserved (plugin registrations are skipped)
- when multiple plugins register the same command, the **earlier** plugin wins

---

## Slash command plugin (external)

`slash_commands` is an external feature plugin that loads markdown commands from
directories and rewrites `/command args` into prompts. Install it from GitHub:

```bash
pip install 'git+https://github.com/z80dev/takopi-slash-commands.git@main'
```

Config (new, preferred):

```toml
[plugins.slash_commands]
command_dirs = ["~/.takopi/commands", "~/.claude/commands"]
```

Legacy config still works:

```toml
command_dirs = ["~/.takopi/commands"]
```

---

## Backend plugins (runners)

Backend plugins expose a runner via entry points:

```toml
[project.entry-points."takopi.backends"]
myengine = "takopi_backend_myengine:BACKEND"
```

`BACKEND` should be an `EngineBackend` instance (or a factory returning one).

Once installed, the engine id:

- appears as a CLI command (`takopi myengine`)
- appears as a Telegram command (`/myengine`)
- reads config from `[myengine]` in `takopi.toml`

---

## Example feature plugin

```py
# takopi_plugin_ping.py
from takopi.plugins.api import TakopiPlugin, PluginRegistry, PluginContext, TelegramCommand

class PingPlugin:
    id = "ping"
    api_version = 1

    def register(self, registry: PluginRegistry, ctx: PluginContext) -> None:
        registry.add_telegram_command_provider(
            lambda: [TelegramCommand(command="ping", description="reply with pong")]
        )
        async def preprocess(message):
            if message.text.strip() == "/ping":
                return "pong", message.engine_override
            return message.text, message.engine_override
        registry.add_message_preprocessor(preprocess)

PLUGIN = PingPlugin()
```

---

## Example backend plugin

```py
# takopi_backend_myengine.py
from takopi.backends import EngineBackend
from takopi.runners.mock import ScriptRunner, Return

BACKEND = EngineBackend(
    id="myengine",
    build_runner=lambda _cfg, _path: ScriptRunner([Return(answer="ok")], engine="myengine"),
)
```

# takopi

🐙 *he just wants to help-pi*

telegram bridge for codex, claude code, opencode, pi, and [other agents](docs/adding-a-runner.md). runs the agent cli, streams progress, and supports resumable sessions.

## features

stateless resume, continue a thread in the chat or pick up in the terminal.

progress updates while agent runs (commands, tools, notes, file changes, elapsed time).

robust markdown rendering of output with a lot of quality of life tweaks.

parallel runs across threads, per thread queue support.

`/cancel` a running task.

`/help` shows available commands (engines + plugins).

plugin system for feature commands and runner backends.

## requirements

- `uv` for installation (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- python 3.14+ (uv can install it: `uv python install 3.14`)
- at least one engine installed:
  - `codex` on PATH (`npm install -g @openai/codex` or `brew install codex`)
  - `claude` on PATH (`npm install -g @anthropic-ai/claude-code`)
  - `opencode` on PATH (`npm install -g opencode-ai@latest`)
  - `pi` on PATH (`npm install -g @mariozechner/pi-coding-agent`)

## install

- `uv python install 3.14`
- `uv tool install -U takopi` to install as `takopi`
- or try it with `uvx takopi@latest`

## setup

run `takopi` and follow the interactive prompts. it will:

- help you create a bot token (via @BotFather)
- capture your `chat_id` from the most recent message you send to the bot
- check installed agents and set a default engine

to re-run onboarding (and overwrite config), use `takopi --onboard`.

run your agent cli once interactively in the repo to trust the directory.

## config

global config `~/.takopi/takopi.toml`

```toml
default_engine = "codex"

bot_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
chat_id = 123456789
# optional: import env vars from a shell command (use `env -0` for robust parsing)
shell_env = ["zsh", "-c", "source ~/.zshrc; env -0"]

[codex]
# optional: profile from ~/.codex/config.toml
profile = "takopi"
# optional: disable sandbox + approvals (high risk)
unrestricted = true

[claude]
model = "sonnet"
# optional: override the CLI command used to invoke claude
command = "yolo"
# optional: defaults to ["Bash", "Read", "Edit", "Write"]
allowed_tools = ["Bash", "Read", "Edit", "Write", "WebSearch"]
dangerously_skip_permissions = false
# uses subscription by default, override to use api billing
use_api_billing = false

[opencode]
model = "claude-sonnet-4-20250514"

[pi]
model = "gpt-4.1"
provider = "openai"
# optional: additional CLI arguments
extra_args = ["--no-color"]

[plugins]
enabled = ["gh:z80dev/takopi-slash-commands@main", "pypi:takopi-plugin-ping"]
auto_install = true

[plugins.slash_commands]
command_dirs = ["~/.takopi/commands", "~/.claude/commands"]
```

See [`docs/plugins.md`](docs/plugins.md) for plugin authoring and config details.

## usage

start takopi in the repo you want to work on:

```sh
cd ~/dev/your-repo
takopi
# or override the default engine for new threads:
takopi claude
takopi opencode
takopi pi
```

resume lines always route to the matching engine; subcommands only override the default for new threads.

send a message to the bot.

start a new thread with a specific engine by prefixing your message with `/codex`, `/claude`, `/opencode`, or `/pi`.

change the default engine for new threads with `/default <engine>`, or run `/default` to see the current one.

to continue a thread, reply to a bot message containing a resume line.
you can also copy it to resume an interactive session in your terminal.

to stop a run, reply to the progress message with `/cancel`.

default: progress is silent, final answer is sent as a new message so you receive a notification, progress message is deleted.

if you prefer no notifications, `--no-final-notify` edits the progress message into the final answer.

## notes

* the bot only responds to the configured `chat_id` (private or group)
* run only one takopi instance per bot token: multiple instances will race telegram's `getUpdates` offsets and cause missed updates

## development

see [`docs/specification.md`](docs/specification.md) and [`docs/developing.md`](docs/developing.md).

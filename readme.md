# takopi

🐙 *he just wants to help-pi*

telegram bot for [codex](https://github.com/openai/codex). runs `codex exec --json`, streams progress, and supports resumable sessions.

## features

stateless resume via `codex resume <token>` lines in chat.

edits a single progress message while codex runs (commands, tools, notes, file changes, elapsed time).

renders markdown to telegram entities.

runs in parallel across threads and queues per thread to keep codex history sane.

## requirements

- `uv` for installation (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- `codex` on PATH (`npm install -g @openai/codex` or `brew install codex`)

## install

- `uv tool install takopi` to install as `takopi`
- or try it with `uvx takopi`

## setup

1. get `bot_token` from [@BotFather](https://t.me/BotFather)
2. get `chat_id` from [@myidbot](https://t.me/myidbot)
3. send `/start` to the bot (telegram won't let it message you first)
4. run `codex` once interactively in the repo to trust the directory

## config

takopi reads `.takopi/takopi.toml` in the current repo, otherwise `~/.takopi/takopi.toml`.
legacy `.codex/takopi.toml` is migrated automatically.

```toml
bot_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
chat_id = 123456789

[codex]
# optional: profile from ~/.codex/config.toml
profile = "takopi"
```

## usage

start takopi in the repo you want to work on:

```sh
cd ~/dev/your-repo
takopi
```

send a message to the bot.

to continue a thread, reply to a bot message containing a resume line.

to stop a run, reply to the progress message with `/cancel`.

## cli

default: progress is silent, final answer is sent as a new message (notification), progress message is deleted.

`--no-final-notify` edits the progress message into the final answer (no new notification).

`--debug` enables verbose logs.

## notes

* private chat only
* run exactly one instance per bot token

## development

see [`docs/specification.md`](docs/specification.md) and [`docs/developing.md`](docs/developing.md).

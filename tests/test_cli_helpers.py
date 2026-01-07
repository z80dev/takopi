from pathlib import Path

import pytest

from takopi import cli
from takopi.config import ConfigError


def test_resolve_default_engine_uses_override() -> None:
    result = cli._resolve_default_engine(
        override="codex",
        config={},
        config_path=Path("cfg"),
        engine_ids=["codex"],
    )
    assert result == "codex"


def test_resolve_default_engine_rejects_unknown() -> None:
    with pytest.raises(ConfigError):
        cli._resolve_default_engine(
            override=None,
            config={"default_engine": "nope"},
            config_path=Path("cfg"),
            engine_ids=["codex"],
        )


def test_default_engine_for_setup_reads_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "load_telegram_config",
        lambda: ({"default_engine": "codex"}, Path("cfg")),
    )
    assert cli._default_engine_for_setup(None) == "codex"


def test_config_path_display_shows_tilde(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    path = tmp_path / "takopi" / "takopi.toml"
    assert cli._config_path_display(path).startswith("~/")


def test_load_and_validate_config_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "load_telegram_config",
        lambda _path=None: ({"bot_token": "t", "chat_id": 1}, Path("cfg")),
    )
    config, cfg_path, token, chat_id = cli.load_and_validate_config()
    assert config["bot_token"] == "t"
    assert cfg_path == Path("cfg")
    assert token == "t"
    assert chat_id == 1

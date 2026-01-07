from pathlib import Path

import pytest

from takopi.config import (
    ConfigError,
    dump_toml,
    load_or_init_config,
    write_config,
    _format_toml_value,
)


def test_format_toml_value_basic_types() -> None:
    assert _format_toml_value(True) == "true"
    assert _format_toml_value(False) == "false"
    assert _format_toml_value(3) == "3"
    assert _format_toml_value(1.5) == "1.5"
    assert _format_toml_value("hi") == '"hi"'
    assert _format_toml_value(["a", 1]) == '["a", 1]'


def test_format_toml_value_rejects_unknown() -> None:
    with pytest.raises(ConfigError):
        _format_toml_value({"bad": True})


def test_dump_toml_writes_nested_tables() -> None:
    config = {
        "default_engine": "codex",
        "projects": {
            "alpha": {"path": "~/dev/alpha", "default_engine": "codex"},
            "beta": {"path": "~/dev/beta"},
        },
    }
    text = dump_toml(config)
    assert "default_engine = \"codex\"" in text
    assert "[projects.alpha]" in text
    assert "path = \"~/dev/alpha\"" in text
    assert "[projects.beta]" in text


def test_write_config_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "takopi.toml"
    write_config({"default_engine": "codex"}, path)
    written = path.read_text(encoding="utf-8")
    assert "default_engine = \"codex\"" in written


def test_load_or_init_config_reads_existing(tmp_path: Path) -> None:
    path = tmp_path / "takopi.toml"
    path.write_text('default_engine = "codex"\n', encoding="utf-8")
    config, loaded_path = load_or_init_config(path)
    assert loaded_path == path
    assert config["default_engine"] == "codex"


def test_load_or_init_config_rejects_directory(tmp_path: Path) -> None:
    path = tmp_path / "takopi.toml"
    path.mkdir()
    with pytest.raises(ConfigError):
        load_or_init_config(path)


def test_load_or_init_config_rejects_bad_toml(tmp_path: Path) -> None:
    path = tmp_path / "takopi.toml"
    path.write_text("=bad", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_or_init_config(path)

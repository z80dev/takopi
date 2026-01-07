import os
import subprocess
from pathlib import Path

import pytest

from takopi.config import ConfigError
from takopi.utils.shell_env import (
    _parse_env_output,
    _parse_shell_env_command,
    apply_shell_env,
)


def test_parse_shell_env_command_string() -> None:
    result = _parse_shell_env_command({"shell_env": "echo hello"}, Path("cfg"))
    assert result == ["echo", "hello"]


def test_parse_shell_env_command_list() -> None:
    result = _parse_shell_env_command({"shell_env": ["env", "-0"]}, Path("cfg"))
    assert result == ["env", "-0"]


def test_parse_shell_env_command_invalid_type() -> None:
    with pytest.raises(ConfigError):
        _parse_shell_env_command({"shell_env": 123}, Path("cfg"))


def test_parse_shell_env_command_empty_list() -> None:
    with pytest.raises(ConfigError):
        _parse_shell_env_command({"shell_env": []}, Path("cfg"))


def test_parse_env_output_null_separated() -> None:
    raw = b"FOO=bar\0BAZ=qux\0"
    parsed = _parse_env_output(raw)
    assert parsed == {"FOO": "bar", "BAZ": "qux"}


def test_parse_env_output_newline_separated() -> None:
    raw = b"FOO=bar\nBAZ=qux\n"
    parsed = _parse_env_output(raw)
    assert parsed == {"FOO": "bar", "BAZ": "qux"}


def test_apply_shell_env_updates_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(*_args, **_kwargs):
        class _Result:
            stdout = b"FOO=bar\0"

        return _Result()

    monkeypatch.delenv("TAKOPI_SHELL_ENV_LOADED", raising=False)
    monkeypatch.setattr(subprocess, "run", _fake_run)

    apply_shell_env({"shell_env": ["env", "-0"]}, Path("cfg"))

    assert "FOO" in os.environ
    assert os.environ["FOO"] == "bar"
    assert os.environ.get("TAKOPI_SHELL_ENV_LOADED") == "1"


def test_apply_shell_env_raises_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["bad"], stderr=b"boom")

    monkeypatch.delenv("TAKOPI_SHELL_ENV_LOADED", raising=False)
    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(ConfigError):
        apply_shell_env({"shell_env": ["bad"]}, Path("cfg"))

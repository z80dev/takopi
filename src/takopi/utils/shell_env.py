from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from ..config import ConfigError
from ..logging import get_logger

logger = get_logger(__name__)

_LOADED_ENV_MARKER = "TAKOPI_SHELL_ENV_LOADED"


def _parse_shell_env_command(config: dict, config_path: Path) -> list[str] | None:
    value = config.get("shell_env")
    if value is None:
        return None
    if isinstance(value, str):
        cmd = shlex.split(value)
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        cmd = list(value)
    else:
        raise ConfigError(
            f"Invalid `shell_env` in {config_path}; expected a string or list of strings."
        )
    if not cmd:
        raise ConfigError(
            f"Invalid `shell_env` in {config_path}; expected a non-empty command."
        )
    return cmd


def _parse_env_output(raw: bytes) -> dict[str, str]:
    if not raw:
        return {}
    sep = b"\0" if b"\0" in raw else b"\n"
    env: dict[str, str] = {}
    for entry in raw.split(sep):
        if not entry or b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        if not key:
            continue
        env[key.decode("utf-8", errors="replace")] = value.decode(
            "utf-8", errors="replace"
        )
    return env


def apply_shell_env(config: dict, config_path: Path) -> None:
    if os.environ.get(_LOADED_ENV_MARKER):
        return
    cmd = _parse_shell_env_command(config, config_path)
    if cmd is None:
        return
    logger.info("shell.env.load", cmd=cmd)
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        message = f"shell_env command failed: {exc}"
        if stderr:
            message = f"{message}\n{stderr}"
        raise ConfigError(message) from exc
    parsed = _parse_env_output(result.stdout)
    if not parsed:
        logger.warning("shell.env.empty", cmd=cmd)
        return
    os.environ.update(parsed)
    os.environ[_LOADED_ENV_MARKER] = "1"
    logger.info("shell.env.loaded", keys=len(parsed))

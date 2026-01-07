from __future__ import annotations

import re
import tomllib
from pathlib import Path

from ..config import ConfigError

HOME_CONFIG_PATH = Path.home() / ".takopi" / "takopi.toml"
_DEFAULT_ENGINE_RE = re.compile(r"^(\s*default_engine\s*=\s*)(.*)$")


def _read_config(cfg_path: Path) -> dict:
    try:
        raw = cfg_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"Missing config file {cfg_path}.") from None
    except OSError as e:
        raise ConfigError(f"Failed to read config file {cfg_path}: {e}") from e
    try:
        return tomllib.loads(raw)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Malformed TOML in {cfg_path}: {e}") from None


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def update_default_engine(config_path: Path, engine: str) -> None:
    try:
        raw = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"Missing config file {config_path}.") from None
    except OSError as e:
        raise ConfigError(f"Failed to read config file {config_path}: {e}") from e

    lines = raw.splitlines()
    replaced = False
    in_section = False

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = True
        if in_section:
            continue
        if not stripped or stripped.startswith("#"):
            continue
        base, comment = (line.split("#", 1) + [""])[:2]
        match = _DEFAULT_ENGINE_RE.match(base)
        if not match:
            continue
        prefix = match.group(1)
        comment_suffix = f" #{comment.strip()}" if comment else ""
        lines[idx] = f'{prefix}"{_toml_escape(engine)}"{comment_suffix}'.rstrip()
        replaced = True
        break

    if not replaced:
        insert_at = 0
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                insert_at = idx
                break
        new_line = f'default_engine = "{_toml_escape(engine)}"'
        lines.insert(insert_at, new_line)
        if insert_at + 1 < len(lines) and lines[insert_at + 1].strip():
            lines.insert(insert_at + 1, "")

    text = "\n".join(lines)
    if raw.endswith("\n"):
        text += "\n"
    try:
        config_path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Failed to write config file {config_path}: {e}") from e


def load_telegram_config(path: str | Path | None = None) -> tuple[dict, Path]:
    if path:
        cfg_path = Path(path).expanduser()
        return _read_config(cfg_path), cfg_path
    cfg_path = HOME_CONFIG_PATH
    if cfg_path.exists() and not cfg_path.is_file():
        raise ConfigError(f"Config path {cfg_path} exists but is not a file.") from None
    return _read_config(cfg_path), cfg_path

from __future__ import annotations

import shutil
import subprocess
import sys
import venv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import ConfigError
from ..logging import get_logger
from .manager import _discover_plugins, _match_plugin_spec, _parse_plugin_list

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PluginVenv:
    path: Path
    python: Path
    site_packages: Path


def _plugin_venv_root() -> Path:
    return Path.home() / ".takopi" / "plugins" / "venv"


def _venv_python(path: Path) -> Path:
    return path / "bin" / "python"


def _ensure_venv(path: Path) -> None:
    python = _venv_python(path)
    if python.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("plugins.venv.create", path=str(path))
    builder = venv.EnvBuilder(with_pip=True)
    builder.create(path)


def _site_packages_for(python: Path) -> Path:
    result = subprocess.run(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())


def _load_plugin_venv() -> PluginVenv:
    venv_root = _plugin_venv_root()
    _ensure_venv(venv_root)
    python = _venv_python(venv_root)
    if not python.exists():
        raise ConfigError(f"Plugin venv python not found at {python}")
    site_packages = _site_packages_for(python)
    return PluginVenv(path=venv_root, python=python, site_packages=site_packages)


def _ensure_sys_path(site_packages: Path) -> None:
    site_path = str(site_packages)
    if site_path in sys.path:
        return
    sys.path.append(site_path)


def _install_command(
    *,
    kind: str,
    name: str,
    ref: str | None,
    python: Path,
) -> list[str]:
    uv = "uv"
    use_uv = shutil.which(uv) is not None

    if kind == "github":
        suffix = f"@{ref}" if ref else ""
        target = f"git+https://github.com/{name}.git{suffix}"
    else:
        target = name

    if use_uv:
        return [uv, "pip", "install", "--python", str(python), target]
    return [str(python), "-m", "pip", "install", target]


def _parse_auto_install(config: dict[str, Any]) -> bool:
    plugins_cfg = config.get("plugins")
    if plugins_cfg is None:
        return True
    if not isinstance(plugins_cfg, dict):
        logger.warning("plugins.invalid_config", value=repr(plugins_cfg))
        return True
    value = plugins_cfg.get("auto_install")
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    logger.warning("plugins.invalid_auto_install", value=repr(value))
    return True


def ensure_plugins_ready(*, config: dict[str, Any], config_path: Path) -> None:
    plugins_cfg = config.get("plugins")
    if plugins_cfg is None:
        return
    if not isinstance(plugins_cfg, dict):
        logger.warning(
            "plugins.invalid_config",
            config_path=str(config_path),
            value=repr(plugins_cfg),
        )
        return
    enabled_specs = _parse_plugin_list(
        plugins_cfg.get("enabled"), label="enabled", config_path=config_path
    )
    if not enabled_specs:
        return

    venv_info = _load_plugin_venv()
    _ensure_sys_path(venv_info.site_packages)

    if not _parse_auto_install(config):
        return

    available = _discover_plugins()
    to_install: list[tuple[str, str, str, str | None]] = []
    for spec in enabled_specs:
        matches = _match_plugin_spec(spec, available)
        if matches:
            continue
        if spec.kind not in {"pypi", "github", "id"}:
            continue
        to_install.append((spec.raw, spec.kind, spec.name, spec.ref))

    for raw, kind, name, ref in to_install:
        cmd = _install_command(kind=kind, name=name, ref=ref, python=venv_info.python)
        logger.info("plugins.install", plugin=raw, cmd=" ".join(cmd))
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            raise ConfigError(
                f"Failed to auto-install plugin {raw!r} with exit code {exc.returncode}"
            ) from exc

    if not to_install:
        return

    available = _discover_plugins()
    missing: list[str] = []
    for spec in enabled_specs:
        if not _match_plugin_spec(spec, available):
            missing.append(spec.raw)
    if missing:
        joined = ", ".join(missing)
        raise ConfigError(f"Plugins still missing after install: {joined}")

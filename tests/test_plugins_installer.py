from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from takopi.config import ConfigError
from takopi.plugins import installer
from takopi.plugins.manager import PluginDefinition, PluginSpec


def _plugin_map() -> dict[str, PluginDefinition]:
    return {
        "alpha": PluginDefinition(
            plugin_id="alpha",
            factory=lambda: None,
            dist_name="alpha",
            source="test",
        )
    }


def _venv_info(tmp_path: Path) -> installer.PluginVenv:
    return installer.PluginVenv(
        path=tmp_path / "venv",
        python=tmp_path / "venv" / "bin" / "python",
        site_packages=tmp_path / "site-packages",
    )


def test_install_command_prefers_uv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer.shutil, "which", lambda _name: "/bin/uv")
    cmd = installer._install_command(
        kind="github",
        name="org/repo",
        ref="main",
        python=Path("/py"),
    )
    assert cmd == [
        "uv",
        "pip",
        "install",
        "--python",
        "/py",
        "git+https://github.com/org/repo.git@main",
    ]


def test_install_command_falls_back_to_pip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer.shutil, "which", lambda _name: None)
    cmd = installer._install_command(
        kind="pypi",
        name="takopi-plugin-thing",
        ref=None,
        python=Path("/py"),
    )
    assert cmd == ["/py", "-m", "pip", "install", "takopi-plugin-thing"]


def test_parse_auto_install_defaults_to_true() -> None:
    assert installer._parse_auto_install({}) is True
    assert installer._parse_auto_install({"plugins": None}) is True
    assert installer._parse_auto_install({"plugins": "nope"}) is True


def test_parse_auto_install_accepts_boolean() -> None:
    assert installer._parse_auto_install({"plugins": {"auto_install": False}}) is False
    assert installer._parse_auto_install({"plugins": {"auto_install": True}}) is True


def test_install_plugin_unsupported_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = PluginSpec(raw="zip:thing", kind="zip", name="thing", ref=None)
    monkeypatch.setattr(installer, "_parse_plugin_spec", lambda _raw: spec)
    with pytest.raises(ConfigError):
        installer.install_plugin("zip:thing")


def test_install_plugin_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    spec = PluginSpec(raw="pypi:alpha", kind="pypi", name="alpha", ref=None)
    venv_info = _venv_info(tmp_path)
    run_calls: list[list[str]] = []
    clear_calls: list[str] = []

    monkeypatch.setattr(installer, "_parse_plugin_spec", lambda _raw: spec)
    monkeypatch.setattr(installer, "_load_plugin_venv", lambda: venv_info)
    monkeypatch.setattr(installer, "_ensure_sys_path", lambda _path: None)
    monkeypatch.setattr(
        installer,
        "_install_command",
        lambda **_kwargs: ["install", "alpha"],
    )

    def _run(cmd, check: bool) -> subprocess.CompletedProcess[str]:
        assert check is True
        run_calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(installer.subprocess, "run", _run)
    monkeypatch.setattr(installer, "_discover_plugins", _plugin_map)
    monkeypatch.setattr(installer, "_match_plugin_spec", lambda _spec, _avail: ["alpha"])
    monkeypatch.setattr(
        installer.metadata,
        "_clear_cache",
        lambda: clear_calls.append("cleared"),
        raising=False,
    )

    result = installer.install_plugin("pypi:alpha")

    assert result == ["alpha"]
    assert run_calls == [["install", "alpha"]]
    assert clear_calls == ["cleared"]


def test_install_plugin_reports_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spec = PluginSpec(raw="pypi:alpha", kind="pypi", name="alpha", ref=None)
    venv_info = _venv_info(tmp_path)
    monkeypatch.setattr(installer, "_parse_plugin_spec", lambda _raw: spec)
    monkeypatch.setattr(installer, "_load_plugin_venv", lambda: venv_info)
    monkeypatch.setattr(installer, "_ensure_sys_path", lambda _path: None)
    monkeypatch.setattr(
        installer,
        "_install_command",
        lambda **_kwargs: ["install", "alpha"],
    )

    def _run(cmd, check: bool) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(2, cmd)

    monkeypatch.setattr(installer.subprocess, "run", _run)

    with pytest.raises(ConfigError):
        installer.install_plugin("pypi:alpha")


def test_ensure_plugins_ready_auto_install_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_info = _venv_info(tmp_path)
    monkeypatch.setattr(installer, "_load_plugin_venv", lambda: venv_info)
    monkeypatch.setattr(installer, "_ensure_sys_path", lambda _path: None)
    config = {"plugins": {"enabled": ["pypi:alpha"], "auto_install": False}}

    installer.ensure_plugins_ready(config=config, config_path=tmp_path / "takopi.toml")


def test_ensure_plugins_ready_installs_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_info = _venv_info(tmp_path)
    monkeypatch.setattr(installer, "_load_plugin_venv", lambda: venv_info)
    monkeypatch.setattr(installer, "_ensure_sys_path", lambda _path: None)
    monkeypatch.setattr(
        installer,
        "_install_command",
        lambda **_kwargs: ["install", "alpha"],
    )
    available_states = iter([{}, _plugin_map()])
    monkeypatch.setattr(installer, "_discover_plugins", lambda: next(available_states))

    run_calls: list[list[str]] = []

    def _run(cmd, check: bool) -> subprocess.CompletedProcess[str]:
        assert check is True
        run_calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(installer.subprocess, "run", _run)

    config = {"plugins": {"enabled": ["pypi:alpha"]}}
    installer.ensure_plugins_ready(config=config, config_path=tmp_path / "takopi.toml")

    assert run_calls == [["install", "alpha"]]


def test_ensure_plugins_ready_reports_missing_after_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_info = _venv_info(tmp_path)
    monkeypatch.setattr(installer, "_load_plugin_venv", lambda: venv_info)
    monkeypatch.setattr(installer, "_ensure_sys_path", lambda _path: None)
    monkeypatch.setattr(
        installer,
        "_install_command",
        lambda **_kwargs: ["install", "alpha"],
    )
    available_states = iter([{}, {}])
    monkeypatch.setattr(installer, "_discover_plugins", lambda: next(available_states))

    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda cmd, check: subprocess.CompletedProcess(cmd, 0),
    )

    config = {"plugins": {"enabled": ["pypi:alpha"]}}
    with pytest.raises(ConfigError):
        installer.ensure_plugins_ready(config=config, config_path=tmp_path / "takopi.toml")


def test_plugin_venv_helpers(tmp_path: Path) -> None:
    root = installer._plugin_venv_root()
    assert root.name == "venv"
    assert root.parent.name == "plugins"

    python = installer._venv_python(tmp_path / "venv")
    assert python == tmp_path / "venv" / "bin" / "python"


def test_ensure_venv_creates_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    created: list[Path] = []

    class _Builder:
        def __init__(self, *, with_pip: bool, symlinks: bool) -> None:
            assert with_pip is True
            assert symlinks is True

        def create(self, path: Path) -> None:
            created.append(path)

    monkeypatch.setattr(installer.venv, "EnvBuilder", _Builder)

    venv_path = tmp_path / "plugins" / "venv"
    installer._ensure_venv(venv_path)

    assert created == [venv_path]


def test_ensure_venv_skips_when_python_exists(tmp_path: Path) -> None:
    venv_path = tmp_path / "plugins" / "venv"
    python = installer._venv_python(venv_path)
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")

    installer._ensure_venv(venv_path)


def test_site_packages_for_uses_python(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(cmd, check: bool, capture_output: bool, text: bool):
        assert check is True
        assert capture_output is True
        assert text is True
        return subprocess.CompletedProcess(cmd, 0, stdout="/tmp/site\n")

    monkeypatch.setattr(installer.subprocess, "run", _run)
    result = installer._site_packages_for(Path("/py"))
    assert result == Path("/tmp/site")


def test_load_plugin_venv_requires_python(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    venv_root = tmp_path / "venv"
    monkeypatch.setattr(installer, "_plugin_venv_root", lambda: venv_root)
    monkeypatch.setattr(installer, "_ensure_venv", lambda _path: None)

    with pytest.raises(ConfigError):
        installer._load_plugin_venv()


def test_load_plugin_venv_recovers_from_site_packages_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_root = tmp_path / "venv"
    site_packages = tmp_path / "site-packages"
    calls = {"ensure": 0, "site": 0}

    def _ensure(path: Path) -> None:
        calls["ensure"] += 1
        python = installer._venv_python(path)
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text("", encoding="utf-8")

    def _site_packages(_python: Path) -> Path:
        calls["site"] += 1
        if calls["site"] == 1:
            raise OSError("boom")
        return site_packages

    removed: list[Path] = []

    monkeypatch.setattr(installer, "_plugin_venv_root", lambda: venv_root)
    monkeypatch.setattr(installer, "_ensure_venv", _ensure)
    monkeypatch.setattr(installer, "_site_packages_for", _site_packages)
    monkeypatch.setattr(installer.shutil, "rmtree", lambda path: removed.append(path))

    info = installer._load_plugin_venv()

    assert info.site_packages == site_packages
    assert removed == [venv_root]


def test_load_plugin_venv_raises_after_second_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_root = tmp_path / "venv"
    calls = {"site": 0}

    def _ensure(path: Path) -> None:
        python = installer._venv_python(path)
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text("", encoding="utf-8")

    def _site_packages(_python: Path) -> Path:
        calls["site"] += 1
        if calls["site"] == 1:
            raise OSError("boom")
        raise subprocess.CalledProcessError(1, ["py"])

    monkeypatch.setattr(installer, "_plugin_venv_root", lambda: venv_root)
    monkeypatch.setattr(installer, "_ensure_venv", _ensure)
    monkeypatch.setattr(installer, "_site_packages_for", _site_packages)
    monkeypatch.setattr(installer.shutil, "rmtree", lambda _path: None)

    with pytest.raises(ConfigError):
        installer._load_plugin_venv()


def test_load_plugin_venv_raises_when_recreate_missing_python(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_root = tmp_path / "venv"
    python = installer._venv_python(venv_root)
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")

    monkeypatch.setattr(installer, "_plugin_venv_root", lambda: venv_root)
    monkeypatch.setattr(installer, "_ensure_venv", lambda _path: None)
    monkeypatch.setattr(
        installer, "_site_packages_for", lambda _python: (_ for _ in ()).throw(OSError("boom"))
    )

    with pytest.raises(ConfigError):
        installer._load_plugin_venv()


def test_ensure_sys_path_appends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer.sys, "path", [])
    installer._ensure_sys_path(Path("/site-packages"))
    assert installer.sys.path == ["/site-packages"]


def test_ensure_sys_path_skips_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer.sys, "path", ["/site-packages"])
    installer._ensure_sys_path(Path("/site-packages"))
    assert installer.sys.path == ["/site-packages"]


def test_parse_auto_install_invalid_value() -> None:
    assert installer._parse_auto_install({"plugins": {"auto_install": "nope"}}) is True


def test_ensure_plugins_ready_ignores_invalid_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = {"plugins": "nope"}
    installer.ensure_plugins_ready(config=config, config_path=tmp_path / "takopi.toml")


def test_ensure_plugins_ready_no_plugins_config(tmp_path: Path) -> None:
    installer.ensure_plugins_ready(config={}, config_path=tmp_path / "takopi.toml")


def test_ensure_plugins_ready_empty_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = {"plugins": {"enabled": []}}
    installer.ensure_plugins_ready(config=config, config_path=tmp_path / "takopi.toml")


def test_ensure_plugins_ready_skips_installed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_info = _venv_info(tmp_path)
    monkeypatch.setattr(installer, "_load_plugin_venv", lambda: venv_info)
    monkeypatch.setattr(installer, "_ensure_sys_path", lambda _path: None)
    monkeypatch.setattr(installer, "_discover_plugins", _plugin_map)
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda _cmd, check: (_ for _ in ()).throw(AssertionError("should not install")),
    )

    config = {"plugins": {"enabled": ["pypi:alpha"]}}
    installer.ensure_plugins_ready(config=config, config_path=tmp_path / "takopi.toml")


def test_ensure_plugins_ready_skips_unsupported_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_info = _venv_info(tmp_path)
    monkeypatch.setattr(installer, "_load_plugin_venv", lambda: venv_info)
    monkeypatch.setattr(installer, "_ensure_sys_path", lambda _path: None)
    monkeypatch.setattr(
        installer,
        "_parse_plugin_list",
        lambda _value, **_kwargs: [PluginSpec(raw="zip:thing", kind="zip", name="thing", ref=None)],
    )
    monkeypatch.setattr(installer, "_match_plugin_spec", lambda _spec, _avail: [])
    monkeypatch.setattr(installer, "_discover_plugins", lambda: {})
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda _cmd, check: (_ for _ in ()).throw(AssertionError("should not install")),
    )

    config = {"plugins": {"enabled": ["zip:thing"]}}
    installer.ensure_plugins_ready(config=config, config_path=tmp_path / "takopi.toml")


def test_ensure_plugins_ready_reports_install_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_info = _venv_info(tmp_path)
    monkeypatch.setattr(installer, "_load_plugin_venv", lambda: venv_info)
    monkeypatch.setattr(installer, "_ensure_sys_path", lambda _path: None)
    monkeypatch.setattr(installer, "_discover_plugins", lambda: {})
    monkeypatch.setattr(installer, "_match_plugin_spec", lambda _spec, _avail: [])
    monkeypatch.setattr(
        installer,
        "_install_command",
        lambda **_kwargs: ["install", "alpha"],
    )

    def _run(cmd, check: bool) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(installer.subprocess, "run", _run)

    config = {"plugins": {"enabled": ["pypi:alpha"]}}
    with pytest.raises(ConfigError):
        installer.ensure_plugins_ready(config=config, config_path=tmp_path / "takopi.toml")

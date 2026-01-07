import json
import os

import pytest

import takopi.lockfile as lockfile


def test_lockfile_creates_and_cleans_up(tmp_path) -> None:
    config_path = tmp_path / "takopi.toml"
    config_path.write_text("ok", encoding="utf-8")

    handle = lockfile.acquire_lock(
        config_path=config_path,
        token_fingerprint="deadbeef",
    )
    try:
        assert lockfile.lock_path_for_config(config_path).exists()
    finally:
        handle.release()

    assert not lockfile.lock_path_for_config(config_path).exists()


def test_lockfile_refuses_running_pid(tmp_path) -> None:
    config_path = tmp_path / "takopi.toml"
    config_path.write_text("ok", encoding="utf-8")

    handle = lockfile.acquire_lock(
        config_path=config_path,
        token_fingerprint="deadbeef",
    )
    try:
        with pytest.raises(lockfile.LockError) as exc:
            lockfile.acquire_lock(
                config_path=config_path,
                token_fingerprint="deadbeef",
            )
        message = str(exc.value).lower()
        assert "already running" in message
        assert str(lockfile.lock_path_for_config(config_path)) in str(exc.value)
    finally:
        handle.release()


def test_lockfile_replaces_dead_pid(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "takopi.toml"
    config_path.write_text("ok", encoding="utf-8")
    lock_path = lockfile.lock_path_for_config(config_path)
    payload = {"pid": 424242, "token_fingerprint": "deadbeef"}
    lock_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(lockfile, "_pid_running", lambda pid: False)

    handle = lockfile.acquire_lock(
        config_path=config_path,
        token_fingerprint="deadbeef",
    )
    try:
        updated = json.loads(lock_path.read_text(encoding="utf-8"))
        assert updated["pid"] == os.getpid()
        assert updated["token_fingerprint"] == "deadbeef"
    finally:
        handle.release()


def test_lockfile_replaces_token_mismatch(tmp_path) -> None:
    config_path = tmp_path / "takopi.toml"
    config_path.write_text("ok", encoding="utf-8")
    lock_path = lockfile.lock_path_for_config(config_path)
    payload = {"pid": os.getpid(), "token_fingerprint": "other"}
    lock_path.write_text(json.dumps(payload), encoding="utf-8")

    handle = lockfile.acquire_lock(
        config_path=config_path,
        token_fingerprint="deadbeef",
    )
    try:
        updated = json.loads(lock_path.read_text(encoding="utf-8"))
        assert updated["token_fingerprint"] == "deadbeef"
    finally:
        handle.release()


def test_read_lock_info_rejects_invalid_json(tmp_path) -> None:
    lock_path = tmp_path / "takopi.lock"
    lock_path.write_text("nope", encoding="utf-8")
    assert lockfile._read_lock_info(lock_path) is None


def test_read_lock_info_coerces_invalid_fields(tmp_path) -> None:
    lock_path = tmp_path / "takopi.lock"
    lock_path.write_text(
        json.dumps({"pid": True, "token_fingerprint": 123}), encoding="utf-8"
    )
    info = lockfile._read_lock_info(lock_path)
    assert info is not None
    assert info.pid is None
    assert info.token_fingerprint is None


def test_pid_running_permission_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_permission(_pid: int, _sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(lockfile.os, "kill", _raise_permission)
    assert lockfile._pid_running(123) is True


def test_pid_running_process_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_lookup(_pid: int, _sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(lockfile.os, "kill", _raise_lookup)
    assert lockfile._pid_running(123) is False


def test_display_lock_path_under_home() -> None:
    path = lockfile.Path.home() / "takopi" / "foo.lock"
    display = lockfile._display_lock_path(path)
    assert display.startswith("~/")


def test_lock_handle_release_logs_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unlink(_self, *, missing_ok: bool = False) -> None:
        _ = missing_ok
        raise OSError("boom")

    monkeypatch.setattr(lockfile.Path, "unlink", _unlink)
    handle = lockfile.LockHandle(path=lockfile.Path("nope"))
    handle.release()


def test_lock_handle_context_manager() -> None:
    handle = lockfile.LockHandle(path=lockfile.Path("nope"))
    with handle as managed:
        assert managed is handle


def test_token_fingerprint_is_stable() -> None:
    value = lockfile.token_fingerprint("token")
    assert value == lockfile.token_fingerprint("token")
    assert len(value) == 10


def test_read_lock_info_handles_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    def _read_text(_self, *, encoding: str) -> str:
        _ = encoding
        raise OSError("boom")

    monkeypatch.setattr(lockfile.Path, "read_text", _read_text)
    assert lockfile._read_lock_info(lockfile.Path("nope")) is None


def test_pid_running_returns_false_for_empty_pid() -> None:
    assert lockfile._pid_running(None) is False
    assert lockfile._pid_running(-1) is False


def test_format_lock_message_non_running() -> None:
    message = lockfile._format_lock_message(lockfile.Path("nope"), "boom")
    assert "lock failed" in message


def test_display_lock_path_outside_home() -> None:
    path = lockfile.Path("/tmp/takopi.lock")
    display = lockfile._display_lock_path(path)
    assert display == str(path)


def test_acquire_lock_wraps_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    def _mkdir(_self, *, parents: bool, exist_ok: bool) -> None:
        _ = parents
        _ = exist_ok
        raise OSError("boom")

    monkeypatch.setattr(lockfile.Path, "mkdir", _mkdir)

    with pytest.raises(lockfile.LockError) as exc:
        lockfile.acquire_lock(config_path=tmp_path / "takopi.toml")

    assert "boom" in str(exc.value)


def test_read_lock_info_rejects_non_dict(tmp_path) -> None:
    lock_path = tmp_path / "takopi.lock"
    lock_path.write_text(json.dumps(["nope"]), encoding="utf-8")
    assert lockfile._read_lock_info(lock_path) is None


def test_pid_running_handles_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_oserror(_pid: int, _sig: int) -> None:
        raise OSError("boom")

    monkeypatch.setattr(lockfile.os, "kill", _raise_oserror)
    assert lockfile._pid_running(123) is False

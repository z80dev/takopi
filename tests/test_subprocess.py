import sys

import pytest
import anyio

from takopi.utils import subprocess as subprocess_utils


class _DummyProcess:
    def __init__(self, *, pid: int | None, returncode: int | None) -> None:
        self.pid = pid
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    async def wait(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


@pytest.mark.anyio
async def test_manage_subprocess_kills_when_terminate_times_out(
    monkeypatch,
) -> None:
    async def fake_wait_for_process(_proc, timeout: float) -> bool:
        _ = timeout
        return True

    monkeypatch.setattr(subprocess_utils, "wait_for_process", fake_wait_for_process)

    async with subprocess_utils.manage_subprocess(
        [
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(10)",
        ]
    ) as proc:
        assert proc.returncode is None

    assert proc.returncode is not None
    assert proc.returncode != 0


@pytest.mark.anyio
async def test_wait_for_process_returns_false_when_finished() -> None:
    class _Proc:
        async def wait(self) -> None:
            return None

    timed_out = await subprocess_utils.wait_for_process(_Proc(), timeout=0.1)
    assert timed_out is False


@pytest.mark.anyio
async def test_wait_for_process_returns_true_on_timeout() -> None:
    class _Proc:
        async def wait(self) -> None:
            await anyio.sleep(0.05)

    timed_out = await subprocess_utils.wait_for_process(_Proc(), timeout=0.01)
    assert timed_out is True


def test_terminate_process_uses_killpg(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []

    def _killpg(pid: int, sig: int) -> None:
        calls.append((pid, sig))

    monkeypatch.setattr(subprocess_utils.os, "killpg", _killpg)
    proc = _DummyProcess(pid=123, returncode=None)
    subprocess_utils.terminate_process(proc)

    assert calls
    assert proc.terminated is False


def test_terminate_process_falls_back_to_terminate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _killpg(_pid: int, _sig: int) -> None:
        raise RuntimeError("boom")

    debug_calls: list[dict] = []
    monkeypatch.setattr(subprocess_utils.os, "killpg", _killpg)
    monkeypatch.setattr(
        subprocess_utils.logger,
        "debug",
        lambda _event, **kwargs: debug_calls.append(kwargs),
    )
    proc = _DummyProcess(pid=456, returncode=None)
    subprocess_utils.terminate_process(proc)

    assert proc.terminated is True
    assert debug_calls


def test_kill_process_falls_back_to_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    def _killpg(_pid: int, _sig: int) -> None:
        raise RuntimeError("boom")

    debug_calls: list[dict] = []
    monkeypatch.setattr(subprocess_utils.os, "killpg", _killpg)
    monkeypatch.setattr(
        subprocess_utils.logger,
        "debug",
        lambda _event, **kwargs: debug_calls.append(kwargs),
    )
    proc = _DummyProcess(pid=789, returncode=None)
    subprocess_utils.kill_process(proc)

    assert proc.killed is True
    assert debug_calls


def test_terminate_process_returns_when_returncode_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess_utils.os,
        "killpg",
        lambda _pid, _sig: (_ for _ in ()).throw(AssertionError("should not call")),
    )
    proc = _DummyProcess(pid=111, returncode=0)
    subprocess_utils.terminate_process(proc)
    assert proc.terminated is False


def test_terminate_process_returns_on_process_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess_utils.os, "killpg", lambda _pid, _sig: (_ for _ in ()).throw(ProcessLookupError()))
    proc = _DummyProcess(pid=222, returncode=None)
    subprocess_utils.terminate_process(proc)
    assert proc.terminated is False


def test_terminate_process_ignores_terminate_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = _DummyProcess(pid=None, returncode=None)

    def _terminate() -> None:
        raise ProcessLookupError

    proc.terminate = _terminate  # type: ignore[assignment]
    subprocess_utils.terminate_process(proc)


def test_kill_process_returns_when_returncode_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess_utils.os,
        "killpg",
        lambda _pid, _sig: (_ for _ in ()).throw(AssertionError("should not call")),
    )
    proc = _DummyProcess(pid=333, returncode=0)
    subprocess_utils.kill_process(proc)
    assert proc.killed is False


def test_kill_process_returns_on_process_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess_utils.os, "killpg", lambda _pid, _sig: (_ for _ in ()).throw(ProcessLookupError()))
    proc = _DummyProcess(pid=444, returncode=None)
    subprocess_utils.kill_process(proc)
    assert proc.killed is False


def test_kill_process_ignores_kill_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = _DummyProcess(pid=None, returncode=None)

    def _kill() -> None:
        raise ProcessLookupError

    proc.kill = _kill  # type: ignore[assignment]
    subprocess_utils.kill_process(proc)


def test_kill_process_uses_killpg(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []

    def _killpg(pid: int, sig: int) -> None:
        calls.append((pid, sig))

    monkeypatch.setattr(subprocess_utils.os, "killpg", _killpg)
    proc = _DummyProcess(pid=555, returncode=None)
    subprocess_utils.kill_process(proc)

    assert calls
    assert proc.killed is False

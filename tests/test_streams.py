import anyio
import pytest

from takopi.utils import streams


class _ByteStream(anyio.abc.ByteReceiveStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def receive(self, max_bytes: int) -> bytes:
        if not self._chunks:
            raise anyio.EndOfStream
        chunk = self._chunks.pop(0)
        if len(chunk) > max_bytes:
            self._chunks.insert(0, chunk[max_bytes:])
            chunk = chunk[:max_bytes]
        return chunk

    async def aclose(self) -> None:
        return None


@pytest.mark.anyio
async def test_iter_bytes_lines_yields_complete_lines() -> None:
    stream = _ByteStream([b"hello\nwor", b"ld\n"])
    lines = [line async for line in streams.iter_bytes_lines(stream)]
    assert lines == [b"hello\n", b"world\n"]


@pytest.mark.anyio
async def test_iter_bytes_lines_drops_partial_line_at_eof() -> None:
    stream = _ByteStream([b"incomplete"])
    lines = [line async for line in streams.iter_bytes_lines(stream)]
    assert lines == []


@pytest.mark.anyio
async def test_drain_stderr_logs_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict]] = []

    def _fake_log_pipeline(logger, event: str, **kwargs) -> None:
        _ = logger
        calls.append((event, kwargs))

    monkeypatch.setattr(streams, "log_pipeline", _fake_log_pipeline)
    stream = _ByteStream([b"one\n", b"two\n"])

    await streams.drain_stderr(stream, logger="logger", tag="stderr")

    assert calls == [
        ("subprocess.stderr", {"tag": "stderr", "line": "one\n"}),
        ("subprocess.stderr", {"tag": "stderr", "line": "two\n"}),
    ]


@pytest.mark.anyio
async def test_drain_stderr_logs_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict]] = []

    def _fake_log_pipeline(logger, event: str, **kwargs) -> None:
        _ = logger
        calls.append((event, kwargs))

    async def _boom_iter_bytes_lines(_stream):
        raise RuntimeError("boom")
        yield b""  # pragma: no cover

    monkeypatch.setattr(streams, "log_pipeline", _fake_log_pipeline)
    monkeypatch.setattr(streams, "iter_bytes_lines", _boom_iter_bytes_lines)

    await streams.drain_stderr(_ByteStream([]), logger="logger", tag="stderr")

    assert calls == [
        ("subprocess.stderr.error", {"tag": "stderr", "error": "boom"}),
    ]

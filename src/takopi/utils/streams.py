from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anyio
from anyio.abc import ByteReceiveStream

from ..logging import log_pipeline


async def iter_bytes_lines(stream: ByteReceiveStream) -> AsyncIterator[bytes]:
    buffer = bytearray()
    while True:
        try:
            chunk = await stream.receive(65536)
        except anyio.EndOfStream:
            return
        buffer.extend(chunk)
        while True:
            newline_index = buffer.find(b"\n")
            if newline_index < 0:
                break
            line = bytes(buffer[: newline_index + 1])
            del buffer[: newline_index + 1]
            yield line


async def drain_stderr(
    stream: ByteReceiveStream,
    logger: Any,
    tag: str,
) -> None:
    try:
        async for line in iter_bytes_lines(stream):
            text = line.decode("utf-8", errors="replace")
            log_pipeline(
                logger,
                "subprocess.stderr",
                tag=tag,
                line=text,
            )
    except Exception as exc:
        log_pipeline(
            logger,
            "subprocess.stderr.error",
            tag=tag,
            error=str(exc),
        )

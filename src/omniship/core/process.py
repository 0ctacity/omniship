"""Async subprocess output capture with task-scoped live logging."""

import asyncio
from dataclasses import dataclass

from omniship.core.context import ExecutionContext
from omniship.core.logging import LogLevel, LogStream


@dataclass(frozen=True)
class ProcessOutput:
    """Captured subprocess streams and termination state."""

    return_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


async def stream_process(
    process: asyncio.subprocess.Process,
    context: ExecutionContext,
    *,
    timeout: float | None = None,
) -> ProcessOutput:
    """Wait for a process while streaming stdout and stderr into ``context``.

    Output is retained for the operation result and normalized to LF line
    endings so behavior is consistent across CI operating systems. A timeout
    kills the process after allowing both stream readers to drain.
    """

    stdout: list[str] = []
    stderr: list[str] = []

    async def read_stream(
        reader: asyncio.StreamReader | None,
        destination: list[str],
        stream: LogStream,
    ) -> None:
        if reader is None:
            return
        while chunk := await reader.readline():
            text = chunk.decode("utf-8", errors="replace").replace("\r\n", "\n")
            destination.append(text)
            context.emit_log(LogLevel.INFO, text.rstrip("\r\n"), stream)

    readers = (
        asyncio.create_task(read_stream(process.stdout, stdout, LogStream.STDOUT)),
        asyncio.create_task(read_stream(process.stderr, stderr, LogStream.STDERR)),
    )
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
    except TimeoutError:
        timed_out = True
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.wait()
    await asyncio.gather(*readers)
    return ProcessOutput(
        return_code=process.returncode or 0,
        stdout="".join(stdout),
        stderr="".join(stderr),
        timed_out=timed_out,
    )

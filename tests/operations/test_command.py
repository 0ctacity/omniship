import asyncio
import sys
from pathlib import Path

import pytest

from omniship.core.context import ExecutionContext
from omniship.core.logging import LogRecord, LogStream
from omniship.core.node import NodeInputs
from omniship.core.stage import Stage
from omniship.operations.command import CommandOperation


@pytest.mark.asyncio
async def test_command_streams_output_before_process_finishes(tmp_path: Path) -> None:
    records: list[LogRecord] = []
    context = ExecutionContext(
        workspace_root=tmp_path,
        stage=Stage.CHECK,
        task_id="stream",
        log_sink=records.append,
    )
    execution = asyncio.create_task(
        CommandOperation().execute(
            context,
            NodeInputs(
                params={
                    "run": [
                        sys.executable,
                        "-c",
                        (
                            "import time; print('first', flush=True); "
                            "time.sleep(0.25); print('second', flush=True)"
                        ),
                    ]
                }
            ),
        )
    )

    await asyncio.sleep(0.1)

    assert [(record.stream, record.message) for record in records] == [
        (LogStream.STDOUT, "first")
    ]
    result = await execution
    assert result.is_success
    assert result.stdout == "first\nsecond\n"
    assert [record.message for record in records] == ["first", "second"]

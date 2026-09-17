from pathlib import Path

import pytest

from omniship.core.artifact import Artifact
from omniship.core.context import ExecutionContext
from omniship.core.node import NodeInputs
from omniship.core.stage import Stage
from omniship.operations.python_task import PythonTaskOperation


@pytest.mark.asyncio
async def test_python_task_executes_and_collects_artifacts(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.py"
    workflow.write_text(
        "def package(ctx):\n"
        "    output = ctx.workspace / 'dist.whl'\n"
        "    output.write_text('wheel')\n"
        "    ctx.log.info('built wheel')\n"
        "    ctx.artifacts.add(output)\n",
        encoding="utf-8",
    )
    context = ExecutionContext(workspace_root=tmp_path, stage=Stage.BUILD)

    result = await PythonTaskOperation().execute(
        context,
        NodeInputs(params={"callable": "workflow.py:package"}),
    )

    assert result.is_success
    assert result.stdout == "built wheel"
    assert [artifact.name for artifact in result.artifacts] == ["dist.whl"]


@pytest.mark.asyncio
async def test_python_task_turns_exceptions_into_failures(tmp_path: Path) -> None:
    (tmp_path / "workflow.py").write_text(
        "def fail(ctx):\n    raise ValueError('broken release')\n",
        encoding="utf-8",
    )
    context = ExecutionContext(workspace_root=tmp_path, stage=Stage.CHECK)

    result = await PythonTaskOperation().execute(
        context,
        NodeInputs(params={"callable": "workflow.py:fail"}),
    )

    assert result.is_failed
    assert result.error_message == "ValueError: broken release"


@pytest.mark.asyncio
async def test_decorated_task_remains_importable_at_execution_time(
    tmp_path: Path,
) -> None:
    (tmp_path / "workflow.py").write_text(
        "from omniship import Pipeline\n"
        "pipeline = Pipeline()\n"
        "@pipeline.build\n"
        "def package(ctx):\n"
        "    ctx.log.info('decorated task ran')\n",
        encoding="utf-8",
    )
    context = ExecutionContext(workspace_root=tmp_path, stage=Stage.BUILD)

    result = await PythonTaskOperation().execute(
        context,
        NodeInputs(params={"callable": "workflow.py:package"}),
    )

    assert result.is_success
    assert result.stdout == "decorated task ran"


@pytest.mark.asyncio
async def test_python_task_can_read_artifacts_from_earlier_stages(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "existing.whl"
    existing.write_text("wheel", encoding="utf-8")
    (tmp_path / "workflow.py").write_text(
        "def publish(ctx):\n"
        "    names = [artifact.name for artifact in ctx.artifacts]\n"
        "    ctx.log.info(','.join(names))\n",
        encoding="utf-8",
    )
    context = ExecutionContext(workspace_root=tmp_path, stage=Stage.SHIP)
    context.artifacts.add(Artifact.from_path(existing))

    result = await PythonTaskOperation().execute(
        context,
        NodeInputs(params={"callable": "workflow.py:publish"}),
    )

    assert result.is_success
    assert result.stdout == "existing.whl"
    assert result.artifacts == ()

from pathlib import Path
from omniship.core.artifact import Artifact, ArtifactSet
from omniship.core.context import ExecutionContext
from omniship.core.node import Node, NodeInputs
from omniship.core.result import NodeResult, NodeStatus
from omniship.core.stage import Stage


def test_stage_enum():
    assert Stage.CHECK == "check"
    assert Stage.BUILD == "build"
    assert Stage.SHIP == "ship"


def test_artifact_and_set(tmp_path: Path):
    f1 = tmp_path / "bin1"
    f1.write_text("dummy1")
    f2 = tmp_path / "bin2"
    f2.write_text("dummy2")

    a1 = Artifact.from_path(f1, name="dist/bin1", metadata={"arch": "x86_64"})
    a2 = Artifact.from_path(f2, name="dist/bin2")

    aset = ArtifactSet()
    aset.add(a1)
    aset.add(a2)

    assert len(aset) == 2
    assert "dist/bin1" in aset
    assert aset.get("dist/bin1") == a1
    assert aset.get("dist/bin2") == a2
    assert len(aset.to_list()) == 2


def test_node_result():
    res_success = NodeResult(status=NodeStatus.SUCCESS, duration=1.5)
    assert res_success.is_success
    assert not res_success.is_failed
    assert not res_success.is_skipped

    res_fail = NodeResult(status=NodeStatus.FAILED, error_message="boom")
    assert res_fail.is_failed

    res_skip = NodeResult(status=NodeStatus.SKIPPED, error_message="dependency failed")
    assert res_skip.is_skipped


def test_execution_context(tmp_path: Path):
    ctx = ExecutionContext(workspace_root=tmp_path, stage=Stage.CHECK)
    f = tmp_path / "file"
    f.write_text("test")
    art = Artifact.from_path(f)
    res = NodeResult(status=NodeStatus.SUCCESS, artifacts=(art,))
    ctx.record_result("node1", res)

    assert ctx.results["node1"] == res
    assert ctx.get_artifact(art.name) == art

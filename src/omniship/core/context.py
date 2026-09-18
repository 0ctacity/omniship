from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omniship.core.artifact import Artifact, ArtifactSet
from omniship.core.logging import LogLevel, LogRecord, LogSink, LogStream
from omniship.core.result import NodeResult
from omniship.core.stage import Stage


@dataclass
class ExecutionContext:
    workspace_root: Path
    stage: Stage
    artifacts: ArtifactSet = field(default_factory=ArtifactSet)
    env: dict[str, str] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    results: dict[str, NodeResult] = field(default_factory=dict)
    task_id: str | None = None
    log_sink: LogSink | None = None

    def get_artifact(self, name: str) -> Artifact | None:
        return self.artifacts.get(name)

    def record_result(self, node_id: str, result: NodeResult) -> None:
        self.results[node_id] = result
        for art in result.artifacts:
            self.artifacts.add(art)

    def emit_log(
        self,
        level: LogLevel,
        message: str,
        stream: LogStream = LogStream.LOG,
    ) -> None:
        if self.log_sink is None or self.task_id is None:
            return
        self.log_sink(
            LogRecord(
                stage=self.stage,
                task=self.task_id,
                level=level,
                message=message,
                stream=stream,
            )
        )

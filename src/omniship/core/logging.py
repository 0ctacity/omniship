"""Provider-neutral structured logging models and level filtering."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from omniship.core.stage import Stage


class LogLevel(StrEnum):
    """Severity assigned to an OmniShip log record."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LogStream(StrEnum):
    """Origin of a log message."""

    LOG = "log"
    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True)
class Logging:
    """User-facing logging behavior for generated and local workflows."""

    level: LogLevel = LogLevel.INFO
    show_output: bool = True
    timestamps: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.level, LogLevel):
            raise TypeError("logging level must be a LogLevel value")
        if not isinstance(self.show_output, bool):
            raise TypeError("show_output must be a boolean")
        if not isinstance(self.timestamps, bool):
            raise TypeError("timestamps must be a boolean")


@dataclass(frozen=True)
class LogRecord:
    """A structured message attributed to a pipeline stage and task."""

    stage: Stage
    task: str
    level: LogLevel
    message: str
    stream: LogStream = LogStream.LOG


LogSink = Callable[[LogRecord], None]


_LEVEL_RANK = {
    LogLevel.DEBUG: 10,
    LogLevel.INFO: 20,
    LogLevel.WARNING: 30,
    LogLevel.ERROR: 40,
}


def includes_level(configured: LogLevel, emitted: LogLevel) -> bool:
    """Return whether ``emitted`` meets the configured severity threshold."""

    return _LEVEL_RANK[emitted] >= _LEVEL_RANK[configured]

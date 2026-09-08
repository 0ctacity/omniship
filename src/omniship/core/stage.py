from enum import StrEnum


class Stage(StrEnum):
    CHECK = "check"
    BUILD = "build"
    SHIP = "ship"

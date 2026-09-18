from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NodeConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    uses: str
    needs: list[str] = Field(default_factory=list)
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")
    if_: dict[str, Any] | str | None = Field(default=None, alias="if")
    when: dict[str, Any] | None = Field(default=None)
    execution: Any = Field(default=None, exclude=True)

    @property
    def condition(self) -> dict[str, Any] | str | None:
        return self.when or self.if_


class OmniShipConfig(BaseModel):
    version: int = 1
    check: dict[str, NodeConfig] = Field(default_factory=dict)
    build: dict[str, NodeConfig] = Field(default_factory=dict)
    ship: dict[str, NodeConfig] = Field(default_factory=dict)

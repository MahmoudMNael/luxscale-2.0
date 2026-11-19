from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RefreshTokenRequestDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    refreshToken: str | None = Field(default=None, alias="refreshToken")

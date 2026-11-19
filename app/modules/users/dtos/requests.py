from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class UpdateSignatureRequestDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    logoObjectKey: str | None = Field(default=None, alias="logoObjectKey")
    extraFields: dict[str, Any] | None = Field(default=None, alias="extraFields")


class UpdatePreferencesRequestDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    preferences: dict[str, Any] = Field(default_factory=dict)

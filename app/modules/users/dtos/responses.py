from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class SignatureResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    userId: str = Field(alias="userId")
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    logoObjectKey: str | None = Field(default=None, alias="logoObjectKey")
    logoUrl: str | None = Field(default=None, alias="logoUrl")
    extraFields: dict[str, Any] = Field(default_factory=dict, alias="extraFields")
    updatedAt: str = Field(alias="updatedAt")


class PreferencesResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    userId: str = Field(alias="userId")
    preferences: dict[str, Any] = Field(default_factory=dict)
    updatedAt: str = Field(alias="updatedAt")

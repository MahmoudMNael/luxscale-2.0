from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.modules.users.dtos.responses import SignatureResponseDto


class UserSummaryResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    email: str
    name: str
    role: str


class TokenResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    accessToken: str = Field(alias="accessToken")
    tokenType: str = Field(default="Bearer", alias="tokenType")
    expiresIn: int = Field(alias="expiresIn")
    user: UserSummaryResponseDto


class LogoutResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    logoutUrl: str = Field(alias="logoutUrl")


class UserMeResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    email: str
    name: str
    role: str
    signature: SignatureResponseDto | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)

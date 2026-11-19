from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UploadTicketResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    uploadUrl: str = Field(
        ...,
        alias="uploadUrl",
        description="Presigned/signed direct upload URL to which the client PUTs binary content.",
    )
    method: str = Field(
        default="PUT",
        description="HTTP method to use when uploading (standard PUT).",
    )
    fileKey: str = Field(
        ...,
        alias="fileKey",
        description="The resulting object storage key to save in database references.",
    )
    downloadUrl: str = Field(
        ...,
        alias="downloadUrl",
        description="Direct download URL for the uploaded object.",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Optional HTTP headers required during the PUT upload request.",
    )

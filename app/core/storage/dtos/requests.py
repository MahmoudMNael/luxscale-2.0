from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class UploadTicketRequestDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    purpose: Literal["project_thumbnail", "project_archive", "signature_logo", "general"] = Field(
        ...,
        description="Category/purpose of the object for access control and folder scoping.",
    )
    contentType: str = Field(
        ...,
        alias="contentType",
        description="MIME type of the file to upload, e.g. 'image/png', 'application/zip'.",
    )
    filename: str | None = Field(
        None,
        description="Original or suggested filename with extension.",
    )
    projectId: str | None = Field(
        None,
        alias="projectId",
        description="Associated project ID when purpose is related to a project.",
    )

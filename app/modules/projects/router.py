from __future__ import annotations

import io
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.modules.auth.dependencies import get_current_user
from app.modules.projects.dtos.requests import CopyProjectRequestDto, SaveProjectRequestDto
from app.modules.projects.dtos.responses import ProjectDetailResponseDto, ProjectListItemDto
from app.modules.projects.services.project_service import ProjectService, get_project_service
from app.modules.users.entities.user_entity import UserEntity

router = APIRouter(prefix="/api/v2/projects", tags=["V2 Projects"])


@router.get(
    "",
    response_model=list[ProjectListItemDto],
    summary="List all projects owned by caller",
    description="Returns a summarized list of all stored projects owned by the authenticated user.",
)
def list_projects(
    current_user: UserEntity = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> list[ProjectListItemDto]:
    return service.list_projects(current_user.id)


@router.post(
    "",
    response_model=ProjectDetailResponseDto,
    summary="Save project (Create or Update)",
    description="Saves a project document. If id is omitted or not found, creates a new project (201); if found and owned, updates it (200). Rejects with 403 if owned by another user.",
)
def save_project(
    doc: SaveProjectRequestDto,
    response: Response,
    current_user: UserEntity = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetailResponseDto:
    dto, is_created = service.save_project(doc, current_user.id)
    response.status_code = status.HTTP_201_CREATED if is_created else status.HTTP_200_OK
    return dto


@router.put(
    "/{project_id}",
    response_model=ProjectDetailResponseDto,
    summary="Explicit save project by ID",
    description="Updates existing project if found and owned (200), or creates it with project_id if it has no previous existence (201). Rejects with 403 if owned by another user.",
)
def explicit_save_project(
    project_id: str,
    doc: SaveProjectRequestDto,
    response: Response,
    current_user: UserEntity = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetailResponseDto:
    dto, is_created = service.save_project(doc, current_user.id, target_id=project_id)
    response.status_code = status.HTTP_201_CREATED if is_created else status.HTTP_200_OK
    return dto


@router.post(
    "/{project_id}/copy",
    response_model=ProjectDetailResponseDto,
    status_code=status.HTTP_201_CREATED,
    summary="Make a copy (Duplicate project)",
    description="Creates a duplicate of an existing project with name 'Copy of {project name}' (or optional custom name) and duplicates its object storage archive.",
)
def copy_project(
    project_id: str,
    body: CopyProjectRequestDto | None = None,
    current_user: UserEntity = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetailResponseDto:
    custom_name = body.name if body else None
    return service.copy_project(project_id, current_user.id, custom_name=custom_name)


@router.get(
    "/{project_id}",
    response_model=ProjectDetailResponseDto,
    summary="Get project by ID",
    description="Retrieves the full project document including room geometry, fixtures, and presigned asset download links.",
)
def get_project(
    project_id: str,
    current_user: UserEntity = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetailResponseDto:
    return service.get_project(project_id, current_user.id)


@router.get(
    "/{project_id}/export",
    summary="Export project as .lxsc archive",
    description="Downloads the self-contained .lxsc zip archive from object storage.",
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "The downloaded .lxsc zip archive",
        }
    },
)
def export_project_lxsc(
    project_id: str,
    current_user: UserEntity = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> Response:
    filename, lxsc_bytes = service.export_lxsc(project_id, current_user.id)
    return StreamingResponse(
        io.BytesIO(lxsc_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/import",
    response_model=ProjectDetailResponseDto,
    status_code=status.HTTP_201_CREATED,
    summary="Import project from .lxsc file",
    description="Uploads an .lxsc archive, unpacks project.json, and saves to database and object storage under current user.",
)
async def import_project_lxsc(
    file: UploadFile = File(..., description="The .lxsc zip archive to upload"),
    current_user: UserEntity = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetailResponseDto:
    if not file.filename or not (file.filename.endswith(".lxsc") or file.filename.endswith(".zip")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .lxsc project archives are supported",
        )
    try:
        content = await file.read()
        return service.import_lxsc(content, current_user.id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to import .lxsc archive: {exc}",
        )


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project",
    description="Deletes project from database and removes its archive from object storage.",
)
def delete_project(
    project_id: str,
    current_user: UserEntity = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> None:
    deleted = service.delete_project(project_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

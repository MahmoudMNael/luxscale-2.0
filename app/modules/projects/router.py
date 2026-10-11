from __future__ import annotations

import io
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.modules.projects.models import ProjectDomainModel
from app.modules.projects.schemas import ProjectDocumentDto, ProjectListItemDto
from app.modules.projects.service import ProjectService, get_project_service

router = APIRouter(prefix="/api/v2/projects", tags=["V2 Projects"])


@router.get(
    "",
    response_model=list[ProjectListItemDto],
    summary="List all projects",
    description="Returns a summarized list of all stored projects with metadata, room areas, and fixture counts.",
)
def list_projects(
    service: ProjectService = Depends(get_project_service),
) -> list[ProjectListItemDto]:
    summaries = service.list_projects()
    return [
        ProjectListItemDto(
            id=s.id,
            name=s.name,
            sceneName=s.scene_name,
            schemaVersion=s.schema_version,
            createdAt=s.created_at,
            updatedAt=s.updated_at,
            fixtureCount=s.fixture_count,
            roomArea=s.room_area,
        )
        for s in summaries
    ]


@router.post(
    "",
    response_model=ProjectDocumentDto,
    status_code=status.HTTP_201_CREATED,
    summary="Create or save project",
    description="Saves a project document to PostgreSQL and stores its .lxsc archive on disk.",
)
def create_or_save_project(
    doc: ProjectDocumentDto,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDocumentDto:
    domain_model = ProjectDomainModel.from_dict(doc.model_dump())
    saved = service.save_project(domain_model)
    return ProjectDocumentDto.model_validate(saved.to_dict())


@router.get(
    "/{project_id}",
    response_model=ProjectDocumentDto,
    summary="Get project by ID",
    description="Retrieves the full project document including room geometry, fixtures, and physics settings.",
)
def get_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDocumentDto:
    model, _ = service.get_project(project_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )
    return ProjectDocumentDto.model_validate(model.to_dict())


@router.get(
    "/{project_id}/export",
    summary="Export project as .lxsc",
    description="Downloads the self-contained .lxsc zip archive containing project.json and all bundled assets.",
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "The downloaded .lxsc zip archive",
        }
    },
)
def export_project_lxsc(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
) -> Response:
    try:
        filename, lxsc_bytes = service.export_lxsc(project_id)
        return StreamingResponse(
            io.BytesIO(lxsc_bytes),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project archive for '{project_id}' not found",
        )


@router.post(
    "/import",
    response_model=ProjectDocumentDto,
    status_code=status.HTTP_201_CREATED,
    summary="Import project from .lxsc file",
    description="Uploads an .lxsc archive, unpacks project.json and assets, validates the schema, and saves to database.",
)
async def import_project_lxsc(
    file: UploadFile = File(..., description="The .lxsc zip archive to upload"),
    service: ProjectService = Depends(get_project_service),
) -> ProjectDocumentDto:
    if not file.filename or not (file.filename.endswith(".lxsc") or file.filename.endswith(".zip")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .lxsc project archives are supported",
        )
    try:
        content = await file.read()
        saved = service.import_lxsc(content)
        return ProjectDocumentDto.model_validate(saved.to_dict())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to import .lxsc archive: {exc}",
        )


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project",
    description="Deletes project from database and removes its .lxsc archive from disk.",
)
def delete_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
) -> None:
    deleted = service.delete_project(project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

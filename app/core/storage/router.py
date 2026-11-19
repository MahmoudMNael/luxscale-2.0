from __future__ import annotations

import mimetypes
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from app.core.storage.dtos.requests import UploadTicketRequestDto
from app.core.storage.dtos.responses import UploadTicketResponseDto
from app.core.storage.providers.local_provider import LocalStorageProvider
from app.core.storage.services.storage_service import StorageService, get_storage_service

router = APIRouter(prefix="/api/v2/storage", tags=["V2 Storage"])


@router.post(
    "/upload-ticket",
    response_model=UploadTicketResponseDto,
    status_code=status.HTTP_200_OK,
    summary="Request a direct upload ticket",
    description="Generates a presigned/signed direct upload URL so the browser can upload files directly without consuming server processing bandwidth.",
)
def create_upload_ticket(
    body: UploadTicketRequestDto,
    service: StorageService = Depends(get_storage_service),
) -> UploadTicketResponseDto:
    # In Phase 1, user_id defaults to anonymous/shared until Phase 2 auth dependency is wired
    return service.create_upload_ticket(body)


@router.put(
    "/raw/{token}",
    status_code=status.HTTP_200_OK,
    summary="Direct binary upload endpoint (Local storage)",
    description="Accepts direct binary PUT upload verified by an HMAC-signed token, streaming directly to disk.",
)
async def upload_local_binary(
    token: str,
    request: Request,
    service: StorageService = Depends(get_storage_service),
) -> dict[str, str]:
    if not isinstance(service.provider, LocalStorageProvider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Direct local raw upload endpoint is only active when using local storage provider.",
        )

    payload = service.provider.verify_token(token, expected_action="put")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired storage upload token.",
        )

    key = payload["k"]
    target_path = service.provider._resolve_path(key)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "wb") as f:
        async for chunk in request.stream():
            f.write(chunk)

    return {"status": "uploaded", "key": key}


@router.get(
    "/raw/{token}",
    summary="Direct binary download endpoint (Local storage)",
    description="Downloads binary object verified by an HMAC-signed token.",
)
def download_local_binary(
    token: str,
    service: StorageService = Depends(get_storage_service),
) -> Response:
    if not isinstance(service.provider, LocalStorageProvider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Direct local raw download endpoint is only active when using local storage provider.",
        )

    payload = service.provider.verify_token(token, expected_action="get")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired storage download token.",
        )

    key = payload["k"]
    file_path = service.provider._resolve_path(key)
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stored object '{key}' not found.",
        )

    filename = payload.get("fn")
    media_type = payload.get("ct")
    if not media_type:
        guessed, _ = mimetypes.guess_type(str(file_path))
        media_type = guessed or "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )

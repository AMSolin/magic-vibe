import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.db.user_data_session import get_user_data_db
from app.services.delver_lens_import import (
    DelverLensImportError,
    apply_import_session,
    create_delver_lens_import_session,
    delete_import_session,
    delete_import_session_entity,
    get_import_session_preview,
    merge_import_session_entity,
    update_import_session_entity,
)

router = APIRouter()


class DelverLensEntityEditRead(BaseModel):
    id: int | None = None
    source_list_id: int | None = None
    target_type: str
    name: str = Field(min_length=1, max_length=255)
    note: str | None = None
    player_id: int
    created_at: int = Field(ge=0)
    target_collection_mode: str | None = None
    target_collection_id: int | None = None
    target_import_list_id: int | None = None


class DelverLensMergePayload(BaseModel):
    target_entity_id: int
    merge_section: str


def _validate_entity_edit(payload: DelverLensEntityEditRead) -> None:
    if payload.target_type not in {"collection", "wishlist", "deck", "wishdeck"}:
        raise DelverLensImportError(f"Unknown target type: {payload.target_type}")
    if payload.target_collection_mode not in {None, "new", "existing", "import"}:
        raise DelverLensImportError(
            f"Unknown target collection mode: {payload.target_collection_mode}"
        )


def _entity_id(payload: DelverLensEntityEditRead, path_entity_id: int) -> int:
    entity_id = payload.id or payload.source_list_id or path_entity_id
    if entity_id != path_entity_id:
        raise DelverLensImportError("Import entity id does not match the request path")
    return entity_id


def _save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix != ".dlens":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select a .dlens file.",
        )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dlens") as temporary_file:
        path = Path(temporary_file.name)
        while chunk := upload.file.read(1024 * 1024):
            temporary_file.write(chunk)
    return path


@router.post("/delver-lens/preview")
def preview_delver_lens(
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_user_data_db),
) -> dict:
    path = _save_upload(file)
    try:
        return create_delver_lens_import_session(path, file.filename or "import.dlens", db)
    except DelverLensImportError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    finally:
        path.unlink(missing_ok=True)


@router.get("/delver-lens/sessions/{session_id}")
def get_delver_lens_session(
    session_id: str,
    db: Session = Depends(get_user_data_db),
) -> dict:
    try:
        return get_import_session_preview(session_id, db)
    except DelverLensImportError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.delete("/delver-lens/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_delver_lens_session(session_id: str) -> None:
    delete_import_session(session_id)


@router.patch("/delver-lens/sessions/{session_id}/entities/{entity_id}")
def update_delver_lens_entity(
    session_id: str,
    entity_id: int,
    payload: DelverLensEntityEditRead,
    db: Session = Depends(get_user_data_db),
) -> dict:
    try:
        _validate_entity_edit(payload)
        resolved_entity_id = _entity_id(payload, entity_id)
        target_collection_ref_id = (
            payload.target_collection_id
            if payload.target_collection_mode == "existing"
            else payload.target_import_list_id
        )
        return update_import_session_entity(
            session_id,
            resolved_entity_id,
            target_type=payload.target_type,  # type: ignore[arg-type]
            name=payload.name,
            note=payload.note,
            player_id=payload.player_id,
            created_at=payload.created_at,
            target_collection_ref_type=payload.target_collection_mode,  # type: ignore[arg-type]
            target_collection_ref_id=target_collection_ref_id,
            db=db,
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Import settings are invalid",
        ) from error
    except DelverLensImportError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.delete("/delver-lens/sessions/{session_id}/entities/{entity_id}")
def delete_delver_lens_entity(
    session_id: str,
    entity_id: int,
    db: Session = Depends(get_user_data_db),
) -> dict:
    try:
        return delete_import_session_entity(session_id, entity_id, db)
    except DelverLensImportError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/delver-lens/sessions/{session_id}/entities/{entity_id}/merge")
def merge_delver_lens_entity(
    session_id: str,
    entity_id: int,
    payload: DelverLensMergePayload,
    db: Session = Depends(get_user_data_db),
) -> dict:
    if payload.merge_section not in {"keep", "main", "side", "maybe", "commander"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Merge section is invalid")
    try:
        return merge_import_session_entity(
            session_id,
            entity_id,
            target_entity_id=payload.target_entity_id,
            merge_section=payload.merge_section,  # type: ignore[arg-type]
            db=db,
        )
    except DelverLensImportError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/delver-lens/sessions/{session_id}/apply")
def apply_delver_lens_session(
    session_id: str,
    db: Session = Depends(get_user_data_db),
) -> dict:
    try:
        return apply_import_session(session_id, db)
    except DelverLensImportError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

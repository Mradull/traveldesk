"""
POST /evidence (multipart 'file' -> EvidenceUploadOut) and GET /evidence/{evidence_id}/file (owner or approving manager).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.engine import Connection

from app.core.deps import get_current_user, get_db, require_employee
from app.core.errors import AppError
from app.schemas import CurrentUser, ErrorCode, EvidenceUploadOut, ReceiptVerificationOut, ReceiptVerifyRequest
from app.services import evidence_service, receipt_service

router = APIRouter(prefix="/evidence", tags=["evidence"])

Db = Annotated[Connection, Depends(get_db)]


@router.post("", response_model=EvidenceUploadOut, status_code=status.HTTP_201_CREATED)
def upload_evidence(
    file: Annotated[UploadFile, File(description="Receipt photo: JPEG, PNG or WEBP, max 5 MB")],
    employee: Annotated[CurrentUser, Depends(require_employee)],
    db: Db,
) -> EvidenceUploadOut:
    """US-10: upload one receipt photo (multipart form field 'file')."""
    return evidence_service.upload(db, employee, file.filename, file.file)


@router.get(
    "/{evidence_id}/file",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}}}},
)
def get_evidence_file(
    evidence_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Db,
) -> Response:
    """Image bytes for the uploader or the approving manager (others 404). Not cached by browsers."""
    content, mime_type = evidence_service.get_file(db, user, evidence_id)
    return Response(content=content, media_type=mime_type, headers={"Cache-Control": "private, no-store"})


@router.post("/{evidence_id}/verify", response_model=ReceiptVerificationOut)
def verify_receipt(
    evidence_id: UUID,
    body: ReceiptVerifyRequest,
    employee: Annotated[CurrentUser, Depends(require_employee)],
    db: Db,
) -> ReceiptVerificationOut:
    """[M3] Receipt check shown under the photo while the employee fills the line.
    The photo is read by AI once (first call can take a few seconds); later calls with a changed
    amount, date or category only re-run the plain-code comparison. Owner only (others 404)."""
    return receipt_service.verify_for_form(db, employee, evidence_id, body)


@router.api_route("/{evidence_id}", methods=["PUT", "PATCH", "DELETE"], include_in_schema=False)
def evidence_is_read_only(evidence_id: UUID) -> None:
    """There is no edit or delete of evidence (spec: PUT/PATCH/DELETE return 405)."""
    raise AppError(ErrorCode.METHOD_NOT_ALLOWED, 405, "Receipt photos cannot be edited or deleted.")

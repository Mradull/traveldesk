"""
Receipt photos: JPEG/PNG/WEBP by file signature, max 5 MB, sha256, EVD code, bytes in evidence_files,
streaming for the uploader or approving manager.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0

Spec references: Business rules > Hard validation (receipt photo file); Transactions (evidence upload
is one transaction); US-10; [POL-7.1], [POL-7.5]. The file type is decided from the first bytes of
the file (its "signature"), never from the file name or the browser's Content-Type, so a PDF renamed
to .jpg is refused with 415.
"""

from hashlib import sha256
from pathlib import PurePath
from typing import BinaryIO
from uuid import UUID

from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.errors import AppError
from app.repositories import evidence_repo
from app.schemas import CurrentUser, ErrorCode, EvidenceUploadOut, Role


def detect_image_type(content: bytes) -> str | None:
    """Return the MIME type from the file signature, or None if it is not JPEG/PNG/WEBP."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _safe_filename(filename: str | None) -> str:
    """Keep only the file's own name (no folders), at most 255 characters; shown in the UI only."""
    name = PurePath((filename or "").replace("\\", "/")).name.strip()
    return name[:255] or "receipt"


def upload(db: Connection, employee: CurrentUser, filename: str | None, stream: BinaryIO) -> EvidenceUploadOut:
    """US-10: store one receipt photo (metadata + bytes in one transaction) and return its EVD code."""
    settings = get_settings()
    max_bytes = settings.evidence_max_bytes
    content = stream.read(max_bytes + 1)            # one byte more than allowed tells us it is too big
    if len(content) > max_bytes:
        raise AppError(
            ErrorCode.EVIDENCE_TOO_LARGE,
            413,
            f"The photo is larger than {max_bytes // (1024 * 1024)} MB.",
        )
    allowed = {mime.strip() for mime in settings.evidence_allowed_mime_types.split(",") if mime.strip()}
    mime_type = detect_image_type(content)
    if mime_type is None or mime_type not in allowed:
        raise AppError(
            ErrorCode.EVIDENCE_INVALID_FILE,
            415,
            "Upload a real JPEG, PNG or WEBP photo of the receipt.",
        )
    row = evidence_repo.insert(
        db,
        employee.employee_id,
        _safe_filename(filename),
        mime_type,
        content,
        sha256(content).hexdigest(),
    )
    result = EvidenceUploadOut(**row)
    db.commit()
    return result


def get_file(db: Connection, user: CurrentUser, evidence_id: UUID) -> tuple[bytes, str]:
    """Photo bytes for the uploader or the uploader's line manager; everyone else 404 [POL-7.5]."""
    row = evidence_repo.get_file(db, evidence_id)
    allowed = row is not None and (
        user.employee_id == row["employee_id"]
        or (user.role == Role.MANAGER and row["owner_manager_id"] == user.employee_id)
    )
    if not allowed:
        raise AppError(ErrorCode.EVIDENCE_NOT_FOUND, 404, "Receipt photo not found.")
    return bytes(row["content"]), row["mime_type"]


def delete_unattached(db: Connection) -> int:
    """Scheduler: remove uploads never attached to a line after EVIDENCE_UNATTACHED_RETENTION_HOURS."""
    return evidence_repo.delete_unattached_older_than(db, get_settings().evidence_unattached_retention_hours)

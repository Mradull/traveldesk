"""
JPEG/PNG/WEBP accepted; renamed PDF 415; > 5 MB 413; view by owner and approving manager; others 404.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy
"""

import hashlib

import pytest
from sqlalchemy import text

from app.services import jobs

SAMPLES = {
    "image/jpeg": ("receipt.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00jpeg-body"),
    "image/png": ("receipt.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRpng-body"),
    "image/webp": ("receipt.webp", b"RIFF\x24\x00\x00\x00WEBPVP8 webp-body"),
}


def upload(api_client, headers: dict, filename: str, content: bytes, content_type: str = "image/jpeg"):
    return api_client.post("/api/v1/evidence", headers=headers, files={"file": (filename, content, content_type)})


@pytest.mark.parametrize("mime_type", SAMPLES)
def test_jpeg_png_webp_are_accepted(api_client, team, auth_header, mime_type: str) -> None:
    filename, content = SAMPLES[mime_type]
    response = upload(api_client, auth_header(team["employee"]), filename, content, mime_type)
    assert response.status_code == 201
    body = response.json()
    assert body["evidence_code"].startswith("EVD-") and body["mime_type"] == mime_type
    assert body["size_bytes"] == len(content) and body["sha256"] == hashlib.sha256(content).hexdigest()
    assert body["original_filename"] == filename


def test_renamed_pdf_is_415(api_client, team, auth_header) -> None:
    """The signature is checked, not the name or the browser's content type [POL-7.1]."""
    response = upload(api_client, auth_header(team["employee"]), "receipt.jpg", b"%PDF-1.7 fake", "image/jpeg")
    assert response.status_code == 415 and response.json()["error"]["code"] == "EVIDENCE_INVALID_FILE"


def test_empty_file_is_415(api_client, team, auth_header) -> None:
    assert upload(api_client, auth_header(team["employee"]), "empty.jpg", b"").status_code == 415


def test_over_5_mb_is_413(api_client, team, auth_header) -> None:
    too_big = b"\xff\xd8\xff\xe0" + b"0" * (5 * 1024 * 1024)
    response = upload(api_client, auth_header(team["employee"]), "big.jpg", too_big)
    assert response.status_code == 413 and response.json()["error"]["code"] == "EVIDENCE_TOO_LARGE"


def test_exactly_5_mb_is_accepted(api_client, team, auth_header) -> None:
    exact = b"\xff\xd8\xff\xe0" + b"0" * (5 * 1024 * 1024 - 4)
    assert upload(api_client, auth_header(team["employee"]), "max.jpg", exact).status_code == 201


def test_managers_cannot_upload(api_client, team, auth_header) -> None:
    filename, content = SAMPLES["image/jpeg"]
    assert upload(api_client, auth_header(team["manager"]), filename, content).status_code == 403


def test_view_by_owner_and_approving_manager_only(api_client, team, auth_header) -> None:
    filename, content = SAMPLES["image/png"]
    evidence_id = upload(api_client, auth_header(team["employee"]), filename, content, "image/png").json()["evidence_id"]
    url = f"/api/v1/evidence/{evidence_id}/file"

    for viewer in ("employee", "manager"):
        response = api_client.get(url, headers=auth_header(team[viewer]))
        assert response.status_code == 200
        assert response.content == content and response.headers["content-type"] == "image/png"
    for stranger in ("colleague", "other_manager"):
        response = api_client.get(url, headers=auth_header(team[stranger]))
        assert response.status_code == 404 and response.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_evidence_cannot_be_edited_or_deleted(api_client, team, auth_header) -> None:
    filename, content = SAMPLES["image/jpeg"]
    evidence_id = upload(api_client, auth_header(team["employee"]), filename, content).json()["evidence_id"]
    for method in ("PUT", "PATCH", "DELETE"):
        response = api_client.request(method, f"/api/v1/evidence/{evidence_id}", headers=auth_header(team["employee"]))
        assert response.status_code == 405 and response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_cleanup_job_deletes_only_old_unattached_uploads(team, make_evidence, test_engine) -> None:
    owner = team["employee"]["employee_id"]
    old = make_evidence(owner, hours_ago=25)
    recent = make_evidence(owner, hours_ago=1)
    with test_engine.begin() as db:
        assert jobs.delete_unattached_evidence(db) == 1
    with test_engine.connect() as db:
        left = {str(r[0]) for r in db.execute(text("SELECT evidence_id FROM expense_evidence"))}
        files = db.execute(text("SELECT count(*) FROM evidence_files")).scalar_one()
    assert left == {recent} and old not in left and files == 1             # bytes removed by CASCADE

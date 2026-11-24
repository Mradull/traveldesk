import { api } from "./client";
import { API_BASE_URL, STORAGE_KEYS, USE_MOCKS } from "../utils/constants";
import { mockEvidenceUrl, mockUploadEvidence, mockVerifyReceipt } from "./mocks";

/** POST /evidence (multipart, field "file") -> { evidence_id, evidence_code, ... } */
export function uploadEvidence(file) {
  if (USE_MOCKS) return mockUploadEvidence(file);
  const form = new FormData();
  form.append("file", file);
  return api.upload("/evidence", form);
}

/**
 * GET /evidence/{id}/file needs the Authorization header, so an <img src> can't call it.
 * We fetch the bytes and return a blob URL. Call URL.revokeObjectURL() when done.
 */
export async function getEvidenceObjectUrl(evidenceId) {
  if (USE_MOCKS) return mockEvidenceUrl(evidenceId);
  const token = sessionStorage.getItem(STORAGE_KEYS.TOKEN);
  const res = await fetch(`${API_BASE_URL}/evidence/${evidenceId}/file`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Couldn't load the receipt photo.");
  return URL.createObjectURL(await res.blob());
}

/**
 * POST /evidence/{id}/verify  body: { trip_id, expense_type, amount, expense_date } (any may be null)
 * -> { verdict, checks, reading, over_threshold, outcome, enabled }
 * The first call reads the receipt with AI (a few seconds); later calls only re-compare.
 */
export function verifyReceipt(evidenceId, body) {
  if (USE_MOCKS) return mockVerifyReceipt(evidenceId, body);
  return api.post(`/evidence/${evidenceId}/verify`, body);
}

// =====================================================================
// The single place every request goes through.
// Adds the JWT, reads the error envelope, signs the user out on 401.
// =====================================================================
import { API_BASE_URL, ERROR_MESSAGES, STORAGE_KEYS } from "../utils/constants";

/** Error thrown for every failed request; carries the backend's error envelope fields. */
export class ApiError extends Error {
  constructor({ status, code, message, details = null, requestId = null }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;       // field errors for VALIDATION_ERROR
    this.requestId = requestId;   // matches the backend log line
  }
}

// AuthContext registers a function here so an expired token signs the user out everywhere
let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

const SESSION_ERRORS = ["TOKEN_EXPIRED", "INVALID_TOKEN", "UNAUTHENTICATED"];

export async function request(path, { method = "GET", body, formData, auth = true, signal } = {}) {
  const headers = {};
  const token = sessionStorage.getItem(STORAGE_KEYS.TOKEN);
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (formData) {
    payload = formData; // the browser sets the multipart boundary itself
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { method, headers, body: payload, signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError({ status: 0, code: "NETWORK_ERROR", message: ERROR_MESSAGES.NETWORK_ERROR });
  }

  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);

  if (!res.ok) {
    const e = data?.error ?? {};
    const code = e.code ?? "INTERNAL_ERROR";
    const err = new ApiError({
      status: res.status,
      code,
      message: ERROR_MESSAGES[code] ?? e.message ?? ERROR_MESSAGES.INTERNAL_ERROR,
      details: e.details ?? null,
      requestId: e.request_id ?? null,
    });
    if (auth && SESSION_ERRORS.includes(code) && onUnauthorized) onUnauthorized(err);
    throw err;
  }
  return data;
}

export const api = {
  get: (path, opts) => request(path, { ...opts, method: "GET" }),
  post: (path, body, opts) => request(path, { ...opts, method: "POST", body }),
  put: (path, body, opts) => request(path, { ...opts, method: "PUT", body }),
  del: (path, opts) => request(path, { ...opts, method: "DELETE" }),
  upload: (path, formData, opts) => request(path, { ...opts, method: "POST", formData }),
};

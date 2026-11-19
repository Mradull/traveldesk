"""
AppError(code, http_status, safe_message, retryable) and handlers that return the error envelope
and write error_logs in their own transaction (JSON-log fallback if that write fails).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

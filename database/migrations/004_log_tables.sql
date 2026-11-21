-- error_logs (Joyal); ai_call_logs, rag_call_logs, weather_tool_logs (Piyush).
-- Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0
-- Runs after 003: Piyush's log tables reference chat_sessions / chat_conversations.

-- =============================================================================
-- [J] Joyal (M1): error_logs - central error storage for every component.
-- Columns follow Agile Spec v2.0 > Table definitions > error_logs and schemas.ErrorLogRecord.
-- No foreign keys on purpose: the spec links error_logs "by ids", and an error must
-- always be storable even when the record it mentions does not exist.
-- Never stored here: passwords, tokens, Authorization headers, API keys.
-- =============================================================================
CREATE TABLE error_logs (
    error_id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity TEXT NOT NULL
        CHECK (severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    source_component TEXT NOT NULL,          -- e.g. 'tickets.router', 'chat.weather_tool'
    category TEXT NOT NULL
        CHECK (
            category IN (
                'VALIDATION', 'AUTHENTICATION', 'AUTHORIZATION', 'BUSINESS_RULE',
                'API', 'DATABASE', 'RAG', 'LLM', 'WEATHER', 'TIMEOUT', 'PARSING',
                'RATE_LIMIT', 'UNEXPECTED'
            )
        ),
    error_code TEXT NOT NULL,                -- stable code from schemas.ErrorCode
    safe_message TEXT NOT NULL,              -- what the user saw
    internal_message TEXT,                   -- diagnostic text, no secrets
    http_status INT,
    retryable BOOLEAN NOT NULL DEFAULT FALSE,
    request_id TEXT,
    correlation_id TEXT,
    tool_call_id TEXT,
    employee_id INT,                         -- NULL when unknown (e.g. before login)
    session_id UUID,
    conversation_id UUID,
    message_id BIGINT,
    context JSONB,                           -- sanitized key facts
    stack_trace TEXT                         -- 5xx only
);

-- =============================================================================
-- [P] Piyush (M2): ai_call_logs, rag_call_logs, weather_tool_logs.
-- Copied exactly from Piyush's file (Google Drive, 2026-11-20).
-- =============================================================================

-- [P] One row per LLM call. Prompts are never stored, only prompt_version.
CREATE TABLE IF NOT EXISTS ai_call_logs (
    log_id             BIGSERIAL   PRIMARY KEY,
    feature            TEXT        NOT NULL CHECK (feature IN ('CHAT', 'SUMMARY')),
    provider           TEXT        NOT NULL,
    model_name         TEXT        NOT NULL,
    prompt_version     TEXT        NOT NULL,
    status             TEXT        NOT NULL CHECK (status IN ('SUCCESS', 'TIMEOUT', 'RATE_LIMITED',
                                                              'AUTH_ERROR', 'INVALID_OUTPUT', 'ERROR')),
    latency_ms         INT         NOT NULL,
    prompt_tokens      INT,
    completion_tokens  INT,
    error_code         TEXT,
    session_id         UUID        REFERENCES chat_sessions(session_id) ON DELETE RESTRICT,
    conversation_id    UUID        REFERENCES chat_conversations(conversation_id) ON DELETE RESTRICT,
    correlation_id     TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- [P] One row per policy retrieval (search_expense_policy).
CREATE TABLE IF NOT EXISTS rag_call_logs (
    rag_call_id        BIGSERIAL   PRIMARY KEY,
    session_id         UUID        REFERENCES chat_sessions(session_id) ON DELETE RESTRICT,
    conversation_id    UUID        REFERENCES chat_conversations(conversation_id) ON DELETE RESTRICT,
    correlation_id     TEXT,
    query_text         TEXT        NOT NULL CHECK (length(query_text) <= 300),   -- masked
    top_k              INT         NOT NULL,
    retrieved_ref_ids  TEXT[]      NOT NULL DEFAULT '{}',
    retrieval_scores   REAL[]      NOT NULL DEFAULT '{}',
    citations_used     TEXT[]      NOT NULL DEFAULT '{}',   -- after output validation
    status             TEXT        NOT NULL CHECK (status IN ('SUCCESS', 'NO_MATCH', 'FAILED')),
    error_code         TEXT,
    latency_ms         INT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- [P] One row per get_weather_forecast call. No trip or business link on purpose.
CREATE TABLE IF NOT EXISTS weather_tool_logs (
    weather_call_id    BIGSERIAL   PRIMARY KEY,
    session_id         UUID        REFERENCES chat_sessions(session_id) ON DELETE RESTRICT,
    conversation_id    UUID        REFERENCES chat_conversations(conversation_id) ON DELETE RESTRICT,
    correlation_id     TEXT,
    tool_call_id       TEXT,
    destination_query  TEXT,                       -- sanitized input as the employee typed it
    start_date         DATE,                       -- NULL if missing
    end_date           DATE,
    resolved_location  TEXT,
    provider           TEXT        NOT NULL DEFAULT 'Open-Meteo',
    http_status        INT,
    latency_ms         INT,
    result_status      TEXT        CHECK (result_status IN ('AVAILABLE', 'PARTIAL', 'FORECAST_OUT_OF_RANGE',
                                                            'LOCATION_NOT_FOUND', 'LOCATION_AMBIGUOUS', 'ERROR')),
    error_code         TEXT,
    cache_hit          BOOLEAN     NOT NULL DEFAULT false,
    retrieved_at       TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

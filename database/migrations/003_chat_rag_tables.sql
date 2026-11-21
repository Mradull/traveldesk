-- =============================================================================
-- 003_chat_rag_tables.sql  (owner: Piyush, M2)            Agile Spec v2.0
-- Vera's tables: chat_sessions, chat_conversations, chat_messages, policy_chunks.
-- None of them references trips, tickets, expenses or evidence: employee_id is
-- used ONLY to own a chat session (Vera isolation).
-- Runs after 001 (needs employees). Applied once by scripts/init_db.py.
-- =============================================================================

-- One complete Vera chat. An employee has many sessions over time, at most one ACTIVE.
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id           INT         NOT NULL REFERENCES employees(employee_id) ON DELETE RESTRICT,
    status                TEXT        NOT NULL DEFAULT 'ACTIVE'
                                      CHECK (status IN ('ACTIVE', 'CLOSED', 'EXPIRED')),
    close_reason          TEXT        CHECK (close_reason IN ('USER_CLOSED', 'IDLE_TIMEOUT', 'REPLACED')),
    summary               TEXT,                       -- rolling summary of THIS session's older turns
    summarized_upto_turn  INT         NOT NULL DEFAULT 0,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at      TIMESTAMPTZ NOT NULL DEFAULT now(),   -- idle check uses this
    closed_at             TIMESTAMPTZ,
    -- an ended session always says why and when it ended
    CHECK ((status = 'ACTIVE' AND close_reason IS NULL AND closed_at IS NULL)
        OR (status <> 'ACTIVE' AND close_reason IS NOT NULL AND closed_at IS NOT NULL))
);

-- "At most one ACTIVE session per employee": opening Vera in a second tab replaces the first.
CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_sessions_one_active
    ON chat_sessions (employee_id) WHERE status = 'ACTIVE';

-- One turn = one employee message and everything Vera did for it.
-- intent / status are NULL only while the turn is still being processed.
CREATE TABLE IF NOT EXISTS chat_conversations (
    conversation_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id         UUID        NOT NULL REFERENCES chat_sessions(session_id) ON DELETE RESTRICT,
    turn_number        INT         NOT NULL CHECK (turn_number >= 1),
    intent             TEXT        CHECK (intent IN ('POLICY', 'WEATHER', 'POLICY_AND_WEATHER',
                                                     'GREETING', 'OUT_OF_SCOPE')),
    status             TEXT        CHECK (status IN ('COMPLETED', 'PARTIAL', 'BLOCKED', 'FAILED')),
    guardrail_status   TEXT        CHECK (guardrail_status IN ('PASSED', 'INPUT_BLOCKED',
                                                               'INPUT_REDACTED', 'OUTPUT_REWRITTEN')),
    guardrail_reasons  TEXT[]      NOT NULL DEFAULT '{}',   -- e.g. {pii:phone}
    error_code         TEXT,                                -- NULL unless PARTIAL / FAILED
    model_name         TEXT,
    latency_ms         INT,
    request_id         TEXT,
    correlation_id     TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, turn_number)
);

-- Ordered events of a turn: human_message -> (ai_tool_call -> tool_response)* -> ai_response.
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id       BIGSERIAL   PRIMARY KEY,
    session_id       UUID        NOT NULL REFERENCES chat_sessions(session_id) ON DELETE RESTRICT,
    conversation_id  UUID        NOT NULL REFERENCES chat_conversations(conversation_id) ON DELETE RESTRICT,
    sequence_no      INT         NOT NULL CHECK (sequence_no >= 1),
    message_type     TEXT        NOT NULL CHECK (message_type IN ('human_message', 'ai_tool_call',
                                                                  'tool_response', 'ai_response')),
    content          TEXT        NOT NULL,          -- masked text, or tool JSON
    tool_name        TEXT        CHECK (tool_name IN ('search_expense_policy', 'get_weather_forecast')),
    tool_call_id     TEXT,                          -- links an ai_tool_call to its tool_response
    tool_args        JSONB,                         -- sanitized arguments
    metadata         JSONB,                         -- citations, weather card, latency, error code
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, sequence_no)
);

-- RAG store built from backend/data/expense_policy.txt by scripts/ingest_policy.py.
-- No link to any business table. Vectors are plain REAL[] (no pgvector extension needed);
-- cosine similarity is computed in Python over the cached vectors.
CREATE TABLE IF NOT EXISTS policy_chunks (
    chunk_id       SERIAL  PRIMARY KEY,
    ref_id         TEXT    NOT NULL,                -- POL-6.2 / GUIDE-6 / FAQ-1 (the citation)
    section_title  TEXT    NOT NULL,                -- rule title, e.g. "Review thresholds per expense line"
    chunk_index    INT     NOT NULL DEFAULT 0,      -- 0 unless a long rule was split
    content        TEXT    NOT NULL,                -- section header + rule id/title + rule text
    embedding      REAL[]  NOT NULL CHECK (array_length(embedding, 1) = 384),
    source_file    TEXT    NOT NULL,
    content_hash   TEXT    NOT NULL UNIQUE          -- makes ingestion idempotent
);

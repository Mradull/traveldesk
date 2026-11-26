--
-- PostgreSQL database dump
--

\restrict zBeoxNOeJ5oW7l9lPO8CExBMFBFbGpkPFpVbEXsBjg0Y8zvV78zsj8rVq3Keq1F

-- Dumped from database version 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: block_change_of_approval_history(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.block_change_of_approval_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = 'P0001',
        MESSAGE = 'ALREADY_DECIDED',
        DETAIL = format('Rows in %s are permanent decision history and cannot be changed or deleted.', TG_TABLE_NAME);
END;
$$;


--
-- Name: block_change_of_decided_evidence(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.block_change_of_decided_evidence() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM expenses AS x
        JOIN expense_tickets AS k ON k.ticket_id = x.ticket_id
        WHERE x.evidence_id = OLD.evidence_id
          AND k.status <> 'PENDING'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'TICKET_READ_ONLY',
            DETAIL = 'This receipt photo belongs to a decided ticket and cannot be changed or deleted.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: block_change_of_decided_expense(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.block_change_of_decided_expense() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    ticket_status TEXT;
BEGIN
    SELECT status INTO ticket_status
    FROM expense_tickets
    WHERE ticket_id = OLD.ticket_id;

    IF ticket_status <> 'PENDING' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'TICKET_READ_ONLY',
            DETAIL = format('Expense %s belongs to a decided ticket and cannot be changed or deleted.', OLD.expense_code);
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: block_change_of_decided_ticket(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.block_change_of_decided_ticket() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF OLD.status <> 'PENDING' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'TICKET_READ_ONLY',
            DETAIL = format('Ticket %s is %s and cannot be changed or deleted.', OLD.ticket_code, OLD.status);
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: check_expense_date_after_trip_created(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_expense_date_after_trip_created() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    trip_created_on DATE;
BEGIN
    SELECT created_on INTO trip_created_on
    FROM travel_requests
    WHERE trip_id = NEW.trip_id;

    IF NEW.expense_date < trip_created_on THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'EXPENSE_DATE_BEFORE_TRIP_CREATED',
            DETAIL = format('Expense date %s is before the trip was created on %s.', NEW.expense_date, trip_created_on);
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: check_ticket_trip_is_active(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_ticket_trip_is_active() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM travel_requests
        WHERE trip_id = NEW.trip_id
          AND approval_status = 'APPROVED'
          AND trip_state = 'ACTIVE'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'TRIP_NOT_ACTIVE',
            DETAIL = 'Tickets can only be raised on Approved - Active trips.';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: set_travel_request_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_travel_request_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ai_call_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_call_logs (
    log_id bigint NOT NULL,
    feature text NOT NULL,
    provider text NOT NULL,
    model_name text NOT NULL,
    prompt_version text NOT NULL,
    status text NOT NULL,
    latency_ms integer NOT NULL,
    prompt_tokens integer,
    completion_tokens integer,
    error_code text,
    session_id uuid,
    conversation_id uuid,
    correlation_id text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ai_call_logs_feature_check CHECK ((feature = ANY (ARRAY['CHAT'::text, 'SUMMARY'::text, 'RECEIPT'::text]))),
    CONSTRAINT ai_call_logs_status_check CHECK ((status = ANY (ARRAY['SUCCESS'::text, 'TIMEOUT'::text, 'RATE_LIMITED'::text, 'AUTH_ERROR'::text, 'INVALID_OUTPUT'::text, 'ERROR'::text])))
);


--
-- Name: ai_call_logs_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_call_logs_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_call_logs_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_call_logs_log_id_seq OWNED BY public.ai_call_logs.log_id;


--
-- Name: chat_conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_conversations (
    conversation_id uuid DEFAULT gen_random_uuid() NOT NULL,
    session_id uuid NOT NULL,
    turn_number integer NOT NULL,
    intent text,
    status text,
    guardrail_status text,
    guardrail_reasons text[] DEFAULT '{}'::text[] NOT NULL,
    error_code text,
    model_name text,
    latency_ms integer,
    request_id text,
    correlation_id text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chat_conversations_guardrail_status_check CHECK ((guardrail_status = ANY (ARRAY['PASSED'::text, 'INPUT_BLOCKED'::text, 'INPUT_REDACTED'::text, 'OUTPUT_REWRITTEN'::text]))),
    CONSTRAINT chat_conversations_intent_check CHECK ((intent = ANY (ARRAY['POLICY'::text, 'WEATHER'::text, 'POLICY_AND_WEATHER'::text, 'GREETING'::text, 'OUT_OF_SCOPE'::text]))),
    CONSTRAINT chat_conversations_status_check CHECK ((status = ANY (ARRAY['COMPLETED'::text, 'PARTIAL'::text, 'BLOCKED'::text, 'FAILED'::text]))),
    CONSTRAINT chat_conversations_turn_number_check CHECK ((turn_number >= 1))
);


--
-- Name: chat_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_messages (
    message_id bigint NOT NULL,
    session_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    sequence_no integer NOT NULL,
    message_type text NOT NULL,
    content text NOT NULL,
    tool_name text,
    tool_call_id text,
    tool_args jsonb,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chat_messages_message_type_check CHECK ((message_type = ANY (ARRAY['human_message'::text, 'ai_tool_call'::text, 'tool_response'::text, 'ai_response'::text]))),
    CONSTRAINT chat_messages_sequence_no_check CHECK ((sequence_no >= 1)),
    CONSTRAINT chat_messages_tool_name_check CHECK ((tool_name = ANY (ARRAY['search_expense_policy'::text, 'get_weather_forecast'::text])))
);


--
-- Name: chat_messages_message_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chat_messages_message_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chat_messages_message_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chat_messages_message_id_seq OWNED BY public.chat_messages.message_id;


--
-- Name: chat_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_sessions (
    session_id uuid DEFAULT gen_random_uuid() NOT NULL,
    employee_id integer NOT NULL,
    status text DEFAULT 'ACTIVE'::text NOT NULL,
    close_reason text,
    summary text,
    summarized_upto_turn integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    last_activity_at timestamp with time zone DEFAULT now() NOT NULL,
    closed_at timestamp with time zone,
    CONSTRAINT chat_sessions_check CHECK ((((status = 'ACTIVE'::text) AND (close_reason IS NULL) AND (closed_at IS NULL)) OR ((status <> 'ACTIVE'::text) AND (close_reason IS NOT NULL) AND (closed_at IS NOT NULL)))),
    CONSTRAINT chat_sessions_close_reason_check CHECK ((close_reason = ANY (ARRAY['USER_CLOSED'::text, 'IDLE_TIMEOUT'::text, 'REPLACED'::text]))),
    CONSTRAINT chat_sessions_status_check CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'CLOSED'::text, 'EXPIRED'::text])))
);


--
-- Name: employees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employees (
    employee_id integer NOT NULL,
    full_name text NOT NULL,
    email text NOT NULL,
    password_hash text NOT NULL,
    department text NOT NULL,
    role text NOT NULL,
    manager_id integer,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_employees_email_lowercase CHECK ((email = lower(email))),
    CONSTRAINT ck_employees_manager_not_self CHECK (((manager_id IS NULL) OR (manager_id <> employee_id))),
    CONSTRAINT ck_managers_have_no_manager CHECK (((role <> 'MANAGER'::text) OR (manager_id IS NULL))),
    CONSTRAINT employees_role_check CHECK ((role = ANY (ARRAY['EMPLOYEE'::text, 'MANAGER'::text])))
);


--
-- Name: employees_employee_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.employees_employee_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: employees_employee_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.employees_employee_id_seq OWNED BY public.employees.employee_id;


--
-- Name: error_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.error_logs (
    error_id bigint NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    severity text NOT NULL,
    source_component text NOT NULL,
    category text NOT NULL,
    error_code text NOT NULL,
    safe_message text NOT NULL,
    internal_message text,
    http_status integer,
    retryable boolean DEFAULT false NOT NULL,
    request_id text,
    correlation_id text,
    tool_call_id text,
    employee_id integer,
    session_id uuid,
    conversation_id uuid,
    message_id bigint,
    context jsonb,
    stack_trace text,
    CONSTRAINT error_logs_category_check CHECK ((category = ANY (ARRAY['VALIDATION'::text, 'AUTHENTICATION'::text, 'AUTHORIZATION'::text, 'BUSINESS_RULE'::text, 'API'::text, 'DATABASE'::text, 'RAG'::text, 'LLM'::text, 'WEATHER'::text, 'TIMEOUT'::text, 'PARSING'::text, 'RATE_LIMIT'::text, 'UNEXPECTED'::text]))),
    CONSTRAINT error_logs_severity_check CHECK ((severity = ANY (ARRAY['INFO'::text, 'WARNING'::text, 'ERROR'::text, 'CRITICAL'::text])))
);


--
-- Name: error_logs_error_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.error_logs_error_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: error_logs_error_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.error_logs_error_id_seq OWNED BY public.error_logs.error_id;


--
-- Name: evidence_code_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.evidence_code_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: evidence_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evidence_files (
    evidence_id uuid NOT NULL,
    content bytea NOT NULL
);


--
-- Name: expense_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.expense_evidence (
    evidence_id uuid DEFAULT gen_random_uuid() NOT NULL,
    evidence_code text DEFAULT ('EVD-'::text || lpad((nextval('public.evidence_code_seq'::regclass))::text, 5, '0'::text)) NOT NULL,
    employee_id integer NOT NULL,
    original_filename text NOT NULL,
    mime_type text NOT NULL,
    size_bytes integer NOT NULL,
    sha256 character(64) NOT NULL,
    uploaded_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT expense_evidence_mime_type_check CHECK ((mime_type = ANY (ARRAY['image/jpeg'::text, 'image/png'::text, 'image/webp'::text]))),
    CONSTRAINT expense_evidence_sha256_check CHECK ((length(sha256) = 64)),
    CONSTRAINT expense_evidence_size_bytes_check CHECK (((size_bytes >= 1) AND (size_bytes <= 5242880)))
);


--
-- Name: expense_tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.expense_tickets (
    ticket_id integer NOT NULL,
    ticket_code text GENERATED ALWAYS AS (('TKT-'::text || lpad((ticket_id)::text, 5, '0'::text))) STORED,
    trip_id integer NOT NULL,
    employee_id integer NOT NULL,
    replacement_of_ticket_id integer,
    status text NOT NULL,
    routing text NOT NULL,
    line_count integer NOT NULL,
    flag_count integer NOT NULL,
    total_amount numeric(12,2) NOT NULL,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    decided_at timestamp with time zone,
    CONSTRAINT ck_expense_tickets_pending_decision_time CHECK (((status = 'PENDING'::text) = (decided_at IS NULL))),
    CONSTRAINT ck_expense_tickets_routing_status CHECK ((((status = 'AUTO_APPROVED'::text) AND (routing = 'AUTO'::text)) OR ((status = 'REJECTED'::text) AND (routing = 'AI_CHECK'::text)) OR ((status <> 'AUTO_APPROVED'::text) AND (routing = 'MANAGER'::text)))),
    CONSTRAINT expense_tickets_flag_count_check CHECK ((flag_count >= 0)),
    CONSTRAINT expense_tickets_line_count_check CHECK (((line_count >= 1) AND (line_count <= 20))),
    CONSTRAINT expense_tickets_routing_check CHECK ((routing = ANY (ARRAY['AUTO'::text, 'MANAGER'::text, 'AI_CHECK'::text]))),
    CONSTRAINT expense_tickets_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'AUTO_APPROVED'::text, 'APPROVED'::text, 'REJECTED'::text]))),
    CONSTRAINT expense_tickets_total_amount_check CHECK ((total_amount > (0)::numeric))
);


--
-- Name: expense_tickets_ticket_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.expense_tickets_ticket_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: expense_tickets_ticket_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.expense_tickets_ticket_id_seq OWNED BY public.expense_tickets.ticket_id;


--
-- Name: expenses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.expenses (
    expense_id integer NOT NULL,
    expense_code text GENERATED ALWAYS AS (('EXP-'::text || lpad((expense_id)::text, 5, '0'::text))) STORED,
    ticket_id integer NOT NULL,
    trip_id integer NOT NULL,
    evidence_id uuid NOT NULL,
    expense_type text NOT NULL,
    amount numeric(12,2) NOT NULL,
    currency character(3) DEFAULT 'INR'::bpchar NOT NULL,
    expense_date date NOT NULL,
    description text NOT NULL,
    invoice_number text,
    status text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    receipt_verdict text,
    receipt_checks jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT expenses_amount_check CHECK (((amount > (0)::numeric) AND (amount <= (200000)::numeric))),
    CONSTRAINT expenses_currency_check CHECK ((currency = 'INR'::bpchar)),
    CONSTRAINT expenses_expense_type_check CHECK ((expense_type = ANY (ARRAY['AIRFARE'::text, 'LODGING'::text, 'MEALS'::text, 'GROUND_TRANSPORT'::text, 'INCIDENTALS'::text]))),
    CONSTRAINT expenses_receipt_verdict_check CHECK ((receipt_verdict = ANY (ARRAY['VALID'::text, 'INVALID'::text, 'NOT_VERIFIED'::text]))),
    CONSTRAINT expenses_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'AUTO_APPROVED'::text, 'APPROVED'::text, 'REJECTED'::text])))
);


--
-- Name: expenses_expense_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.expenses_expense_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: expenses_expense_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.expenses_expense_id_seq OWNED BY public.expenses.expense_id;


--
-- Name: policy_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.policy_chunks (
    chunk_id integer NOT NULL,
    ref_id text NOT NULL,
    section_title text NOT NULL,
    chunk_index integer DEFAULT 0 NOT NULL,
    content text NOT NULL,
    embedding real[] NOT NULL,
    source_file text NOT NULL,
    content_hash text NOT NULL,
    CONSTRAINT policy_chunks_embedding_check CHECK ((array_length(embedding, 1) = 384))
);


--
-- Name: policy_chunks_chunk_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.policy_chunks_chunk_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: policy_chunks_chunk_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.policy_chunks_chunk_id_seq OWNED BY public.policy_chunks.chunk_id;


--
-- Name: policy_flags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.policy_flags (
    flag_id integer NOT NULL,
    expense_id integer NOT NULL,
    rule_code text NOT NULL,
    message text NOT NULL,
    policy_ref text NOT NULL,
    threshold_amount numeric(12,2),
    rules_version text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_policy_flags_threshold CHECK (((rule_code = 'OVER_THRESHOLD'::text) = (threshold_amount IS NOT NULL))),
    CONSTRAINT policy_flags_rule_code_check CHECK ((rule_code = ANY (ARRAY['OVER_THRESHOLD'::text, 'DUPLICATE_RECEIPT'::text, 'RECEIPT_MISMATCH'::text, 'RECEIPT_NOT_VERIFIED'::text])))
);


--
-- Name: policy_flags_flag_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.policy_flags_flag_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: policy_flags_flag_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.policy_flags_flag_id_seq OWNED BY public.policy_flags.flag_id;


--
-- Name: rag_call_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_call_logs (
    rag_call_id bigint NOT NULL,
    session_id uuid,
    conversation_id uuid,
    correlation_id text,
    query_text text NOT NULL,
    top_k integer NOT NULL,
    retrieved_ref_ids text[] DEFAULT '{}'::text[] NOT NULL,
    retrieval_scores real[] DEFAULT '{}'::real[] NOT NULL,
    citations_used text[] DEFAULT '{}'::text[] NOT NULL,
    status text NOT NULL,
    error_code text,
    latency_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT rag_call_logs_query_text_check CHECK ((length(query_text) <= 300)),
    CONSTRAINT rag_call_logs_status_check CHECK ((status = ANY (ARRAY['SUCCESS'::text, 'NO_MATCH'::text, 'FAILED'::text])))
);


--
-- Name: rag_call_logs_rag_call_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_call_logs_rag_call_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_call_logs_rag_call_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_call_logs_rag_call_id_seq OWNED BY public.rag_call_logs.rag_call_id;


--
-- Name: receipt_checks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.receipt_checks (
    evidence_id uuid NOT NULL,
    status text NOT NULL,
    is_receipt boolean,
    total_amount numeric(12,2),
    currency text,
    receipt_date date,
    merchant text,
    city text,
    from_place text,
    to_place text,
    summary text,
    ai_generated_score real,
    error_code text,
    model_name text,
    analyzed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT receipt_checks_ai_generated_score_check CHECK (((ai_generated_score IS NULL) OR ((ai_generated_score >= (0)::double precision) AND (ai_generated_score <= (1)::double precision)))),
    CONSTRAINT receipt_checks_status_check CHECK ((status = ANY (ARRAY['READ'::text, 'UNREADABLE'::text, 'ERROR'::text])))
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ticket_approvals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ticket_approvals (
    approval_id integer NOT NULL,
    ticket_id integer NOT NULL,
    reviewer_type text NOT NULL,
    reviewer_id integer,
    decision text NOT NULL,
    rejection_reason text,
    review_comment text,
    decided_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_ticket_approvals_rejection_comment CHECK (((decision <> 'REJECTED'::text) OR (length(TRIM(BOTH FROM COALESCE(review_comment, ''::text))) >= 10))),
    CONSTRAINT ck_ticket_approvals_rejection_reason CHECK (((decision = 'REJECTED'::text) = (rejection_reason IS NOT NULL))),
    CONSTRAINT ck_ticket_approvals_reviewer CHECK (((reviewer_type = 'SYSTEM'::text) = (reviewer_id IS NULL))),
    CONSTRAINT ticket_approvals_decision_check CHECK ((decision = ANY (ARRAY['APPROVED'::text, 'REJECTED'::text, 'AUTO_APPROVED'::text]))),
    CONSTRAINT ticket_approvals_rejection_reason_check CHECK ((rejection_reason = ANY (ARRAY['MISSING_EVIDENCE'::text, 'INSUFFICIENT_EVIDENCE'::text, 'INCORRECT_EVIDENCE'::text, 'UNCLEAR_PURPOSE'::text, 'POLICY_CONCERN'::text, 'OTHER'::text, 'AI_RECEIPT_INVALID'::text]))),
    CONSTRAINT ticket_approvals_reviewer_type_check CHECK ((reviewer_type = ANY (ARRAY['MANAGER'::text, 'SYSTEM'::text])))
);


--
-- Name: ticket_approvals_approval_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ticket_approvals_approval_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ticket_approvals_approval_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ticket_approvals_approval_id_seq OWNED BY public.ticket_approvals.approval_id;


--
-- Name: travel_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.travel_requests (
    trip_id integer NOT NULL,
    trip_code text GENERATED ALWAYS AS (('TRP-'::text || lpad((trip_id)::text, 5, '0'::text))) STORED,
    employee_id integer NOT NULL,
    destination text NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    purpose text NOT NULL,
    approval_status text DEFAULT 'IN_PROGRESS'::text NOT NULL,
    trip_state text,
    completion_type text,
    completed_by integer,
    completed_at timestamp with time zone,
    created_on date DEFAULT CURRENT_DATE NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_travel_requests_approval_trip_state CHECK (((approval_status = 'APPROVED'::text) = (trip_state IS NOT NULL))),
    CONSTRAINT ck_travel_requests_completed_by CHECK ((((completion_type = 'MANAGER'::text) AND (completed_by IS NOT NULL)) OR ((completion_type IS DISTINCT FROM 'MANAGER'::text) AND (completed_by IS NULL)))),
    CONSTRAINT ck_travel_requests_completion_type CHECK ((((trip_state = 'COMPLETED'::text) AND (completion_type IS NOT NULL)) OR ((trip_state IS DISTINCT FROM 'COMPLETED'::text) AND (completion_type IS NULL)))),
    CONSTRAINT ck_travel_requests_end_after_start CHECK ((end_date > start_date)),
    CONSTRAINT ck_travel_requests_max_duration CHECK (((end_date - start_date) <= 29)),
    CONSTRAINT travel_requests_approval_status_check CHECK ((approval_status = ANY (ARRAY['IN_PROGRESS'::text, 'APPROVED'::text, 'REJECTED'::text]))),
    CONSTRAINT travel_requests_completion_type_check CHECK ((completion_type = ANY (ARRAY['MANAGER'::text, 'AUTO'::text]))),
    CONSTRAINT travel_requests_destination_check CHECK (((length(destination) >= 2) AND (length(destination) <= 100))),
    CONSTRAINT travel_requests_purpose_check CHECK (((length(purpose) >= 10) AND (length(purpose) <= 500))),
    CONSTRAINT travel_requests_trip_state_check CHECK ((trip_state = ANY (ARRAY['ACTIVE'::text, 'COMPLETED'::text])))
);


--
-- Name: travel_requests_trip_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.travel_requests_trip_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: travel_requests_trip_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.travel_requests_trip_id_seq OWNED BY public.travel_requests.trip_id;


--
-- Name: trip_approvals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trip_approvals (
    approval_id integer NOT NULL,
    trip_id integer NOT NULL,
    reviewer_id integer NOT NULL,
    decision text NOT NULL,
    review_comment text,
    decided_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_trip_approvals_rejection_comment CHECK (((decision = 'APPROVED'::text) OR (length(TRIM(BOTH FROM COALESCE(review_comment, ''::text))) >= 10))),
    CONSTRAINT trip_approvals_decision_check CHECK ((decision = ANY (ARRAY['APPROVED'::text, 'REJECTED'::text])))
);


--
-- Name: trip_approvals_approval_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.trip_approvals_approval_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trip_approvals_approval_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.trip_approvals_approval_id_seq OWNED BY public.trip_approvals.approval_id;


--
-- Name: weather_tool_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.weather_tool_logs (
    weather_call_id bigint NOT NULL,
    session_id uuid,
    conversation_id uuid,
    correlation_id text,
    tool_call_id text,
    destination_query text,
    start_date date,
    end_date date,
    resolved_location text,
    provider text DEFAULT 'Open-Meteo'::text NOT NULL,
    http_status integer,
    latency_ms integer,
    result_status text,
    error_code text,
    cache_hit boolean DEFAULT false NOT NULL,
    retrieved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT weather_tool_logs_result_status_check CHECK ((result_status = ANY (ARRAY['AVAILABLE'::text, 'PARTIAL'::text, 'FORECAST_OUT_OF_RANGE'::text, 'LOCATION_NOT_FOUND'::text, 'LOCATION_AMBIGUOUS'::text, 'ERROR'::text])))
);


--
-- Name: weather_tool_logs_weather_call_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.weather_tool_logs_weather_call_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: weather_tool_logs_weather_call_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.weather_tool_logs_weather_call_id_seq OWNED BY public.weather_tool_logs.weather_call_id;


--
-- Name: ai_call_logs log_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_call_logs ALTER COLUMN log_id SET DEFAULT nextval('public.ai_call_logs_log_id_seq'::regclass);


--
-- Name: chat_messages message_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages ALTER COLUMN message_id SET DEFAULT nextval('public.chat_messages_message_id_seq'::regclass);


--
-- Name: employees employee_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees ALTER COLUMN employee_id SET DEFAULT nextval('public.employees_employee_id_seq'::regclass);


--
-- Name: error_logs error_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.error_logs ALTER COLUMN error_id SET DEFAULT nextval('public.error_logs_error_id_seq'::regclass);


--
-- Name: expense_tickets ticket_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_tickets ALTER COLUMN ticket_id SET DEFAULT nextval('public.expense_tickets_ticket_id_seq'::regclass);


--
-- Name: expenses expense_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expenses ALTER COLUMN expense_id SET DEFAULT nextval('public.expenses_expense_id_seq'::regclass);


--
-- Name: policy_chunks chunk_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_chunks ALTER COLUMN chunk_id SET DEFAULT nextval('public.policy_chunks_chunk_id_seq'::regclass);


--
-- Name: policy_flags flag_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_flags ALTER COLUMN flag_id SET DEFAULT nextval('public.policy_flags_flag_id_seq'::regclass);


--
-- Name: rag_call_logs rag_call_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_call_logs ALTER COLUMN rag_call_id SET DEFAULT nextval('public.rag_call_logs_rag_call_id_seq'::regclass);


--
-- Name: ticket_approvals approval_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_approvals ALTER COLUMN approval_id SET DEFAULT nextval('public.ticket_approvals_approval_id_seq'::regclass);


--
-- Name: travel_requests trip_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.travel_requests ALTER COLUMN trip_id SET DEFAULT nextval('public.travel_requests_trip_id_seq'::regclass);


--
-- Name: trip_approvals approval_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trip_approvals ALTER COLUMN approval_id SET DEFAULT nextval('public.trip_approvals_approval_id_seq'::regclass);


--
-- Name: weather_tool_logs weather_call_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weather_tool_logs ALTER COLUMN weather_call_id SET DEFAULT nextval('public.weather_tool_logs_weather_call_id_seq'::regclass);


--
-- Name: ai_call_logs ai_call_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_call_logs
    ADD CONSTRAINT ai_call_logs_pkey PRIMARY KEY (log_id);


--
-- Name: chat_conversations chat_conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_conversations
    ADD CONSTRAINT chat_conversations_pkey PRIMARY KEY (conversation_id);


--
-- Name: chat_conversations chat_conversations_session_id_turn_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_conversations
    ADD CONSTRAINT chat_conversations_session_id_turn_number_key UNIQUE (session_id, turn_number);


--
-- Name: chat_messages chat_messages_conversation_id_sequence_no_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_conversation_id_sequence_no_key UNIQUE (conversation_id, sequence_no);


--
-- Name: chat_messages chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_pkey PRIMARY KEY (message_id);


--
-- Name: chat_sessions chat_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT chat_sessions_pkey PRIMARY KEY (session_id);


--
-- Name: employees employees_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_email_key UNIQUE (email);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (employee_id);


--
-- Name: error_logs error_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.error_logs
    ADD CONSTRAINT error_logs_pkey PRIMARY KEY (error_id);


--
-- Name: evidence_files evidence_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_files
    ADD CONSTRAINT evidence_files_pkey PRIMARY KEY (evidence_id);


--
-- Name: expense_evidence expense_evidence_evidence_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_evidence
    ADD CONSTRAINT expense_evidence_evidence_code_key UNIQUE (evidence_code);


--
-- Name: expense_evidence expense_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_evidence
    ADD CONSTRAINT expense_evidence_pkey PRIMARY KEY (evidence_id);


--
-- Name: expense_tickets expense_tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_tickets
    ADD CONSTRAINT expense_tickets_pkey PRIMARY KEY (ticket_id);


--
-- Name: expense_tickets expense_tickets_replacement_of_ticket_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_tickets
    ADD CONSTRAINT expense_tickets_replacement_of_ticket_id_key UNIQUE (replacement_of_ticket_id);


--
-- Name: expense_tickets expense_tickets_ticket_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_tickets
    ADD CONSTRAINT expense_tickets_ticket_code_key UNIQUE (ticket_code);


--
-- Name: expenses expenses_evidence_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expenses
    ADD CONSTRAINT expenses_evidence_id_key UNIQUE (evidence_id);


--
-- Name: expenses expenses_expense_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expenses
    ADD CONSTRAINT expenses_expense_code_key UNIQUE (expense_code);


--
-- Name: expenses expenses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expenses
    ADD CONSTRAINT expenses_pkey PRIMARY KEY (expense_id);


--
-- Name: policy_chunks policy_chunks_content_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_chunks
    ADD CONSTRAINT policy_chunks_content_hash_key UNIQUE (content_hash);


--
-- Name: policy_chunks policy_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_chunks
    ADD CONSTRAINT policy_chunks_pkey PRIMARY KEY (chunk_id);


--
-- Name: policy_flags policy_flags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_flags
    ADD CONSTRAINT policy_flags_pkey PRIMARY KEY (flag_id);


--
-- Name: rag_call_logs rag_call_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_call_logs
    ADD CONSTRAINT rag_call_logs_pkey PRIMARY KEY (rag_call_id);


--
-- Name: receipt_checks receipt_checks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipt_checks
    ADD CONSTRAINT receipt_checks_pkey PRIMARY KEY (evidence_id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: ticket_approvals ticket_approvals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_approvals
    ADD CONSTRAINT ticket_approvals_pkey PRIMARY KEY (approval_id);


--
-- Name: ticket_approvals ticket_approvals_ticket_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_approvals
    ADD CONSTRAINT ticket_approvals_ticket_id_key UNIQUE (ticket_id);


--
-- Name: travel_requests travel_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.travel_requests
    ADD CONSTRAINT travel_requests_pkey PRIMARY KEY (trip_id);


--
-- Name: travel_requests travel_requests_trip_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.travel_requests
    ADD CONSTRAINT travel_requests_trip_code_key UNIQUE (trip_code);


--
-- Name: trip_approvals trip_approvals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trip_approvals
    ADD CONSTRAINT trip_approvals_pkey PRIMARY KEY (approval_id);


--
-- Name: trip_approvals trip_approvals_trip_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trip_approvals
    ADD CONSTRAINT trip_approvals_trip_id_key UNIQUE (trip_id);


--
-- Name: expense_tickets uq_expense_tickets_ticket_trip; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_tickets
    ADD CONSTRAINT uq_expense_tickets_ticket_trip UNIQUE (ticket_id, trip_id);


--
-- Name: policy_flags uq_policy_flags_expense_rule; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_flags
    ADD CONSTRAINT uq_policy_flags_expense_rule UNIQUE (expense_id, rule_code);


--
-- Name: weather_tool_logs weather_tool_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weather_tool_logs
    ADD CONSTRAINT weather_tool_logs_pkey PRIMARY KEY (weather_call_id);


--
-- Name: ix_chat_messages_session_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_messages_session_created ON public.chat_messages USING btree (session_id, created_at);


--
-- Name: ix_chat_sessions_employee_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_sessions_employee_started ON public.chat_sessions USING btree (employee_id, started_at DESC);


--
-- Name: ix_error_logs_correlation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_error_logs_correlation ON public.error_logs USING btree (correlation_id);


--
-- Name: ix_error_logs_occurred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_error_logs_occurred ON public.error_logs USING btree (occurred_at DESC);


--
-- Name: ix_expense_evidence_employee_sha256; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_expense_evidence_employee_sha256 ON public.expense_evidence USING btree (employee_id, sha256);


--
-- Name: ix_expense_tickets_employee_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_expense_tickets_employee_status ON public.expense_tickets USING btree (employee_id, status);


--
-- Name: ix_expense_tickets_trip; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_expense_tickets_trip ON public.expense_tickets USING btree (trip_id);


--
-- Name: ix_expenses_invoice_upper; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_expenses_invoice_upper ON public.expenses USING btree (upper(invoice_number));


--
-- Name: ix_expenses_ticket; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_expenses_ticket ON public.expenses USING btree (ticket_id);


--
-- Name: ix_expenses_trip; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_expenses_trip ON public.expenses USING btree (trip_id);


--
-- Name: ix_travel_requests_employee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_travel_requests_employee ON public.travel_requests USING btree (employee_id);


--
-- Name: ix_travel_requests_state_start; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_travel_requests_state_start ON public.travel_requests USING btree (trip_state, start_date);


--
-- Name: ix_travel_requests_status_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_travel_requests_status_state ON public.travel_requests USING btree (approval_status, trip_state);


--
-- Name: uq_chat_sessions_one_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_chat_sessions_one_active ON public.chat_sessions USING btree (employee_id) WHERE (status = 'ACTIVE'::text);


--
-- Name: evidence_files trg_evidence_files_read_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_evidence_files_read_only BEFORE DELETE OR UPDATE ON public.evidence_files FOR EACH ROW EXECUTE FUNCTION public.block_change_of_decided_evidence();


--
-- Name: expense_evidence trg_expense_evidence_read_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_expense_evidence_read_only BEFORE DELETE OR UPDATE ON public.expense_evidence FOR EACH ROW EXECUTE FUNCTION public.block_change_of_decided_evidence();


--
-- Name: expense_tickets trg_expense_tickets_read_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_expense_tickets_read_only BEFORE DELETE OR UPDATE ON public.expense_tickets FOR EACH ROW EXECUTE FUNCTION public.block_change_of_decided_ticket();


--
-- Name: expense_tickets trg_expense_tickets_trip_active; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_expense_tickets_trip_active BEFORE INSERT ON public.expense_tickets FOR EACH ROW EXECUTE FUNCTION public.check_ticket_trip_is_active();


--
-- Name: expenses trg_expenses_date_after_trip_created; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_expenses_date_after_trip_created BEFORE INSERT OR UPDATE OF expense_date, trip_id ON public.expenses FOR EACH ROW EXECUTE FUNCTION public.check_expense_date_after_trip_created();


--
-- Name: expenses trg_expenses_read_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_expenses_read_only BEFORE DELETE OR UPDATE ON public.expenses FOR EACH ROW EXECUTE FUNCTION public.block_change_of_decided_expense();


--
-- Name: ticket_approvals trg_ticket_approvals_read_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_ticket_approvals_read_only BEFORE DELETE OR UPDATE ON public.ticket_approvals FOR EACH ROW EXECUTE FUNCTION public.block_change_of_approval_history();


--
-- Name: travel_requests trg_travel_requests_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_travel_requests_updated_at BEFORE UPDATE ON public.travel_requests FOR EACH ROW EXECUTE FUNCTION public.set_travel_request_updated_at();


--
-- Name: trip_approvals trg_trip_approvals_read_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_trip_approvals_read_only BEFORE DELETE OR UPDATE ON public.trip_approvals FOR EACH ROW EXECUTE FUNCTION public.block_change_of_approval_history();


--
-- Name: ai_call_logs ai_call_logs_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_call_logs
    ADD CONSTRAINT ai_call_logs_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.chat_conversations(conversation_id) ON DELETE RESTRICT;


--
-- Name: ai_call_logs ai_call_logs_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_call_logs
    ADD CONSTRAINT ai_call_logs_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id) ON DELETE RESTRICT;


--
-- Name: chat_conversations chat_conversations_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_conversations
    ADD CONSTRAINT chat_conversations_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id) ON DELETE RESTRICT;


--
-- Name: chat_messages chat_messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.chat_conversations(conversation_id) ON DELETE RESTRICT;


--
-- Name: chat_messages chat_messages_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id) ON DELETE RESTRICT;


--
-- Name: chat_sessions chat_sessions_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT chat_sessions_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE RESTRICT;


--
-- Name: employees employees_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_manager_id_fkey FOREIGN KEY (manager_id) REFERENCES public.employees(employee_id) ON DELETE RESTRICT;


--
-- Name: evidence_files evidence_files_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_files
    ADD CONSTRAINT evidence_files_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES public.expense_evidence(evidence_id) ON DELETE CASCADE;


--
-- Name: expense_evidence expense_evidence_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_evidence
    ADD CONSTRAINT expense_evidence_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE RESTRICT;


--
-- Name: expense_tickets expense_tickets_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_tickets
    ADD CONSTRAINT expense_tickets_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE RESTRICT;


--
-- Name: expense_tickets expense_tickets_replacement_of_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_tickets
    ADD CONSTRAINT expense_tickets_replacement_of_ticket_id_fkey FOREIGN KEY (replacement_of_ticket_id) REFERENCES public.expense_tickets(ticket_id) ON DELETE RESTRICT;


--
-- Name: expense_tickets expense_tickets_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expense_tickets
    ADD CONSTRAINT expense_tickets_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.travel_requests(trip_id) ON DELETE RESTRICT;


--
-- Name: expenses expenses_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expenses
    ADD CONSTRAINT expenses_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES public.expense_evidence(evidence_id) ON DELETE RESTRICT;


--
-- Name: expenses expenses_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expenses
    ADD CONSTRAINT expenses_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.travel_requests(trip_id) ON DELETE RESTRICT;


--
-- Name: expenses fk_expenses_ticket_trip; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.expenses
    ADD CONSTRAINT fk_expenses_ticket_trip FOREIGN KEY (ticket_id, trip_id) REFERENCES public.expense_tickets(ticket_id, trip_id) ON DELETE RESTRICT;


--
-- Name: policy_flags policy_flags_expense_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_flags
    ADD CONSTRAINT policy_flags_expense_id_fkey FOREIGN KEY (expense_id) REFERENCES public.expenses(expense_id) ON DELETE RESTRICT;


--
-- Name: rag_call_logs rag_call_logs_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_call_logs
    ADD CONSTRAINT rag_call_logs_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.chat_conversations(conversation_id) ON DELETE RESTRICT;


--
-- Name: rag_call_logs rag_call_logs_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_call_logs
    ADD CONSTRAINT rag_call_logs_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id) ON DELETE RESTRICT;


--
-- Name: receipt_checks receipt_checks_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipt_checks
    ADD CONSTRAINT receipt_checks_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES public.expense_evidence(evidence_id) ON DELETE CASCADE;


--
-- Name: ticket_approvals ticket_approvals_reviewer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_approvals
    ADD CONSTRAINT ticket_approvals_reviewer_id_fkey FOREIGN KEY (reviewer_id) REFERENCES public.employees(employee_id) ON DELETE RESTRICT;


--
-- Name: ticket_approvals ticket_approvals_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_approvals
    ADD CONSTRAINT ticket_approvals_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.expense_tickets(ticket_id) ON DELETE RESTRICT;


--
-- Name: travel_requests travel_requests_completed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.travel_requests
    ADD CONSTRAINT travel_requests_completed_by_fkey FOREIGN KEY (completed_by) REFERENCES public.employees(employee_id) ON DELETE RESTRICT;


--
-- Name: travel_requests travel_requests_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.travel_requests
    ADD CONSTRAINT travel_requests_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE RESTRICT;


--
-- Name: trip_approvals trip_approvals_reviewer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trip_approvals
    ADD CONSTRAINT trip_approvals_reviewer_id_fkey FOREIGN KEY (reviewer_id) REFERENCES public.employees(employee_id) ON DELETE RESTRICT;


--
-- Name: trip_approvals trip_approvals_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trip_approvals
    ADD CONSTRAINT trip_approvals_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.travel_requests(trip_id) ON DELETE RESTRICT;


--
-- Name: weather_tool_logs weather_tool_logs_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weather_tool_logs
    ADD CONSTRAINT weather_tool_logs_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.chat_conversations(conversation_id) ON DELETE RESTRICT;


--
-- Name: weather_tool_logs weather_tool_logs_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weather_tool_logs
    ADD CONSTRAINT weather_tool_logs_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id) ON DELETE RESTRICT;


--
-- PostgreSQL database dump complete
--

\unrestrict zBeoxNOeJ5oW7l9lPO8CExBMFBFbGpkPFpVbEXsBjg0Y8zvV78zsj8rVq3Keq1F


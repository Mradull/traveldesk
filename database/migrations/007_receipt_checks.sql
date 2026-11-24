-- Receipt verification: what the AI read from each receipt photo, and the per-line result.
-- Owner: Mradul (M3)  |  Spec: Agile Spec v2.1 > Receipt verification (team decision 2026-11-24)
--
-- Flow: after upload, the photo is read ONCE (Sightengine: AI-generated score; vision LLM:
-- amount, date, merchant, place) and stored in receipt_checks. Comparing that with the line the
-- employee typed is plain code (services/receipt_rules.py), stored on the line at submission.
--   amount <= threshold, receipt INVALID      -> flag RECEIPT_MISMATCH  -> manager decides
--   amount >  threshold, receipt INVALID      -> line moves to its own ticket, REJECTED by SYSTEM
--                                               (routing AI_CHECK, reason AI_RECEIPT_INVALID)
--   AI service down                           -> flag RECEIPT_NOT_VERIFIED -> manager decides
--   receipt unreadable                        -> submission refused (422), employee re-uploads

-- (1) One reading per photo. Deleted with the photo (unattached uploads are cleaned up after 24 h).
CREATE TABLE receipt_checks (
    evidence_id UUID PRIMARY KEY
        REFERENCES expense_evidence (evidence_id) ON DELETE CASCADE,
    status TEXT NOT NULL
        CHECK (status IN ('READ', 'UNREADABLE', 'ERROR')),
    is_receipt BOOLEAN,
    total_amount NUMERIC(12, 2),
    currency TEXT,
    receipt_date DATE,
    merchant TEXT,
    city TEXT,
    from_place TEXT,
    to_place TEXT,
    summary TEXT,
    ai_generated_score REAL
        CHECK (ai_generated_score IS NULL OR ai_generated_score BETWEEN 0 AND 1),
    error_code TEXT,                       -- why status = ERROR (e.g. AI_UNAVAILABLE)
    model_name TEXT,                       -- which vision model read it
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- (2) The result for each expense line, frozen at submission like the rest of the line.
--     ALTER TABLE does not fire the row triggers of migration 006.
ALTER TABLE expenses
    ADD COLUMN receipt_verdict TEXT
        CHECK (receipt_verdict IN ('VALID', 'INVALID', 'NOT_VERIFIED')),
    ADD COLUMN receipt_checks JSONB NOT NULL DEFAULT '[]'::jsonb;

-- (3) Two new policy flag codes.
ALTER TABLE policy_flags DROP CONSTRAINT policy_flags_rule_code_check;
ALTER TABLE policy_flags ADD CONSTRAINT policy_flags_rule_code_check
    CHECK (rule_code IN ('OVER_THRESHOLD', 'DUPLICATE_RECEIPT', 'RECEIPT_MISMATCH', 'RECEIPT_NOT_VERIFIED'));

-- (4) Tickets rejected by the receipt check at submission: routing AI_CHECK, status REJECTED.
ALTER TABLE expense_tickets DROP CONSTRAINT expense_tickets_routing_check;
ALTER TABLE expense_tickets ADD CONSTRAINT expense_tickets_routing_check
    CHECK (routing IN ('AUTO', 'MANAGER', 'AI_CHECK'));
ALTER TABLE expense_tickets DROP CONSTRAINT ck_expense_tickets_routing_status;
ALTER TABLE expense_tickets ADD CONSTRAINT ck_expense_tickets_routing_status
    CHECK (
        (status = 'AUTO_APPROVED' AND routing = 'AUTO')
        OR (status = 'REJECTED' AND routing = 'AI_CHECK')
        OR (status <> 'AUTO_APPROVED' AND routing = 'MANAGER')
    );

-- (5) The SYSTEM rejection reason used by the receipt check (managers cannot pick it).
ALTER TABLE ticket_approvals DROP CONSTRAINT ticket_approvals_rejection_reason_check;
ALTER TABLE ticket_approvals ADD CONSTRAINT ticket_approvals_rejection_reason_check
    CHECK (
        rejection_reason IN (
            'MISSING_EVIDENCE', 'INSUFFICIENT_EVIDENCE', 'INCORRECT_EVIDENCE',
            'UNCLEAR_PURPOSE', 'POLICY_CONCERN', 'OTHER', 'AI_RECEIPT_INVALID'
        )
    );

-- (6) AI call logs: receipt reading is its own feature.
ALTER TABLE ai_call_logs DROP CONSTRAINT ai_call_logs_feature_check;
ALTER TABLE ai_call_logs ADD CONSTRAINT ai_call_logs_feature_check
    CHECK (feature IN ('CHAT', 'SUMMARY', 'RECEIPT'));

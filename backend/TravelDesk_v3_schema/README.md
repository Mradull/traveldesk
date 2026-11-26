# TravelDesk v3.0 - schema files

| File | What it is |
|---|---|
| `schemas.py` | The API data contract: every Pydantic request/response model and enum. Save as `backend/app/schemas.py`. Identical to `main` (commit 96875a4). |
| `traveldesk_schema.sql` | The full PostgreSQL schema (tables, constraints, indexes, triggers) produced by migrations 001-007, exported with `pg_dump --schema-only`. For reading and review; to build a database use `python scripts/init_db.py`, which applies the migration files in order. |
| `er_diagrams/` | Six entity-relationship figures generated from the same database: trips, tickets, receipt evidence (with `receipt_checks`), chat, AI / RAG / weather logs, error_logs. Every column is shown. |

Changes since v2.0: 11 new receipt / dashboard models; new enum values (`RECEIPT_MISMATCH`, `RECEIPT_NOT_VERIFIED`, `AI_RECEIPT_INVALID`, `AI_CHECK`, `RECEIPT_UNREADABLE`, feature `RECEIPT`); new fields `ExpenseOut.receipt_*`, `TicketDetailOut.ai_rejected_ticket`, `PendingExpenseOut.ticket_id`, `ChatReplyOut.weather_cards`, `VeraWeatherAnswer.days`; migration 007 adds `receipt_checks` and `expenses.receipt_verdict` / `receipt_checks`.

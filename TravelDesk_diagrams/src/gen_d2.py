"""TravelDesk Agile Spec v3.0 - diagrams in D2 (rendered with the ELK layout, then SVG -> PNG at 2x).

Design rules (so every figure is readable on an A4 page):
  * one shared style: rounded boxes, bold title + regular description, muted colours with meaning;
  * designed for a page width of about 950 px, so text prints at roughly 9-11 pt;
  * one main direction per figure, few boxes side by side, short labels;
  * ER figures are generated from the database catalog (schema/tables.json), every column shown.
Run:  python gen_d2.py [name ...]
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SRC, PNG = HERE / "src", HERE / "png"
SRC.mkdir(exist_ok=True); PNG.mkdir(exist_ok=True)
TABLES = json.load(open("/home/claude/spec3/schema/tables.json"))

HEAD = '''vars: {d2-config: {layout-engine: elk; pad: 28}}
(** -> **)[*].style: {stroke: "#64748B"; stroke-width: 2; font-size: 14; font-color: "#1E293B"; italic: false}
(** <-> **)[*].style: {stroke: "#64748B"; stroke-width: 2; font-size: 14; font-color: "#1E293B"; italic: false}
classes: {
  emp: {style: {fill: "#E6F4F1"; stroke: "#0F766E"; stroke-width: 2; border-radius: 10; font-color: "#0B3B36"}}
  mgr: {style: {fill: "#EEF0FF"; stroke: "#4338CA"; stroke-width: 2; border-radius: 10; font-color: "#1E1B4B"}}
  sys: {style: {fill: "#FEF6E4"; stroke: "#B45309"; stroke-width: 2; border-radius: 10; font-color: "#451A03"}}
  ai: {style: {fill: "#F3EEFF"; stroke: "#7C3AED"; stroke-width: 2; border-radius: 10; font-color: "#2E1065"}}
  ok: {style: {fill: "#EAF7EE"; stroke: "#15803D"; stroke-width: 2; border-radius: 10; font-color: "#052E16"}}
  bad: {style: {fill: "#FDECEC"; stroke: "#B91C1C"; stroke-width: 2; border-radius: 10; font-color: "#450A0A"}}
  ext: {style: {fill: "#FFF3EB"; stroke: "#C2410C"; stroke-width: 2; border-radius: 10; font-color: "#431407"}}
  neu: {style: {fill: "#F8FAFC"; stroke: "#475569"; stroke-width: 2; border-radius: 10; font-color: "#0F172A"}}
  db: {shape: cylinder; style: {fill: "#F1F5F9"; stroke: "#334155"; stroke-width: 2; font-color: "#0F172A"}}
  q: {shape: diamond; style: {fill: "#FFFFFF"; stroke: "#475569"; stroke-width: 2; font-color: "#0F172A"; font-size: 15}}
  grp: {style: {fill: "#FBFCFD"; stroke: "#94A3B8"; stroke-width: 1; border-radius: 14; font-color: "#334155"; font-size: 19; bold: true}}
  grpv: {style: {fill: "#FBF9FF"; stroke: "#A78BFA"; stroke-width: 1; border-radius: 14; font-color: "#4C1D95"; font-size: 19; bold: true}}
  qr: {shape: rectangle; style: {fill: "#FFFFFF"; stroke: "#475569"; stroke-width: 2; border-radius: 22; font-color: "#0F172A"; font-size: 15}}
  note: {shape: page; style: {fill: "#FFFBEB"; stroke: "#B45309"; stroke-width: 1; font-color: "#451A03"}}
}
'''


def n(key, title, desc="", cls="neu", extra=""):
    """A box: bold title + regular description (lines joined with <br/>)."""
    lines = [f"**{title}**"] + ([desc] if isinstance(desc, str) and desc else list(desc) if desc else [])
    body = "<br/>".join(lines).replace("<=", "&le;").replace(">=", "&ge;").replace("->", "&rarr;")
    shape = {"db": "cylinder", "note": "page"}.get(cls, "rectangle")
    return f"{key}: {{\n  shape: {shape}\n  class: {cls}\n  label: |||md\n    {body}\n  |||\n  {extra}\n}}\n"


def q(key, text):
    return f'{key}: "{text}" {{class: q}}\n'


def qr(key, text):
    return f'{key}: "{text}" {{class: qr}}\n'


def e(a, b, label="", style=""):
    lab = f': "{label}"' if label else ""
    st = f" {{style: {{{style}}}}}" if style else ""
    if lab and st:
        return f"{a} -> {b}{lab}{st}\n"
    return f"{a} -> {b}{lab}{st}\n"


DASH = 'stroke-dash: 5'
RED = 'stroke: "#B91C1C"; stroke-dash: 5; font-color: "#B91C1C"'

D = {}

# ---------------------------------------------------------------------------------------------- d01 context
D["d01_context"] = "direction: down\n" + n("emp", "Employee", "requests trips, claims expenses, asks Vera", "emp") + \
    n("mgr", "Manager", "approves trips and tickets, sees spending", "mgr") + '''
td: "TravelDesk" {
  class: grp
''' + n("app", "React app", "Employee view, Manager view, Vera window") + \
    n("api", "FastAPI backend", ["auth, business rules, receipt checks,", "Vera, weather and every AI call"]) + \
    n("db", "PostgreSQL (local)", ["business data, receipt photos,", "chat history, policy chunks, logs"], "db") + '''
  app -> api: "HTTPS JSON + JWT"
  api -> db: "SQL"
}
''' + n("llm", "LLM provider", ["OpenRouter or Gemini", "(AI_PROVIDER in .env)"], "ext") + \
    n("om", "Open-Meteo", "geocoding + 16-day forecast", "ext") + \
    n("se", "Sightengine", "optional receipt authenticity", "ext") + \
    n("dev", "Developer / assessor", "Swagger, pgAdmin, logs") + \
    e("emp", "td.app") + e("mgr", "td.app") + e("td.api", "llm", "Vera, receipt reading") + \
    e("td.api", "om", "weather tool") + e("td.api", "se", "authenticity") + \
    e("dev", "td", "Swagger, pgAdmin", DASH)

# ---------------------------------------------------------------------------------------------- d02 architecture
D["d02_architecture"] = "direction: down\n" + '''
fe: "React app" {
  class: grp
''' + n("ev", "Employee view", "trips, tickets, receipts", "emp") + \
    n("vw", "Vera window", "3 employee pages", "ai") + \
    n("mv", "Manager view", "approvals, reports", "mgr") + '''
}
be: "FastAPI" {
  class: grp
''' + n("mw", "Middleware (JWT, ids, errors)", "") + '''
  bus: "Business side" {
    class: grp
''' + n("br", "Routers + services", "") + \
    n("pe", "Rules (pure code)", "flags, routing, receipt checks", "sys") + \
    n("rs", "Receipt service", "reads each photo once", "ai") + '''
    br -> pe
    br -> rs
  }
  vera: "Vera side (no business code)" {
    class: grpv
''' + n("cs", "Chat package", "", "ai") + \
    n("tl", "RAG + WeatherService", "", "ai") + '''
    cs -> tl
  }
''' + n("ai", "Shared AI layer", "provider switch, retries, logs", "ai") + '''
  mw -> bus.br
  mw -> vera.cs
  bus.rs -> ai: "RECEIPT"
  vera.cs -> ai: "CHAT"
}
''' + n("pg", "PostgreSQL", "data, photos, logs", "db") + \
    n("llm", "LLM provider", "OpenRouter or Gemini", "ext") + \
    n("om", "Open-Meteo", "forecast", "ext") + \
    e("fe", "be.mw", "HTTPS + JWT") + e("be", "pg", "SQL") + e("be.ai", "llm") + e("be.vera.tl", "om")

# ---------------------------------------------------------------------------------------------- d03 backend modules
D["d03_backend_modules"] = "direction: down\n" + n("main", "main.py", "app, middleware, routers, scheduler") + '''
b: "Business side" {
  class: grp
''' + n("r", "routers/", ["auth, trips, evidence, tickets, expenses,", "dashboard, reports, policy, health"]) + \
    n("s", "services/", ["trip, approval, evidence, ticket,", "report, receipt_service, jobs"]) + \
    n("p", "Pure rules", "policy_engine, receipt_rules", "sys") + \
    n("rp", "repositories/", "business tables") + '''
  r -> s
  s -> p
  s -> rp
}
v: "Vera side: cannot import business code" {
  class: grpv
''' + n("r2", "routers/chat.py", "Employee only", "ai") + \
    n("c", "chat/", ["service, sessions, router, context,", "memory, guardrails, tools, formatter"], "ai") + \
    n("x", "rag/ + weather_service", "policy search, forecasts", "ai") + \
    n("vr", "chat_repo, log_repo,", "policy_chunk_repo") + '''
  r2 -> c
  c -> x
  c -> vr
}
''' + n("ai", "ai/ (shared)", "llm_client, prompts, validators, receipt reader", "ai") + \
    n("core", "core/ (used by every module)", ["config, database, security, deps, errors,", "middleware, logging, scheduler"]) + \
    e("main", "b.r") + e("main", "v.r2") + e("b.s", "ai", "receipt_service only") + e("v.c", "ai") + \
    e("b.rp", "core") + e("v.vr", "core")

# ---------------------------------------------------------------------------------------------- d04 LLM layer
D["d04_llm_layer"] = "direction: down\n" + \
    n("c1", "Vera turn", "CHAT", "ai") + n("c2", "Session memory", "SUMMARY", "ai") + n("c3", "Receipt service", "RECEIPT", "ai") + \
    n("sw", "Provider switch (ai/llm_client.py)", ["AI_PROVIDER = openrouter | gemini | azure", "model, key, base URL only in backend/.env"]) + \
    n("rt", "Call policy", ["timeout 15 s; up to 2 retries", "on timeout / 5xx only, never on 401 / 429"], "sys") + \
    n("lg", "ai_call_logs", ["feature, provider, model, status,", "latency, tokens; failure reason"]) + \
    n("p1", "OpenRouter", "e.g. nemotron-3.5-super-vl:free", "ext") + \
    n("p2", "Gemini", "e.g. gemini-3.1-flash-lite", "ext") + \
    n("p3", "Azure OpenAI", "optional", "ext") + \
    n("er", "After retries: LLMError", ["Vera: safe message + Retry", "Receipt: NOT_VERIFIED, manager decides"], "bad") + \
    e("c1", "sw") + e("c2", "sw") + e("c3", "sw") + e("sw", "rt") + e("rt", "lg", "", DASH) + \
    e("rt", "p1") + e("rt", "p2") + e("rt", "p3", "", DASH) + e("p2", "er", "failure", DASH)

# ---------------------------------------------------------------------------------------------- d05 journey
D["d05_journey"] = "direction: down\n" + \
    n("s1", "1. Sign in (JWT) -> Dashboard", "", "emp") + \
    n("s2", "2. Create a trip request", "date rules checked as you type", "emp") + \
    n("s3", "3. Manager decides", "reject needs a 10+ character comment", "mgr") + \
    n("tr", "Trip rejected (final)", "", "bad") + \
    n("s4", "4. Trip Approved - Active", "", "ok") + \
    n("v", "Ask Vera any time", "", "ai") + \
    n("s5", "5. Raise a ticket", "each line: amount, date, receipt photo", "emp") + \
    n("s6", "6. Live receipt check", "AI reads the photo; code compares", "ai") + \
    n("s7", "7. Submit", "validation, policy flags, receipt verdict", "sys") + \
    n("a", "Auto-approved", "", "ok") + \
    n("p", "8. Manager review", "", "mgr") + \
    n("x", "Rejected by SYSTEM", "receipt invalid above threshold", "bad") + \
    n("ap", "Approved", "", "ok") + \
    n("rm", "Rejected by manager", "", "bad") + \
    n("nt", "9. Create new ticket", "same trip, new ids, checks again", "emp") + \
    n("c", "10. Trip completed", "manager, or system at start + 90 days") + \
    n("r", "11. Spending Summary, Dashboard", "", "mgr") + \
    e("s1", "s2") + e("s2", "s3") + e("s3", "tr", "reject") + e("s3", "s4", "approve") + e("s4", "v", "", DASH) + \
    e("s4", "s5") + e("s5", "s6") + e("s6", "s7") + e("s7", "a", "clean") + e("s7", "p", "flagged") + \
    e("s7", "x", "invalid, over threshold") + e("p", "ap", "approve") + e("p", "rm", "reject") + \
    e("rm", "nt") + e("x", "nt") + e("a", "c") + e("ap", "c") + e("c", "r")

# ---------------------------------------------------------------------------------------------- d06 trip lifecycle
D["d06_trip_lifecycle"] = "direction: down\n" + \
    'start: "" {shape: circle; width: 22; height: 22; style: {fill: "#0F172A"; stroke: "#0F172A"}}\n' + \
    n("ip", "In Progress", ["IN_PROGRESS; employee may edit", "start today..+365, end > start, <= 30 days"], "emp") + \
    n("rj", "Rejected", "final, read-only", "bad") + \
    n("ac", "Approved - Active", "APPROVED + ACTIVE; tickets allowed", "ok") + \
    n("co", "Approved - Completed", ["COMPLETED (MANAGER or AUTO);", "pending tickets still decided"]) + \
    e("start", "ip", "employee submits") + e("ip", "rj", "manager rejects (comment)") + \
    e("ip", "ac", "manager approves (before start + 90 d)") + \
    e("ac", "co", "manager after end date, or system at start + 90 d")

# ---------------------------------------------------------------------------------------------- d07 receipt check
D["d07_receipt_check"] = "direction: down\n" + \
    n("up", "1. Upload the photo", "POST /evidence - JPEG/PNG/WEBP, max 5 MB", "emp") + \
    n("upx", "Refused", "415 type / 413 size", "bad") + \
    n("vf", "2. Check while typing the line", "POST /evidence/{id}/verify", "emp") + \
    q("st", "Reading\\nstored?") + \
    n("rd", "3. Read the photo once (AI)", ["total, date, merchant, city / route,", "is it a receipt? (+ Sightengine score)"], "ai") + \
    q("rs", "Reading\\nstatus?") + \
    n("nv", "NOT_VERIFIED", "AI failed: manager decides", "sys") + \
    n("ur", "UNREADABLE", "blurred, cut off, not a receipt", "bad") + \
    n("ck", "4. Four checks (plain code)", ["**Amount** within 1 % or Rs 10", "**Date** within 1 day, not before the trip", "**Place** city / route matches", "**Authenticity** score below 0.5"], "sys") + \
    q("fl", "Any check\\nfailed?") + \
    n("inv", "INVALID", "shows the failed check", "bad") + \
    n("ok", "VALID", "Receipt verified", "ok") + \
    e("up", "upx", "refused") + e("up", "vf") + e("vf", "st") + e("st", "rd", "no") + e("st", "rs", "yes") + \
    e("rd", "rs") + e("rs", "nv", "error") + e("rs", "ur", "unreadable") + e("rs", "ck", "read") + \
    e("ck", "fl") + e("fl", "inv", "yes") + e("fl", "ok", "no")

# ---------------------------------------------------------------------------------------------- d08 ticket routing
D["d08_ticket_routing"] = "direction: down\n" + \
    n("s", "Submit the ticket", "POST /trips/{id}/tickets - 1 to 20 lines", "emp") + \
    q("v1", "Lines\\nvalid?") + n("e1", "422 validation", "", "bad") + \
    q("v2", "Trip Active,\\nphotos OK?") + n("e2", "409 / 404", "", "bad") + \
    n("pe", "Policy engine", "OVER_THRESHOLD, DUPLICATE_RECEIPT", "sys") + \
    n("rc", "Receipt verdict per line", "stored reading vs final values", "ai") + \
    q("u", "Any\\nunreadable?") + n("e3", "422 RECEIPT_UNREADABLE", "", "bad") + \
    n("m", "Receipt effects", ["INVALID, at or below threshold: flag RECEIPT_MISMATCH", "NOT_VERIFIED: flag RECEIPT_NOT_VERIFIED", "INVALID, above threshold: line split off"], "sys") + \
    q("k", "Flags on\\nthe ticket?") + \
    n("aa", "AUTO_APPROVED", "", "ok") + \
    n("pd", "PENDING (manager)", "", "mgr") + \
    n("ar", "Second ticket REJECTED", "by SYSTEM: AI_CHECK, AI_RECEIPT_INVALID", "bad") + \
    e("s", "v1") + e("v1", "e1", "no") + e("v1", "v2", "yes") + e("v2", "e2", "no") + e("v2", "pe", "yes") + \
    e("pe", "rc") + e("rc", "u") + e("u", "e3", "yes") + e("u", "m", "no") + e("m", "k") + \
    e("m", "ar", "split") + e("k", "aa", "none") + e("k", "pd", "any")

# ---------------------------------------------------------------------------------------------- d09 decision + replacement
D["d09_decision_replacement"] = "direction: down\n" + \
    n("pd", "PENDING ticket", "in the manager's queue", "sys") + \
    n("rv", "Ticket review", "photos, flags, receipt checks", "mgr") + \
    n("ap", "APPROVED", "comment optional", "ok") + \
    n("rm", "REJECTED by manager", "reason + comment of 10+", "bad") + \
    n("rs", "REJECTED by SYSTEM", "receipt check above threshold", "bad") + \
    n("nt", "Create new ticket", "same trip, once, while Active", "emp") + \
    n("nw", "New ticket", "new ids; all checks again", "emp") + \
    n("ro", "Decided = read-only", ["no edit / delete (405),", "DB triggers, second decision 409"], "note") + \
    e("pd", "rv") + e("rv", "ap", "approve") + e("rv", "rm", "reject") + \
    e("rm", "nt") + e("rs", "nt") + e("nt", "nw")

# ---------------------------------------------------------------------------------------------- d10 frontend
D["d10_frontend"] = "direction: down\n" + \
    n("lg", "/login", "JWT in sessionStorage; landing page by role") + '''
emp: "Employee pages" {
  class: grp
  grid-columns: 1
''' + n("a", "/dashboard", "totals, recent trips", "emp") + \
    n("b", "/trips  (Vera)", "list, filters, search", "emp") + \
    n("c", "/trips/new", "Create Trip", "emp") + \
    n("d", "/trips/:id  (Vera)", "detail, timeline, tickets", "emp") + \
    n("e", "/trips/:id/expenses/new  (Vera)", "Raise Ticket + receipt check", "emp") + \
    n("f", "/tickets/:id", "lines, photos, checks", "emp") + '''
}
mgr: "Manager pages (no Vera)" {
  class: grp
  grid-columns: 1
''' + n("g", "/manager/approvals", "three tabs with counts", "mgr") + \
    n("h", "/manager/trips/:id", "approve, reject, complete", "mgr") + \
    n("i", "/manager/tickets/:id", "decision panel", "mgr") + \
    n("j", "/manager/reports", "Spending Summary", "mgr") + '''
}
''' + n("api", "src/api/client.js", ["Bearer JWT on every call; errors as toasts;", "401 back to /login"]) + \
    n("fa", "FastAPI re-checks everything", "signature, expiry, role, ownership", "bad") + \
    e("lg", "emp", "EMPLOYEE") + e("lg", "mgr", "MANAGER") + e("emp", "api") + e("mgr", "api") + e("api", "fa")

# ---------------------------------------------------------------------------------------------- d11 Vera turn
D["d11_vera_turn"] = "direction: down\n" + \
    n("m", "Employee message", "max 1,000 characters", "emp") + \
    n("g1", "Session + rate limit", "own, active, idle < 60 min, 10 / min", "sys") + \
    n("x1", "403 / 404 / 410 / 429", "410: new chat, resend once", "bad") + \
    n("g2", "Input guardrails", "mask personal data; block injection", "sys") + \
    n("rt", "Intent router", "decides the allowed tools", "sys") + \
    n("fx", "Fixed reply", "greeting, boundary or blocked") + \
    n("r1", "LLM round 1", "tool calls, or a clarifying question", "ai") + \
    n("ad", "Searches code always adds", "policy; follow-up; claim procedure", "sys") + \
    n("tl", "Run tools (max 4)", "policy search, weather forecast") + \
    n("r2", "Round 2 if needed", "places listed but not looked up", "ai") + \
    n("pp", "Policy part", "steps + rules, cited", "ai") + \
    n("wp", "Weather part", "1 place or one trip answer, 20 s", "ai") + \
    n("oc", "Output checks", "grounding, citations, boundaries", "sys") + \
    n("fn", "Reply + logs", "ai_response, weather_cards, latency", "ok") + \
    e("m", "g1") + e("g1", "x1", "fails") + e("g1", "g2") + e("g2", "rt") + e("g2", "fx", "blocked", DASH) + \
    e("rt", "fx", "no tool needed") + e("rt", "r1", "policy / weather") + e("r1", "ad") + e("ad", "tl") + \
    e("tl", "r2") + e("r2", "pp") + e("r2", "wp") + e("pp", "oc") + e("wp", "oc") + e("oc", "fn") + \
    e("r1", "fn", "question only", DASH) + e("fx", "fn", "", DASH)

# ---------------------------------------------------------------------------------------------- d12 intent routing
_steps = [("q1", "Only greeting words?", "GREETING", "fixed reply", "neu"),
          ("q2", "Asks for own records, or an action?", "OUT_OF_SCOPE", "boundary reply", "bad"),
          ("q3", "Weather AND policy words?", "POLICY_AND_WEATHER", "both tools", "ai"),
          ("q4", "Weather words?", "WEATHER", "forecast tool", "ai"),
          ("q5", "Policy or how-to words?", "POLICY", "policy search", "ai"),
          ("q6", "Travel plan ('going to Italy')?", "WEATHER", "asks city + exact dates", "ai"),
          ("q7", "Follow-up: short, or gives dates?", "Previous intent", "continues the topic", "ai"),
          ("q8", "Similar to a policy rule (>= 0.35)?", "POLICY", "embedding similarity", "ai")]
_d = "grid-rows: 9\ngrid-columns: 2\ngrid-gap: 30\n"
for k, (qk, qt, ot, od, oc) in enumerate(_steps):          # each row: question | outcome
    _d += qr(qk, f"{k + 1}. {qt}") + n("o" + qk, ot, od, oc)
_d += qr("q9", "9. Nothing matched") + n("oq9", "OUT_OF_SCOPE", "boundary reply", "bad")
for k, (qk, *_r) in enumerate(_steps):
    _d += e(qk, "o" + qk, "yes") + e(qk, _steps[k + 1][0] if k + 1 < len(_steps) else "q9", "no")
_d += e("q9", "oq9")
D["d12_intent_routing"] = _d

# ---------------------------------------------------------------------------------------------- d13 Vera sequence
D["d13_vera_sequence"] = '''shape: sequence_diagram
W: "Vera window" {style: {fill: "#E6F4F1"; stroke: "#0F766E"; stroke-width: 2}}
C: "Chat service" {style: {fill: "#F3EEFF"; stroke: "#7C3AED"; stroke-width: 2}}
DB: "PostgreSQL" {style: {fill: "#F1F5F9"; stroke: "#334155"; stroke-width: 2}}
L: "LLM" {style: {fill: "#FFF3EB"; stroke: "#C2410C"; stroke-width: 2}}
T: "Tools" {style: {fill: "#FEF6E4"; stroke: "#B45309"; stroke-width: 2}}
W -> C: "message (JWT)"
C -> DB: "check + store"
C -> C: "guardrails, routing"
C -> L: "round 1"
L -> C: "tool calls"
C -> T: "search / forecast"
T -> C: "results"
C -> L: "round 2 (if places missing)"
C -> L: "write answer (20 s)"
L -> C: "checked text"
C -> DB: "reply + logs"
C -> W: "reply + cards"
'''

# ---------------------------------------------------------------------------------------------- d14 weather tool
D["d14_weather_tool"] = "direction: down\n" + \
    n("c", "get_weather_forecast", "destination, start, end (one call per place)", "ai") + \
    q("v", "Inputs\\nvalid?") + n("v1", "Ask the employee", "missing or invalid inputs", "sys") + \
    q("ch", "In cache?") + \
    n("g", "Geocode", "Open-Meteo, 5 candidates") + \
    q("gq", "Found and\\nunambiguous?") + n("g1", "Ask which place", "not found / ambiguous", "sys") + \
    q("r", "Any date within\\n16 days?") + n("r1", "Forecast not available", "no values, no forecast call", "sys") + \
    n("f", "Forecast call", "covered dates only; values copied exactly") + \
    n("e1", "Provider failure", "timeout, 5xx, 429, bad JSON: Retry", "bad") + \
    n("ok", "AVAILABLE / PARTIAL", "logged in weather_tool_logs", "ok") + \
    e("c", "v") + e("v", "v1", "no") + e("v", "ch", "yes") + e("ch", "ok", "yes") + e("ch", "g", "no") + \
    e("g", "gq") + e("gq", "g1", "no") + e("gq", "r", "yes") + e("r", "r1", "no") + e("r", "f", "yes") + \
    e("f", "ok") + e("f", "e1", "fails")

# ---------------------------------------------------------------------------------------------- d15 weather answers
D["d15_weather_answers"] = "direction: down\n" + \
    n("in", "Forecasts of this turn", "in the order the employee listed them", "ai") + \
    q("k", "How many\\nplaces?") + '''
one: "One place" {
  class: grp
''' + n("a1", "AI writes", "summary + 3-5 tips with reasons", "ai") + \
    n("a2", "Grounding", "numbers and conditions from the data", "sys") + \
    n("a3", "Reply", "summary, What to pack, note, 1 card", "ok") + '''
  a1 -> a2 -> a3
}
many: "Two or more places" {
  class: grp
''' + n("b1", "One AI call", "overview, a summary per place, one list", "ai") + \
    n("b2", "Grounding per place", "each place against its own data", "sys") + \
    n("b3", "Fixed layout", "sections per place, 1 card per place", "ok") + '''
  b1 -> b2 -> b3
}
''' + n("fb", "Fallback within 20 s", "same layout built from the data", "sys") + \
    e("in", "k") + e("k", "one.a1", "1") + e("k", "many.b1", "2 or more") + \
    e("one", "fb", "late or wrong twice", DASH) + e("many", "fb", "late or wrong twice", DASH)

# ---------------------------------------------------------------------------------------------- d16 RAG
D["d16_rag"] = "direction: down\n" + '''
ing: "Ingestion (scripts/ingest_policy.py)" {
  class: grp
  direction: right
''' + n("p1", "Policy document", "expense_policy.txt") + \
    n("p2", "Chunker", "one rule = one chunk") + \
    n("p3", "Embed", "MiniLM, 384 dims", "ai") + \
    n("p4", "policy_chunks", "84 chunks", "db") + '''
  p1 -> p2 -> p3 -> p4
}
ret: "Retrieval (POLICY turns)" {
  class: grp
  direction: right
''' + n("q1", "Queries", "words + previous question + procedure", "ai") + \
    n("q2", "Top 4 by cosine", "keep similarity >= 0.35") + \
    n("q3", "Answer", "steps + rules, cited", "ai") + '''
  q1 -> q2 -> q3
}
''' + n("q4", "No match", "'not in the policy' + Finance contact", "sys") + \
    e("ing.p4", "ret.q2", "cached vectors", DASH) + e("ret.q2", "q4", "nothing >= 0.35")

# ---------------------------------------------------------------------------------------------- d17 session
D["d17_session"] = "direction: down\n" + \
    'start: "" {shape: circle; width: 22; height: 22; style: {fill: "#0F172A"; stroke: "#0F172A"}}\n' + \
    n("ac", "ACTIVE", ["memory = this session only;", "one active chat per employee"], "ok") + \
    n("cl", "CLOSED", "X clicked, or replaced") + \
    n("ex", "EXPIRED", "60 minutes idle", "bad") + \
    n("pc", "Past chats", ["kept in PostgreSQL, read-only;", "never loaded into a new chat"], "note") + \
    e("start", "ac", "Vera icon clicked") + e("ac", "ac", "each message = new turn") + \
    e("ac", "cl", "close / replace") + e("ac", "ex", "idle") + e("cl", "pc", "", DASH) + e("ex", "pc", "", DASH)

# ---------------------------------------------------------------------------------------------- d18 errors
D["d18_errors_tracing"] = "direction: down\n" + \
    n("rq", "HTTP request", "optional X-Correlation-ID", "emp") + \
    n("mw", "Middleware", "request_id + correlation_id") + \
    n("sv", "Router and service", "raise AppError or fail") + \
    n("eh", "Error handler", "envelope with ids, retryable", "sys") + \
    n("cl", "Client", "message + request id", "emp") + \
    n("el", "error_logs", "own transaction; 5xx stack traces", "db") + \
    n("js", "JSON log", "fallback if the write fails") + \
    n("ids", "Same correlation_id on", "chat_conversations, ai / rag / weather logs") + \
    e("rq", "mw") + e("mw", "sv") + e("sv", "eh") + e("eh", "cl", "4xx / 5xx") + e("eh", "el") + \
    e("el", "js", "write fails", DASH) + e("mw", "ids", "", DASH)


# ---------------------------------------------------------------------------------------------- ER (sql_table)
def er_table(name, only=None):
    t = next(x for x in TABLES if x["name"] == name)
    pk = set()
    fks, uks = set(), set()
    for c in t["cons"] or []:
        cols = c["def"][c["def"].find("(") + 1: c["def"].find(")")].replace(" ", "").split(",")
        if c["type"] == "p": pk |= set(cols)
        if c["type"] == "f": fks |= set(cols)
        if c["type"] == "u" and len(cols) == 1: uks |= set(cols)
    rows = []
    for c in t["cols"]:
        if only and c["col"] not in only:
            continue
        typ = c["type"].replace("timestamp with time zone", "timestamptz").replace("character(64)", "char(64)") \
            .replace("double precision", "float8").replace("character(3)", "char(3)").replace("[]", " array")
        cons = [k for k, s in (("primary_key", pk), ("foreign_key", fks), ("unique", uks)) if c["col"] in s]
        cs = f" {{constraint: [{'; '.join(cons)}]}}" if cons else ""
        rows.append(f'  {c["col"]}: "{typ}"{cs}')
    if only:
        rows.append('  "...": "see its own figure"')
    return f'w_{name}: {{\n  label: ""\n  style: {{fill: transparent; stroke: transparent}}\n  {name}: {{\n  shape: sql_table\n  style: {{fill: "#115E59"; stroke: "#FFFFFF"; font-color: "#FFFFFF"; font-size: 16}}\n' + "\n".join(rows) + "\n  }\n}\n"


ERHEAD = "grid-columns: 2\ngrid-gap: 50\n"


def rel(a, ac, b, bc, label=""):
    """FK edge between wrapped tables: child column -> parent column."""
    lab = f': "{label}"' if label else ""
    return f"w_{a}.{a}.{ac} -> w_{b}.{b}.{bc}{lab}\n"


D["d19_er_trips"] = ERHEAD + er_table("travel_requests") + er_table("employees") + er_table("trip_approvals") + \
    rel("travel_requests", "employee_id", "employees", "employee_id") + rel("travel_requests", "completed_by", "employees", "employee_id") + \
    rel("trip_approvals", "trip_id", "travel_requests", "trip_id") + rel("trip_approvals", "reviewer_id", "employees", "employee_id")
D["d20_er_tickets"] = ERHEAD + er_table("expenses") + er_table("expense_tickets") + er_table("policy_flags") + \
    er_table("ticket_approvals") + er_table("travel_requests", ["trip_id", "trip_code", "created_on"]) + \
    rel("expense_tickets", "trip_id", "travel_requests", "trip_id") + rel("expenses", "ticket_id", "expense_tickets", "ticket_id") + \
    rel("expenses", "trip_id", "travel_requests", "trip_id") + rel("policy_flags", "expense_id", "expenses", "expense_id") + \
    rel("ticket_approvals", "ticket_id", "expense_tickets", "ticket_id")
D["d20b_er_evidence"] = ERHEAD + er_table("receipt_checks") + er_table("expense_evidence") + \
    er_table("expenses", ["expense_id", "evidence_id", "receipt_verdict", "receipt_checks"]) + er_table("evidence_files") + \
    rel("expenses", "evidence_id", "expense_evidence", "evidence_id") + rel("evidence_files", "evidence_id", "expense_evidence", "evidence_id") + \
    rel("receipt_checks", "evidence_id", "expense_evidence", "evidence_id")
D["d21_er_chat"] = ERHEAD + er_table("chat_conversations") + er_table("chat_messages") + er_table("chat_sessions") + \
    er_table("policy_chunks") + er_table("employees", ["employee_id", "full_name"]) + \
    rel("chat_sessions", "employee_id", "employees", "employee_id") + rel("chat_conversations", "session_id", "chat_sessions", "session_id") + \
    rel("chat_messages", "session_id", "chat_sessions", "session_id") + rel("chat_messages", "conversation_id", "chat_conversations", "conversation_id")
D["d22_er_logs"] = ERHEAD + er_table("ai_call_logs") + er_table("rag_call_logs") + er_table("weather_tool_logs") + \
    er_table("chat_sessions", ["session_id", "employee_id"]) + er_table("chat_conversations", ["conversation_id", "session_id"]) + \
    "".join(rel(t, c, p_, c) for t in ("ai_call_logs", "rag_call_logs", "weather_tool_logs")
            for c, p_ in (("session_id", "chat_sessions"), ("conversation_id", "chat_conversations")))
D["d22b_er_errors"] = er_table("error_logs")

def render(names=None):
    for name, body in D.items():
        if names and name not in names:
            continue
        src = SRC / f"{name}.d2"
        src.write_text(HEAD + body, encoding="utf-8")
        svg = SRC / f"{name}.svg"
        r = subprocess.run(["d2", "--elk-nodeNodeBetweenLayers=34", "--elk-edgeNodeBetweenLayers=18", "--elk-padding=[top=36,left=20,bottom=20,right=20]", str(src), str(svg)], capture_output=True, text=True)
        if r.returncode != 0:
            print("FAILED", name, r.stderr[-600:]); continue
        out = subprocess.run(["node", str(HERE / "svg2png.js"), str(svg), str(PNG / f"{name}.png")], capture_output=True, text=True)
        print(out.stdout.strip() or out.stderr[-300:])


if __name__ == "__main__":
    render(sys.argv[1:] or None)

"""
chat/guardrails.py - Vera's input and output safety checks (owner: Piyush, M2).

Input (before the LLM):
  G2  more than CHAT_RATE_LIMIT_PER_MINUTE messages a minute -> 429 (length 1..1000 is Pydantic's 422)
  G3  personal data (email, phone, PAN, Aadhaar, card numbers with Luhn, passport) -> masked, continue
  G4  prompt injection / abuse -> fixed polite reply, NO LLM call (turn stored as BLOCKED)
Output (before the reply is shown):
  O3  promises, bookings, safety guarantees, claims about the user's trips/tickets,
      severe-weather warnings -> the sentence is replaced with the boundary text
  O4  HTML / script tags stripped, internal error details replaced, max 1,200 characters
(G1 is the router's job; G5 is tool validation; O1/O2 live in ai/output_validators.py.)
Regex guardrails can miss new phrasings: tools are read-only and take no ids, so a miss
cannot reach business data (see Risks in the spec).
"""
import re
import threading
import time
from collections import defaultdict, deque

from app.ai import prompts
from app.core.config import get_settings
from app.schemas import GuardrailResult, GuardrailStatus

# ----------------------------------------------------------------------------- G2 rate limit
_calls: dict[int, deque] = defaultdict(deque)
_calls_lock = threading.Lock()


def within_rate_limit(employee_id: int) -> bool:
    """Sliding 60-second window per employee.
    shortcut: in-memory, per backend process; move to a DB/Redis counter if several workers run."""
    now = time.monotonic()
    with _calls_lock:
        window = _calls[employee_id]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= get_settings().chat_rate_limit_per_minute:
            return False
        window.append(now)
        return True


def reset_rate_limits() -> None:
    """Tests only."""
    with _calls_lock:
        _calls.clear()


# ----------------------------------------------------------------------------- G3 personal data
def _luhn_ok(digits: str) -> bool:
    """Card-number checksum, so 16-digit invoice numbers are not masked by mistake."""
    total, double = 0, False
    for ch in reversed(digits):
        d = int(ch) * (2 if double else 1)
        total += d - 9 if d > 9 else d
        double = not double
    return total % 10 == 0


_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_PII = [  # (label, pattern) - order matters: cards first, they contain long digit runs
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("aadhaar", re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")),
    ("phone", re.compile(r"(?<!\d)(?:\+91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)")),
    ("pan", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("passport", re.compile(r"\b[A-PR-WY][1-9]\d{6}\b")),
]


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Replace personal data with [REDACTED_<TYPE>]; return masked text and reasons like 'pii:phone'."""
    reasons = []

    def card(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            reasons.append("pii:card")
            return "[REDACTED_CARD]"
        return m.group(0)

    text = _CARD.sub(card, text)
    for label, pattern in _PII:
        if pattern.search(text):
            reasons.append(f"pii:{label}")
            text = pattern.sub(f"[REDACTED_{label.upper()}]", text)
    return text, sorted(set(reasons))


# ----------------------------------------------------------------------------- G4 injection / abuse
_INJECTION = [
    ("ignore_previous", r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all|your|the)\b"
                        r".{0,20}\b(instructions?|rules?|prompts?|guidelines?)\b"),
    ("reveal_prompt", r"\b(reveal|show|print|repeat|tell me|what is|what's)\b.{0,25}\b(system prompt|your prompt|"
                      r"your instructions|hidden instructions)\b"),
    ("role_play", r"\b(act as|pretend to be|you are now|behave as|roleplay as)\b.{0,25}\b(manager|admin\w*|developer|"
                  r"system|approver|finance)\b"),
    ("developer_mode", r"\b(developer mode|jailbreak|dan mode|do anything now|sudo mode)\b"),
    ("tool_abuse", r"\b(call|use|run)\b.{0,20}\b(tool|function)\b.{0,30}\b(trip_id|ticket_id|employee_id|sql|database)\b"),
]
_INJECTION = [(name, re.compile(p, re.I | re.S)) for name, p in _INJECTION]
_ABUSE = re.compile(r"\b(fuck\w*|shit\w*|bastard|idiot|stupid bot|moron|asshole)\b", re.I)


def check_input(message: str) -> GuardrailResult:
    """Run G3 and G4 on one employee message (G2 is checked separately, before the turn exists)."""
    masked, reasons = mask_pii(message)
    blocked = [f"injection:{name}" for name, p in _INJECTION if p.search(masked)]
    if _ABUSE.search(masked):
        blocked.append("abuse")
    if blocked:
        return GuardrailResult(status=GuardrailStatus.INPUT_BLOCKED, sanitized_text=masked,
                               reasons=reasons + blocked, blocked_reply=prompts.BLOCKED_REPLY)
    status = GuardrailStatus.INPUT_REDACTED if reasons else GuardrailStatus.PASSED
    return GuardrailResult(status=status, sanitized_text=masked, reasons=reasons)


# ----------------------------------------------------------------------------- O3 / O4 output
# Aimed at claims about THIS user's records or promises ("your ticket will be approved"),
# not at general policy explanations ("a ticket with no flags is approved automatically").
_UNSUPPORTED = re.compile(
    r"\b(your (trip|ticket|claim|expense|request|reimbursement)s? (will be|has been|have been|was|were|is now|is already)"
    r" (approved|rejected|reimbursed|paid|accepted|completed|submitted|booked)|"
    r"you will (be reimbursed|get reimbursed|get paid|be paid)|"
    r"i (have |'ve )?(approved|rejected|submitted|booked|edited|cancelled)\b|i will (approve|book|submit|reimburse)|"
    r"(i |we )?guarantee\w*|it is (completely |perfectly )?safe to travel|it's safe to travel|"
    r"severe weather|weather (warning|alert)|red alert|cyclone warning)", re.I)
_HTML = re.compile(r"<[^>]{1,200}>")
_INTERNAL = re.compile(r"(traceback|exception|sqlalchemy|psycopg|stack trace|sk-or-|api[_ ]key|\.py\b)", re.I)
MAX_REPLY_CHARS = 1200


def check_output(text: str) -> tuple[str, list[str]]:
    """O3 + O4. Returns (safe text, reasons). Reasons are empty when nothing had to change."""
    reasons = []
    if _HTML.search(text):
        text, reasons = _HTML.sub("", text), reasons + ["output:html_stripped"]
    if _INTERNAL.search(text):
        return prompts.AI_UNAVAILABLE, reasons + ["output:internal_details"]
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept, replaced = [], False
    for s in sentences:
        if _UNSUPPORTED.search(s):
            if not replaced:          # one boundary sentence is enough
                kept.append(prompts.BOUNDARY_ACTION)
            replaced = True
        else:
            kept.append(s)
    if replaced:
        text, reasons = " ".join(kept), reasons + ["output:unsupported_claim"]
    if len(text) > MAX_REPLY_CHARS:
        cut = text[:MAX_REPLY_CHARS]
        text, reasons = cut[: cut.rfind(" ")].rstrip() + " ...", reasons + ["output:trimmed"]
    return text, reasons

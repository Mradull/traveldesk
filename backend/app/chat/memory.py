"""
chat/memory.py - what Vera remembers: ONLY the current session (owner: Piyush, M2).

* recent_turns(): the last CHAT_HISTORY_TURNS turns of THIS session, read from chat_messages.
* session_weather(): every weather result already fetched in THIS session (output check O1
  accepts numbers from these, so "what should I pack?" can reuse the earlier forecast).
* maybe_summarize(): when a session passes 8 turns, older turns of this session are summarised
  by the LLM (feature SUMMARY) into chat_sessions.summary; if the AI is down they are dropped.
Another session's messages are never loaded, so a new chat starts with empty memory.
"""
import json
import logging
from dataclasses import dataclass, field
from uuid import UUID

from langchain_core.messages import HumanMessage

from app.ai import llm_client, prompts
from app.core.config import get_settings
from app.core.database import transaction
from app.repositories import chat_repo
from app.schemas import AIFeature, MessageType, ToolContext, ToolName, ToolResult, WeatherForecastResult

log = logging.getLogger("traveldesk.chat")


@dataclass
class Turn:
    turn_number: int
    human: str = ""
    ai: str = ""
    tool_outputs: list[tuple[str, str]] = field(default_factory=list)   # (tool name, ToolResult JSON)


def _group(rows) -> list[Turn]:
    """Rows ordered by turn and sequence -> one Turn per turn_number."""
    turns: dict[int, Turn] = {}
    for r in rows:
        t = turns.setdefault(r["turn_number"], Turn(r["turn_number"]))
        if r["message_type"] == MessageType.HUMAN_MESSAGE.value:
            t.human = r["content"]
        elif r["message_type"] == MessageType.AI_RESPONSE.value:
            t.ai = r["content"]
        elif r["message_type"] == MessageType.TOOL_RESPONSE.value:
            t.tool_outputs.append((r["tool_name"], r["content"]))
    return [turns[k] for k in sorted(turns)]


def recent_turns(session_id: UUID, current_turn: int) -> list[Turn]:
    """Completed turns of this session inside the history window (oldest first)."""
    first = max(1, current_turn - get_settings().chat_history_turns)
    with transaction() as conn:
        rows = chat_repo.list_messages(conn, session_id, from_turn=first, to_turn=current_turn - 1)
    return [t for t in _group(rows) if t.human and t.ai]


def session_weather(session_id: UUID) -> list[WeatherForecastResult]:
    """All successful weather tool results of this session (for grounding follow-up answers)."""
    with transaction() as conn:
        rows = chat_repo.list_messages(conn, session_id)
    found = []
    for r in rows:
        if r["message_type"] == MessageType.TOOL_RESPONSE.value and r["tool_name"] == ToolName.GET_WEATHER_FORECAST.value:
            result = ToolResult.model_validate_json(r["content"])
            if result.ok and isinstance(result.data, dict):
                found.append(WeatherForecastResult.model_validate(result.data))
    return found


def tool_digest(name: str, content: str) -> str:
    """One-line description of an older tool result (full JSON is kept only for the last 2 turns)."""
    try:
        result = ToolResult.model_validate_json(content)
    except ValueError:
        return f"{name}: (unreadable)"
    if not result.ok:
        return f"{name}: failed ({result.error_code.value if result.error_code else 'error'})"
    if name == ToolName.SEARCH_EXPENSE_POLICY.value:
        return f"{name}: retrieved {', '.join(c['ref_id'] for c in result.data) or 'nothing'}"
    data = result.data or {}
    return f"{name}: {data.get('resolved_location')} {data.get('requested_from')}..{data.get('requested_to')} {data.get('status')}"


def maybe_summarize(session: dict, current_turn: int, ctx: ToolContext) -> str | None:
    """Return the session summary, first folding in turns that just left the history window."""
    window_start = current_turn - get_settings().chat_history_turns        # turns before this are "older"
    done = session["summarized_upto_turn"] or 0
    if window_start - 1 <= done:
        return session["summary"]
    with transaction() as conn:
        rows = chat_repo.list_messages(conn, ctx.session_id, from_turn=done + 1, to_turn=window_start - 1)
    text = "\n".join(f"Employee: {t.human}\nVera: {t.ai}" for t in _group(rows))
    try:
        reply = llm_client.invoke([HumanMessage(prompts.SUMMARY_PROMPT.format(
            old=session["summary"] or "(none)", messages=text))], feature=AIFeature.SUMMARY, ctx=ctx)
        summary = llm_client.content_text(reply).strip()[:1600]          # ~400 tokens
    except llm_client.LLMError:
        log.warning(json.dumps({"event": "summary_skipped", "session_id": str(ctx.session_id)}))
        summary = session["summary"]                                     # older turns are simply dropped
    with transaction() as conn:
        chat_repo.update_summary(conn, ctx.session_id, summary or "", window_start - 1)
    return summary

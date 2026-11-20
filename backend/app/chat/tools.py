"""
chat/tools.py - Vera's ONLY two tools (owner: Piyush, M2).

  search_expense_policy(query)                        -> RAG over the expense policy
  get_weather_forecast(destination, start_date, end_date) -> Open-Meteo via WeatherService

Both are LangChain @tool functions whose args_schema comes from schemas.py; neither has
an id argument, so the LLM has no way to ask for trips, tickets or any business record.
The server-side ToolContext (employee/session/conversation/correlation ids, used only for
logging) is put in a ContextVar for the turn: the LLM never sees it.
Both tools return ToolResult JSON, even on errors, so the LLM always gets the same shape.
"""
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

from langchain_core.tools import tool

from app.core.config import get_settings
from app.rag import retriever
from app.schemas import (ErrorCode, RagCallLog, RetrievedChunk, SearchPolicyInput, ToolContext, ToolResult,
                         WeatherToolInput)
from app.services import weather_service


@dataclass
class TurnState:
    """Per-turn data shared with the tools without passing it through the LLM."""
    ctx: ToolContext
    tool_call_id: str | None = None
    rag_logs: list[RagCallLog] = field(default_factory=list)   # written at the end of the turn


current_turn: ContextVar[TurnState] = ContextVar("current_turn")


@tool("search_expense_policy", args_schema=SearchPolicyInput)
def search_expense_policy(query: str) -> str:
    """Search the Veridian expense policy and TravelDesk guide. Returns the matching rules with their ids
    (e.g. POL-6.2) and text. Use it for every policy, limit, claim or how-to question."""
    turn = current_turn.get()
    started = time.monotonic()
    log = dict(session_id=turn.ctx.session_id, conversation_id=turn.ctx.conversation_id,
               correlation_id=turn.ctx.correlation_id, query_text=query[:300], top_k=get_settings().rag_top_k)
    try:
        top = retriever.top_chunks(query)
    except retriever.RetrievalError:
        turn.rag_logs.append(RagCallLog(**log, status="FAILED", error_code=ErrorCode.POLICY_RETRIEVAL_FAILED,
                                        latency_ms=int((time.monotonic() - started) * 1000)))
        return ToolResult(ok=False, error_code=ErrorCode.POLICY_RETRIEVAL_FAILED, retryable=True,
                          error_message="Policy information is temporarily unavailable.").model_dump_json()
    kept: list[RetrievedChunk] = [c for c in top if c.similarity >= get_settings().rag_min_similarity]
    turn.rag_logs.append(RagCallLog(**log, retrieved_ref_ids=[c.ref_id for c in top],
                                    retrieval_scores=[c.similarity for c in top],
                                    status="SUCCESS" if kept else "NO_MATCH",
                                    latency_ms=int((time.monotonic() - started) * 1000)))
    return ToolResult(ok=True, data=[c.model_dump() for c in kept]).model_dump_json()


@tool("get_weather_forecast", args_schema=WeatherToolInput)
def get_weather_forecast(destination: str, start_date: str, end_date: str) -> str:
    """Daily forecast (condition, min/max temperature, rain chance, rain amount, max wind) for a destination
    and dates the employee typed in this chat. Call it only when all three are known."""
    turn = current_turn.get()
    args = {"destination": destination, "start_date": str(start_date), "end_date": str(end_date)}
    return weather_service.get_weather_forecast(args, turn.ctx, turn.tool_call_id).model_dump_json()


TOOLS_BY_NAME = {t.name: t for t in (search_expense_policy, get_weather_forecast)}


def run_tool(name: str, args: dict) -> ToolResult:
    """Execute one tool call from the LLM. Bad arguments never reach Open-Meteo or the database:
    the weather service validates its own inputs (G5); here unknown fields and bad queries are refused."""
    if name == "get_weather_forecast":
        # call the service directly so missing/extra arguments map to the spec's weather error codes
        turn = current_turn.get()
        return weather_service.get_weather_forecast(args, turn.ctx, turn.tool_call_id)
    if set(args) - {"query"} or not isinstance(args.get("query"), str) or not 3 <= len(args["query"].strip()) <= 300:
        return ToolResult(ok=False, error_code=ErrorCode.VALIDATION_ERROR,
                          error_message="search_expense_policy takes one 'query' text of 3-300 characters.")
    return ToolResult.model_validate_json(search_expense_policy.invoke({"query": args["query"].strip()}))

"""
chat/chat_service.py - one Vera turn, end to end (owner: Piyush, M2).

Steps (spec "Request flow"):
 1 session checks (owner 404, ACTIVE 410, idle 410) + rate limit (429)
 2 input guardrails: mask personal data; injection/abuse -> fixed reply, no LLM (BLOCKED)
 3 new conversation_id + turn_number; store human_message (masked)
 4 intent router -> allowed tools (GREETING / OUT_OF_SCOPE get fixed replies, no LLM)
 5 context: system prompt + this session's summary + last 8 turns + the message
 6 LLM round 1 with the allowed tools; each ai_tool_call / tool_response stored in order.
   A POLICY intent always retrieves, even if the model forgot to call the tool.
 7 answers + output guardrails:
     policy  -> LLM answers from the chunks only; citations checked (O2), regenerated once
     weather -> card JSON from the LLM checked against the data (O1), regenerated once,
                else a template built from the data; non-data outcomes get fixed texts
     then O3/O4 on the whole reply
 8 store ai_response (citations / weather card in metadata), conversation outcome,
   RAG logs, last_activity_at; return ChatReplyOut
Failures: a tool failure gives a 200 reply with PARTIAL/FAILED; an LLM failure in round 1 stores
a safe reply, marks the turn FAILED and raises LLMError (-> 503/429 envelope). Business features
are never touched here.
"""
import json
import time
import uuid
from dataclasses import dataclass, field
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app import schemas
from app.ai import llm_client, output_validators, prompts
from app.chat import context_builder, formatter, guardrails, intent_router, memory, session_manager, tools
from app.core.config import get_settings
from app.core.database import transaction
from app.core.errors import AppError
from app.rag import retriever
from app.repositories import chat_repo, log_repo
from app.schemas import (ChatIntent, ChatReplyOut, Citation, ConversationStatus, CurrentUser, ErrorCategory, ErrorCode,
                         ErrorLogRecord, ErrorSeverity, GuardrailStatus, IntentDecision, MessageType, RetrievedChunk,
                         ToolContext, ToolName, ToolResult, ToolTrace, VeraWeatherAnswer, VeraWeatherLLMOutput,
                         WeatherForecastResult, WeatherStatus)

POLICY, WEATHER = ToolName.SEARCH_EXPENSE_POLICY.value, ToolName.GET_WEATHER_FORECAST.value


# ----------------------------------------------------------------------------- persistence helper
class TurnRecorder:
    """Stores the ordered message events of one turn. Each event is committed on its own,
    so the transcript survives even if a later step fails or the backend restarts."""

    def __init__(self, session_id: UUID, conversation_id: UUID):
        self.session_id, self.conversation_id, self.seq = session_id, conversation_id, 0

    def add(self, message_type: MessageType, content: str, **extra) -> int:
        self.seq += 1
        with transaction() as conn:
            return chat_repo.add_message(conn, session_id=self.session_id, conversation_id=self.conversation_id,
                                         sequence_no=self.seq, message_type=message_type.value, content=content,
                                         **extra)


@dataclass
class Outcome:
    """Everything the turn produced, before it is stored and returned."""
    intent: ChatIntent
    reply: str = ""
    citations: list[Citation] = field(default_factory=list)
    weather: VeraWeatherAnswer | None = None
    traces: list[ToolTrace] = field(default_factory=list)
    errors: list[ToolResult] = field(default_factory=list)   # failed tool results / failed answer steps
    successes: int = 0
    reasons: list[str] = field(default_factory=list)          # guardrail reasons (pii:..., output:...)
    intent_reason: str = ""


# ----------------------------------------------------------------------------- entry point
def handle_message(user: CurrentUser, session_id: UUID, message: str,
                   request_id: str | None, correlation_id: str | None) -> ChatReplyOut:
    started = time.monotonic()
    correlation_id = correlation_id or str(uuid.uuid4())

    # 1. G1 session checks, then G2 rate limit (before anything is stored)
    session_manager.ensure_active(user, session_id)
    if not guardrails.within_rate_limit(user.employee_id):
        raise AppError(ErrorCode.CHAT_RATE_LIMITED, 429, "You're sending messages too quickly. Please wait a moment.",
                       retryable=True)

    # 2. G3/G4 input guardrails
    checked = guardrails.check_input(message)

    # 3. new turn + human_message (session row locked so turn numbers never collide)
    with transaction() as conn:
        session = dict(chat_repo.get_session(conn, session_id, get_settings().chat_idle_timeout_minutes, for_update=True))
        conv = chat_repo.create_conversation(conn, session_id, request_id, correlation_id,
                                             llm_client.provider_and_model()[1])
        chat_repo.touch_session(conn, session_id)
        previous = chat_repo.last_intent(conn, session_id, conv["turn_number"])
    rec = TurnRecorder(session_id, conv["conversation_id"])
    rec.add(MessageType.HUMAN_MESSAGE, checked.sanitized_text)
    ctx = ToolContext(employee_id=user.employee_id, session_id=session_id,
                      conversation_id=conv["conversation_id"], correlation_id=correlation_id)
    state = tools.TurnState(ctx=ctx)
    token = tools.current_turn.set(state)
    try:
        if checked.status == GuardrailStatus.INPUT_BLOCKED:
            out = Outcome(intent=ChatIntent.OUT_OF_SCOPE, reply=checked.blocked_reply, reasons=checked.reasons,
                          intent_reason="blocked")
            status = ConversationStatus.BLOCKED
        else:
            # 4. route
            decision = intent_router.route(checked.sanitized_text, ChatIntent(previous) if previous else None,
                                           retriever.best_similarity)
            out = _answer(decision, checked.sanitized_text, session, conv["turn_number"], ctx, rec)
            out.reasons = checked.reasons + out.reasons
            status = _status(out)
    except llm_client.LLMError as exc:
        _finish(rec, ctx, state, Outcome(intent=ChatIntent.OUT_OF_SCOPE, reply=prompts.AI_UNAVAILABLE,
                                         reasons=checked.reasons, intent_reason="ai_failure"),
                ConversationStatus.FAILED, checked.status, exc.code, started)
        raise
    except Exception:
        _finish(rec, ctx, state, Outcome(intent=ChatIntent.OUT_OF_SCOPE, reply=prompts.AI_UNAVAILABLE,
                                         intent_reason="unexpected"),
                ConversationStatus.FAILED, checked.status, ErrorCode.INTERNAL_ERROR, started)
        raise
    finally:
        tools.current_turn.reset(token)

    error_code = out.errors[0].error_code if out.errors else None
    guardrail = _guardrail_status(checked.status, out.reasons)
    _finish(rec, ctx, state, out, status, guardrail, error_code, started)
    return ChatReplyOut(session_id=session_id, conversation_id=conv["conversation_id"],
                        turn_number=conv["turn_number"], intent=out.intent, reply=out.reply, citations=out.citations,
                        weather=out.weather, tools_used=out.traces, guardrail_status=guardrail, status=status,
                        error_code=error_code, retryable=any(e.retryable for e in out.errors),
                        created_at=conv["created_at"])


# ----------------------------------------------------------------------------- the answer
def _answer(decision: IntentDecision, text: str, session: dict, turn: int, ctx: ToolContext,
            rec: TurnRecorder) -> Outcome:
    out = Outcome(intent=decision.intent, intent_reason=decision.reason)
    if decision.intent == ChatIntent.GREETING:
        word = text.lower()
        key = "thanks" if "thank" in word or "thx" in word else "bye" if "bye" in word or "see you" in word else "hello"
        out.reply = prompts.GREETING_REPLIES[key]
        return out
    if decision.intent == ChatIntent.OUT_OF_SCOPE:
        out.reply = {"business_data": prompts.BOUNDARY_BUSINESS,
                     "action_request": prompts.BOUNDARY_ACTION}.get(decision.reason, prompts.BOUNDARY_GENERAL)
        return out

    # 5. context from THIS session only
    summary = memory.maybe_summarize(session, turn, ctx)
    turns = memory.recent_turns(ctx.session_id, turn)
    # the employee's previous question in THIS chat: a short follow-up ("What about ground transport?")
    # carries its topic there, so policy search uses both texts together when needed
    previous_question = turns[-1].human if turns else None
    bundle = context_builder.build(turns, summary, text, decision.allowed_tools, schemas.today())
    messages = context_builder.to_messages(bundle)
    allowed = [t.value for t in decision.allowed_tools]

    # 6. LLM round 1 with only the allowed tools (an LLMError here fails the turn)
    first = llm_client.invoke(messages, tools=[tools.TOOLS_BY_NAME[n] for n in allowed], ctx=ctx)
    calls = [c for c in first.tool_calls if c["name"] in allowed][: get_settings().chat_max_tool_calls_per_turn]
    if POLICY in allowed and not any(c["name"] == POLICY for c in calls):
        # policy is never answered from memory: retrieve with the employee's own words
        # (for an inherited follow-up, together with the previous question of this chat)
        query = text if not decision.reason.startswith("inherited") else _with_previous(previous_question, text)
        calls.append({"name": POLICY, "args": {"query": query}, "id": f"auto-{uuid.uuid4().hex[:12]}"})
    if not calls:
        return _direct_reply(out, first, messages, decision, ctx)

    executed = [(c, _run_and_store(c, rec, out)) for c in calls]
    if previous_question and _policy_found_nothing(executed):
        # follow-up whose own words matched no rule: search once more with the previous question added
        retry = {"name": POLICY, "args": {"query": _with_previous(previous_question, text)},
                 "id": f"auto-{uuid.uuid4().hex[:12]}"}
        executed.append((retry, _run_and_store(retry, rec, out)))

    # 7a. policy part
    parts: list[str] = []
    policy_runs = [(c, r) for c, r in executed if c["name"] == POLICY]
    weather_runs = [(c, r) for c, r in executed if c["name"] == WEATHER]
    if policy_runs:
        parts.append(_policy_part(policy_runs, messages, ctx, out, has_other_part=bool(weather_runs)))
    # 7b. weather part (the last weather call of the turn is the one shown)
    if weather_runs:
        parts.append(_weather_part(weather_runs[-1][1], text, ctx, out))
    out.reply = _output_checks("\n\n".join(p for p in parts if p), out)
    return out


def _with_previous(previous_question: str | None, text: str) -> str:
    """Search text for a follow-up: previous question of this chat + the new message (max 300 chars)."""
    return (f"{previous_question} {text}" if previous_question else text)[-300:]


def _policy_found_nothing(executed: list) -> bool:
    """True when the policy tool ran, worked, and no chunk reached the similarity floor (NO_MATCH)."""
    runs = [r for c, r in executed if c["name"] == POLICY]
    return bool(runs) and all(r.ok for r in runs) and not any(r.data for r in runs)


def _run_and_store(call: dict, rec: TurnRecorder, out: Outcome) -> ToolResult:
    """Run one tool call and store the ai_tool_call / tool_response pair, linked by tool_call_id."""
    call_id = call.get("id") or f"call-{uuid.uuid4().hex[:12]}"
    args = {k: (guardrails.mask_pii(v)[0] if isinstance(v, str) else v) for k, v in (call.get("args") or {}).items()}
    rec.add(MessageType.AI_TOOL_CALL, json.dumps({"name": call["name"], "args": args}, default=str),
            tool_name=call["name"], tool_call_id=call_id, tool_args=json.loads(json.dumps(args, default=str)))
    tools.current_turn.get().tool_call_id = call_id
    started = time.monotonic()
    result = tools.run_tool(call["name"], args)
    latency = int((time.monotonic() - started) * 1000)
    rec.add(MessageType.TOOL_RESPONSE, result.model_dump_json(), tool_name=call["name"], tool_call_id=call_id,
            metadata={"latency_ms": latency, "error_code": result.error_code.value if result.error_code else None})
    out.traces.append(ToolTrace(tool_name=call["name"], status="ok" if result.ok else "error",
                                error_code=result.error_code, latency_ms=latency))
    if result.ok:
        out.successes += 1
    else:
        out.errors.append(result)
    return result


def _policy_part(runs, messages, ctx: ToolContext, out: Outcome, has_other_part: bool) -> str:
    """Answer from the retrieved chunks only, with checked citations (O2)."""
    chunks: dict[int, RetrievedChunk] = {}
    for _, r in runs:
        if r.ok:
            for c in r.data:
                chunks.setdefault(c["chunk_id"], RetrievedChunk(**c))
    if not any(r.ok for _, r in runs):
        _store_error(ctx, ErrorCode.POLICY_RETRIEVAL_FAILED, "policy retrieval failed", ErrorCategory.RAG)
        return prompts.POLICY_UNAVAILABLE              # never an uncited rule
    if not chunks:
        return prompts.POLICY_NO_MATCH                 # nothing reached the 0.35 similarity floor

    found = list(chunks.values())
    tool_calls = [{"name": POLICY, "args": c["args"], "id": c.get("id") or "auto"} for c, _ in runs]
    convo = messages + [AIMessage(content="", tool_calls=tool_calls)] + [
        ToolMessage(content=json.dumps([{"ref_id": x["ref_id"], "title": x["section_title"], "text": x["content"]}
                                        for x in (r.data or [])]), tool_call_id=tc["id"])
        for (_, r), tc in zip(runs, tool_calls)] + [HumanMessage(prompts.POLICY_ANSWER_RULES)]
    try:
        answer = llm_client.content_text(llm_client.invoke(convo, ctx=ctx)).strip()
        check = output_validators.check_citations(answer, found)
        if not check.ok:                               # regenerate once
            out.reasons.append("output:citation_regenerated")
            note = prompts.POLICY_RETRY_NOTE.format(ids=", ".join(sorted({c.ref_id for c in found})))
            answer = llm_client.content_text(llm_client.invoke(
                convo + [AIMessage(answer), HumanMessage(note)], ctx=ctx)).strip()
            check = output_validators.check_citations(answer, found)
    except llm_client.LLMError as exc:
        if not has_other_part:
            raise                                      # nothing else to show: fail the turn (503/429)
        out.errors.append(ToolResult(ok=False, error_code=exc.code, retryable=exc.retryable))
        return prompts.AI_UNAVAILABLE
    if check.invalid:
        answer = output_validators.remove_citations(answer, check.invalid)
    if not check.valid or check.bad_amounts:
        out.reasons.append("output:policy_unavailable")
        return prompts.POLICY_UNAVAILABLE
    out.citations = formatter.citations(found, check.valid)
    _mark_citations(check.valid)
    return answer


def _mark_citations(ids: list[str]) -> None:
    """Fill citations_used on this turn's successful RAG log rows (written at the end of the turn)."""
    for entry in tools.current_turn.get().rag_logs:
        if entry.status == "SUCCESS":
            entry.citations_used = [i for i in ids if i in entry.retrieved_ref_ids]


def _weather_part(result: ToolResult, question: str, ctx: ToolContext, out: Outcome) -> str:
    """Weather card for forecasts with values; fixed honest text for every other outcome."""
    fixed = formatter.weather_status_reply(result)
    if not result.ok:
        return fixed
    forecast = WeatherForecastResult.model_validate(result.data)
    if not forecast.days:
        if forecast.status == WeatherStatus.FORECAST_OUT_OF_RANGE:
            out.weather = formatter.weather_answer(forecast, formatter.template_weather_output(forecast))
        return fixed
    card = _weather_card(forecast, question, ctx, out)
    out.weather = formatter.weather_answer(forecast, card)
    return formatter.weather_reply_text(out.weather)


def _weather_card(forecast: WeatherForecastResult, question: str, ctx: ToolContext,
                  out: Outcome) -> VeraWeatherLLMOutput:
    """LLM writes summary/checklist/limitations from the data; O1 checks it; one retry; then template."""
    facts = output_validators.weather_facts([forecast])
    convo = [SystemMessage(prompts.WEATHER_CARD_PROMPT.format(data=formatter.compact_weather_for_llm(forecast))),
             HumanMessage(question)]
    try:
        for attempt in (1, 2):
            card = llm_client.invoke_json(convo, VeraWeatherLLMOutput, ctx=ctx)
            if card is None:
                problems = ["not valid JSON in the required shape"]
            else:
                problems = output_validators.check_weather_grounding(
                    " ".join([card.weather_summary, *card.travel_checklist, *card.limitations]), facts)
                if not problems:
                    return card
            if attempt == 1:
                convo = convo + [HumanMessage(prompts.WEATHER_CARD_RETRY_NOTE.format(problems="; ".join(problems)))]
    except llm_client.LLMError:
        out.reasons.append("output:weather_template_ai_down")
        return formatter.template_weather_output(forecast)
    out.reasons.append("output:weather_rewritten")
    return formatter.template_weather_output(forecast)


def _direct_reply(out: Outcome, first: AIMessage, messages, decision: IntentDecision, ctx: ToolContext) -> Outcome:
    """The model answered without a tool (e.g. asks for missing dates, or packing advice from the
    forecast already fetched in THIS session). Weather numbers/conditions must still be grounded."""
    reply = llm_client.content_text(first).strip()
    if decision.intent in (ChatIntent.WEATHER, ChatIntent.POLICY_AND_WEATHER):
        earlier = memory.session_weather(ctx.session_id)
        facts = output_validators.weather_facts(earlier)
        problems = output_validators.check_weather_grounding(reply, facts)
        if problems:
            note = prompts.WEATHER_CARD_RETRY_NOTE.format(problems="; ".join(problems))
            reply = llm_client.content_text(llm_client.invoke(messages + [AIMessage(reply), HumanMessage(note)],
                                                              ctx=ctx)).strip()
            if output_validators.check_weather_grounding(reply, facts):
                out.reasons.append("output:weather_rewritten")
                if earlier:   # rebuild the answer from the forecast already fetched in this session
                    reply = formatter.weather_reply_text(formatter.weather_answer(
                        earlier[-1], formatter.template_weather_output(earlier[-1])))
                else:
                    reply = prompts.WEATHER_NEEDS_INPUTS
    out.reply = _output_checks(reply or prompts.WEATHER_NEEDS_INPUTS, out)
    return out


# ----------------------------------------------------------------------------- finishing
def _output_checks(text: str, out: Outcome) -> str:
    """O3 + O4 on the whole reply."""
    safe, reasons = guardrails.check_output(text)
    out.reasons.extend(reasons)
    return safe


def _status(out: Outcome) -> ConversationStatus:
    if not out.errors:
        return ConversationStatus.COMPLETED
    return ConversationStatus.PARTIAL if out.successes else ConversationStatus.FAILED


def _guardrail_status(input_status: GuardrailStatus, reasons: list[str]) -> GuardrailStatus:
    if input_status == GuardrailStatus.INPUT_BLOCKED:
        return input_status
    if any(r.startswith("output:") for r in reasons):
        return GuardrailStatus.OUTPUT_REWRITTEN
    return input_status


def _store_error(ctx: ToolContext, code: ErrorCode, internal: str, category: ErrorCategory) -> None:
    """error_logs row for a failure that still ends in a 200 reply (e.g. RAG down)."""
    log_repo.log_safely(log_repo.insert_error_log, ErrorLogRecord(
        severity=ErrorSeverity.ERROR, source_component="chat.policy_tool", category=category, error_code=code,
        safe_message=prompts.POLICY_UNAVAILABLE, internal_message=internal, retryable=True,
        correlation_id=ctx.correlation_id, employee_id=ctx.employee_id, session_id=ctx.session_id,
        conversation_id=ctx.conversation_id))


def _finish(rec: TurnRecorder, ctx: ToolContext, state: tools.TurnState, out: Outcome, status: ConversationStatus,
            guardrail: GuardrailStatus, error_code: ErrorCode | None, started: float) -> None:
    """8. store ai_response + turn outcome + RAG logs, and restart the idle timer."""
    latency = int((time.monotonic() - started) * 1000)
    rec.add(MessageType.AI_RESPONSE, out.reply, metadata={
        "citations": [c.model_dump() for c in out.citations],
        "weather": out.weather.model_dump(mode="json") if out.weather else None,
        "tools_used": [t.model_dump(mode="json") for t in out.traces],
        "intent_reason": out.intent_reason, "error_code": error_code.value if error_code else None,
        "guardrail_reasons": out.reasons, "latency_ms": latency})
    with transaction() as conn:
        chat_repo.finish_conversation(conn, ctx.conversation_id, intent=out.intent.value, status=status.value,
                                      guardrail_status=guardrail.value, guardrail_reasons=out.reasons,
                                      error_code=error_code.value if error_code else None, latency_ms=latency)
        chat_repo.touch_session(conn, ctx.session_id)
    for entry in state.rag_logs:
        log_repo.log_safely(log_repo.insert_rag_call_log, entry)

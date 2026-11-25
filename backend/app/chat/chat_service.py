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
import re
from concurrent.futures import ThreadPoolExecutor, wait
import time
import uuid
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel, Field
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
# "what should I do to get reimbursed?", "how do I claim my dinner?": the answer needs the STEPS
# (raise a ticket, attach the receipt photo) as well as the rules, so Vera also searches the procedure
CLAIM_QUESTION = re.compile(r"\b(reimburs\w*|claim\w*|get (my )?money back|get paid|what (should|do) i do|"
                            r"how (do|can|should) i (claim|submit|get|raise|add))\b", re.I)
PROCEDURE_QUERY = "Raising an expense ticket: receipt photo required for every expense line, submit the ticket"
# date ranges in a message ("2nd to 4th", "5-7 Dec", "8th and 9th", "2026-12-01 to 2026-12-05"):
# each one is usually one destination, so it tells us how many weather lookups the employee expects
DAY_RANGE = re.compile(r"(?<![\d-])\d{1,2}(?:st|nd|rd|th)?\s*(?:to|till|until|and|-|–)\s*\d{1,2}(?:st|nd|rd|th)?(?![\d-])",
                       re.I)
ISO_RANGE = re.compile(r"\d{4}-\d{2}-\d{2}\s*(?:to|-|–)\s*\d{4}-\d{2}-\d{2}")
DAY_LIST = re.compile(r"(?<![\d-])\d{1,2}(?:st|nd|rd|th)?(?:\s*,\s*\d{1,2}(?:st|nd|rd|th)?)+(?![\d-])")   # "1,2,3"
class _TripCity(BaseModel):
    place: str
    summary: str = Field(min_length=1, max_length=350)


class _TripWeatherOut(BaseModel):
    """What the AI writes for a multi-place trip; the layout around it is fixed by code."""
    overview: str = Field(min_length=1, max_length=350)
    cities: list[_TripCity]
    travel_checklist: list[str] = Field(min_length=3, max_length=6)


# Time budget for writing the weather texts of one answer. The AI writes all cities AT THE SAME TIME;
# any city whose text is not ready in time gets the grounded fallback text, so a 4-city answer never
# waits minutes on a slow free-tier model.
WEATHER_CARDS_BUDGET_SECONDS = 20


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
    weather_cards: list[VeraWeatherAnswer] = field(default_factory=list)   # one per city, in order
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
                        weather=out.weather, weather_cards=out.weather_cards, tools_used=out.traces, guardrail_status=guardrail, status=status,
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
    if (POLICY in allowed and CLAIM_QUESTION.search(text)
            and len(calls) < get_settings().chat_max_tool_calls_per_turn):
        calls.append({"name": POLICY, "args": {"query": PROCEDURE_QUERY}, "id": f"auto-{uuid.uuid4().hex[:12]}"})
    if not calls:
        return _direct_reply(out, first, messages, decision, ctx)

    executed = [(c, _run_and_store(c, rec, out)) for c in calls]
    if WEATHER in allowed:
        executed += _remaining_destinations(text, messages, executed, rec, ctx, out)
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
    # 7b. weather part(s)
    # one part per weather lookup ("Rome 1-3 Dec, then Catania 4-7 Dec"); the card shows the last one
    parts.extend(_weather_parts([result for _, result in weather_runs], text, ctx, out))
    out.reply = _output_checks("\n\n".join(p for p in parts if p), out)
    return out


def _expected_destinations(text: str) -> int:
    """How many trip legs the message lists ("Delhi 2nd to 4th, Mumbai 5th to 7th, Chennai 8th and 9th" = 3)."""
    return len(DAY_RANGE.findall(text)) + len(ISO_RANGE.findall(text)) + len(DAY_LIST.findall(text))


def _remaining_destinations(text: str, messages: list, executed: list, rec: TurnRecorder,
                            ctx: ToolContext, out: Outcome) -> list:
    """The model sometimes looks up only the first of several destinations. If the message lists more
    trip legs than were looked up, show the model what it has done and ask once more for the rest.
    One extra LLM call, only in that case; never more lookups than the per-turn tool budget."""
    done = [c for c, _ in executed if c["name"] == WEATHER]
    budget = get_settings().chat_max_tool_calls_per_turn - len(executed)
    if not done or len(done) >= _expected_destinations(text) or budget <= 0:
        return []
    ids = [c.get("id") or f"call-{i}" for i, (c, _) in enumerate(executed)]       # pair calls with results
    convo = messages + [AIMessage(content="", tool_calls=[
        {"name": c["name"], "args": c.get("args") or {}, "id": i} for (c, _), i in zip(executed, ids)])] + [
        ToolMessage(content=r.model_dump_json()[:1500], tool_call_id=i) for (_, r), i in zip(executed, ids)] + [
        HumanMessage(prompts.MORE_DESTINATIONS_NOTE.format(done=", ".join(c["args"].get("destination", "?")
                                                                          for c in done)))]
    try:
        more = llm_client.invoke(convo, tools=[tools.TOOLS_BY_NAME[WEATHER]], ctx=ctx)
    except llm_client.LLMError:
        return []                                     # keep the destinations we already have
    seen = {json.dumps(c.get("args"), sort_keys=True) for c in done}
    new = [c for c in more.tool_calls
           if c["name"] == WEATHER and json.dumps(c.get("args"), sort_keys=True) not in seen][:budget]
    return [(c, _run_and_store(c, rec, out)) for c in new]


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


def _weather_parts(results: list[ToolResult], question: str, ctx: ToolContext, out: Outcome) -> list[str]:
    """One text + card per weather lookup, in the order the employee listed the places.
    Forecasts with values: the AI writes their texts in parallel, within WEATHER_CARDS_BUDGET_SECONDS;
    late or failed ones use the grounded template. Other outcomes (errors, out of range, place not
    found) get fixed honest texts."""
    texts: list[str | None] = [None] * len(results)
    answers: list[VeraWeatherAnswer | None] = [None] * len(results)
    jobs: dict[int, WeatherForecastResult] = {}
    for i, result in enumerate(results):
        if not result.ok:
            texts[i] = formatter.weather_status_reply(result)
            continue
        forecast = WeatherForecastResult.model_validate(result.data)
        if forecast.days:
            jobs[i] = forecast
            continue
        texts[i] = formatter.weather_status_reply(result)
        if forecast.status == WeatherStatus.FORECAST_OUT_OF_RANGE:
            answers[i] = formatter.weather_answer(forecast, formatter.template_weather_output(forecast))

    if len(jobs) >= 2:
        # several places: ONE answer for the whole trip (overview, a short section per place, one packing
        # list), written by ONE AI call within the time budget; otherwise the same layout from the data
        order = sorted(jobs)
        forecasts = [jobs[i] for i in order]
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(_trip_text, forecasts, ctx, out)
        done, _ = wait([future], timeout=WEATHER_CARDS_BUDGET_SECONDS)
        pool.shutdown(wait=False, cancel_futures=True)
        written = future.result() if future in done and future.exception() is None else None
        if written is None:
            if future not in done:
                out.reasons.append("output:weather_template_slow")
            written = formatter.trip_fallback(forecasts)
        texts[order[0]] = formatter.trip_reply_text(forecasts, *written)
        for i, forecast in zip(order, forecasts):          # cards: daily tables, from the data
            answers[i] = formatter.weather_answer(forecast, formatter.template_weather_output(forecast))
        jobs = {}

    if jobs:
        # all cities at once; shutdown(wait=False) so a stuck call never holds the reply back
        pool = ThreadPoolExecutor(max_workers=min(4, len(jobs)))
        futures = {i: pool.submit(_weather_card, forecast, question, ctx, out) for i, forecast in jobs.items()}
        done, _ = wait(futures.values(), timeout=WEATHER_CARDS_BUDGET_SECONDS)
        pool.shutdown(wait=False, cancel_futures=True)
        for i, forecast in jobs.items():
            future = futures[i]
            if future in done and future.exception() is None:
                card = future.result()
            else:                                  # too slow or crashed: the grounded template, right away
                out.reasons.append("output:weather_template_slow")
                card = formatter.template_weather_output(forecast)
            answers[i] = formatter.weather_answer(forecast, card)
            texts[i] = formatter.weather_reply_text(answers[i])

    for answer in answers:                         # cards in the employee's order; `weather` = the last one
        if answer is not None:
            out.weather_cards.append(answer)
            out.weather = answer
    return [t for t in texts if t]


def _trip_text(forecasts: list[WeatherForecastResult], ctx: ToolContext,
               out: Outcome) -> tuple[str, list[str], list[str]] | None:
    """One AI call writes the overview, one summary per place and one packing list. Each place's summary is
    checked against THAT place's data; overview and packing list against the trip's data. One retry.
    Returns None when the AI is down or still wrong (the caller then uses the data-based layout)."""
    data = json.dumps([{"place": formatter.city_name(f), **json.loads(formatter.compact_weather_for_llm(f))}
                       for f in forecasts])
    convo = [SystemMessage(prompts.TRIP_WEATHER_PROMPT.format(data=data)),
             HumanMessage("Write the weather part for this trip.")]
    all_facts = output_validators.weather_facts(forecasts)
    try:
        for attempt in (1, 2):
            trip = llm_client.invoke_json(convo, _TripWeatherOut, ctx=ctx)
            if trip is None:
                problems = ["not valid JSON in the required shape"]
            elif len(trip.cities) != len(forecasts):
                problems = [f"expected {len(forecasts)} places in 'cities', got {len(trip.cities)}"]
            else:
                problems = [f"{formatter.city_name(f)}: {p}" for f, c in zip(forecasts, trip.cities)
                            for p in output_validators.check_weather_grounding(
                                c.summary, output_validators.weather_facts([f]))]
                problems += output_validators.check_weather_grounding(
                    " ".join([trip.overview, *trip.travel_checklist]), all_facts)
                if not problems:
                    overview = (f"Here's the weather for your {len(forecasts)}-stop trip "
                                f"({formatter.trip_dates(forecasts)}). {trip.overview}")
                    return overview, [c.summary for c in trip.cities], trip.travel_checklist
            if attempt == 1:
                convo = convo + [HumanMessage(prompts.WEATHER_CARD_RETRY_NOTE.format(problems="; ".join(problems)))]
    except llm_client.LLMError:
        out.reasons.append("output:weather_template_ai_down")
        return None
    out.reasons.append("output:weather_rewritten")
    return None


def _weather_card(forecast: WeatherForecastResult, question: str, ctx: ToolContext,
                  out: Outcome) -> VeraWeatherLLMOutput:
    """LLM writes summary/checklist/limitations from the data; O1 checks it; one retry; then template."""
    facts = output_validators.weather_facts([forecast])
    place = forecast.resolved_location or forecast.destination
    # one city at a time: never the employee's whole multi-city message, so the text cannot talk about
    # (or wrongly "rule out") the other places
    convo = [SystemMessage(prompts.WEATHER_CARD_PROMPT.format(data=formatter.compact_weather_for_llm(forecast))),
             HumanMessage(prompts.WEATHER_CARD_REQUEST.format(
                 place=place, dates=formatter._date_list(forecast.covered_dates or forecast.uncovered_dates)))]
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
        "weather_cards": [c.model_dump(mode="json") for c in out.weather_cards],
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

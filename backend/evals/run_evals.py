"""
evals/run_evals.py - Vera's eval suite (owner: Piyush, M2; datasets: Mradul, M3).

Run from backend/ (after init_db.py and ingest_policy.py):
    python -m evals.run_evals --suite all          # or one suite name, e.g. --suite routing
Writes evals/reports/eval_report_<timestamp>.json (git-ignored) and prints a summary.

EVAL_USE_LIVE_LLM=false (default): deterministic suites only, no AI calls, no network
  (Open-Meteo is mocked with respx; the weather card is the code template).
EVAL_USE_LIVE_LLM=true: also runs policy_qa, platform_howto, weather_missing_inputs, memory
  and latency through the real chat pipeline, and lets the real model write the weather cards.
Datasets: evals/datasets/<suite>.jsonl, one JSON object per line (format in datasets/README.md).
"""
import argparse
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import respx
from sqlalchemy import text

from app import schemas
from app.ai import output_validators as ov
from app.chat import chat_service, context_builder, formatter, guardrails, intent_router, memory, session_manager
from app.core.config import get_settings
from app.core.database import transaction
from app.rag import retriever
from app.repositories import chat_repo
from app.schemas import (ChatIntent, CurrentUser, DailyForecast, GuardrailStatus, MessageType,
                         WeatherForecastResult, WeatherStatus)
from app.services import weather_service
from evals.metrics import LATENCY_P95_TARGET_MS, SUITES, contains_all, has_weather_values, p95, suite_summary

HERE = Path(__file__).resolve().parent
LATENCIES: list[float] = []          # every live turn, for the latency suite


def load(suite: str) -> list[dict]:
    path = HERE / "datasets" / f"{suite}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def eval_user() -> CurrentUser:
    """The first seeded EMPLOYEE (Rohan in the seed) owns the eval chats."""
    with transaction() as conn:
        row = conn.execute(text("SELECT employee_id, full_name, email, department, role, manager_id FROM employees "
                                "WHERE role = 'EMPLOYEE' ORDER BY employee_id LIMIT 1")).mappings().one()
    return CurrentUser(**row)


def live_turn(user: CurrentUser, session_id, message: str):
    """One real Vera turn (rate limiter reset so long eval runs are not throttled)."""
    guardrails.reset_rate_limits()
    started = time.monotonic()
    reply = chat_service.handle_message(user, session_id, message, "eval", f"eval-{uuid.uuid4().hex[:8]}")
    LATENCIES.append((time.monotonic() - started) * 1000)
    return reply


def forecast_from_case(case: dict) -> WeatherForecastResult:
    """Build a mocked tool result: days given as offsets from today."""
    today = schemas.today()
    days = [DailyForecast(**{**{k: v for k, v in d.items() if k != "day_offset"},
                             "date": today + timedelta(days=d["day_offset"]),
                             "condition": weather_service.wmo_condition(d.get("weather_code"))})
            for d in case["days"]]
    return WeatherForecastResult(status=WeatherStatus.AVAILABLE, destination=case.get("destination", "Testville"),
                                 resolved_location=case.get("destination", "Testville"),
                                 requested_from=days[0].date, requested_to=days[-1].date,
                                 covered_dates=[d.date for d in days], days=days, retrieved_at=datetime.now(timezone.utc))


def weather_card_text(case: dict, live: bool):
    f = forecast_from_case(case)
    if live:
        card = chat_service._weather_card(f, case.get("question", "What will the weather be?"), None,
                                          chat_service.Outcome(intent=ChatIntent.WEATHER))
    else:
        card = formatter.template_weather_output(f)
    return f, card


# ----------------------------------------------------------------------------- suites
def s_routing(case, live):
    prev = ChatIntent(case["previous_intent"]) if case.get("previous_intent") else None
    d = intent_router.route(case["message"], prev, retriever.best_similarity)
    ok = d.intent.value == case["expected_intent"] and [t.value for t in d.allowed_tools] == case["expected_tools"]
    return ok, f"got {d.intent.value} {[t.value for t in d.allowed_tools]} ({d.reason})"


def s_retrieval(case, live):
    ids = [c.ref_id for c in retriever.top_chunks(case["query"])]
    return case["expected_ref_id"] in ids, f"top ids {ids}"


def s_weather_grounding(case, live):
    f, card = weather_card_text(case, live)
    problems = ov.check_weather_grounding(" ".join([card.weather_summary, *card.travel_checklist]),
                                          ov.weather_facts([f]))
    return not problems, "; ".join(problems) or card.weather_summary


def s_packing_grounding(case, live):
    f, card = weather_card_text(case, live)
    checklist = " ".join(card.travel_checklist)
    problems = ov.check_weather_grounding(checklist, ov.weather_facts([f]))
    missing = contains_all(checklist, case.get("must_include", []))
    forbidden = [w for w in case.get("must_not_include", []) if w.lower() in checklist.lower()]
    return not (problems or missing or forbidden), f"problems={problems} missing={missing} forbidden={forbidden}"


def _mock_weather(case, mock):
    mock.get(get_settings().weather_geocoding_url).mock(return_value=httpx.Response(200, json={"results": [
        {"name": case["destination"], "country": "Testland", "latitude": 1.0, "longitude": 1.0, "population": 500000}]}))
    failure = case.get("failure")
    route = mock.get(get_settings().weather_forecast_url)
    if failure == "timeout":
        route.mock(side_effect=httpx.TimeoutException("slow"))
    elif failure == "invalid_json":
        route.mock(return_value=httpx.Response(200, text="<html>"))
    elif failure:
        route.mock(return_value=httpx.Response(int(failure)))
    else:
        route.mock(return_value=httpx.Response(500))      # must not be called for out-of-range


def _weather_offline(case):
    weather_service.clear_cache()
    today = schemas.today()
    args = {"destination": case["destination"],
            "start_date": (today + timedelta(days=case["start_offset"])).isoformat(),
            "end_date": (today + timedelta(days=case["end_offset"])).isoformat()}
    with respx.mock(assert_all_called=False) as mock:
        _mock_weather(case, mock)
        result = weather_service.get_weather_forecast(args)
    return result, formatter.weather_status_reply(result) or ""


def s_out_of_range(case, live):
    result, reply = _weather_offline(case)
    data = result.data or {}
    ok = ("Forecast not available" in reply and not has_weather_values(reply) and data.get("days") == []
          and not ov.check_weather_grounding(reply, ov.weather_facts([])))
    return ok, reply


def s_weather_failure(case, live):
    result, reply = _weather_offline(case)
    ok = not result.ok and result.data is None and reply and not has_weather_values(reply)
    return ok, f"{result.error_code} {reply}"


def s_boundary(case, live):
    d = intent_router.route(case["message"])
    out = chat_service._answer(d, case["message"], {}, 1, None, None)
    ok = d.intent == ChatIntent.OUT_OF_SCOPE and not out.traces and all(
        w.lower() in out.reply.lower() for w in case.get("expected_keywords", []))
    return ok, out.reply


def s_injection_pii(case, live):
    r = guardrails.check_input(case["message"])
    expected = {"blocked": GuardrailStatus.INPUT_BLOCKED, "masked": GuardrailStatus.INPUT_REDACTED}[case["expected"]]
    ok = r.status == expected and all(x in r.reasons for x in case.get("expected_reasons", []))
    ok = ok and all(s not in r.sanitized_text for s in case.get("must_not_contain", []))
    return ok, f"{r.status.value} {r.reasons} -> {r.sanitized_text}"


def s_session_boundary(case, live):
    user = eval_user()
    first = session_manager.open_session(user).session_id
    with transaction() as conn:                              # session A remembers the destination
        conv = chat_repo.create_conversation(conn, first, "eval", "eval", "eval")
        for seq, (kind, content) in enumerate([(MessageType.HUMAN_MESSAGE, case["first_message"]),
                                               (MessageType.AI_RESPONSE, case["first_reply"])], start=1):
            chat_repo.add_message(conn, session_id=first, conversation_id=conv["conversation_id"],
                                  sequence_no=seq, message_type=kind.value, content=content)
    second = session_manager.open_session(user).session_id   # session B must not
    bundle = context_builder.build(memory.recent_turns(second, 1), None, case["second_message"], [], schemas.today())
    leaked = case["forbidden"].lower() in json.dumps(bundle.model_dump()).lower()
    return not leaked, "previous destination leaked into the new session" if leaked else "clean"


def s_policy_live(case, live):
    user = eval_user()
    reply = live_turn(user, session_manager.open_session(user).session_id, case["question"])
    missing = contains_all(reply.reply, case.get("expected_keywords", []))
    cited = [c.ref_id for c in reply.citations]
    ok = not missing and (not case.get("expected_ref_ids") or any(r in cited for r in case["expected_ref_ids"]))
    return ok, f"missing={missing} cited={cited} reply={reply.reply[:200]}"


def s_missing_inputs(case, live):
    user = eval_user()
    reply = live_turn(user, session_manager.open_session(user).session_id, case["message"])
    called = [t.tool_name.value for t in reply.tools_used]
    return "get_weather_forecast" not in called and "?" in reply.reply, f"tools={called} reply={reply.reply[:200]}"


def s_memory(case, live):
    user = eval_user()
    sid = session_manager.open_session(user).session_id
    reply = None
    for message in case["turns"]:
        reply = live_turn(user, sid, message)
    missing = contains_all(reply.reply, case["expected_keywords"])
    return not missing, f"missing={missing} reply={reply.reply[:200]}"


RUNNERS = {"routing": s_routing, "retrieval": s_retrieval, "policy_qa": s_policy_live,
           "platform_howto": s_policy_live, "weather_grounding": s_weather_grounding,
           "weather_missing_inputs": s_missing_inputs, "out_of_range": s_out_of_range,
           "weather_failure": s_weather_failure, "packing_grounding": s_packing_grounding,
           "business_data_boundary": s_boundary, "boundaries": s_boundary, "injection_pii": s_injection_pii,
           "memory": s_memory, "session_boundary": s_session_boundary}


def run(suites: list[str]) -> dict:
    live = get_settings().eval_use_live_llm
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "live_llm": live,
              "model": get_settings().openrouter_model if live else None, "prompt_version": get_settings().prompt_version,
              "suites": {}}
    for name in suites:
        needs_live = SUITES[name][1]
        if needs_live and not live:
            report["suites"][name] = {"skipped": "needs EVAL_USE_LIVE_LLM=true"}
            continue
        cases = load(name)
        if not cases:
            report["suites"][name] = {"skipped": f"no dataset evals/datasets/{name}.jsonl"}
            continue
        results = []
        for case in cases:
            try:
                ok, detail = RUNNERS[name](case, live)
            except Exception as exc:  # noqa: BLE001 - a crashing case is a failed case
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            results.append({"id": case.get("id", "?"), "ok": bool(ok), "detail": str(detail)[:400]})
        report["suites"][name] = suite_summary(name, results)
    if live and LATENCIES:
        value = p95(LATENCIES)
        report["suites"]["latency"] = {"cases": len(LATENCIES), "p95_ms": round(value), "target_ms": LATENCY_P95_TARGET_MS,
                                       "pass": value < LATENCY_P95_TARGET_MS}
    ran = [s for s in report["suites"].values() if "skipped" not in s]
    report["overall_pass"] = bool(ran) and all(s["pass"] for s in ran)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Vera's eval suites")
    parser.add_argument("--suite", default="all", help="'all' or one of: " + ", ".join(SUITES))
    suites = list(SUITES) if (s := parser.parse_args().suite) == "all" else [s]
    report = run(suites)
    out = HERE / "reports" / f"eval_report_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for name, s in report["suites"].items():
        line = s.get("skipped") or (f"{s.get('score', s.get('p95_ms'))} (target {s.get('target', s.get('target_ms'))})"
                                    f" {'PASS' if s['pass'] else 'FAIL'}")
        print(f"{name:24} {line}")
    print(f"overall: {'PASS' if report['overall_pass'] else 'FAIL'}  ->  {out}")


if __name__ == "__main__":
    main()

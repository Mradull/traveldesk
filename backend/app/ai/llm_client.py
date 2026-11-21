"""
ai/llm_client.py - the ONLY place that talks to the AI provider (owner: Piyush, M2).

* Provider switch (AI_PROVIDER): openrouter (team choice, Nemotron free, reasoning off),
  gemini (its OpenAI-compatible endpoint) or azure. Keys are read from .env only.
* Timeout AI_TIMEOUT_SECONDS; one retry (AI_MAX_RETRIES) on timeout / 5xx / connection errors,
  never on 401/403/429.
* Failures become LLMError (an AppError): 503 AI_UNAVAILABLE, 429 AI_RATE_LIMITED, 503 AI_AUTH_ERROR.
* Every call writes one ai_call_logs row: provider, model, prompt version, status, latency,
  token counts, ids. Prompts and keys are never logged.
* It authorises nothing and never receives business records (it only sees chat text).
Tests replace the model with LangChain's fake chat model via set_chat_model().
"""
import json
import re
import time
from typing import Any, TypeVar

import httpx
import openai
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.errors import AppError
from app.repositories import log_repo
from app.schemas import AICallLog, AICallStatus, AIFeature, AIProvider, ErrorCode, ToolContext

M = TypeVar("M", bound=BaseModel)

_model: BaseChatModel | None = None


class LLMError(AppError):
    """The provider failed; the chat service stores a safe reply and lets this become the envelope."""


def _secret(value) -> str:
    """Plain text of a SecretStr setting ('' when not set)."""
    return value.get_secret_value() if value is not None else ""


def provider_and_model() -> tuple[AIProvider, str]:
    provider = AIProvider(get_settings().ai_provider)
    model = {AIProvider.OPENROUTER: get_settings().openrouter_model, AIProvider.GEMINI: get_settings().gemini_model,
             AIProvider.AZURE: get_settings().azure_openai_deployment}[provider]
    return provider, model


def _build_model() -> BaseChatModel:
    """Create the LangChain chat model for the configured provider (max_retries=0: we retry ourselves)."""
    from langchain_openai import AzureChatOpenAI, ChatOpenAI
    common = dict(temperature=get_settings().ai_temperature, max_tokens=get_settings().ai_max_output_tokens,
                  timeout=get_settings().ai_timeout_seconds, max_retries=0)
    provider, model = provider_and_model()
    if provider == AIProvider.OPENROUTER:
        return ChatOpenAI(model=model, api_key=_secret(get_settings().openrouter_api_key), base_url=get_settings().openrouter_base_url,
                          default_headers={"X-Title": get_settings().openrouter_app_title},
                          # Nemotron "thinks" by default; off = faster, plain answers.
                          extra_body={"reasoning": {"enabled": get_settings().openrouter_reasoning_enabled}}, **common)
    if provider == AIProvider.GEMINI:
        return ChatOpenAI(model=model, api_key=_secret(get_settings().gemini_api_key), base_url=get_settings().gemini_base_url, **common)
    return AzureChatOpenAI(azure_endpoint=get_settings().azure_openai_endpoint, api_key=_secret(get_settings().azure_openai_api_key),
                           azure_deployment=get_settings().azure_openai_deployment,
                           api_version=get_settings().azure_openai_api_version, **common)


def get_chat_model() -> BaseChatModel:
    global _model
    if _model is None:
        _model = _build_model()
    return _model


def set_chat_model(model: BaseChatModel | None) -> None:
    """Tests/evals: swap in a fake model (None = rebuild the real one on next use)."""
    global _model
    _model = model


def is_configured() -> tuple[bool, str]:
    """/health: is a key/model set for the chosen provider? (No network call, no quota used.)"""
    provider, model = provider_and_model()
    settings = get_settings()
    key = _secret({AIProvider.OPENROUTER: settings.openrouter_api_key, AIProvider.GEMINI: settings.gemini_api_key,
                   AIProvider.AZURE: settings.azure_openai_api_key}[provider])
    ok = bool(model) and bool(key) and "<" not in key and "change-me" not in key
    return ok, f"{provider.value}:{model}" if ok else f"{provider.value}: key or model missing in .env"


def _classify(exc: Exception) -> tuple[AICallStatus, ErrorCode, int, bool]:
    """Map a provider exception to (log status, error code, HTTP status, retry?)."""
    if isinstance(exc, (openai.APITimeoutError, httpx.TimeoutException, TimeoutError)):
        return AICallStatus.TIMEOUT, ErrorCode.AI_UNAVAILABLE, 503, True
    if isinstance(exc, openai.RateLimitError):
        return AICallStatus.RATE_LIMITED, ErrorCode.AI_RATE_LIMITED, 429, False
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return AICallStatus.AUTH_ERROR, ErrorCode.AI_AUTH_ERROR, 503, False
    if isinstance(exc, (openai.APIConnectionError, httpx.TransportError)):
        return AICallStatus.ERROR, ErrorCode.AI_UNAVAILABLE, 503, True
    if isinstance(exc, openai.APIStatusError):
        return AICallStatus.ERROR, ErrorCode.AI_UNAVAILABLE, 503, exc.status_code >= 500
    return AICallStatus.ERROR, ErrorCode.AI_UNAVAILABLE, 503, False


def _log(feature: AIFeature, status: AICallStatus, started: float, ctx: ToolContext | None,
         usage: dict | None = None, error_code: str | None = None) -> None:
    provider, model = provider_and_model()
    log_repo.log_safely(log_repo.insert_ai_call_log, AICallLog(
        feature=feature, provider=provider, model_name=model, prompt_version=get_settings().prompt_version,
        status=status, latency_ms=int((time.monotonic() - started) * 1000),
        prompt_tokens=(usage or {}).get("input_tokens"), completion_tokens=(usage or {}).get("output_tokens"),
        error_code=error_code, session_id=ctx.session_id if ctx else None,
        conversation_id=ctx.conversation_id if ctx else None,
        correlation_id=ctx.correlation_id if ctx else "no-correlation-id"))


def _call(messages: list[BaseMessage], tools: list | None, feature: AIFeature,
          ctx: ToolContext | None) -> tuple[AIMessage, float]:
    """Call the model with the retry policy. Failed attempts are logged here; the caller logs success."""
    model = get_chat_model()
    runnable = model.bind_tools(tools) if tools else model
    attempts = 1 + get_settings().ai_max_retries
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            return runnable.invoke(messages), started
        except Exception as exc:  # noqa: BLE001 - classified below
            status, code, http, retry = _classify(exc)
            _log(feature, status, started, ctx, error_code=code.value)
            if retry and attempt < attempts:
                continue          # one more try on timeout / 5xx / connection errors only
            raise LLMError(code, http, "Vera is unavailable right now. Everything else in TravelDesk works.",
                           retryable=code != ErrorCode.AI_AUTH_ERROR) from exc
    raise AssertionError("unreachable")


def invoke(messages: list[BaseMessage], *, tools: list | None = None, feature: AIFeature = AIFeature.CHAT,
           ctx: ToolContext | None = None) -> AIMessage:
    """One LLM call (with optional tools). Raises LLMError after the retry policy is exhausted."""
    reply, started = _call(messages, tools, feature, ctx)
    _log(feature, AICallStatus.SUCCESS, started, ctx, usage=getattr(reply, "usage_metadata", None))
    return reply


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def invoke_json(messages: list[BaseMessage], output_model: type[M], *, feature: AIFeature = AIFeature.CHAT,
                ctx: ToolContext | None = None) -> M | None:
    """Ask for JSON and validate it against output_model. Returns None (logged as INVALID_OUTPUT)
    when the text is not valid JSON for that schema - the caller then uses its template."""
    reply, started = _call(messages, None, feature, ctx)
    usage = getattr(reply, "usage_metadata", None)
    text = _FENCE.sub("", content_text(reply).strip())
    start, end = text.find("{"), text.rfind("}")
    try:
        parsed = output_model.model_validate(json.loads(text[start:end + 1]))
    except (ValueError, ValidationError) as exc:
        _log(feature, AICallStatus.INVALID_OUTPUT, started, ctx, usage=usage, error_code=type(exc).__name__)
        return None
    _log(feature, AICallStatus.SUCCESS, started, ctx, usage=usage)
    return parsed


def content_text(message: AIMessage) -> str:
    """Plain text of a reply (some providers return a list of content parts)."""
    content: Any = message.content
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")

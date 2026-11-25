"""Sightengine client (HTTP mocked with respx) and receipt reader (fake model). Owner: Mradul (M3)."""
from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from pydantic import SecretStr

from app.ai import llm_client, receipt_reader, sightengine_client
from app.core.config import get_settings

URL = "https://api.sightengine.com/1.0/check.json"


@pytest.fixture
def sightengine_keys(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "sightengine_api_user", "123")
    monkeypatch.setattr(settings, "sightengine_api_secret", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "sightengine_url", URL)


def test_not_configured_returns_none(monkeypatch):
    monkeypatch.setattr(get_settings(), "sightengine_api_user", "")
    assert sightengine_client.ai_generated_score(b"x", "image/jpeg") is None


@respx.mock
def test_score_is_read(sightengine_keys):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"status": "success", "type": {"ai_generated": 0.87}}))
    assert sightengine_client.ai_generated_score(b"\xff\xd8\xff", "image/jpeg") == pytest.approx(0.87)


@pytest.mark.parametrize("response, code", [
    (httpx.Response(429), "SIGHTENGINE_RATE_LIMITED"),
    (httpx.Response(500), "SIGHTENGINE_HTTP_500"),
    (httpx.Response(200, text="<html>"), "SIGHTENGINE_INVALID_RESPONSE"),
    (httpx.Response(200, json={"status": "failure", "error": {"type": "credentials_error"}}), "SIGHTENGINE_CREDENTIALS_ERROR"),
])
@respx.mock
def test_failures_raise_with_a_code(sightengine_keys, response, code):
    respx.post(URL).mock(return_value=response)
    with pytest.raises(sightengine_client.SightengineError) as err:
        sightengine_client.ai_generated_score(b"x", "image/jpeg")
    assert err.value.code == code


@respx.mock
def test_timeout(sightengine_keys):
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(sightengine_client.SightengineError) as err:
        sightengine_client.ai_generated_score(b"x", "image/jpeg")
    assert err.value.code == "SIGHTENGINE_TIMEOUT"


def test_reader_parses_the_model_json(monkeypatch):
    reply = ('```json\n{"is_receipt": true, "readable": true, "total_amount": 1850.0, "currency": "INR", '
             '"receipt_date": "2026-11-24", "merchant": "Hotel Blue", "city": "Bengaluru", "from_place": null, '
             '"to_place": null, "summary": "Dinner at Hotel Blue, Rs 1,850 on 24 Nov 2026."}\n```')
    llm_client.set_chat_model(FakeListChatModel(responses=[reply]))
    monkeypatch.setattr(get_settings(), "receipt_vision_model", "")
    try:
        out = receipt_reader.read_receipt(b"\xff\xd8\xff", "image/jpeg")
    finally:
        llm_client.set_chat_model(None)
    assert out.total_amount == Decimal("1850.0") and out.receipt_date == date(2026, 11, 24)
    assert out.city == "Bengaluru" and out.readable


def test_reader_returns_none_on_non_json(monkeypatch):
    llm_client.set_chat_model(FakeListChatModel(responses=["sorry, I cannot read this"]))
    monkeypatch.setattr(get_settings(), "receipt_vision_model", "")
    try:
        assert receipt_reader.read_receipt(b"x", "image/png") is None
    finally:
        llm_client.set_chat_model(None)

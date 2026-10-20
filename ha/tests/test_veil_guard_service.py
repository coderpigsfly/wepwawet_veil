"""veil_guard_service in a real Home Assistant: commands understood locally and by an LLM's tools are
asked about, allowed, refused with the router's message, or (no answer) allowed or blocked.
Run from ha/:  python -m pytest tests -q   (needs pytest-homeassistant-custom-component)"""

import asyncio

import pytest
from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import intent
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

ROUTER = "http://router.test:8770"


async def setup(hass: HomeAssistant, aioclient_mock, ask=True, check=None, **conf):
    aioclient_mock.get(f"{ROUTER}/firewall/summary", json={"ask": ask, "enabled": ask, "rules": 1 if ask else 0})
    if isinstance(check, Exception):
        aioclient_mock.post(f"{ROUTER}/firewall/check", exc=check)
    elif check is not None:
        aioclient_mock.post(f"{ROUTER}/firewall/check", json=check)
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    assert await async_setup_component(hass, "intent", {})
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen light"})
    hass.states.async_set("lock.front_door", "locked", {"friendly_name": "Front door"})
    calls = async_mock_service(hass, "light", "turn_on")
    assert await async_setup_component(hass, "veil_guard_service", {"veil_guard_service": {"url": ROUTER, "timeout": 0.5, **conf}})
    await hass.async_block_till_done()
    return calls


def checks(aioclient_mock):
    return [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/firewall/check")]


async def say(hass, text):
    result = await conversation.async_converse(hass, text, None, Context(), language="en")
    return result.response


@pytest.fixture(autouse=True)
def restore_async_handle():
    original = intent.async_handle
    yield
    intent.async_handle = original


async def test_firewall_off_never_asks(hass, aioclient_mock):
    calls = await setup(hass, aioclient_mock, ask=False)
    response = await say(hass, "turn on the kitchen light")
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    assert len(calls) == 1
    assert checks(aioclient_mock) == []


async def test_allowed_command_runs(hass, aioclient_mock):
    calls = await setup(hass, aioclient_mock, check={"allow": True})
    response = await say(hass, "turn on the kitchen light")
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    assert len(calls) == 1
    body = checks(aioclient_mock)[0][2]
    assert body["intent"] == "HassTurnOn"
    assert body["text"] == "turn on the kitchen light"
    assert "light.kitchen" in body["targets"] and "light" in body["domains"]


async def test_refused_command_never_runs_and_she_says_why(hass, aioclient_mock):
    calls = await setup(hass, aioclient_mock, check={"allow": False, "message": "Ask a grown-up, please."})
    response = await say(hass, "turn on the kitchen light")
    assert len(calls) == 0
    assert response.response_type == intent.IntentResponseType.ERROR
    assert response.speech["plain"]["speech"] == "Ask a grown-up, please."


async def test_llm_tool_path_is_checked_too(hass, aioclient_mock):
    """A language model's tool call reaches intent.async_handle the same way (helpers/llm.py)."""
    calls = await setup(hass, aioclient_mock, check={"allow": False, "message": "No."})
    response = await intent.async_handle(hass, "google_generative_ai_conversation", "HassTurnOn",
                                         {"name": {"value": "Kitchen light"}}, None, Context(), "en",
                                         device_id=None)
    assert len(calls) == 0
    assert response.speech["plain"]["speech"] == "No."
    body = checks(aioclient_mock)[0][2]
    assert body["text"] is None and body["platform"] == "google_generative_ai_conversation"


async def test_llm_tool_path_with_every_value_named(hass, aioclient_mock):
    """Home Assistant 2026.10's helpers/llm.py names every value (hass=..., platform=...)."""
    calls = await setup(hass, aioclient_mock, check={"allow": False, "message": "No."})
    response = await intent.async_handle(hass=hass, platform="conversation", intent_type="HassTurnOn",
                                         slots={"name": {"value": "Kitchen light"}}, text_input=None,
                                         context=Context(), language="en", assistant="conversation",
                                         device_id=None)
    assert len(calls) == 0
    assert response.speech["plain"]["speech"] == "No."
    body = checks(aioclient_mock)[0][2]
    assert body["intent"] == "HassTurnOn" and "light.kitchen" in body["targets"]


async def test_named_values_allowed_run(hass, aioclient_mock):
    calls = await setup(hass, aioclient_mock, check={"allow": True})
    response = await intent.async_handle(hass=hass, platform="conversation", intent_type="HassTurnOn",
                                         slots={"name": {"value": "Kitchen light"}}, context=Context(),
                                         language="en")
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    assert len(calls) == 1


async def test_a_lock_is_named_as_a_lock(hass, aioclient_mock):
    await setup(hass, aioclient_mock, check={"allow": False, "message": "No."})
    await intent.async_handle(hass, "test", "HassTurnOff", {"name": {"value": "front door"}}, None, Context(), "en")
    body = checks(aioclient_mock)[0][2]
    assert "lock" in body["domains"] and "lock.front_door" in body["targets"]


async def test_no_answer_allows_by_default(hass, aioclient_mock):
    calls = await setup(hass, aioclient_mock, check=asyncio.TimeoutError())
    await say(hass, "turn on the kitchen light")
    assert len(calls) == 1


async def test_no_answer_can_block(hass, aioclient_mock):
    calls = await setup(hass, aioclient_mock, check=asyncio.TimeoutError(), on_no_answer="block")
    response = await say(hass, "turn on the kitchen light")
    assert len(calls) == 0
    assert "can't check" in response.speech["plain"]["speech"]


async def test_read_only_commands_are_skipped(hass, aioclient_mock):
    await setup(hass, aioclient_mock, check={"allow": False, "message": "No."})
    await say(hass, "is the kitchen light on")
    assert checks(aioclient_mock) == []


async def test_router_unreachable_at_start_still_asks(hass, aioclient_mock):
    aioclient_mock.get(f"{ROUTER}/firewall/summary", exc=asyncio.TimeoutError())
    aioclient_mock.post(f"{ROUTER}/firewall/check", json={"allow": False, "message": "No."})
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    assert await async_setup_component(hass, "intent", {})
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen light"})
    calls = async_mock_service(hass, "light", "turn_on")
    assert await async_setup_component(hass, "veil_guard_service", {"veil_guard_service": {"url": ROUTER}})
    await say(hass, "turn on the kitchen light")
    assert len(calls) == 0

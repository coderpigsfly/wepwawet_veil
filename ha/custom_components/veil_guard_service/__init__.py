"""Veil Guard Service: Wepwawet Veil's hook in Home Assistant: the firewall for Home Assistant's own commands.

Every device command Home Assistant carries out by voice passes through one function,
homeassistant.helpers.intent.async_handle: the ones it understands itself ("Prefer handling
commands locally", in conversation/default_agent.py) and the ones a language model asks for
through Assist's tools (helpers/llm.py). This integration wraps that function. Before a command
runs, it asks Wepwawet Veil (POST /firewall/check on the router's chat door, port 8770): this
command, these targets, these words, from this satellite: may it run?

- The router answers "allow": the command goes straight on, exactly as Home Assistant meant.
- The router answers "not allowed": nothing is done, and she says the router's message
  ("Sorry, that's not something I can do for you.") as the command's answer.
- The router's firewall is off or has no rules: the guard knows (it asks /firewall/summary every
  summary_seconds) and doesn't ask about each command at all, so nothing is slowed down.
- The router doesn't answer in time: on_no_answer decides (allow, the default, keeps the house
  working; block keeps it safe).

The rules themselves live in the router (firewall.yaml, the Firewall page), with who spoke from
Oread. Nothing here knows about people.

Wrapping async_handle isn't an official extension point: an update to Home Assistant could move
it. The guard checks the function's shape at startup and, if it isn't what it expects, doesn't
wrap it and says so (in the log and as a notification), rather than failing quietly.

Configuration (a package file, e.g. /config/packages/veil_guard_service.yaml):

    veil_guard_service:
      url: http://192.168.1.20:8770        # the router's chat door
      token: !secret veil_guard_service_token      # only with security: guard_token_required in the router
      timeout: 4                           # seconds to wait for the router (set it here, in Home Assistant)
      on_no_answer: allow                  # or block
      summary_seconds: 30
      skip_intents: [HassNevermind, HassGetCurrentTime, HassGetCurrentDate, HassGetWeather, HassGetState]
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)
DOMAIN = "veil_guard_service"
VERSION = "1.1.0"            # 1.1.0: Home Assistant 2026.10 names every value (helpers/llm.py)
EXPECTED = ("hass", "platform", "intent_type", "slots", "text_input", "context", "language")
READ_ONLY = ["HassNevermind", "HassGetCurrentTime", "HassGetCurrentDate", "HassGetWeather", "HassGetState"]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("url"): cv.url,
                vol.Optional("token", default=""): cv.string,
                vol.Optional("timeout", default=4.0): vol.All(vol.Coerce(float), vol.Range(min=0.2, max=10)),
                vol.Optional("on_no_answer", default="allow"): vol.In(["allow", "block"]),
                vol.Optional("summary_seconds", default=30): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
                vol.Optional("skip_intents", default=READ_ONLY): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("message_no_answer", default="I can't check that right now, so I won't do it."): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


class Guard:
    """Asks the router about each command; remembers whether there's anything to ask about."""

    def __init__(self, hass: HomeAssistant, conf: dict[str, Any]) -> None:
        self.hass = hass
        self.url = conf["url"].rstrip("/")
        self.token = conf.get("token") or ""
        self.timeout = conf["timeout"]
        self.on_no_answer = conf["on_no_answer"]
        self.skip = {s.lower() for s in conf["skip_intents"]}
        self.message_no_answer = conf["message_no_answer"]
        self.ask = True            # until the router says otherwise, ask
        self.reachable = None
        self.last: dict[str, Any] = {}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def refresh(self, *_: Any) -> None:
        """Is the router's firewall on, with rules? (If not, commands aren't asked about.)"""
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(max(self.timeout, 3)):
                async with session.get(f"{self.url}/firewall/summary", headers=self._headers()) as r:
                    if r.status >= 300:
                        raise RuntimeError(f"the router answered {r.status}")
                    data = await r.json()
            ask = bool(data.get("ask"))
            if ask != self.ask or self.reachable is not True:
                _LOGGER.info("Wepwawet Veil's firewall: %s", "on, asking about commands" if ask
                             else "off or no rules, commands go straight through")
            self.ask, self.reachable = ask, True
        except Exception as err:  # keep asking while the router can't be reached
            if self.reachable is not False:
                _LOGGER.warning("Can't reach Wepwawet Veil at %s (%s); each command will be asked "
                                "about, and on_no_answer (%s) decides when it doesn't answer",
                                self.url, err, self.on_no_answer)
            self.ask, self.reachable = True, False

    def describe(self, intent_type: str, slots: dict | None, device_id: str | None,
                 satellite_id: str | None) -> dict[str, Any]:
        """What the command names: targets (names, areas, entity ids), their domains, the device."""
        targets: list[str] = []
        domains: set[str] = set()
        for key, slot in (slots or {}).items():
            value = slot.get("value") if isinstance(slot, dict) else slot
            values = value if isinstance(value, list) else [value]
            for v in values:
                if v is None or isinstance(v, (dict, bool)):
                    continue
                v = str(v)
                if key == "domain":
                    domains.add(v.lower())
                elif key in ("name", "area", "floor", "device_class") or key.endswith("_id"):
                    if key not in ("preferred_area_id", "preferred_floor_id"):
                        targets.append(v)
        # the entities a name means, so rules can name kinds of device (lock, cover)
        names = {t.lower() for t in targets}
        if names:
            ent_reg = er.async_get(self.hass)
            for state in self.hass.states.async_all():
                friendly = str(state.attributes.get("friendly_name") or "").lower()
                entry = ent_reg.async_get(state.entity_id)
                aliases = {a.lower() for a in (entry.aliases if entry else set()) if isinstance(a, str)}
                if friendly in names or state.entity_id.lower() in names or names & aliases:
                    targets.append(state.entity_id)
                    domains.add(state.domain)
        device_name = None
        if device_id:
            dev = dr.async_get(self.hass).async_get(device_id)
            if dev:
                device_name = dev.name_by_user or dev.name
        return {"intent": intent_type, "targets": targets, "domains": sorted(domains),
                "device_id": device_id, "device_name": device_name, "satellite_id": satellite_id}

    async def check(self, body: dict[str, Any]) -> dict[str, Any] | None:
        """The router's answer, or None when it didn't answer in time."""
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(self.timeout):
                async with session.post(f"{self.url}/firewall/check", json=body, headers=self._headers()) as r:
                    if r.status >= 300:
                        raise RuntimeError(f"the router answered {r.status}")
                    return await r.json()
        except Exception as err:
            _LOGGER.warning("Wepwawet Veil didn't answer about %s (%s): %s", body.get("intent"), err,
                            "allowing it" if self.on_no_answer == "allow" else "not doing it")
            return None


def _shape_ok() -> bool:
    try:
        params = list(inspect.signature(intent.async_handle).parameters)
    except (TypeError, ValueError):
        return False
    return params[: len(EXPECTED)] == list(EXPECTED)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the guard from YAML (a package file)."""
    conf = config.get(DOMAIN)
    if conf is None:
        return True
    if getattr(intent.async_handle, "_veil_guard_service", False):
        _LOGGER.info("Veil Guard Service is already in place")
        return True
    if not _shape_ok():
        msg = ("Veil Guard Service did NOT start: Home Assistant's intent.async_handle has changed shape in this "
               "version, so device commands are not checked by Wepwawet Veil's firewall. Open an issue with the "
               "Home Assistant version.")
        _LOGGER.error(msg)
        from homeassistant.components import persistent_notification
        persistent_notification.async_create(hass, msg, title="Veil Guard Service")
        return True

    guard = Guard(hass, conf)
    hass.data[DOMAIN] = guard
    original = intent.async_handle
    signature = inspect.signature(original)

    async def guarded(*args: Any, **kwargs: Any) -> intent.IntentResponse:
        # Home Assistant passes these in order, by name, or mixed (2026.10's language-model
        # tools name every one), so read them by name whichever way they came.
        try:
            given = signature.bind_partial(*args, **kwargs).arguments
        except TypeError:
            return await original(*args, **kwargs)
        extra = given.get("kwargs") or {}

        def arg(name: str) -> Any:
            return given.get(name, extra.get(name))

        hass_ = arg("hass") or hass
        intent_type = str(arg("intent_type") or "")
        language = arg("language")
        if guard.ask and intent_type.lower() not in guard.skip:
            body = guard.describe(intent_type, arg("slots"), arg("device_id"), arg("satellite_id"))
            body.update(text=arg("text_input"), platform=arg("platform"), language=language,
                        assistant=arg("assistant"), agent=arg("conversation_agent_id"))
            answer = await guard.check(body)
            guard.last = {"intent": intent_type, "answer": answer}
            refuse = None
            if answer is None:
                if guard.on_no_answer == "block":
                    refuse = guard.message_no_answer
            elif not answer.get("allow", True):
                refuse = answer.get("message") or "Sorry, that's not something I can do for you."
            if refuse is not None:
                _LOGGER.info("Veil Guard Service stopped %s %s: %s", intent_type, body["targets"],
                             (answer or {}).get("why") or "no answer from the router")
                response = intent.IntentResponse(language=language or hass_.config.language)
                response.async_set_error(intent.IntentResponseErrorCode.FAILED_TO_HANDLE, refuse)
                return response
        return await original(*args, **kwargs)

    guarded._veil_guard_service = True  # type: ignore[attr-defined]
    guarded._veil_original = original  # type: ignore[attr-defined]
    intent.async_handle = guarded
    await guard.refresh()
    async_track_time_interval(hass, guard.refresh, timedelta(seconds=conf["summary_seconds"]))
    _LOGGER.info("Veil Guard Service is checking Home Assistant's commands with Wepwawet Veil at %s", guard.url)
    _LOGGER.info("Veil Guard Service %s: a command check takes its values in order or by name", VERSION)
    return True

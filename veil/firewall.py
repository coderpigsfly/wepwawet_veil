# veil/firewall.py - who may use what: rules by person, from Oread's "who spoke".
# With Oread off every voice is "unknown": rules for anyone or unknown apply, rules naming a person wait.
#
# Rules live in firewall.yaml (edited on the Firewall page). Each rule names people and
# what they may not do; when one matches, she says the rule's message (or a line from
# phrases/router.yaml firewall_blocked) and nothing else happens. Kinds of rule:
#   voice_devices  they may not use these assistants at all (iris, felix)
#   devices        home devices they may not work: these words in what they say block it, and
#                  so does a Gemini tool call naming them ("open the garage door")
#   commands       phrases they may not say (whole words, like "open the garage")
#   topics         home topics (chores) or one action of a topic (chores.add)
#   gemini         true: nothing they say goes out to Gemini
#   intents        Home Assistant commands they may not run (HassTurnOn, HassTurnOff,
#                  HassSetPosition...); "HassTurnOn:lock" limits it to one kind of device
#   domains        kinds of device they may not work at all (lock, cover, alarm_control_panel)
# people: the voice ID's own names (Oread's profile names) or any other name of the same row in the
# people grid (veil/people.py), "unknown" (a voice it can't name for sure) or "anyone". Nicknames
# from Name Sparkle never count here. assistants: limit the rule to some voice devices (empty = all).
#
# Home Assistant's own commands: Home Assistant answers device commands itself first (Prefer
# handling commands locally), and Gemini works devices through Home Assistant's tools. Both
# end in one place in Home Assistant (intent.async_handle), where Veil Guard Service, the router's hook in Home Assistant
# (ha/custom_components/veil_guard_service) asks the router first: check_command() below. So devices,
# intents and domains rules cover every device command, wherever it was understood.

from veil import util

# what the Off-Platform model never works, whoever spoke, when firewall.yaml doesn't say (off_platform_never)
OFF_PLATFORM_NEVER = ["lock", "alarm", "garage door"]


def _words(text):
    return " " + util.words(text) + " "


def _has(text, phrase):
    p = _words(phrase).strip()
    return bool(p) and (" " + p + " ") in _words(text)


def unknown_devices(rules, names):
    """The device names in the rules that no device of the front end's has (names: its devices' names,
    like Home Assistant's friendly names): a rule for "gaurd test" silently stops nothing (Oct 13).
    [{rule: its number from 1, name: the rule's name, device: the word}]."""
    out = []
    for i, rule in enumerate(rules or []):
        for dv in rule.get("devices") or []:
            if not any(_has(n, dv) for n in names):
                out.append({"rule": i + 1, "name": rule.get("name") or "", "device": dv})
    return out


class Firewall:
    def __init__(self, spec, sure_score=0.8, sure_labels=("known",)):
        spec = spec or {}
        self.enabled = bool(spec.get("enabled", False))
        self.when_unsure = spec.get("when_oread_down", "unknown")    # unknown | allow
        self.sure_score = float(spec.get("sure_score", sure_score))
        self.sure_labels = list(spec.get("sure_labels") or sure_labels)
        self.rules = [r for r in (spec.get("rules") or []) if isinstance(r, dict) and r.get("enabled", True)]
        # never worked by the Off-Platform model, whoever spoke: its tool calls naming these (dump16)
        self.off_platform_never = [str(w) for w in spec.get("off_platform_never", OFF_PLATFORM_NEVER) or []]

    # who a rule is about

    def identity(self, who):
        """The names this voice answers to for rules: the voice ID's own name and every other name
        its row in the people grid gives the person (veil/people.py: Oread's "Sam" profile is
        Owner too), or 'unknown' when it isn't sure (or couldn't be asked and when_oread_down is
        unknown)."""
        who = who or {}
        if who.get("error") and self.when_unsure == "allow":
            return None                    # Oread is down and you chose not to block anyone
        name = str(who.get("speaker") or who.get("person") or "").strip().lower()   # the voice ID's own name
        sure = name and who.get("label") in self.sure_labels \
            and float(who.get("score") or 0) >= self.sure_score
        if not sure:
            return {"unknown"}
        from veil import people
        return people.names(name)

    def _applies(self, rule, names, assistant):
        people = {str(p).lower() for p in (rule.get("people") or [])}
        if not people:
            return False
        if "anyone" not in people and not (people & names):
            return False
        only = [str(a).lower() for a in (rule.get("assistants") or [])]
        return not only or (assistant or "").lower() in only

    # checks

    def check(self, who, assistant, said, topic=None, action=None, going_to_gemini=False):
        """The first rule this request breaks, as {rule, why}, or None."""
        if not self.enabled or not self.rules:
            return None
        names = self.identity(who)
        if names is None:
            return None
        for rule in self.rules:
            if not self._applies(rule, names, assistant):
                continue
            voice = [str(v).lower() for v in (rule.get("voice_devices") or [])]
            if (assistant or "").lower() in voice:
                return {"rule": rule, "why": f"may not use {assistant}"}
            for c in rule.get("commands") or []:
                if _has(said, c):
                    return {"rule": rule, "why": f"may not say \"{c}\""}
            for dv in rule.get("devices") or []:
                if _has(said, dv):
                    return {"rule": rule, "why": f"may not work the {dv}"}
            if topic:
                for t in rule.get("topics") or []:
                    t = str(t).lower()
                    if t == topic or (action and t == f"{topic}.{action}"):
                        return {"rule": rule, "why": f"may not use {t}"}
            if going_to_gemini and rule.get("gemini"):
                return {"rule": rule, "why": "may not go Off-Platform"}
        return None

    def watches_tools(self, who, assistant):
        """Does any rule for this voice watch Gemini's tool calls (devices:)?"""
        if not self.enabled:
            return False
        names = self.identity(who)
        if names is None:
            return False
        return any(self._applies(r, names, assistant) and r.get("devices") for r in self.rules)

    def check_tools(self, who, assistant, tool_calls):
        """The first rule a Gemini tool call breaks (a call whose name or arguments name a
        blocked device), or None. tool_calls: [{name, arguments}]."""
        if not self.enabled or not tool_calls:
            return None
        names = self.identity(who)
        if names is None:
            return None
        for rule in self.rules:
            if not self._applies(rule, names, assistant):
                continue
            for call in tool_calls:
                text = f"{call.get('name', '')} {call.get('arguments', '')}".replace("_", " ")
                for dv in rule.get("devices") or []:
                    if _has(text, dv):
                        return {"rule": rule, "why": f"the Off-Platform model tried to work the {dv} ({call.get('name')})"}
        return None

    def check_off_platform(self, tool_calls):
        """A tool call of the Off-Platform model's naming one of off_platform_never (locks, doors, the
        alarm): {rule, why} whoever spoke, or None. Home Assistant's own commands (said plainly) aren't these."""
        if not self.off_platform_never:
            return None
        for call in tool_calls or []:
            text = f"{call.get('name', '')} {call.get('arguments', '')}".replace("_", " ")
            for w in self.off_platform_never:
                if _has(text, w):
                    return {"rule": {"name": "off_platform_never", "message": ""}, "why": f"the Off-Platform model tried to work a {w} ({call.get('name')})",
                            "section": "off_platform_never"}
        return None

    def check_command(self, who, assistant, intent, targets=None, domains=None, text=None):
        """The first rule a Home Assistant command breaks, as {rule, why}, or None.
        intent: HassTurnOn...; targets: the names and areas it names (and the entity ids it
        resolved to); domains: their kinds (lock, cover...); text: the words, when HA had them."""
        if not self.enabled or not self.rules:
            return None
        names = self.identity(who)
        if names is None:
            return None
        intent = str(intent or "")
        targets = [str(t) for t in (targets or []) if t]
        domains = {str(d).lower() for d in (domains or []) if d}
        said = " ".join([text or ""] + [t.replace("_", " ").replace(".", " ") for t in targets])
        for rule in self.rules:
            if not self._applies(rule, names, assistant):
                continue
            voice = [str(v).lower() for v in (rule.get("voice_devices") or [])]
            if (assistant or "").lower() in voice:
                return {"rule": rule, "why": f"may not use {assistant}"}
            for dv in rule.get("devices") or []:
                if _has(said, dv):
                    return {"rule": rule, "why": f"may not work the {dv} ({intent})"}
            for c in rule.get("commands") or []:
                if text and _has(text, c):
                    return {"rule": rule, "why": f"may not say \"{c}\""}
            for d in rule.get("domains") or []:
                if str(d).lower() in domains:
                    return {"rule": rule, "why": f"may not work a {d} ({intent})"}
            for it in rule.get("intents") or []:
                name, _, dom = str(it).partition(":")
                if name.lower() == intent.lower() and (not dom or dom.lower() in domains):
                    return {"rule": rule, "why": f"may not run {it}"}
        return None

    def has_command_rules(self):
        """Is there anything for Veil Guard Service to ask about? (Off, or no rules: it needn't ask.)"""
        return self.enabled and bool(self.rules)

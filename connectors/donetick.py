# connectors/donetick.py - Donetick's quirks, where its API diverges from the Wepwawet standard
# (the API rule, Oct 18): everything else is the generic Connector's (connector.py).
#   its key in a header of its own (secretkey); its answers wrapped in res; /chores moved to /chores/
#   (expectation 7); no standard names for its fields (expectation 13); a move needs the chore's
#   updatedAt (expectation 6); an edit replaces the whole chore (expectation 5); how it stores a
#   repeat and reminders.
# Safety: a change needs a strong match to ONE real chore; a tie or no match changes nothing,
# and every change says which chore it touched.

import datetime as dt

from connector import Connector
from veil import config


def _unit(minutes):
    if minutes % 1440 == 0:
        return minutes // 1440, "d"
    if minutes % 60 == 0:
        return minutes // 60, "h"
    return minutes, "m"


class Donetick(Connector):
    AUTH = {"in": "header", "name": "secretkey", "prefix": ""}
    FIELDS = {"id": "id", "name": "name", "group": "projectId", "who": "assignedTo", "when": "nextDueDate"}
    NOUN = "chore"
    # Donetick sends /chores on to /chores/ (301 for a read, 307 for a change, which keeps the body):
    # asked at /chores/ itself, and followed anyway, so a command as its spec names it (a user rule's) reaches it
    FOLLOW_REDIRECTS = True
    TOO_LATE = ("undone within", "No recent action")      # its words when an undo comes too late

    def address(self, path):
        return path + "/" if path == "/chores" else path

    def unwrap(self, answer):
        return answer.get("res", answer) if isinstance(answer, dict) else answer

    def complete_body(self):
        return {}

    def nudge_body(self, item):
        return {"all_assignees": False, "message": f"Reminder: {self.name_of(item)}"}

    async def move_body(self, item, new_due):
        # its spec requires the chore's updatedAt with the new date (it refuses a change made over a
        # newer one): read the chore as it is now, then send both (the generic class does it, dump15)
        from veil import phases
        if phases.on("dump15"):
            return await self.with_required({"dueDate": new_due}, "move", item)
        fresh = await self.api("GET", f"{self.items_command()}/{item['id']}")
        stamp = (fresh or {}).get("updatedAt") if isinstance(fresh, dict) else None
        return {"dueDate": new_due, "updatedAt": stamp or item.get("updatedAt")}

    # ---------- how Donetick stores a chore (read from real chores, Oct 10) ----------
    #   repeat  -> frequencyType + frequency + frequencyMetadata {days, unit, time, timezone}
    #   due     -> nextDueDate (UTC)
    #   reminders -> notificationMetadata {dueDate, nagging, templates [{value, unit m/h/d}]}
    #                value 0 = at the due time, positive = after (nags), negative = before
    #                (before confirmed by the Oct 10 voice test)

    def new_body(self, name, person, gid, filled, today):
        body = {"name": name, "assignStrategy": "keep_last_assigned",
                "frequencyType": "once", "frequency": 1, "frequencyMetadata": {},
                "isRolling": False, "labelsV2": [], "notification": False}
        if person:
            body.update(assignedTo=person[0], assignees=[{"userId": person[0]}])
        if gid is not None:
            body["projectId"] = gid
        body.update(self.body_fields(filled, today))
        return body

    def body_fields(self, filled, today):
        """Donetick's fields for what's filled (name, who and project are handled by the caller)."""
        tz = dt.datetime.now().astimezone().tzinfo
        body = {}
        date = filled.get("due_date")
        time = filled.get("due_time")
        rep = filled.get("repeat")
        if rep and not date:                  # a repeat needs a first due date: today
            date = {"date": today.isoformat()}
        if date:
            if time:
                h, m = time["hour"], time["minute"]
            elif self.opt("default_chore_time"):
                h, m = map(int, str(self.opt("default_chore_time")).split(":"))
            else:
                # no time said and no default chore time (the Defaults tab): due at the start of the day
                print("  ! donetick: a day with no time and no default_chore_time: due at the start of the day", flush=True)
                h, m = 0, 0
            local = dt.datetime.combine(dt.date.fromisoformat(date["date"]), dt.time(h, m), tz)
            body["nextDueDate"] = local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            at = local.isoformat()
        if rep:
            meta = {"time": at, "timezone": config.house_timezone(self.settings) or str(tz)}   # the house's (Settings, The house)
            if rep.get("days"):
                body.update(frequencyType="days_of_the_week", frequency=1)
                meta.update(days=[self.weekdays[d] for d in rep["days"]], weekPattern="every_week")
            elif rep["every"] == 1 and rep["unit"] in ("day", "week", "month", "year"):
                body.update(frequencyType={"day": "daily", "week": "weekly", "month": "monthly",
                                           "year": "yearly"}[rep["unit"]], frequency=1)
            else:
                body.update(frequencyType="interval", frequency=rep["every"])
                meta["unit"] = rep["unit"] + "s"
            body["frequencyMetadata"] = meta
        templates, notif = [], {}
        if filled.get("remind_before"):
            v, u = _unit(filled["remind_before"]["minutes"])
            templates.append({"value": -v, "unit": u})
        if filled.get("remind_at_due") and filled["remind_at_due"].get("value"):
            templates.append({"value": 0, "unit": "m"})
            notif["dueDate"] = True
        if filled.get("nag"):
            step = filled["nag"]["minutes"]
            for k in range(1, int(self.opt("nag_max") or 0) + 1):
                v, u = _unit(step * k)
                templates.append({"value": v, "unit": u})
            notif["nagging"] = True
        if templates:
            body["notification"] = True
            body["notificationMetadata"] = dict(notif, templates=templates)
        return body

    REQ_KEYS = ["id", "name", "assignStrategy", "assignedTo", "assignees", "completionWindow",
                "description", "frequency", "frequencyMetadata", "frequencyType", "isActive",
                "isPrivate", "isRolling", "labelsV2", "nextDueDate", "notification",
                "notificationMetadata", "points", "priority", "projectId", "requireApproval", "subTasks"]

    async def apply_extras(self, state, changes):
        """Save what the series just added: GET the whole chore, merge, PUT it back
        (Donetick's edit replaces the whole chore; labelsV2 must be sent, even empty)."""
        items = self.items_command()
        chore = await self.api("GET", f"{items}/{state.get('chore_id')}")
        body = {k: chore.get(k) for k in self.REQ_KEYS if k in chore}
        body["labelsV2"] = [{"id": l["id"]} for l in (chore.get("labelsV2") or []) if l.get("id")]
        if not body.get("assignStrategy"):
            body["assignStrategy"] = "keep_last_assigned"
        today = dt.datetime.now().astimezone().date()
        body.update(self.body_fields(self.timed_reminder(state["filled"]), today))   # everything filled so far (reminders rebuilt whole)
        await self.api("PUT", items, json=body)
        await self.refresh()


APP = Donetick

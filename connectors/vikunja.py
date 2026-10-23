# connectors/vikunja.py - Vikunja's quirks, where its API diverges from the Wepwawet standard
# (the API rule, Oct 18): everything else is the generic Connector's (connector.py).
#   its key as a Bearer token; no standard names for its fields (expectation 13); an edit replaces
#   the whole task (expectation 5: assignees and reminders too); a task with no due date reads as
#   the year 1; its people as a list on each task; how it stores a repeat and reminders. It has no
#   skip, nudge or undo of its own: each is an edit of the whole task.
# Safety: a change needs a strong match to ONE real task; a tie or no match changes nothing,
# and every change says which task it touched.

import datetime as dt

from connector import Connector, log

SECONDS = {"minute": 60, "hour": 3600, "day": 86400, "week": 604800, "year": 31536000}


def _plain(task):
    """A task with its due date empty when it has none, and its first assignee as one field."""
    if isinstance(task, dict) and "repeat_after" in task:
        if str(task.get("due_date") or "").startswith("0001-"):
            task["due_date"] = None
        task["assignee"] = next((a.get("id") for a in task.get("assignees") or []), None)
    return task


class Vikunja(Connector):
    AUTH = {"in": "header", "name": "Authorization", "prefix": "Bearer "}
    FIELDS = {"id": "id", "name": "title", "group": "project_id", "who": "assignee", "when": "due_date"}
    NOUN = "chore"

    def unwrap(self, answer):
        return [_plain(x) for x in answer] if isinstance(answer, list) else _plain(answer)

    # ---------- a change is the whole task sent back (POST /tasks/{id}) ----------
    # done on a repeating task leaves it open, its due date and reminders one repeat on: Vikunja's skip

    def complete_body(self):
        return lambda item: dict(item, done=True)

    def skip_body(self):
        return self.complete_body()

    async def move_body(self, item, new_due):
        return dict(item, due_date=new_due)

    def repeat_of(self, item):
        """Monthly (repeat_mode 1), else every repeat_after seconds (a day's multiple counted in days)."""
        if item.get("repeat_mode") == 1:
            return ("months", 1)
        s = int(item.get("repeat_after") or 0)
        if not s:
            return None
        return ("days", s // 86400) if s % 86400 == 0 else ("seconds", s)

    def nudge_body(self, item):
        """A reminder a minute from now: its webhook (task.reminder.fired) is the nudge."""
        soon = (dt.datetime.now().astimezone() + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
        return dict(item, reminders=list(item.get("reminders") or []) + [{"reminder": soon.isoformat()}])

    async def undo_body(self, last):
        """Put it back: a finished one open again, a repeat moved on, one repeat back."""
        task = await self.api("GET", f"{self.items_command()}/{last['id']}")
        due = task.get("due_date")
        if task.get("done") or not due or not (task.get("repeat_after") or task.get("repeat_mode") == 1):
            return dict(task, done=False)
        due = dt.datetime.fromisoformat(due.replace("Z", "+00:00"))
        if task.get("repeat_mode") == 1:              # monthly
            y, m = (due.year, due.month - 1) if due.month > 1 else (due.year - 1, 12)
            back = due.replace(year=y, month=m)
        else:
            back = due - dt.timedelta(seconds=task["repeat_after"])
        return dict(task, due_date=back.isoformat())

    # ---------- how Vikunja stores a task (read from real tasks, Oct 21) ----------
    #   due       -> due_date (RFC 3339; none reads as 0001-01-01)
    #   repeat    -> repeat_after (seconds), or repeat_mode 1 (monthly); no "these weekdays" (every day)
    #   reminders -> reminders [{relative_to: due_date, relative_period: seconds}], negative = before
    #   who       -> assignees [{id}]

    def new_body(self, name, person, gid, filled, today):
        body = {"title": name}
        if gid is not None:
            body["project_id"] = gid
        if person:
            body["assignees"] = [{"id": person[0]}]
        body.update(self.body_fields(filled, today))
        return body

    def body_fields(self, filled, today):
        """Vikunja's fields for what's filled (name, who and project are handled by the caller)."""
        body = {}
        local = self.due_local(filled, today)
        rep = filled.get("repeat")
        if rep:
            days = rep.get("days") or []
            if len(days) == 1:
                body["repeat_after"] = SECONDS["week"] * rep["every"]
                if not filled.get("due_date"):      # "every Tuesday": the first one is the next Tuesday
                    local += dt.timedelta(days=(days[0] - local.weekday()) % 7)
            elif days:
                # repeats by an interval only: several weekdays are every day, its days kept in its
                # description; which days she's told is the briefing's (Home Assistant: its days)
                body["repeat_after"] = SECONDS["day"]
                body["description"] = f"Said: {rep.get('say')}."
            elif rep["unit"] == "month" and rep["every"] == 1:
                body["repeat_mode"] = 1
            elif rep["unit"] == "month":
                body["repeat_after"] = 30 * SECONDS["day"] * rep["every"]
                log.info("  ! vikunja: %s saved as every %d days", rep.get("say"), 30 * rep["every"])
            elif rep["unit"] in SECONDS:
                body["repeat_after"] = SECONDS[rep["unit"]] * rep["every"]
        if local:
            body["due_date"] = local.isoformat()
        if filled.get("remind_by"):        # how it comes (issue #19): read by Home Assistant's reminder automation
            body["description"] = "\n".join(x for x in (body.get("description"), f"Remind by: {filled['remind_by']['value']}") if x)
        at = self.reminder_minutes(filled)
        if at:
            body["reminders"] = [{"relative_to": "due_date", "relative_period": m * 60} for m in at]
        return body

    async def apply_extras(self, state, changes):
        """Save what the series just added: GET the whole task, merge, send it back."""
        path = f"{self.items_command()}/{state.get('chore_id')}"
        task = await self.api("GET", path)
        today = dt.datetime.now().astimezone().date()
        await self.api("POST", path, json=dict(task, **self.body_fields(self.timed_reminder(state["filled"]), today)))
        await self.refresh()


APP = Vikunja

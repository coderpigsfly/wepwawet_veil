"""addons/trainer/api.py - the Trainer page's doors: everyone in the People grid with their trainer switch.
Registered only when the add-on is on."""
from fastapi import Request  # noqa: F401


def register(app):
    import sys
    from veil import people
    from veil.web import audit, body_of, need
    from veil.errors import VeilError

    def mod():
        return sys.modules["addon_trainer"]

    @app.get("/api/addons/trainer")
    def trainer_people(request: Request):
        """Everyone in the People grid, with trainer mode on or off and who switched it last."""
        need(request, "reviewer")
        on = mod().people_on()
        names = [r["wepwawet"] for r in people.grid()["rows"] if r.get("wepwawet")]
        low = {k.lower(): v for k, v in on.items()}
        return {"topics": mod().settings().get("topics") or [],
                "people": [dict({"name": n, "on": False, "by": None, "at": None}, **(low.get(n.lower()) or {})) for n in names]}

    @app.post("/api/addons/trainer")
    async def trainer_switch(request: Request):
        """{person, on}: switched now; the person's next request is trained or not (no restart)."""
        actor = need(request, "administrator")
        b = await body_of(request)
        name = str(b.get("person") or "").strip()
        if name.lower() not in {r["wepwawet"].lower() for r in people.grid()["rows"] if r.get("wepwawet")}:
            raise VeilError(f"{name or 'Nobody'} isn't in the People grid")
        mod().set_on(name, bool(b.get("on")), (actor or {}).get("name") if isinstance(actor, dict) else None)
        audit(request, "trainer mode " + ("on" if b.get("on") else "off"), target=name)
        return {"person": name, "on": mod().is_on(name)}

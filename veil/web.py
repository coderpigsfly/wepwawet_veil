# veil/web.py - Wepwawet Veil's pages and the admin API behind them (port 8771).
#
# Everything the pages do is a JSON call under /api/, so a program with an API token can do it
# too. Every call needs a signed-in person or a token, except sign-in and first-run setup;
# every change is written to the audit log (data/audit.jsonl). Only addresses in security:
# admin_allowed may connect (empty: the local network only). A change from a page must carry
# the X-Requested-With: veil header (a cross-site form can't), and the session cookie is
# HttpOnly and SameSite=Strict (and Secure over https).
#
# Roles (security.py): viewer reads; reviewer works the Gemini bank, the miss log and the
# flair candidates; administrator changes settings, topics, integrations, people, firewall,
# flair and runs the tools; super manages users, tokens, the vault and permitted addresses.
#
# Most changes are written to their file at once (settings.yaml, firewall.yaml, personality/)
# with comments kept. The firewall and the address lists take effect at once; anything else
# the router reads at start, so the page offers Restart (the container comes straight back).

import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid

import yaml
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from veil import activity as activity_mod, apps, flairlines, fleas as fleas_mod, frontend, lists, mishearings, openapi, people as people_mod, phases, people_map, rules as rulebook, doors as doorset, access, config, firewall as firewall_mod, security, speakers, version
from veil.errors import VeilError

log = logging.getLogger("router")
HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "web")
COOKIE = "veil_session"
SECURE_COOKIES = False
VERSION = f"{version.VERSION} (Wepwawet Veil)"     # veil/version.py

AUDIT = security.Audit(config.DATA_DIR)
security.use(config.section(config.settings(), "security"))
USERS = security.Users(config.DATA_DIR, AUDIT.record)
TOKENS = security.Tokens(config.DATA_DIR)
RESTART_NEEDED = {}          # what changed since the router started, that a restart would apply

app = FastAPI(title="Wepwawet Veil", docs_url=None, redoc_url=None, openapi_url=None)


def router():
    import router as r          # the running router (same process, see veil/main.py)
    return r


def startup():
    if USERS.needs_setup():
        code = USERS.setup_code()
        log.info("Wepwawet Veil isn't set up yet. Open the pages and use this setup code: %s", code)
        log.info("(the setup code is also in data/setup-code.txt)")


# ---------- the doors: addresses, sign-in, roles ----------

PUBLIC = {("GET", "/api/setup"), ("POST", "/api/setup"), ("POST", "/api/session"),
          ("GET", "/api/session"), ("DELETE", "/api/session")}


def client_of(request):
    return request.client.host if request.client else ""


def actor_of(request):
    """{name, role, how} for a signed-in person or a token, or None."""
    tok = TOKENS.check(security.bearer(request.headers))
    if tok:
        return {"name": f"token {tok['name']}", "role": tok["role"], "how": "token"}
    user = USERS.session_user(request.cookies.get(COOKIE))
    if user:
        return {"name": user["name"], "role": user["role"], "how": "session"}
    return None


@app.middleware("http")
async def doors(request: Request, call_next):
    addr = client_of(request)
    if not access.ACCESS.allowed("admin_allowed", addr, "the pages"):
        access.ACCESS.note("admin_allowed", addr, request.url.path)
        return JSONResponse({"detail": "This address isn't permitted (security: admin_allowed)"}, status_code=403)
    path = request.url.path
    if path.startswith("/api/"):
        request.state.actor = actor_of(request)
        if (request.method, path) not in PUBLIC and not request.state.actor:
            return JSONResponse({"detail": "Sign in first"}, status_code=401)
        if request.method not in ("GET", "HEAD") and request.state.actor and \
                request.state.actor["how"] == "session" and request.headers.get("x-requested-with") != "veil":
            return JSONResponse({"detail": "Missing the X-Requested-With: veil header"}, status_code=403)
    try:
        response = await call_next(request)
    except VeilError as e:
        response = JSONResponse({"detail": str(e)}, status_code=e.status)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    return response


@app.exception_handler(VeilError)
async def veil_error(request, e):
    return JSONResponse({"detail": str(e)}, status_code=e.status)


@app.exception_handler(yaml.YAMLError)
async def yaml_error(request, e):
    log.info("  ! a file couldn't be read: %s", e)
    return JSONResponse({"detail": f"A file couldn't be read (fix it in your editor, or git restore it): {e}"},
                        status_code=500)


def need(request, role):
    actor = getattr(request.state, "actor", None)
    if not actor:
        raise VeilError("Sign in first", 401)
    if security.RANK[actor["role"]] < security.RANK[role]:
        raise VeilError(f"That needs the {role} role (you're {actor['role']})", 403)
    return actor


def audit(request, action, target=None, detail=None, ok=True):
    actor = getattr(request.state, "actor", None) or {}
    AUDIT.record(action=action, who=actor.get("name"), client=client_of(request), target=target,
                 detail=detail if isinstance(detail, str) or detail is None else json.dumps(detail)[:400],
                 ok=ok)


def restart_note(what):
    RESTART_NEEDED[what] = time.time()


async def body_of(request):
    try:
        return await request.json()
    except Exception:
        raise VeilError("The request needs a JSON body")


# ---------- the page itself ----------

# The page's own files are checked with the router on every load (no-cache: a quick "not changed"
# when they're the same), so a browser never runs an old app.js after an update.
def page_file(request, name, kind):
    path = os.path.join(STATIC, name)
    st = os.stat(path)
    tag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
    headers = {"Cache-Control": "no-cache", "ETag": tag}
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    return FileResponse(path, media_type=kind, headers=headers)


@app.get("/")
def index(request: Request):
    return page_file(request, "index.html", "text/html")


@app.get("/{name}")
def static(name: str, request: Request):
    if not re.fullmatch(r"[a-z0-9_-]+\.(js|css|svg|html)", name) or not os.path.exists(os.path.join(STATIC, name)):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    kind = {"js": "text/javascript", "css": "text/css", "svg": "image/svg+xml", "html": "text/html"}[name.rsplit(".", 1)[1]]
    return page_file(request, name, kind)


# ---------- setup and sessions ----------

@app.get("/api/setup")
def setup_needed():
    return {"needs_setup": USERS.needs_setup()}


@app.post("/api/setup")
async def setup(request: Request):
    b = await body_of(request)
    user = USERS.setup(b.get("code", ""), b.get("name", ""), b.get("password", ""), client_of(request))
    session, _ = USERS.sign_in(user["name"], b.get("password", ""), client_of(request))
    r = JSONResponse({"user": user})
    set_cookie(r, session)
    return r


def set_cookie(r, session):
    r.set_cookie(COOKIE, session, httponly=True, samesite="strict", secure=SECURE_COOKIES,
                 max_age=security.MAX_SECONDS, path="/")


@app.post("/api/session")
async def sign_in(request: Request):
    b = await body_of(request)
    session, user = USERS.sign_in(b.get("name", ""), b.get("password", ""), client_of(request))
    r = JSONResponse({"user": user})
    set_cookie(r, session)
    return r


CAN = {
    "viewer": ["overview", "transactions", "inbound", "outbound", "account", "guide"],
    "reviewer": ["bank", "misses", "candidates", "try", "fleas", "words"],
    "administrator": ["topics", "tools", "flair", "integrations", "people", "firewall", "settings"],
    "super": ["security", "users", "audit"],
}


def can(role):
    out = []
    for r in security.ROLES:
        if security.RANK[r] <= security.RANK[role]:
            out += CAN[r]
    return out


@app.get("/api/session")
def who(request: Request):
    actor = getattr(request.state, "actor", None)
    if not actor:
        return {"user": None, "needs_setup": USERS.needs_setup(), "password_min_length": security.MIN_PASSWORD}
    return {"user": {"name": actor["name"], "role": actor["role"]}, "can": can(actor["role"]),
            "grantable": USERS.grantable(actor) if actor["how"] == "session" else [],
            "version": VERSION, "restart_needed": sorted(RESTART_NEEDED),
            "password_min_length": security.MIN_PASSWORD, "assistants": assistants()}


def assistants():
    """The assistants (personalities, from personality/*.yaml): for the pages' pick lists."""
    try:
        return router().FLAIR.names()
    except Exception:
        return []


@app.delete("/api/session")
def sign_out(request: Request):
    USERS.sign_out(request.cookies.get(COOKIE))
    r = JSONResponse({"signed_out": True})
    r.delete_cookie(COOKIE, path="/")
    return r


@app.post("/api/account/password")
async def own_password(request: Request):
    actor = need(request, "viewer")
    if actor["how"] != "session":
        raise VeilError("Tokens don't have passwords", 409)
    b = await body_of(request)
    USERS.change_own_password(actor["name"], b.get("current", ""), b.get("new", ""), request.cookies.get(COOKIE))
    return {"changed": True}


# ---------- overview, transactions ----------

@app.get("/api/overview")
def overview(request: Request):
    need(request, "viewer")
    r = router()
    s = r.SETTINGS
    now = time.time()
    counts = r.ACTIVITY.counts(now - 86400) if r.ACTIVITY else None
    week = r.ACTIVITY.counts(now - 7 * 86400) if r.ACTIVITY else None
    services = []
    for name, svc in (s.get("services") or {}).items():
        services.append({"name": name, "enabled": config.service_enabled(svc), "kind": svc.get("kind"),
                         "url": svc.get("url"),
                         "topics": [t for t, v in (s.get("topics") or {}).items() if (v or {}).get("service") == name]})
    o = config.section(config.section(s, "integrations"), "oread")
    return {
        "version": VERSION, "model_name": r.MODEL, "fallback_model": r.FALLBACK_MODEL,
        "litellm": r.LITELLM_URL, "topics": {t: v.get("service") for t, v in r.SCORER.topics.items()},
        "services": services, "oread": {"enabled": bool(o.get("enabled")), "url": o.get("url"),
                                        "source": o.get("source", "wyoming")},
        "firewall": {"enabled": r.FIREWALL.enabled, "rules": len(r.FIREWALL.rules)},
        "flair": {"on": bool(r.FLAIR.flaired()), "personalities": r.FLAIR.flaired()},
        "connectors": sorted(r.CONNECTORS), "spacy": bool(r.NLP),
        "last_day": counts, "last_week": week, "restart_needed": sorted(RESTART_NEEDED),
        "confidence_local": r.CONFIDENCE,
    }


@app.get("/api/activity")
def activity_list(request: Request, direction: str = "all", limit: int = 100, before: int = 0,
                  assistant: str = "", search: str = "", handled: str = "all", sort: str = "time",
                  order: str = "desc", offset: int = 0):
    """The Transactions page. direction: all, out (left the house), gemini, home, blocked;
    handled: hide (not yet dealt with), only (banked or recorded as misheard), all; sort: time,
    assistant, speaker, heard, went, said; order: asc or desc; offset: the next page when sorted."""
    need(request, "viewer")
    r = router()
    if not r.ACTIVITY:
        return {"rows": [], "off": True}
    direction = direction if direction in ("out", "gemini", "home", "blocked") else None
    handled = handled if handled in ("hide", "only") else "all"
    return {"rows": r.ACTIVITY.recent(limit, before or None, direction, assistant or None, search or None, handled,
                                      sort=sort, descending=order != "asc", offset=offset),
            "bank_keeps": r.BANK_KEEPS}


@app.delete("/api/activity/{activity_id}")
def activity_delete(request: Request, activity_id: int):
    """Delete on the Transactions page: right, and routed right, so nothing to learn from it."""
    need(request, "reviewer")
    r = router()
    try:
        r.ACTIVITY.delete(activity_id)
    except ValueError as e:
        raise VeilError(str(e), 404)
    audit(request, "transaction deleted", target=str(activity_id))
    return {"deleted": activity_id}


@app.post("/api/activity/{activity_id}/misheard")
async def activity_misheard(request: Request, activity_id: int):
    """Misheard on the Transactions page: into learn/mishearings.yaml, the words heard under what
    was really meant (said; optional: without it, it waits under not given yet). Her answer isn't
    kept: what matters is catching the mishearing before it's decided."""
    need(request, "reviewer")
    b = await body_of(request)
    r = router()
    row = r.ACTIVITY.get(activity_id) if r.ACTIVITY else None
    if not row:
        raise VeilError("That transaction isn't in the log any more", 404)
    if not (row.get("heard") or "").strip():
        raise VeilError("Nothing was heard on that one")
    said = mishearings.tidy(b.get("said"))
    p, c = mishearings.add(row["heard"], said, clip=row.get("clip"), device=row.get("device"))
    r.ACTIVITY.mark(activity_id, "misheard")
    audit(request, "recorded as misheard", target=str(activity_id), detail={"heard": row["heard"], "said": said})
    return {"recorded": {"meant": p.get("meant"), "heard": c["said"], "count": c["count"], "total": mishearings.total(p)}}


# ---------- stats: counts and Time Routes ----------

def trend_span(act, now, who):
    """How far back the 30-day usual reaches: the log's own span, with first moved back to the
    first day the daily summaries cover (they outlast the log's keep_days)."""
    out = act.span(now - 30 * 86400, who)
    since = act.usual_since(who)
    if since and (not out.get("first") or since < out["first"]):
        out["first"] = since
    return out


@app.get("/api/stats")
def stats(request: Request, days: int = 1, tz: int = 0, assistant: str = ""):
    """days: the period for Time Routes and the charts; tz: the viewer's minutes east of UTC (days start at their midnight)."""
    need(request, "viewer")
    r = router()
    if not r.ACTIVITY:
        return {"off": True}
    days = max(1, min(int(days), 3650))
    tz = max(-900, min(int(tz), 900))
    who = re.sub(r"[^a-z0-9_ -]", "", assistant.lower())[:40] or None      # one assistant, or all
    now = time.time()
    st = config.section(config.settings(), "stats")
    top_days = float(st.get("top_cpu_days", 7))
    net = config.section(st, "internet_check")
    return {"days": days, "last_day": r.ACTIVITY.counts(now - 86400), "last_week": r.ACTIVITY.counts(now - 7 * 86400),
            "time_routes": r.ACTIVITY.time_routes(now - days * 86400, assistant=who), "model": r.FALLBACK_MODEL,
            "span": r.ACTIVITY.span(now - days * 86400, who), "trend_span": trend_span(r.ACTIVITY, now, who),
            "legs": dict(r.ACTIVITY.legs(now, tz, st.get("slower_than_usual", 1.5), st.get("slow_min_requests", 3),
                                         net.get("slower", 2.0), who),
                         checking=r.NETCHECK.enabled and sorted(r.NETCHECK.routes), servers=r.NETCHECK.servers,
                         cooldown_minutes=r.NETCHECK.cooldown / 60),
            "audio_path": bool(r.wyoming.SERVERS), "keep_days": r.ACTIVITY.keep_days, "assistant": who or "",
            "shares": r.ACTIVITY.shares(now - days * 86400, tz, who),
            "trend": r.ACTIVITY.route_trend(now, tz, 30, st.get("slower_than_usual", 1.5), st.get("slow_min_requests", 3), who),
            "top_cpu": r.ACTIVITY.top_cpu(now - top_days * 86400, st.get("top_cpu", 10), who), "top_cpu_days": top_days,
            "resources": dict(r.ACTIVITY.resources(now), now=r.SAMPLER.now(),
                              sample_seconds=r.SAMPLER.seconds),
            "unclaimed_after": r.wyoming.UNCLAIMED_AFTER, "apps": app_labels()}


def app_labels():
    """Each app's title for Stats' routes, and whether its data comes from outside the house (an
    address on the internet): "At home, outside data: Liturgical calendar" (dump18)."""
    if not phases.on("dump18"):
        return {}
    return {n: {"title": (v or {}).get("title") or n.replace("_", " ").capitalize(), "outside": access.outside((v or {}).get("url"))}
            for n, v in (config.settings().get("services") or {}).items()}


# ---------- savings: trips and tokens kept in the house ----------

@app.get("/api/savings")
def savings(request: Request, days: int = 30):
    need(request, "viewer")
    r = router()
    if not r.ACTIVITY:
        return {"off": True}
    days = max(1, min(int(days), 3650))
    tpr = config.section(config.settings(), "savings").get("tokens_per_request", 3000)
    out = r.ACTIVITY.savings(time.time() - days * 86400, tpr)
    out["days"] = days
    out["keep_days"] = r.ACTIVITY.keep_days
    return out


# ---------- the Off-Platform bank ----------

@app.get("/api/bank")
def bank(request: Request, review: str = "", klass: str = "", search: str = "", order: str = "last",
         limit: int = 200, added: str = "yes", personality: str = ""):
    """added: yes (the replacement answers you added, the default), no (only counted), all.
    personality: one personality's bank (each has its own)."""
    need(request, "reviewer")
    r = router()
    if not r.ACTIVITY:
        return {"rows": [], "classes": [], "off": True}
    out = r.ACTIVITY.bank(review or None, klass or None, search or None, order, limit,
                          {"yes": True, "no": False}.get(added), personality or None)
    out["answer_from_bank"] = r.ACTIVITY.answer_from_bank
    out["bank_keeps"] = r.BANK_KEEPS
    return out


@app.post("/api/bank/add")
async def bank_add(request: Request):
    """The + on the Transactions page: that request becomes a replacement answer in the bank."""
    need(request, "reviewer")
    b = await body_of(request)
    try:
        row = router().ACTIVITY.bank_add_from(int(b.get("activity_id") or 0))
    except (TypeError, ValueError) as e:
        raise VeilError(str(e))
    audit(request, "added to the bank", target=str(row["id"]), detail=row.get("heard"))
    return row


@app.post("/api/bank/upload")
async def bank_upload(request: Request):
    """The generic upload (dump19): {personality, generic, sayings: [{said, answers: [...]}]} or {yaml: the
    same list as YAML text}: each saying put in the bank, added, with the ways it may be answered, so it's
    answered at home with no Off-Platform trip."""
    need(request, "reviewer")
    if not phases.on("dump19"):
        raise VeilError("Not here yet", 404)
    b = await body_of(request)
    rows = b.get("sayings")
    if isinstance(b.get("yaml"), str):
        try:
            rows = yaml.safe_load(b["yaml"])
        except yaml.YAMLError as e:
            raise VeilError(f"That isn't YAML that can be read: {str(e)[:120]}")
    if not isinstance(rows, list) or not rows:
        raise VeilError("sayings is a list of {said, answers}")
    r = router()
    pers = str(b.get("personality") or (r.FLAIR.names() or [""])[0]).strip().lower()
    done = []
    for i, x in enumerate(rows[:500]):
        said = " ".join(str((x or {}).get("said") or "").split())[:300]
        answers = [" ".join(str(a).split())[:600] for a in ((x or {}).get("answers") or []) if str(a).strip()]
        words = r.without_polite(said)
        if not words or not answers:
            raise VeilError(f"saying {i + 1}: it needs its words (said) and at least one answer")
        done.append(r.ACTIVITY.bank_upload(pers, activity_mod.key_of(words), said, answers, b.get("generic", True) is not False))
    audit(request, "bank upload", detail=f"{len(done)} sayings for {pers}")
    return {"added": len(done), "personality": pers}


@app.post("/api/bank/{bank_id}/flea")
async def bank_to_flea(request: Request, bank_id: int):
    """Answer at home: a saying in the bank becomes a brain flea (its words the way it's asked, the answers
    kept for it her lines), answered at home before anything goes Off-Platform (dump19)."""
    need(request, "reviewer")
    if not phases.on("dump19"):
        raise VeilError("Not here yet", 404)
    row = router().ACTIVITY.bank_row(bank_id)
    if not row:
        raise VeilError("No such bank row", 404)
    if not row["answers"]:
        raise VeilError("It has no answers kept yet to say")
    taken = names_taken()
    base = re.sub(r"[^a-z0-9]+", "_", str(row["key"]))[:30].strip("_") or "saying"
    name, n = base, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    flea = {"title": str(row["heard"])[:60], "words": [str(row["key"])], "steps": [{"response": {"lines": row["answers"][:5]}}]}

    def change(doc):
        from ruamel.yaml.comments import CommentedMap
        if doc.get("fleas") is None:
            doc["fleas"] = CommentedMap()
        doc["fleas"][name] = flea
    fleas_mod.edit(change)
    audit(request, "bank saying made a flea", target=name, detail=row["heard"])
    return {"flea": name}


@app.patch("/api/bank/{bank_id}")
async def bank_review(request: Request, bank_id: int):
    need(request, "reviewer")
    b = await body_of(request)
    try:
        row = router().ACTIVITY.bank_review(bank_id, b.get("review"), b.get("note"))
        if "added" in b:
            row = router().ACTIVITY.bank_set_added(bank_id, bool(b["added"]))
        if "generic" in b:
            row = router().ACTIVITY.bank_set_generic(bank_id, bool(b["generic"]))
    except ValueError as e:
        raise VeilError(str(e))
    if not row:
        raise VeilError("No such bank row", 404)
    audit(request, "bank reviewed", target=str(bank_id), detail={k: b.get(k) for k in ("review", "note", "added", "generic")})
    return row


@app.get("/api/bank/results")
def bank_results(request: Request, limit: int = 0, personality: str = ""):
    """The top things the Off-Platform model turned requests into, with every wording that led there."""
    need(request, "reviewer")
    r = router()
    if not r.ACTIVITY:
        return {"results": [], "off": True}
    out = r.ACTIVITY.by_result(limit or getattr(r.ACTIVITY, "bank_top", 25), personality or None)
    out["knobs"] = {k: getattr(r.ACTIVITY, k, None) for k in
                    ("answer_from_bank", "answers_kept", "use_from", "bank_top", "trim_days")}
    return out


BANK_EXPORT_HEADER = """# learn/bank.yaml - the Off-Platform Bank, written out for git (Export on the Off-Platform Bank page).
# The bank itself lives in the database (data/veil.db), which never goes into git; this is a copy
# to read and commit. Nothing reads it back: changing it changes nothing.
# Each saying: how often heard, its Off-Platform trips, how often the bank answered it, whether
# you added it, your review and note, the answers kept for it, and what Gemini turned it into.

"""


@app.post("/api/bank/export")
def bank_export(request: Request):
    """Export on the bank page: the bank written to learn/bank.yaml, to commit and push."""
    need(request, "reviewer")
    r = router()
    if not r.ACTIVITY:
        raise VeilError("The activity log is off, so there's no bank")
    rows = r.ACTIVITY.bank_export()
    file = config.path("learn", "bank.yaml")
    config.make_dirs(os.path.dirname(file))
    tmp = file + ".tmp"
    with open(tmp, "w") as f:
        f.write(BANK_EXPORT_HEADER + f"# Exported {time.strftime('%Y-%m-%d %H:%M')}: {len(rows)} sayings.\n\n")
        yaml.safe_dump({"bank": rows}, f, sort_keys=False, allow_unicode=True, width=120)
    os.replace(tmp, file)
    config.hand_back(file)
    audit(request, "bank exported", detail=f"{len(rows)} sayings")
    return {"file": "learn/bank.yaml", "sayings": len(rows), "added": sum(1 for x in rows if x["added"])}


@app.post("/api/bank/trim")
def bank_trim(request: Request):
    need(request, "administrator")
    r = router()
    n = r.ACTIVITY.trim(getattr(r.ACTIVITY, "trim_days", 30) or 30) if r.ACTIVITY else 0
    audit(request, "bank trimmed", detail=f"{n} one-offs")
    return {"trimmed": n}


@app.delete("/api/bank/{bank_id}")
def bank_delete(request: Request, bank_id: int):
    need(request, "administrator")
    router().ACTIVITY.bank_delete(bank_id)
    audit(request, "bank row deleted", target=str(bank_id))
    return {"deleted": bank_id}


# ---------- try a sentence (the same decision a real request gets; calls nothing) ----------

@app.post("/api/try")
async def try_it(request: Request):
    need(request, "reviewer")
    b = await body_of(request)
    said = (b.get("say") or "").strip()
    if not said:
        raise VeilError("Say something to try")
    first = (assistants() or [""])[0]
    assistant = re.sub(r"[^a-z0-9_-]", "", (b.get("assistant") or first).lower()) or first
    if not assistant:
        raise VeilError("Pick an assistant (there are no personalities in personality/)")
    body = {"messages": [{"role": "system", "content": f"{assistant.title()} Personality"},
                         {"role": "user", "content": said}],
            "speaker": b.get("speaker") or {}}
    if isinstance(b.get("firewall"), dict):
        body["firewall"] = b["firewall"]

    class Fake:            # /explain reads the body and query from a request
        def __init__(self, data):
            self._d = data
            self.headers = {"authorization": f"Bearer {security.INTERNAL}"}

        async def json(self):
            return self._d
    return await router().explain(Fake(body), live=bool(b.get("live")))


# ---------- the miss log ----------

def word_diff(heard, said):
    """[{op: same | heard | said | both, heard, said}] word by word, case and punctuation aside."""
    import difflib
    clean = lambda t: re.findall(r"[a-z0-9']+", str(t or "").lower())          # noqa: E731
    a, b = clean(heard), clean(said)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        kind = {"equal": "same", "delete": "heard", "insert": "said", "replace": "both"}[op]
        out.append({"op": kind, "heard": " ".join(a[i1:i2]), "said": " ".join(b[j1:j2])})
    return out


def decision_of(text, assistant):
    """What the router would decide today for these words (calls nothing, changes nothing)."""
    try:
        d = router().decide([{"role": "system", "content": f"{assistant or 'iris'} personality"},
                             {"role": "user", "content": text}], fresh=True, pending={}, memory={}, turns=[])
    except Exception as e:  # never let one miss break the page
        return {"path": "?", "why": [str(e)]}
    return {"path": d.get("path"), "topic": d.get("topic"), "action": d.get("action")}


@app.get("/api/misses")
def misses(request: Request):
    """The miss log: engine misses ("Who answered that?"). Mishearings: /api/mishearings."""
    need(request, "reviewer")
    try:
        items = config.load_yaml(config.path("learn", "misses.yaml")).get("misses") or []
    except FileNotFoundError:
        items = []
    return {"misses": [dict(m) for m in items if m.get("kind") != "misheard"]}


@app.get("/api/mishearings")
def mishearings_list(request: Request):
    """Each intention (what was really meant) with what speech-to-text heard for it, each with
    its count, the words that differ, and whether today's router still decides differently
    because of them. Not given yet comes first; then the most heard."""
    need(request, "reviewer")
    out = []
    for p in mishearings.load():
        meant = p.get("meant")
        now_meant = decision_of(meant, None) if meant else None
        heard = []
        for c in p.get("heard") or []:
            c = dict(c)
            if meant:
                c["diff"] = word_diff(c.get("said"), meant)
                c["now_heard"] = decision_of(c.get("said") or "", None)
                same = all(c["now_heard"].get(k) == now_meant.get(k) for k in ("path", "topic", "action"))
                c["verdict"] = "harmless now: the router decides the same for both" if same \
                    else "still matters: the router decides differently for what was heard"
            heard.append(c)
        heard.sort(key=lambda c: (-int(c.get("count", 1)), str(c.get("said"))))
        out.append({"meant": meant, "now_meant": now_meant, "total": mishearings.total(p), "heard": heard})
    out.sort(key=lambda p: (p["meant"] is not None, -p["total"]))
    r = router()
    sw = [dict(x) for x in mishearings.swaps()]
    uses = r.ACTIVITY.swap_uses([x["heard"] for x in sw]) if r.ACTIVITY else {}
    for x in sw:
        x["used"], x["last_used"] = uses.get(x["heard"], (0, None))
    return {"mishearings": out, "swaps": sw, "swap_days": r.ACTIVITY.keep_days if r.ACTIVITY else 0}


@app.post("/api/mishearings/swap")
async def mishearings_swap(request: Request):
    """{heard, meant, on, line}: use one difference of a mishearing before anything is decided (learn/swaps.yaml),
    or stop using it: a word fix (Use it) or a phrase fix (Use a phrase). line: the heard line a phrase is
    taken from, which must hold it as whole words. Used at once."""
    need(request, "reviewer")
    b = await body_of(request)
    if b.get("on", True):
        if not " ".join(str(b.get("meant") or "").split()):
            raise VeilError("Say what was meant")
        if b.get("line") is not None:
            said = re.findall(r"[a-z0-9']+", str(b.get("line") or "").lower())
            want = re.findall(r"[a-z0-9']+", str(b.get("heard") or "").lower())
            if not want or not any(said[i:i + len(want)] == want for i in range(len(said) - len(want) + 1)):
                raise VeilError("Those words aren't in what was heard, as whole words: it would never be swapped")
    try:
        got = mishearings.use(b.get("heard"), b.get("meant"), bool(b.get("on", True)))
    except ValueError as e:
        raise VeilError(str(e).capitalize())
    audit(request, "mishearing swap " + ("used" if b.get("on", True) else "stopped"), detail={"heard": b.get("heard"), "meant": b.get("meant")})
    return {"swaps": got}


@app.post("/api/mishearings/meant")
async def mishearings_meant(request: Request):
    """What was really said, for a heard line: it moves under that intention, count and all
    (typing it for one not given yet, or moving one filed under the wrong intention)."""
    need(request, "reviewer")
    b = await body_of(request)
    try:
        p, c = mishearings.set_meant(str(b.get("heard") or ""), b.get("meant"))
    except ValueError as e:
        raise VeilError(str(e).capitalize())
    if not c:
        raise VeilError("That mishearing isn't there any more (reload the page)", 404)
    audit(request, "mishearing filed", detail={"heard": c["said"], "meant": p.get("meant")})
    return {"meant": p.get("meant"), "total": mishearings.total(p)}


@app.post("/api/mishearings/drop")
async def mishearings_drop(request: Request):
    """Take one heard line out (by its words, never its place in the list)."""
    need(request, "reviewer")
    b = await body_of(request)
    if not mishearings.drop(str(b.get("heard") or "")):
        raise VeilError("That mishearing isn't there any more (reload the page)", 404)
    audit(request, "mishearing dropped", detail={"heard": b.get("heard")})
    return {"dropped": True}


@app.post("/api/misses/drop")
async def misses_drop(request: Request):
    """Drop one miss, named by its kind and words (never by its place in the list, which moves)."""
    need(request, "reviewer")
    b = await body_of(request)
    if not router().misslog.drop(str(b.get("kind") or ""), str(b.get("heard") or "")):
        raise VeilError("That miss isn't in the log any more (reload the page)", 404)
    config.hand_back(router().misslog.MISSES_FILE)
    audit(request, "miss dropped", detail={"kind": b.get("kind"), "heard": b.get("heard")})
    return {"dropped": True}


@app.post("/api/misses/should_be")
async def misses_should_be(request: Request):
    """What was really said (or should have happened), typed on the Misses page."""
    need(request, "reviewer")
    b = await body_of(request)
    note = " ".join(str(b.get("should_be") or "").split())[:200]
    if not note:
        raise VeilError("Type what was really said")
    if not router().misslog.add_note(str(b.get("heard") or ""), str(b.get("kind") or ""), note):
        raise VeilError("That miss isn't in the log any more (reload the page)", 404)
    config.hand_back(router().misslog.MISSES_FILE)
    return {"saved": True}


# ---------- settings: any knob, by its path ----------

SUPER_ONLY = {"security", "web"}
NEVER = {"topics", "people", "services", "integrations"}     # these have their own pages


@app.get("/api/starting")
def starting_get(request: Request):
    """What's new in the starting copies (defaults/) that the household's files don't have yet."""
    need(request, "administrator")
    from veil import starting
    return {"items": starting.new_items()}


@app.post("/api/starting/{item_id}/add")
def starting_add(request: Request, item_id: str):
    need(request, "administrator")
    from veil import starting
    item = starting.add(item_id)
    restart_note(item["file"])
    audit(request, "starting copy added", target=item["file"], detail={"path": item["path"], "value": item["value"]})
    return {"added": item}


@app.post("/api/starting/{item_id}/dismiss")
def starting_dismiss(request: Request, item_id: str):
    need(request, "administrator")
    from veil import starting
    item = starting.dismiss(item_id)
    audit(request, "starting copy not for us", target=item["file"], detail={"path": item["path"], "value": item["value"]})
    return {"dismissed": item}


@app.get("/api/settings")
def settings_get(request: Request):
    need(request, "administrator")
    try:
        own = config.plain(config.load_yaml(config.SETTINGS_FILE))
    except FileNotFoundError:
        own = {}
    read = settings_comments()
    return {"settings": own, "defaults": config.DEFAULTS, "comments": read["comments"], "sections": read["sections"]}


def settings_comments(file=None):
    """settings.yaml (or another YAML file of ours) read as the pages show it: its sections (the
    "# ---------- title ----------" lines, in order, each with the keys under it) and every key's
    comment (the lines just above it, and anything after a # on its own line), by dotted path."""
    sections, comments = [], {}
    section = {"title": "general", "keys": []}
    block, stack = [], []
    head = re.compile(r"^#\s*-{4,}\s*(.*?)\s*-{4,}\s*$")
    key_line = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*):(.*)$")
    try:
        lines = open(file or config.SETTINGS_FILE).read().splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        m = head.match(line)
        if m:
            if section["keys"]:
                sections.append(section)
            section, block = {"title": m.group(1), "keys": []}, []
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            block.append(stripped.lstrip("#").strip())
            continue
        if not stripped:
            if not line.startswith(" "):
                block = []
            continue
        m = key_line.match(line)
        if not m or stripped.startswith("- "):
            continue
        indent, key, rest = len(m.group(1)), m.group(2), m.group(3)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([k for _, k in stack] + [key])
        inline = rest.split(" #", 1)[1].strip() if " #" in rest else ""
        text = ""
        for x in (x for x in block if x):          # lines of one comment, read as sentences
            if text and text[-1] not in ".:;!?,(" and x[:1].isupper():
                text += "."
            text = f"{text} {x}" if text else x
        comments[path] = " ".join(x for x in (text, inline) if x)[:600]
        block = []
        if indent == 0:
            section["keys"].append(key)
        stack.append((indent, key))
    if section["keys"]:
        sections.append(section)
    return {"sections": sections, "comments": comments}


def check_value(keys, value):
    top = keys[0]
    if top in NEVER:
        raise VeilError(f"{top} is changed on its own page")
    old = config.DEFAULTS
    for k in keys:
        old = old.get(k) if isinstance(old, dict) else None
    if old is not None and not isinstance(old, dict):
        if isinstance(old, bool) and not isinstance(value, bool):
            raise VeilError(f"{'.'.join(keys)} is true or false")
        if isinstance(old, (int, float)) and not isinstance(old, bool) and \
                (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise VeilError(f"{'.'.join(keys)} is a number")
    if isinstance(value, (dict, list)) and len(json.dumps(value)) > 20000:
        raise VeilError("That's too big for one setting")
    lo_hi = RANGES.get(tuple(keys))
    if lo_hi and not (lo_hi[0] <= value <= lo_hi[1]):
        raise VeilError(f"{'.'.join(keys)} is from {lo_hi[0]} to {lo_hi[1]}")


# settings with a range (the bank's formula: T at least 1, U a share)
RANGES = {("activity", "bank_answers_kept"): (0, 1000), ("activity", "bank_use_from"): (0, 1),
          ("activity", "keep_days"): (1, 3650), ("activity", "keep_rows"): (100, 10000000),
          ("security", "password_min_length"): (8, 256), ("security", "lock_after_failures"): (1, 100),
          ("security", "lock_minutes"): (1, 10080), ("security", "session_idle_hours"): (1, 720),
          ("security", "session_max_days"): (1, 365),
          ("names_in_replies", "min_score"): (0, 1), ("names_in_replies", "rate"): (0, 1),
          ("names_in_replies", "max_in_a_row"): (0, 10)}



# activity: settings the pages change while running: setting -> (the Activity attribute, its type)
LIVE_ACTIVITY = {"keep_days": ("keep_days", float), "keep_rows": ("keep_rows", int),
                 "bank_answers_kept": ("answers_kept", int), "bank_use_from": ("use_from", float),
                 "trim_days": ("trim_days", float), "answer_from_bank": ("answer_from_bank", bool),
                 "bank_top": ("bank_top", int)}


@app.patch("/api/settings")
async def settings_set(request: Request):
    """{path: ["names_in_replies", "rate"], value: 0.4} -> settings.yaml, comments kept."""
    b = await body_of(request)
    keys = [str(k) for k in (b.get("path") or [])]
    if not keys or not all(re.fullmatch(r"[A-Za-z0-9_]+", k) for k in keys):
        raise VeilError("path is a list of setting names")
    need(request, "super" if keys[0] in SUPER_ONLY else "administrator")
    check_value(keys, b.get("value"))
    if keys[0] == "security" and b.get("value") is True and (
            (len(keys) == 4 and keys[1] == "doors" and keys[3] == "locked")
            or (len(keys) == 2 and keys[1].endswith("_token_required"))):
        name = keys[2] if len(keys) == 4 else keys[1][:-len("_token_required")]
        door = doorset.doors(config.section(config.settings(), "security")).get(name)
        if not door:
            raise VeilError(f"There's no door named {name}", 404)
        if not TOKENS.list():
            raise VeilError(f"Make an API token first (Security, API keys) and give it to {door.get('who') or 'its program'}; "
                            "otherwise this locks it out")
    config.edit_yaml(config.SETTINGS_FILE, lambda doc: config.set_in(doc, keys, b.get("value")))
    audit(request, "setting changed", target=".".join(keys), detail=json.dumps(b.get("value"))[:200])
    if keys[0] == "security":                 # in use at once: the addresses, the doors, the sign-in rules
        use_security()
    elif keys[0] == "savings":
        pass                                  # read fresh on every Savings page
    elif keys[:1] == ["activity"] and len(keys) == 2 and keys[1] in LIVE_ACTIVITY and router().ACTIVITY:
        attr, kind = LIVE_ACTIVITY[keys[1]]
        setattr(router().ACTIVITY, attr, kind(b.get("value")))   # in use at once
    else:
        restart_note("settings")
    return {"saved": ".".join(keys)}


# ---------- topics and their seed words ----------

TOPIC_KEYS = ("service", "seed", "always_tentative", "pinned")


def word_list(v, what):
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise VeilError(f"{what} is a list of words")
    out = []
    for w in v:
        w = " ".join(w.lower().split())
        if w and not re.fullmatch(r"[a-z0-9' -]{1,40}", w):
            raise VeilError(f"'{w}' in {what}: letters, digits, spaces, ' and - only (40 at most)")
        if w and w not in out:
            out.append(w)
    return out


@app.get("/api/topics")
def topics(request: Request):
    need(request, "viewer")
    r = router()
    s = config.settings()
    out = []
    for name, v in (s.get("topics") or {}).items():
        v = v or {}
        gen = {}
        try:
            t = config.load_yaml(config.path("topics", f"{name}.yaml"))
            doors = t.get("doors") or {}
            gen = {"doors": {k: len(x or []) for k, x in doors.items()} if isinstance(doors, dict) else len(doors),
                   "learn_from": t.get("learn_from"), "built": True}
        except FileNotFoundError:
            gen = {"built": False}
        out.append({"name": name, **{k: v.get(k) if k == "service" else list(v.get(k) or []) for k in TOPIC_KEYS},
                    "then": list(v.get("then") or []), "datasets": v.get("datasets") is not False,
                    "generated": gen, "running": name in r.SCORER.topics})
    return {"topics": out, "services": sorted((s.get("services") or {}).keys())}


@app.put("/api/topics/{name}")
async def topic_set(request: Request, name: str):
    """Add or change a topic: its service and word lists (the same keys for every topic)."""
    need(request, "administrator")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", name):
        raise VeilError("Topic names are 2-31 lowercase letters, digits or _")
    b = await body_of(request)
    s = config.settings()
    svc_name = b.get("service") or ""         # "": no app answers it yet (Add an app offers it)
    if svc_name and svc_name not in (s.get("services") or {}):
        raise VeilError(f"service is one of: {', '.join(s.get('services') or {})}, or none yet")
    entry = {"service": svc_name}
    for k in ("seed", "always_tentative", "pinned"):
        entry[k] = word_list(b.get(k) or [], k)
    # the apps of the same nature after it, in order: each answers when the one before is busy (dump9)
    then = b.get("then")
    if then is not None:
        if not isinstance(then, list) or not all(isinstance(x, str) for x in then):
            raise VeilError("then is a list of apps")
        then = list(dict.fromkeys(x.strip() for x in then if x.strip() and x.strip() != svc_name))
        odd = [x for x in then if x not in (s.get("services") or {})]
        if odd:
            raise VeilError(f"then lists apps: {', '.join(odd)} isn't one ({', '.join(s.get('services') or {})})")
    if "datasets" in b and not isinstance(b["datasets"], bool):
        raise VeilError("datasets is true (learn from them too) or false (your words alone)")

    def change(doc):
        from ruamel.yaml.comments import CommentedMap
        topics_ = doc.get("topics")
        if topics_ is None:
            doc["topics"] = topics_ = CommentedMap()
        node = topics_.get(name)
        if node is None:
            topics_[name] = node = CommentedMap()
        node["service"] = entry["service"]
        for k in ("seed", "always_tentative", "pinned"):
            seq = config.flow_list(entry[k])
            node[k] = seq
        if then is not None:
            if then:
                node["then"] = config.flow_list(then)
            else:
                node.pop("then", None)
        if "datasets" in b:              # false: built from your words alone, never the datasets' labels
            if b["datasets"]:
                node.pop("datasets", None)
            else:
                node["datasets"] = False
    config.edit_yaml(config.SETTINGS_FILE, change)
    audit(request, "topic saved", target=name, detail=entry)
    restart_note("topics (seeds and pinned words need a restart; new seeds need a build too)")
    return {"saved": name, "rebuild": True}


@app.delete("/api/topics/{name}")
def topic_delete(request: Request, name: str):
    need(request, "administrator")

    def change(doc):
        if name not in (doc.get("topics") or {}):
            raise VeilError(f"No topic named {name}", 404)
        del doc["topics"][name]
    config.edit_yaml(config.SETTINGS_FILE, change)
    audit(request, "topic removed", target=name)
    restart_note("topics")
    return {"removed": name}


@app.get("/api/sources")
def sources(request: Request):
    need(request, "viewer")
    spec = config.load_yaml(config.path("tools", "sources.yaml"))
    out = []
    for name, src in (spec.get("sources") or {}).items():
        local = os.path.expanduser(src.get("local") or "")
        out.append({"name": name, "description": src.get("description"), "format": src.get("format"),
                    "use": src.get("use"), "url": src.get("url"), "local": src.get("local"),
                    "present": bool(local) and os.path.exists(local),
                    "enabled": src.get("enabled", True) is not False})
    return {"sources": out}


@app.patch("/api/sources/{name}")
async def source_set(request: Request, name: str):
    need(request, "administrator")
    b = await body_of(request)
    if not isinstance(b.get("enabled"), bool):
        raise VeilError("enabled is true or false")
    file = config.path("tools", "sources.yaml")

    def change(doc):
        if name not in (doc.get("sources") or {}):
            raise VeilError(f"No source named {name}", 404)
        doc["sources"][name]["enabled"] = b["enabled"]
    config.edit_yaml(file, change)
    audit(request, "dataset switched", target=name, detail="on" if b["enabled"] else "off")
    return {"saved": name}


# ---------- tools (the same ones you run on myserver) ----------

JOBS = {}
JOB_LOCK = threading.Lock()


def tools_spec():
    return (config.load_yaml(config.path("tools", "tools.yaml")).get("tools")) or {}


def choices(kind):
    if kind == "sources":
        return list((config.load_yaml(config.path("tools", "sources.yaml")).get("sources") or {}))
    if kind == "topics":
        return list((config.settings().get("topics") or {}))
    if kind == "assistants":
        try:
            return list(config.load_yaml(config.path("personality", "sources.yaml")))
        except FileNotFoundError:
            return []
    if kind == "misses":
        try:
            n = len(config.load_yaml(config.path("learn", "misses.yaml")).get("misses") or [])
        except FileNotFoundError:
            n = 0
        return [str(i) for i in range(1, n + 1)]
    return []


@app.get("/api/tools")
def tools_list(request: Request):
    actor = need(request, "viewer")
    out = []
    for tid, t in tools_spec().items():
        role = t.get("role", "administrator")
        args = {}
        for a, spec in (t.get("args") or {}).items():
            args[a] = {"optional": bool(spec.get("optional")),
                       "choices": choices(spec["choices"]) if spec.get("choices") else None,
                       "text": bool(spec.get("text"))}
        out.append({"id": tid, "group": t.get("group", "Tools"), "section": t.get("section") or "",
                    "page": t.get("page") or "tools",
                    "label": t.get("label", tid),
                    "about": t.get("about", ""), "role": role, "args": args,
                    "allowed": security.RANK[actor["role"]] >= security.RANK.get(role, 3),
                    "restart": bool(t.get("restart"))})
    with JOB_LOCK:
        running = next((j["id"] for j in JOBS.values() if j["state"] == "running"), None)
    return {"tools": out, "running": running}


def command_for(tool, args):
    cmd = []
    specs = tool.get("args") or {}
    for part in tool["run"]:
        m = re.fullmatch(r"(.*)\{(\w+)\}(.*)", str(part))
        if not m:
            cmd.append(str(part))
            continue
        name = m.group(2)
        spec = specs.get(name) or {}
        value = str(args.get(name) or "").strip()
        if not value:
            if spec.get("optional"):
                continue
            raise VeilError(f"Pick a {name}")
        if spec.get("choices"):
            if value not in choices(spec["choices"]):
                raise VeilError(f"{value} isn't one of the {spec['choices']}")
        elif not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", value):
            raise VeilError(f"{name}: letters, digits, _ . - only")
        cmd.append(m.group(1) + value + m.group(3))
    return cmd


def run_job(job, cmd, writes):
    env = dict(os.environ, ROUTER_URL=f"http://127.0.0.1:{os.environ.get('ROUTER_PORT', 8770)}",
               ROUTER_TOKEN=security.INTERNAL, PYTHONUNBUFFERED="1")
    started = time.monotonic()
    try:
        p = subprocess.Popen(cmd, cwd=config.ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, text=True, bufsize=1)
        job["pid"] = p.pid
        for line in p.stdout:
            with JOB_LOCK:
                job["lines"].append(line.rstrip("\n"))
                if len(job["lines"]) > 20000:
                    del job["lines"][:1000]
                    job["trimmed"] = True
        job["exit"] = p.wait()
        job["state"] = "done" if job["exit"] == 0 else "failed"
    except Exception as e:
        job["lines"].append(f"! couldn't run it: {e}")
        job["state"] = "failed"
    job["seconds"] = round(time.monotonic() - started, 1)
    for folder in writes:
        top = config.path(folder)
        for base, _, names in os.walk(top):
            for n in names:
                config.hand_back(os.path.join(base, n))


@app.post("/api/tools/{tid}")
async def tool_run(request: Request, tid: str):
    t = tools_spec().get(tid)
    if not t:
        raise VeilError(f"No tool named {tid}", 404)
    need(request, t.get("role", "administrator"))
    b = await body_of(request)
    cmd = command_for(t, b.get("args") or {})
    with JOB_LOCK:
        if any(j["state"] == "running" for j in JOBS.values()):
            raise VeilError("Another tool is still running; wait for it to finish", 409)
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "tool": tid, "label": t.get("label", tid), "cmd": " ".join(cmd), "state": "running",
               "lines": [], "exit": None, "started": time.time(), "restart": bool(t.get("restart"))}
        JOBS[jid] = job
        for old in sorted(JOBS.values(), key=lambda j: j["started"])[:-10]:
            JOBS.pop(old["id"], None)
    audit(request, "tool run", target=tid, detail=" ".join(cmd))
    threading.Thread(target=run_job, args=(job, cmd, t.get("writes") or []), daemon=True).start()
    if t.get("restart"):
        restart_note(f"tool: {t.get('label', tid)}")
    return {"job": jid, "cmd": job["cmd"]}


@app.get("/api/jobs/{jid}")
def job_get(request: Request, jid: str, since: int = 0):
    need(request, "viewer")
    with JOB_LOCK:
        j = JOBS.get(jid)
        if not j:
            raise VeilError("No such job (only the last 10 are kept)", 404)
        return {k: v for k, v in j.items() if k != "lines"} | {"lines": j["lines"][since:], "next": len(j["lines"])}


@app.get("/api/jobs")
def jobs(request: Request):
    need(request, "viewer")
    with JOB_LOCK:
        return {"jobs": [{k: v for k, v in j.items() if k != "lines"}
                         for j in sorted(JOBS.values(), key=lambda j: -j["started"])]}


# ---------- flair: each personality's file, her book candidates, how the books are combed ----------

PERS = config.path("personality")
SLOTS = ("any", "opener", "closer", "aside")
MOODS = ("plain", "warning", "sorry")


def assistant_ok(who):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", who or "") or who in ("sources", "combing", "candidates", "approved"):
        raise VeilError("Assistant names are lowercase letters, digits, _ or -")
    return who


def clean_flourish(f):
    text = " ".join(str(f.get("text") or "").split())
    if not text or len(text) > 200:
        raise VeilError("Each flourish needs text (200 characters at most)")
    if text.endswith("?"):
        raise VeilError(f"\"{text}\": a flourish is never a question (the persona must end on its own question)")
    slot = str(f.get("slot") or "opener").lower()
    if slot not in SLOTS:
        raise VeilError(f"slot is one of {', '.join(SLOTS)}")
    topics_ = [str(t).lower() for t in (f.get("topics") or ["any"])] or ["any"]
    mood = [str(m).lower() for m in (f.get("mood") or ["plain"])] or ["plain"]
    if any(m not in MOODS for m in mood):
        raise VeilError(f"mood is one or more of {', '.join(MOODS)}")
    out = {"text": text, "slot": slot, "topics": topics_, "mood": mood}
    if f.get("placeholder"):
        out["placeholder"] = True
    return out


@app.get("/api/flair")
def flair_all(request: Request):
    need(request, "viewer")
    r = router()
    names = sorted(set(r.FLAIR.names()) | set(choices("assistants")))
    out = []
    for who in names:
        try:
            spec = config.plain(config.load_yaml(os.path.join(PERS, f"{who}.yaml")))
        except FileNotFoundError:
            spec = {}
        try:
            approved = len(config.load_yaml(os.path.join(PERS, "approved", f"{who}.yaml")).get("flourishes") or [])
        except FileNotFoundError:
            approved = 0
        try:
            cands = config.load_yaml(os.path.join(PERS, "candidates", f"{who}.yaml")).get("candidates") or []
        except FileNotFoundError:
            cands = []
        out.append({"name": who, "rate": spec.get("rate"), "max_in_a_row": spec.get("max_in_a_row"),
                    "flourishes": len(spec.get("flourishes") or []), "approved": approved,
                    "candidates": len(cands), "kept": sum(str(c.get("keep")).lower() in ("yes", "true") for c in cands),
                    "has_file": bool(spec), "names": spec.get("names") or {}})
    return {"personalities": out, "names_in_replies": config.settings().get("names_in_replies")}


@app.get("/api/flair/{who}")
def flair_one(request: Request, who: str):
    need(request, "viewer")
    assistant_ok(who)
    try:
        spec = config.plain(config.load_yaml(os.path.join(PERS, f"{who}.yaml")))
    except FileNotFoundError:
        spec = {"rate": 0, "max_in_a_row": 1, "flourishes": []}
    try:
        approved = config.plain(config.load_yaml(os.path.join(PERS, "approved", f"{who}.yaml")).get("flourishes") or [])
    except FileNotFoundError:
        approved = []
    try:
        src = config.plain((config.load_yaml(os.path.join(PERS, "sources.yaml")) or {}).get(who) or {})
    except FileNotFoundError:
        src = {}
    return {"name": who, "personality": spec, "approved": approved, "sources": src}


@app.put("/api/flair/{who}")
async def flair_save(request: Request, who: str):
    """Her personality file: rate, max_in_a_row, names (rate, max_in_a_row, enabled), flourishes."""
    need(request, "administrator")
    assistant_ok(who)
    b = await body_of(request)
    try:
        rate = float(b.get("rate", 0))
        streak = int(b.get("max_in_a_row", 1))
    except (TypeError, ValueError):
        raise VeilError("rate is a number from 0 to 1; max_in_a_row a whole number")
    if not 0 <= rate <= 1 or not 0 <= streak <= 10:
        raise VeilError("rate is 0 to 1; max_in_a_row 0 to 10")
    # her lines bank is edited line by line now (PATCH /lines); a whole list only if one is sent
    flourishes = [clean_flourish(f) for f in (b.get("flourishes") or [])] if "flourishes" in b else None
    names = b.get("names")
    if names is not None:
        if not isinstance(names, dict):
            raise VeilError("names is a set of knobs (rate, max_in_a_row, min_score)")
        names = {k: names[k] for k in ("rate", "max_in_a_row", "min_score") if k in names}
    file = os.path.join(PERS, f"{who}.yaml")
    header = (f"# personality/{who}.yaml - {who.title()}'s flair. Read by flair.py; edited on the Flair page.\n"
              "# (See defaults/examples/personality/assistant.yaml for what each knob means.)")

    def change(doc):
        from ruamel.yaml.comments import CommentedMap
        doc["rate"] = rate
        doc["max_in_a_row"] = streak
        if names is not None:
            if names:
                doc["names"] = CommentedMap(names)
            elif "names" in doc:
                del doc["names"]
        if flourishes is not None:
            doc["flourishes"] = flairlines.lines_seq(flourishes)
    config.edit_yaml(file, change, header=header)
    audit(request, "flair saved", target=who, detail=f"rate {rate}" + (f", {len(flourishes)} flourishes" if flourishes is not None else ""))
    restart_note("flair")
    return {"saved": who}


@app.get("/api/flair/{who}/candidates")
def candidates(request: Request, who: str):
    need(request, "viewer")
    assistant_ok(who)
    try:
        cands = config.plain(config.load_yaml(os.path.join(PERS, "candidates", f"{who}.yaml")).get("candidates") or [])
    except FileNotFoundError:
        cands = []
    for i, c in enumerate(cands):
        c["index"] = i
        c["keep"] = str(c.get("keep")).lower() in ("yes", "true")
    return {"candidates": cands}


@app.post("/api/flair/{who}/candidates/accept")
async def candidates_accept(request: Request, who: str):
    """Accept on Lines from her books: {found, slot?, mood?, topics?} moves that line into her lines bank."""
    need(request, "reviewer")
    assistant_ok(who)
    b = await body_of(request)
    changes = {k: b[k] for k in ("slot", "topics", "mood") if b.get(k)}
    if "slot" in changes and changes["slot"] not in SLOTS:
        raise VeilError(f"slot is one of {', '.join(SLOTS)}")
    if any(m not in MOODS for m in changes.get("mood") or []):
        raise VeilError(f"mood is one or more of {', '.join(MOODS)}")
    line = flairlines.accept(who, str(b.get("found") or ""), changes)
    if not line:
        raise VeilError("That line isn't in the persona's books list any more (reload the page)", 404)
    audit(request, "book line accepted into the lines bank", target=who, detail=line["text"])
    restart_note(f"flair: {who}")
    return {"banked": line}


@app.post("/api/flair/{who}/candidates/clear")
def candidates_clear(request: Request, who: str):
    """Empty Lines from her books; combing the books again fills it (leaving out what's taken)."""
    need(request, "reviewer")
    assistant_ok(who)
    n = flairlines.clear_candidates(who)
    audit(request, "book lines cleared", target=who, detail=f"{n} lines")
    return {"cleared": n}


@app.patch("/api/flair/{who}/lines")
async def lines_edit(request: Request, who: str):
    """One line of her lines bank: {index, text_was, text, slot, topics, mood} saves it;
    {index, text_was, delete: true} deletes it."""
    need(request, "administrator")
    assistant_ok(who)
    b = await body_of(request)
    try:
        i = int(b.get("index"))
    except (TypeError, ValueError):
        raise VeilError("Which line? (reload the page)")
    line = None if b.get("delete") else clean_flourish({"text": b.get("text"), "slot": b.get("slot"),
                                                        "topics": b.get("topics"), "mood": b.get("mood")})
    try:
        lines = flairlines.edit_bank(who, i, b.get("text_was"), line)
    except LookupError as e:
        raise VeilError(str(e), 409)
    audit(request, "lines bank: line deleted" if line is None else "lines bank: line saved", target=who,
          detail={"was": b.get("text_was"), "now": line and line["text"]})
    restart_note(f"flair: {who}")
    return {"lines": lines}


@app.post("/api/flair/{who}/lines")
async def lines_add(request: Request, who: str):
    """Lines typed on the page into her lines bank: {lines: [{text, slot?, topics?, mood?}]}."""
    need(request, "administrator")
    assistant_ok(who)
    b = await body_of(request)
    new = [clean_flourish(f) for f in (b.get("lines") or [])]
    if not new:
        raise VeilError("Type a line (or many, separated by |)")
    n = flairlines.add_to_bank(who, new)
    audit(request, "lines bank: lines added", target=who, detail=f"{n} added")
    restart_note(f"flair: {who}")
    return {"added": n, "already": len(new) - n}


@app.get("/api/combing")
def combing_get(request: Request):
    need(request, "viewer")
    try:
        return {"combing": config.plain(config.load_yaml(os.path.join(PERS, "combing.yaml")))}
    except FileNotFoundError:
        return {"combing": {}}


@app.put("/api/combing")
async def combing_set(request: Request):
    """The whole combing.yaml, as JSON: each list a list of words or phrases."""
    need(request, "administrator")
    b = (await body_of(request)).get("combing")
    if not isinstance(b, dict):
        raise VeilError("combing is a set of word lists")
    lists = ("said_words", "speaker_adjectives", "never", "story_words", "allowed_capitals",
             "closer_words", "interjections")

    def words(v, what):
        if not isinstance(v, list) or not all(isinstance(x, str) and 0 < len(x) <= 40 for x in v):
            raise VeilError(f"{what} is a list of words or short phrases")
        return [" ".join(x.split()) for x in v]
    clean = {k: words(b[k], k) for k in lists if k in b}
    if "max_words" in b:
        clean["max_words"] = int(b["max_words"])
    for group in ("moods", "topics"):
        if group in b:
            if not isinstance(b[group], dict):
                raise VeilError(f"{group} is a set of word lists")
            clean[group] = {str(k): words(v, f"{group}.{k}") for k, v in b[group].items()}
    if "score" in b:
        clean["score"] = {k: int(v) for k, v in (b["score"] or {}).items()}

    def change(doc):
        for k, v in clean.items():
            if isinstance(v, list):
                s_ = config.flow_list(v)
                doc[k] = s_
            elif isinstance(v, dict):
                node = config.map_in(doc, k)
                for kk in list(node):
                    if kk not in v:
                        del node[kk]
                for kk, vv in v.items():
                    if isinstance(vv, list):
                        s_ = config.flow_list(vv)
                        node[kk] = s_
                    else:
                        node[kk] = vv
            else:
                doc[k] = v
    config.edit_yaml(os.path.join(PERS, "combing.yaml"), change)
    audit(request, "combing saved")
    return {"saved": True}


@app.put("/api/flair/{who}/sources")
async def flair_sources(request: Request, who: str):
    """Her books, speakers and near words (personality/sources.yaml)."""
    need(request, "administrator")
    assistant_ok(who)
    b = await body_of(request)
    speakers_ = [str(x).strip().lower() for x in (b.get("speakers") or []) if str(x).strip()]
    near = [str(x).strip().lower() for x in (b.get("near") or []) if str(x).strip()]
    books = []
    for bk in b.get("books") or []:
        title, url, local = (str(bk.get(k) or "").strip() for k in ("title", "url", "local"))
        if not (title and url.startswith(("https://", "http://")) and local):
            raise VeilError("Each book needs a title, an http(s) address and a local path")
        books.append({"title": title, "url": url, "local": local})

    def change(doc):
        from ruamel.yaml.comments import CommentedMap, CommentedSeq
        node = config.map_in(doc, who)
        for k, v in (("speakers", speakers_), ("near", near)):
            s_ = config.flow_list(v)
            node[k] = s_
        node["books"] = CommentedSeq([CommentedMap(x) for x in books])
    config.edit_yaml(os.path.join(PERS, "sources.yaml"), change)
    audit(request, "flair sources saved", target=who, detail=f"{len(books)} books")
    return {"saved": who}


# ---------- integrations: Oread, the weather brain, Donetick, LiteLLM ----------

@app.get("/api/integrations")
def integrations(request: Request):
    need(request, "viewer")
    s = config.settings()
    r = router()
    o = dict(config.section(config.section(s, "integrations"), "oread"))
    ha = dict(config.section(config.section(s, "integrations"), "home_assistant"))
    services = {}
    for name, svc in (s.get("services") or {}).items():
        services[name] = {"enabled": config.service_enabled(svc), "kind": svc.get("kind"), "url": svc.get("url"),
                          "spec": svc.get("spec"), "timeout": svc.get("timeout"), "secret": svc.get("secret"),
                          "secret_from": config.secret_source(svc.get("secret")),
                          "title": svc.get("title") or name.replace("_", " ").capitalize(),
                          "connector": bool(connector_file(name)),
                          "keeps_copy": name in r.CONNECTORS, "cache_refresh_seconds": svc.get("cache_refresh_seconds", 60),
                          "spec_prefix": svc.get("spec_prefix") or "", "test_said": svc.get("test_said") or "",
                          "spoken_name": svc.get("spoken_name") or "", "pages_max": svc.get("pages_max", 1),
                          "send_only_accepted": bool(svc.get("send_only_accepted")),
                          "app_version": app_version(openapi.load(commands_file(name))),
                          "topics": [t for t, v in (s.get("topics") or {}).items()
                                     if (v or {}).get("service") == name or name in ((v or {}).get("then") or [])]}
    o["token_from"] = config.secret_source(o.get("token"))
    from veil import wyoming
    o["listening"] = wyoming.listening()
    ha["token_from"] = config.secret_source(ha.get("token"))
    o["app_version"] = app_version(openapi.load(commands_file("oread")))
    warn = config.section(s, "security").get("refused_warn_minutes", 60)
    return {"oread": o, "home_assistant": ha, "services": services,
            "refused": access.ACCESS.lately(warn) if warn else [], "refused_minutes": warn,
            "litellm": dict(config.litellm(s), url=r.LITELLM_URL, running=r.FALLBACK_MODEL,
                            key_name=llm_key_name(), key_from=config.secret_source(llm_key_name()))}


def connector_file(name):
    """connectors/<name>.yaml: an app's voice map and its clean-up words (an app we didn't write)."""
    if not re.fullmatch(r"[a-z0-9_]{1,40}", name or ""):
        return None
    path = config.path("connectors", f"{name}.yaml")
    return path if os.path.exists(path) else None


@app.get("/api/integrations/{name}/details")
def integration_details(request: Request, name: str):
    """The tabs an integration has beyond its connection: its options (settings.yaml services:
    <name>: options:), its clean-up words and voice map (connectors/<name>.yaml), and the doors it
    calls the router through (security: doors: with program: <name>)."""
    need(request, "viewer")
    s = config.settings()
    svc = (s.get("services") or {}).get(name)
    known = svc is not None or name in (s.get("integrations") or {}) or name == "litellm"
    if not known:
        raise VeilError(f"No integration named {name}", 404)
    notes = settings_comments()["comments"]
    out = {"name": name, "options": {}, "option_notes": {}, "language": {}, "language_notes": {}, "actions": [],
           "defaults": {}, "connector": None,
           "doors": [dict(d, name=n) for n, d in doorset.doors(config.section(s, "security")).items()
                     if d.get("program") == name]}
    if svc is not None:
        out["options"] = dict(svc.get("options") or {})
        out["option_notes"] = {k: notes.get(f"services.{name}.options.{k}", "") for k in out["options"]}
    path = connector_file(name)
    if path:
        hand = config.load_yaml(path)
        cnotes = settings_comments(path)["comments"]
        out["connector"] = os.path.relpath(path, config.path())
        out["stamps"] = {k: config.stamp(path, k) for k in ("actions", "rules")}   # sent back on Save: an old copy is refused
        out["language"] = {k: v for k, v in (hand.get("language") or {}).items() if isinstance(v, (list, dict))}
        out["language_notes"] = {k: cnotes.get(f"language.{k}", "") for k in out["language"]}
        for k, (empty, note) in GENERIC_LANGUAGE.items():       # every app's matching reads these
            out["language"].setdefault(k, empty)
            out["language_notes"][k] = out["language_notes"].get(k) or note
        out["defaults"] = hand.get("defaults") or {}
        out["match_min"] = hand.get("match_min", (svc or {}).get("options", {}).get("match_min") if svc else None)
        out["sound_alike"] = bool(hand.get("sound_alike", False))
        for a, spec in (hand.get("actions") or {}).items():
            spec = spec or {}
            out["actions"].append({"name": a, "api": spec.get("api", ""), "words": spec.get("words") or [],
                                   "objects": spec.get("objects") or [], "needs": spec.get("needs") or {},
                                   "note": cnotes.get(f"actions.{a}", "")})
        # user rules (the User rules tab): each step as the page edits it, and the steps it can use
        saved_cmds = openapi.load(commands_file(name)) or {}
        known = {c["api"].upper() for c in openapi.expanded(saved_cmds.get("commands"))} if saved_cmds else None
        out["rules"] = rules_rows(hand.get("rules") or {}, {n: rulebook.check(r or {}, known) for n, r in (hand.get("rules") or {}).items()})
        out["rule_steps"] = rulebook.STEPS
    where, nd = apps.node(s, name)
    if where:
        i = apps.info(s, name)
        out["title"] = i["title"]
        out["spec"] = i["spec"]
        saved = openapi.load(commands_file(name))
        if i["spec"] or saved:
            # None: the spec hasn't been read yet; a command whose path takes a few values, once per value too
            out["commands"] = openapi.expanded(saved["commands"]) if (saved or {}).get("commands") else (saved or {}).get("commands")
        out["heard_needs"] = dict(config.knob(s, "heard_needs") or {})
        # Wepwawet compliance: its x-wepwawet section, as last read (None: not compliant, or not read)
        w = (saved or {}).get("wepwawet")
        out["wepwawet"] = w
        out["offers"] = []
        for key, o in ((w or {}).get("offers") or {}).items():
            bind = apps.OFFER_SETTINGS.get(key) or {}
            state = (nd.get("offers") or {}).get(key) or {}
            on = nd.get(bind["on"]) if "on" in bind else state.get("on")
            way = apps.way_from_setting(key, nd.get(bind["way"])) if "way" in bind else state.get("way")
            out["offers"].append({"key": key, "title": o.get("title") or key.replace("_", " "), "description": o.get("description") or "",
                                  "ways": o.get("ways") or {}, "on": bool(on), "way": way})
        if where == "integrations" and not out["options"]:
            out["options"] = {k: v for k, v in (nd.get("options") or {}).items()}
    if svc is not None:
        out["options_from"] = dict(svc.get("options_from") or {})
        # where an option's choices can come from: every app whose commands are read (any app,
        # not only this one), with its commands that list things and the fields they answer with
        out["sources"] = []
        for app_name, other in (s.get("services") or {}).items():
            cmds = (openapi.load(commands_file(app_name)) or {}).get("commands") or []
            gets = [{"api": c["api"], "summary": c.get("summary") or "", "returns": c.get("returns") or []}
                    for c in cmds if c["api"].upper().startswith("GET ") and c.get("returns")]
            if gets:
                out["sources"].append({"app": app_name, "title": (other or {}).get("title") or app_name, "commands": gets})
    return out


CONNECTOR_TEMPLATE = """# connectors/{name}.yaml - the voice map for {title} (an app we didn't write; the build reads it).
# Made on the Integrations page ({when}). Fill it in, then Tools, Maintenance, build.
# For each voice action:
#   api:        the app's command (method and path, as listed in its spec: the Commands tab)
#   learn_from: dataset intents whose sentences teach how people say this action
#   words:      your own words, for actions the datasets don't cover (kept short)
#   objects:    nouns that decide the action outright
#   needs:      spoken needs: details the action uses (required: she asks; default: used and said; optional)
# Only actions listed here can be spoken. The app's own quirks live in connectors/{name}.py
# (its helper, written for this app's API), its lines in phrases/{phrases}.yaml.

service: {name}
topic: {topic}
default_action: list

# the defaults are settings: services: {name}: options: in settings.yaml
defaults: {{}}

actions: {{}}

# the words its helper uses to clean up what was said (each list shows on the Integrations card)
language: {{}}
"""


@app.get("/api/integrations/add-choices")
def integration_add_choices(request: Request):
    """What Add an app offers: the vault keys no app uses yet (step 1, Security, Grantors), each
    with its program, and the topics no app answers yet."""
    need(request, "administrator")
    s = config.settings()
    free = sorted(t for t, v in (s.get("topics") or {}).items() if not (v or {}).get("service"))
    if phases.on("dump9"):       # a topic with an app can take another of the same nature, after it
        free += sorted(t for t, v in (s.get("topics") or {}).items() if (v or {}).get("service"))
    return {"keys": app_keys(), "topics": free}


@app.post("/api/integrations")
async def integration_add(request: Request):
    """Add an app: {name, title, kind (openapi: an app we didn't write, described by its OpenAPI
    spec; contract: one that speaks our /ask door), url, spec, secret, timeout, topic}. It starts
    switched off; its card's "Getting ready" tab says what's left before it can be switched on."""
    need(request, "administrator")
    b = await body_of(request)
    s = config.settings()
    name = str(b.get("name") or "").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", name):
        raise VeilError("An app's name is a short word: small letters, digits and _ (like mealie)")
    if name in (s.get("services") or {}) or name in (s.get("integrations") or {}) or name == "litellm":
        raise VeilError(f"There's already an integration named {name}")
    kind = b.get("kind") if b.get("kind") in ("openapi", "contract") else None
    if not kind:
        raise VeilError("kind is openapi (an app we didn't write) or contract (it speaks our /ask door)")
    url, spec = str(b.get("url") or "").strip(), str(b.get("spec") or "").strip()
    for k, v in (("url", url), ("spec", spec)):
        if v and not re.fullmatch(r"https?://[A-Za-z0-9.\-:\[\]_/]+", v):
            raise VeilError(f"{k} is an http:// or https:// address")
    if not url:
        raise VeilError("Where is it? (its url)")
    if kind == "openapi" and not spec:
        raise VeilError("An app we didn't write needs its OpenAPI (Swagger) spec's address")
    secret = str(b.get("secret") or "").strip().upper()
    if secret and not re.fullmatch(r"[A-Z][A-Z0-9_]{1,40}", secret):
        raise VeilError("Its key's name is like MEALIE_TOKEN (the vault keeps the key itself)")
    topic = str(b.get("topic") or "").strip().lower()
    if topic in ("none", "-"):
        topic = ""
    if topic:
        t = (s.get("topics") or {}).get(topic)
        if t is None:
            raise VeilError(f"There's no topic named {topic} (add it on Seed Topics first, or pick none)")
        if (t or {}).get("service") and not phases.on("dump9"):
            raise VeilError(f"The topic {topic} already belongs to {t['service']}")
    entry = {"enabled": False, "title": str(b.get("title") or name).strip()[:60], "kind": kind, "url": url,
             "spec": spec, "secret": secret, "timeout": float(b.get("timeout") or 8), "options": {}}
    def write(doc):
        config.set_in(doc, ["services", name], entry)
        if topic and ((s.get("topics") or {}).get(topic) or {}).get("service"):
            # a second app of the same nature: after the ones there, in order (its Seed Topics card)
            then = list(((s.get("topics") or {}).get(topic) or {}).get("then") or []) + [name]
            config.set_in(doc, ["topics", topic, "then"], config.flow_list(then))
        elif topic:
            config.set_in(doc, ["topics", topic, "service"], name)
    config.edit_yaml(config.SETTINGS_FILE, write)
    made = []
    if kind == "openapi" and not connector_file(name):
        path = config.path("connectors", f"{name}.yaml")
        with open(path, "w") as f:
            f.write(CONNECTOR_TEMPLATE.format(name=name, title=entry["title"], topic=topic or "''", phrases=name,
                                              when=time.strftime("%b %d, %Y")))
        config.hand_back(path)          # yours to edit too (written by the router, as root)
        made.append(f"connectors/{name}.yaml")
    audit(request, "app added", target=name, detail=f"{kind} {url}")
    restart_note(f"{name}: added")
    return {"added": name, "made": made}


@app.get("/api/integrations/{name}/ready")
def integration_ready(request: Request, name: str):
    """Getting an app ready: each step, whether it's done, and how."""
    need(request, "viewer")
    s = config.settings()
    svc = (s.get("services") or {}).get(name)
    if svc is None:
        raise VeilError(f"No service named {name}", 404)
    steps = []

    def step(what, done, how):
        steps.append({"step": what, "done": bool(done), "how": how})
    topics = [t for t, v in (s.get("topics") or {}).items() if (v or {}).get("service") == name]
    if svc.get("secret"):
        step(f"Its key ({svc['secret']}) is set", config.secret_source(svc["secret"]),
             "Security, API keys and vault, Grantors: Set (or .env).")
    if svc.get("kind") == "openapi":
        saved = openapi.load(commands_file(name))
        step("Its commands are read from its spec", saved and saved.get("commands"),
             "Commands: Read its spec (its address is on Connection).")
    step("A topic it answers", topics, "Seed Topics, Add a topic, with this app as its service (seed words that point at it).")
    if svc.get("kind") == "openapi":
        path = connector_file(name)
        hand = config.load_yaml(path) if path else {}
        actions = hand.get("actions") or {}
        known = {c["api"].upper() for c in openapi.expanded((saved or {}).get("commands"))}
        stray = [a for a, v in actions.items() if known and str((v or {}).get("api", "")).upper() not in known]
        step("Its voice map lists what can be said, each calling one of its commands", actions and not stray,
             "Voice map: Add an action for each thing to say (a word of your own, the command it calls, its words, its spoken needs)."
             + (f" Not one of its commands: {', '.join(stray)}." if stray else ""))
        broken = {n: rulebook.check(r or {}, known or None) for n, r in (hand.get("rules") or {}).items()}
        broken = {n: w for n, w in broken.items() if w}
        step("Its user rules check out (their steps, settings and commands)", not broken,
             "User rules: " + "; ".join(f"{n}: {w}" for n, w in broken.items()) + ". A rule that doesn't check out isn't used.")
        step(f"Its helper (connectors/{name}.py)", os.path.exists(config.path("connectors", f"{name}.py")),
             "The code that speaks the app's own API and its quirks: written for each app we didn't write.")
        phrases = svc.get("phrases") or name
        step(f"Its lines (phrases/{phrases}.yaml)", os.path.exists(config.path("phrases", f"{phrases}.yaml")),
             f"What the persona says for it; copy phrases/chores.yaml's shape (or set services: {name}: phrases:).")
        built = config.path("actions", f"{name}.yaml")
        built_map = config.load_yaml(built) if os.path.exists(built) else {}
        bad = [a for a, v in (built_map.get("actions") or {}).items() if (v or {}).get("spec") != "ok"]
        step("The build has made its voice map, every command found in its spec",
             built_map and built_map.get("spec_read") and not bad and len(built_map.get("actions") or {}) == len(actions),
             "Tools, Maintenance, build (after the topic and the voice map). Its report says which commands it found."
             + (f" Not found last time: {', '.join(bad)}." if bad else ""))
        step("Regression cases (tests/cases/)", any(os.path.exists(config.path("tests", "cases", f"{t}.yaml")) for t in topics + [name]),
             f"tests/cases/{(topics or [name])[0]}.yaml with requires: [{name}], so what it should decide is checked.")
    else:
        step("It answers the router's /ask door", svc.get("url"), "Connection, Test.")
    step("Switched on", config.service_enabled(svc), "Connection: On, Save, then restart.")
    return {"name": name, "kind": svc.get("kind"), "steps": steps, "ready": all(x["done"] for x in steps[:-1])}


def commands_file(name):
    """connectors/<name>.commands.json: the app's commands as last read from its spec and accepted."""
    if not re.fullmatch(r"[a-z0-9_]{1,40}", name or ""):
        return None
    return config.path("connectors", f"{name}.commands.json")


def openapi_service(name):
    """Any app with an OpenAPI spec: a service or an integration (veil/apps.py)."""
    i = apps.info(config.settings(), name)
    if not i["spec"]:
        raise VeilError(f"{i['title']} has no spec address (its URL / ports tab)", 404)
    return i


def voice_map_uses(name):
    """{command: [actions]} from the app's voice map."""
    path = connector_file(name)
    used = {}
    for a, v in ((config.load_yaml(path) if path else {}).get("actions") or {}).items():
        used.setdefault(str((v or {}).get("api", "")).strip().upper(), []).append(a)
    return used


PENDING_SPECS = {}      # a spec read but not yet accepted, per app (gone after a restart: read it again)
KEPT_BESIDE = ("wepwawet", "auth", "base", "version", "checked")     # kept beside the commands at each save


async def check_versions():
    """At start-up: read each app's spec once and note the version it runs now (checked), beside
    the version its commands were accepted at. Nothing else changes: a new version is flagged on
    Integrations and waits for Read its spec and Accept. Apps that can't be reached are left as they
    were. (settings: router: check_app_versions_at_start)"""
    s = config.settings()
    names = list((s.get("services") or {})) + [n for n, v in (s.get("integrations") or {}).items() if isinstance(v, dict)]
    out = {}
    for name in names:
        path = commands_file(name)
        saved = openapi.load(path)
        if not saved:
            continue                       # never read: nothing to compare with
        if phases.on("dump10") and recently_checked(saved, s):
            continue                       # read within the day: an app with a limit spends no call (dump10)
        try:
            svc = apps.info(s, name)
            if not svc["spec"]:
                continue
            spec = await apps.read_spec(svc)
        except Exception as e:
            log.info("  version check: %s not read (%s%s)", name, type(e).__name__, f": {str(e)[:120]}" if str(e) else "")
            continue
        running = str((spec.get("info") or {}).get("version") or "") or None
        saved["checked"] = {"version": running, "at": time.strftime("%Y-%m-%d %H:%M"), "from": svc["spec"]}
        if "version" not in saved:
            # accepted before versions were recorded (Oct 14): what it runs now becomes the version
            # its commands are taken to be at; flagging it as a change would only alarm
            saved["version"] = running
            log.info("  version check: %s: no version recorded with its commands yet; %s taken as theirs",
                     name, running or "no version")
        openapi.save(path, saved.get("read_from") or svc["spec"], saved.get("title"), saved.get("commands") or [],
                     {k: saved[k] for k in KEPT_BESIDE if k in saved})
        config.hand_back(path)
        v = app_version(saved)
        out[name] = v
        log.info("  version check: %s runs %s%s", name, running or "no version",
                 f" (accepted at {v['version'] or 'no version'}: look at its Commands)" if v["version_changed"] else "")
    return out


def recently_checked(saved, s):
    """Was its spec read for the version check within router: check_app_versions_every_hours?"""
    hours = float(config.section(s, "router").get("check_app_versions_every_hours", 24) or 0)
    at = (saved.get("checked") or {}).get("at")
    if not at or hours <= 0:
        return False
    try:
        return time.time() - time.mktime(time.strptime(at, "%Y-%m-%d %H:%M")) < hours * 3600
    except ValueError:
        return False


def app_version(saved):
    """The app's version as its spec said it: when its commands were accepted, and at the latest read.
    An app whose spec names no version is compared by its commands alone."""
    saved = saved or {}
    checked = saved.get("checked") or {}
    version, running = saved.get("version"), checked.get("version")
    return {"version": version, "running": running, "checked_at": checked.get("at"),
            "version_changed": bool(saved) and "checked" in saved and "version" in saved and running != version}


@app.get("/api/integrations/{name}/commands")
def integration_commands(request: Request, name: str):
    """The app's commands as saved (connectors/<name>.commands.json), each with the voice map's
    actions that call it, and a pending read with its marks if one waits to be accepted."""
    need(request, "viewer")
    openapi_service(name)
    saved = openapi.load(commands_file(name))
    used = voice_map_uses(name)
    rows = [dict(c, mark="same") for c in (saved or {}).get("commands") or []]
    pend = PENDING_SPECS.get(name)
    if pend:
        rows = pend["rows"]
    for r in rows:
        r["actions"] = used.get(r["api"].upper(), [])
    return dict({"name": name, "saved": bool(saved), "read_from": (saved or {}).get("read_from"),
                 "accepted": (saved or {}).get("accepted"), "title": (saved or {}).get("title"),
                 "pending": bool(pend), "commands": rows, "key_change": key_said((pend or {}).get("key_change"))}, **app_version(saved))


def key_said(change):
    """How its key is sent, was and is now, in plain words, or None (inbound defense 4)."""
    if not change:
        return None
    way = lambda a: "no key at all" if not a else f"in the {a.get('name')} header" + (f" after \"{a.get('prefix').strip()}\"" if (a.get("prefix") or "").strip() else "")  # noqa: E731
    return f"How its key is sent changed: it was {way(change.get('was'))}, its spec now says {way(change.get('now'))}. Accept only if you expected this."


@app.post("/api/integrations/{name}/commands/read")
async def integration_commands_read(request: Request, name: str):
    """Read the app's spec now. The first time, what it lists is saved at once; after that the
    differences are marked (add, modified, deleted) and wait for Accept."""
    need(request, "administrator")
    svc = openapi_service(name)
    try:
        spec = await apps.read_parts(svc, await apps.read_spec(svc))
    except VeilError:
        raise
    except Exception as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (401, 403):
            # it shows its description only to a program with a key: say which, and where it goes
            have = config.secret_source(svc["key"]) if svc["key"] else None
            raise VeilError(f"{svc['title']} wants a key to show its spec ({code}). "
                            + (f"The key it has ({svc['key']}, from {have}) was refused: make a new one on {svc['title']}."
                               if have else f"Make one on {svc['title']} (a viewer is enough), then Security, API keys and vault, "
                               f"Grantors: Set {svc['key'] or 'its key'}. No restart needed."), 502)
        raise VeilError(f"Couldn't read its spec ({svc['spec']}): {str(e)[:200]}", 502)
    cmds = openapi.commands(spec)
    title = (spec.get("info") or {}).get("title")
    extra = apps.described(spec, svc["spec"], svc["node"].get("url"))          # its x-wepwawet section, how to call it
    path = commands_file(name)
    saved = openapi.load(path)
    # the app's version (its spec's info: version:): what it said when its commands were last
    # accepted (version), and what it says now (checked), so an update shows before it can hurt
    running = str((spec.get("info") or {}).get("version") or "") or None
    checked = {"version": running, "at": time.strftime("%Y-%m-%d %H:%M"), "from": svc["spec"]}
    key_change = None
    if saved and phases.on("dump16") and "auth" in saved and (extra.get("auth") or None) != (saved.get("auth") or None):
        # how its key is sent changed: never taken quietly; it waits for Accept, said plainly (inbound defense 4)
        key_change = {"was": saved.get("auth"), "now": extra.get("auth")}
        extra = {k: v for k, v in extra.items() if k != "auth"}
    if saved:          # how it fits and how to call it aren't commands: kept at once
        saved.update(extra)
        saved["checked"] = checked
        # what the router reads beside each command (its parameters, their types) is kept at once
        # too: it changes how the router writes an address, not what the command does
        fresh = {c["api"]: c for c in cmds}
        for c in saved.get("commands") or []:
            for k in ("params", "types", "patterns", "enums", "accepts"):
                if k in (fresh.get(c["api"]) or {}):
                    c[k] = fresh[c["api"]][k]
        openapi.save(path, saved.get("read_from") or svc["spec"], saved.get("title"), saved.get("commands") or [],
                     {k: saved[k] for k in KEPT_BESIDE if k in saved})
    if not saved:
        openapi.save(path, svc["spec"], title, cmds, dict(extra, version=running, checked=checked))
        config.hand_back(path)
        PENDING_SPECS.pop(name, None)
        audit(request, "app spec read", target=name, detail=f"{len(cmds)} commands")
        return {"first": True, "count": len(cmds), "changes": 0}
    rows = openapi.compare(saved.get("commands"), cmds)
    changes = sum(1 for x in rows if x["mark"] != "same")
    version_changed = running != saved.get("version")
    if changes or version_changed or key_change:
        # a new version waits for Accept even when its commands look the same: what they do may not
        PENDING_SPECS[name] = {"rows": rows, "commands": cmds, "title": title, "spec": svc["spec"], "version": running,
                               **({"key_change": key_change} if key_change else {})}
    else:
        PENDING_SPECS.pop(name, None)
    return {"first": False, "count": len(cmds), "changes": changes, "version_changed": version_changed,
            "version": saved.get("version"), "running": running, "key_change": key_change}


@app.post("/api/integrations/{name}/commands/accept")
def integration_commands_accept(request: Request, name: str):
    """Keep the spec just read as the app's commands (the voice map's Calls choices)."""
    need(request, "administrator")
    openapi_service(name)
    pend = PENDING_SPECS.pop(name, None)
    if not pend:
        raise VeilError("There are no changes waiting: read its spec first", 409)
    path = commands_file(name)
    old = openapi.load(path) or {}
    keep = {k: old[k] for k in KEPT_BESIDE if k in old}
    keep["version"] = pend.get("version")
    if pend.get("key_change"):                  # how its key is sent, now as its spec says (you accepted it)
        keep["auth"] = pend["key_change"]["now"]
    openapi.save(path, pend["spec"], pend["title"], pend["commands"], keep)
    config.hand_back(path)
    gone = [x["api"] for x in pend["rows"] if x["mark"] == "deleted"]
    audit(request, "app spec accepted", target=name, detail=f"{len(pend['commands'])} commands")
    return {"accepted": len(pend["commands"]), "deleted": gone}


@app.post("/api/integrations/{name}/commands/discard")
def integration_commands_discard(request: Request, name: str):
    need(request, "administrator")
    PENDING_SPECS.pop(name, None)
    return {"discarded": name}


NEED_RULES = ("required", "optional", "default")


@app.patch("/api/integrations/{name}/voice-map")
async def integration_voice_map_knobs(request: Request, name: str):
    """The voice map's own knobs, kept in connectors/<name>.yaml: {match_min: 0..1, or null} and
    {sound_alike: true or false} (either or both)."""
    need(request, "administrator")
    path = connector_file(name)
    if not path:
        raise VeilError(f"{name} has no voice map", 404)
    b = await body_of(request)
    v = b.get("match_min")
    if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1):
        raise VeilError("match min is a share from 0 to 1 (like 0.6), or empty")
    sa = b.get("sound_alike")
    if sa is not None and not isinstance(sa, bool):
        raise VeilError("sound alike is on or off")

    def put(doc, key, value, comment):
        if key in doc:
            doc[key] = value
        else:
            doc.insert(list(doc.keys()).index("actions") if "actions" in doc else len(doc), key, value, comment=comment)

    def write(doc):
        if "match_min" in b:
            if v is None:
                doc.pop("match_min", None)
            else:
                put(doc, "match_min", v, "share of an item's words that must be said to count as that item (the Voice map tab)")
        if sa is not None:
            put(doc, "sound_alike", sa, "nothing found by the words: try how they sound (the Voice map tab)")

    def drop_old(doc):        # it lived in settings.yaml's options before the Voice map tab had it
        opts = (((doc.get("services") or {}).get(name) or {}).get("options")) or {}
        if "match_min" in opts:
            del opts["match_min"]
    config.edit_yaml(path, write, width=4096)
    config.edit_yaml(config.SETTINGS_FILE, drop_old)
    audit(request, "voice map knob", target=name, detail=str({k: b[k] for k in ("match_min", "sound_alike") if k in b}))
    restart_note(f"{name}: voice map")
    return {"match_min": v, "sound_alike": sa}


@app.put("/api/integrations/{name}/actions")
async def integration_actions(request: Request, name: str):
    """Save the voice map from the page: {actions: [{name, was, api, words, needs: {detail: rule}}]}.
    Each action keeps what the page doesn't show (learn_from, objects, fields...) and its comment;
    one left out is taken out. The build then learns the words; the needs are used after a restart."""
    need(request, "administrator")
    path = connector_file(name)
    if not path:
        raise VeilError(f"{name} has no voice map (connectors/{name}.yaml)", 404)
    b = await body_of(request)
    rows = b.get("actions")
    if not isinstance(rows, list):
        raise VeilError("actions is a list")
    saved = openapi.load(commands_file(name))
    known = {c["api"].upper() for c in openapi.expanded((saved or {}).get("commands"))}
    # a user rule or a brain flea of the same name would win over the action (the rules save refuses
    # the other way round): refused here too (dump15)
    taken = {k: v for k, v in names_taken().items() if "Voice map" not in v} if phases.on("dump15") else {}
    clean, seen = [], set()
    for r in rows:
        a = str((r or {}).get("name") or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", a):
            raise VeilError(f"An action is one short word: small letters, digits and _ (\"{a}\" isn't)")
        if a in taken:
            raise VeilError(f"{a} is already {taken[a]}: pick another name")
        if a in seen:
            raise VeilError(f"Two actions are named {a}: each must be its own word")
        seen.add(a)
        api_ = " ".join(str(r.get("api") or "").split())
        if not re.fullmatch(r"(GET|POST|PUT|PATCH|DELETE) /\S*", api_, re.I):
            raise VeilError(f"{a}: pick the command it calls")
        api_ = api_.split(" ", 1)[0].upper() + " " + api_.split(" ", 1)[1]
        if saved and api_.upper() not in known:
            raise VeilError(f"{a}: {api_} isn't one of the app's commands (Commands tab)")
        words = [" ".join(str(w).lower().split()) for w in (r.get("words") or []) if str(w).strip()]
        needs = {}
        for k, v in (r.get("needs") or {}).items():
            k = str(k).strip().lower()
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", k):
                raise VeilError(f"{a}: a spoken need is one short word, like who or when (\"{k}\" isn't)")
            if v not in NEED_RULES:
                raise VeilError(f"{a}: {k} is required, optional or default")
            needs[k] = v
        was = str(r.get("was") or "").strip().lower() or None
        clean.append((a, was, api_, words, needs))

    def write(doc):
        from ruamel.yaml.comments import CommentedMap
        acts = doc.get("actions")
        if not isinstance(acts, dict) or not acts:
            acts = CommentedMap()
            doc["actions"] = acts
        old = {k: acts[k] for k in list(acts.keys())}
        notes = dict(getattr(acts, "ca", None).items) if hasattr(acts, "ca") else {}
        for k in list(acts.keys()):
            del acts[k]
        for a, was, api_, words, needs in clean:
            node = old.get(was or a)
            if not isinstance(node, dict):
                node = CommentedMap()
                node["api"] = api_
                node["learn_from"] = CommentedMap()
            node["api"] = api_
            w = config.flow_list(words)
            node["words"] = w
            if "objects" not in node:
                o = config.flow_list()
                node["objects"] = o
            n = CommentedMap(needs)
            n.fa.set_flow_style()
            node["needs"] = n
            acts[a] = node
            if (was or a) in notes:
                acts.ca.items[a] = notes[was or a]
    config.check_stamp(path, "actions", b.get("stamp"))
    config.edit_yaml(path, write, width=4096)
    audit(request, "voice map saved", target=name, detail=", ".join(a for a, *_ in clean))
    restart_note(f"{name}: voice map")
    return {"saved": [a for a, *_ in clean], "stamp": config.stamp(path, "actions")}


def clean_step(i, x):
    """One step from the page as it's saved: {call: command} or {step: {its parameters}}, or a VeilError."""
    kind = str((x or {}).get("kind") or "")
    if kind == "call":
        c = " ".join(str(x.get("command") or "").split())
        return {"call": (c.split(" ", 1)[0].upper() + " " + c.split(" ", 1)[1]) if " " in c else c}
    if kind not in rulebook.STEPS:
        raise VeilError(f"step {i}: pick what it does")
    out = {}
    for p in rulebook.STEPS[kind]["params"]:
        v = x.get(p["name"])
        if v in (None, "", [], {}):
            continue
        k = p["kind"]
        try:
            if k == "number":
                v = float(v)
                v = int(v) if v.is_integer() else v
            elif k == "yesno":
                v = bool(v)
            elif k == "words":
                v = [" ".join(str(w).lower().split()) for w in (v if isinstance(v, list) else str(v).split(",")) if str(w).strip()]
            elif k == "lines":
                v = [" ".join(str(w).split()) for w in (v if isinstance(v, list) else [v]) if str(w).strip()]
            elif k == "fields":
                v = {str(a).strip(): str(b).strip() for a, b in dict(v).items() if str(a).strip()}
            elif k == "choice" and v not in p["choices"]:
                raise ValueError
            else:
                v = " ".join(str(v).split())
        except (TypeError, ValueError):
            raise VeilError(f"step {i}: {p['name']} isn't right ({p['about']})")
        if v not in ([], {}):
            out[p["name"]] = v
    return {kind: out}


def names_taken(skip_app=None, skip_fleas=False):
    """{name: where} for every voice map action, user rule and brain flea, so no two share a name
    (skip_app: the app whose rules are being saved; skip_fleas: the fleas are being saved)."""
    out = {}
    for f in sorted(os.listdir(config.path("connectors"))):
        if not f.endswith(".yaml"):
            continue
        app_name = f[:-5]
        hand = config.load_yaml(config.path("connectors", f))
        for a in hand.get("actions") or {}:
            out.setdefault(str(a), f"an action on {app_name}'s Voice map")
        if app_name != skip_app:
            for r in hand.get("rules") or {}:
                out.setdefault(str(r), f"a user rule of {app_name}")
    if not skip_fleas:
        for n in (fleas_mod.load().get("fleas") or {}):
            out.setdefault(str(n), "a brain flea")
    return out


def clean_rules(rows, known, taken):
    """[(name, rule)] from the page's rows ({name, words, objects, steps: [{kind, ...}]}), each checked;
    or a VeilError saying what's wrong. taken: names used elsewhere ({name: where})."""
    if not isinstance(rows, list):
        raise VeilError("rules is a list")
    clean, seen = [], set()
    for r in rows:
        n = str((r or {}).get("name") or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", n):
            raise VeilError(f"A name is one short word: small letters, digits and _ (\"{n}\" isn't)")
        if n in seen or n in taken:
            raise VeilError(f"{n} is already " + ("used above" if n in seen else taken[n]) + ": each must be its own name")
        seen.add(n)
        words = [" ".join(str(w).lower().split()) for w in (r.get("words") or []) if str(w).strip()]
        if not words:
            raise VeilError(f"{n}: give it the words that pick it")
        objects = [" ".join(str(o).lower().split()) for o in (r.get("objects") or []) if str(o).strip()]
        rule = {"words": words, "objects": objects, "steps": [clean_step(i, x) for i, x in enumerate(r.get("steps") or [], 1)]}
        wrong = rulebook.check(rule, known)
        if wrong:
            raise VeilError(f"{n}: {wrong}")
        clean.append((n, rule))
    return clean


def rules_node(clean, keep=None):
    """The rules as YAML for edit_yaml: steps one to a line. keep: {name: {key: value}} carried over
    from what was saved (a flea's title, system)."""
    from ruamel.yaml.comments import CommentedMap
    node = CommentedMap()
    for n, rule in clean:
        r = CommentedMap()
        for k, v in ((keep or {}).get(n) or {}).items():
            r[k] = v
        r["words"] = config.flow_list(rule["words"])
        if rule["objects"]:
            r["objects"] = config.flow_list(rule["objects"])
        steps = []
        for st in rule["steps"]:
            k, v = next(iter(st.items()))
            if isinstance(v, dict):
                m = CommentedMap()
                for a, b2 in v.items():
                    m[a] = config.flow_list(b2) if isinstance(b2, list) else b2
                m.fa.set_flow_style()
                v = m
            steps.append(CommentedMap([(k, v)]))
        r["steps"] = steps
        node[n] = r
    return node


def rules_rows(rules, broken=None):
    """Saved rules as the page edits them: each step's kind and parameters, and what's wrong with it."""
    return [{"name": n, "words": (r or {}).get("words") or [], "objects": (r or {}).get("objects") or [],
             "title": (r or {}).get("title") or "", "system": bool((r or {}).get("system")),
             "problem": (broken or {}).get(n) or rulebook.check(r or {}, None),
             "steps": [dict(rulebook.kind_of(x)[1], kind=rulebook.kind_of(x)[0]) for x in (r or {}).get("steps") or []]}
            for n, r in (rules or {}).items()]


@app.put("/api/integrations/{name}/rules")
async def integration_rules(request: Request, name: str):
    """Save the app's user rules from its User rules tab: {rules: [{name, words, objects, steps: [{kind, ...}]}]},
    kept in connectors/<name>.yaml (rules:). One left out is taken out. Used at once (no restart)."""
    need(request, "administrator")
    path = connector_file(name)
    if not path:
        raise VeilError(f"{name} has no voice map (connectors/{name}.yaml)", 404)
    b = await body_of(request)
    saved = openapi.load(commands_file(name))
    known = {c["api"].upper() for c in openapi.expanded((saved or {}).get("commands"))} if saved else None
    clean = clean_rules(b.get("rules"), known, names_taken(skip_app=name))

    def write(doc):
        if clean:
            doc["rules"] = rules_node(clean)
        else:
            doc.pop("rules", None)
    config.check_stamp(path, "rules", b.get("stamp"))
    config.edit_yaml(path, write, width=4096)
    audit(request, "user rules saved", target=name, detail=", ".join(n for n, _ in clean))
    return {"saved": [n for n, _ in clean], "stamp": config.stamp(path, "rules")}


# ---------- brain fleas: the household's small true facts (learn/fleas.yaml; veil/fleas.py) ----------

# ---------- the people grid: one row per person, a column per attached app (veil/people.py) ----------

def people_columns(s):
    """The integrations that can be a column: every service, Oread and Home Assistant."""
    out = [{"id": n, "title": (v or {}).get("title") or n.replace("_", " ").capitalize()}
           for n, v in (s.get("services") or {}).items()]
    return out + [{"id": "oread", "title": "Oread"}, {"id": "home_assistant", "title": "Home Assistant"}]


@app.get("/api/people")
def people_get(request: Request):
    """The grid as the People page edits it, and the integrations that can be added as columns."""
    need(request, "administrator")
    s = config.settings()
    return dict(people_mod.grid(), columns=people_columns(s))


@app.put("/api/people")
async def people_save(request: Request):
    """Save the grid from the page: {apps: [columns], rows: [{wepwawet, called, <app>: [names]}]}.
    A name in two rows would make two people one, so it's refused. Used at once."""
    need(request, "administrator")
    b = await body_of(request)
    known = {c["id"] for c in people_columns(config.settings())}
    apps_ = [str(a) for a in (b.get("apps") or []) if str(a) in known]
    rows, seen = [], {}
    for r in b.get("rows") or []:
        r = r or {}
        row = {"wepwawet": " ".join(str(r.get("wepwawet") or "").split()),
               "called": [" ".join(str(n).split()) for n in r.get("called") or [] if str(n).strip()]}
        row.update({a: [" ".join(str(n).split()) for n in r.get(a) or [] if str(n).strip()] for a in apps_})
        every = people_mod.row_names(row)
        if not every:
            continue                          # an empty row is dropped
        for n in every:
            if n in seen:
                raise VeilError(f"'{n}' is in two rows ({seen[n]} and {row['wepwawet'] or 'a row'}): one name is one person")
            seen[n] = row["wepwawet"] or "a row"
        rows.append(row)

    def write(doc):
        from ruamel.yaml.comments import CommentedMap
        out = [CommentedMap([("wepwawet", r["wepwawet"]), ("called", config.flow_list(r["called"]))]
                            + [(a, config.flow_list(r[a])) for a in apps_]) for r in rows]
        for m in out:
            m.fa.set_flow_style()
        doc["people"] = CommentedMap([("apps", config.flow_list(apps_)), ("rows", out)])
    config.edit_yaml(config.SETTINGS_FILE, write)
    audit(request, "people grid saved", detail=f"{len(rows)} rows; columns {', '.join(apps_)}")
    return dict(people_mod.grid(), columns=people_columns(config.settings()))


@app.get("/api/fleas")
def fleas_list(request: Request):
    """The fleas as the Brain fleas page edits them, the steps they can use, the router's own commands
    for fleas, its settings (match_at, changers) and the voices that can be named as changers."""
    need(request, "reviewer")
    s = config.settings()
    book = fleas_mod.Fleas().fresh()
    doc = book.doc
    return {"rules": rules_rows(doc.get("fleas") or {}, book.broken), "rule_steps": rulebook.STEPS,
            "commands": list(fleas_mod.COMMANDS.values()), "file": os.path.relpath(fleas_mod.FILE, config.path()),
            "match_at": doc.get("match_at", 0.8), "changers": doc.get("changers") or [],
            "never_count": doc.get("never_count") or [], "voices": people_map.voices(s),
            "stamp": config.stamp(fleas_mod.FILE, "fleas")}


@app.put("/api/fleas")
async def fleas_save(request: Request):
    """Save the fleas from the page: {rules: [...]}, the same rows as an app's User rules. Used at once."""
    need(request, "administrator")
    b = await body_of(request)
    clean = clean_rules(b.get("rules"), set(fleas_mod.COMMANDS), names_taken(skip_fleas=True))
    old = fleas_mod.load().get("fleas") or {}
    keep = {n: {k: old[n][k] for k in ("title", "system") if k in (old.get(n) or {})} for n, _ in clean if n in old}
    for r in b.get("rules") or []:          # a title typed on the page
        n = str((r or {}).get("name") or "").strip().lower()
        if str(r.get("title") or "").strip():
            keep.setdefault(n, {})["title"] = " ".join(str(r["title"]).split())

    def write(doc):
        doc["fleas"] = rules_node(clean, keep)
    config.check_stamp(fleas_mod.FILE, "fleas", b.get("stamp"))
    config.edit_yaml(fleas_mod.FILE, write, width=4096)
    config.hand_back(fleas_mod.FILE)
    audit(request, "brain fleas saved", target="fleas", detail=", ".join(n for n, _ in clean))
    return {"saved": [n for n, _ in clean], "stamp": config.stamp(fleas_mod.FILE, "fleas")}


@app.patch("/api/fleas/settings")
async def fleas_settings(request: Request):
    """{match_at: 0..1, changers: [voice names]}: how closely a sentence must fit, and who may change fleas by voice."""
    need(request, "administrator")
    b = await body_of(request)
    m = b.get("match_at")
    if m is not None and (isinstance(m, bool) or not isinstance(m, (int, float)) or not 0 < m <= 1):
        raise VeilError("match at is a share from 0 to 1 (like 0.75)")
    voices = {v.lower(): v for v in people_map.voices(config.settings())}
    who = b.get("changers")
    if who is not None and (not isinstance(who, list) or any(str(x).lower() not in voices for x in who)):
        raise VeilError("changers are voices the voice ID knows (Name Sparkle)")

    def write(doc):
        if m is not None:
            doc["match_at"] = m
        if who is not None:
            doc["changers"] = config.flow_list([voices[str(x).lower()] for x in who])
    config.edit_yaml(fleas_mod.FILE, write, width=4096)
    config.hand_back(fleas_mod.FILE)
    audit(request, "brain flea settings", target="fleas", detail=str(b))
    return {"match_at": m, "changers": who}


# word lists every app's matching reads (veil/match.py), shown on every app's Clean-up words tab even
# before its voice map has them: {key: (empty value, its note)}
GENERIC_LANGUAGE = {
    "never_in_names": ([], "Words that never count toward matching one of its things' names (the, of, feast, day): "
                           "dropped on both sides, so \"St. Joseph's Day\" is Saint Joseph."),
    "alike": ({}, "Same meaning, matched as one on both sides: a phrase = what it means (our lady = mary, "
                  "blessed virgin mary = mary, all saints day = all saints)."),
    "nearby": ([], "Words that never decide alone (mary, joseph): a thing sharing only them isn't a fit; said "
                   "alone, she asks which, and outside this app's context they aren't this app's."),
    "not_said": ([], "Words or phrases in the app's own text she leaves out when she reads it ((pictured), (depicted): "
                     "Wikipedia's notes about its pictures)."),
}


@app.put("/api/integrations/{name}/language")
async def integration_language(request: Request, name: str):
    """One list of an app's clean-up words ({key, value}: a list of words, or a word -> words
    map), saved to connectors/<name>.yaml with its comments kept. Used after a restart."""
    need(request, "administrator")
    path = connector_file(name)
    if not path:
        raise VeilError(f"{name} has no connector file", 404)
    b = await body_of(request)
    key, value = str(b.get("key") or ""), b.get("value")
    hand = config.load_yaml(path)
    if key not in (hand.get("language") or {}) and key in GENERIC_LANGUAGE:
        hand.setdefault("language", {})
        hand["language"] = dict(hand["language"] or {}, **{key: GENERIC_LANGUAGE[key][0]})
    if key not in (hand.get("language") or {}):
        raise VeilError(f"{name} has no word list called {key}")
    if isinstance(value, list):
        value = [" ".join(str(w).split())[:80] for w in value if str(w).strip()]
        if len(value) > 2000:
            raise VeilError("That's too many words for one list")
    elif isinstance(value, dict):
        value = {" ".join(str(k).split())[:80]: " ".join(str(v).split())[:120] for k, v in value.items() if str(k).strip()}
    else:
        raise VeilError("A word list is a list of words, or words matched to words")
    if isinstance(hand["language"][key], list) != isinstance(value, list):
        raise VeilError(f"{key} keeps its shape (a list, or words matched to words)")
    config.edit_yaml(path, lambda doc: config.set_in(doc, ["language", key], value), width=4096)
    audit(request, "clean-up words changed", target=f"{name}.{key}", detail=json.dumps(value)[:200])
    restart_note(f"{name}: clean-up words")
    return {"saved": key, "value": value}


@app.patch("/api/integrations/{name}/offers")
async def integration_offer(request: Request, name: str):
    """Switch one of what an app offers on or off, and pick its way: {key, on, way}. Offers come
    from its x-wepwawet section (the Wepwawet standard)."""
    need(request, "administrator")
    s = config.settings()
    where, nd = apps.node(s, name)
    if not where:
        raise VeilError(f"No app named {name}", 404)
    b = await body_of(request)
    key = str(b.get("key") or "")
    offer = (((apps.wepwawet(name) or {}).get("offers")) or {}).get(key)
    if offer is None:
        raise VeilError(f"{name} doesn't offer {key} (its spec's x-wepwawet section)")
    on, way = bool(b.get("on")), b.get("way")
    ways = offer.get("ways") or {}
    if ways and way not in ways:
        raise VeilError(f"{key} comes {', '.join(ways)}")
    bind = apps.OFFER_SETTINGS.get(key) or {}

    def write(doc):
        if "on" in bind:
            config.set_in(doc, [where, name, bind["on"]], on)
        else:
            config.set_in(doc, [where, name, "offers", key, "on"], on)
        if ways:
            if "way" in bind:
                config.set_in(doc, [where, name, bind["way"]], apps.way_to_setting(key, way))
            else:
                config.set_in(doc, [where, name, "offers", key, "way"], way)
    config.edit_yaml(config.SETTINGS_FILE, write)
    audit(request, "app offer set", target=f"{name}.{key}", detail=f"{'on' if on else 'off'} {way or ''}")
    restart_note(f"{name}: {key}")
    return {"key": key, "on": on, "way": way}


@app.get("/api/integrations/{name}/choices")
async def integration_choices(request: Request, name: str, app_: str = Query("", alias="app"), api_: str = Query("", alias="api"),
                              field_: str = Query("", alias="field")):
    """The values an option can take from an app's answer: app's command api, each item's field."""
    need(request, "viewer")
    conn = router().CONNECTORS.get(app_)
    call = getattr(conn, "api", None)
    if not call:
        raise VeilError(f"{app_ or 'That app'} isn't running, so it can't be asked", 409)
    method, _, path = api_.partition(" ")
    if method.upper() != "GET" or not path:
        raise VeilError("The command is a GET one")
    data = await call("GET", path)
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), [])
    vals = []
    for item in data or []:
        v = item.get(field_) if isinstance(item, dict) else None
        if v is not None and str(v) not in vals:
            vals.append(str(v))
    return {"values": vals}


@app.patch("/api/integrations/{name}/options")
async def integration_option(request: Request, name: str):
    """One of a service's options ({key, value}), the same kind as before (a number stays a
    number), saved to settings.yaml services: <name>: options:. Used after a restart."""
    need(request, "administrator")
    svc = (config.settings().get("services") or {}).get(name)
    if svc is None:
        raise VeilError(f"No service named {name}", 404)
    b = await body_of(request)
    key, value = str(b.get("key") or ""), b.get("value")
    opts = svc.get("options") or {}
    # a new option is one of its commands' parameters (calendar_id): what the router fills them with
    params = {str(p).partition(": ")[2] for c in (openapi.load(commands_file(name)) or {}).get("commands") or []
              for p in c.get("params") or [] if not str(p).endswith(": id")}
    params |= {f"{p}_as" for p in params}          # how a date part is written (month_as: name)
    if key not in opts and not (key in params and "from" not in b):
        raise VeilError(f"{name} has no option called {key}"
                        + (f" (a new one is one of its commands' parameters: {', '.join(sorted(params))})" if params else ""))
    if "from" in b:              # where the option's choices come from: an app's answer, or typed (null)
        src = b.get("from")
        if src:
            src = {"app": str(src.get("app") or ""), "api": " ".join(str(src.get("api") or "").split()),
                   "field": str(src.get("field") or "")}
            cmd = next((c for c in (openapi.load(commands_file(src["app"])) or {}).get("commands") or []
                        if c["api"] == src["api"]), None)
            if not cmd or not src["api"].upper().startswith("GET "):
                raise VeilError("Pick an app and one of its commands that lists things (its Commands tab)")
            if src["field"] not in (cmd.get("returns") or [src["field"]]) or not src["field"]:
                raise VeilError(f"The field is one of what {src['api']} answers with")

        def write_from(doc):
            from ruamel.yaml.comments import CommentedMap
            if src:
                n = CommentedMap(src)
                n.fa.set_flow_style()
                config.set_in(doc, ["services", name, "options_from", key], n)
            else:
                node = ((doc.get("services") or {}).get(name) or {}).get("options_from")
                if isinstance(node, dict) and key in node:
                    del node[key]
                    if not node:
                        del doc["services"][name]["options_from"]
        config.edit_yaml(config.SETTINGS_FILE, write_from)
        audit(request, "option source changed", target=f"{name}.{key}", detail=json.dumps(src)[:200])
        if "value" not in b:
            return {"saved": key, "from": src}
    old = opts[key] if key in opts else ""      # a new one: a word or a number, as given
    if key not in opts and isinstance(value, (int, float)) and not isinstance(value, bool):
        old = 0
    if isinstance(old, bool):
        ok = isinstance(value, bool)
    elif isinstance(old, (int, float)):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    else:
        ok = isinstance(value, str) and len(value) <= 200
    if not ok:
        raise VeilError(f"{key} keeps its kind of value ({type(old).__name__})")
    config.edit_yaml(config.SETTINGS_FILE, lambda doc: config.set_in(doc, ["services", name, "options", key], value))
    audit(request, "option changed", target=f"{name}.{key}", detail=json.dumps(value)[:200])
    restart_note(f"{name}: options")
    return {"saved": key, "value": value}


@app.patch("/api/integrations/{name}")
async def integration_set(request: Request, name: str):
    """Switch one on or off, or change its address and knobs."""
    need(request, "administrator")
    b = await body_of(request)
    s = config.settings()
    if name in (s.get("integrations") or {}):
        allowed = {"enabled": bool, "source": str, "url": str, "token": str, "verify_tls": (bool, str),
                   "timeout": (int, float), "max_age_seconds": (int, float), "min_word_overlap": (int, float),
                   "devices": dict, "satellites": dict, "wyoming": dict, "spec": str}
        if name == "litellm":            # everything about talking to LiteLLM (Oct 15: off Settings)
            allowed = {"fallback_model": str, "timeout": (int, float), "key": str, "model_name": str, "spec": str}
        base = ["integrations", name]
    elif name in (s.get("services") or {}):
        allowed = {"enabled": bool, "url": str, "spec": str, "timeout": (int, float), "secret": str, "me": str, "title": str,
                   "cache_refresh_seconds": (int, float), "spec_prefix": str, "test_said": str, "spoken_name": str,
                   "pages_max": int, "send_only_accepted": bool}
        base = ["services", name]
    else:
        raise VeilError(f"No integration named {name}", 404)
    sets = []
    for k, v in b.items():
        if k not in allowed:
            raise VeilError(f"{k} can't be changed here")
        kind = allowed[k]
        ok = isinstance(v, kind)
        if kind == (int, float) and isinstance(v, bool):
            ok = False                     # true isn't a number here
        if not ok:
            raise VeilError(f"{k} has the wrong kind of value")
        if k == "url" and v and not re.fullmatch(r"https?://[A-Za-z0-9.\-:\[\]_/]+", v):
            raise VeilError("url is an http:// or https:// address")
        if k in ("fallback_model", "model_name", "key") and not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,80}", v):
            raise VeilError(f"{k} is a name: letters, digits, and . _ : / -")
        if k == "pages_max" and not 1 <= v <= 20:
            raise VeilError("pages_max is how many pages it reads, from 1 to 20")
        if k == "spec_prefix" and v and not re.fullmatch(r"(/[A-Za-z0-9_.{}-]+)+", v):
            raise VeilError("spec_prefix is the start of its spec's paths, like /{domain}/v1")
        if k in ("timeout", "cache_refresh_seconds") and not 1 <= v <= 3600:
            raise VeilError(f"{k} is seconds, from 1 to 3600")
        if k == "source" and v not in ("wyoming", "oread", "home_assistant"):
            raise VeilError("source is wyoming, oread or home_assistant")
        if k == "wyoming":                 # key by key, so the comments on the others stay
            sets.extend((base + ["wyoming", wk], wv) for wk, wv in wyoming_checked(v).items())
            continue
        if k == "devices" and not all(re.fullmatch(r"[a-z0-9_-]{1,40}", str(x)) for kv in v.items() for x in kv):
            raise VeilError("devices maps assistant names to Oread device names")
        if k == "satellites" and not all(re.fullmatch(r"[A-Za-z0-9_. -]{1,80}", str(x)) for kv in v.items() for x in kv):
            raise VeilError("satellites maps a Home Assistant device id, satellite or name to an assistant")
        if k == "me":
            if v not in ("default", "speaker"):
                raise VeilError("me is default or speaker")
            sets.append((base + ["options", "me"], v))
            continue
        sets.append((base + [k], v))

    def change(doc):
        for keys, v in sets:
            config.set_in(doc, keys, v)
    config.edit_yaml(config.SETTINGS_FILE, change)
    audit(request, "integration changed", target=name, detail={k: v for k, v in b.items()})
    restart_note(f"integration: {name}")
    return {"saved": name}


def wyoming_checked(w):
    """integrations: oread: wyoming: as the page sent it, checked; VeilError if it isn't right."""
    out = {}
    for k, v in w.items():
        if k == "host":
            if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]{0,253}", v):
                raise VeilError("wyoming host is Oread's address (a name or IP, no http://)")
            out[k] = v
        elif k == "connect_timeout":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 < v <= 30:
                raise VeilError("wyoming connect_timeout is seconds, above 0 and at most 30")
            out[k] = v
        elif k == "devices":
            if not isinstance(v, dict):
                raise VeilError("wyoming devices maps assistants to their ports")
            devices, seen = {}, set()
            for a, ports in v.items():
                if not re.fullmatch(r"[a-z0-9_-]{1,40}", str(a)) or not isinstance(ports, dict):
                    raise VeilError("wyoming devices: assistant: {listen: port, oread: port}")
                try:
                    listen, oread = int(ports.get("listen")), int(ports.get("oread"))
                except (TypeError, ValueError):
                    raise VeilError(f"{a} needs a listen port and an Oread port")
                if not (1024 <= listen <= 65535 and 1 <= oread <= 65535):
                    raise VeilError(f"{a}: ports are numbers up to 65535 (listen from 1024)")
                if listen in seen or listen in (8770, 8771):
                    raise VeilError(f"{a}: listen port {listen} is already taken")
                seen.add(listen)
                devices[a] = {"listen": listen, "oread": oread}
            out[k] = devices
        else:
            raise VeilError(f"wyoming {k} can't be changed here")
    return out


@app.post("/api/integrations/{name}/test")
async def integration_test(request: Request, name: str):
    need(request, "administrator")
    s = config.settings()
    if name == "oread":
        o = dict(config.section(config.section(s, "integrations"), "oread"))
        return await speakers.test({**s, "integrations": {**s.get("integrations", {}), "oread": o}})
    if name == "home_assistant":
        ha = dict(config.section(config.section(s, "integrations"), "home_assistant"))
        url = (ha.get("url") or "").rstrip("/")
        if not url:
            return {"ok": False, "detail": "Home Assistant's address isn't set"}
        token = config.secret(ha.get("token") or "HA_TOKEN")
        try:
            async with access.client(5) as c:
                resp = await c.get(url + "/api/", headers={"Authorization": f"Bearer {token}"})
            return {"ok": resp.status_code < 300, "detail": f"Home Assistant answered {resp.status_code}"
                    + (" (the token was refused)" if resp.status_code == 401 else "") + ("" if token else " (no token set)")}
        except Exception as e:
            return {"ok": False, "detail": f"Couldn't reach Home Assistant: {e}"}
    if name == "litellm":
        r = router()
        try:
            async with access.client(5) as c:
                resp = await c.get(r.LITELLM_URL + "/models", headers={"Authorization": "Bearer " + r.LITELLM_KEY})
            ids = [m.get("id") for m in (resp.json().get("data") or [])] if resp.status_code < 300 else []
            return {"ok": resp.status_code < 300, "detail": f"LiteLLM answered {resp.status_code}; models: {', '.join(ids)}"}
        except Exception as e:
            return {"ok": False, "detail": f"Couldn't reach LiteLLM: {e}"}
    svc = (s.get("services") or {}).get(name)
    if not svc:
        raise VeilError(f"No integration named {name}", 404)
    try:
        async with access.client(float(svc.get("timeout", 8))) as c:
            if svc.get("kind") == "contract" and phases.on("dump14") and not svc.get("test_said"):
                # no test question of its own (its card): its spec is asked for, which says it's there
                if not svc.get("spec"):
                    return {"ok": False, "detail": f"{name} has no test question and no spec to ask for (its card)"}
                resp = await c.get(svc["spec"])
                return {"ok": resp.status_code < 300, "detail": f"its spec answered {resp.status_code} (set a test question on its card to ask it one)"}
            if svc.get("kind") == "contract":
                resp = await c.get(svc["url"], params={"text": svc.get("test_said") or "what's the weather today"})
                d = resp.json() if resp.status_code < 300 else {}
                return {"ok": resp.status_code < 300 and bool(d.get("status")),
                        "detail": f"answered {resp.status_code}: {d.get('status')}: {d.get('speech', '')[:160]}"}
        # an app the router runs: asked its list of things through its own connector (its address, its key)
        conn = router().APPS.get(name)
        if not conn or not conn.items_command():
            return {"ok": False, "detail": f"{name} isn't running here (switched off, or it didn't load: see the log)"}
        found = await conn.api("GET", conn.items_command())
        n = len(found) if isinstance(found, list) else 1
        return {"ok": True, "detail": f"{name} answered GET {conn.items_command()}: {n} {conn.noun()}{'' if n == 1 else 's'}"
                + ("" if conn.token else " (no token set)")}
    except Exception as e:
        return {"ok": False, "detail": f"Couldn't reach {name}: {e}"}


def list_choices(name):
    """An app's commands that list things (GET), with the fields each answers with."""
    saved = openapi.load(commands_file(name)) or {}
    return [{"api": c["api"], "summary": c.get("summary") or "", "returns": c.get("returns") or []}
            for c in saved.get("commands") or [] if c["api"].upper().startswith("GET ")]


def list_users(name, word):
    """The voice map's fields filled from this list (connectors/<name>.yaml: fields: list:)."""
    path = connector_file(name)
    out = []
    for a, v in ((config.load_yaml(path) if path else {}).get("actions") or {}).items():
        for f, spec in ((v or {}).get("fields") or {}).items():
            if (spec or {}).get("list") == word:
                out.append(f"{a}: {f}")
    return out


def declared_lists(name):
    """The lists an app's x-wepwawet section names (a compliant app fills in its own cards)."""
    return ((apps.wepwawet(name) or {}).get("lists")) or {}


def app_caller(s, name):
    """How to ask an app one of its commands: its running connector's own call (it knows the app's
    quirks), else the router's call the app's spec describes (veil/apps.py), else None."""
    conn = router().CONNECTORS.get(name)
    call = getattr(conn, "api", None)
    if call:
        return call
    if apps.saved(name).get("base"):
        return lambda method, path, **kw: apps.call(s, name, method, path, **kw)
    return None


@app.get("/api/integrations/{name}/lists")
def integration_lists(request: Request, name: str):
    """An app's list cards (the Defaults tab): their words, and what the page needs to draw them."""
    need(request, "viewer")
    s = config.settings()
    where, svc = apps.node(s, name)
    if where is None:
        raise VeilError(f"No app named {name}", 404)
    card = lists.people_card(svc, declared_lists(name))
    house = people_map.household(s, card)
    household = [{"key": v, "say_as": v, "names": sorted(n for n in ns if n != v.lower())} for v, ns in house.items()]
    return {"name": name, "words": list(lists.cards(svc, declared_lists(name))), "choices": list_choices(name), "household": household,
            "house_default": card.get("default")}


@app.get("/api/integrations/{name}/lists/{word}")
async def integration_list(request: Request, name: str, word: str, source: str = "", id: str = "", label: str = ""):
    """One list card: where it comes from, its items as the app lists them now, its default, and
    for a list of people, who each is in the house (saved, or matched by name until saved).
    source, id and label try other choices before saving."""
    need(request, "viewer")
    s = config.settings()
    where, svc = apps.node(s, name)
    if where is None:
        raise VeilError(f"No app named {name}", 404)
    conf = dict(lists.card(svc, word, declared_lists(name)))
    if source:
        conf.update({"from": source, "id": id, "name": label})
    house = people_map.household(s, conf)
    out = {"word": word, "card": {k: v for k, v in conf.items() if k != "map"}, "exists": word in lists.cards(svc),
           "declared": bool(conf.get("declared")),
           "used_by": list_users(name, word), "saved_map": isinstance(conf.get("map"), dict), "items": [], "reached": False}
    call = app_caller(s, name)
    if not conf.get("from"):
        out["detail"] = "Pick the command that lists them."
    elif not call:
        out["detail"] = f"{apps.info(s, name)['title']} can't be asked yet (switch it on and restart, or read its spec), so its {word} can't be listed."
    else:
        try:
            found = await lists.items(call, conf)
            m = people_map.mapping(found, conf, house) if conf.get("house") == "people" else {}
            out["items"] = [{"id": str(i), "name": n, "household": m.get(str(i), ""),
                             "suggested": conf.get("house") == "people" and not out["saved_map"] and str(i) in m}
                            for i, n in found]
            out["reached"] = True
            if not found:
                out["detail"] = "It answered, but with nothing in those fields: check the command and the two fields."
        except Exception as e:
            out["detail"] = f"Couldn't list them: {str(e)[:200]}"
    return out


@app.put("/api/integrations/{name}/lists/{word}")
async def integration_list_set(request: Request, name: str, word: str):
    """Save a list card: {from, id, name, house: "people" or "", default, me (people), map (people)}."""
    need(request, "administrator")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", word or ""):
        raise VeilError("A list's word is one short word, like people or project")
    b = await body_of(request)
    s = config.settings()
    where, svc = apps.node(s, name)
    if where is None:
        raise VeilError(f"No app named {name}", 404)
    gets = {c["api"]: c for c in list_choices(name)}
    src = " ".join(str(b.get("from") or "").split())
    if src not in gets:
        raise VeilError("Pick one of its commands that lists things (Commands: read its spec first)")
    fields = gets[src].get("returns") or []
    for k in ("id", "name"):
        v = str(b.get(k) or "").strip()
        if not v or (fields and v not in fields):
            raise VeilError(f"An item's {k} is one of the fields {src} answers with")
    house = str(b.get("house") or "")
    if house not in ("", "people"):
        raise VeilError("Its items are people in the house, or nothing in the house")
    keys = set(people_map.household(s, lists.people_card(svc))) | {str(v) for v in (b.get("names") or {})}
    entry = {"from": src, "id": str(b["id"]).strip(), "name": str(b["name"]).strip()}
    if house:
        entry["house"] = house
    skip = {}                    # kinds of things kept out of the list: {field: value} (is_vigil_mass: true)
    for k, v in (b.get("skip") or {}).items():
        k = str(k).strip()
        if fields and k not in fields:
            raise VeilError(f"A skip's field is one of the fields {src} answers with ({k} isn't)")
        if not isinstance(v, (str, int, float, bool)) or v is None:
            raise VeilError(f"A skip is a field and one value (true, a word or a number) ({k})")
        skip[k] = v
    if skip:
        entry["skip"] = skip
    w = b.get("weight") or {}            # how much each matters: {field, higher, from, words} ("When to ask", 4)
    if w.get("field"):
        for k in ("field", "words"):
            if w.get(k) and fields and w[k] not in fields:
                raise VeilError(f"The weight's {k} is one of the fields {src} answers with ({w[k]} isn't)")
        if w.get("from") is not None and (isinstance(w["from"], bool) or not isinstance(w["from"], (int, float))):
            raise VeilError("The weight's from is a number (worth it from here up)")
        entry["weight"] = {"field": str(w["field"]), "higher": bool(w.get("higher", True)),
                           **({"from": w["from"]} if w.get("from") is not None else {}),
                           **({"words": str(w["words"])} if w.get("words") else {})}
    dfd = b.get("defined") or {}         # the app's list of what should be (the collision hook, dump18)
    if dfd.get("from"):
        dsrc = " ".join(str(dfd["from"]).split())
        if dsrc not in gets:
            raise VeilError("What should be is one of its commands that lists things")
        dfields = gets[dsrc].get("returns") or []
        for k in ("month", "day"):
            if dfields and str(dfd.get(k) or k) not in dfields:
                raise VeilError(f"Its usual {k} is one of the fields {dsrc} answers with ({dfd.get(k) or k} isn't)")
        entry["defined"] = {"from": dsrc, "month": str(dfd.get("month") or "month"), "day": str(dfd.get("day") or "day")}
    default = str(b.get("default") or "").strip()
    if default:
        if house == "people" and default not in keys:
            raise VeilError(f"The default person is one of the voices (Name Sparkle); {default} isn't")
        entry["default"] = default
    m = {}
    if house == "people":
        me = str(b.get("me") or "default")
        if me not in ("default", "speaker"):
            raise VeilError("me is default (the default person) or speaker (whoever Oread is sure spoke)")
        entry["me"] = me
        for pid, key in (b.get("map") or {}).items():
            key = str(key or "")
            if key and key not in keys:
                raise VeilError(f"{key} isn't one of the voices (Name Sparkle)")
            m[str(pid)] = key
        names = {}
        for v, ns in (b.get("names") or {}).items():
            if str(v) not in keys:
                raise VeilError(f"{v} isn't one of the voices (Name Sparkle)")
            ws = word_list(list(ns or []), f"{v}'s other names")
            if ws:
                names[str(v)] = ws

    def write(doc):
        from ruamel.yaml.comments import CommentedMap
        node = CommentedMap(entry)
        if house == "people":
            node["map"] = CommentedMap(m)
            node["names"] = CommentedMap({v: config.flow_list(ws) for v, ws in names.items()})
        else:
            node.fa.set_flow_style()
        config.set_in(doc, [where, name, "lists", word], node)
        old = (doc.get(where) or {}).get(name) or {}
        if house == "people" and "people" in old:      # the people: entry before list cards
            del old["people"]
    config.edit_yaml(config.SETTINGS_FILE, write)
    audit(request, "app list saved", target=f"{name}.{word}", detail=json.dumps(entry)[:200])
    restart_note(f"{name}: {word} list")
    return {"saved": word, "card": entry}


@app.delete("/api/integrations/{name}/lists/{word}")
def integration_list_delete(request: Request, name: str, word: str):
    need(request, "administrator")
    users = list_users(name, word)
    if users:
        raise VeilError(f"The voice map fills {', '.join(users)} from it: change those first", 409)

    where, _ = apps.node(config.settings(), name)

    def write(doc):
        node = (((doc.get(where or "services") or {}).get(name) or {}).get("lists")) or {}
        if word not in node:
            raise VeilError(f"{name} has no list called {word}", 404)
        del node[word]
    config.edit_yaml(config.SETTINGS_FILE, write)
    audit(request, "app list taken out", target=f"{name}.{word}")
    restart_note(f"{name}: {word} list")
    return {"deleted": word}


# ---------- what the router carries between requests (Settings and Stats) ----------

@app.get("/api/holding")
def holding(request: Request):
    """What the router carries between requests right now (the Settings and Stats pages)."""
    need(request, "viewer")
    return router().holding_now()


# ---------- her sayings: every fixed line she says (phrases/*.yaml), on Persona Flair (Oct 14) ----------
# Each section has an "any" list (everyone) and may have one per personality; she uses her own when
# she has any, else the shared ones. Nothing she says is pinned in a file only. The rules for a line
# come from the section itself, not from code: the {placeholders} it may use are the ones its lines
# use, one every shared line has is needed, and a section whose shared lines are all questions takes
# questions (she asks it and waits), one with none takes none.

PHRASE_DIR = config.path("phrases")
_PH = re.compile(r"{(\w+)}")


def phrase_files():
    try:
        return sorted(f[:-5] for f in os.listdir(PHRASE_DIR) if f.endswith(".yaml"))
    except FileNotFoundError:
        return []


def phrase_rules(sec):
    lines = [str(x) for v in (sec or {}).values() for x in (v or [])]
    shared = [str(x) for x in ((sec or {}).get("any") or [])]
    allowed = set(_PH.findall(" ".join(lines)))
    needed = set.intersection(*[set(_PH.findall(x)) for x in shared]) if shared else set()
    asks = None
    if shared and all(x.rstrip().endswith("?") for x in shared):
        asks = True
    elif shared and not any(x.rstrip().endswith("?") for x in shared):
        asks = False
    return {"allowed": sorted(allowed), "needed": sorted(needed), "question": asks}


@app.get("/api/phrases")
def phrases_get(request: Request):
    """Every file of her sayings: its parts (the file's own headings) and each section with its note,
    the shared lines, each personality's own, and the rules for a new line."""
    need(request, "viewer")
    out = []
    for f in phrase_files():
        file = os.path.join(PHRASE_DIR, f"{f}.yaml")
        doc = config.plain(config.load_yaml(file)) or {}
        notes = settings_comments(file)
        parts = [{"title": p["title"], "sections": [k for k in p["keys"] if isinstance(doc.get(k), dict)]}
                 for p in notes["sections"]]
        sections = {}
        for k, v in doc.items():
            if not isinstance(v, dict):
                continue
            sections[k] = {"note": notes["comments"].get(k, ""),
                           "lines": {who: [str(x) for x in (lines or [])] for who, lines in v.items()},
                           "notes": {who: notes["comments"].get(f"{k}.{who}", "") for who in v},
                           "rules": phrase_rules(v)}
        # the router's own lines are per personality; an app's lines are shared (it doesn't know who's speaking)
        out.append({"file": f, "personal": f == "router", "parts": [p for p in parts if p["sections"]], "sections": sections})
    asking = config.plain((config.load_yaml(config.path("vocab", "answers.yaml")) or {}).get("about_asking") or [])
    return {"files": out, "about_asking": asking}


@app.put("/api/phrases/{file}/{section}/{who}")
async def phrases_set(request: Request, file: str, section: str, who: str):
    """One personality's lines for one section ({lines: [...]}); who: any for everyone. An empty list
    takes her own lines out (she uses the shared ones); the shared list always keeps one line."""
    need(request, "administrator")
    if file not in phrase_files() or not re.fullmatch(r"[a-z0-9_]{1,60}", section):
        raise VeilError("No such sayings", 404)
    if who != "any":
        assistant_ok(who)
        if file != "router":
            raise VeilError("An app's lines are shared by everyone (edit the shared ones)")
    path = os.path.join(PHRASE_DIR, f"{file}.yaml")
    doc = config.plain(config.load_yaml(path)) or {}
    if not isinstance(doc.get(section), dict):
        raise VeilError("No such sayings", 404)
    rules = phrase_rules(doc[section])
    lines, seen = [], set()
    for x in (await body_of(request)).get("lines") or []:
        x = " ".join(str(x or "").split())
        if not x or x.lower() in seen:
            continue
        if len(x) > 300:
            raise VeilError(f'"{x[:30]}...": 300 characters at most')
        used = set(_PH.findall(x))
        if used - set(rules["allowed"]):
            raise VeilError(f'"{x}": {{{", ".join(sorted(used - set(rules["allowed"])))}}} isn\'t filled in here '
                            f'(this one can use {", ".join("{" + a + "}" for a in rules["allowed"]) or "none"})')
        if set(rules["needed"]) - used:
            raise VeilError(f'"{x}": keep {", ".join("{" + n + "}" for n in rules["needed"])} in it (the persona says what goes there)')
        if rules["question"] is True and not x.endswith("?"):
            raise VeilError(f'"{x}": the persona asks this and waits for your answer, so it ends with a question')
        if rules["question"] is False and x.endswith("?"):
            raise VeilError(f'"{x}": not a question here (a question keeps the mic open)')
        seen.add(x.lower())
        lines.append(x)
    if who == "any" and not lines:
        raise VeilError("The shared lines need one at least (everyone falls back on them)")

    def change(d):
        from ruamel.yaml.comments import CommentedSeq
        node = d[section]
        if lines:
            node[who] = CommentedSeq(lines)
        elif who in node:
            del node[who]
    config.edit_yaml(path, change, width=200)
    try:                                   # in use at once: the router's copy, and its shuffled decks
        r = router()
        r.PHRASES[file] = config.load_yaml(path) or {}
        for k in [k for k in r._bags if k[0] == file and k[1] == section]:
            del r._bags[k]
    except Exception as e:
        log.info("  ! sayings not reloaded (%s): restart to use them", e)
        restart_note(f"sayings: {file}")
    audit(request, "sayings saved", target=f"{file}.{section}.{who}", detail=f"{len(lines)} lines")
    return {"file": file, "section": section, "who": who, "lines": lines}


# ---------- words understood: the vocab/ lists on a page (Oct 18) ----------

def vocab_file(name):
    """vocab/<name>.yaml, or None."""
    if not re.fullmatch(r"[a-z0-9_]{1,40}", name or ""):
        return None
    path = config.path("vocab", f"{name}.yaml")
    return path if os.path.exists(path) else None


def vocab_lists(path):
    """A vocab file as the Words understood page shows it: every list of words (a top-level key or
    one level under one) with its comment, editable; everything else (numbers, word: value maps)
    shown as it is, kept in the file."""
    doc = config.load_yaml(path)
    notes = settings_comments(path)["comments"]
    lists, other = [], []
    for k, v in doc.items():
        subs = [([k], v)] if not isinstance(v, dict) else [([k, k2], v2) for k2, v2 in v.items()]
        for keys, val in subs:
            dotted = ".".join(str(x) for x in keys)
            if isinstance(val, list) and all(isinstance(x, str) for x in val):
                lists.append({"path": [str(x) for x in keys], "words": val, "note": notes.get(dotted) or notes.get(str(k), "")})
            else:
                other.append({"path": [str(x) for x in keys], "value": val})
    return {"lists": lists, "other": other}


@app.get("/api/words")
def words_understood(request: Request):
    """Every vocab/ file's word lists: what's understood rather than said (yes and no, fillers,
    dismissals, the learn commands, dates and moods). Each file with its own header note."""
    need(request, "reviewer")
    out = []
    for f in sorted(os.listdir(config.path("vocab"))):
        if not f.endswith(".yaml"):
            continue
        path = config.path("vocab", f)
        head = []
        for line in open(path).read().splitlines():
            if not line.startswith("#"):
                break
            head.append(line.lstrip("#").strip())
        out.append({"file": f[:-5], "note": " ".join(x for x in head[1:] if x), **vocab_lists(path),
                    "stamps": {k: config.stamp(path, k) for k in config.load_yaml(path)}})
    return {"files": out}


@app.put("/api/words/{name}")
async def words_save(request: Request, name: str):
    """{path: [key] or [key, key], words: [...], stamp}: one list of a vocab file, saved with the
    file's comments kept; refused when that section changed since the page was opened. Used after
    a restart (the router reads its words at start)."""
    need(request, "administrator")
    path = vocab_file(name)
    if not path:
        raise VeilError(f"No word file vocab/{name}.yaml", 404)
    b = await body_of(request)
    keys = [str(x) for x in (b.get("path") or [])]
    if not 1 <= len(keys) <= 2:
        raise VeilError("path is one key, or a key and one under it")
    have = vocab_lists(path)["lists"]
    if keys not in [x["path"] for x in have]:
        raise VeilError(f"{'.'.join(keys)} isn't a list of words in vocab/{name}.yaml")
    words = word_list(b.get("words"), ".".join(keys))
    config.check_stamp(path, keys[0], b.get("stamp"))

    def change(doc):
        node = doc if len(keys) == 1 else doc[keys[0]]
        node[keys[-1]] = config.flow_list(words)
    config.edit_yaml(path, change, width=4096)
    restart_note(f"vocab: {name}")
    audit(request, "words saved", target=f"{name}.{'.'.join(keys)}", detail=f"{len(words)} words")
    return {"words": words, "stamp": config.stamp(path, keys[0])}


@app.put("/api/phrases/asking")
async def phrases_asking(request: Request):
    """The words she uses for asking around (vocab/answers.yaml about_asking), so "yes, check with
    the coven" counts as a yes."""
    need(request, "administrator")
    words = word_list((await body_of(request)).get("words") or [], "asking words")

    def change(d):
        seq = config.flow_list(words)
        d["about_asking"] = seq
    config.edit_yaml(config.path("vocab", "answers.yaml"), change)
    restart_note("vocab: asking words")
    audit(request, "asking words saved", detail=words)
    return {"words": words}


# ---------- Name Sparkle: saying people's names (Oct 14) ----------
# The house rule (names_in_replies: on, how sure the voice ID must be, how often, most in a row),
# where the names come from (voice_id_from: an integration with a people list, Oread here), each
# device's own switch and rate (personality/<who>.yaml names:), and what she calls each person the
# voice ID knows (names_in_replies: calls: {their voice ID name: [what she may call them]}).

def voice_id_sources(s):
    """Integrations and apps that can name people: those offering who spoke first, then any with a
    people list. [{name, title, who_spoke, people}]"""
    out = []
    names = [n for n, v in (s.get("integrations") or {}).items() if isinstance(v, dict)] + list(s.get("services") or {})
    for name in names:
        w = apps.wepwawet(name) or {}
        node = apps.node(s, name)[1] or {}
        card = lists.people_card(node, (w.get("lists") or {}))
        who = "who_spoke" in (w.get("offers") or {})
        if who or card:
            try:
                title = apps.info(s, name)["title"]
            except VeilError:
                title = name
            out.append({"name": name, "title": title, "who_spoke": who, "people": bool(card)})
    out.sort(key=lambda x: (not x["who_spoke"], x["title"].lower()))
    return out


async def voice_id_people(s, name):
    """The names the chosen integration knows, from its people list (x-wepwawet lists:), or why not."""
    if not name:
        return [], "Pick where the names come from (Voice ID from)."
    w = apps.wepwawet(name) or {}
    node = apps.node(s, name)[1] or {}
    card = lists.people_card(node, (w.get("lists") or {}))
    if not card:
        return [], f"{name} has no people list (read its spec on Integrations)."
    try:
        got = await lists.items(lambda m, p: apps.call(s, name, m, p), card)
    except Exception as e:
        return [], f"Couldn't ask {name}: {e}"
    seen, out = set(), []
    for _, n in got:
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out, None


def device_names():
    r = router()
    return sorted(set(r.FLAIR.names()) | set(choices("assistants")))


@app.get("/api/sparkle")
async def sparkle_get(request: Request):
    need(request, "viewer")
    s = config.settings()
    n = config.plain(s.get("names_in_replies") or {})
    sources = voice_id_sources(s)
    src = n.get("voice_id_from") or (sources[0]["name"] if sources and sources[0]["who_spoke"] else "")
    calls = n.get("calls") or {}
    devices = []
    for who in device_names():
        try:
            spec = config.plain(config.load_yaml(os.path.join(PERS, f"{who}.yaml")))
        except FileNotFoundError:
            spec = {}
        devices.append({"name": who, "names": spec.get("names") or {}, "has_file": bool(spec)})
    return {"settings": {k: n.get(k) for k in ("labels",)},
            "voice_id_from": src, "saved_from": n.get("voice_id_from"), "sources": sources,
            "people": list(calls), "calls": calls, "devices": devices}


@app.post("/api/sparkle/pull")
async def sparkle_pull(request: Request):
    """Pull the names from the voice ID integration now: anyone not saved yet is added (with no
    names under them yet); saved people stay until you delete them, whether or not it still knows them."""
    need(request, "administrator")
    s = config.settings()
    n = config.plain(s.get("names_in_replies") or {})
    sources = voice_id_sources(s)
    src = n.get("voice_id_from") or (sources[0]["name"] if sources and sources[0]["who_spoke"] else "")
    if not src:
        raise VeilError("Pick where the names come from (Voice ID from) and save first")
    people, why = await voice_id_people(s, src)
    if why:
        raise VeilError(why, 502)
    have = {str(k).lower() for k in (n.get("calls") or {})}
    new = [p for p in people if p.lower() not in have]

    def change(doc):
        node = config.map_in(doc, "names_in_replies")
        calls = config.map_in(node, "calls", block=True)      # one to a line
        for p in new:
            seq = config.flow_list()
            calls[p] = seq
    if new:
        config.edit_yaml(config.SETTINGS_FILE, change)
    audit(request, "voice names pulled", detail={"from": src, "added": new})
    return {"from": src, "known": people, "added": new}


@app.put("/api/sparkle")
async def sparkle_set(request: Request):
    """Where the names come from (how often, how sure and each persona's own names are the
    persona's: /api/sparkle/device)."""
    need(request, "administrator")
    b = await body_of(request)
    s = config.settings()
    vals = {}
    if "voice_id_from" in b:
        v = str(b.get("voice_id_from") or "")
        if v and v not in {x["name"] for x in voice_id_sources(s)}:
            raise VeilError(f"{v} can't name people (it has no people list)")
        vals["voice_id_from"] = v

    def change(doc):
        for k, v in vals.items():
            config.set_in(doc, ["names_in_replies", k], v)
    config.edit_yaml(config.SETTINGS_FILE, change)
    audit(request, "user sparkle saved", detail=vals)
    restart_note("names")
    return {"saved": vals}


def call_names(raw):
    """The names to call someone, tidied: no blanks, no duplicates, no questions, 40 characters each."""
    names, seen = [], set()
    for x in raw or []:
        x = " ".join(str(x or "").split())
        if not x:
            continue
        if len(x) > 40:
            raise VeilError(f'"{x[:20]}...": a name is 40 characters at most')
        if x.endswith("?"):
            raise VeilError(f'"{x}": a name, not a question')
        if x.lower() not in seen:
            seen.add(x.lower())
            names.append(x)
    return names


@app.put("/api/sparkle/calls")
async def sparkle_calls(request: Request):
    """What she calls one person the voice ID knows: {person, names: [...]}; {person, remove: true}
    deletes the person (a saved voice stays until then, even with no names under it)."""
    need(request, "administrator")
    b = await body_of(request)
    person = " ".join(str(b.get("person") or "").split())
    if not person or len(person) > 40:
        raise VeilError("Whose names? (the voice ID's name for them, 40 characters at most)")
    names = call_names(b.get("names"))

    def change(doc):
        n = config.map_in(doc, "names_in_replies")
        calls = config.map_in(n, "calls", block=True)      # one to a line
        if b.get("remove"):
            if person in calls:
                del calls[person]
        else:
            seq = config.flow_list(names)
            calls[person] = seq
    config.edit_yaml(config.SETTINGS_FILE, change)
    audit(request, "voice person deleted" if b.get("remove") else "names the persona calls someone", target=person, detail=names)
    restart_note("names")
    return {"person": person, "names": names, "removed": bool(b.get("remove"))}


@app.put("/api/sparkle/device/{who}/calls")
async def sparkle_device_calls(request: Request, who: str):
    """One persona's own names for one voice: {person, names: [...]} (personality/<who>.yaml
    names: calls:). The persona uses these first, and the shared ones when it has none for them."""
    need(request, "administrator")
    assistant_ok(who)
    b = await body_of(request)
    person = " ".join(str(b.get("person") or "").split())
    if not person or len(person) > 40:
        raise VeilError("Whose names? (the voice ID's name for them, 40 characters at most)")
    names = call_names(b.get("names"))
    file = os.path.join(PERS, f"{who}.yaml")

    def change(doc):
        n = config.map_in(doc, "names")
        calls = config.map_in(n, "calls", block=True)
        if names:
            calls[person] = config.flow_list(names)
        elif person in calls:
            del calls[person]
        if not calls:
            del n["calls"]
    config.edit_yaml(file, change)
    audit(request, "persona's own names", target=f"{who}: {person}", detail=names)
    restart_note(f"names: {who}")
    return {"name": who, "person": person, "names": names}


@app.put("/api/sparkle/device/{who}")
async def sparkle_device(request: Request, who: str):
    """One persona's own names rate, most in a row and optional least score (personality/<who>.yaml
    names:). A rate above 0 is the switch; an empty min_score leaves it to the voice ID's "known"."""
    need(request, "administrator")
    assistant_ok(who)
    b = await body_of(request)
    names = {}
    if "min_score" in b and b["min_score"] not in (None, ""):
        try:
            ms = float(b["min_score"])
        except (TypeError, ValueError):
            raise VeilError("min_score is a number from 0 to 1, or empty")
        if not 0 <= ms <= 1:
            raise VeilError("min_score is from 0 to 1, or empty")
        names["min_score"] = ms
    for k, lo, hi in (("rate", 0, 1), ("max_in_a_row", 0, 10)):
        v = b.get(k)
        if v in (None, ""):
            continue
        try:
            v = float(v) if k == "rate" else int(v)
        except (TypeError, ValueError):
            raise VeilError(f"{k} is a number")
        if not lo <= v <= hi:
            raise VeilError(f"{k} is from {lo} to {hi}")
        names[k] = v
    file = os.path.join(PERS, f"{who}.yaml")
    header = (f"# personality/{who}.yaml - {who.title()}'s flair. Read by flair.py; edited on the Persona Flair page.\n"
              "# (See defaults/examples/personality/assistant.yaml for what each knob means.)")

    def change(doc):
        from ruamel.yaml.comments import CommentedMap
        doc.setdefault("rate", 0)
        doc.setdefault("max_in_a_row", 1)
        was = doc.get("names") if isinstance(doc.get("names"), dict) else {}
        keep = {k: v for k, v in was.items() if k not in ("enabled", "rate", "max_in_a_row", "min_score")}
        doc["names"] = CommentedMap({**names, **keep})
    config.edit_yaml(file, change, header=header)
    audit(request, "device names saved", target=who, detail=names)
    restart_note(f"names: {who}")
    return {"name": who, "names": names}


# ---------- the firewall ----------

@app.get("/api/firewall")
def firewall_get(request: Request):
    need(request, "viewer")
    try:
        spec = config.plain(config.load_yaml(config.FIREWALL_FILE))
    except FileNotFoundError:
        spec = {"enabled": False, "rules": []}
    s = config.settings()
    return {"firewall": spec, "oread_on": bool(config.section(config.section(s, "integrations"), "oread").get("enabled")),
            "people": people_map.voices(s),      # the voice ID's own names (saved on Name Sparkle)
            "assistants": sorted(set(router().FLAIR.names()) | set(choices("assistants"))),
            "words": frontend.words(s),
            "topics": sorted((s.get("topics") or {}).keys())}


@app.get("/api/firewall/devices")
async def firewall_devices(request: Request):
    """The rules' device names checked against Home Assistant's own devices (their names and entity
    ids, read with its token): {devices: how many it has, unknown: [{rule, name, device}]}, or
    {error} when it can't be read. Only the saved rules."""
    need(request, "viewer")
    s = config.settings()
    ha = dict(config.section(config.section(s, "integrations"), "home_assistant"))
    url, token = (ha.get("url") or "").rstrip("/"), config.secret(ha.get("token") or "HA_TOKEN")
    if not url or not token:
        return {"error": "Home Assistant's address or token isn't set (Integrations, Home Assistant)"}
    try:
        async with access.client(8) as c:
            resp = await c.get(url + "/api/states", headers={"Authorization": f"Bearer {token}"})
        if resp.status_code >= 300:
            return {"error": f"Home Assistant answered {resp.status_code}" + (" (the token was refused)" if resp.status_code == 401 else "")}
        states = resp.json()
    except Exception as e:
        return {"error": f"Couldn't reach Home Assistant: {e}"}
    names = []
    for st in states if isinstance(states, list) else []:
        names.append(str((st.get("attributes") or {}).get("friendly_name") or ""))
        names.append(str(st.get("entity_id") or "").split(".", 1)[-1].replace("_", " "))
    try:
        spec = config.plain(config.load_yaml(config.FIREWALL_FILE))
    except FileNotFoundError:
        spec = {}
    return {"devices": len(states) if isinstance(states, list) else 0,
            "unknown": firewall_mod.unknown_devices(spec.get("rules"), [n for n in names if n])}


@app.put("/api/firewall")
async def firewall_set(request: Request):
    need(request, "administrator")
    b = (await body_of(request)).get("firewall")
    if not isinstance(b, dict):
        raise VeilError("firewall is a set of rules")
    rules = []
    for i, r in enumerate(b.get("rules") or []):
        if not isinstance(r, dict):
            raise VeilError(f"rule {i + 1} isn't a rule")
        rule = {"name": " ".join(str(r.get("name") or "").split())[:80], "enabled": r.get("enabled", True) is not False}
        for k in ("people", "assistants", "voice_devices", "devices", "commands", "topics", "domains"):
            rule[k] = word_list([str(x) for x in (r.get(k) or [])], f"rule {i + 1} {k}") \
                if k not in ("topics", "domains") else [str(x).lower().strip() for x in (r.get(k) or []) if str(x).strip()]
        rule["intents"] = []
        for it in r.get("intents") or []:
            it = str(it).strip()
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,40}(:[a-z_]{1,40})?", it):
                raise VeilError(f"rule {i + 1}: '{it}' isn't a Home Assistant command (HassTurnOn, or HassTurnOn:lock)")
            rule["intents"].append(it)
        for dm in rule["domains"]:
            if not re.fullmatch(r"[a-z_]{1,40}", dm):
                raise VeilError(f"rule {i + 1}: '{dm}' isn't a kind of device (lock, cover, light...)")
        if not rule["people"]:
            raise VeilError(f"rule {i + 1} needs people (a name, unknown, or anyone)")
        rule["gemini"] = bool(r.get("gemini"))
        rule["message"] = " ".join(str(r.get("message") or "").split())[:200]
        if not (rule["gemini"] or any(rule[k] for k in ("voice_devices", "devices", "commands", "topics",
                                                         "domains", "intents"))):
            raise VeilError(f"rule {i + 1} ({rule['name'] or 'unnamed'}) stops nothing: give it devices, commands, "
                            "topics, kinds of device, Home Assistant commands, voice devices, or Off-Platform")
        rules.append(rule)
    spec = {"enabled": bool(b.get("enabled")), "sure_score": float(b.get("sure_score", 0.8)),
            "sure_labels": [str(x) for x in (b.get("sure_labels") or ["known"])],
            "when_oread_down": "allow" if b.get("when_oread_down") == "allow" else "unknown", "rules": rules,
            "off_platform_never": [str(x) for x in b.get("off_platform_never", router().FIREWALL.off_platform_never) or []]}
    firewall_mod.Firewall(spec)          # it must load

    def change(doc):
        from ruamel.yaml.comments import CommentedMap, CommentedSeq
        for k in ("enabled", "sure_score", "when_oread_down"):
            doc[k] = spec[k]
        sl = config.flow_list(spec["sure_labels"])
        doc["sure_labels"] = sl
        seq = CommentedSeq()
        for r in rules:
            m = CommentedMap()
            for k, v in r.items():
                if isinstance(v, list):
                    s_ = config.flow_list(v)
                    m[k] = s_
                else:
                    m[k] = v
            seq.append(m)
        doc["rules"] = seq
    config.edit_yaml(config.FIREWALL_FILE, change)
    router().FIREWALL = firewall_mod.Firewall(spec)       # takes effect at once
    audit(request, "firewall saved", detail=f"{'on' if spec['enabled'] else 'off'}, {len(rules)} rules")
    return {"saved": True, "active": spec["enabled"]}


# ---------- security: users, tokens, the vault, permitted addresses, the audit log ----------

@app.get("/api/users")
def users_list(request: Request):
    actor = need(request, "super")
    return {"users": USERS.list(), "grantable": USERS.grantable(actor), "roles": list(security.ROLES)}


@app.post("/api/users")
async def users_add(request: Request):
    actor = need(request, "super")
    b = await body_of(request)
    return USERS.create(actor, b.get("name", ""), b.get("password", ""), b.get("role", "viewer"))


@app.patch("/api/users/{name}")
async def users_change(request: Request, name: str):
    actor = need(request, "super")
    b = await body_of(request)
    return USERS.update(actor, name, b.get("role"), b.get("password"))


@app.delete("/api/users/{name}")
def users_remove(request: Request, name: str):
    actor = need(request, "super")
    USERS.delete(actor, name)
    return {"deleted": name}


@app.get("/api/tokens")
def tokens_list(request: Request):
    """Grantees: the doors (settings), each with the tokens tied to it; tokens tied to no door;
    and the sign-in rules (the Users tab)."""
    need(request, "super")
    sec = config.section(config.settings(), "security")
    all_doors = doorset.doors(sec)
    tokens = TOKENS.list()
    for t in tokens:                          # a token named like a door belongs to it until tied
        if not t.get("door") and t["name"].lower() in all_doors:
            t["door"] = t["name"].lower()
    built_in = set((config.DEFAULTS.get("security") or {}).get("doors") or {})
    rules = {k: sec.get(k) for k in ("password_min_length", "lock_after_failures", "lock_minutes",
                                     "session_idle_hours", "session_max_days")}
    return {"tokens": tokens, "roles": list(security.ROLES),
            "doors": [dict(d, name=n, built_in=n in built_in,
                           tokens=[t for t in tokens if t.get("door") == n]) for n, d in all_doors.items()],
            "untied": [t for t in tokens if t.get("door") not in all_doors],
            "rules": rules}


@app.post("/api/tokens")
async def tokens_add(request: Request):
    need(request, "super")
    b = await body_of(request)
    door = b.get("door") or None
    if door and door not in doorset.doors(config.section(config.settings(), "security")):
        raise VeilError(f"There's no door named {door}", 404)
    token = TOKENS.create(b.get("name", ""), b.get("role", "viewer"), door)
    audit(request, "token created", target=b.get("name"), detail=f"{b.get('role')} {door or ''}".strip())
    return {"name": b.get("name"), "token": token}


@app.patch("/api/tokens/{name}")
async def tokens_tie(request: Request, name: str):
    """Tie a token to a door (or untie it: door null)."""
    need(request, "super")
    b = await body_of(request)
    door = b.get("door") or None
    if door and door not in doorset.doors(config.section(config.settings(), "security")):
        raise VeilError(f"There's no door named {door}", 404)
    TOKENS.tie(name, door)
    audit(request, "token tied to a door", target=name, detail=door)
    return {"name": name, "door": door}


@app.post("/api/doors")
async def doors_add(request: Request):
    """A new door, as it's needed: {name, description, who, paths, role}. Saved to settings.yaml
    (security: doors:), open until you lock it."""
    need(request, "super")
    b = await body_of(request)
    name = str(b.get("name") or "").strip().lower()
    paths = b.get("paths") or []
    if isinstance(paths, str):
        paths = [p.strip() for p in paths.replace(",", " ").split() if p.strip()]
    d = {"description": str(b.get("description") or "").strip()[:200], "who": str(b.get("who") or "").strip()[:200],
         "paths": paths, "role": b.get("role") or "viewer", "locked": False}
    problem = doorset.check_new(name, d, doorset.doors(config.section(config.settings(), "security")))
    if problem:
        raise VeilError(problem)
    config.edit_yaml(config.SETTINGS_FILE, lambda doc: config.set_in(doc, ["security", "doors", name], d))
    use_security()
    audit(request, "door added", target=name, detail=" ".join(paths))
    return dict(d, name=name)


@app.delete("/api/doors/{name}")
def doors_remove(request: Request, name: str):
    """Take out a door you added (the built-in ones stay; they can be left open)."""
    need(request, "super")
    if name in ((config.DEFAULTS.get("security") or {}).get("doors") or {}):
        raise VeilError(f"The {name} door is built in: leave it open instead")

    def drop(doc):
        d = ((doc.get("security") or {}).get("doors") or {})
        if name not in d:
            raise VeilError(f"There's no door named {name}", 404)
        del d[name]
    config.edit_yaml(config.SETTINGS_FILE, drop)
    use_security()
    audit(request, "door removed", target=name)
    return {"removed": name}


def use_security():
    """The security settings, in use at once: addresses, doors, sign-in rules."""
    sec = config.section(config.settings(), "security")
    access.ACCESS.load(config.settings().get("security"))
    security.use(sec)
    router()._SEC.clear()
    router()._SEC.update(sec)


@app.delete("/api/tokens/{name}")
def tokens_remove(request: Request, name: str):
    need(request, "super")
    TOKENS.revoke(name)
    audit(request, "token revoked", target=name)
    return {"revoked": name}


@app.get("/api/vault")
def vault_list(request: Request):
    need(request, "super")
    v = config.vault()
    if not v:
        return {"keys": [], "off": True}
    listing = v.list()
    s = config.settings()
    # grantors: each key the router sends, and the program that granted it
    wanted = {llm_key_name(): "LiteLLM"}
    for name, svc in (s.get("services") or {}).items():
        if svc.get("secret"):
            wanted[svc["secret"]] = (svc.get("title") or name.replace("_", " ").capitalize())
    for k, svc in (s.get("integrations") or {}).items():
        t = (svc or {}).get("token") if isinstance(svc, dict) else None
        if t:
            wanted[t] = (svc.get("title") or k.replace("_", " ").title())
    # step 1 of adding an app: a key added here with its program, before the app is
    taken = {n.lower() for n in wanted}
    for k in listing["keys"]:
        if k.get("service") and k["name"] not in taken:
            wanted[k["name"].upper()] = k["service"]
    listing["wanted"] = [{"name": n, "for": who, "from": config.secret_source(n)} for n, who in sorted(wanted.items())]
    return listing


def llm_key_name():
    """The name LiteLLM's key goes by (settings: llm: key)."""
    return config.litellm()["key"]


def app_keys():
    """Step 1 of adding an app: vault keys no setting uses yet, each with the program it's for."""
    v = config.vault()
    if not v:
        return []
    s = config.settings()
    used = {llm_key_name().lower()}
    used |= {str(svc.get("secret")).lower() for svc in (s.get("services") or {}).values() if (svc or {}).get("secret")}
    used |= {str(i.get("token")).lower() for i in (s.get("integrations") or {}).values() if isinstance(i, dict) and i.get("token")}
    return [{"name": k["name"].upper(), "for": k.get("service") or ""} for k in v.list()["keys"] if k["name"] not in used]


@app.put("/api/vault/{name}")
async def vault_set(request: Request, name: str):
    need(request, "super")
    b = await body_of(request)
    v = config.vault()
    if not v:
        raise VeilError("The vault isn't available", 409)
    item = v.set(name, b.get("value", ""), b.get("service"), b.get("note"))
    audit(request, "vault key set", target=item["name"])
    restart_note(f"vault: {item['name']}")      # keys are read when the router starts
    return item


@app.delete("/api/vault/{name}")
def vault_delete(request: Request, name: str):
    need(request, "super")
    v = config.vault()
    if not v:
        raise VeilError("The vault isn't available", 409)
    v.delete(name)
    audit(request, "vault key deleted", target=name)
    restart_note(f"vault: {name}")
    return {"deleted": name}


@app.get("/api/access")
def access_get(request: Request):
    need(request, "super")
    return access.ACCESS.view()


@app.put("/api/access")
async def access_set(request: Request):
    """{inbound_allowed: [...], admin_allowed: [...], outbound_allowed: [...]}: saved and used at once.
    You can't leave yourself out of admin_allowed."""
    need(request, "super")
    b = await body_of(request)
    new = {k: [str(e).strip() for e in (b.get(k) or []) if str(e).strip()] for k in access.LISTS}
    for k, v in new.items():
        access.parse(v, names_ok=k == "outbound_allowed")
    test = access.Access(new)
    if not test.allowed("admin_allowed", client_of(request)):
        raise VeilError(f"That would lock you out: your address ({client_of(request)}) isn't in admin_allowed", 409)

    def change(doc):
        for k, v in new.items():
            s_ = config.flow_list(v)
            config.set_in(doc, ["security", k], s_)
    config.edit_yaml(config.SETTINGS_FILE, change)
    access.ACCESS.load(dict(config.settings().get("security") or {}))
    audit(request, "permitted addresses changed", detail=new)
    return access.ACCESS.view()


@app.get("/api/audit")
def audit_list(request: Request, limit: int = 200):
    need(request, "super")
    return {"events": AUDIT.recent(max(1, min(limit, 2000)))}


# ---------- restart (the container comes straight back: restart: unless-stopped) ----------

@app.post("/api/restart")
def restart(request: Request):
    need(request, "administrator")
    audit(request, "restart")
    log.info("restart asked for on the pages (%s)", ", ".join(sorted(RESTART_NEEDED)) or "nothing pending")

    def later():
        time.sleep(0.7)
        os._exit(0)
    threading.Thread(target=later, daemon=True).start()
    return {"restarting": True}


# ---------- the guides (docs/ in the page) ----------

@app.get("/api/guide/{name}")
def guide(request: Request, name: str):
    need(request, "viewer")
    files = {"users": "docs/users-guide.md", "guide": "docs/coders-guide.md", "design": "docs/design.md", "readme": "README.md"}
    if name not in files:
        raise VeilError("No such guide", 404)
    try:
        with open(config.path(files[name])) as f:
            return Response(f.read(), media_type="text/plain; charset=utf-8")
    except FileNotFoundError:
        raise VeilError("That guide isn't in this copy", 404)

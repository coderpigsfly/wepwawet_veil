"""addons/mishearings/api.py - the Mishearings page's doors: what was heard under what was meant, the swaps in
use, and Misheard on the Transactions page. Moved out of the core's pages server (veil/web.py) with the add-on
(issue #25): registered only when Mishearings is on."""
import re  # noqa: F401

from fastapi import Request  # noqa: F401


def register(app):
    from veil.errors import VeilError  # noqa: F401
    from veil.web import audit, body_of, decision_of, need, router, word_diff  # noqa: F401
    import mishearings  # noqa: E402  (beside it)

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

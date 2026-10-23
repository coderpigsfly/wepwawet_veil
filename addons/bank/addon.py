"""addons/bank: the Off-Platform Bank answering in place of a trip out (issue #25, step 4). The core counts each
saying that goes out (its activity log); this decides whether the answers kept for it answer it this time."""


def before_off_platform(said, ctx):
    """The bank's answer for this request this time ({kind: answer, text, bank_id, q, generic_from}), else None.
    ctx: assistant, key (its saying), rewrite (a yes to ask around goes out as asked), activity (the core's
    log), keeps (answers are kept), step (the request's why)."""
    act, step = ctx.get("activity"), ctx.get("step") or (lambda text: None)
    if not (act and ctx.get("keeps") and getattr(act, "answer_from_bank", False)) or ctx.get("rewrite") or not ctx.get("key"):
        step("not looked in: " + ("the activity log is off" if not act else
                                  "answers kept is 0" if not ctx.get("keeps") else
                                  "Use the bank (answer_from_bank) is off" if not getattr(act, "answer_from_bank", False) else
                                  "a yes to ask around goes out as asked" if ctx.get("rewrite") else "no words to look up"))
        return None
    hit, why = act.bank_choose(ctx.get("assistant"), ctx["key"])
    step(why)
    # words only (Oct 14): a device command is never kept, so never handed out
    return hit if hit and hit.get("kind") == "answer" and (hit.get("text") or "").strip() else None

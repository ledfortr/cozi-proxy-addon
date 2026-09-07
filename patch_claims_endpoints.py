"""Rewrite the chore endpoints onto the claim lifecycle.

Everything that used to mutate the chore - done_by, approved, queued_for,
posted - now creates or advances a claim instead. The chore row is read-only
from here on, which is what lets two kids hold the same job at once.
"""
import io
import os
import re

P = 'cozi_proxy/server.py'
s = io.open(P, encoding='utf-8').read()


def cut(start_marker, end_marker, replacement, what):
    """Replace a whole endpoint, from its decorator to the next one."""
    global s
    i = s.find(start_marker)
    if i < 0:
        raise SystemExit('start missing: ' + what)
    j = s.find(end_marker, i + len(start_marker))
    if j < 0:
        raise SystemExit('end missing: ' + what)
    s = s[:i] + replacement + s[j:]


NEXT = '\n\n@app.post("/chores/parent_done")'

cut('@app.post("/chores/claim")', NEXT, '''@app.post("/chores/claim")
async def chores_claim(req: ChoreClaim):
    """A kid takes a job. This creates a claim; the chore itself is untouched and
    stays on the board, so the other kid can take the same job the same day."""
    kid = req.kid.lower()
    if kid not in ("ian", "evan", "parent"):
        raise HTTPException(status_code=400, detail="kid must be ian, evan or parent")
    async with _chores_lock:
        d = _chores_read()
        target = next((c for c in d["chores"] if c["id"] == req.id), None)
        if not target:
            raise HTTPException(status_code=404, detail="chore not found")
        # One open claim each. Repeats are unlimited, but finish the one you have
        # before taking the same job again, or the queue fills with duplicates.
        if any(c["state"] in CLAIM_OPEN
               for c in _claims_for(d, kid=kid, chore_id=req.id)):
            raise HTTPException(status_code=409,
                                detail="You already have that one in your queue")
        cid = d.get("next_claim", 1)
        d["next_claim"] = cid + 1
        d.setdefault("claims", []).append({
            "id": cid, "chore_id": target["id"], "name": target["name"],
            "points": int(target.get("points", 0)), "kid": kid, "state": "queued",
            "queued_at": _now_local().isoformat(timespec="seconds"),
            "on": _today().isoformat(),
        })
        _chores_write(d)
    return {"status": "ok", "claim": cid}


@app.post("/chores/done")
async def chores_done(req: ChoreId):
    """Kid says they've finished it. Moves the claim into the parent queue; the
    points stay pending until a parent signs off."""
    async with _chores_lock:
        d = _chores_read()
        cl = next((c for c in d.get("claims", []) if c["id"] == req.id), None)
        if not cl:
            raise HTTPException(status_code=404, detail="claim not found")
        if cl["state"] != "queued":
            raise HTTPException(status_code=409, detail="that claim isn't open")
        cl["state"] = "done"
        cl["done_at"] = _now_local().isoformat(timespec="seconds")
        cl.pop("rejected", None)
        _chores_write(d)
    kid_label = PEOPLE_LABEL.get(cl["kid"], cl["kid"].title())
    asyncio.create_task(_send_sms(
        "mom", "%s just completed chore [%s] at %s"
               % (kid_label, cl["name"], _stamp(_now_local()))))
    return {"status": "ok"}
''', 'claim')

# ------------------------------------------------------------------ unclaim
NEXT2 = '\n\n@app.post("/chores/reject")'
cut('@app.post("/chores/unclaim")', NEXT2, '''@app.post("/chores/unclaim")
async def chores_unclaim(req: ChoreId):
    """Kid drops a claim. Nothing was banked, so the row just goes away."""
    async with _chores_lock:
        d = _chores_read()
        before = len(d.get("claims", []))
        d["claims"] = [c for c in d.get("claims", [])
                       if not (c["id"] == req.id and c["state"] in CLAIM_OPEN)]
        _chores_write(d)
    return {"status": "ok", "removed": before - len(d["claims"])}
''', 'unclaim')

# ------------------------------------------------------------------ reject
NEXT3 = '\n\n@app.post("/chores/approve")'
cut('@app.post("/chores/reject")', NEXT3, '''@app.post("/chores/reject")
async def chores_reject(req: ChoreReject):
    """Parent sends a claim back. Nothing to claw back - points only ever land on
    approval - so the claim simply returns to the kid's queue with the note."""
    async with _chores_lock:
        d = _chores_read()
        cl = next((c for c in d.get("claims", []) if c["id"] == req.id), None)
        if not cl:
            raise HTTPException(status_code=404, detail="claim not found")
        if cl["state"] != "done":
            raise HTTPException(status_code=409, detail="that claim isn't waiting")
        cl["state"] = "queued"
        cl.pop("done_at", None)
        cl["rejected"] = {
            "kid": cl["kid"],
            "comment": (req.comment or "").strip(),
            "at": _now_local().isoformat(timespec="minutes"),
        }
        d.setdefault("rejections", []).append({
            "chore": cl["name"], "kid": cl["kid"], "points": int(cl.get("points", 0)),
            "comment": (req.comment or "").strip(),
            "at": _now_local().isoformat(timespec="minutes"),
        })
        d["rejections"] = d["rejections"][-100:]
        _chores_write(d)
    body = "Your chore [%s] was sent back: %s" % (cl["name"],
                                                  (req.comment or "").strip() or "please redo it")
    sent = await _send_sms(cl["kid"], body)
    return {"status": "ok", "sms": sent}
''', 'reject')

# ------------------------------------------------------------------ approve
NEXT4 = '\n\n@app.post("/chores/repost")'
cut('@app.post("/chores/approve")', NEXT4, '''@app.post("/chores/approve")
async def chores_approve(req: ChoreId):
    """Parent signs off. This is the moment the points actually move, which is
    why the board shows banked and pending as two separate numbers."""
    async with _chores_lock:
        d = _chores_read()
        cl = next((c for c in d.get("claims", []) if c["id"] == req.id), None)
        if not cl:
            raise HTTPException(status_code=404, detail="claim not found")
        if cl["state"] == "approved":
            return {"status": "ok", "already": True}
        if cl["state"] != "done":
            raise HTTPException(status_code=409, detail="that claim isn't finished yet")
        cl["state"] = "approved"
        cl["approved_at"] = _now_local().isoformat(timespec="seconds")
        cl.pop("rejected", None)
        kid = cl["kid"]
        d["log"].setdefault(kid, []).append({
            "chore_id": cl["chore_id"], "claim_id": cl["id"], "name": cl["name"],
            "points": int(cl.get("points", 0)),
            "on": cl.get("on"), "at": cl["approved_at"],
        })
        _chores_write(d)
    return {"status": "ok", "points": int(cl.get("points", 0)), "kid": cl["kid"]}
''', 'approve')

# ------------------------------------------------------------ parent_done
NEXT5 = '\n\n@app.post("/chores/unclaim")'
cut('@app.post("/chores/parent_done")', NEXT5, '''@app.post("/chores/parent_done")
async def chores_parent_done(req: ChoreId):
    """A parent finishing their own job needs no approval step, so this claims
    and approves in one move."""
    async with _chores_lock:
        d = _chores_read()
        target = next((c for c in d["chores"] if c["id"] == req.id), None)
        if not target:
            raise HTTPException(status_code=404, detail="chore not found")
        cid = d.get("next_claim", 1)
        d["next_claim"] = cid + 1
        now = _now_local().isoformat(timespec="seconds")
        d.setdefault("claims", []).append({
            "id": cid, "chore_id": target["id"], "name": target["name"],
            "points": int(target.get("points", 0)), "kid": "parent",
            "state": "approved", "queued_at": now, "done_at": now,
            "approved_at": now, "on": _today().isoformat(),
        })
        d["log"].setdefault("parent", []).append({
            "chore_id": target["id"], "claim_id": cid, "name": target["name"],
            "points": int(target.get("points", 0)),
            "on": _today().isoformat(), "at": now,
        })
        _chores_write(d)
    return {"status": "ok"}
''', 'parent_done')

tmp = P + '.tmp'
io.open(tmp, 'w', encoding='utf-8').write(s)
os.replace(tmp, P)
print('server: claim / done / approve / reject / unclaim rewritten')

"""Ad-hoc one-off jobs close out and approve on the spot, 2026-10-30.

A one-off is nearly always work that has already happened - a parent is
recording it, not handing it out. The old path created a claimable chore, put a
queued claim in the kid's queue, waited for a Done tap, then waited again for a
parent sign-off: three steps to record something already finished.

Now /chores/adhoc writes one approved claim and banks the points immediately.
No chore row, so the closed-out job does not sit on the board claimable again
for the same points until Monday. Pass approve=false for the old queue path.

Also adds /chores/void. An instantly-approved claim had no way back: unclaim
only accepts open claims and reject only accepts finished ones, so both buttons
on a completed card were dead. Parent-gated in the dashboard.

Anchored edits: each anchor must match exactly once or nothing is written
(the jobboard.py convention).
"""
import io
import shutil
import sys
import time

P = "cozi_proxy/server.py"
s = io.open(P, encoding="utf-8").read()


def sub(anchor, new, where="replace"):
    global s
    n = s.count(anchor)
    if n != 1:
        sys.exit("anchor matched %d times, expected 1:\n%s" % (n, anchor[:200]))
    if where == "before":
        s = s.replace(anchor, new + anchor)
    elif where == "after":
        s = s.replace(anchor, anchor + new)
    else:
        s = s.replace(anchor, new)


# ---------------------------------------------------------------- 1. the flag
sub('''class ChoreAdHoc(BaseModel):
    name: str
    description: str = ""
    points: int = 0
    kid: str                     # ian or evan
''',
    'class ChoreAdHoc(BaseModel):\n'
    '    name: str\n'
    '    description: str = ""\n'
    '    points: int = 0\n'
    '    kid: str                     # ian, evan or parent\n'
    '    # A one-off is nearly always work that already happened, so closing it\n'
    '    # out is the default. approve=false keeps the old queue-and-sign-off path.\n'
    '    approve: bool = True\n')

# ------------------------------------------------------- 2. what it does now
sub('''    """Parent adds a one-off chore straight into a kid's queue and texts them.
    It's a normal chore (claimable for points) but frequency 'once' so the
    weekly roll drops it instead of reposting."""''',
    '''    """Parent adds a one-off job.

    approve=True (the default): no chore row and no queue. One approved claim is
    written and the points are banked on the spot - new job straight to approved,
    no Done tap and no sign-off. Nothing is left on the board, so a job that is
    already finished cannot be claimed again for the same points until Monday.

    approve=False: the old path - a normal claimable chore at frequency 'once'
    that lands in the kid's queue, so the weekly roll drops it instead of
    reposting."""''')

# --------------------------------------------- 3. the instant-approve branch
sub('''@app.post("/chores/adhoc")
async def chores_adhoc(req: ChoreAdHoc):''',
    '''async def _adhoc_approved(kid, req):
    """One-off, already done, already signed off.

    No chore is appended. Every claim lookup in the board and the reports runs
    chore -> claims and never the other way, and a claim carries its own name and
    points, so a chore_id with nothing behind it renders, banks and rolls up
    correctly. next_id is still consumed so the id can never collide with a real
    chore later."""
    name = req.name.strip()
    desc = (req.description or "").strip()
    points = int(req.points)
    async with _chores_lock:
        d = _chores_read()
        cid = d.get("next_id", 1)
        d["next_id"] = cid + 1
        clid = d.get("next_claim", 1)
        d["next_claim"] = clid + 1
        now = _now_local().isoformat(timespec="seconds")
        d.setdefault("claims", []).append({
            "id": clid, "chore_id": cid, "name": name, "points": points,
            "kid": kid, "state": "approved", "description": desc,
            "queued_at": now, "done_at": now, "approved_at": now,
            "on": _today().isoformat(), "source": "adhoc",
        })
        d["log"].setdefault(kid, []).append({
            "chore_id": cid, "claim_id": clid, "name": name, "points": points,
            "on": _today().isoformat(), "at": now,
        })
        _chores_write(d)
    what = desc or name
    if kid == "parent":
        body = "Logged and approved: %s (%s pts)." % (what, points)
        sent = await _notify_parents(body, title="Job approved",
                                     tag="chore_adhoc_approved")
    else:
        # Not the cupcake speech - there is nothing left for them to go and do.
        body = ("Logged for you: %s. That is %s pts, already approved and banked."
                % (what, points))
        sent = await _notify(kid, body, title="Job approved",
                             tag="chore_adhoc_approved")
    return {"status": "ok", "id": cid, "claim": clid, "approved": True,
            "points": points, "kid": kid, "sms": sent}


@app.post("/chores/adhoc")
async def chores_adhoc(req: ChoreAdHoc):''')

sub('''        raise HTTPException(status_code=400, detail="kid must be ian, evan or parent")
    async with _chores_lock:
        d = _chores_read()
        cid = d.get("next_id", 1)
        c = {"id": cid, "name": req.name.strip(),''',
    '''        raise HTTPException(status_code=400, detail="kid must be ian, evan or parent")
    if req.approve:
        return await _adhoc_approved(kid, req)
    async with _chores_lock:
        d = _chores_read()
        cid = d.get("next_id", 1)
        c = {"id": cid, "name": req.name.strip(),''')

# ------------------------------------- 4. the legacy reply says so explicitly
sub("""        sent = await _notify(kid, body, title="New chore", tag="chore_new")
    return {"status": "ok", "id": cid, "sms": sent}""",
    """        sent = await _notify(kid, body, title="New chore", tag="chore_new")
    return {"status": "ok", "id": cid, "approved": False, "sms": sent}""")


# ------------------------------------------------------------- 5. the way back
sub('''@app.post("/chores/repost")''',
    '''@app.post("/chores/void")
async def chores_void(req: ChoreId):
    """Take back an approved claim and unbank its points.

    The only way back from an instantly-approved one-off: unclaim drops open
    claims only and reject accepts finished ones only, so neither touches an
    approved claim. Points live in two places once signed off - the claim and
    the weekly log - and both have to go or the board and the bank disagree."""
    async with _chores_lock:
        d = _chores_read()
        cl = next((c for c in d.get("claims", []) if c["id"] == req.id), None)
        if not cl:
            raise HTTPException(status_code=404, detail="claim not found")
        if cl.get("state") != "approved":
            raise HTTPException(status_code=409, detail="that claim is not approved")
        kid = cl["kid"]
        name = cl["name"]
        points = int(cl.get("points", 0))
        d["claims"] = [c for c in d["claims"] if c["id"] != req.id]
        d["log"][kid] = [e for e in d["log"].get(kid, [])
                         if e.get("claim_id") != req.id]
        _chores_write(d)
    return {"status": "ok", "name": name, "kid": kid, "points": points}


@app.post("/chores/repost")''')

shutil.copyfile(P, P + ".bak_adhoc_" + time.strftime("%Y%m%d-%H%M%S"))
with io.open(P, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(s)
print("patched", P)

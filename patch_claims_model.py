"""Rebuild the chore engine around claims instead of schedules.

A chore used to be a thing that moved: it sat on the board until somebody took
it, then it left, then a timer put it back. That made "walk the dog" a race -
whoever grabbed it first owned it for the day - and it meant the board's
contents depended on what time you looked.

Now a chore is a permanent catalogue entry that never leaves the board, and each
attempt is a separate claim row:

    queued -> done -> approved

Ian can walk the dog at 7am and Evan can walk it again at 6pm; those are two
claims against one unchanged chore, and both pay. Points move on approval, so
the header can show banked and pending separately.

Approved claims still append to log[kid], which is what totals, the champion,
the streak and the casino balance already read - so none of that had to change.
"""
import io
import os

P = 'cozi_proxy/server.py'
s = io.open(P, encoding='utf-8').read()


def sub(old, new, what):
    global s
    if old not in s:
        raise SystemExit('anchor missing: ' + what)
    s = s.replace(old, new, 1)


# ------------------------------------------------------------ storage shape
sub('''    return {"target": 100, "chores": [], "log": {"ian": [], "evan": [], "parent": []},
            "week_start": None,''',
    '''    return {"target": 100, "chores": [], "log": {"ian": [], "evan": [], "parent": []},
            "claims": [], "next_claim": 1, "week_start": None,''',
    'default store')

sub('''        base["log"].setdefault("parent", [])''',
    '''        base["log"].setdefault("parent", [])
        base.setdefault("claims", [])
        base.setdefault("next_claim", 1)''',
    'read defaults')

# ------------------------------------------------------------ claim helpers
sub('''def _roll_week(d, on=None):''',
    '''CLAIM_OPEN = ("queued", "done")


def _claims_for(d, kid=None, state=None, chore_id=None):
    out = []
    for cl in d.get("claims", []):
        if kid is not None and cl.get("kid") != kid:
            continue
        if state is not None and cl.get("state") != state:
            continue
        if chore_id is not None and cl.get("chore_id") != chore_id:
            continue
        out.append(cl)
    return out


def _pending_points(d):
    """Claimed and finished, still waiting on a parent. Shown next to the banked
    total so a kid can see the work is counted, just not signed off yet."""
    out = {}
    for kid in ("ian", "evan", "parent"):
        out[kid] = sum(int(c.get("points", 0))
                       for c in _claims_for(d, kid=kid, state="done"))
    return out


def _roll_week(d, on=None):''',
    'claim helpers')

# ------------------------------------------------------------ weekly roll
sub('''    on = on or _today()
    done = [c for c in d["chores"] if c.get("done_by")]
    for c in done:
        c["last_done"] = on.isoformat()
    if done:''',
    '''    on = on or _today()
    # Approved claims are the week's record now; the chores themselves never
    # changed state, so there is nothing on them to stamp.
    done = _claims_for(d, state="approved")
    if done:''',
    'roll_week head')

sub('''            "completed": [{"name": c["name"], "by": c["done_by"],
                           "points": c.get("points", 0)} for c in done],''',
    '''            "completed": [{"name": c["name"], "by": c["kid"],
                           "points": c.get("points", 0)} for c in done],''',
    'roll_week history')

sub('''    # one-off ad-hoc chores that got done just disappear; they don't repost
    d["chores"] = [c for c in d["chores"]
                   if not (c.get("frequency") == "once" and c.get("done_by"))]
    for c in d["chores"]:
        c["done_by"] = None
        c.pop("rejected", None)
        c["queued_for"] = "na"       # queues start fresh each week
        c.pop("queued_at", None)
        c.pop("queued_by", None)
    d["log"] = {"ian": [], "evan": [], "parent": []}
    d["week_start"] = _monday(on).isoformat()
    _repost(d, on)
    return len(done)''',
    '''    # a one-off that somebody actually finished has served its purpose
    finished_once = {c["chore_id"] for c in done}
    d["chores"] = [c for c in d["chores"]
                   if not (c.get("frequency") == "once" and c["id"] in finished_once)]
    d["claims"] = []
    d["log"] = {"ian": [], "evan": [], "parent": []}
    d["week_start"] = _monday(on).isoformat()
    return len(done)''',
    'roll_week tail')

# ------------------------------------------------------------ no more rolling
sub('''def _maybe_roll(d):
    """Auto-advance on Monday, reopen dailies each morning, expire stale self-
    grabbed queue items, and run the duplicate-tidy pass; catches up if off."""
    today = _today()
    this_monday = _monday(today)
    ws = _parse_date(d.get("week_start") or "")
    changed = False
    if ws is None or ws < this_monday:
        _roll_week(d, today)
        changed = True
    elif _roll_daily(d) > 0:
        changed = True
    if _expire_queues(d) > 0:
        changed = True
    if _dedupe(d):
        _repost(d, today)
        changed = True
    return changed''',
    '''def _maybe_roll(d):
    """Only the scoring week rolls now. Chores no longer go anywhere, so there
    are no dailies to reopen, nothing to re-post, and no stale queue items to
    expire - an unfinished claim is just work the kid hasn't done yet."""
    today = _today()
    this_monday = _monday(today)
    ws = _parse_date(d.get("week_start") or "")
    changed = False
    if ws is None or ws < this_monday:
        _roll_week(d, today)
        changed = True
    if _dedupe(d):
        changed = True
    return changed''',
    'maybe_roll')

# ------------------------------------------------------------ board state
sub('''def _gate(chores):
    """Board state. Optional chores are unlocked per-kid on a 1-required-unlocks-
    1-optional basis (see _credits); `optional_unlocked` is true if either kid
    currently has an unlock to spend."""
    req = [c for c in chores
           if c.get("kind", "required") == "required" and c.get("posted", True)]
    left = [c for c in req if not c.get("done_by")]
    credits = {k: max(0, _credits(chores, k)) for k in ("ian", "evan")}
    return {"required_total": len(req), "required_left": len(left),
            "optional_credits": credits,
            "optional_unlocked": any(v > 0 for v in credits.values())}''',
    '''def _gate(chores):
    """Required/Optional is a priority label now, not a lock. The unlock gate
    counted chores whose done_by the daily roll cleared every morning, so it
    never worked the way its docstring claimed; nothing gates a claim today."""
    req = [c for c in chores if c.get("kind", "required") == "required"]
    return {"required_total": len(req), "required_left": len(req),
            "optional_credits": {"ian": 0, "evan": 0},
            "optional_unlocked": True}''',
    'gate')

tmp = P + '.tmp'
io.open(tmp, 'w', encoding='utf-8').write(s)
os.replace(tmp, P)
print('server: storage, weekly roll and board state moved onto claims')

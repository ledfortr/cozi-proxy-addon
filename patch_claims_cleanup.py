"""Retire the scheduling leftovers now that chores never leave the board.

_repost decided which chores were visible from a due date; there is no such
thing any more, so the calls go and the survivors stop reading done_by, which
nothing writes.
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


# reconcile: a chore with open work shouldn't be deleted out from under the kid
sub('''                if (gone or sheet_dropped) and not c.get("done_by"):''',
    '''                held = any(cl["state"] in CLAIM_OPEN
                           for cl in _claims_for(d, chore_id=c["id"]))
                if (gone or sheet_dropped) and not held:''',
    'reconcile drop guard')

sub('''        rolled = _maybe_roll(d)
        if not rolled:
            _repost(d)
        d["last_sync"]''',
    '''        _maybe_roll(d)
        d["last_sync"]''',
    'sync roll')

sub('''                if req.assigned_to is not None:
                    c["assigned_to"] = _person(req.assigned_to)
        _repost(d)
        _chores_write(d)''',
    '''                if req.assigned_to is not None:
                    c["assigned_to"] = _person(req.assigned_to)
        _chores_write(d)''',
    'edit repost')

# dedupe ranking: prefer the row with live claims against it
sub('''        def _rank(x):
            return (bool(x.get("done_by")), x.get("queued_for", "na") != "na",
                    bool(x.get("from_sheet")))''',
    '''        def _rank(x):
            claimed = any(cl["chore_id"] == x.get("id") for cl in d.get("claims", []))
            return (claimed, bool(x.get("from_sheet")))''',
    'dedupe rank')

# /chores/queue is the old "grab it" path; claiming is what does that now
sub('''        if c.get("done_by"):
            raise HTTPException(status_code=409, detail="already completed")
        c["queued_for"] = kid''',
    '''        c["queued_for"] = kid''',
    'queue guard')

tmp = P + '.tmp'
io.open(tmp, 'w', encoding='utf-8').write(s)
os.replace(tmp, P)
print('server: scheduling leftovers retired')

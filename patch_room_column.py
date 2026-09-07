"""Carry the spreadsheet's new "Room" column through to the board.

The job board is one long flat list, which is hard to scan when you're standing
at the tablet looking for something specific. Grouping by room is only possible
if the room actually reaches the client, so the value has to survive both the
sheet parse and the reconcile that merges sheet rows onto existing chores.
"""
import io
import os

P = 'cozi_proxy/server.py'
s = io.open(P, encoding='utf-8').read()

# ---- 1. read the column out of each sheet row
old = '''        out[_norm(name)] = {"name": name, "points": pts,
                            "description": val(row, "description"),
                            "kind": kind, "source": "sheet",
                            "frequency": _freq(val(row, "frequency")),
                            "assigned_to": _person(val(row, "assigned"))}'''
new = '''        out[_norm(name)] = {"name": name, "points": pts,
                            "description": val(row, "description"),
                            "kind": kind, "source": "sheet",
                            "frequency": _freq(val(row, "frequency")),
                            "room": val(row, "room").strip(),
                            "assigned_to": _person(val(row, "assigned"))}'''
assert old in s, 'sheet row builder not found'
s = s.replace(old, new, 1)

# ---- 2. claim the header. Before "name": "room" would otherwise be swallowed
# by the name pattern's "name" needle, and after "description" so a
# "Room / Details" style header still goes to description first.
old = '''    claim("points", "point", "pts", "value", "worth")'''
new = '''    claim("room", "room", "area", "location", "where", "zone")
    claim("points", "point", "pts", "value", "worth")'''
assert old in s, 'claim block not found'
s = s.replace(old, new, 1)

# ---- 3. keep it on the chore through reconcile (update path)
old = '''                c.update({"name": e["name"], "points": e["points"],
                          "description": _merge_desc(c.get("description"), e["description"]),
                          "kind": e["kind"],
                          "assigned_to": e.get("assigned_to", c.get("assigned_to", "na"))})'''
new = '''                c.update({"name": e["name"], "points": e["points"],
                          "description": _merge_desc(c.get("description"), e["description"]),
                          "kind": e["kind"],
                          "assigned_to": e.get("assigned_to", c.get("assigned_to", "na"))})
                # Cozi rows carry no room, so an empty one must not wipe the
                # sheet's value on a later Cozi-only pass.
                if e.get("room"):
                    c["room"] = e["room"]'''
assert old in s, 'reconcile update path not found'
s = s.replace(old, new, 1)

# ---- 4. and on the create path
old = '''                nc = {"id": cid, "name": e["name"], "points": e["points"],
                      "description": e["description"], "kind": e["kind"],
                      "frequency": e.get("frequency") or DEFAULT_FREQ,'''
new = '''                nc = {"id": cid, "name": e["name"], "points": e["points"],
                      "description": e["description"], "kind": e["kind"],
                      "room": e.get("room", ""),
                      "frequency": e.get("frequency") or DEFAULT_FREQ,'''
assert old in s, 'reconcile create path not found'
s = s.replace(old, new, 1)

tmp = P + '.tmp'
io.open(tmp, 'w', encoding='utf-8').write(s)
os.replace(tmp, P)
print('server: Room column now parsed, merged and persisted')

import os
import json
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from cozi import Cozi
from cozi.exceptions import InvalidLoginException, CoziException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp

app = FastAPI(title="Cozi Proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cozi_client: Cozi | None = None
logged_in = False

# ====================== IMPROVED AUTO LOGIN WITH BROWSER HEADERS ======================
async def auto_login():
    global cozi_client, logged_in
    print("=== Cozi Proxy: Auto-login starting ===")

    options_path = "/data/options.json"
    if not os.path.exists(options_path):
        print("❌ options.json not found!")
        return

    with open(options_path, "r") as f:
        options = json.load(f)
        username = options.get("username")
        password = options.get("password")

    if not username or not password:
        print("❌ Username or password missing!")
        return

    print(f"Logging in with username: {username}")

    # Create a real browser-like session
    session = aiohttp.ClientSession(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.cozi.com/",
            "Origin": "https://www.cozi.com",
        }
    )

    cozi_client = Cozi(username, password)
    cozi_client._session = session  # Override with our browser session

    for attempt in range(6):
        try:
            await cozi_client.login()
            print("✅ Login successful!")
            logged_in = True
            return
        except Exception as e:
            print(f"❌ Login attempt {attempt+1}/6 failed: {e}")
            await asyncio.sleep(12)

    print("⚠️ All login attempts failed. Use /relogin to try again.")

@app.on_event("startup")
async def startup_event():
    await auto_login()
    asyncio.create_task(_sync_loop())     # keeps chores reconciled with Cozi + sheet

@app.on_event("shutdown")
async def shutdown_event():
    global cozi_client
    if cozi_client and hasattr(cozi_client, '_session'):
        try:
            await cozi_client._session.close()
            print("✅ Session closed on shutdown")
        except:
            pass

# ====================== RELOGIN PAGE (browser friendly) ======================
@app.get("/relogin", response_class=HTMLResponse)
async def relogin_get():
    status = "✅ Logged in" if logged_in else "❌ Not logged in - Click the button below"
    html = f"""
    <html>
    <head><title>Cozi Proxy - Relogin</title></head>
    <body style="font-family:Arial; text-align:center; padding:80px; background:#f8f9fa;">
        <h1>Cozi Proxy Status</h1>
        <p style="font-size:20px;"><strong>{status}</strong></p>
        <button onclick="retry()" style="font-size:20px; padding:18px 50px; background:#ff9800; color:white; border:none; border-radius:12px; cursor:pointer;">
            🔄 Retry Login Now
        </button>
        <p id="result" style="margin-top:30px; font-size:18px; min-height:30px;"></p>
        <script>
        async function retry() {{
            const res = await fetch('/relogin', {{ method: 'POST' }});
            const data = await res.json();
            document.getElementById('result').innerHTML = '<strong>' + data.message + '</strong>';
            if (data.status === 'success') setTimeout(() => location.reload(), 1000);
        }}
        </script>
    </body>
    </html>
    """
    return html

@app.post("/relogin")
async def relogin_post():
    global logged_in
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Client not initialized")
    try:
        await cozi_client.login()
        logged_in = True
        return {"status": "success", "message": "✅ Login successful!"}
    except Exception as e:
        logged_in = False
        return {"status": "error", "message": f"❌ Login failed: {str(e)}"}

# ====================== STATUS ======================
@app.get("/status")
async def status():
    return {
        "logged_in": logged_in,
        "message": "Ready - lists should load" if logged_in else "Not logged in - go to /relogin"
    }

# ====================== SERVE YOUR HTML ======================
@app.get("/", response_class=HTMLResponse)
async def serve_html():
    try:
        with open("/cozi_proxy/cozi-interface.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>cozi-interface.html not found in add-on</h1>")

# ====================== YOUR ORIGINAL ENDPOINTS ======================
class AddItemRequest(BaseModel):
    list_id: str
    item_text: str
    item_pos: int

class EditItemRequest(BaseModel):
    list_id: str
    item_id: str
    item_text: str

class MarkItemRequest(BaseModel):
    list_id: str
    item_id: str
    status: str

class RemoveItemsRequest(BaseModel):
    list_id: str
    item_ids: list[str]

class ReorderRequest(BaseModel):
    list_id: str
    list_title: str
    items_list: list
    list_type: str

class AddListRequest(BaseModel):
    list_title: str
    list_type: str = "shopping"

class ReorderListsRequest(BaseModel):
    lists: list


@app.get("/lists")
async def get_lists():
    if not cozi_client or not logged_in:
        raise HTTPException(status_code=503, detail="Not logged in. Go to /relogin first")
    try:
        lists = await cozi_client.get_lists()
        return {"lists": lists}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/add_item")
async def add_item(req: AddItemRequest):
    if not cozi_client or not logged_in:
        raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.add_item(req.list_id, req.item_text, req.item_pos)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/edit_item")
async def edit_item(req: EditItemRequest):
    if not cozi_client or not logged_in:
        raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.edit_item(req.list_id, req.item_id, req.item_text)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/mark_item")
async def mark_item(req: MarkItemRequest):
    if not cozi_client or not logged_in:
        raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.mark_item(req.list_id, req.item_id, req.status)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/remove_items")
async def remove_items(req: RemoveItemsRequest):
    if not cozi_client or not logged_in:
        raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.remove_items(req.list_id, req.item_ids)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/reorder_items")
async def reorder_items(req: ReorderRequest):
    if not cozi_client or not logged_in:
        raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.reorder_list(req.list_id, req.list_title, req.items_list, req.list_type)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/add_list")
async def add_list(req: AddListRequest):
    if not cozi_client or not logged_in:
        raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.add_list(req.list_title, req.list_type)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/reorder_lists")
async def reorder_lists(req: ReorderListsRequest):
    if not cozi_client or not logged_in:
        raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.reorder_lists(req.lists)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

# ====================== CHORES / LEDPOINTS ======================
# Local JSON is the store; Cozi lists and an optional published-CSV spreadsheet are
# additional INPUT channels that stay reconciled with it. Chores are matched across
# all three sources by normalised name, so the same chore never lands twice.
#
# FREQUENCY ROTATION: the board is re-posted once a week (anchored to Monday). A
# chore only goes back up once its interval has elapsed since it was last completed,
# so a monthly job done on the 3rd stays off the board until the 2nd of next month.
# The spreadsheet is the source of truth for each chore's frequency; the "last done"
# dates live here because only this service sees claims as they happen.
import re
import csv
import io
import datetime

CHORES_DB = "/data/chores.json"
_chores_lock = asyncio.Lock()

COZI_LISTS = {"chores required": "required", "chores optional": "optional"}
SYNC_EVERY = 300  # seconds

FREQ_DAYS = {"weekly": 7, "bi-weekly": 14, "biweekly": 14, "monthly": 30}
FREQ_CANON = {"weekly": "weekly", "bi-weekly": "bi-weekly", "biweekly": "bi-weekly",
              "monthly": "monthly"}
DEFAULT_FREQ = "weekly"


def _freq(value):
    v = re.sub(r"[^a-z]", "", (value or "").lower())
    if v.startswith("bi") or v.startswith("every2") or v.startswith("fort"):
        return "bi-weekly"
    if v.startswith("mo"):
        return "monthly"
    if v.startswith("we") or v.startswith("每"):
        return "weekly"
    return None


def _freq_days(f):
    return FREQ_DAYS.get((f or DEFAULT_FREQ).lower(), 7)


def _today():
    return datetime.date.today()


def _monday(d):
    return d - datetime.timedelta(days=d.weekday())


def _parse_date(s):
    try:
        return datetime.date.fromisoformat(s)
    except Exception:
        return None


def _chores_default():
    return {"target": 100, "chores": [], "log": {"ian": [], "evan": []}, "week_start": None,
            "next_id": 1, "sheet_url": "", "last_sync": None, "sync_error": "", "sync_note": "",
            "history": [], "rejections": [], "schema": 0}


def _chores_read():
    if not os.path.exists(CHORES_DB):
        return _chores_default()
    try:
        with open(CHORES_DB, "r") as f:
            d = json.load(f)
        base = _chores_default()
        base.update(d or {})
        base.setdefault("log", {}).setdefault("ian", [])
        base["log"].setdefault("evan", [])
        for c in base.get("chores", []):          # migrate older rows
            c.setdefault("kind", "required")
            c.setdefault("source", "dashboard")
            c.setdefault("frequency", DEFAULT_FREQ)
            c.setdefault("last_done", None)
            c.setdefault("posted", True)
            c.setdefault("from_sheet", False)
        return base
    except Exception:
        return _chores_default()


def _chores_write(d):
    tmp = CHORES_DB + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, CHORES_DB)


def _norm(name):
    """Match key across Cozi / sheet / dashboard: case- and space-insensitive."""
    return re.sub(r"\s+", " ", (name or "").strip().lower())


_PTS_RE = re.compile(r"\[\s*(\d+)\s*\]")


def _parse_item(text):
    """`Unload dishwasher [10] Put everything away` -> (name, 10, description)."""
    text = (text or "").strip()
    m = _PTS_RE.search(text)
    if not m:
        return text, 0, ""
    return (text[:m.start()].strip(" -:–—"),
            int(m.group(1)),
            text[m.end():].strip(" -:–—"))


COZI_MAX = 250          # Cozi silently truncates list-item text around here


def _fmt_item(c):
    """Inverse of _parse_item, for pushing dashboard-added chores into Cozi.
    Trimmed on a word boundary so Cozi's own truncation never cuts mid-word."""
    s = "%s [%d]" % (c["name"], int(c.get("points", 0)))
    desc = (c.get("description") or "").strip()
    if desc:
        room = COZI_MAX - len(s) - 1
        if len(desc) > room:
            desc = desc[:room].rsplit(" ", 1)[0].rstrip(" ,.;—-") + "…"
        s += " " + desc
    return s


def _merge_desc(old, new):
    """Cozi caps item text, so the description that comes back can be a truncated
    prefix of what we hold. Never let that shorter copy overwrite the full one."""
    old, new = (old or "").strip(), (new or "").strip()
    if not new:
        return old
    if old and len(new) < len(old):
        stem = new.rstrip("…").rstrip()
        if old.startswith(stem[:max(1, len(stem) - 2)]):
            return old
    return new


def _due_date(c):
    """When this chore is next allowed on the board."""
    ld = _parse_date(c.get("last_done") or "")
    if not ld:
        return None                      # never done -> eligible now
    return ld + datetime.timedelta(days=_freq_days(c.get("frequency")))


def _is_due(c, on=None):
    d = _due_date(c)
    return True if d is None else d <= (on or _today())


def _repost(d, on=None):
    """Decide what sits on the board. Unfinished chores stay up; completed ones
    come back only once their frequency interval has elapsed."""
    on = on or _today()
    for c in d["chores"]:
        # a chore sent back by a parent stays up until it's redone
        c["posted"] = True if c.get("rejected") else _is_due(c, on)


def _gate(chores):
    """Optional chores stay locked until every POSTED required chore is claimed."""
    req = [c for c in chores
           if c.get("kind", "required") == "required" and c.get("posted", True)]
    left = [c for c in req if not c.get("done_by")]
    return {"required_total": len(req), "required_left": len(left),
            "optional_unlocked": len(left) == 0}


def _roll_week(d, on=None):
    """Close out the week: stamp completions, clear the board, re-post what's due."""
    on = on or _today()
    done = [c for c in d["chores"] if c.get("done_by")]
    for c in done:
        c["last_done"] = on.isoformat()
    if done:
        d.setdefault("history", []).append({
            "week_start": d.get("week_start"),
            "closed": on.isoformat(),
            "totals": {k: sum(int(e.get("points", 0)) for e in v) for k, v in d["log"].items()},
            "completed": [{"name": c["name"], "by": c["done_by"],
                           "points": c.get("points", 0)} for c in done],
        })
        d["history"] = d["history"][-52:]          # keep a year
    for c in d["chores"]:
        c["done_by"] = None
        c.pop("rejected", None)
    d["log"] = {"ian": [], "evan": []}
    d["week_start"] = _monday(on).isoformat()
    _repost(d, on)
    return len(done)


def _maybe_roll(d):
    """Auto-advance on Monday; catches up if the box was off."""
    today = _today()
    this_monday = _monday(today)
    ws = _parse_date(d.get("week_start") or "")
    if ws is None or ws < this_monday:
        _roll_week(d, today)
        return True
    return False


# ---------------------------------------------------------------- sync sources
async def _from_cozi():
    """{norm_name: chore-ish} from the two Cozi lists, plus the list ids we found.
    Cozi item text can't carry a frequency, so those entries leave it as None and
    the reconcile step keeps whatever the sheet (or an earlier add) already set."""
    out, list_ids, item_ids = {}, {}, {}
    if not cozi_client or not logged_in:
        return out, list_ids, item_ids, "Cozi not connected"
    lists = await cozi_client.get_lists()
    for l in (lists or []):
        kind = COZI_LISTS.get((l.get("title") or "").strip().lower())
        if not kind:
            continue
        list_ids[kind] = l.get("listId") or l.get("list_id")
        for it in (l.get("items") or []):
            if it.get("itemType") == "header":
                continue
            name, pts, desc = _parse_item(it.get("text"))
            if not name:
                continue
            key = _norm(name)
            out[key] = {"name": name, "points": pts, "description": desc,
                        "kind": kind, "source": "cozi", "frequency": None}
            item_ids[key] = (list_ids[kind], it.get("itemId") or it.get("item_id"))
    return out, list_ids, item_ids, ""


async def _from_sheet(url):
    """{norm_name: chore-ish} from a Google Sheet published as CSV."""
    out = {}
    if not url:
        return out, ""
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return out, "sheet HTTP %d" % r.status
                body = await r.text()
    except Exception as ex:
        return out, "sheet fetch failed: %s" % str(ex)[:80]

    try:
        body = body.lstrip("﻿")                # Google prepends a BOM
        rows = list(csv.DictReader(io.StringIO(body)))
    except Exception as ex:
        return out, "sheet parse failed: %s" % str(ex)[:80]
    if not rows:
        return out, ""

    cols = _map_columns(rows[0].keys())
    if "name" not in cols:
        return out, "sheet: no chore-name column found"

    def val(row, field):
        return (row.get(cols[field]) or "").strip() if field in cols else ""

    for row in rows:
        name = val(row, "name")
        if not name:
            continue
        try:
            pts = int(float(val(row, "points") or 0))
        except ValueError:
            pts = 0
        kind = "optional" if val(row, "kind").lower().startswith("o") else "required"
        out[_norm(name)] = {"name": name, "points": pts,
                            "description": val(row, "description"),
                            "kind": kind, "source": "sheet",
                            "frequency": _freq(val(row, "frequency"))}
    return out, ""


def _map_columns(fieldnames):
    """Map whatever the family typed as headers onto our fields.

    Real headers in use are things like "Chore Title", "Chore Steps/Details" and
    "Type (Required / Optional)", so match on substrings rather than exact names.
    Order matters: "chore" appears in BOTH the title and the steps column, so the
    more specific patterns get to claim their column first.
    """
    heads = [h for h in fieldnames if h]
    cols, taken = {}, set()

    def claim(field, *needles):
        for h in heads:
            if h in taken:
                continue
            lh = h.strip().lower()
            if any(n in lh for n in needles):
                cols[field] = h
                taken.add(h)
                return

    claim("frequency", "frequen", "how often", "repeat", "cadence", "schedule")
    claim("description", "detail", "step", "descri", "how", "note", "instruction")
    claim("points", "point", "pts", "value", "worth")
    claim("kind", "type", "kind", "required", "optional", "categ")
    claim("name", "chore", "task", "job", "title", "name")
    return cols


_sync_gate = asyncio.Lock()


async def _sync_chores():
    """Serialised so concurrent callers can't each push the same new chore."""
    async with _sync_gate:
        return await _do_sync()


async def _do_sync():
    """Reconcile local chores with Cozi + sheet. Never drops a claimed chore."""
    cozi_items, list_ids, cozi_item_ids, cozi_err = await _from_cozi()
    d0 = _chores_read()
    sheet_items, sheet_err = await _from_sheet(d0.get("sheet_url") or "")

    # Cozi wins on the text fields (it's the shared list the family edits), but the
    # sheet keeps ownership of frequency since Cozi can't express one.
    sheet_ok = bool(sheet_items) and not sheet_err
    ext = dict(sheet_items)
    for k, v in cozi_items.items():
        if k in ext:
            v = dict(v)
            v["frequency"] = ext[k].get("frequency")
        ext[k] = v

    push = []
    async with _chores_lock:
        d = _chores_read()
        local = {}
        for c in d["chores"]:
            local.setdefault(_norm(c["name"]), c)

        for key, e in ext.items():
            c = local.get(key)
            if c:
                c.update({"name": e["name"], "points": e["points"],
                          "description": _merge_desc(c.get("description"), e["description"]),
                          "kind": e["kind"]})
                if e.get("frequency"):
                    c["frequency"] = e["frequency"]
                if key in sheet_items:
                    c["from_sheet"] = True
                if c.get("source") == "dashboard":
                    c["source"] = e["source"]
            else:
                cid = d.get("next_id", 1)
                d["next_id"] = cid + 1
                nc = {"id": cid, "name": e["name"], "points": e["points"],
                      "description": e["description"], "kind": e["kind"],
                      "frequency": e.get("frequency") or DEFAULT_FREQ,
                      "last_done": None, "posted": True,
                      "from_sheet": key in sheet_items,
                      "done_by": None, "source": e["source"]}
                d["chores"].append(nc)
                local[key] = nc

        # One-time: everything currently held originated from the seeded catalog that
        # the spreadsheet now mirrors, so hand ownership of it to the sheet.
        if d.get("schema", 0) < 2:
            if sheet_ok:
                for c in d["chores"]:
                    c["from_sheet"] = True
                d["schema"] = 2

        drop_from_cozi = []
        if not cozi_err:
            keep = []
            for c in d["chores"]:
                key = _norm(c["name"])
                # a chore the sheet introduced and has since dropped (a rename counts)
                # goes away even though Cozi still mirrors the old name
                sheet_dropped = sheet_ok and c.get("from_sheet") and key not in sheet_items
                gone = c.get("source") in ("cozi", "sheet") and key not in ext
                if (gone or sheet_dropped) and not c.get("done_by"):
                    if key in cozi_item_ids:
                        drop_from_cozi.append(cozi_item_ids[key])
                    continue
                keep.append(c)
            d["chores"] = keep

        # Only push what Cozi doesn't already have. Without this the same chore is
        # re-pushed on every sync until the read-back flips its source, which piles
        # up hundreds of duplicate list items.
        for c in d["chores"]:
            if (c.get("source") == "dashboard"
                    and list_ids.get(c.get("kind", "required"))
                    and _norm(c["name"]) not in cozi_items):
                push.append((list_ids[c["kind"]], _fmt_item(c)))

        rolled = _maybe_roll(d)
        if not rolled:
            _repost(d)
        d["last_sync"] = datetime.datetime.now().isoformat(timespec="seconds")
        d["sync_error"] = cozi_err or sheet_err or ""
        d["sync_note"] = "cozi:%d sheet:%d" % (len(cozi_items), len(sheet_items))
        _chores_write(d)

    for list_id, item_id in drop_from_cozi:
        try:
            await cozi_client.remove_items(list_id, [item_id])
        except Exception:
            pass
    for list_id, text in push:
        try:
            await cozi_client.add_item(list_id, text, 0)
        except Exception:
            pass
    return {"cozi": len(cozi_items), "sheet": len(sheet_items), "pushed": len(push),
            "removed": len(drop_from_cozi), "rolled": rolled,
            "error": cozi_err or sheet_err or ""}


async def _sync_loop():
    while True:
        try:
            await _sync_chores()
        except Exception as ex:
            print("chores sync failed:", ex)
        await asyncio.sleep(SYNC_EVERY)


class ChoreAdd(BaseModel):
    name: str
    points: int = 0
    description: str = ""
    kind: str = "required"
    frequency: str = DEFAULT_FREQ

class ChoreEdit(BaseModel):
    id: int
    name: str | None = None
    points: int | None = None
    description: str | None = None
    kind: str | None = None
    frequency: str | None = None

class ChoreId(BaseModel):
    id: int

class ChoreClaim(BaseModel):
    id: int
    kid: str

class ChoreTarget(BaseModel):
    target: int

class ChoreReject(BaseModel):
    id: int
    comment: str = ""

class SheetUrl(BaseModel):
    url: str


def _decorate(c):
    out = dict(c)
    dd = _due_date(c)
    out["next_due"] = dd.isoformat() if dd else None
    out["days_until_due"] = max(0, (dd - _today()).days) if dd else 0
    return out


@app.get("/chores")
async def chores_get():
    d = _chores_read()
    totals = {k: sum(int(e.get("points", 0)) for e in v) for k, v in d["log"].items()}
    chores = [_decorate(c) for c in d["chores"]]
    out = {"target": d.get("target", 100), "chores": chores, "log": d["log"],
           "totals": totals, "week_start": d.get("week_start"),
           "sheet_url": d.get("sheet_url", ""), "last_sync": d.get("last_sync"),
           "sync_error": d.get("sync_error", ""), "sync_note": d.get("sync_note", ""),
           "today": _today().isoformat(),
           "frequencies": ["weekly", "bi-weekly", "monthly"]}
    out.update(_gate(d["chores"]))
    return out


@app.post("/chores/add")
async def chores_add(req: ChoreAdd):
    async with _chores_lock:
        d = _chores_read()
        cid = d.get("next_id", 1)
        d["chores"].append({"id": cid, "name": req.name.strip(), "points": int(req.points),
                            "description": (req.description or "").strip(),
                            "kind": "optional" if req.kind == "optional" else "required",
                            "frequency": _freq(req.frequency) or DEFAULT_FREQ,
                            "last_done": None, "posted": True,
                            "done_by": None, "source": "dashboard"})
        d["next_id"] = cid + 1
        _chores_write(d)
    return {"status": "ok", "id": cid}


@app.post("/chores/edit")
async def chores_edit(req: ChoreEdit):
    async with _chores_lock:
        d = _chores_read()
        for c in d["chores"]:
            if c["id"] == req.id:
                if req.name is not None: c["name"] = req.name.strip()
                if req.points is not None: c["points"] = int(req.points)
                if req.description is not None: c["description"] = req.description.strip()
                if req.kind is not None:
                    c["kind"] = "optional" if req.kind == "optional" else "required"
                if req.frequency is not None:
                    c["frequency"] = _freq(req.frequency) or DEFAULT_FREQ
        _repost(d)
        _chores_write(d)
    return {"status": "ok"}


@app.post("/chores/delete")
async def chores_delete(req: ChoreId):
    async with _chores_lock:
        d = _chores_read()
        d["chores"] = [c for c in d["chores"] if c["id"] != req.id]
        _chores_write(d)
    return {"status": "ok"}


@app.post("/chores/claim")
async def chores_claim(req: ChoreClaim):
    kid = req.kid.lower()
    async with _chores_lock:
        d = _chores_read()
        if kid not in d["log"]:
            d["log"][kid] = []
        target = next((c for c in d["chores"] if c["id"] == req.id), None)
        if not target:
            raise HTTPException(status_code=404, detail="chore not found")
        if target.get("done_by"):
            raise HTTPException(status_code=409, detail="already claimed")
        if not target.get("posted", True):
            dd = _due_date(target)
            raise HTTPException(status_code=425,
                                detail="Not due yet — back on the board %s"
                                       % (dd.strftime("%b %-d") if dd else "soon"))
        gate = _gate(d["chores"])
        if target.get("kind", "required") == "optional" and not gate["optional_unlocked"]:
            raise HTTPException(status_code=423,
                                detail="Finish the %d required chore(s) first"
                                       % gate["required_left"])
        target["done_by"] = kid
        target.pop("rejected", None)          # redone -> clear the parent's note
        d["log"][kid].append({"chore_id": target["id"], "name": target["name"],
                              "points": int(target.get("points", 0))})
        _chores_write(d)
    return {"status": "ok"}


@app.post("/chores/unclaim")
async def chores_unclaim(req: ChoreId):
    async with _chores_lock:
        d = _chores_read()
        for c in d["chores"]:
            if c["id"] == req.id and c.get("done_by"):
                kid = c["done_by"]
                c["done_by"] = None
                d["log"][kid] = [e for e in d["log"].get(kid, []) if e.get("chore_id") != req.id]
        _chores_write(d)
    return {"status": "ok"}


@app.post("/chores/reject")
async def chores_reject(req: ChoreReject):
    """Parent sends a claimed chore back: points come off that kid's total, the
    chore returns to the board, and the comment rides along so the kid sees why."""
    async with _chores_lock:
        d = _chores_read()
        c = next((x for x in d["chores"] if x["id"] == req.id), None)
        if not c:
            raise HTTPException(status_code=404, detail="chore not found")
        kid = c.get("done_by")
        if not kid:
            raise HTTPException(status_code=409, detail="that chore isn't claimed")
        # drop it from the kid's log -> the points go with it
        d["log"][kid] = [e for e in d["log"].get(kid, []) if e.get("chore_id") != req.id]
        c["done_by"] = None
        c["posted"] = True                      # straight back on the board
        c["rejected"] = {
            "kid": kid,
            "comment": (req.comment or "").strip(),
            "at": datetime.datetime.now().isoformat(timespec="minutes"),
        }
        d.setdefault("rejections", []).append({
            "chore": c["name"], "kid": kid, "points": int(c.get("points", 0)),
            "comment": (req.comment or "").strip(),
            "at": datetime.datetime.now().isoformat(timespec="minutes"),
        })
        d["rejections"] = d["rejections"][-100:]
        _chores_write(d)
    return {"status": "ok", "kid": kid, "points_removed": int(c.get("points", 0))}


@app.post("/chores/clear_rejection")
async def chores_clear_rejection(req: ChoreId):
    async with _chores_lock:
        d = _chores_read()
        for c in d["chores"]:
            if c["id"] == req.id:
                c.pop("rejected", None)
        _chores_write(d)
    return {"status": "ok"}


@app.post("/chores/target")
async def chores_target(req: ChoreTarget):
    async with _chores_lock:
        d = _chores_read()
        d["target"] = int(req.target)
        _chores_write(d)
    return {"status": "ok"}


@app.post("/chores/sheeturl")
async def chores_sheeturl(req: SheetUrl):
    async with _chores_lock:
        d = _chores_read()
        d["sheet_url"] = (req.url or "").strip()
        _chores_write(d)
    return await _sync_chores()


@app.post("/chores/sync")
async def chores_sync():
    return await _sync_chores()


@app.get("/chores/history")
async def chores_history():
    d = _chores_read()
    return {"history": d.get("history", []), "rejections": d.get("rejections", [])}


@app.post("/chores/newweek")
async def chores_newweek():
    async with _chores_lock:
        d = _chores_read()
        n = _roll_week(d)
        _chores_write(d)
    return {"status": "ok", "stamped": n, "week_start": d.get("week_start")}

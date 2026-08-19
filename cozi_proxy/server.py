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

# ====================== STANDALONE CHORES / LEDPOINTS (local JSON, no Cozi) ======================
CHORES_DB = "/data/chores.json"
_chores_lock = asyncio.Lock()

def _chores_default():
    return {"target": 100, "chores": [], "log": {"ian": [], "evan": []}, "week_start": None, "next_id": 1}

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
        return base
    except Exception:
        return _chores_default()

def _chores_write(d):
    tmp = CHORES_DB + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, CHORES_DB)


class ChoreAdd(BaseModel):
    name: str
    points: int = 0
    description: str = ""

class ChoreEdit(BaseModel):
    id: int
    name: str | None = None
    points: int | None = None
    description: str | None = None

class ChoreId(BaseModel):
    id: int

class ChoreClaim(BaseModel):
    id: int
    kid: str

class ChoreTarget(BaseModel):
    target: int


@app.get("/chores")
async def chores_get():
    d = _chores_read()
    totals = {k: sum(int(e.get("points", 0)) for e in v) for k, v in d["log"].items()}
    return {"target": d.get("target", 100), "chores": d["chores"], "log": d["log"], "totals": totals,
            "week_start": d.get("week_start")}

@app.post("/chores/add")
async def chores_add(req: ChoreAdd):
    async with _chores_lock:
        d = _chores_read()
        cid = d.get("next_id", 1)
        d["chores"].append({"id": cid, "name": req.name.strip(), "points": int(req.points),
                            "description": (req.description or "").strip(), "done_by": None})
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
        target["done_by"] = kid
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

@app.post("/chores/target")
async def chores_target(req: ChoreTarget):
    async with _chores_lock:
        d = _chores_read()
        d["target"] = int(req.target)
        _chores_write(d)
    return {"status": "ok"}

@app.post("/chores/newweek")
async def chores_newweek():
    import datetime
    async with _chores_lock:
        d = _chores_read()
        d["log"] = {"ian": [], "evan": []}
        for c in d["chores"]:
            c["done_by"] = None
        d["week_start"] = datetime.date.today().isoformat()
        _chores_write(d)
    return {"status": "ok"}

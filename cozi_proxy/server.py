import os
import json
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from cozi import Cozi
from cozi.exceptions import InvalidLoginException, CoziException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

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

# ====================== AUTO LOGIN WITH ROBUST CLEANUP ======================
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

    # Clean up any previous session
    if cozi_client and hasattr(cozi_client, '_session'):
        try:
            await cozi_client._session.close()
        except:
            pass

    cozi_client = Cozi(username, password)

    for attempt in range(5):
        try:
            await cozi_client.login()
            print("✅ Login successful!")
            logged_in = True
            return
        except Exception as e:
            print(f"❌ Login attempt {attempt+1}/5 failed: {e}")
            await asyncio.sleep(12)

    print("⚠️ All login attempts failed. Use the /relogin button to try again.")

@app.on_event("startup")
async def startup_event():
    await auto_login()

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
        "message": "Ready" if logged_in else "Not logged in - click Relogin"
    }

# ====================== SERVE HTML ======================
@app.get("/", response_class=HTMLResponse)
async def serve_html():
    try:
        with open("/cozi_proxy/cozi-interface.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>cozi-interface.html not found</h1>")

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
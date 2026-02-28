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

# ====================== IMPROVED AUTO LOGIN ======================
async def auto_login():
    global cozi_client, logged_in
    options_path = "/data/options.json"
    print("=== Cozi Proxy: Auto-login starting ===")

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

    cozi_client = Cozi(username, password)

    for attempt in range(5):  # Try 5 times
        try:
            await cozi_client.login()
            print("✅ Login successful!")
            logged_in = True
            return
        except Exception as e:
            print(f"❌ Login attempt {attempt+1}/5 failed: {e}")
            await asyncio.sleep(10)  # Wait longer between attempts

    print("⚠️ All login attempts failed. Proxy is running - use /relogin to try again later.")


@app.on_event("startup")
async def startup_event():
    await auto_login()


# ====================== SERVE HTML ======================
@app.get("/", response_class=HTMLResponse)
async def serve_html():
    try:
        with open("/cozi_proxy/cozi-interface.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>cozi-interface.html not found</h1>")


# ====================== STATUS & RELOGIN ======================
@app.get("/status")
async def status():
    return {
        "logged_in": logged_in,
        "cozi_client_ready": cozi_client is not None
    }

@app.post("/relogin")
async def relogin():
    global logged_in
    if not cozi_client:
        raise HTTPException(status_code=400, detail="No client initialized")
    try:
        await cozi_client.login()
        logged_in = True
        return {"status": "success", "message": "Logged in successfully"}
    except Exception as e:
        logged_in = False
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


# ====================== YOUR ORIGINAL ENDPOINTS (unchanged) ======================
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
        raise HTTPException(status_code=503, detail="Not logged in. Try /relogin first")
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
    if not cozi_client or not logged_in: raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.edit_item(req.list_id, req.item_id, req.item_text)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/mark_item")
async def mark_item(req: MarkItemRequest):
    if not cozi_client or not logged_in: raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.mark_item(req.list_id, req.item_id, req.status)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/remove_items")
async def remove_items(req: RemoveItemsRequest):
    if not cozi_client or not logged_in: raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.remove_items(req.list_id, req.item_ids)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/reorder_items")
async def reorder_items(req: ReorderRequest):
    if not cozi_client or not logged_in: raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.reorder_list(req.list_id, req.list_title, req.items_list, req.list_type)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/add_list")
async def add_list(req: AddListRequest):
    if not cozi_client or not logged_in: raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.add_list(req.list_title, req.list_type)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/reorder_lists")
async def reorder_lists(req: ReorderListsRequest):
    if not cozi_client or not logged_in: raise HTTPException(status_code=503, detail="Not logged in")
    try:
        await cozi_client.reorder_lists(req.lists)
        return {"status": "ok"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
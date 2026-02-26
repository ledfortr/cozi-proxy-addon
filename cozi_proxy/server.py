import os
import json
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from cozi import Cozi
from cozi.exceptions import InvalidLoginException, CoziException

app = FastAPI()

# Global Cozi client instance
cozi_client: Cozi | None = None


# -----------------------------
# Auto-login on startup
# -----------------------------
async def auto_login():
    global cozi_client

    options_path = "/data/options.json"
    print("=== Cozi Proxy: Auto-login starting ===")
    print(f"Options file exists: {os.path.exists(options_path)}")

    if not os.path.exists(options_path):
        print("Error: options.json not found!")
        return

    with open(options_path, "r") as options_file:
        options = json.load(options_file)
        username = options.get("username")
        password = options.get("password")

        if not username or not password:
            print("Error: Username or password not found in options.json!")
            return

        print("Logging in with username:", username)

        cozi_client = Cozi(username, password)

        try:
            await cozi_client.login()
            print("Login successful")
        except InvalidLoginException:
            print("Invalid login credentials")
        except CoziException as ex:
            print("Error logging in:", str(ex))


@app.on_event("startup")
async def startup_event():
    await auto_login()


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
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Not logged in")
    try:
        lists = await cozi_client.get_lists()
        return {"lists": lists}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/add_item")
async def add_item(req: AddItemRequest):
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Not logged in")
    try:
        await cozi_client.add_item(req.list_id, req.item_text, req.item_pos)
        return {"status": "ok"}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/edit_item")
async def edit_item(req: EditItemRequest):
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Not logged in")
    try:
        await cozi_client.edit_item(req.list_id, req.item_id, req.item_text)
        return {"status": "ok"}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/mark_item")
async def mark_item(req: MarkItemRequest):
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Not logged in")
    try:
        await cozi_client.mark_item(req.list_id, req.item_id, req.status)
        return {"status": "ok"}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/remove_items")
async def remove_items(req: RemoveItemsRequest):
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Not logged in")
    try:
        await cozi_client.remove_items(req.list_id, req.item_ids)
        return {"status": "ok"}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/reorder_items")
async def reorder_items(req: ReorderRequest):
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Not logged in")
    try:
        await cozi_client.reorder_list(
            req.list_id,
            req.list_title,
            req.items_list,
            req.list_type
        )
        return {"status": "ok"}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/add_list")
async def add_list(req: AddListRequest):
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Not logged in")
    try:
        await cozi_client.add_list(req.list_title, req.list_type)
        return {"status": "ok"}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/reorder_lists")
async def reorder_lists(req: ReorderListsRequest):
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Not logged in")
    try:
        await cozi_client.reorder_lists(req.lists)
        return {"status": "ok"}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))
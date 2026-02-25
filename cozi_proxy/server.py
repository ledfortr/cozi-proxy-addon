from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from cozi import Cozi
from cozi.exceptions import InvalidLoginException, CoziException

app = FastAPI()

class LoginRequest(BaseModel):
    username: str
    password: str

class ItemRequest(BaseModel):
    list_id: str
    item_text: str
    item_pos: int = 0

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

cozi_client: Cozi | None = None

@app.post("/login")
async def login(req: LoginRequest):
    global cozi_client
    cozi_client = Cozi(req.username, req.password)
    try:
        await cozi_client.login()
    except InvalidLoginException:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"status": "ok"}

@app.get("/lists")
async def get_lists():
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Not logged in")
    try:
        lists = await cozi_client.get_lists()
        return {"lists": lists}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))

@app.get("/persons")
async def get_persons():
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Not logged in")
    try:
        persons = await cozi_client.get_persons()
        return {"persons": persons}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))

@app.post("/add_item")
async def add_item(req: ItemRequest):
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
        await cozi_client.reorder_list(req.list_id, req.list_title, req.items_list, req.list_type)
        return {"status": "ok"}
    except CoziException as ex:
        raise HTTPException(status_code=500, detail=str(ex))
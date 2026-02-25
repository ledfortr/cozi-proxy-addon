import os
import asyncio
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from cozi import Cozi

COZI_EMAIL = os.getenv("COZI_EMAIL")
COZI_PASSWORD = os.getenv("COZI_PASSWORD")

if not COZI_EMAIL or not COZI_PASSWORD:
    raise RuntimeError("COZI_EMAIL and COZI_PASSWORD must be set as environment variables")

app = FastAPI(title="Cozi Proxy API")

# Global Cozi client
cozi_client: Optional[Cozi] = None


def get_cozi() -> Cozi:
    """Ensure we have a logged-in Cozi client."""
    global cozi_client
    if cozi_client is None:
        cozi_client = Cozi(COZI_EMAIL, COZI_PASSWORD)
        asyncio.run(cozi_client.login())
    return cozi_client


@app.on_event("startup")
async def startup_event():
    """Login once at startup and keep the session."""
    global cozi_client
    cozi_client = Cozi(COZI_EMAIL, COZI_PASSWORD)
    await cozi_client.login()


class AddListRequest(BaseModel):
    list_title: str
    list_type: str  # "shopping" or "todo"


class AddItemRequest(BaseModel):
    item_text: str
    item_pos: int = 0  # 0 = top of list


class EditItemRequest(BaseModel):
    item_text: str


class MarkItemRequest(BaseModel):
    status: str  # "complete" or "incomplete"


class RemoveItemsRequest(BaseModel):
    item_ids: List[str]


@app.get("/lists")
def get_lists():
    """Return all Cozi lists."""
    try:
        cozi = get_cozi()
        lists = asyncio.run(cozi.get_lists())
        return {"lists": lists}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch lists: {e}")


@app.post("/lists")
def add_list(body: AddListRequest):
    """Create a new list."""
    try:
        cozi = get_cozi()
        result = asyncio.run(cozi.add_list(body.list_title, body.list_type))
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add list: {e}")


@app.delete("/lists/{list_id}")
def remove_list(list_id: str):
    """Remove a list."""
    try:
        cozi = get_cozi()
        result = asyncio.run(cozi.remove_list(list_id))
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove list: {e}")


@app.get("/lists/{list_id}")
def get_list_by_id(list_id: str):
    """
    Return a single list (including items) by ID.
    py-cozi returns all lists; we filter here.
    """
    try:
        cozi = get_cozi()
        lists = asyncio.run(cozi.get_lists())
        for lst in lists:
            if lst.get("listId") == list_id or lst.get("id") == list_id:
                return lst
        raise HTTPException(status_code=404, detail="List not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch list: {e}")


@app.post("/lists/{list_id}/items")
def add_item(list_id: str, body: AddItemRequest):
    """Add an item to a list."""
    try:
        cozi = get_cozi()
        result = asyncio.run(cozi.add_item(list_id, body.item_text, body.item_pos))
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add item: {e}")


@app.post("/lists/{list_id}/items/{item_id}/edit")
def edit_item(list_id: str, item_id: str, body: EditItemRequest):
    """Edit an item in a list."""
    try:
        cozi = get_cozi()
        result = asyncio.run(cozi.edit_item(list_id, item_id, body.item_text))
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to edit item: {e}")


@app.post("/lists/{list_id}/items/{item_id}/mark")
def mark_item(list_id: str, item_id: str, body: MarkItemRequest):
    """Mark an item complete/incomplete."""
    try:
        cozi = get_cozi()
        result = asyncio.run(cozi.mark_item(list_id, item_id, body.status))
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark item: {e}")


@app.post("/lists/{list_id}/items/remove")
def remove_items(list_id: str, body: RemoveItemsRequest):
    """Remove one or more items from a list."""
    try:
        cozi = get_cozi()
        result = asyncio.run(cozi.remove_items(list_id, body.item_ids))
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove items: {e}")
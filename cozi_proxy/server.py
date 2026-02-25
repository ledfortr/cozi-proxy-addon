import os
import asyncio
import httpx
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Cozi Proxy API")

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

COZI_EMAIL = os.getenv("COZI_EMAIL")
COZI_PASSWORD = os.getenv("COZI_PASSWORD")

if not COZI_EMAIL or not COZI_PASSWORD:
    raise RuntimeError("Cozi credentials not set in environment variables.")

BASE_URL = "https://www.cozi.com/api/v1"

# Global session
client: Optional[httpx.AsyncClient] = None
auth_token: Optional[str] = None


# ---------------------------------------------------------
# LOGIN
# ---------------------------------------------------------

async def cozi_login():
    """Log in to Cozi mobile API and store the auth token."""
    global client, auth_token

    if client is None:
        client = httpx.AsyncClient(timeout=20)

    payload = {
        "email": COZI_EMAIL,
        "password": COZI_PASSWORD
    }

    r = await client.post(f"{BASE_URL}/login", json=payload)

    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Cozi login failed")

    data = r.json()

    if "token" not in data:
        raise HTTPException(status_code=500, detail="Cozi login returned no token")

    auth_token = data["token"]


def auth_headers():
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not logged in to Cozi")
    return {"Authorization": f"Bearer {auth_token}"}


# ---------------------------------------------------------
# STARTUP
# ---------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Login once at startup."""
    try:
        await cozi_login()
        print("Cozi login successful.")
    except Exception as e:
        print(f"Startup login failed: {e}")


# ---------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------

class AddListRequest(BaseModel):
    list_title: str
    list_type: str  # "shopping" or "todo"


class AddItemRequest(BaseModel):
    item_text: str
    item_pos: int = 0


class EditItemRequest(BaseModel):
    item_text: str


class MarkItemRequest(BaseModel):
    status: str  # "complete" or "incomplete"


class RemoveItemsRequest(BaseModel):
    item_ids: List[str]


# ---------------------------------------------------------
# LIST ENDPOINTS
# ---------------------------------------------------------

@app.get("/lists")
async def get_lists():
    """Return all Cozi lists."""
    try:
        await cozi_login()
        r = await client.get(f"{BASE_URL}/lists", headers=auth_headers())
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch lists: {e}")


@app.post("/lists")
async def add_list(body: AddListRequest):
    """Create a new list."""
    try:
        await cozi_login()
        payload = {
            "title": body.list_title,
            "type": body.list_type
        }
        r = await client.post(f"{BASE_URL}/lists", json=payload, headers=auth_headers())
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add list: {e}")


@app.delete("/lists/{list_id}")
async def remove_list(list_id: str):
    """Delete a list."""
    try:
        await cozi_login()
        r = await client.delete(f"{BASE_URL}/lists/{list_id}", headers=auth_headers())
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove list: {e}")


@app.get("/lists/{list_id}")
async def get_list_by_id(list_id: str):
    """Return a single list including items."""
    try:
        await cozi_login()
        r = await client.get(f"{BASE_URL}/lists/{list_id}", headers=auth_headers())
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch list: {e}")


# ---------------------------------------------------------
# ITEM ENDPOINTS
# ---------------------------------------------------------

@app.post("/lists/{list_id}/items")
async def add_item(list_id: str, body: AddItemRequest):
    """Add an item to a list."""
    try:
        await cozi_login()
        payload = {
            "text": body.item_text,
            "position": body.item_pos
        }
        r = await client.post(
            f"{BASE_URL}/lists/{list_id}/items",
            json=payload,
            headers=auth_headers()
        )
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add item: {e}")


@app.post("/lists/{list_id}/items/{item_id}/edit")
async def edit_item(list_id: str, item_id: str, body: EditItemRequest):
    """Edit an item."""
    try:
        await cozi_login()
        payload = {"text": body.item_text}
        r = await client.post(
            f"{BASE_URL}/lists/{list_id}/items/{item_id}/edit",
            json=payload,
            headers=auth_headers()
        )
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to edit item: {e}")


@app.post("/lists/{list_id}/items/{item_id}/mark")
async def mark_item(list_id: str, item_id: str, body: MarkItemRequest):
    """Mark item complete/incomplete."""
    try:
        await cozi_login()
        payload = {"status": body.status}
        r = await client.post(
            f"{BASE_URL}/lists/{list_id}/items/{item_id}/mark",
            json=payload,
            headers=auth_headers()
        )
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark item: {e}")


@app.post("/lists/{list_id}/items/remove")
async def remove_items(list_id: str, body: RemoveItemsRequest):
    """Remove multiple items."""
    try:
        await cozi_login()
        payload = {"itemIds": body.item_ids}
        r = await client.post(
            f"{BASE_URL}/lists/{list_id}/items/remove",
            json=payload,
            headers=auth_headers()
        )
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove items: {e}")
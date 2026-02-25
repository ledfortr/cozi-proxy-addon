from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
import uvicorn

app = FastAPI()

COZI_EMAIL = os.getenv("COZI_EMAIL")
COZI_PASSWORD = os.getenv("COZI_PASSWORD")

BASE_URL = "https://api.cozi.com/api/v1"


def cozi_login():
    """Authenticate with Cozi and return a session token."""
    payload = {
        "email": COZI_EMAIL,
        "password": COZI_PASSWORD
    }

    r = requests.post(f"{BASE_URL}/login", json=payload)
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Cozi credentials")

    return r.json().get("token")


def cozi_headers():
    """Return headers including auth token."""
    token = cozi_login()
    return {"Authorization": f"Bearer {token}"}


@app.get("/lists")
def get_lists():
    """Return all Cozi to-do lists."""
    r = requests.get(f"{BASE_URL}/lists", headers=cozi_headers())
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch lists")
    return r.json()


@app.get("/list/{list_id}")
def get_list_items(list_id: str):
    """Return items for a specific list."""
    r = requests.get(f"{BASE_URL}/lists/{list_id}", headers=cozi_headers())
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch list items")
    return r.json()


class AddItem(BaseModel):
    item: str


@app.post("/list/{list_id}/add")
def add_item(list_id: str, data: AddItem):
    """Add an item to a list."""
    payload = {"text": data.item}

    r = requests.post(
        f"{BASE_URL}/lists/{list_id}/items",
        json=payload,
        headers=cozi_headers()
    )

    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to add item")

    return {"status": "ok"}


class RemoveItem(BaseModel):
    item_id: str


@app.post("/list/{list_id}/remove")
def remove_item(list_id: str, data: RemoveItem):
    """Remove an item from a list."""
    r = requests.delete(
        f"{BASE_URL}/lists/{list_id}/items/{data.item_id}",
        headers=cozi_headers()
    )

    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to remove item")

    return {"status": "ok"}


# ⭐ THIS IS THE PART YOU WERE MISSING ⭐
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)

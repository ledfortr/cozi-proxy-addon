import json
import requests
from fastapi import FastAPI
from pathlib import Path

app = FastAPI()
session = requests.Session()
token = None

def load_options():
    options_path = Path("/data/options.json")
    data = json.loads(options_path.read_text())
    return data["cozi_email"], data["cozi_password"]

def login():
    global token
    email, password = load_options()
    r = session.post(
        "https://api.cozi.com/api/v3/login",
        json={"email": email, "password": password}
    )
    r.raise_for_status()
    token = r.json()["token"]
    session.headers.update({"Authorization": f"Bearer {token}"})

@app.on_event("startup")
def startup():
    login()

@app.get("/lists")
def get_lists():
    r = session.get("https://api.cozi.com/api/v3/lists")
    r.raise_for_status()
    return r.json()

@app.get("/list/{list_id}")
def get_list(list_id: str):
    r = session.get(f"https://api.cozi.com/api/v3/lists/{list_id}")
    r.raise_for_status()
    return r.json()

@app.post("/list/{list_id}/add")
def add_item(list_id: str, item: dict):
    r = session.post(
        f"https://api.cozi.com/api/v3/lists/{list_id}/items",
        json={"text": item["item"]}
    )
    r.raise_for_status()
    return r.json()

@app.post("/list/{list_id}/remove")
def remove_item(list_id: str, item: dict):
    item_id = item["item_id"]
    r = session.delete(
        f"https://api.cozi.com/api/v3/lists/{list_id}/items/{item_id}"
    )
    r.raise_for_status()
    return {"status": "ok"}

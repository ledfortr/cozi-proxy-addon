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

# ====================== AUTO LOGIN WITH CLEANUP ======================
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

    print(f"Logging in with: {username}")

    # Clean up any old client
    if cozi_client:
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
            print(f"❌ Attempt {attempt+1}/5 failed: {e}")
            await asyncio.sleep(10)

    print("⚠️ All login attempts failed. Use /relogin later.")

@app.on_event("startup")
async def startup_event():
    await auto_login()

# ====================== MANUAL RELOGIN ======================
@app.post("/relogin")
async def relogin():
    global logged_in
    if not cozi_client:
        raise HTTPException(status_code=400, detail="Client not initialized")
    try:
        await cozi_client.login()
        logged_in = True
        return {"status": "success", "message": "Logged in!"}
    except Exception as e:
        logged_in = False
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

# ====================== SERVE HTML ======================
@app.get("/", response_class=HTMLResponse)
async def serve_html():
    try:
        with open("/cozi_proxy/cozi-interface.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>cozi-interface.html not found</h1>")

# ====================== STATUS ======================
@app.get("/status")
async def status():
    return {
        "logged_in": logged_in,
        "message": "Ready" if logged_in else "Not logged in - click Relogin"
    }

# ====================== YOUR ORIGINAL ENDPOINTS (unchanged) ======================
# ... (all your AddItemRequest, EditItemRequest, etc. classes and endpoints stay exactly the same)

# (Copy-paste all your endpoint classes and functions from your current file here - they are unchanged)

# For brevity I'm not repeating them all - keep them exactly as you have them now.

# Just make sure /lists checks logged_in:
@app.get("/lists")
async def get_lists():
    if not cozi_client or not logged_in:
        raise HTTPException(status_code=503, detail="Not logged in. Go to /relogin first")
    try:
        lists = await cozi_client.get_lists()
        return {"lists": lists}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
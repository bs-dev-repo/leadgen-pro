import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel
import io

from .database import init_db, get_db
from .scraper import run_maps_scraper, stop_scraper, get_scraper_status
from .email_extractor import extract_emails_from_url, extract_emails_from_sites

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent

app = FastAPI(title="LeadGen Pro", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Init DB on startup
@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Database initialized")

# ─── Models ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    keyword: str
    location: str
    max_results: int = 50

class BookmarkRequest(BaseModel):
    lead_id: int
    bookmarked: bool

class ImportRequest(BaseModel):
    websites: list[str]

# ─── Pages ────────────────────────────────────────────────────────────────────

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/results")
async def results_page(request: Request):
    return templates.TemplateResponse("results.html", {"request": request})

@app.get("/bookmarks")
async def bookmarks_page(request: Request):
    return templates.TemplateResponse("bookmarks.html", {"request": request})

@app.get("/history")
async def history_page(request: Request):
    return templates.TemplateResponse("history.html", {"request": request})

@app.get("/import")
async def import_page(request: Request):
    return templates.TemplateResponse("import.html", {"request": request})

# ─── API: Search ──────────────────────────────────────────────────────────────

@app.post("/api/search")
async def start_search(req: SearchRequest, background_tasks: BackgroundTasks):
    if not req.keyword.strip() or not req.location.strip():
        raise HTTPException(400, "Keyword and location are required")
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO searches (keyword, location) VALUES (?, ?)",
        (req.keyword.strip(), req.location.strip())
    )
    db.commit()
    search_id = cursor.lastrowid
    db.close()
    
    background_tasks.add_task(
        run_maps_scraper,
        search_id=search_id,
        keyword=req.keyword.strip(),
        location=req.location.strip(),
        max_results=req.max_results
    )
    
    return {"search_id": search_id, "status": "started"}

@app.get("/api/search/status")
async def search_status():
    return get_scraper_status()

@app.post("/api/search/stop")
async def stop_search():
    stop_scraper()
    return {"status": "stopped"}

# ─── API: Results ─────────────────────────────────────────────────────────────

@app.get("/api/results")
async def get_results(
    search_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    bookmarked_only: bool = False
):
    db = get_db()
    cursor = db.cursor()
    
    conditions = []
    params = []
    
    if search_id:
        conditions.append("search_id = ?")
        params.append(search_id)
    if bookmarked_only:
        conditions.append("bookmarked = 1")
    
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    
    cursor.execute(f"SELECT COUNT(*) FROM leads {where}", params)
    total = cursor.fetchone()[0]
    
    offset = (page - 1) * per_page
    cursor.execute(
        f"SELECT * FROM leads {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    )
    rows = cursor.fetchall()
    db.close()
    
    leads = [dict(row) for row in rows]
    
    return {
        "leads": leads,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page)
    }

@app.get("/api/results/all")
async def get_all_results(search_id: Optional[int] = None):
    db = get_db()
    cursor = db.cursor()
    if search_id:
        cursor.execute("SELECT * FROM leads WHERE search_id = ?", (search_id,))
    else:
        cursor.execute("SELECT * FROM leads")
    rows = cursor.fetchall()
    db.close()
    return [dict(row) for row in rows]

# ─── API: Bookmark ─────────────────────────────────────────────────────────────

@app.post("/api/bookmark")
async def toggle_bookmark(req: BookmarkRequest):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE leads SET bookmarked = ? WHERE id = ?",
        (1 if req.bookmarked else 0, req.lead_id)
    )
    db.commit()
    db.close()
    return {"success": True}

# ─── API: Export ──────────────────────────────────────────────────────────────

@app.get("/api/download")
async def download_excel(
    search_id: Optional[int] = None,
    bookmarked_only: bool = False,
    all_leads: bool = False
):
    db = get_db()
    cursor = db.cursor()
    
    if bookmarked_only:
        cursor.execute("SELECT * FROM leads WHERE bookmarked = 1")
        filename = "bookmarked_leads"
    elif search_id and not all_leads:
        cursor.execute("SELECT * FROM leads WHERE search_id = ?", (search_id,))
        filename = f"search_{search_id}_leads"
    else:
        cursor.execute("SELECT * FROM leads")
        filename = "all_leads"
    
    rows = cursor.fetchall()
    db.close()
    
    data = [dict(row) for row in rows]
    df = pd.DataFrame(data, columns=[
        "id", "search_id", "name", "phone", "address", "website",
        "email", "maps_link", "rating", "reviews", "bookmarked"
    ])
    df = df[["name", "phone", "address", "website", "email", "maps_link", "rating", "reviews"]]
    df.columns = ["Business Name", "Phone", "Address", "Website", "Email", "Google Maps Link", "Rating", "Reviews"]
    
    out_path = f"/tmp/{filename}.xlsx"
    df.to_excel(out_path, index=False, engine="openpyxl")
    
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{filename}.xlsx"
    )

@app.get("/api/download/csv")
async def download_csv(search_id: Optional[int] = None, bookmarked_only: bool = False):
    db = get_db()
    cursor = db.cursor()
    
    if bookmarked_only:
        cursor.execute("SELECT * FROM leads WHERE bookmarked = 1")
        filename = "bookmarked_leads"
    elif search_id:
        cursor.execute("SELECT * FROM leads WHERE search_id = ?", (search_id,))
        filename = f"search_{search_id}_leads"
    else:
        cursor.execute("SELECT * FROM leads")
        filename = "all_leads"
    
    rows = cursor.fetchall()
    db.close()
    
    data = [dict(row) for row in rows]
    df = pd.DataFrame(data)
    out_path = f"/tmp/{filename}.csv"
    df.to_csv(out_path, index=False)
    
    return FileResponse(out_path, media_type="text/csv", filename=f"{filename}.csv")

# ─── API: Search History ───────────────────────────────────────────────────────

@app.get("/api/history")
async def get_history():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT s.*, COUNT(l.id) as lead_count
        FROM searches s
        LEFT JOIN leads l ON s.id = l.search_id
        GROUP BY s.id
        ORDER BY s.date DESC
    """)
    rows = cursor.fetchall()
    db.close()
    return [dict(row) for row in rows]

@app.delete("/api/history/{search_id}")
async def delete_search(search_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM leads WHERE search_id = ?", (search_id,))
    cursor.execute("DELETE FROM searches WHERE id = ?", (search_id,))
    db.commit()
    db.close()
    return {"success": True}

# ─── API: Import ──────────────────────────────────────────────────────────────

@app.post("/api/import")
async def import_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    content = await file.read()
    
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {str(e)}")
    
    # Find website column
    website_col = None
    for col in df.columns:
        if "website" in col.lower() or "url" in col.lower() or "site" in col.lower():
            website_col = col
            break
    if not website_col and len(df.columns) > 0:
        website_col = df.columns[0]
    
    if not website_col:
        raise HTTPException(400, "No website column found")
    
    websites = df[website_col].dropna().astype(str).tolist()
    
    # Create a search entry for this import
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO searches (keyword, location) VALUES (?, ?)",
        (f"Import: {file.filename}", "imported")
    )
    db.commit()
    search_id = cursor.lastrowid
    db.close()
    
    background_tasks.add_task(extract_emails_from_sites, search_id, websites)
    
    return {"search_id": search_id, "count": len(websites), "status": "processing"}

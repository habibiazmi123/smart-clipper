import sqlite3
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import init_db
from app.api import projects, clips, jobs_api

app = FastAPI(title="Smart Clipper Engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(projects.router, prefix="/api")
app.include_router(clips.router, prefix="/api")
app.include_router(jobs_api.router, prefix="/api")

# serve frontend build
frontend_dist = Path(__file__).parent.parent.parent / "desktop" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")


@app.on_event("startup")
def startup():
    db_path = settings.DATA_ROOT / "smartclipper.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}

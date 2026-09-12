import logging
import sqlite3
from pathlib import Path
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import init_db
from app.api import projects, clips, jobs_api, from_hooks

app = FastAPI(title="Smart Clipper Engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(projects.router, prefix="/api")
app.include_router(clips.router, prefix="/api")
app.include_router(jobs_api.router, prefix="/api")
app.include_router(from_hooks.router, prefix="/api")

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/media/{pid}/video")
def serve_video(pid: str):
    from fastapi import HTTPException
    pdir = settings.DATA_ROOT / "projects" / pid / "source"
    videos = list(pdir.glob("*.mp4"))
    if not videos:
        raise HTTPException(404, "No video found")
    return FileResponse(str(videos[0]), media_type="video/mp4")


# serve frontend build with SPA fallback
frontend_dist = Path(__file__).parent.parent.parent / "desktop" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")


@app.on_event("startup")
def startup():
    db_path = settings.DATA_ROOT / "smartclipper.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.close()

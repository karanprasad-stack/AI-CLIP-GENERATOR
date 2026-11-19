"""FastAPI Application Server for AI Gaming Shorts Generator."""

import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.api.router import router as api_router
from backend.app.services.health import HealthChecker

app = FastAPI(
    title="AI Gaming Shorts Generator API",
    description="Production backend API for video analysis, candidate discovery, 9:16 rendering, subtitles, effects, SFX, and publishing packages.",
    version="1.0.0",
)

# CORS configuration for Vite React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API endpoints
app.include_router(api_router)


@app.get("/health")
def health_check():
    """Service health check endpoint with full system telemetry."""
    return HealthChecker.get_full_health()


# Serve React production build if available
frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="static_assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.server:app", host="127.0.0.1", port=8000, reload=True)

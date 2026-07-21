from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from .config import settings
from .database import init_db, check_db_connection, SessionLocal
from .routers import securities, portfolio, dividends, rates, economy, auth
from .load_moex_securities import load_all_securities
from .seed import run_seed
from . import models
import logging
import os

logger = logging.getLogger(__name__)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API для управления портфелем ценных бумаг",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === API Routes (must be registered first) ===
app.include_router(securities.router)
app.include_router(portfolio.router)
app.include_router(dividends.router)
app.include_router(rates.router)
app.include_router(economy.router)
app.include_router(auth.router)


@app.get("/api/health")
def health_check():
    db_ok = check_db_connection()
    return {
        "status": "ok" if db_ok else "error",
        "database": "connected" if db_ok else "disconnected",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.on_event("startup")
def on_startup():
    try:
        init_db()
        logger.info("Database initialized successfully")

        # Seed database with initial data (portfolio, securities from dump)
        run_seed()

        # Load all MOEX securities and ensure currencies in background
        def load_moex():
            db = SessionLocal()
            try:
                import asyncio
                # Skip the heavy full-MOEX load on restarts once the DB is already
                # populated (seed.py + critical securities). This keeps startup fast;
                # the full catalog can still be loaded on demand via
                # POST /api/securities/load-all.
                count = db.query(models.Security).count()
                if count < 100:
                    asyncio.run(load_all_securities(db))
                else:
                    logger.info(f"{count} securities already present, skipping full MOEX load")
                from .load_moex_securities import ensure_currency_securities
                ensure_currency_securities(db)
            except Exception as e:
                logger.warning(f"Could not auto-load MOEX securities: {e}")
            finally:
                db.close()

        import threading
        thread = threading.Thread(target=load_moex, daemon=True)
        thread.start()


    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        logger.error("Make sure PostgreSQL is running and the database exists")


# === Frontend static files (must be registered after API routes) ===
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "frontend")
frontend_path = Path(FRONTEND_DIR).resolve()

if frontend_path.exists():
    # Mount static files (css, js, assets) - only if directories exist
    css_dir = frontend_path / "css"
    js_dir = frontend_path / "js"
    assets_dir = frontend_path / "assets"

    if css_dir.exists():
        app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
    if js_dir.exists():
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(str(frontend_path / "index.html"))

    @app.get("/favicon.svg")
    def serve_favicon():
        return FileResponse(str(frontend_path / "favicon.svg"), media_type="image/svg+xml")

    @app.get("/manifest.json")
    def serve_manifest():
        return FileResponse(str(frontend_path / "manifest.json"), media_type="application/manifest+json")

    @app.api_route("/{full_path:path}", methods=["GET"])
    def serve_static(full_path: str):
        """Serve static files or index.html for SPA routing"""
        # Skip API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = frontend_path / full_path
        if file_path.exists() and file_path.is_file():
            # Determine media type based on extension
            ext = file_path.suffix.lower()
            media_types = {
                '.png': 'image/png',
                '.svg': 'image/svg+xml',
                '.json': 'application/json',
                '.js': 'application/javascript',
                '.css': 'text/css',
                '.html': 'text/html',
            }
            media_type = media_types.get(ext, 'application/octet-stream')
            return FileResponse(str(file_path), media_type=media_type)
        return FileResponse(str(frontend_path / "index.html"), media_type="text/html")

"""
Digital Employee Platform — Web Server entry point.

Usage:
    cd app
    python web/server.py

The server will:
  1. Initialize the SQLite database
  2. Start FastAPI on http://localhost:8000
  3. Serve the React frontend at /
  4. Expose REST API at /api/
  5. Expose WebSocket at /api/conversations/{id}/ws
"""
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from config import WEB_HOST, WEB_PORT, WEB_STATIC_DIR, DOCS_DIR, WEB_BASE_PATH
from web.db.database import init_db
from web.api.agents import router as agents_router
from web.api.chat import router as chat_router
from web.api.knowledge import router as knowledge_router
from web.api.audit import router as audit_router
from web.api.exams import router as exams_router
from web.api.group_chat import router as group_chat_router
from web.api.prompts import router as prompts_router
from web.api.role_prompts import router as role_prompts_router
from web.api.permissions import router as permissions_router
from web.api.test_suites import router as test_suites_router
from web.api.test_runs import router as test_runs_router
from web.api.test_plans import router as test_plans_router
from web.api.browser_skills import router as browser_skills_router

_BASE = WEB_BASE_PATH.rstrip("/")  # e.g. '/digital-employee'


class StripBasePath:
    """
    Strips the base-path prefix from API and WebSocket requests so that
    existing /api/... route handlers work whether the app is accessed directly
    (macOS dev, no nginx) or behind nginx (which already strips the prefix).

    Example: /digital-employee/api/agents  →  /api/agents
             /digital-employee/api/conversations/1/ws  →  /api/conversations/1/ws

    Static-file mounts (/digital-employee/assets/, /digital-employee/docs/) are
    handled separately and are NOT rewritten here.
    """
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._prefix = _BASE + "/api"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path: str = scope.get("path", "")
            if path.startswith(self._prefix):
                new_path = path[len(_BASE):]
                scope = dict(scope)
                scope["path"] = new_path
                scope["raw_path"] = new_path.encode("latin-1")
        await self.app(scope, receive, send)


app = FastAPI(title="Digital Employee Platform", version="1.0.0", docs_url="/api-docs", redoc_url="/api-redoc")
app.add_middleware(StripBasePath)  # must be added before CORSMiddleware

# Allow React dev server (localhost:5173) during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(agents_router,    prefix="/api")
app.include_router(chat_router,      prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(audit_router,     prefix="/api")
app.include_router(exams_router,     prefix="/api")
app.include_router(group_chat_router, prefix="/api")
app.include_router(prompts_router,      prefix="/api")
app.include_router(role_prompts_router, prefix="/api")
app.include_router(permissions_router,  prefix="/api")
app.include_router(test_suites_router,   prefix="/api")
app.include_router(test_runs_router,     prefix="/api")
app.include_router(test_plans_router,    prefix="/api")
app.include_router(browser_skills_router, prefix="/api")

# Health check
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Digital Employee Platform"}


# /docs redirect — handle both with and without the base prefix
@app.get("/docs")
async def docs_redirect():
    return RedirectResponse(url="/docs/", status_code=301)

@app.get(f"{_BASE}/docs")
async def docs_redirect_prefixed():
    return RedirectResponse(url=f"{_BASE}/docs/", status_code=301)

# Serve HTML docs — mount at both paths
# (nginx strips prefix → FastAPI sees /docs/; direct access → /digital-employee/docs/)
if os.path.isdir(DOCS_DIR):
    app.mount("/docs",         StaticFiles(directory=DOCS_DIR, html=True), name="docs")
    app.mount(f"{_BASE}/docs", StaticFiles(directory=DOCS_DIR, html=True), name="docs_prefixed")

# Serve React build (production)
if os.path.isdir(WEB_STATIC_DIR):
    _assets_dir = os.path.join(WEB_STATIC_DIR, "assets")
    # Mount assets at both paths:
    #   /assets/          — nginx mode (nginx strips /digital-employee prefix)
    #   /digital-employee/assets/ — direct macOS mode
    app.mount("/assets",          StaticFiles(directory=_assets_dir), name="assets")
    app.mount(f"{_BASE}/assets",  StaticFiles(directory=_assets_dir), name="assets_prefixed")

    # Redirect bare root to the app
    @app.get("/")
    async def redirect_root():
        return RedirectResponse(url=f"{_BASE}/", status_code=301)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        index_file = os.path.join(WEB_STATIC_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Frontend not built. Run: cd web/frontend && npm install && npm run build"}


if __name__ == "__main__":
    init_db()
    print(f"🚀 Digital Employee Platform")
    print(f"   访问地址：http://localhost:{WEB_PORT}{_BASE}/")
    print(f"   API Docs： http://localhost:{WEB_PORT}{_BASE}/api-docs")
    print(f"   HTML Docs：http://localhost:{WEB_PORT}{_BASE}/docs/")
    uvicorn.run("web.server:app", host=WEB_HOST, port=WEB_PORT, reload=True)

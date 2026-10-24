"""
Runs the API as a live server on http://localhost:8000/ for development. It is the same app the build
writes out, so what you see here is what gets published.

Usage: python -m lsio_hub.serve
"""

import uvicorn

from .app import create_app
from .config import DATA_DIR, SiteConfig
from .fleet import load_fleet
from .store import load_store

if __name__ == "__main__":
    config = SiteConfig()
    uvicorn.run(create_app(load_fleet(load_store(DATA_DIR), config), config), port=8000)

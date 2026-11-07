"""
Vercel's entrypoint (vercel.json: "main:app").

Vercel installs the dependencies but not this project, so the app package
in src/ is not importable on its own there. This file puts src/ on the path
and exposes the FastAPI app. Everywhere else (uvicorn, Docker, tests) the
project is installed and imports app.main directly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from app.main import app  # noqa: E402

__all__ = ["app"]

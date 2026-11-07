"""
Vercel's entrypoint: backend/main.py must work without the project installed.

Vercel's Python builder installs the dependencies into _vendor/ but leaves
the project itself out ("Excluding project package ... from runtime
installation"), then imports the entrypoint from the service root. A
src/app package that only an install makes importable therefore fails
there with "No module named 'app'" (every /api request returned 500 once).

These tests import the entrypoint the same way: site-packages on the path
but its .pth files not processed (python -S), so the editable install of
this project is invisible.
"""

import json
import subprocess
import sys
import sysconfig
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def _import_like_vercel(module: str, tmp_path: Path) -> subprocess.CompletedProcess:
    code = (
        "import importlib, sys\n"
        f"sys.path[:0] = [{str(BACKEND)!r}, {sysconfig.get_paths()['purelib']!r}]\n"
        f"m = importlib.import_module({module!r})\n"
        "from fastapi.testclient import TestClient\n"
        "print(TestClient(m.app).get('/api/health').text)\n"
    )
    return subprocess.run(
        [sys.executable, "-I", "-S", "-c", code],
        cwd=tmp_path,  # nowhere near the code, like a function's working dir
        capture_output=True,
        text=True,
        timeout=60,
        env={"INNGEST_DEV": "1", "PATH": "/usr/bin:/bin"},
    )


def test_the_project_is_not_importable_without_an_install(tmp_path) -> None:
    """The premise: without an install, `app` can't be found from the root."""
    result = _import_like_vercel("src.app.main", tmp_path)
    assert "No module named 'app'" in result.stderr


def test_vercel_entrypoint_serves_the_api_without_an_install(tmp_path) -> None:
    result = _import_like_vercel("main", tmp_path)
    assert result.returncode == 0, result.stderr[-2000:]
    assert json.loads(result.stdout.strip().splitlines()[-1])["status"] == "ok"


def test_vercel_json_points_at_the_entrypoint() -> None:
    config = json.loads((BACKEND.parent / "vercel.json").read_text())
    backend = config["services"]["backend"]
    assert backend["entrypoint"] == "main:app"
    assert "main.py" in backend["functions"]
    assert (BACKEND / "main.py").is_file()

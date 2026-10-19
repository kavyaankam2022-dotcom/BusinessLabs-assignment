#!/usr/bin/env python3
"""Start the three AI Consultant services and verify their shared API links."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK1_DIR = REPO_ROOT / "task1-knowledge-brain"
TASK2_DIR = REPO_ROOT / "task2-inbox-agent"
TASK3_DIR = REPO_ROOT / "task3-meeting-to-scope"


def log(message: str) -> None:
    print(message)


def discover_node_runtime() -> tuple[str | None, str | None]:
    program_files = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")),
    ]
    seen: set[Path] = set()
    for root in program_files:
        if not root.exists():
            continue
        for candidate_dir in [root / "nodejs", root / "nodejs" / "node-v*-win-x64"]:
            for node_path in candidate_dir.glob("node.exe"):
                if node_path not in seen:
                    seen.add(node_path)
                    node_dir = node_path.parent
                    npm_path = node_dir / "npm.cmd"
                    if npm_path.exists():
                        return str(node_path), str(npm_path)
        for node_dir in root.glob("nodejs/node-v*-win-x64"):
            node_path = node_dir / "node.exe"
            npm_path = node_dir / "npm.cmd"
            if node_path.exists() and npm_path.exists():
                return str(node_path), str(npm_path)

    return ensure_command("node"), ensure_command("npm") or ensure_command("npm.cmd")


def ensure_command(name: str) -> str | None:
    return shutil.which(name) or shutil.which(f"{name}.cmd")


def find_python_executable() -> str | None:
    candidates = [
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
        Path(os.environ.get("PYTHON", "")),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return str(candidate)
    return ensure_command("python") or ensure_command("py") or ensure_command("python.exe")


def wait_for_health(url: str, label: str, timeout_seconds: float = 45.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if 200 <= response.status < 500:
                    return payload
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:  # pragma: no cover - exercised at runtime
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"{label} did not become healthy at {url}: {last_error}")


def start_process(command: list[str], cwd: Path, env: dict[str, str], label: str) -> subprocess.Popen[str]:
    log(f"Starting {label}: {' '.join(shlex.quote(part) for part in command)}")
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        text=True,
    )


def build_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    if extra:
        env.update(extra)
    return env


def start_all() -> None:
    python_bin = sys.executable or find_python_executable()
    if not python_bin:
        raise RuntimeError("No Python executable was found on PATH or in the project virtual environment.")

    env = build_env({"KB_API_URL": "http://127.0.0.1:8000"})
    task1_proc = start_process(
        [python_bin, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        TASK1_DIR,
        env,
        "Task 1",
    )
    try:
        task1_health = wait_for_health("http://127.0.0.1:8000/health", "Task 1")
    except RuntimeError as exc:  # pragma: no cover - exercised at runtime
        task1_proc.terminate()
        raise RuntimeError(f"Task 1 could not start: {exc}") from exc

    task3_env = build_env({**env, "KB_API_URL": "http://127.0.0.1:8000", "SCOPE_PORT": "8002"})
    task3_proc = start_process(
        [python_bin, "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", "8002"],
        TASK3_DIR,
        task3_env,
        "Task 3",
    )
    try:
        wait_for_health("http://127.0.0.1:8002/health", "Task 3")
    except RuntimeError as exc:  # pragma: no cover - exercised at runtime
        task1_proc.terminate()
        task3_proc.terminate()
        raise RuntimeError(f"Task 3 could not start: {exc}") from exc

    node_bin, npm_bin = discover_node_runtime()
    if not node_bin or not npm_bin:
        log("Task 2 requires Node.js and npm to run. Install Node LTS and rerun this launcher.")
        log("Shared services are available at: http://127.0.0.1:8000 and http://127.0.0.1:8002")
        return

    task2_env = build_env({**env, "KB_API_URL": "http://127.0.0.1:8000", "INBOX_PORT": "3002"})
    node_dir = str(Path(node_bin).parent)
    task2_env["PATH"] = f"{node_dir}{os.pathsep}{task2_env.get('PATH', '')}"
    task2_proc = start_process([npm_bin, "install", "--silent"], TASK2_DIR, task2_env, "Task 2 install")
    task2_proc.wait(timeout=180)
    if task2_proc.returncode not in (0, None):
        raise RuntimeError(f"Task 2 dependency install failed with exit code {task2_proc.returncode}.")

    task2_proc = start_process([npm_bin, "run", "dev"], TASK2_DIR, task2_env, "Task 2")
    try:
        wait_for_health("http://127.0.0.1:3002/api/health", "Task 2")
    except RuntimeError as exc:  # pragma: no cover - exercised at runtime
        task1_proc.terminate()
        task3_proc.terminate()
        task2_proc.terminate()
        raise RuntimeError(f"Task 2 could not start: {exc}") from exc

    print()
    print("BusinessLabs Assignment: AI Tech Consultant")
    print("=" * 48)
    print("All three services are running.")
    print(f"Task 1 Knowledge Brain: {task1_health}")
    print("Task 1 API: http://127.0.0.1:8000/docs")
    print("Task 3 Meeting to Scope: http://127.0.0.1:8002/docs")
    print("Task 2 Inbox Agent: http://127.0.0.1:3002")
    print()
    print("Shared API wiring: Task 2 and Task 3 both query Task 1 via KB_API_URL=http://127.0.0.1:8000")
    print("Press Ctrl-C to stop the combined workflow.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("Stopping services...")
        for proc in (task1_proc, task3_proc, task2_proc):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()


if __name__ == "__main__":
    try:
        start_all()
    except RuntimeError as exc:
        print(f"Failed to start the integrated project: {exc}", file=sys.stderr)
        sys.exit(1)

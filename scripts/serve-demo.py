"""Run the public web interface and its private Python API in one Render service."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Event
from urllib.error import URLError
from urllib.request import urlopen


def main() -> int:
    stopping = Event()
    children: list[subprocess.Popen] = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopping.set())

    api_port = os.getenv("RAPID_API_PORT", "8900")
    web_dir = Path(os.getenv("RAPID_WEB_DIR", "/app/web"))
    try:
        api = subprocess.Popen([
            sys.executable, "-m", "uvicorn",
            "services.api.app.public_demo:create_app", "--factory",
            "--host", "127.0.0.1", "--port", api_port,
        ])
        children.append(api)
        for _ in range(150):
            if stopping.is_set() or api.poll() is not None:
                return 1
            try:
                with urlopen(f"http://127.0.0.1:{api_port}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (OSError, URLError):
                pass
            stopping.wait(0.2)
        else:
            print("The analysis service did not start.", flush=True)
            return 1

        web_env = {
            **os.environ,
            "HOSTNAME": "0.0.0.0",
            "PORT": os.getenv("PORT", "10000"),
        }
        children.append(subprocess.Popen(
            [os.getenv("NODE_BINARY", "node"), str(web_dir / "server.js")],
            cwd=web_dir,
            env=web_env,
        ))
        while not stopping.wait(0.2):
            if any(child.poll() is not None for child in children):
                print("A demo service stopped; shutting down for a clean restart.", flush=True)
                return 1
        return 0
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        deadline = time.monotonic() + 8
        for child in children:
            try:
                child.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    sys.exit(main())

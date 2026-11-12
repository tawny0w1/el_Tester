"""Shared helpers for the check scripts in tests/ (the scripts not run by pytest).

Each script makes a Checks, records PASS/FAIL lines with check(), and ends with
sys.exit(checks.exit_code()).
"""
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

PROJECT_DIR = Path(__file__).resolve().parent.parent
TEST_PAGES = PROJECT_DIR / "test_pages"

# Review360 course used by the Rise checks (the toolbar's default link, see Notes)
REVIEW_URL = "https://360.eu.articulate.com/review/content/1e64fc6d-b59c-4abf-8e4e-dfdbfd41838b/review"

# Make the project importable when a script runs as python3 tests/<script>.py
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


@contextmanager
def fixture_server(port: int) -> Iterator[tuple[str, str]]:
    """Serve test_pages/ over HTTP. Yields the two origins: left (localhost), right (127.0.0.1).

    Two host names, so the windows are on different URLs, like two course versions.
    """
    server = subprocess.Popen([sys.executable, "-m", "http.server", "-d", str(TEST_PAGES), str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for(lambda: _port_open(port), timeout=10):
            raise RuntimeError(f"Fixture server did not start on port {port}")
        yield f"http://localhost:{port}", f"http://127.0.0.1:{port}"
    finally:
        server.terminate()


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for(condition: Callable[[], object], timeout: float = 10.0, interval: float = 0.3) -> bool:
    """True as soon as condition() is truthy; exceptions count as "not yet" (e.g. a page still loading)."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if condition():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def live_chromium_processes() -> int:
    """Running Chromium processes. Zombies (state Z) don't count: in the container,
    PID 1 is `sleep infinity`, which never reaps exited processes."""
    ps = subprocess.run(["ps", "-eo", "stat,args"], capture_output=True, text=True).stdout.splitlines()
    return sum("chrom" in line and not line.lstrip().startswith("Z") for line in ps)


class Checks:
    """Collects PASS/FAIL results and prints them as they happen."""

    def __init__(self) -> None:
        self.results: list[tuple[str, bool]] = []

    def check(self, name: str, ok: bool, detail: object = "") -> bool:
        self.results.append((name, ok))
        print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""), flush=True)
        return ok

    def exit_code(self) -> int:
        passed = sum(ok for _, ok in self.results)
        print(f"\n{passed}/{len(self.results)} passed", flush=True)
        return 0 if self.results and passed == len(self.results) else 1

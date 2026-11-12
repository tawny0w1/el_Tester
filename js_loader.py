"""Loads the tracker scripts in js/ so both engines inject the same JS."""
from pathlib import Path

# js/ next to this file, so loading works from any current directory
JS_DIR: Path = Path(__file__).resolve().parent / "js"


def load_js(*names: str) -> str:
    """Join the given js/ files into one script, in the given order.

    One script, because each execute_script call has its own scope: a
    function injected in one call is gone in the next.
    Example: load_js("xpath.js", "click_tracker.js"). Helpers go first by
    convention; function declarations are hoisted, so the order only matters
    for top-level code that runs immediately.
    """
    return "\n".join((JS_DIR / name).read_text(encoding="utf-8") for name in names)

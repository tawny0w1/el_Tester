"""Run a test command and save its output as a log in unit_test_results/.

    cd selenium_el_tester
    python3 tests/run_and_log.py tests/pw_e2e_sync.py          # a check script
    python3 tests/run_and_log.py tests/e2e_sync.py
    python3 tests/run_and_log.py -m pytest -q                   # pytest
    python3 tests/run_and_log.py --note "after fix X" tests/e2e_engine_switch.py

Every run gets its own timestamped log in /workspace/unit_test_results/
(outside the repo), with a header: date, commit, uncommitted files, command.
The output is also shown live. The exit code is the test's own.
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_DIR.parent / "unit_test_results"


def git(*args: str) -> str:
    # rstrip, not strip: "git status --short" lines start with a meaningful space
    return subprocess.run(["git", "-C", str(PROJECT_DIR), *args], capture_output=True, text=True).stdout.rstrip()


def log_name(command: list[str], started: datetime) -> str:
    """2026-11-10_201500_pw_e2e_sync.log, or ..._pytest.log for -m pytest."""
    script = next((Path(a).stem for a in command if a.endswith(".py")), None)
    name = script or ("pytest" if "pytest" in command else "run")
    return f"{started:%Y-%m-%d_%H%M%S}_{name}.log"


def main() -> int:
    # Only a leading --note belongs to this script; everything after goes to
    # python3 unchanged (argparse would take pytest's -m for its own option)
    argv = sys.argv[1:]
    note = ""
    if argv[:1] == ["--note"] and len(argv) >= 2:
        note, argv = argv[1], argv[2:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    args = argparse.Namespace(note=note, command=argv)

    started = datetime.now()
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / log_name(args.command, started)
    dirty = git("status", "--short")
    header = [
        f"Date: {started:%Y-%m-%d %H:%M:%S}",
        f"Commit: selenium_el_tester @ {git('rev-parse', '--short', 'HEAD')}"
        + (" + uncommitted changes:" if dirty else " (clean)"),
        *(f"  {line}" for line in dirty.splitlines()),
        f"Command: python3 {' '.join(args.command)}  (in {PROJECT_DIR})",
    ]
    if args.note:
        header.append(f"Note: {args.note}")

    with log_path.open("w", encoding="utf-8") as log:
        log.write("\n".join(header) + "\n\n")
        log.flush()
        process = subprocess.Popen([sys.executable, *args.command], cwd=PROJECT_DIR, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
        assert process.stdout is not None
        for line in process.stdout:  # live output, and the same into the log
            sys.stdout.write(line)
            log.write(line)
        code = process.wait()
        finished = datetime.now()
        log.write(f"\nExit code: {code}  ({(finished - started).total_seconds():.0f} s)\n")
    print(f"\nLog: {log_path}")
    return code


if __name__ == "__main__":
    sys.exit(main())

# Tests (for developers)

This page is for people who **change EL Tester's code**. You don't need these tests to use the app: for
that, see the main [README](../README.md).

Run everything from the project folder (`el_Tester/`), after the install steps in the main README.

## Quick start

```bash
python3 -m pytest -q             # quick tests, no browser (a few seconds)
python3 tests/e2e_sync.py        # Selenium: opens hidden browsers and checks every kind of sync
python3 tests/pw_e2e_sync.py     # the same with Playwright (add --headed to watch it)
```

Each check script prints `PASS` or `FAIL` for every check and ends with a total such as `12/12 passed`.
It exits with code 0 when every check passed. The scripts serve `test_pages/` themselves, so you don't
need to start a web server first.

## Two kinds of tests

- **pytest** (`test_*.py`): the parts without a browser: the bug database, the file names of screenshots,
  the PDF export, the texts of the bug form. Fast, and safe to run at any time.
- **Check scripts** (the other `.py` files): start real browsers on the test pages and check what the
  user would see. They take from a few seconds to about a minute each.

## The check scripts

| Script                   | What it checks                                                                       | Needs              |
| ------------------------ | ------------------------------------------------------------------------------------ | ------------------ |
| `e2e_sync.py`            | Selenium: clicks, scroll, inputs, drag, iframes, links, video warning                 | -                  |
| `pw_e2e_sync.py`         | Playwright: clicks, scroll, inputs, iframes (also from another website), links       | -                  |
| `e2e_engine_switch.py`   | Switching between Selenium and Playwright in the running app                         | -                  |
| `e2e_pdf_report.py`      | "Save and create PDF" with both tools                                                 | -                  |
| `pw_drag.py`             | Playwright: drag and drop on `drag.html`, also in a cross-origin iframe (Phase 7)    | -                  |
| `pw_video.py`            | Playwright: video warning on `video.html` (Phase 7)                                   | -                  |
| `pw_rise_drag.py`        | Playwright: drag and drop on the real Review 360 course (Phase 7)                     | internet           |
| `pw_review360.py`        | Playwright on a real Articulate Review 360 course                                     | internet           |
| `ui_missing_element.py`  | A button missing on the Target opens the filled-in bug report, with both tools        | a screen           |
| `ui_pdf_save.py`         | Toolbar → Report bug form → save dialog                                               | a screen           |
| `ui_bug_window.py`       | The bug list, the Edit form, the toolbar's size and Bugs button                       | a screen           |
| `ui_window_layout.py`    | The two browser windows touch, with no gap between them                               | a screen           |

"A screen" means the script opens real windows: run it on a desktop (Linux: an X11 session), and don't
use the mouse or keyboard while it runs.

Helper files (not tests): `helpers.py` (shared code: the test-page server, `wait_for`, `Checks`),
`xgrab.py` (saves a window as a PNG), `run_and_log.py` (see below).

## Keeping a log of each run

```bash
python3 tests/run_and_log.py --note "what changed" tests/e2e_sync.py
python3 tests/run_and_log.py -m pytest -q
```

It runs the command as usual and also saves its output, with the date and the current commit, as a
timestamped `.log` file in `unit_test_results/`, **next to** the project folder (outside the repository).

## The README animations

The animations in the main README are made from the test pages in the same way, with the Playwright
engine:

```bash
python3 docs/make_animations.py  # rewrites docs/img/ (needs a screen for the toolbar and form pictures)
```

Run it again after a change to how the windows or the toolbar look.

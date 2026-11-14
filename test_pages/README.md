# Test pages

Static pages for manual regression of the sync features (`project-plan.md`, Phase 1).

## Run

Serve them over HTTP. Don't open them as `file://`: Chrome gives every `file://` page an
opaque origin, so `iframe.contentDocument` is `null` and same-origin iframe sync can't work.

```bash
cd selenium_el_tester
python3 -m http.server -d test_pages 8000     # terminal 1
python3 el_tester.py                          # terminal 2
```

Enter `http://localhost:8000/index.html` in the toolbar and click Load. The page loads after about 10 s,
because the app first waits for a Rise `iframe.player`. Use `localhost`, not `127.0.0.1`: `cross_origin.html`
relies on the two names being different origins.

Every `Button (n)` shows how often it was clicked. Compare the numbers in the two windows.

## Automated run

`python3 tests/e2e_sync.py` starts this server itself (port 8765), runs `el_tester.py` with headless
browsers and no toolbar, and checks page scroll, clicks, drag, the video notice, link clicks (left on
`localhost`, right on `127.0.0.1`), nested-iframe click and input, and in-frame scroll. Takes about a minute;
exit code 0 when all checks pass. Pass a directory to test another copy of the app.

## Checklist

Results from 2026-11-04 (headless run of `el_tester.py` with scripted input on the left), updated 2026-11-05 for items 3, 4 and 5.

| Page | Do on the left | Right should | Now |
|---|---|---|---|
| `index.html` | scroll the page | follow the scroll | ✅ |
| `index.html` | click Button A / B | same counters | ✅ |
| `index.html` ↔ `page2.html` | click the links a few times, then scroll | both navigate, scroll still syncs | ✅ (stale-element errors retried and recovered) |
| `nested.html` | click Top / Level 1 buttons | same counters | ✅ |
| `nested.html` | click Level 2 button | same counter | ✅ |
| `nested.html` | type in the Level 2 text field | same text | ✅ |
| `nested.html` | scroll the boxes (and the page) inside both iframes | same scroll | ✅ |
| `nested.html` | scroll the `box-top` div (top page) | same scroll | ❌ top page: only page scroll and Rise containers sync (by design, item 5 covers iframes only) |
| `cross_origin.html` | click the button in the same-origin frame | same counter | ✅ |
| `cross_origin.html` | click the button in the cross-origin frame | nothing (known limit) | ✅ not reachable |
| `form.html` | type a name, pick a language, click radio "2" | same values | ✅ |
| `form.html` | tick the checkbox | ticked | ✅ |
| `form.html` | press Enter in Name, or click Submit | `submitted.html` with the same values | ⚠️ right submits too (implicit submission clicks the Submit button); values match since item 3 |
| `page2.html` | browser Back | go back too | ❌ item 6 |
| `index.html` ↔ `index2.html` (right) | click Button B (missing on the right) | Phase 5 item 6: a pre-filled "Element … not found" bug form opens | ⏳ today only "not found on the right" is printed (`tests/ui_missing_element.py`) |

The terminal should show no `sync stopped` lines. `... error #N ..., retrying` right after a navigation is
expected.

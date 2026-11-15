"""Make the README animations (docs/img/*.gif) from the test pages.

Runs the real Playwright engine (PwTester) headless on test_pages/, takes a
screenshot of both windows after every step, and puts them side by side:
Source on the left, Target on the right, a caption on top, and a red ring
where the click happened. The Tk windows (toolbar, missing-element form) are
grabbed from the display with tests/xgrab.py, so DISPLAY must be set.

    cd selenium_el_tester
    python3 docs/make_animations.py
"""
import io
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import Locator, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from helpers import fixture_server  # noqa: E402
from pw_tester import PwTester  # noqa: E402
from xgrab import grab  # noqa: E402

OUT_DIR = ROOT / "docs" / "img"
PORT = 8770
CROP = (0, 0, 620, 470)  # the part of each window that is shown (pixels of the page)
SCALE = 0.75
CAPTION_H = 44
LABEL_H = 26
GAP = 6
SLOWDOWN = 2  # every frame is shown this many times longer than the times in the scenarios
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class Recorder:
    """Collects side-by-side frames of the two windows and saves them as a GIF."""

    def __init__(self, tester: PwTester) -> None:
        self.tester = tester
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []
        self.caption_font = ImageFont.truetype(FONT_BOLD, 18)
        self.label_font = ImageFont.truetype(FONT, 14)

    def snap(self, caption: str, ms: int = 1200, ring_on: Locator | None = None) -> None:
        """One frame: both windows now, with a caption; ring_on marks a spot on the left."""
        self.tester.left.wait_for_timeout(300)  # let the sync reach the right window
        ring = None
        if ring_on is not None:
            box = ring_on.bounding_box()
            if box:
                ring = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        left = self._window(self.tester.left.screenshot(), ring)
        right = self._window(self.tester.right.screenshot(), None)
        self.add(self._compose(caption, left, right), ms)

    def add(self, frame: Image.Image, ms: int) -> None:
        self.frames.append(frame.convert("RGB"))
        self.durations.append(ms * SLOWDOWN)

    def _window(self, png: bytes, ring: tuple[float, float] | None) -> Image.Image:
        image = Image.open(io.BytesIO(png)).convert("RGB").crop(CROP)
        if ring:
            x, y = ring
            draw = ImageDraw.Draw(image)
            draw.ellipse((x - 22, y - 22, x + 22, y + 22), outline=(230, 20, 20), width=5)
        return image.resize((int(image.width * SCALE), int(image.height * SCALE)), Image.LANCZOS)

    def _compose(self, caption: str, left: Image.Image, right: Image.Image) -> Image.Image:
        width = left.width + GAP + right.width
        frame = Image.new("RGB", (width, CAPTION_H + LABEL_H + left.height), (245, 245, 245))
        draw = ImageDraw.Draw(frame)
        draw.text((12, 11), caption, font=self.caption_font, fill=(30, 30, 30))
        for x, label, color in ((0, "Source: reference  (you click here)", (40, 110, 200)),
                                (left.width + GAP, "Target: being tested  (follows by itself)", (40, 150, 70))):
            draw.rectangle((x, CAPTION_H, x + left.width, CAPTION_H + LABEL_H), fill=color)
            draw.text((x + 8, CAPTION_H + 4), label, font=self.label_font, fill="white")
        frame.paste(left, (0, CAPTION_H + LABEL_H))
        frame.paste(right, (left.width + GAP, CAPTION_H + LABEL_H))
        return frame

    def save(self, name: str) -> None:
        path = OUT_DIR / name
        # Shared palette: smaller files, no colour flicker between frames
        frames = [f.quantize(colors=128, method=Image.MEDIANCUT) for f in self.frames]
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=self.durations, loop=0, optimize=True)
        print(f"Saved {path.relative_to(ROOT)} ({len(frames)} frames, {path.stat().st_size // 1024} KB)")
        self.frames, self.durations = [], []


def clicks_and_scroll(rec: Recorder, left: str, right: str) -> None:
    t = rec.tester
    t.open(f"{left}/index.html", f"{right}/index.html")
    rec.snap("Two windows, different versions of the same page", 1800)
    for button, caption in (("#btn-a", "Click Button A on the Source..."), ("#btn-a", "...and again"),
                            ("#btn-b", "Click Button B")):
        loc = t.left.locator(button)
        ring = loc.bounding_box()
        loc.click()
        rec.snap(caption + "  →  the Target clicks it too", 1300, ring_on=loc if ring else None)
    t.left.mouse.move(200, 400)
    for step in range(4):
        t.left.mouse.wheel(0, 250)
        rec.snap("Scroll the Source  →  the Target scrolls the same", 500 if step < 3 else 1800)


def form_inputs(rec: Recorder, left: str, right: str) -> None:
    t = rec.tester
    t.open(f"{left}/form.html", f"{right}/form.html")
    rec.snap("A form on both sides", 1500)
    name = t.left.locator("#name")
    name.click()
    for i in range(1, len("Anna") + 1):
        name.fill("Anna"[:i])
        rec.snap("Type in a field  →  the same text appears on the Target", 350)
    rec.add(rec.frames[-1], 900)
    t.left.select_option("#lang", "pl")
    rec.snap("Pick from a list  →  same choice", 1300, ring_on=t.left.locator("#lang"))
    t.left.click("#agree")
    rec.snap("Tick a checkbox  →  ticked on the Target too", 1300, ring_on=t.left.locator("#agree"))
    t.left.click("#lvl-2")
    rec.snap("Choose a radio button  →  same choice", 2000, ring_on=t.left.locator("#lvl-2"))


def nested_frames(rec: Recorder, left: str, right: str) -> None:
    t = rec.tester
    t.open(f"{left}/nested.html", f"{right}/nested.html")
    t.left.wait_for_timeout(800)
    rec.snap("Pages inside pages (iframes)", 1500)
    level1 = t.left.frame_locator("#frame1")
    level2 = level1.frame_locator("#frame2")
    for loc, caption in ((t.left.locator("#btn-top"), "Click on the main page"),
                         (level1.locator("#btn-l1"), "Click inside an iframe"),
                         (level2.locator("#btn-l2"), "Click inside an iframe inside an iframe")):
        loc.click()
        rec.snap(caption + "  →  synced", 1400, ring_on=loc)


def missing_element(rec: Recorder, left: str, right: str) -> None:
    t = rec.tester
    t.open(f"{left}/index.html", f"{right}/index2.html")
    rec.snap("The Target version has no Button B (a real bug!)", 2000)
    t.left.locator("#btn-a").click()
    rec.snap("Button A is on both pages  →  synced", 1300, ring_on=t.left.locator("#btn-a"))
    loc = t.left.locator("#btn-b")
    loc.click()
    rec.snap("Click Button B  →  the Target has nothing to click...", 1500, ring_on=loc)
    rec.snap("...the tool waits 2 seconds, in case the page is still loading...", 1500)
    last = rec.frames[-1]
    form = grab_window(["report_form.py", "missing"], "Clicked element not found", "form.png")
    form.thumbnail((int(last.width * 0.62), int(last.height * 0.85)))
    shown = last.copy()
    shown.paste(form, ((last.width - form.width) // 2, CAPTION_H + LABEL_H + 10))
    draw = ImageDraw.Draw(shown)
    draw.rectangle((0, 0, last.width, CAPTION_H - 1), fill=(245, 245, 245))
    draw.text((12, 11), "...then a bug report opens, already filled in", font=rec.caption_font, fill=(30, 30, 30))
    rec.add(shown, 4000)


def grab_window(command: list[str], title: str, png_name: str) -> Image.Image:
    """Start a Tk window of the app on the display, save it as a PNG, close it."""
    process = subprocess.Popen([sys.executable, *command], cwd=ROOT, stdout=subprocess.DEVNULL)
    path = OUT_DIR / png_name
    try:
        for _ in range(20):  # the window needs a moment to appear
            time.sleep(0.5)
            try:
                grab(title, str(path))
                break
            except LookupError:
                continue
        else:
            raise LookupError(f"Window {title!r} did not open")
    finally:
        process.terminate()
    return Image.open(path).convert("RGB")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grab_window(["floating_ui.py", "http://localhost:8000/index.html"], "EL Tester", "toolbar.png")
    with fixture_server(PORT) as (left, right), sync_playwright() as p:
        rec = Recorder(PwTester(p, headless=True))
        try:
            for scenario, name in ((clicks_and_scroll, "clicks_and_scroll.gif"), (form_inputs, "form_inputs.gif"),
                                   (nested_frames, "nested_iframes.gif"), (missing_element, "missing_element.gif")):
                scenario(rec, left, right)
                rec.save(name)
        finally:
            rec.tester.close()


if __name__ == "__main__":
    main()

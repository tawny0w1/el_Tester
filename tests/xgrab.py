"""Save an X window as a PNG, found by part of its title (no screenshot tool in the container).

Uses libX11's XGetImage through ctypes, so it needs only libX11 (tkinter
already depends on it), xwininfo (x11-utils) and Pillow.

    python3 tests/xgrab.py "Report bug" form.png
    python3 tests/xgrab.py "Bug reports - Chromium" pdf.png    # a PDF open in Chromium

Used by ui_pdf_save.py --shots, and to look at a PDF in Chromium's viewer.
"""
import ctypes
import ctypes.util
import re
import subprocess
import sys

from PIL import Image

Z_PIXMAP = 2
ALL_PLANES = 0xFFFFFFFF


class XImage(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int), ("xoffset", ctypes.c_int),
                ("format", ctypes.c_int), ("data", ctypes.POINTER(ctypes.c_char)),
                ("byte_order", ctypes.c_int), ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int),
                ("bitmap_pad", ctypes.c_int), ("depth", ctypes.c_int), ("bytes_per_line", ctypes.c_int),
                ("bits_per_pixel", ctypes.c_int)]


def find_window(title_part: str) -> tuple[int, int, int]:
    """(window id, width, height) of the first window whose title contains title_part."""
    tree = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, check=True).stdout
    pattern = r'(0x[0-9a-f]+) "[^"]*' + re.escape(title_part) + r'[^"]*".*?(\d+)x(\d+)\+'
    match = re.search(pattern, tree)
    if match is None:
        raise LookupError(f"No window with {title_part!r} in its title")
    return int(match.group(1), 16), int(match.group(2)), int(match.group(3))


def grab(title_part: str, out_path: str) -> None:
    window, width, height = find_window(title_part)
    _save(lambda x11, display: window, width, height, out_path)


def grab_root(out_path: str, width: int = 2000, height: int = 1200) -> None:
    """The top-left width x height of the whole screen (e.g. to see where windows sit side by side)."""
    _save(lambda x11, display: x11.XDefaultRootWindow(display), width, height, out_path)


def _save(get_window, width: int, height: int, out_path: str) -> None:
    """Copy the window's pixels (XGetImage) to a PNG. get_window(x11, display) -> window id."""
    x11 = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11"))
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XGetImage.restype = ctypes.POINTER(XImage)
    x11.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                              ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    try:
        window = get_window(x11, display)
        image = x11.XGetImage(display, window, 0, 0, width, height, ALL_PLANES, Z_PIXMAP).contents
        raw = ctypes.string_at(image.data, image.bytes_per_line * height)
        Image.frombuffer("RGBX", (width, height), raw, "raw", "BGRX", image.bytes_per_line, 1) \
            .convert("RGB").save(out_path)
    finally:
        x11.XCloseDisplay(display)
    print(f"Saved {width}x{height} window {hex(window)} to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    grab(sys.argv[1], sys.argv[2])

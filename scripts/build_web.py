#!/usr/bin/env python3
"""Build the hosted web app into docs/ for GitHub Pages.

The page is the same dashboard the Python app serves; hosted standalone it
detects no local server and switches to Web Bluetooth mode (Chrome/Edge),
talking to the Movella DOT directly from the browser.

Run after any change to swingcoach/dashboard.html:
    python scripts/build_web.py
then commit docs/index.html.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swingcoach.webapp import _render_page  # noqa: E402

out = ROOT / "docs" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_bytes(_render_page())
print(f"wrote {out} ({out.stat().st_size/1024:.1f} KB)")

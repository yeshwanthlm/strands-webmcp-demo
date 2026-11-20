"""Launching the one Chrome that both arms share.

WebMCP currently lives behind a flag, so this uses your real Chrome (not
Playwright's bundled Chromium) with a persistent profile folder. Turn the flag
on once in that profile and it sticks for every later run.
"""

from __future__ import annotations

import os
from pathlib import Path

PROFILE_DIR = Path(__file__).parent / ".chrome-profile"
SITE_ROOT = os.environ.get("CANTEEN_URL", "https://d2gk3ykaq9ah2.cloudfront.net/")

# chrome://flags/#enable-webmcp-testing maps to blink::features::kWebMCP in
# Chromium's about_flags.cc, so we can switch it on from the command line and
# skip the manual flag dance. Verified working on Chrome 157.
# Add more with: CHROME_ARGS="--foo" python benchmark.py
WEBMCP_ARGS = ["--enable-features=WebMCP"]
EXTRA_ARGS = WEBMCP_ARGS + [a for a in os.environ.get("CHROME_ARGS", "").split() if a]


async def launch(playwright, headless: bool = False):
    """Open Chrome with the persistent profile. Returns (context, page)."""
    PROFILE_DIR.mkdir(exist_ok=True)
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=EXTRA_ARGS,
    )
    page = context.pages[0] if context.pages else await context.new_page()
    page.set_default_timeout(8000)

    # The persistent profile keeps a disk cache, and once served a stale
    # index.html from before the WebMCP switch existed. Always fetch fresh, so
    # what the agent sees is what you just deployed.
    cdp = await context.new_cdp_session(page)
    await cdp.send("Network.clearBrowserCache")
    await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    return context, page


def url_for(query: str = "") -> str:
    return SITE_ROOT.rstrip("/") + "/" + query

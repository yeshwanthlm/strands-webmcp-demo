"""The live stage demo. Opens Chrome, and lets the audience watch.

    python show.py            # without WebMCP, then with it, then the scoreboard
    python show.py without    # just the no-WebMCP run
    python show.py with       # just the WebMCP run

What the room sees, all inside the website:

  1. Chrome opens on the tiffin room site, by itself.
  2. The WebMCP switch is clicked off on screen.
  3. The agent panel (bottom left) starts a timer and lists every step,
     while the agent clicks the + buttons and fills the form.
  4. The switch is clicked on. Same request, same model, run again.
  5. The panel shows both runs side by side.

The browser stays open at the end. Press Enter in the terminal to close it.

Uses CANTEEN_URL if set, so it works against localhost or the CloudFront site:
    CANTEEN_URL="https://d2gk3ykaq9ah2.cloudfront.net/" python show.py
"""

from __future__ import annotations

import argparse
import asyncio
import os

# A roomy window that sits where the audience can see it.
os.environ.setdefault("CHROME_ARGS", "--window-position=0,0 --window-size=1440,900")

from playwright.async_api import async_playwright

import arms
from browser import launch, url_for
from present import run_arm

PAUSE_BETWEEN = 4.0  # seconds to let the room read the first result


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("which", nargs="?", choices=["both", "without", "with"],
                        default="both")
    parser.add_argument("--ask", default=arms.TASK)
    args = parser.parse_args()

    plan = {"both": ["A_no_webmcp", "B_webmcp"],
            "without": ["A_no_webmcp"],
            "with": ["B_webmcp"]}[args.which]

    async with async_playwright() as p:
        context, page = await launch(p, headless=False)
        await page.goto(url_for(""))
        await page.wait_for_function("window.AgentHUD !== undefined")

        if not await page.evaluate("!!document.modelContext") and "B_webmcp" in plan:
            print("\n  This Chrome has no WebMCP. Run: python doctor.py\n")
            await context.close()
            return

        if args.which == "both":
            await page.evaluate("window.AgentHUD.clear()")

        for i, arm_key in enumerate(plan):
            if i:
                await asyncio.sleep(PAUSE_BETWEEN)
            await run_arm(page, arm_key, ask=args.ask, hud=True, flip_switch=True)

        print("\nDone. The scoreboard is on the page. Press Enter to close Chrome.")
        await asyncio.to_thread(input)
        await context.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print()

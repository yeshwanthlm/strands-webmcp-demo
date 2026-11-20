"""Test the site and the Arm A locators without spending a rupee on Bedrock.

Runs in plain Chromium, so it does not need the WebMCP flag. It proves:

  1. the page loads and app.js works
  2. the labels Arm A's tools rely on actually resolve
  3. placing an order sets window.__lastOrder
  4. arms.check() agrees with a correct order and rejects a wrong one
  5. the WebMCP page degrades gracefully when the API is absent

    ../.venv/bin/python smoke_test.py      (site/serve.sh must be running)
"""

from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright

import arms
from browser import url_for

checks: list[tuple[bool, str]] = []


def expect(cond: bool, what: str) -> None:
    checks.append((bool(cond), what))
    print(f"[{'  ok  ' if cond else ' FAIL '}] {what}")


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.set_default_timeout(5000)
        arms.set_page(page)

        await page.goto(url_for())
        await page.wait_for_function("window.Canteen !== undefined")
        expect(True, "plain page loads")

        # The outline Arm A reads.
        outline = await arms.read_page()
        expect("Masala Dosa" in outline, "read_page shows the menu")
        expect("Pickup time" in outline, "read_page shows the pickup field")
        expect(len(outline) > 200, f"outline is substantial ({len(outline)} chars)")

        # Every label Arm A's prompt will make the model guess at.
        for label in ["Masala Dosa quantity", "Filter Coffee quantity", "Your name"]:
            r = await arms.fill_field(label, "2" if "quantity" in label else "Yeshwanth")
            expect(not r.startswith("ERROR"), f"fill_field({label!r}) works")

        r = await arms.fill_field("Filter Coffee quantity", "1")
        expect(not r.startswith("ERROR"), "coffee quantity set to 1")

        r = await arms.select_option("Pickup time", "13:00")
        expect(not r.startswith("ERROR"), "select_option by value works")

        r = await arms.select_option("Pickup time", "1:00 PM")
        expect(not r.startswith("ERROR"), "select_option by visible label works")

        r = await arms.click_button("Place order")
        expect(not r.startswith("ERROR"), "click_button('Place order') works")

        ok, why = await arms.check(page)
        expect(ok, f"a correct order passes the oracle ({why})")

        total = await page.text_content("#total")
        expect(total == "₹95", f"total is right: {total} (2x40 + 1x15)")

        # A wrong order must fail, or the benchmark proves nothing.
        await page.evaluate("window.Canteen.reset()")
        await page.evaluate(
            "window.Canteen.placeOrder({items:[{id:'dosa',qty:1}],"
            "name:'Yeshwanth',pickup:'13:00'})"
        )
        ok, why = await arms.check(page)
        expect(not ok, f"a wrong order fails the oracle ({why})")

        # Validation rejects what it should.
        await page.evaluate("window.Canteen.reset()")
        bad = await page.evaluate(
            "window.Canteen.placeOrder({items:[{id:'dosa',qty:2}],"
            "name:'Y',pickup:'13:00'})"
        )
        expect(bad["ok"] is False, "short name is rejected")
        bad = await page.evaluate(
            "window.Canteen.placeOrder({items:[{id:'dosa',qty:2}],"
            "name:'Yeshwanth',pickup:'1 pm'})"
        )
        expect(bad["ok"] is False, "pickup '1 pm' is rejected, 13:00 is required")

        # Pay path.
        await page.evaluate("window.Canteen.reset()")
        placed = await page.evaluate(
            "window.Canteen.placeOrder({items:[{id:'dosa',qty:2},{id:'coffee',qty:1}],"
            "name:'Yeshwanth',pickup:'13:00'})"
        )
        expect(placed["ok"] is True, f"order placed: {placed.get('orderId')}")
        paid = await page.evaluate(
            f"window.Canteen.payOrder({placed['orderId']!r})"
        )
        expect(paid["ok"] is True, "pay_order path works")

        # The WebMCP page without the flag must not break for humans.
        await page.goto(url_for("?webmcp=1"))
        await page.wait_for_function("window.Canteen !== undefined")
        await page.wait_for_timeout(300)
        expect(
            await page.evaluate("document.querySelectorAll('#menu .item').length") == 13,
            "webmcp page still renders when the API is missing",
        )
        log = await page.text_content("#log")
        expect("modelContext" in (log or ""), "it says why WebMCP is unavailable")

        # Arm B's tools should fail loudly, not silently, without the API.
        r = await arms.list_site_tools()
        expect(r.startswith("ERROR"), "list_site_tools reports the missing API")

        await browser.close()

        # The header switch, in real Chrome with WebMCP enabled.
        try:
            chrome = await p.chromium.launch(channel="chrome",
                                             args=["--enable-features=WebMCP"])
        except Exception as exc:
            print(f"[ skip ] WebMCP switch tests — no Chrome ({str(exc)[:60]})")
            chrome = None
        if chrome:
            page = await chrome.new_page()
            names = "async () => (await document.modelContext.getTools()).map(t => t.name)"

            await page.goto(url_for())
            await page.wait_for_function("window.CanteenWebMCP !== undefined")
            expect(await page.evaluate(names) == [], "plain URL: switch off, no tools")
            expect(await page.get_attribute("#webmcp-toggle", "aria-checked") == "false",
                   "switch shows off")

            await page.click("#webmcp-toggle")
            await page.wait_for_function("window.CanteenWebMCP.on")
            await page.wait_for_timeout(200)
            expect(sorted(await page.evaluate(names)) ==
                   ["get_menu", "pay_order", "place_order"], "switch on: 3 tools appear")
            expect("webmcp=1" in page.url, "switch on: URL gains ?webmcp=1")
            expect(await page.text_content("#webmcp-state") == "on", "switch label says on")

            await page.click("#webmcp-toggle")
            await page.wait_for_timeout(300)
            expect(await page.evaluate(names) == [], "switch off: tools removed live")
            expect("webmcp" not in page.url, "switch off: URL drops ?webmcp")

            await page.click("#webmcp-toggle")
            await page.wait_for_timeout(300)
            expect(len(await page.evaluate(names)) == 3, "switch on again: no duplicate error")

            await page.goto(url_for("?webmcp=1"))
            await page.wait_for_function("window.CanteenWebMCP && window.CanteenWebMCP.on")
            expect(len(await page.evaluate(names)) == 3, "?webmcp=1 link opens switched on")
            await chrome.close()

    failed = [what for ok, what in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
    if failed:
        print("\nfailed:")
        for what in failed:
            print("  - " + what)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

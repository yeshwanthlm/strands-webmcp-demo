"""Check everything the demo needs, and say exactly what to fix.

    python doctor.py

Run this the morning of the talk, on the venue network.
"""

from __future__ import annotations

import asyncio
import os
import sys

MODEL_ID = os.environ.get("BENCH_MODEL", "us.amazon.nova-2-lite-v1:0")
REGION = os.environ.get("AWS_REGION", "us-east-1")

PASS, FAIL, WARN = "  ok  ", " FAIL ", " warn "
problems: list[str] = []


def say(status: str, what: str, detail: str = "") -> None:
    print(f"[{status}] {what}" + (f"  —  {detail}" if detail else ""))


def check_bedrock() -> None:
    try:
        import boto3
    except ImportError:
        say(FAIL, "boto3 installed")
        problems.append("pip install -r requirements.txt")
        return
    try:
        client = boto3.client("bedrock-runtime", region_name=REGION)
        client.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": "Reply with: ok"}]}],
            inferenceConfig={"maxTokens": 5},
        )
        say(PASS, f"Bedrock can call {MODEL_ID}", REGION)
    except Exception as exc:
        say(FAIL, f"Bedrock call to {MODEL_ID}", str(exc).splitlines()[0][:110])
        problems.append(
            "Check AWS creds (aws sso login / aws configure) and that this "
            f"account has access to {MODEL_ID} in {REGION}."
        )


async def check_browser() -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        say(FAIL, "playwright installed")
        problems.append("pip install -r requirements.txt && playwright install chrome")
        return

    from browser import launch, url_for

    try:
        async with async_playwright() as p:
            context, page = await launch(p, headless=False)
            try:
                await page.goto(url_for(), timeout=8000)
                say(PASS, "canteen site reachable", url_for())
            except Exception as exc:
                say(FAIL, "canteen site reachable", str(exc).splitlines()[0][:90])
                problems.append("Start the site:  ./site/serve.sh")
                await context.close()
                return

            if await page.evaluate("typeof window.Canteen !== 'undefined'"):
                say(PASS, "page logic loaded (window.Canteen)")
            else:
                say(FAIL, "page logic loaded (window.Canteen)")
                problems.append("app.js did not load — check the browser console.")

            version = await page.evaluate("navigator.userAgentData?.brands?.map(b => b.brand + ' ' + b.version).join(', ') || navigator.userAgent")
            say(PASS, "chrome", version[:90])

            await page.goto(url_for("?webmcp=1"))
            has_api = await page.evaluate("!!document.modelContext")
            if not has_api:
                say(FAIL, "document.modelContext present")
                problems.append(
                    "WebMCP did not switch on. browser.py launches Chrome with "
                    "--enable-features=WebMCP, which needs Chrome 149 or newer; "
                    "check your version above. If the flag was renamed, set it by "
                    "hand at chrome://flags/#enable-webmcp-testing in this profile "
                    "(agent/.chrome-profile) and run doctor.py again."
                )
            else:
                say(PASS, "document.modelContext present")
                tools = await page.evaluate(
                    "async () => (await document.modelContext.getTools()).map(t => t.name)"
                )
                if sorted(tools) == ["get_menu", "pay_order", "place_order"]:
                    say(PASS, "3 tools registered", ", ".join(sorted(tools)))
                else:
                    say(WARN, "tools registered", str(tools))

            await context.close()
    except Exception as exc:
        say(FAIL, "launch Chrome", str(exc).splitlines()[0][:110])
        problems.append("playwright install chrome")


async def main() -> int:
    print("\nMysuru Campus Canteen — pre-flight\n")
    check_bedrock()
    await check_browser()
    if problems:
        print("\nTo fix:\n")
        for i, fix in enumerate(problems, 1):
            print(f"  {i}. {fix}")
        print()
        return 1
    print("\nAll clear. You can run demo.py and benchmark.py.\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

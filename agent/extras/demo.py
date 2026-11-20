"""The on-stage run. One arm, one window, slow enough to narrate.

    python demo.py A      # the fumbling one
    python demo.py B      # the WebMCP one
    python demo.py B --ask "Order 3 idli vada for Asha at 2 pm"

Leaves the browser open at the end so the audience keeps looking at the result.
Ctrl-C to close.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from playwright.async_api import async_playwright
from strands import Agent
from strands.models import BedrockModel

import arms
from browser import launch, url_for
from present import LiveTrace

MODEL_ID = os.environ.get("BENCH_MODEL", "us.amazon.nova-2-lite-v1:0")
REGION = os.environ.get("AWS_REGION", "us-east-1")

RULE = "=" * 64


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("arm", choices=["A", "B"])
    parser.add_argument("--ask", default=arms.TASK)
    args = parser.parse_args()

    arm_key = "A_no_webmcp" if args.arm == "A" else "B_webmcp"
    arm = arms.ARMS[arm_key]

    async with async_playwright() as p:
        context, page = await launch(p, headless=False)
        await page.goto(url_for(arm["query"]))
        await page.wait_for_function("window.Canteen !== undefined")
        await page.evaluate("window.Canteen.reset()")
        arms.set_page(page)

        if arm_key == "B_webmcp" and not await page.evaluate("!!document.modelContext"):
            print("\n  document.modelContext is missing. Run: python doctor.py\n")
            await context.close()
            return

        print(f"\n{RULE}\n  {arm['label']}\n  model: {MODEL_ID}\n{RULE}")
        print(f"  asking: {args.ask}\n")

        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, region_name=REGION, max_tokens=2048),
            tools=arm["tools"],
            system_prompt=arm["system_prompt"],
            hooks=[LiveTrace(), arms.ToolBudget()],
            callback_handler=None,
        )

        result = await agent.invoke_async(args.ask)

        ok, why = await arms.check(page)
        usage = result.metrics.accumulated_usage

        print(f"\n{RULE}")
        print(f"  result        {'CORRECT ORDER' if ok else 'WRONG: ' + why}")
        print(f"  cycles        {result.metrics.cycle_count}")
        print(f"  tool calls    {sum(m.call_count for m in result.metrics.tool_metrics.values())}")
        print(f"  input tokens  {usage['inputTokens']}")
        print(f"  output tokens {usage['outputTokens']}")
        print(f"  model time    {result.metrics.accumulated_metrics['latencyMs']} ms")
        print(RULE)
        for name, m in sorted(result.metrics.tool_metrics.items()):
            print(f"  {name:<18} {m.call_count} call(s), {m.error_count} error(s)")
        print(f"{RULE}\n")

        print("Browser stays open. Ctrl-C when you are done talking.")
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await context.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print()

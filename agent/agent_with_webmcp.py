"""
Agent WITH WebMCP
=================

Opens Chrome on the Palace Road Tiffin Room site, clicks the WebMCP switch ON,
and asks a Strands agent to place an order.

The agent never touches the page. It asks the website which actions it offers
(WebMCP tools), then calls them.

    python agent_with_webmcp.py

Every tool call streams live into a side panel on the right of the website,
and the terminal. What the agent touches lights up on the site.
"""

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright
from strands import Agent, tool
from strands.hooks import (AfterModelCallEvent, AfterToolCallEvent, BeforeModelCallEvent,
                           BeforeToolCallEvent, HookProvider, HookRegistry)
from strands.models import BedrockModel

SITE = "https://d2gk3ykaq9ah2.cloudfront.net/"  # the live site on AWS
MODEL = "us.amazon.nova-2-lite-v1:0"
TASK = "Order 2 masala dosas and 1 filter coffee for Yeshwanth, pickup at 1 pm."
RESULTS = Path(__file__).resolve().parent.parent / "results" / "last_runs.json"

page = None  # the Chrome tab, shared with the tools below


# ---------------------------------------------------------------- the tools
# Two tools. The agent never sees buttons or inputs, only what the site declares.
# It never clicks anything, so instead the page scrolls through what each action
# changed and lights it up. That runs in the page by itself: the agent never waits.

SHOW_WHAT_CHANGED = """([name, args]) => {
    const steps = [];
    if (name === "get_menu") steps.push({ selector: "#menu-section", label: "get_menu", kind: "webmcp" });
    if (name === "place_order") {
        for (const item of args.items || [])
            steps.push({ selector: "#qty-" + item.id, label: "set to " + item.qty, kind: "webmcp" });
        steps.push({ selector: "#name", label: "name", kind: "webmcp" });
        steps.push({ selector: "#pickup", label: "pickup", kind: "webmcp" });
        steps.push({ selector: "#receipt", label: "place_order", kind: "webmcp" });
    }
    if (name === "pay_order") steps.push({ selector: "#pay", label: "pay_order", kind: "webmcp" });
    window.AgentHUD.tour(steps);
}"""


PAY_ALLOWED = False  # set from your request: only pay when you asked it to


def repair(name, args):
    """Nova sometimes leaks its own call syntax into the name, e.g.
    'place_order>\n<__parameter=args>{...}'. Recover the real name and arguments."""
    clean = re.match(r"[A-Za-z_]*", name).group(0)
    if clean != name and not args and "args>" in name:
        try:
            args = json.loads(name.split("args>", 1)[1].split("</")[0].strip())
        except ValueError:
            pass
    return clean, args


@tool
async def list_site_tools() -> str:
    """List the actions this website offers to agents, and what each one needs."""
    await page.evaluate("""() => window.AgentHUD.flash(
        document.getElementById("webmcp-toggle"), "reading the tools", "webmcp")""")
    tools = await page.evaluate("""async () =>
        (await document.modelContext.getTools()).map(t =>
            ({ name: t.name, description: t.description, inputSchema: t.inputSchema }))""")
    return json.dumps(tools)


@tool
async def call_site_tool(name: str, args: dict | None = None) -> str:
    """Run one of the website's actions.

    Args:
        name: The action's name only, for example "place_order".
        args: The action's arguments, as an object matching its inputSchema.
    """
    name, args = repair(name, args)
    if name == "pay_order" and not PAY_ALLOWED:
        return "ERROR: the user did not ask you to pay. Do not pay; tell them it is ready to pay."
    result = await page.evaluate("""async ([name, args]) => {
        const tool = (await document.modelContext.getTools()).find(t => t.name === name);
        if (!tool) return "ERROR: no tool named " + name;
        try { return JSON.stringify(await document.modelContext.executeTool(tool, args)); }
        catch (e) { return "ERROR: " + e.message; }
    }""", [name, args or {}])
    if not str(result).startswith("ERROR"):
        await page.evaluate(SHOW_WHAT_CHANGED, [name, args or {}])
    return result


PROMPT = (
    "You help customers of Palace Road Tiffin Room through its website, which "
    "exposes actions to agents. Call list_site_tools to see what the site can do, "
    "then call_site_tool to do it."
)

RULES = (
    "Do exactly what the user asks: place an order, pay for it, or just answer a "
    "question about the menu. Only pay if the user asks you to. "
    "If they ask for something that is not on the menu, leave it out, still "
    "complete the rest of the task in full, and mention what you left out at the end. "
    "Finish the whole task in one go: never stop halfway to report or ask. "
    "Pickup is on the half hour between 07:00 and 20:30; pick the slot closest to "
    "what they asked for. If a detail is missing, use a sensible default (name "
    "'Guest', the next pickup slot after the current time) and say what you assumed. "
    "Never ask the user a question; finish the job with what you were given."
)


def prompt_for_now():
    """The rules, plus the clock, so "pickup in an hour" or "now" makes sense."""
    return PROMPT + " " + RULES + f" The time now is {datetime.now():%H:%M}."



# ------------------------------------------------- show what the agent does
# Everything the agent does streams into the side panel docked on the right of
# the website (site/hud.js) and into the terminal, as it happens.


def SHOWN_AS(tool_use):
    """For the panel: show the website's own tool, not the call_site_tool wrapper."""
    name, args = tool_use["name"], tool_use.get("input") or {}
    if name == "call_site_tool":
        return args.get("name", name), args.get("args") or {}
    return name, args


class LivePanel(HookProvider):
    """Strands hooks: report every model call and tool call, live."""

    def __init__(self, page):
        self.page = page
        self.calls = 0
        self.models = 0
        self.numbers = {}  # toolUseId -> call number, to match results to calls

    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(BeforeModelCallEvent, self.before_model)
        registry.add_callback(AfterModelCallEvent, self.after_model)
        registry.add_callback(BeforeToolCallEvent, self.before_tool)
        registry.add_callback(AfterToolCallEvent, self.after_tool)

    async def show(self, js, *args):
        try:
            await self.page.evaluate(js, list(args))
        except Exception:
            pass  # the panel is decoration: never let it break a run

    async def before_model(self, event):
        self.models += 1
        await self.show("a => window.AgentPanel.thinking(a[0])", self.models)

    async def after_model(self, event):
        await self.update_tokens(event.agent)

    async def update_tokens(self, agent):
        try:
            usage = agent.event_loop_metrics.accumulated_usage
            await self.show("a => window.AgentPanel.tokens(a[0])", usage["inputTokens"] + usage["outputTokens"])
        except Exception:
            pass

    async def before_tool(self, event):
        self.calls += 1
        self.numbers[event.tool_use["toolUseId"]] = self.calls
        name, args = SHOWN_AS(event.tool_use)
        print(f"  {self.calls:>2}. {name}({json.dumps(args)})"[:100])
        await self.show("a => window.AgentPanel.call(a[0], a[1], a[2])", self.calls, name, args)
        await self.update_tokens(event.agent)  # usage is settled once the model has replied

        if self.calls > 20:  # safety net: stop a run that goes in circles
            event.cancel_tool = "Stopped: too many tool calls."
            event.agent.cancel(message="Gave up after 20 tool calls.")

    async def after_tool(self, event):
        n = self.numbers.get(event.tool_use["toolUseId"], self.calls)
        content = event.result.get("content") or [{}]
        text = " ".join(str(content[0].get("text", "")).split())
        ok = event.result.get("status") == "success" and not text.startswith("ERROR")
        await self.show("a => window.AgentPanel.result(a[0], a[1], a[2])", n, ok, text[:240])


# ------------------------------------------------------------------- run it


async def ask_for_order():
    """Type the order in the side panel on the website, where the room can see it.

    After you press Enter there is a 3-2-1 countdown, then the agent starts.
    Leave the box empty to run the example order.
    """
    print("Type your order in the side panel on the website, then press Enter.")
    await page.bring_to_front()
    await page.evaluate("t => window.AgentPanel.ask({ fallback: t })", TASK)
    await page.wait_for_function("window.__agentGo === true", timeout=0, polling=100)
    return await page.evaluate("window.__agentTask")


async def place_window(tab, left, top, width, height):
    """Move and size the Chrome window, so it fills the screen."""
    cdp = await tab.context.new_cdp_session(tab)
    window = await cdp.send("Browser.getWindowForTarget")
    await cdp.send("Browser.setWindowBounds", {
        "windowId": window["windowId"],
        "bounds": {"left": left, "top": top, "width": width, "height": height},
    })


async def main():
    global page, PAY_ALLOWED

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome", headless=False, args=["--enable-features=WebMCP"],
        )

        # One window, filling the screen. The agent panel docks inside the site.
        page = await browser.new_page(no_viewport=True)
        x, y, w, h = await page.evaluate(
            "[screen.availLeft || 0, screen.availTop || 0, screen.availWidth, screen.availHeight]")
        await place_window(page, x, y, w, h)

        # Open the site with WebMCP already ON (?webmcp=1 flips the switch on load).
        await page.goto(SITE + "?webmcp=1")
        await page.wait_for_function("window.CanteenWebMCP && window.CanteenWebMCP.on && window.AgentHUD")
        await page.evaluate("window.Canteen.reset()")
        await page.evaluate("window.AgentPanel.ready({ mode: 'on' })")

        # The site is on screen. Type the order in its side panel, live.
        print(f"\nWITH WebMCP  ·  {MODEL}\nSite: {SITE}")
        task = await ask_for_order()  # always typed in the side panel
        print(f"Task: {task}\n")

        # Spending money needs your say-so, in code, not just in the prompt.
        PAY_ALLOWED = bool(re.search(r"\b(pay|paid|upi)\b", task, re.I))

        previous = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
        await page.evaluate("a => window.AgentPanel.start(a)", {"mode": "on", "task": task, "previous": previous})

        live = LivePanel(page)
        agent = Agent(
            model=BedrockModel(model_id=MODEL, region_name="us-east-1", max_tokens=2048),
            tools=[list_site_tools, call_site_tool],
            system_prompt=prompt_for_now(),
            hooks=[live],
            callback_handler=None,
        )

        start = time.perf_counter()
        result = await agent.invoke_async(task)
        seconds = time.perf_counter() - start

        usage = result.metrics.accumulated_usage
        order = await page.evaluate("window.__lastOrder")
        run = {
            "ok": order is not None,
            "calls": live.calls,
            "models": result.metrics.cycle_count,
            "tokens": usage["inputTokens"] + usage["outputTokens"],
            "wall_ms": round(seconds * 1000),
        }
        await page.evaluate("a => window.AgentPanel.finish(a)", {**run, "reply": str(result).strip()})

        print(f"\n{'─' * 46}")
        print("  WITH WebMCP")
        print(f"  tool calls     {live.calls}")
        print(f"  model calls    {result.metrics.cycle_count}")
        print(f"  time           {seconds:.1f} s")
        print(f"  tokens in      {usage['inputTokens']:,}")
        print(f"  tokens out     {usage['outputTokens']:,}")
        if order:
            items = ", ".join(f"{i['qty']} x {i['id']}" for i in order["items"])
            print(f"  order          {order['orderId']} · {items} · {order['name']} · {order['pickup']}")
            if order.get("notes"):
                print(f"  notes          {order['notes']}")
            print(f"  paid           {'yes' if await page.evaluate('window.__paid') else 'no'}")
        else:
            print("  order          none placed")
        print(f"{'─' * 46}")
        print(f"  agent says: {str(result).strip()}\n")

        previous["on"] = run
        RESULTS.parent.mkdir(exist_ok=True)
        RESULTS.write_text(json.dumps(previous, indent=2))

        # Chrome stays open until you close its window yourself.
        print("Chrome stays open. Close the Chrome window when you are done.")
        try:
            await page.wait_for_event("close", timeout=0)
        except Exception:
            pass  # Chrome was quit entirely, which also ends the wait
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

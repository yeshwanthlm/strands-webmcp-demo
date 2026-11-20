"""The two ways an agent can use the canteen site.

Arm A (no WebMCP) gets what a browser-driving agent gets today: an outline of
the page, plus click / fill / select. This is the same shape of toolset that
Playwright MCP and Chrome DevTools MCP hand to a model, so it is a fair
baseline and not a strawman.

Arm B (WebMCP) gets two tools: list what the page offers, and call one of them.

Everything else is held constant: same model, same site, same request, same
success check.
"""

from __future__ import annotations

import asyncio
import json

from strands import tool
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

# The live Playwright page, set by whichever runner is driving.
PAGE = None
ACTION_TIMEOUT_MS = 5000

# A browser has one keyboard and one focus. Strands may run several tool calls
# in the same cycle, and concurrent Playwright actions steal focus from each
# other: three parallel fills once put "2", "1" and "Yeshwanth" all into the
# name box as "21Yeshwanth". Real browser-driving agents serialise for the same
# reason, so this lock makes the baseline fair rather than sabotaged.
BROWSER = asyncio.Lock()


def set_page(page) -> None:
    global PAGE
    PAGE = page


def _err(exc: Exception) -> str:
    """Hand failures back to the model as text, the way a real agent sees them."""
    first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else repr(exc)
    return f"ERROR: {first_line}"


# --------------------------------------------------------------------------
# Arm A — no WebMCP. Drive the page like a human would.
# --------------------------------------------------------------------------


@tool
async def read_page() -> str:
    """Read the current page as an outline of its headings, text and form fields.

    Use this first, and again after anything changes, to see what is on screen.
    """
    async with BROWSER:
        try:
            return await PAGE.locator("body").aria_snapshot()
        except Exception as exc:
            return _err(exc)


@tool
async def fill_field(label: str, value: str) -> str:
    """Type a value into the form field with the given label.

    Args:
        label: The field's visible label, e.g. "Your name" or "Masala Dosa quantity".
        value: The text to put in it.
    """
    async with BROWSER:
        try:
            await PAGE.get_by_label(label, exact=False).first.fill(
                value, timeout=ACTION_TIMEOUT_MS
            )
            return f"filled {label!r} with {value!r}"
        except Exception as exc:
            return _err(exc)


@tool
async def select_option(label: str, option: str) -> str:
    """Choose an option in the dropdown with the given label.

    Args:
        label: The dropdown's visible label, e.g. "Pickup time".
        option: The option to choose, by its visible text or its value.
    """
    async with BROWSER:
        target = PAGE.get_by_label(label, exact=False).first
        try:
            await target.select_option(value=option, timeout=ACTION_TIMEOUT_MS)
            return f"selected {option!r} in {label!r}"
        except Exception:
            try:
                await target.select_option(label=option, timeout=ACTION_TIMEOUT_MS)
                return f"selected {option!r} in {label!r}"
            except Exception as exc:
                return _err(exc)


@tool
async def click_button(name: str) -> str:
    """Click the button with the given visible text.

    Args:
        name: The button's text, e.g. "Place order".
    """
    async with BROWSER:
        try:
            await PAGE.get_by_role("button", name=name).first.click(
                timeout=ACTION_TIMEOUT_MS
            )
            return f"clicked {name!r}"
        except Exception as exc:
            return _err(exc)


# --------------------------------------------------------------------------
# Arm B — WebMCP. Ask the page what it does, then do it.
# --------------------------------------------------------------------------

_LIST_TOOLS_JS = """async () => {
  if (!document.modelContext) return null;
  const tools = await document.modelContext.getTools();
  return tools.map(t => ({
    name: t.name,
    description: t.description,
    inputSchema: t.inputSchema,
  }));
}"""

_CALL_TOOL_JS = """async ([name, args]) => {
  if (!document.modelContext) return "ERROR: this page offers no agent tools";
  const tools = await document.modelContext.getTools();
  const tool = tools.find(t => t.name === name);
  if (!tool) {
    return "ERROR: no tool named " + name +
           ". Available: " + tools.map(t => t.name).join(", ");
  }
  try {
    return JSON.stringify(await document.modelContext.executeTool(tool, args));
  } catch (e) {
    return "ERROR: " + e.message;
  }
}"""


@tool
async def list_site_tools() -> str:
    """List the actions this website offers to agents, with their input schemas.

    Call this first. It tells you exactly what you can do and what each action needs.
    """
    async with BROWSER:
        try:
            tools = await PAGE.evaluate(_LIST_TOOLS_JS)
        except Exception as exc:
            return _err(exc)
    if tools is None:
        return "ERROR: this page offers no agent tools (document.modelContext missing)"
    return json.dumps(tools)


@tool
async def call_site_tool(name: str, args: dict | None = None) -> str:
    """Run one of this site's actions.

    Args:
        name: The action's name only, exactly as given by list_site_tools,
            e.g. "place_order". Nothing else goes in this field.
        args: The arguments object, matching that action's inputSchema.
            Pass an empty object when the action takes nothing.
    """
    # Nova sometimes leaks its own call syntax into the name, e.g.
    # 'get_menu>\n<__parameter=args>{...}'. Answer with a plain, fixable error
    # instead of a schema-validation failure it cannot read its way out of.
    if not name or any(ch in name for ch in "<>{}\n "):
        return ("ERROR: 'name' must be just the action name, like \"place_order\". "
                "Put the arguments in 'args' as an object, not inside 'name'.")
    # Some models hand this back as a JSON string rather than an object.
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError as exc:
            return f"ERROR: args is not valid JSON ({exc.msg})"
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return 'ERROR: args must be an object, e.g. {"orderId": "PR001"}'
    async with BROWSER:
        try:
            return await PAGE.evaluate(_CALL_TOOL_JS, [name, args])
        except Exception as exc:
            return _err(exc)


# --------------------------------------------------------------------------
# A safety net, the same for both arms
# --------------------------------------------------------------------------


class ToolBudget(HookProvider):
    """Stop a run that is going in circles, instead of letting it spin forever.

    A model can get stuck repeating one malformed call. Past the budget the
    run is cancelled and scored as a failure. Both arms get the same budget,
    and a healthy run of either uses well under half of it.
    """

    def __init__(self, max_calls: int = 20) -> None:
        self.max_calls = max_calls
        self.calls = 0

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self._count)

    def _count(self, event: BeforeToolCallEvent) -> None:
        self.calls += 1
        if self.calls > self.max_calls:
            event.cancel_tool = f"Stopped: more than {self.max_calls} tool calls."
            event.agent.cancel(message=f"Gave up after {self.max_calls} tool calls.")


# --------------------------------------------------------------------------
# Arm definitions
# --------------------------------------------------------------------------

PROMPT_A = (
    "You order food on a campus canteen website by operating the page itself.\n"
    "Call read_page to see what is on screen. Use fill_field, select_option and "
    "click_button to complete the order. Read the page again after you submit to "
    "check it worked.\n"
    "Never ask the user a question. Work with what you were given."
)

PROMPT_B = (
    "You order food on a campus canteen website that exposes actions to agents.\n"
    "Call list_site_tools to see what the site can do and what each action needs, "
    "then call call_site_tool to do it.\n"
    "Never ask the user a question. Work with what you were given."
)

ARMS = {
    "A_no_webmcp": {
        "label": "Arm A — no WebMCP",
        "query": "",
        "tools": [read_page, fill_field, select_option, click_button],
        "system_prompt": PROMPT_A,
    },
    "B_webmcp": {
        "label": "Arm B — WebMCP",
        "query": "?webmcp=1",
        "tools": [list_site_tools, call_site_tool],
        "system_prompt": PROMPT_B,
    },
}


# --------------------------------------------------------------------------
# The task and its success check
# --------------------------------------------------------------------------

TASK = "Order 2 masala dosas and 1 filter coffee for Yeshwanth, pickup at 1 pm."

EXPECTED = {
    "items": {"dosa": 2, "coffee": 1},
    "name": "Yeshwanth",
    "pickup": "13:00",  # the model has to turn "1 pm" into this
}


async def check(page) -> tuple[bool, str]:
    """Did the right order actually land? Same check for both arms."""
    order = await page.evaluate("window.__lastOrder || null")
    if not order:
        return False, "no order was placed"
    got = {i["id"]: i["qty"] for i in order["items"]}
    if got != EXPECTED["items"]:
        return False, f"wrong items: {got} != {EXPECTED['items']}"
    if order["name"].strip().lower() != EXPECTED["name"].lower():
        return False, f"wrong name: {order['name']!r}"
    if order["pickup"] != EXPECTED["pickup"]:
        return False, f"wrong pickup: {order['pickup']!r} != {EXPECTED['pickup']!r}"
    return True, "ok"

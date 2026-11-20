"""Presentation helpers: live tool tracing and the comparison views.

Everything here exists to make a projector-friendly notebook. The benchmark
itself does not need any of it.
"""

from __future__ import annotations

import json
from pathlib import Path

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry

RESULTS = Path(__file__).resolve().parent.parent.parent / "results" / "results.json"


class LiveTrace(HookProvider):
    """Print every tool call as it happens, so the room can count along.

        trace = LiveTrace()
        agent = Agent(..., hooks=[trace])
    """

    def __init__(self, show_results: bool = True, width: int = 92) -> None:
        self.show_results = show_results
        self.width = width
        self.steps: list[dict] = []

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self._before)
        registry.add_callback(AfterToolCallEvent, self._after)

    def _before(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        args = event.tool_use.get("input") or {}
        shown = json.dumps(args)
        if len(shown) > self.width:
            shown = shown[: self.width - 3] + "..."
        n = len(self.steps) + 1
        self.steps.append({"n": n, "tool": name, "args": args})
        print(f"  {n}. {name}({shown})")

    def _after(self, event: AfterToolCallEvent) -> None:
        if not self.show_results:
            return
        try:
            text = event.result["content"][0].get("text", "")
        except Exception:
            text = str(event.result)
        text = " ".join(str(text).split())
        if len(text) > self.width:
            text = text[: self.width - 3] + "..."
        print(f"       -> {text}")

    @property
    def count(self) -> int:
        return len(self.steps)


def _label(tool_use: dict, width: int = 44) -> str:
    """Short text for one tool call, for the on-page panel."""
    name = tool_use["name"]
    args = tool_use.get("input") or {}
    if name == "call_site_tool":           # show the WebMCP tool, not the wrapper
        name = args.get("name", name)
        args = args.get("args") or {}
    inner = ", ".join(f"{v}" if isinstance(v, str) else json.dumps(v)
                      for v in args.values())
    text = f"{name}({inner})"
    return text if len(text) <= width else text[: width - 1] + "…"


class PageHUD(HookProvider):
    """Push every tool call to the site's agent panel (site/hud.js), live."""

    def __init__(self, page) -> None:
        self.page = page

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self._step)

    async def _step(self, event: BeforeToolCallEvent) -> None:
        try:
            await self.page.evaluate(
                "label => window.AgentHUD && window.AgentHUD.step(label)",
                _label(event.tool_use),
            )
        except Exception:
            pass  # the panel is decoration; never let it break a run


async def set_webmcp(page, on: bool, visible_pause: float = 0.0) -> None:
    """Flip the site's WebMCP switch by clicking it, the way a person would."""
    import asyncio

    await page.wait_for_function("window.CanteenWebMCP !== undefined")
    if await page.evaluate("window.CanteenWebMCP.on") != on:
        if visible_pause:
            await asyncio.sleep(visible_pause)
        await page.click("#webmcp-toggle")
        await page.wait_for_function(f"window.CanteenWebMCP.on === {str(on).lower()}")
    if visible_pause:
        await asyncio.sleep(visible_pause)


async def run_arm(page, arm_key: str, ask: str | None = None, model_id: str | None = None,
                  setup=None, hud: bool = True, flip_switch: bool = False):
    """One narrated run, for the notebook. Returns the numbers for compare().

    `setup` is an async callable taking the page, run after the page has loaded
    and been reset but before the agent starts. Use it to change the page for
    this run — registering an extra tool, for instance. Anything done before
    calling run_arm is lost, because this navigates first.
    """
    import os
    import time

    from strands import Agent
    from strands.models import BedrockModel

    import arms
    from browser import url_for

    arm = arms.ARMS[arm_key]
    ask = ask or arms.TASK
    model_id = model_id or os.environ.get("BENCH_MODEL", "us.amazon.nova-2-lite-v1:0")

    webmcp_on = arm_key == "B_webmcp"

    if flip_switch:
        # Open the plain site, then click the switch on screen, so the room
        # sees exactly what changes between the two runs.
        await page.goto(url_for(""))
        await page.wait_for_function("window.Canteen !== undefined")
        await set_webmcp(page, webmcp_on, visible_pause=0.8)
    else:
        await page.goto(url_for(arm["query"]))
        await page.wait_for_function("window.Canteen !== undefined")
    await page.evaluate("window.Canteen.reset()")
    if setup is not None:
        await setup(page)
    arms.set_page(page)

    mode = "on" if webmcp_on else "off"
    if hud:
        await page.evaluate("a => window.AgentHUD && window.AgentHUD.start(a)",
                            {"mode": mode, "task": ask})

    print(f"{arm['label']}\n  asking: {ask}\n")
    trace = LiveTrace()
    hooks = [trace, arms.ToolBudget()] + ([PageHUD(page)] if hud else [])
    agent = Agent(
        model=BedrockModel(model_id=model_id,
                           region_name=os.environ.get("AWS_REGION", "us-east-1"),
                           max_tokens=2048),
        tools=arm["tools"],
        system_prompt=arm["system_prompt"],
        hooks=hooks,
        callback_handler=None,  # silence Strands' own printing; LiveTrace is the narration
    )

    started = time.perf_counter()
    result = await agent.invoke_async(ask)
    wall = time.perf_counter() - started

    ok, why = await arms.check(page)
    print(f"\n  {trace.count} tool calls, {wall:.1f}s, "
          f"{'correct order' if ok else 'WRONG: ' + why}")
    out = summarise(result, trace, ok, why)
    out["wall_s"] = round(wall, 1)
    out["reply"] = str(result)

    if hud:
        tokens = out["input_tokens"] + out["output_tokens"]
        summary = (f"Correct order · {trace.count} steps · {wall:.1f}s" if ok
                   else f"Wrong: {why}")
        await page.evaluate(
            "a => window.AgentHUD && window.AgentHUD.finish(a)",
            {"mode": mode, "ok": ok, "steps": trace.count, "tokens": tokens,
             "wall_ms": round(wall * 1000), "summary": summary},
        )
    return out


def summarise(result, trace: LiveTrace, ok: bool, why: str) -> dict:
    """Pull the numbers that go on the slide out of one agent run."""
    usage = result.metrics.accumulated_usage
    return {
        "correct": ok,
        "why": why,
        "steps": trace.count,
        "cycles": result.metrics.cycle_count,
        "input_tokens": usage["inputTokens"],
        "output_tokens": usage["outputTokens"],
        "model_ms": result.metrics.accumulated_metrics["latencyMs"],
    }


# ---------------------------------------------------------------- rendering

_CSS = """
<style>
.scd { font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
.scd table { border-collapse: collapse; width: 100%; margin: 8px 0 4px; }
.scd th, .scd td { padding: 10px 14px; text-align: left;
  border-bottom: 1px solid rgba(128,128,128,0.3); }
.scd th { font-size: 13px; text-transform: uppercase; letter-spacing: .5px;
  opacity: .65; font-weight: 600; }
.scd td.n { font-variant-numeric: tabular-nums; font-size: 22px; font-weight: 650; }
.scd .win { color: #ff9900; }
.scd .lose { opacity: .72; }
.scd .delta { font-size: 13px; opacity: .8; font-weight: 500; }
.scd h3 { margin: 18px 0 2px; font-size: 16px; }
.scd .sub { opacity: .65; font-size: 13px; margin: 0 0 10px; }
.scd .ok { color: #35c08a; font-weight: 600; }
.scd .bad { color: #ff6b6b; font-weight: 600; }
</style>
"""

_ROWS = [
    ("steps", "Tool calls", "lower"),
    ("cycles", "Model round trips", "lower"),
    ("input_tokens", "Input tokens", "lower"),
    ("output_tokens", "Output tokens", "lower"),
    ("model_ms", "Model time (ms)", "lower"),
]


def compare(a: dict, b: dict, title: str = "Same model. Same request."):
    """Side-by-side of two runs, with the change spelled out."""
    from IPython.display import HTML

    def verdict(run):
        return ('<span class="ok">correct order</span>' if run["correct"]
                else f'<span class="bad">wrong: {run["why"]}</span>')

    body = [
        _CSS,
        '<div class="scd">',
        f"<h3>{title}</h3>",
        '<p class="sub">Arm A drives the page. Arm B calls the tools the page declares.</p>',
        "<table><tr><th></th><th>No WebMCP</th><th>WebMCP</th><th>Change</th></tr>",
        f"<tr><td>Result</td><td>{verdict(a)}</td><td>{verdict(b)}</td><td></td></tr>",
    ]
    for key, label, _ in _ROWS:
        av, bv = a[key], b[key]
        pct = f"{(bv - av) / av * 100:+.0f}%" if av else "—"
        a_cls = "n win" if av < bv else "n lose"
        b_cls = "n win" if bv < av else "n lose"
        body.append(
            f"<tr><td>{label}</td>"
            f'<td class="{a_cls}">{av:,}</td>'
            f'<td class="{b_cls}">{bv:,}</td>'
            f'<td class="delta">{pct}</td></tr>'
        )
    body.append("</table></div>")
    return HTML("".join(body))


def benchmark_table(path: Path = RESULTS):
    """The saved ten-run result, rendered for the projector."""
    import statistics

    from IPython.display import HTML

    if not path.exists():
        return HTML(f"<p>No results at {path}. Run benchmark.py first.</p>")

    data = json.loads(path.read_text())
    meta, runs = data["meta"], data["runs"]
    med = lambda rs, k: statistics.median([r[k] for r in rs])

    cols = [("tool_calls", "Tool calls"), ("cycles", "Cycles"),
            ("input_tokens", "Input tok"), ("output_tokens", "Output tok"),
            ("wall_s", "Wall s")]

    head = "".join(f"<th>{label}</th>" for _, label in cols)
    body = [
        _CSS, '<div class="scd">',
        f"<h3>{meta['runs_per_arm']} runs of each, median</h3>",
        f'<p class="sub">{meta["model_id"]} &middot; {meta["region"]} &middot; '
        f'recorded {meta["recorded_at"][:10]}</p>',
        f"<table><tr><th>Arm</th><th>Correct</th>{head}</tr>",
    ]
    for arm_key, rs in runs.items():
        wins = sum(r["ok"] for r in rs)
        cells = "".join(f'<td class="n">{med(rs, k):,.0f}</td>' for k, _ in cols)
        body.append(
            f'<tr><td>{meta["labels"].get(arm_key, arm_key)}</td>'
            f'<td class="ok">{wins}/{len(rs)}</td>{cells}</tr>'
        )
    body.append("</table></div>")
    return HTML("".join(body))


def show_file(path: str, lang: str = "javascript", first: int = None, last: int = None):
    """Print a file (or a slice of it) with syntax colour, for the code slide."""
    from IPython.display import Code

    text = Path(path).read_text()
    if first or last:
        lines = text.splitlines()
        text = "\n".join(lines[(first or 1) - 1: last or len(lines)])
    return Code(text, language=lang)

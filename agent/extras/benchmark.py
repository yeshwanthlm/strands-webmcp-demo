"""Run the same task, with the same model, both ways. Record what it cost.

    python benchmark.py                 # 10 runs of each arm
    python benchmark.py --runs 3        # quick check
    python benchmark.py --arm B_webmcp  # one arm only
    python benchmark.py --headless      # no visible window (Arm B needs the flag)

Writes ../results/results.json, then print a table with report.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright
from strands import Agent
from strands.models import BedrockModel

import arms
from browser import launch, url_for

MODEL_ID = os.environ.get("BENCH_MODEL", "us.amazon.nova-2-lite-v1:0")
REGION = os.environ.get("AWS_REGION", "us-east-1")
RUN_TIMEOUT_S = float(os.environ.get("BENCH_RUN_TIMEOUT", "120"))
# Default output cap is small; a long place_order argument string can hit it
# mid-JSON and abort the run. Same value for both arms, so the comparison holds.
MAX_TOKENS = int(os.environ.get("BENCH_MAX_TOKENS", "2048"))
RESULTS = Path(__file__).resolve().parent.parent.parent / "results" / "results.json"


def blank_run(note: str) -> dict:
    return {
        "ok": False,
        "why": note,
        "cycles": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "model_latency_ms": 0,
        "wall_s": 0.0,
        "tool_calls": 0,
        "tool_errors": 0,
        "tools_used": {},
    }


async def one_run(page, arm_key: str, arm: dict) -> dict:
    """One clean attempt at the task. Never raises."""
    await page.goto(url_for(arm["query"]))
    await page.wait_for_function("window.Canteen !== undefined")
    await page.evaluate("window.Canteen.reset()")
    arms.set_page(page)

    agent = Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION, max_tokens=MAX_TOKENS),
        tools=arm["tools"],
        system_prompt=arm["system_prompt"],
        hooks=[arms.ToolBudget()],
        callback_handler=None,
    )

    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            agent.invoke_async(arms.TASK), timeout=RUN_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        row = blank_run(f"gave up after {RUN_TIMEOUT_S:.0f}s")
        row["wall_s"] = round(time.perf_counter() - started, 1)
        return row
    except Exception as exc:  # model throttling, browser crash, anything
        row = blank_run(f"crashed: {str(exc).splitlines()[0][:120]}")
        row["wall_s"] = round(time.perf_counter() - started, 1)
        return row

    wall = time.perf_counter() - started
    ok, why = await arms.check(page)

    usage = result.metrics.accumulated_usage
    tool_metrics = result.metrics.tool_metrics
    return {
        "ok": ok,
        "why": why,
        "cycles": result.metrics.cycle_count,
        "input_tokens": usage["inputTokens"],
        "output_tokens": usage["outputTokens"],
        "model_latency_ms": result.metrics.accumulated_metrics["latencyMs"],
        "wall_s": round(wall, 1),
        "tool_calls": sum(m.call_count for m in tool_metrics.values()),
        "tool_errors": sum(m.error_count for m in tool_metrics.values()),
        "tools_used": {name: m.call_count for name, m in tool_metrics.items()},
        "stop_reason": str(result.stop_reason),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--arm", choices=list(arms.ARMS), default=None)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--pause", type=float, default=2.0,
                        help="seconds between runs, to stay under Bedrock rate limits")
    args = parser.parse_args()

    selected = {args.arm: arms.ARMS[args.arm]} if args.arm else dict(arms.ARMS)
    rows: dict[str, list[dict]] = {}

    async with async_playwright() as p:
        context, page = await launch(p, headless=args.headless)

        if "B_webmcp" in selected:
            await page.goto(url_for("?webmcp=1"))
            has_api = await page.evaluate("!!document.modelContext")
            if not has_api:
                print("\n  document.modelContext is missing in this Chrome.")
                print("  Arm B cannot run. Fix it with:  python doctor.py\n")
                selected.pop("B_webmcp")
                if not selected:
                    await context.close()
                    return

        for arm_key, arm in selected.items():
            print(f"\n=== {arm['label']}  ({args.runs} runs)")
            runs = []
            for i in range(args.runs):
                row = await one_run(page, arm_key, arm)
                runs.append(row)
                mark = "PASS" if row["ok"] else "FAIL"
                print(
                    f"  run {i + 1:>2}  {mark}  "
                    f"cycles={row['cycles']:<3} "
                    f"in={row['input_tokens']:<7} "
                    f"wall={row['wall_s']:<6} "
                    f"{'' if row['ok'] else row['why'][:60]}"
                )
                if args.pause:
                    await asyncio.sleep(args.pause)
            rows[arm_key] = runs

        await context.close()

    payload = {
        "meta": {
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model_id": MODEL_ID,
            "region": REGION,
            "task": arms.TASK,
            "expected": arms.EXPECTED,
            "runs_per_arm": args.runs,
            "labels": {k: v["label"] for k, v in arms.ARMS.items()},
        },
        "runs": rows,
    }
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {RESULTS}")

    med = lambda rs, k: statistics.median([r[k] for r in rs]) if rs else 0
    print(f"\n{'arm':14}{'wins':>8}{'cycles':>9}{'in-tok':>10}{'wall s':>9}")
    for arm_key, rs in rows.items():
        print(
            f"{arm_key:14}{sum(r['ok'] for r in rs):>4}/{len(rs):<3}"
            f"{med(rs, 'cycles'):>9.0f}{med(rs, 'input_tokens'):>10.0f}"
            f"{med(rs, 'wall_s'):>9.1f}"
        )
    print("\nFull table:  python report.py")


if __name__ == "__main__":
    asyncio.run(main())

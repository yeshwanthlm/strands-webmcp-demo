"""Turn results.json into the table that goes on the slide.

    python report.py
    python report.py --price-in 0.06 --price-out 0.24   # USD per 1M tokens
    python report.py --markdown > ../results/RESULTS.md

Prices are not hardcoded on purpose. Look them up on the Amazon Bedrock
pricing page on the day, so the number on your slide is defensible.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent.parent / "results" / "results.json"


def med(rows, key):
    return statistics.median([r[key] for r in rows]) if rows else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-in", type=float, default=None,
                        help="USD per 1M input tokens")
    parser.add_argument("--price-out", type=float, default=None,
                        help="USD per 1M output tokens")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    if not RESULTS.exists():
        raise SystemExit(f"no results yet at {RESULTS} — run benchmark.py first")

    data = json.loads(RESULTS.read_text())
    meta, runs = data["meta"], data["runs"]

    print(f"# Benchmark: {meta['task']}\n")
    print(f"- Model: `{meta['model_id']}` in {meta['region']}")
    print(f"- Runs per arm: {meta['runs_per_arm']}")
    print(f"- Recorded: {meta['recorded_at']}\n")

    header = ["Arm", "Wins", "Cycles", "Tool calls", "Input tok", "Output tok",
              "Model ms", "Wall s", "Tool errors"]
    if args.price_in is not None:
        header.append("Cost / 1k runs")

    rows_out = []
    for arm_key, rs in runs.items():
        label = meta["labels"].get(arm_key, arm_key)
        row = [
            label,
            f"{sum(r['ok'] for r in rs)}/{len(rs)}",
            f"{med(rs, 'cycles'):.0f}",
            f"{med(rs, 'tool_calls'):.0f}",
            f"{med(rs, 'input_tokens'):.0f}",
            f"{med(rs, 'output_tokens'):.0f}",
            f"{med(rs, 'model_latency_ms'):.0f}",
            f"{med(rs, 'wall_s'):.1f}",
            f"{sum(r['tool_errors'] for r in rs)}",
        ]
        if args.price_in is not None:
            cost = (med(rs, "input_tokens") * args.price_in
                    + med(rs, "output_tokens") * (args.price_out or 0)) / 1_000_000
            row.append(f"${cost * 1000:.2f}")
        rows_out.append(row)

    widths = [max(len(h), *(len(r[i]) for r in rows_out)) for i, h in enumerate(header)]
    line = lambda cells: "| " + " | ".join(
        c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"
    print(line(header))
    print("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    for r in rows_out:
        print(line(r))

    print("\n## Why runs failed\n")
    for arm_key, rs in runs.items():
        fails = [r["why"] for r in rs if not r["ok"]]
        label = meta["labels"].get(arm_key, arm_key)
        if not fails:
            print(f"- **{label}**: no failures.")
            continue
        print(f"- **{label}**: {len(fails)} of {len(rs)} failed.")
        for why in sorted(set(fails)):
            print(f"  - {why}  (x{fails.count(why)})")

    print("\n## Tools each arm reached for\n")
    for arm_key, rs in runs.items():
        tally: dict[str, int] = {}
        for r in rs:
            for name, n in r.get("tools_used", {}).items():
                tally[name] = tally.get(name, 0) + n
        label = meta["labels"].get(arm_key, arm_key)
        parts = ", ".join(f"`{k}` x{v}" for k, v in sorted(tally.items(),
                                                           key=lambda x: -x[1]))
        print(f"- **{label}**: {parts or 'none'}")

    if args.price_in is None:
        print("\n> Cost column omitted. Re-run with --price-in and --price-out "
              "using today's Bedrock pricing.")


if __name__ == "__main__":
    main()

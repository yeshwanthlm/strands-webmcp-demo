# Benchmark: Order 2 masala dosas and 1 filter coffee for Yeshwanth, pickup at 1 pm.

- Model: `us.amazon.nova-2-lite-v1:0` in us-east-1
- Runs per arm: 10
- Recorded: 2026-11-20T17:47:13+00:00

| Arm               | Wins  | Cycles | Tool calls | Input tok | Output tok | Model ms | Wall s | Tool errors |
|-------------------|-------|--------|------------|-----------|------------|----------|--------|-------------|
| Arm A — no WebMCP | 10/10 | 5      | 8          | 16081     | 259        | 3872     | 6.8    | 0           |
| Arm B — WebMCP    | 10/10 | 3      | 2          | 4757      | 154        | 1964     | 3.5    | 0           |

## Why runs failed

- **Arm A — no WebMCP**: no failures.
- **Arm B — WebMCP**: no failures.

## Tools each arm reached for

- **Arm A — no WebMCP**: `click_button` x40, `read_page` x20, `fill_field` x10, `select_option` x10
- **Arm B — WebMCP**: `list_site_tools` x10, `call_site_tool` x10

> Cost column omitted. Re-run with --price-in and --price-out using today's Bedrock pricing.

# My website can talk to an AI agent. I added it in 20 lines.

### Demo Prompts:

```
Get me 3 idli vada and a badam milk for Asha, pickup at 9:30 in the morning. Less spicy please.

Order one Mysore Pak and one Kesari Bath for Ravi at 6 pm, and pay for it.
```

AWS Student Community Day Mysuru, 2026.

**Palace Road Tiffin Room** is one ordinary restaurant website with a
**WebMCP switch** in its header. Two Strands agents place the same order on it,
one with WebMCP and one without. Same model, same request.

The shop is invented. Everything else is real.

Live site: https://d2gk3ykaq9ah2.cloudfront.net/

## Run the two agents

```
cd /Users/yeshwanthlm/Documents/scd-mysuru-2026/agent
../.venv/bin/python agent_without_webmcp.py
../.venv/bin/python agent_with_webmcp.py
```

Each one opens Chrome by itself and clicks the WebMCP switch. Then the side
panel on the right of the site asks what to do. Type the order there, where the
audience can see it, and press Enter:

```
What should the agent do?
Order 2 masala dosas and 1 filter coffee for Yeshwanth, pickup at 1 pm.
```

A 3-2-1 countdown runs, then the agent starts, so everyone is watching when it
moves. The timer starts after the countdown. Type the same order for both agents. Leave the box empty to run that example.
The panel scrolls with the mouse wheel.

While it works, everything it touches lights up on the site:

| Colour | Meaning |
|---|---|
| Pink + ripple | Clicking a button |
| Cyan box | Typing into a field |
| Purple | Picking from a dropdown |
| Amber | Changed by a WebMCP tool |

If the element is off screen, the page scrolls to it first. The scroll is
instant and the glow fades by itself, so the agent never waits and the timing
stays fair.

A **side panel** docks on the right of the website while the agent runs. The
site moves over to make room, so nothing is covered. It streams every model
call and tool call as it happens: the tool, its arguments, what came back, and
how long it took. Live counters show time, tool calls, model calls and tokens.
When the run ends it shows the result, and once both agents have run, the two
side by side. People browsing the site never see it, and it is hidden from the
agent, so it cannot change the result.

To start the side-by-side table fresh, delete `results/last_runs.json`.

The terminal shows the same steps. At the end you get:

```
  WITH WebMCP
  tool calls     2
  model calls    3
  time           3.7 s
  tokens in      4,256
  tokens out     137
  order          PR001 · 2 x dosa, 1 x coffee · Yeshwanth · 13:00
```

Run both, and the side panel shows them side by side.

### What you can ask

Anything a customer would. Both agents do what you type, not a fixed script.

| You type | It does |
|---|---|
| any items, any quantities | orders exactly those |
| a pickup time from 7 AM to 8:30 PM | picks the closest half-hour slot |
| "less spicy", "extra chutney" | adds a kitchen note |
| "...and pay for it" | places the order, then pays |
| "Which drink is cheapest?" | answers, orders nothing |
| something not on the menu | leaves it out, orders the rest, tells you |
| no name or time | uses "Guest" and the next slot, and says so |

**Paying is locked in code.** The agent can only pay if your request says
"pay", "paid" or "UPI". Otherwise the pay action is refused, whatever the model
decides.

| Agent | Its tools | How it works |
|---|---|---|
| `agent_without_webmcp.py` | `read_page`, `fill_field`, `select_option`, `click_button` | Reads the page and clicks, like a person |
| `agent_with_webmcp.py` | `list_site_tools`, `call_site_tool` | Asks the site what it can do, then calls it |

Both use Strands with `us.amazon.nova-2-lite-v1:0` on Amazon Bedrock. Playwright
opens and drives Chrome.

## What is in here

```
agent/
  agent_without_webmcp.py   agent 1
  agent_with_webmcp.py      agent 2
  requirements.txt
  extras/                   benchmark, notebook, tests. not needed to run the agents

site/
  index.html, app.js        the restaurant, built for people
  webmcp.js                 the WebMCP layer and the switch
  hud.js                    the agent side panel and highlights (demo only)
  styles.css

infra/                      S3 + CloudFront, Terraform. see infra/LIVE.md
results/                    benchmark numbers and screenshots
```

## Setup, once

```
cd /Users/yeshwanthlm/Documents/scd-mysuru-2026
python3 -m venv .venv
.venv/bin/pip install -r agent/requirements.txt
```

Needs Chrome 149 or newer and AWS credentials that can call Bedrock in
`us-east-1`. The agents start Chrome with `--enable-features=WebMCP`, so you do
not need to touch `chrome://flags` for them.

To use the site in your own Chrome, turn on
`chrome://flags/#enable-webmcp-testing` once and relaunch.

## Which site the agents use

Both agents always use the live site, https://d2gk3ykaq9ah2.cloudfront.net/.
It is set on the `SITE =` line near the top of each file, and printed when the
agent starts.

## The honest bit

It is **one website**, not two. The switch changes nothing a person can see. It
only registers or removes three tools.

The page is deliberately well built, with a real label on every control, so the
no-WebMCP agent gets the best page it could hope for. It still gets the order
right. It just takes more steps, more time and more tokens.

## Extras

All in `agent/extras/`. Run them from that folder.

| File | What it does |
|---|---|
| `benchmark.py` | 10 runs of each agent, writes `results/results.json` |
| `report.py` | Turns that into a table |
| `TALK.ipynb` | Notebook version of the talk, including the attack demo |
| `show.py` | Runs both agents in one Chrome window, back to back |
| `doctor.py` | Checks Bedrock, Chrome and WebMCP before the talk |
| `smoke_test.py` | 30 checks of the site, no Bedrock cost |

The extras use their own copy of the agent code in `arms.py`, so the benchmark
stays the same even if you edit the two agents.

### Two bugs worth knowing about, because each nearly faked a result

**My rig broke the no-WebMCP side.** Strands ran three fills at once, a browser
has one focus, and `"2"`, `"1"` and `"Yeshwanth"` all landed in the name box as
`"21Yeshwanth"`. Fixed with a lock so browser actions run one at a time.

**My rig broke the WebMCP side.** Passing tool arguments as a JSON string made
Nova loop and blow its output limit. A plain object argument fixed it, and
made it cheaper.

When a benchmark agrees with you on the first run, go looking for the bug.

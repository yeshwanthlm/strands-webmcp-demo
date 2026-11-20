/**
 * Palace Road Tiffin Room — the whole WebMCP layer.
 *
 * It adds no features. It only tells a visiting AI agent what this page can
 * already do, so the agent calls an action instead of hunting for a button.
 *
 * The switch in the header turns it on and off live:
 *   on  -> registerTool() for each tool below
 *   off -> abort the signal, and Chrome removes every tool
 * The URL keeps up (?webmcp=1), so a link or a test can open either state.
 *
 * Needs Chrome 149+ with WebMCP enabled. If the API is missing, the page
 * carries on working normally for humans and the switch says why.
 */

(() => {
  "use strict";

  const mc = document.modelContext;
  const supported = !!(mc && typeof mc.registerTool === "function");

  // Show each agent call in the Activity panel, so the room can watch.
  const announce = (name, fn) => async (args, options) => {
    Canteen.log(`agent called ${name}(${JSON.stringify(args ?? {})})`, "tool");
    return fn(args ?? {}, options);
  };

  // ------------------------------------------------------------- the tools

  const TOOLS = [
    {
      name: "get_menu",
      title: "Get today's menu",
      description:
        "List everything the tiffin room is serving today, with the item id to " +
        "use when ordering and the price in rupees.",
      inputSchema: { type: "object", properties: {} },
      annotations: { readOnlyHint: true },
      execute: announce("get_menu", async () => Canteen.getMenu()),
    },
    {
      name: "place_order",
      title: "Place a pickup order",
      description:
        "Create a pickup order at the tiffin room. Needs the items with " +
        "quantities, the customer's name, and a pickup time; kitchen notes are " +
        "optional. Placing a new order replaces the previous one. Returns an " +
        "order id. Fails with a reason if anything is missing or invalid.",
      inputSchema: {
        type: "object",
        required: ["items", "name", "pickup"],
        properties: {
          items: {
            type: "array",
            minItems: 1,
            description: "The items being ordered.",
            items: {
              type: "object",
              required: ["id", "qty"],
              properties: {
                id: {
                  type: "string",
                  enum: ["dosa", "idli", "rava", "setdosa", "kharabath",
                         "bisibele", "curdrice", "lemonrice",
                         "coffee", "badam", "chai", "mysorepak", "kesari"],
                  description: "Item id from get_menu.",
                },
                qty: { type: "integer", minimum: 1, description: "How many." },
              },
            },
          },
          name: {
            type: "string",
            minLength: 2,
            description: "The customer's name, as they gave it.",
          },
          pickup: {
            type: "string",
            enum: Canteen.SLOTS,
            description: "Pickup time in 24-hour HH:MM, on the half hour, between " +
                         "07:00 and 20:30. 1 pm is 13:00, 9:30 am is 09:30.",
          },
          notes: {
            type: "string",
            description: "Optional notes for the kitchen, e.g. less spicy.",
          },
        },
      },
      annotations: { readOnlyHint: false },
      execute: announce("place_order", async (args) => Canteen.placeOrder(args)),
    },
    {
      name: "pay_order",
      title: "Pay for an order",
      description:
        "Pay for an existing order by its order id using UPI. This spends money.",
      inputSchema: {
        type: "object",
        required: ["orderId"],
        properties: {
          orderId: { type: "string", description: "Order id from place_order." },
        },
      },
      annotations: { readOnlyHint: false, destructiveHint: true },
      execute: announce("pay_order", async ({ orderId }) => Canteen.payOrder(orderId)),
    },
  ];

  // ------------------------------------------------------------ on and off

  let controller = null;

  function enable() {
    if (!supported || controller) return;
    controller = new AbortController();
    // Register all three in one go, so an agent never sees a half-ready page.
    for (const tool of TOOLS) {
      try {
        mc.registerTool(tool, { signal: controller.signal });
      } catch (err) {
        Canteen.log(`could not register ${tool.name}: ${err.message}`);
      }
    }
    Canteen.log(`WebMCP on — ${TOOLS.length} tools registered`, "tool");
    render();
  }

  function disable() {
    if (!controller) return;
    controller.abort();
    controller = null;
    Canteen.log("WebMCP off — tools removed");
    render();
  }

  // ------------------------------------------------------------ the switch

  const toggle = document.getElementById("webmcp-toggle");
  const stateText = document.getElementById("webmcp-state");

  function render() {
    const on = controller !== null;
    if (toggle) {
      toggle.setAttribute("aria-checked", String(on));
      toggle.classList.toggle("is-on", on);
    }
    if (stateText) stateText.textContent = supported ? (on ? "on" : "off") : "unavailable";

    // Keep the address bar honest, without reloading the page.
    const url = new URL(location.href);
    if (on) url.searchParams.set("webmcp", "1");
    else url.searchParams.delete("webmcp");
    history.replaceState(null, "", url);
  }

  if (toggle) {
    if (!supported) {
      toggle.disabled = true;
      toggle.title = "This browser has no document.modelContext";
    }
    toggle.addEventListener("click", () => (controller ? disable() : enable()));
  }

  window.CanteenWebMCP = {
    supported,
    enable,
    disable,
    get on() { return controller !== null; },
  };

  // ------------------------------------------------------------ first load

  const wantOn = new URLSearchParams(location.search).has("webmcp");
  if (wantOn && supported) {
    enable();
  } else {
    if (wantOn) {
      Canteen.log("document.modelContext missing — WebMCP needs Chrome 149+ with it enabled");
    }
    render();
  }
})();

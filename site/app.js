/**
 * Palace Road Tiffin Room — shared page logic.
 *
 * This file knows nothing about AI agents. It is the ordinary website.
 * Both demo arms end up calling the same two functions here:
 *
 *   Canteen.placeOrder({ items, name, pickup })
 *   Canteen.payOrder(orderId)
 *
 * Arm A (no WebMCP) reaches them by filling the form and clicking the button.
 * Arm B (WebMCP) reaches them through tools registered in webmcp.js.
 *
 * Because both paths land on the same functions, the benchmark's success
 * check is identical for both arms. That is what makes the comparison fair.
 *
 * Accessibility is deliberate, not decorative. Every control has a real label,
 * so the no-WebMCP agent gets the best page it could reasonably hope for.
 * Beating a well-built page is the only result worth showing.
 */

(() => {
  "use strict";

  const CATEGORIES = [
    { id: "tiffin", title: "Tiffin" },
    { id: "rice", title: "Rice plates" },
    { id: "drinks", title: "Coffee & drinks" },
    { id: "sweets", title: "Sweets" },
  ];

  const MENU = [
    { id: "dosa", cat: "tiffin", name: "Masala Dosa", price: 40,
      desc: "Crisp, ghee-roasted, potato palya inside." },
    { id: "idli", cat: "tiffin", name: "Idli Vada", price: 30,
      desc: "Two idlis and one vada, chutney and sambar." },
    { id: "rava", cat: "tiffin", name: "Rava Idli", price: 35,
      desc: "Soft semolina idli with cashew and curry leaf." },
    { id: "setdosa", cat: "tiffin", name: "Set Dosa", price: 45,
      desc: "Three spongy dosas with vegetable saagu." },
    { id: "kharabath", cat: "tiffin", name: "Khara Bath", price: 35,
      desc: "Savoury upma with beans, carrot and ghee." },

    { id: "bisibele", cat: "rice", name: "Bisi Bele Bath", price: 50,
      desc: "Rice, lentils and spice, served with boondi." },
    { id: "curdrice", cat: "rice", name: "Curd Rice", price: 40,
      desc: "Cooled, tempered, with pomegranate." },
    { id: "lemonrice", cat: "rice", name: "Lemon Rice", price: 35,
      desc: "Turmeric, peanut and fresh lemon." },

    { id: "coffee", cat: "drinks", name: "Filter Coffee", price: 15,
      desc: "Twice-filtered decoction, boiled milk." },
    { id: "badam", cat: "drinks", name: "Badam Milk", price: 30,
      desc: "Almond and saffron, served warm." },
    { id: "chai", cat: "drinks", name: "Masala Chai", price: 12,
      desc: "Ginger, cardamom, strong brew." },

    { id: "mysorepak", cat: "sweets", name: "Mysore Pak", price: 25,
      desc: "Gram flour and ghee, cut fresh each morning." },
    { id: "kesari", cat: "sweets", name: "Kesari Bath", price: 30,
      desc: "Semolina, saffron and raisins." },
  ];

  // Pickup every half hour while the counter is open: 7:00 AM to 8:30 PM.
  const SLOTS = [];
  for (let m = 7 * 60; m <= 20 * 60 + 30; m += 30) {
    SLOTS.push(`${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
  }

  function slotLabel(hhmm) {
    const [h, m] = hhmm.split(":").map(Number);
    return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
  }

  const el = (id) => document.getElementById(id);
  const rupees = (n) => "₹" + n;

  // ---------------------------------------------------------------- render

  function renderMenu() {
    const root = el("menu");
    root.innerHTML = "";

    for (const cat of CATEGORIES) {
      const section = document.createElement("section");
      section.className = "cat";
      section.id = "cat-" + cat.id;

      const title = document.createElement("h3");
      title.className = "cat-title";
      title.textContent = cat.title;
      section.appendChild(title);

      for (const item of MENU.filter((m) => m.cat === cat.id)) {
        const row = document.createElement("div");
        row.className = "item";
        row.dataset.itemId = item.id;
        row.innerHTML = `
          <span class="veg" role="img" aria-label="Vegetarian"></span>
          <div>
            <div class="item-name">${item.name}</div>
            <div class="item-desc">${item.desc}</div>
          </div>
          <div class="item-price">${rupees(item.price)}</div>
          <div class="stepper">
            <button type="button" aria-label="One less ${item.name}"
                    data-step="-1" data-for="${item.id}">&minus;</button>
            <input type="number" min="0" max="20" value="0"
                   id="qty-${item.id}" name="qty-${item.id}"
                   aria-label="${item.name} quantity" />
            <button type="button" aria-label="One more ${item.name}"
                    data-step="1" data-for="${item.id}">+</button>
          </div>
        `;
        section.appendChild(row);
      }
      root.appendChild(section);
    }

    root.addEventListener("input", renderCart);
    root.addEventListener("click", (event) => {
      const button = event.target.closest("[data-step]");
      if (!button) return;
      const input = el("qty-" + button.dataset.for);
      const next = Math.max(0, (Number(input.value) || 0) + Number(button.dataset.step));
      input.value = String(next);
      renderCart();
    });
  }

  function readFormItems() {
    return MENU
      .map((m) => ({ id: m.id, qty: Number(el(`qty-${m.id}`).value) || 0 }))
      .filter((i) => i.qty > 0);
  }

  function priceOf(items) {
    return items.reduce((sum, i) => {
      const m = MENU.find((x) => x.id === i.id);
      return sum + (m ? m.price * i.qty : 0);
    }, 0);
  }

  function renderCart() {
    const items = readFormItems();
    const list = el("cart");
    list.innerHTML = "";

    if (items.length === 0) {
      const li = document.createElement("li");
      li.className = "cart-empty";
      li.textContent = "Nothing added yet.";
      list.appendChild(li);
    } else {
      for (const i of items) {
        const m = MENU.find((x) => x.id === i.id);
        const li = document.createElement("li");
        li.innerHTML = `<span><span class="qty">${i.qty} ×</span> ${m.name}</span>` +
                       `<span>${rupees(m.price * i.qty)}</span>`;
        list.appendChild(li);
      }
    }
    el("total").textContent = rupees(priceOf(items));
  }

  function showError(message) {
    const node = el("error");
    node.textContent = message;
    node.hidden = !message;
  }

  function log(message, kind) {
    const list = el("log");
    const placeholder = list.querySelector(".muted");
    if (placeholder) placeholder.remove();
    const li = document.createElement("li");
    li.textContent = message;
    if (kind) li.className = kind;
    list.appendChild(li);
    list.scrollTop = list.scrollHeight;
  }

  function flash(node) {
    if (!node) return;
    node.classList.remove("flash");
    void node.offsetWidth;
    node.classList.add("flash");
  }

  // ---------------------------------------------------------------- state

  let orderSeq = 0;

  function reset() {
    for (const m of MENU) el(`qty-${m.id}`).value = "0";
    el("name").value = "";
    el("pickup").value = "";
    if (el("notes")) el("notes").value = "";
    el("receipt").hidden = true;
    el("paid").hidden = true;
    showError("");
    renderCart();
    el("log").innerHTML = '<li class="muted">Nothing yet.</li>';
    window.__lastOrder = null;
    window.__paid = null;
  }

  // -------------------------------------------------------------- actions

  /**
   * The one way an order is ever created, whichever arm is driving.
   * Returns { ok: true, orderId, total } or { ok: false, error }.
   */
  function placeOrder({ items, name, pickup, notes } = {}) {
    if (!Array.isArray(items) || items.length === 0) {
      return fail("Pick at least one item.");
    }
    for (const i of items) {
      if (!MENU.some((m) => m.id === i.id)) return fail(`Unknown item: ${i.id}`);
      if (!Number.isInteger(i.qty) || i.qty < 1) {
        return fail(`Quantity for ${i.id} must be a whole number of 1 or more.`);
      }
    }
    if (!name || String(name).trim().length < 2) {
      return fail("Please give a name of at least 2 characters.");
    }
    if (!SLOTS.includes(pickup)) {
      return fail(`Pickup must be on the half hour between 07:00 and 20:30 (24-hour HH:MM), ` +
                  `for example 13:00 for 1 pm.`);
    }
    notes = notes ? String(notes).trim().slice(0, 200) : "";

    const normalised = items.map((i) => ({ id: i.id, qty: i.qty }));
    const total = priceOf(normalised);
    const orderId = "PR" + String(++orderSeq).padStart(3, "0");

    // Mirror the order into the visible form, so the audience sees what the
    // agent did even when it never touched an input.
    for (const m of MENU) {
      const found = normalised.find((i) => i.id === m.id);
      el(`qty-${m.id}`).value = found ? String(found.qty) : "0";
    }
    el("name").value = String(name).trim();
    el("pickup").value = pickup;
    el("notes").value = notes;
    renderCart();
    showError("");

    el("order-id").textContent = orderId;
    el("receipt-items").innerHTML = normalised
      .map((i) => {
        const m = MENU.find((x) => x.id === i.id);
        return `<li>${i.qty} &times; ${m.name}</li>`;
      })
      .join("");
    el("receipt-pickup").textContent = slotLabel(pickup) + (notes ? ` · “${notes}”` : "");
    el("receipt-total").textContent = rupees(total);
    el("receipt").hidden = false;
    el("paid").hidden = true;
    flash(el("receipt"));

    // The benchmark's oracle reads this. Nothing else writes it.
    window.__lastOrder = {
      orderId,
      items: normalised,
      name: String(name).trim(),
      pickup,
      notes,
      total,
    };

    log(`order ${orderId} placed · ${normalised.length} line(s) · ₹${total}`);
    return { ok: true, orderId, total };
  }

  function payOrder(orderId) {
    const order = window.__lastOrder;
    if (!order) return fail("There is no order to pay for yet.");
    if (orderId !== order.orderId) return fail(`No order with id ${orderId}.`);
    window.__paid = orderId;
    el("paid").hidden = false;
    flash(el("paid"));
    log(`order ${orderId} paid · ₹${order.total}`);
    return { ok: true, orderId, paid: order.total };
  }

  function fail(error) {
    showError(error);
    log("rejected: " + error);
    return { ok: false, error };
  }

  // ----------------------------------------------------------------- wire

  function onSubmit(event) {
    event.preventDefault();
    placeOrder({
      items: readFormItems(),
      name: el("name").value,
      pickup: el("pickup").value,
      notes: el("notes").value,
    });
  }

  function renderSlots() {
    const select = el("pickup");
    for (const s of SLOTS) {
      const option = document.createElement("option");
      option.value = s;
      option.textContent = slotLabel(s);
      select.appendChild(option);
    }
  }

  renderMenu();
  renderSlots();
  renderCart();
  el("order-form").addEventListener("submit", onSubmit);
  el("pay").addEventListener("click", () => {
    const order = window.__lastOrder;
    payOrder(order ? order.orderId : "none");
  });

  window.__lastOrder = null;
  window.__paid = null;

  window.Canteen = {
    MENU,
    SLOTS,
    CATEGORIES,
    getMenu: () => MENU.map((m) => ({ id: m.id, name: m.name, price: m.price, category: m.cat })),
    placeOrder,
    payOrder,
    reset,
    log,
  };
})();

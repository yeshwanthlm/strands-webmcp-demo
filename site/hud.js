/**
 * Agent side panel + highlights. Demo only.
 *
 * window.AgentPanel  a sidebar docked on the right of the site. It appears
 *                    only while a Python agent is driving the page, and
 *                    streams every model call and tool call live.
 * window.AgentHUD    glows and ripples on the elements the agent uses.
 *
 * A person browsing the site never sees either. Both are hidden from the
 * accessibility tree (aria-hidden) and ignore the mouse, so they add nothing
 * to what the no-WebMCP agent reads and never block a click.
 */

(() => {
  "use strict";

  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const fmt = (ms) => (ms / 1000).toFixed(1) + "s";
  const num = (n) => Number(n || 0).toLocaleString("en-IN");

  // ------------------------------------------------------------ side panel

  let root = null;
  let t0 = 0;
  let tick = null;
  let mode = "off";
  let previous = {};
  const startedAt = {};
  const $ = (id) => root.querySelector(`[data-ap="${id}"]`);

  function build() {
    root = document.createElement("aside");
    root.className = "ap";
    root.setAttribute("aria-hidden", "true");
    root.innerHTML = `
      <header class="ap-head">
        <div class="ap-row">
          <span class="ap-dot"></span>
          <span class="ap-title">AI agent</span>
          <span class="ap-badge" data-ap="badge">—</span>
        </div>
        <p class="ap-task" data-ap="task"></p>
        <div class="ap-stats">
          <div class="ap-stat"><b data-ap="time">0.0s</b><span>time</span></div>
          <div class="ap-stat ap-calls"><b data-ap="calls">0</b><span>tool calls</span></div>
          <div class="ap-stat"><b data-ap="models">0</b><span>model calls</span></div>
          <div class="ap-stat"><b data-ap="tokens">0</b><span>tokens</span></div>
        </div>
      </header>
      <div class="ap-feed" data-ap="feed"></div>
      <footer class="ap-foot" data-ap="foot"></footer>`;
    document.body.appendChild(root);
  }

  function setState(state) {
    root.classList.remove("ap-running", "ap-done", "ap-failed");
    if (state) root.classList.add("ap-" + state);
  }

  function scrollFeed() {
    const feed = $("feed");
    feed.scrollTop = feed.scrollHeight;
  }

  const AgentPanel = {
    /** Dock the empty panel before the run, so the site never jumps mid-run. */
    ready({ mode: m }) {
      if (!root) build();
      mode = m;
      document.body.classList.add("has-ap");
      root.classList.toggle("ap-on", m === "on");
      $("badge").textContent = m === "on" ? "WebMCP ON" : "WebMCP OFF";
      $("task").textContent = "Waiting for an order…";
      setState(null);
    },

    /**
     * Ask for the order right here in the panel, where the room can see it.
     * On submit: a 3-2-1 countdown, then window.__agentGo = true and the
     * request is in window.__agentTask. The Python agent waits for that.
     */
    ask({ fallback }) {
      if (!root) build();
      window.__agentGo = false;
      window.__agentTask = null;
      $("task").textContent = "";
      const feed = $("feed");
      feed.innerHTML = `
        <form class="ap-ask">
          <label for="ap-prompt">What should the agent do?</label>
          <textarea id="ap-prompt" rows="4" placeholder="${esc(fallback || "")}"></textarea>
          <button type="submit">Run agent</button>
          <p class="ap-hint">Enter to run · Shift+Enter for a new line · empty runs the example</p>
        </form>`;
      const form = feed.querySelector("form");
      const box = feed.querySelector("textarea");
      box.focus();

      const go = (event) => {
        event && event.preventDefault();
        const task = box.value.trim() || fallback || "";
        if (!task) return;
        window.__agentTask = task;
        $("task").textContent = task;
        let n = 3;
        feed.innerHTML = `<div class="ap-count"><b>${n}</b><span>agent starting</span></div>`;
        const step = setInterval(() => {
          n -= 1;
          if (n > 0) { feed.querySelector(".ap-count b").textContent = n; return; }
          clearInterval(step);
          feed.innerHTML = "";
          window.__agentGo = true;
        }, 800);
      };
      form.addEventListener("submit", go);
      box.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) go(e);
      });
    },

    /** A new run. mode: "on" or "off" (WebMCP). previous: the other run's numbers. */
    start({ mode: m, task, previous: prev }) {
      if (!root) build();
      mode = m;
      previous = prev || {};
      document.body.classList.add("has-ap");
      root.classList.toggle("ap-on", m === "on");
      $("badge").textContent = m === "on" ? "WebMCP ON" : "WebMCP OFF";
      $("task").textContent = task || "";
      $("feed").innerHTML = "";
      $("foot").innerHTML = "";
      ["calls", "models", "tokens"].forEach((k) => ($(k).textContent = "0"));
      setState("running");
      t0 = performance.now();
      clearInterval(tick);
      tick = setInterval(() => ($("time").textContent = fmt(performance.now() - t0)), 100);
    },

    thinking(n) {
      if (!root) return;
      $("models").textContent = n;
      const p = document.createElement("p");
      p.className = "ap-thinking";
      p.textContent = `Model call ${n}: deciding what to do next`;
      $("feed").appendChild(p);
      scrollFeed();
    },

    tokens(n) { if (root) $("tokens").textContent = num(n); },

    call(n, name, args) {
      if (!root) return;
      $("calls").textContent = n;
      startedAt[n] = performance.now();
      const el = document.createElement("div");
      el.className = "ap-call";
      el.dataset.n = n;
      const a = args && Object.keys(args).length ? JSON.stringify(args) : "";
      el.innerHTML = `
        <div class="ap-call-head">
          <span class="ap-n">${n}</span>
          <span class="ap-name">${esc(name)}</span>
          <span class="ap-ms">+${fmt(performance.now() - t0)}</span>
        </div>
        ${a ? `<div class="ap-args">${esc(a)}</div>` : ""}
        <div class="ap-result ap-pending"></div>`;
      $("feed").appendChild(el);
      scrollFeed();
    },

    result(n, ok, text) {
      if (!root) return;
      const el = root.querySelector(`.ap-call[data-n="${n}"]`);
      if (!el) return;
      const took = Math.round(performance.now() - (startedAt[n] || t0));
      const r = el.querySelector(".ap-result");
      r.className = "ap-result " + (ok ? "ap-ok" : "ap-bad");
      r.textContent = text;
      if (!ok) el.classList.add("ap-error");
      el.querySelector(".ap-ms").textContent += ` · ${took} ms`;
    },

    finish({ ok, calls, models, tokens, wall_ms, reply }) {
      if (!root) return;
      clearInterval(tick);
      $("time").textContent = fmt(wall_ms);
      $("calls").textContent = calls;
      if (models != null) $("models").textContent = models;
      $("tokens").textContent = num(tokens);
      // A question with no order is a finished run, not a failure.
      setState("done");

      const runs = { ...previous, [mode]: { ok, calls, models, tokens, wall_ms } };
      const off = runs.off, on = runs.on;
      const cell = (r, k, f) => (r && r[k] != null ? f(r[k]) : "—");
      const row = (label, k, f) =>
        `<tr><td>${label}</td><td>${cell(off, k, f)}</td><td class="ap-col-on">${cell(on, k, f)}</td></tr>`;

      $("foot").innerHTML = `
        <p class="ap-summary">${ok ? "Order placed" : "Finished · no order placed"} · ${calls} tool calls · ${fmt(wall_ms)}</p>
        <table>
          <tr><th></th><th>Without</th><th class="ap-col-on">With WebMCP</th></tr>
          ${row("Time", "wall_ms", fmt)}
          ${row("Tool calls", "calls", num)}
          ${row("Model calls", "models", num)}
          ${row("Tokens", "tokens", num)}
          ${row("Order", "ok", (v) => (v ? "placed" : "none"))}
        </table>
        ${reply ? `<p class="ap-reply">${esc(reply)}</p>` : ""}`;
    },

    hide() {
      clearInterval(tick);
      document.body.classList.remove("has-ap");
      if (root) { root.remove(); root = null; }
    },
  };

  // ------------------------------------------------------------ highlights

  let stepCount = 0;

  const AgentHUD = {
    /**
     * Light up an element the agent is using, so the back row can see it.
     *
     * If the element is off screen, the page scrolls to it first. The scroll
     * is instant and the glow fades by itself, so nothing here makes the agent
     * wait. The glow follows the element if the page moves afterwards.
     * kind: "click" (pink, with a ripple), "type" (cyan), "select" (purple),
     * "webmcp" (amber).
     */
    flash(el, label, kind, smooth) {
      if (!el || !el.getBoundingClientRect) return;
      kind = kind || "click";

      const r0 = el.getBoundingClientRect();
      if (!r0.width && !r0.height) return;
      const offscreen = r0.top < 70 || r0.bottom > innerHeight - 10;
      if (offscreen) el.scrollIntoView({ block: "center", behavior: smooth ? "smooth" : "instant" });

      const box = document.createElement("div");
      box.className = `hud-flash hud-flash-${kind}`;
      box.setAttribute("aria-hidden", "true");
      if (label) {
        const tag = document.createElement("span");
        tag.className = "hud-flash-tag";
        tag.textContent = label;
        box.appendChild(tag);
      }
      document.body.appendChild(box);

      // Track the element every frame, so scrolling and sticky panels never
      // leave the glow behind.
      const born = performance.now();
      const follow = () => {
        const r = el.getBoundingClientRect();
        box.style.left = `${r.left - 6}px`;
        box.style.top = `${r.top - 6}px`;
        box.style.width = `${r.width + 12}px`;
        box.style.height = `${r.height + 12}px`;
        if (performance.now() - born < 1800) requestAnimationFrame(follow);
        else box.remove();
      };
      follow();

      if (kind === "click") {
        const ring = document.createElement("div");
        ring.className = "hud-ripple";
        ring.setAttribute("aria-hidden", "true");
        document.body.appendChild(ring);
        // The ripple follows the button too, or a scroll leaves it behind.
        const pin = () => {
          const r = el.getBoundingClientRect();
          ring.style.left = `${r.left + r.width / 2}px`;
          ring.style.top = `${r.top + r.height / 2}px`;
          if (performance.now() - born < 900) requestAnimationFrame(pin);
          else ring.remove();
        };
        pin();
      }
    },

    /**
     * Light up several elements one after another, scrolling smoothly between
     * them. Runs in the page on its own timers: the agent does not wait for it.
     * steps: [{ selector, label, kind }]
     */
    tour(steps, gap) {
      (steps || []).forEach((s, i) => {
        setTimeout(() => this.flash(document.querySelector(s.selector), s.label, s.kind, true),
                   i * (gap || 550));
      });
    },

    // Older callers (agent/extras) drive the panel through these three.
    start({ mode: m, task }) {
      stepCount = 0;
      AgentPanel.start({ mode: m, task, previous: {} });
    },
    step(label) {
      stepCount += 1;
      AgentPanel.call(stepCount, label, null);
      AgentPanel.result(stepCount, true, "");
    },
    finish({ ok, steps, tokens, wall_ms, summary }) {
      AgentPanel.finish({ ok, calls: steps, models: null, tokens, wall_ms, reply: summary });
    },
    clear() { AgentPanel.hide(); },
  };

  window.AgentPanel = AgentPanel;
  window.AgentHUD = AgentHUD;
})();

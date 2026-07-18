/* AB Bank Zambia chat widget — vanilla JS, zero dependencies.
 *
 * Embed with one tag:
 *   <script src="https://<host>/widget/widget.js" defer></script>
 * Cross-domain embedding: add data-endpoint="https://<host>".
 *
 * Accessibility (build spec §3.4, WCAG 2.1 AA): role="log" + aria-live,
 * full keyboard operation, visible focus, Esc closes and returns focus,
 * respects prefers-reduced-motion (in CSS), relative units for 200% zoom.
 *
 * Kill switch: if /health reports widget_enabled=false (or is unreachable),
 * the widget never renders — the page is untouched.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var BASE =
    (script && script.getAttribute("data-endpoint")) ||
    (script && script.src ? script.src.replace(/\/widget\/widget\.js.*$/, "") : "");

  var sessionId = null;
  try {
    sessionId = sessionStorage.getItem("abz_chat_session"); // no cookies (§3.3)
  } catch (e) { /* storage blocked — session lives for the page only */ }

  var els = {};
  var started = false;

  function h(tag, className, attrs) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (attrs) {
      Object.keys(attrs).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    }
    return el;
  }

  function build() {
    var link = h("link", null, { rel: "stylesheet", href: BASE + "/widget/widget.css" });
    document.head.appendChild(link);

    els.launcher = h("button", "abz-launcher", {
      type: "button",
      "aria-label": "Open AB Bank chat assistant",
      "aria-expanded": "false",
      "aria-haspopup": "dialog"
    });
    els.launcher.textContent = "Chat";

    els.panel = h("div", "abz-panel", {
      role: "dialog",
      "aria-label": "AB Bank chat assistant",
      hidden: ""
    });

    var header = h("div", "abz-header");
    var title = h("div", "abz-title");
    title.textContent = "AB Bank Assistant";
    var badge = h("span", "abz-badge");
    badge.textContent = "Automated";
    title.appendChild(badge);
    els.close = h("button", "abz-close", { type: "button", "aria-label": "Close chat" });
    els.close.textContent = "×";
    header.appendChild(title);
    header.appendChild(els.close);

    els.log = h("div", "abz-log", {
      role: "log",
      "aria-live": "polite",
      "aria-label": "Chat messages"
    });
    els.quick = h("div", "abz-quick", { role: "group", "aria-label": "Quick replies" });

    var form = h("form", "abz-form");
    var label = h("label", "abz-visually-hidden", { for: "abz-input" });
    label.textContent = "Type your message";
    els.input = h("input", "abz-input", {
      id: "abz-input",
      type: "text",
      maxlength: "500",
      autocomplete: "off",
      placeholder: "Type your message…"
    });
    els.send = h("button", "abz-send", { type: "submit" });
    els.send.textContent = "Send";
    form.appendChild(label);
    form.appendChild(els.input);
    form.appendChild(els.send);

    els.panel.appendChild(header);
    els.panel.appendChild(els.log);
    els.panel.appendChild(els.quick);
    els.panel.appendChild(form);
    document.body.appendChild(els.launcher);
    document.body.appendChild(els.panel);

    els.launcher.addEventListener("click", toggle);
    els.close.addEventListener("click", close);
    els.panel.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = els.input.value.trim();
      if (!text) return;
      els.input.value = "";
      addBubble("user", text);
      post({ session_id: sessionId, message: text });
    });
  }

  function toggle() {
    if (els.panel.hasAttribute("hidden")) open();
    else close();
  }

  function open() {
    els.panel.removeAttribute("hidden");
    els.launcher.setAttribute("aria-expanded", "true");
    els.input.focus();
    if (!started) {
      started = true;
      post({ session_id: sessionId }); // empty message → welcome + disclosure
    }
  }

  function close() {
    els.panel.setAttribute("hidden", "");
    els.launcher.setAttribute("aria-expanded", "false");
    els.launcher.focus();
  }

  function setBusy(busy) {
    els.input.disabled = busy;
    els.send.disabled = busy;
  }

  var typingEl = null;

  function showTyping() {
    if (typingEl) return;
    typingEl = h("div", "abz-msg abz-msg--bot abz-typing", { "aria-hidden": "true" });
    for (var i = 0; i < 3; i++) typingEl.appendChild(h("span", "abz-typing-dot"));
    els.log.appendChild(typingEl);
    els.log.scrollTop = els.log.scrollHeight;
  }

  function hideTyping() {
    if (typingEl && typingEl.parentNode) typingEl.parentNode.removeChild(typingEl);
    typingEl = null;
  }

  function addBubble(role, text) {
    var bubble = h("div", "abz-msg abz-msg--" + role);
    var parts = String(text).split("\n");
    for (var i = 0; i < parts.length; i++) {
      if (i > 0) bubble.appendChild(document.createElement("br"));
      bubble.appendChild(document.createTextNode(parts[i]));
    }
    els.log.appendChild(bubble);
    els.log.scrollTop = els.log.scrollHeight;
  }

  function renderQuick(buttons) {
    els.quick.textContent = "";
    (buttons || []).forEach(function (b) {
      var btn = h("button", "abz-quickbtn", { type: "button" });
      btn.textContent = b.label;
      btn.addEventListener("click", function () {
        addBubble("user", b.label);
        renderQuick([]);
        post({ session_id: sessionId, payload: b.payload });
      });
      els.quick.appendChild(btn);
    });
  }

  function post(body) {
    setBusy(true);
    showTyping();
    fetch(BASE + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        hideTyping();
        sessionId = data.session_id;
        try { sessionStorage.setItem("abz_chat_session", sessionId); } catch (e) {}
        // After a page reload the server replays the earlier (masked)
        // transcript so the customer isn't staring at an empty window.
        (data.history || []).forEach(function (turn) {
          addBubble(turn.role === "user" ? "user" : "bot", turn.text);
        });
        (data.replies || []).forEach(function (reply) {
          addBubble("bot", reply.text);
        });
        var last = data.replies && data.replies[data.replies.length - 1];
        renderQuick(last ? last.buttons : []);
      })
      .catch(function () {
        hideTyping();
        addBubble(
          "bot",
          "Sorry — I can't connect right now. Please try again in a " +
            "moment, or contact the bank directly."
        );
      })
      .then(function () {
        setBusy(false);
        if (!els.panel.hasAttribute("hidden")) els.input.focus();
      });
  }

  // Kill switch: render only if the backend says the widget is enabled.
  fetch(BASE + "/health")
    .then(function (r) { return r.json(); })
    .then(function (health) {
      if (health && health.widget_enabled) build();
    })
    .catch(function () { /* backend down — stay invisible */ });
})();

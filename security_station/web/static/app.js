"use strict";
(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const TITLES = {
    status: "System Status",
    pir: "PIR Motion Detector",
    ultrasonic: "Ultrasonic Distance",
    environment: "Ambient Environment (DHT)",
    manual: "Manual Controls",
    auth: "User Authentication",
    logs: "Security Logs (SQLite)",
  };
  const ACTION_LABELS = { relay: "Toggle relay", buzzer: "Buzzer test", arm: "Arm system", disarm: "Disarm system" };
  const SHIELD_MARKS = { SECURE: "m10 16 4 4 8-9", ALERT: "M11 11l10 10M21 11 11 21", DISARMED: "M11 16h10" };
  const COLORS = {
    accent: "#38d6f5", accent2: "#1d8fd8", grid: "rgba(143,169,191,0.16)", axis: "#8fa9bf",
    text: "#e8f1f8", threshold: "#3ddc84", red: "#ff4d4f", amber: "#f5b638",
  };

  let state = null;
  let clockOffset = 0;          // server clock minus local clock, in seconds
  let logVersion = -1;
  let lastLogId = 0;
  let expanded = null;
  let pendingAction = null;

  // ------------------------------------------------------------------ helpers
  const bound = name => $$(`[data-bind="${name}"]`);
  const setText = (name, text) => bound(name).forEach(el => { if (el.textContent !== text) el.textContent = text; });
  const toggle = (name, cls, on) => bound(name).forEach(el => el.classList.toggle(cls, on));
  const serverNow = () => Date.now() / 1000 + clockOffset;
  const fmtClock = ts => new Date(ts * 1000).toLocaleTimeString("en-US", { hour12: true });
  const fmtCm = v => (v == null ? "-- cm" : `${Math.round(v)} cm`);
  const fmtUptime = s => {
    s = Math.max(0, Math.floor(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return `${h}h ${String(m).padStart(2, "0")}m ${String(sec).padStart(2, "0")}s`;
  };
  const el = (tag, props = {}, ...children) => {
    const node = document.createElement(tag);
    Object.assign(node, props);
    children.forEach(c => node.append(c));
    return node;
  };

  // ------------------------------------------------------------------- canvas
  function fitCanvas(canvas) {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(rect.width * dpr));
    const h = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);
    return { ctx, w: rect.width, h: rect.height };
  }

  function niceStep(range, target) {
    const raw = range / Math.max(1, target);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    return (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  }

  function drawChart(canvas, o) {
    const { ctx, w, h } = fitCanvas(canvas);
    if (w < 40 || h < 40) return;
    const pad = { l: 46, r: 12, t: 10, b: 34 };
    const pw = w - pad.l - pad.r, ph = h - pad.t - pad.b;
    const X = x => pad.l + ((x - o.xMin) / (o.xMax - o.xMin)) * pw;
    const Y = y => pad.t + ph - ((y - o.yMin) / (o.yMax - o.yMin)) * ph;

    ctx.font = "11px system-ui, sans-serif";
    ctx.lineWidth = 1;
    // grid + ticks
    const yStep = o.yStep || niceStep(o.yMax - o.yMin, Math.max(2, Math.floor(ph / 32)));
    ctx.textAlign = "right"; ctx.textBaseline = "middle";
    for (let y = Math.ceil(o.yMin / yStep) * yStep; y <= o.yMax + 1e-9; y += yStep) {
      ctx.strokeStyle = COLORS.grid; ctx.beginPath(); ctx.moveTo(pad.l, Y(y)); ctx.lineTo(w - pad.r, Y(y)); ctx.stroke();
      ctx.fillStyle = COLORS.axis; ctx.fillText(o.yFmt ? o.yFmt(y) : String(+y.toFixed(2)), pad.l - 6, Y(y));
    }
    const xStep = o.xStep || niceStep(o.xMax - o.xMin, Math.max(2, Math.floor(pw / 60)));
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    for (let x = Math.ceil(o.xMin / xStep) * xStep; x <= o.xMax + 1e-9; x += xStep) {
      ctx.strokeStyle = COLORS.grid; ctx.beginPath(); ctx.moveTo(X(x), pad.t); ctx.lineTo(X(x), pad.t + ph); ctx.stroke();
      ctx.fillStyle = COLORS.axis; ctx.fillText(o.xFmt ? o.xFmt(x) : String(+x.toFixed(2)), X(x), pad.t + ph + 4);
    }
    // axis labels
    ctx.fillStyle = COLORS.axis;
    if (o.xLabel) { ctx.textBaseline = "bottom"; ctx.fillText(o.xLabel, pad.l + pw / 2, h - 1); }
    if (o.yLabel) {
      ctx.save(); ctx.translate(11, pad.t + ph / 2); ctx.rotate(-Math.PI / 2);
      ctx.textBaseline = "middle"; ctx.fillText(o.yLabel, 0, 0); ctx.restore();
    }
    ctx.strokeStyle = "rgba(143,169,191,0.45)";
    ctx.beginPath(); ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, pad.t + ph); ctx.lineTo(w - pad.r, pad.t + ph); ctx.stroke();

    const pts = o.points.filter(p => p[0] >= o.xMin - 1e-6);
    ctx.save();
    ctx.beginPath(); ctx.rect(pad.l, pad.t, pw, ph); ctx.clip();
    if (pts.length > 1) {
      const path = new Path2D();
      pts.forEach(([x, y], i) => (i ? path.lineTo(X(x), Y(y)) : path.moveTo(X(x), Y(y))));
      const fill = new Path2D(path);
      fill.lineTo(X(pts[pts.length - 1][0]), Y(o.yMin));
      fill.lineTo(X(pts[0][0]), Y(o.yMin));
      fill.closePath();
      const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + ph);
      grad.addColorStop(0, o.fill || "rgba(56,214,245,0.45)");
      grad.addColorStop(1, "rgba(56,214,245,0.02)");
      ctx.fillStyle = grad; ctx.fill(fill);
      ctx.strokeStyle = o.color || COLORS.accent; ctx.lineWidth = 2.2; ctx.lineJoin = "round";
      ctx.shadowColor = o.color || COLORS.accent; ctx.shadowBlur = 6;
      ctx.stroke(path);
      ctx.shadowBlur = 0;
    }
    if (o.threshold != null) {
      ctx.strokeStyle = COLORS.threshold; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(pad.l, Y(o.threshold)); ctx.lineTo(w - pad.r, Y(o.threshold)); ctx.stroke();
      ctx.fillStyle = COLORS.threshold; ctx.textAlign = "right"; ctx.textBaseline = "bottom";
      ctx.font = "bold 11px system-ui, sans-serif";
      ctx.fillText(o.thresholdLabel || "", w - pad.r - 4, Y(o.threshold) - 3);
    }
    ctx.restore();
  }

  function drawGauge(canvas, value, min, max, label, text) {
    const { ctx, w, h } = fitCanvas(canvas);
    if (w < 40 || h < 30) return;
    // Fit the whole arc (ends dip 0.24 r below the centre) plus stroke inside the canvas.
    const r = Math.max(10, Math.min((w / 2 - 4) / 1.04, (h - 4) / 1.37));
    const lw = Math.max(5, r * 0.13);
    const cx = w / 2, cy = h - 2 - 0.25 * r - lw / 2;
    const a0 = Math.PI * 1.08, a1 = Math.PI * 1.92;
    const frac = value == null ? 0 : Math.max(0, Math.min(1, (value - min) / (max - min)));
    const av = a0 + (a1 - a0) * frac;
    ctx.lineCap = "round";
    ctx.lineWidth = lw; ctx.strokeStyle = "rgba(143,169,191,0.18)";
    ctx.beginPath(); ctx.arc(cx, cy, r, a0, a1); ctx.stroke();
    const grad = ctx.createLinearGradient(cx - r, 0, cx + r, 0);
    grad.addColorStop(0, COLORS.accent2); grad.addColorStop(1, COLORS.accent);
    ctx.strokeStyle = grad; ctx.shadowColor = COLORS.accent; ctx.shadowBlur = 8;
    ctx.beginPath(); ctx.arc(cx, cy, r, a0, av); ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.fillStyle = "#fff";
    ctx.beginPath(); ctx.arc(cx + r * Math.cos(av), cy + r * Math.sin(av), lw * 0.55, 0, Math.PI * 2); ctx.fill();
    ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "#c9d7e3"; ctx.font = `${Math.max(10, r * 0.2)}px system-ui, sans-serif`;
    ctx.fillText(label, cx, cy - r * 0.32);
    ctx.fillStyle = COLORS.text; ctx.font = `bold ${Math.max(13, r * 0.36)}px system-ui, sans-serif`;
    ctx.fillText(text, cx, cy + r * 0.08);
  }

  function drawAllCharts() {
    if (!state) return;
    const now = state.server_time;
    const d = state.distance;
    const dpts = d.history.map(([t, cm]) => [d.window - (now - t), cm]);
    const dmax = Math.max(200, ...dpts.map(p => p[1]));
    $$('canvas[data-chart="distance"]').forEach(c => drawChart(c, {
      points: dpts, xMin: 0, xMax: d.window, yMin: 0, yMax: Math.ceil(dmax / 50) * 50,
      xStep: 10, yStep: 50, xLabel: "Time (s)", yLabel: "Distance (cm)",
      threshold: d.threshold, thresholdLabel: `${Math.round(d.threshold)} cm`,
    }));

    const env = state.env;
    const series = idx => env.history.map(row => [-(now - row[0]) / 60, row[idx]]);
    const range = (pts, minSpan) => {
      if (!pts.length) return [0, 1];
      let lo = Math.min(...pts.map(p => p[1])), hi = Math.max(...pts.map(p => p[1]));
      const mid = (lo + hi) / 2, span = Math.max(minSpan, (hi - lo) * 1.3);
      return [Math.floor((mid - span / 2) * 2) / 2, Math.ceil((mid + span / 2) * 2) / 2];
    };
    const tPts = series(1), hPts = series(2);
    const [tLo, tHi] = range(tPts, 2), [hLo, hHi] = range(hPts, 6);
    $$('canvas[data-chart="temperature"]').forEach(c => drawChart(c, {
      points: tPts, xMin: -10, xMax: 0, yMin: tLo, yMax: tHi, xStep: 1,
      xFmt: x => (x === 0 ? "now" : `${x}m`), yFmt: y => `${y.toFixed(1)}°`, yLabel: "°C",
    }));
    $$('canvas[data-chart="humidity"]').forEach(c => drawChart(c, {
      points: hPts, xMin: -10, xMax: 0, yMin: hLo, yMax: hHi, xStep: 1,
      xFmt: x => (x === 0 ? "now" : `${x}m`), yFmt: y => `${Math.round(y)}%`, yLabel: "% RH",
    }));

    $$('canvas[data-gauge="temperature"]').forEach(c => drawGauge(c, env.temperature, 15, 30, "Temperature",
      env.temperature == null ? "--" : `${env.temperature.toFixed(1)}°C`));
    $$('canvas[data-gauge="humidity"]').forEach(c => drawGauge(c, env.humidity, 0, 100, "Humidity",
      env.humidity == null ? "--" : `${Math.round(env.humidity)}%`));
  }

  // ------------------------------------------------------------------- render
  function render() {
    if (!state) return;
    const s = state;

    setText("armed-word", s.armed ? "ARMED" : "DISARMED");
    toggle("armed-word", "armed", s.armed);
    toggle("armed-word", "disarmed", !s.armed);
    bound("badge").forEach(b => {
      b.classList.remove("secure", "alert", "disarmed");
      b.classList.add(s.status.toLowerCase());
      $(".shield-mark", b).setAttribute("d", SHIELD_MARKS[s.status] || SHIELD_MARKS.SECURE);
    });
    setText("status", s.status);
    $$(".status-block").forEach(b => (b.style.background = s.armed ? "" : "none"));

    // PIR
    const motion = s.pir.motion;
    setText("pir-word", motion ? "MOTION" : "CLEAR");
    toggle("pir-state", "motion", motion);
    $$(".tile-pir").forEach(t => t.classList.toggle("motion", motion));
    bound("pir-detail").forEach(node => {
      node.classList.toggle("motion", motion);
      node.replaceChildren("PIR State: ", el("b", { textContent: motion ? "Active" : "Passive" }), el("br"),
        motion ? `(Motion Detected: ${s.pir.zone})` : "(No Motion Detected)");
    });
    bound("zone-counts").forEach(dl => dl.replaceChildren(...Object.entries(s.pir.counts).map(([z, n]) =>
      el("div", {}, el("dt", { textContent: `${z} detections` }), el("dd", { textContent: String(n) })))));
    bound("detections").forEach(tb => tb.replaceChildren(...s.pir.detections.map(d => {
      const tr = el("tr", { className: d.armed ? "sev-HIGH" : "sev-INFO" });
      [fmtClock(d.ts), d.zone, d.duration == null ? "active" : `${d.duration.toFixed(1)} s`, d.armed ? "Armed" : "Disarmed"]
        .forEach(v => tr.append(el("td", { textContent: v })));
      return tr;
    })));
    if (!s.pir.detections.length) bound("detections").forEach(tb =>
      tb.replaceChildren(el("tr", {}, el("td", { colSpan: 4, className: "muted", textContent: "No detections yet" }))));

    // Ultrasonic
    const d = s.distance;
    setText("distance", fmtCm(d.current));
    toggle("distance", "close", d.current != null && d.current < d.threshold);
    setText("d-min", fmtCm(d.stats.min));
    setText("d-avg", fmtCm(d.stats.avg));
    setText("d-max", fmtCm(d.stats.max));
    setText("d-threshold", fmtCm(d.threshold));
    setText("d-breaches", String(d.breaches));

    // Environment
    setText("temperature", s.env.temperature == null ? "--" : `${s.env.temperature.toFixed(1)} °C`);
    setText("humidity", s.env.humidity == null ? "--" : `${s.env.humidity.toFixed(1)} %`);

    // Controls
    setText("relay-btn", `[RELAY: ${s.controls.relay ? "ON" : "OFF"}]`);
    toggle("relay-btn", "on", s.controls.relay);
    setText("buzzer-btn", s.controls.buzzer ? "[BUZZER: ON]" : "[BUZZER TEST]");
    toggle("buzzer-btn", "ringing", s.controls.buzzer);
    setText("relay", s.controls.relay ? "ON" : "OFF");
    setText("buzzer", s.controls.buzzer ? "SOUNDING" : "Silent");

    // Auth
    setText("arm-btn", s.armed ? "DISARM SYSTEM" : "ARM SYSTEM");
    bound("default-pw").forEach(p => (p.hidden = !s.default_password));

    // Logs
    setText("log-total", String(s.logs.total));
    if (s.logs.version !== logVersion) {
      logVersion = s.logs.version;
      fetchLogs();
    }

    tick();
    drawAllCharts();
  }

  function tick() {
    setText("clock", fmtClock(serverNow()));
    if (state) setText("uptime", fmtUptime(serverNow() - state.started_at));
  }

  // --------------------------------------------------------------------- logs
  function logRow(ev, fresh) {
    const tr = el("tr", { className: `sev-${ev.severity}${fresh ? " fresh" : ""}` });
    [ev.timestamp, ev.event_type, ev.details].forEach(v => tr.append(el("td", { textContent: v })));
    tr.append(el("td", { textContent: ev.severity }));
    return tr;
  }

  async function fetchLogs() {
    try {
      const compact = await (await fetch("/api/logs?limit=100", { cache: "no-store" })).json();
      const maxId = compact.events.length ? compact.events[0].id : 0;
      const fresh = id => lastLogId && id > lastLogId;
      bound("log-rows").forEach(tb => tb.replaceChildren(...compact.events.map(ev => logRow(ev, fresh(ev.id)))));
      setText("log-total", String(compact.total));
      const full = bound("log-rows-full");
      if (full.length) {
        const sev = ($("#sev-filter") || {}).value || "";
        const res = await (await fetch(`/api/logs?limit=1000&severity=${encodeURIComponent(sev)}`, { cache: "no-store" })).json();
        full.forEach(tb => tb.replaceChildren(...(res.events.length ? res.events.map(ev => logRow(ev, fresh(ev.id)))
          : [el("tr", {}, el("td", { colSpan: 4, className: "muted", textContent: "No events" }))])));
      }
      lastLogId = maxId;
    } catch (e) {
      console.warn("log fetch failed", e);
    }
  }

  // ------------------------------------------------------------------ actions
  async function postAction(action, password) {
    try {
      const res = await fetch("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, password }),
      });
      return await res.json();
    } catch (e) {
      return { ok: false, message: "Station unreachable" };
    }
  }

  function showMsg(node, result) {
    node.textContent = result.message;
    node.className = `msg ${result.ok ? "ok" : "err"}`;
    clearTimeout(node._timer);
    node._timer = setTimeout(() => { node.textContent = ""; }, 4000);
  }

  document.addEventListener("submit", async e => {
    const form = e.target;
    if (form.classList.contains("auth-form")) {
      e.preventDefault();
      const input = form.elements.password, btn = $("button[type=submit]", form);
      const action = state && state.armed ? "disarm" : "arm";
      btn.disabled = true;
      const result = await postAction(action, input.value);
      btn.disabled = false;
      input.value = "";
      showMsg($(".msg", form), result);
    } else if (form.id === "pw-form") {
      e.preventDefault();
      const input = form.elements.password;
      const result = await postAction(pendingAction, input.value);
      input.value = "";
      if (result.ok) {
        $("#pw-dialog").close();
      } else {
        showMsg($("#pw-msg"), result);
        input.focus();
      }
    }
  });

  function askPassword(action) {
    pendingAction = action;
    $("#pw-title").textContent = `${ACTION_LABELS[action]}: password required`;
    $("#pw-msg").textContent = "";
    const dialog = $("#pw-dialog");
    dialog.showModal();
    dialog.querySelector("input").focus();
  }
  $("#pw-cancel").addEventListener("click", () => $("#pw-dialog").close());

  // ----------------------------------------------------------- expand/collapse
  function route() {
    const name = decodeURIComponent(location.hash.slice(1));
    if (TITLES[name]) open(name); else close();
  }

  function open(name) {
    if (expanded === name) return;
    expanded = name;
    $("#expanded-title").textContent = TITLES[name];
    $("#expanded-body").replaceChildren($(`#tpl-${name}`).content.cloneNode(true));
    $("#expanded").hidden = false;
    $("#dashboard").inert = true;
    document.body.style.overflow = "hidden";
    const filter = $("#sev-filter");
    if (filter) filter.addEventListener("change", fetchLogs);
    observeCanvases($("#expanded-body"));
    render();
    if (name === "logs") fetchLogs();
    $("#back").focus();
  }

  function close() {
    if (!expanded) return;
    const was = expanded;
    expanded = null;
    $("#expanded").hidden = true;
    $("#expanded-body").replaceChildren();
    $("#dashboard").inert = false;
    document.body.style.overflow = "";
    const tile = $(`.tile[data-tile="${was}"]`);
    if (tile) tile.focus({ preventScroll: true });
    drawAllCharts();
  }

  function expand(name) {
    history.pushState({ expanded: name }, "", `#${name}`);
    route();
  }

  function back() {
    if (history.state && history.state.expanded) history.back();
    else { history.replaceState(null, "", location.pathname); route(); }
  }

  window.addEventListener("popstate", route);
  $("#back").addEventListener("click", back);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && expanded && !$("#pw-dialog").open) back();
  });

  document.addEventListener("click", e => {
    const actionBtn = e.target.closest("[data-action]");
    if (actionBtn) { askPassword(actionBtn.dataset.action); return; }
    if (e.target.closest('[data-logs="refresh"]')) { fetchLogs(); return; }
    const tile = e.target.closest("#dashboard .tile");
    if (!tile) return;
    const interactive = e.target.closest("button:not(.expand), input, a, select, label, form, .table-wrap");
    if (interactive) return;
    expand(tile.dataset.tile);
  });
  $("#dashboard").addEventListener("keydown", e => {
    if ((e.key === "Enter" || e.key === " ") && e.target.classList.contains("tile")) {
      e.preventDefault();
      expand(e.target.dataset.tile);
    }
  });

  // ---------------------------------------------------------- live updates
  const resizeObserver = new ResizeObserver(() => drawAllCharts());
  function observeCanvases(root) { $$("canvas", root).forEach(c => resizeObserver.observe(c)); }
  observeCanvases(document);

  function setConn(stateName, text) {
    const c = $("#conn");
    c.dataset.state = stateName;
    c.textContent = text;
  }

  function accept(snapshot) {
    state = snapshot;
    clockOffset = state.server_time - Date.now() / 1000;
    render();
  }

  function connect() {
    const es = new EventSource("/api/events");
    es.onopen = () => setConn("live", "● live");
    es.onmessage = e => { setConn("live", "● live"); accept(JSON.parse(e.data)); };
    es.onerror = () => setConn("connecting", "reconnecting…");
  }

  fetch("/api/state", { cache: "no-store" }).then(r => r.json()).then(accept).catch(() => {});
  connect();
  setInterval(tick, 1000);
  route();
})();

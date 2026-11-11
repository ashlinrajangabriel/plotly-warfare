// Animation, done inside the Plotly maps themselves (no canvas, no other library).
//
// Plotly draws every unit as an <image> in its own SVG. After each update we find those images by the
// unit id in their URL and glide them from the old tile to the new one (ease in and out, so units
// accelerate and brake), turn them by their heading, and bob ships on the water. Shells, missiles,
// explosions, wakes and work particles are small SVG shapes added to the same Plotly SVG.
const Anim = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const XLINK = "http://www.w3.org/1999/xlink";
  const prev = {};            // map name -> {unit id: unit} from the previous update
  const live = {};            // map name -> [{node, ship, bobPhase, from, hTo, t0, dur}]
  const fx = [];              // active effects
  let speed = 1, raf = null, lastFrame = 0;

  const ease = (p) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2);   // accelerate, then brake
  const turn = (a, b) => ((b - a + 540) % 360) - 180;                                // shortest way round

  function geom(gd) {
    const L = gd._fullLayout, xa = L.xaxis, ya = L.yaxis, H = L.meta.H;
    return { xa, ya, H, tw: Math.abs(xa.l2p(1) - xa.l2p(0)), th: Math.abs(ya.l2p(1) - ya.l2p(0)) };
  }
  // centre of tile (c, r) in the plot SVG's pixels
  function px(gd, c, r) {
    const g = geom(gd);
    return [g.xa._offset + g.xa.l2p(c + 0.5), g.ya._offset + g.ya.l2p(g.H - r - 0.5)];
  }
  function layer(gd) {
    const svg = gd.querySelector(".main-svg");
    if (!svg) return null;
    let g = svg.querySelector(".fx-layer");
    if (!g) { g = document.createElementNS(NS, "g"); g.setAttribute("class", "fx-layer"); g.style.pointerEvents = "none"; svg.appendChild(g); }
    return g;
  }
  function mk(gd, tag, attrs) {
    const l = layer(gd);
    if (!l) return null;
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    l.appendChild(e);
    return e;
  }
  function add(item) { item.t0 = performance.now(); fx.push(item); start(); }

  // ---- effects ----
  function puff(gd, x, y, { color = "#fff", r0 = 3, r1 = 12, ms = 900, op = 0.55, dy = 0 } = {}) {
    const e = mk(gd, "circle", { cx: x, cy: y, r: r0, fill: color });
    if (!e) return;
    add({ dur: ms / speed, upd: (p) => { e.setAttribute("r", r0 + (r1 - r0) * p); e.setAttribute("cy", y + dy * p); e.setAttribute("opacity", op * (1 - p)); }, end: () => e.remove() });
  }
  function ring(gd, x, y, r1, { color = "#fff", ms = 700, w = 3 } = {}) {
    const e = mk(gd, "circle", { cx: x, cy: y, r: 2, fill: "none", stroke: color, "stroke-width": w });
    if (!e) return;
    add({ dur: ms / speed, upd: (p) => { e.setAttribute("r", 2 + r1 * p); e.setAttribute("opacity", 1 - p); }, end: () => e.remove() });
  }
  function flash(gd, x, y, r = 9) {
    const e = mk(gd, "circle", { cx: x, cy: y, r, fill: "#ffe9a0" });
    if (e) add({ dur: 110 / speed, upd: (p) => e.setAttribute("opacity", 0.95 * (1 - p)), end: () => e.remove() });
  }
  function projectile(gd, a, b, ms, arc, { color = "#ffd166", trail = null, size = 3 } = {}) {
    const e = mk(gd, "circle", { r: size, fill: color, cx: a[0], cy: a[1] });
    if (!e) return;
    let last = 0;
    add({ dur: ms / speed, upd: (p, now) => {
      const x = a[0] + (b[0] - a[0]) * p, y = a[1] + (b[1] - a[1]) * p - arc * 4 * p * (1 - p);
      e.setAttribute("cx", x); e.setAttribute("cy", y); e.setAttribute("r", size + (arc > 30 ? 2 * 4 * p * (1 - p) : 0));
      if (trail && now - last > 70 / speed) { last = now; puff(gd, x, y, { color: trail, r0: 2, r1: 6, ms: 700, op: 0.5 }); }
    }, end: () => e.remove() });
  }
  function shake(gd, ms = 600, amp = 6) {
    add({ dur: ms / speed, upd: (p) => { gd.style.transform = `translate(${(Math.random() - 0.5) * amp * (1 - p)}px, ${(Math.random() - 0.5) * amp * (1 - p)}px)`; }, end: () => { gd.style.transform = ""; } });
  }

  // ---- shots, missiles, impacts, called once per server event ----
  function event(gd, e) {
    if (!gd._fullLayout || !gd._fullLayout.meta || e.c === null || e.c === undefined) return;
    const g = geom(gd), a = px(gd, e.c, e.r), b = e.c2 != null ? px(gd, e.c2, e.r2) : null;
    const dist = b ? Math.hypot(b[0] - a[0], b[1] - a[1]) : 0;
    switch (e.kind) {
      case "gun":                                           // a squad opens up: several rifles, a little out of step
        for (let i = 0; i < 4; i++) {
          const ox = (Math.random() - 0.5) * g.tw * 0.5, oy = (Math.random() - 0.5) * g.th * 0.5, A = [a[0] + ox, a[1] + oy];
          setTimeout(() => { flash(gd, A[0], A[1], 4); if (b) projectile(gd, A, [b[0] + ox * 0.3, b[1] + oy * 0.3], 150, 0, { color: "#fff2b0", size: 1.6 }); }, i * 70 / speed);
        }
        break;
      case "cannon":                                        // a battery or a tank group fires in a ragged volley
        for (let i = 0; i < 3; i++) {
          const ox = (Math.random() - 0.5) * g.tw * 0.6, oy = (Math.random() - 0.5) * g.th * 0.6, A = [a[0] + ox, a[1] + oy];
          setTimeout(() => { flash(gd, A[0], A[1], 9); puff(gd, A[0], A[1], { color: "#ccc", r0: 5, r1: 18, ms: 1000 });
            if (b) projectile(gd, A, [b[0] + ox * 0.4, b[1] + oy * 0.4], 520, 14 + dist * 0.35, { color: "#ffd166", trail: "#ddd", size: 3 }); }, i * 140 / speed);
        }
        break;
      case "launch": puff(gd, a[0], a[1], { color: "#fff", r0: 6, r1: 34, ms: 1800, op: 0.7 });
        if (b) projectile(gd, a, b, (e.dur || 6) * 1000, 70 + dist * 0.5, { color: "#fff", trail: "#f0d9c0", size: 4 }); break;
      case "miss": ring(gd, a[0], a[1], g.tw * 0.5, { color: "#bfe6ff" }); puff(gd, a[0], a[1], { color: "#9fd0f0", r0: 3, r1: 14, ms: 800 }); break;
      case "hit": flash(gd, a[0], a[1], 7); for (let i = 0; i < 4; i++) puff(gd, a[0] + (Math.random() - 0.5) * 10, a[1] + (Math.random() - 0.5) * 10, { color: "#ffb347", r0: 1.5, r1: 4, ms: 400, op: 0.9 }); break;
      case "boom": puff(gd, a[0], a[1], { color: "#ff9a3c", r0: 4, r1: g.tw * 0.8, ms: 600, op: 0.95 });
        puff(gd, a[0], a[1], { color: "#555", r0: 6, r1: g.tw * 1.1, ms: 1600, op: 0.5, dy: -14 }); ring(gd, a[0], a[1], g.tw * 1.3, { color: "#ffd9a0", ms: 500 }); break;
      case "coup": for (let i = 0; i < 4; i++) setTimeout(() => ring(gd, a[0], a[1], g.tw * (2 + i), { color: "#ff2bd6", ms: 1400, w: 5 }), i * 260 / speed); shake(gd, 700, 6); break;
      case "nuke": { const l = gd.querySelector(".main-svg"); const r = mk(gd, "rect", { x: 0, y: 0, width: l.getAttribute("width"), height: l.getAttribute("height"), fill: "#fff" });
        if (r) add({ dur: 1800 / speed, upd: (p) => r.setAttribute("opacity", 0.95 * Math.pow(1 - p, 2)), end: () => r.remove() });
        ring(gd, a[0], a[1], g.tw * 4.5, { color: "#fff", ms: 1800, w: 6 }); puff(gd, a[0], a[1], { color: "#ffcf70", r0: 10, r1: g.tw * 4, ms: 1600, op: 0.9 }); shake(gd, 900, 10); break; }
    }
  }

  // ---- unit movement ----
  function nodesById(gd) {
    const out = {};                                        // a unit drawn as a group of tanks has several pictures
    for (const n of gd.querySelectorAll("image")) {
      const h = n.getAttribute("href") || n.getAttributeNS(XLINK, "href") || "";
      const m = /[?&]u=([^&]+)/.exec(h);
      if (m) (out[decodeURIComponent(m[1])] = out[decodeURIComponent(m[1])] || []).push(n);
    }
    return out;
  }

  function onRender(name, gd, fig) {
    const meta = fig.layout && fig.layout.meta;
    if (!meta || !gd._fullLayout) return;
    const nodes = nodesById(gd), before = prev[name] || {}, now = {}, list = [];
    const g = geom(gd), t0 = performance.now(), dur = Math.max(300, 950 / speed);
    for (const u of meta.units) {
      now[u.id] = u;
      const group = nodes[u.id];
      if (!group) continue;
      const p = before[u.id];
      const moved = p && (p.c !== u.c || p.r !== u.r);
      const from = p ? { dx: (p.c - u.c) * g.tw, dy: (p.r - u.r) * g.th, h: p.h } : { dx: 0, dy: 0, h: u.h };
      group.forEach((node, i) => {
        node.style.transformBox = "fill-box"; node.style.transformOrigin = "50% 50%";
        if (u.air && u.up) node.style.filter = "drop-shadow(7px 9px 3px rgba(0,0,0,.5))"; else node.style.filter = "";   // altitude: a shadow far below
        list.push({ node, ship: u.ship, foot: u.t === "infantry" || u.t === "rebel", rolling: !u.ship && !u.air && u.t !== "infantry" && u.t !== "rebel",
          up: u.air && u.up, mv: u.mv || !!moved, phase: Math.random() * 6.28 + i, from, h: u.h, t0, dur, moving: !!moved || from.h !== u.h });
      });
      if (moved) {                                       // a wake behind ships, dust behind vehicles
        const a = px(gd, p.c, p.r), b = px(gd, u.c, u.r);
        for (let i = 0; i < 3; i++) {
          const k = i / 3;
          puff(gd, a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, u.ship ? { color: "#fff", r0: 2, r1: 9, ms: 1400, op: 0.45 } : { color: "#c9b38a", r0: 2, r1: 8, ms: 1000, op: 0.4 });
        }
      }
      if (u.j) {                                          // someone is at work: bubbles, dust or sparks
        const c = px(gd, u.c, u.r);
        for (let i = 0; i < 3; i++) puff(gd, c[0] + (Math.random() - 0.5) * g.tw * 0.6, c[1] + (Math.random() - 0.5) * g.th * 0.4,
          u.j === "clear" && u.ship ? { color: "#bfe6ff", r0: 1.5, r1: 4, ms: 900, op: 0.8, dy: -16 } : u.j === "dig" || u.j === "plant" ? { color: "#a58a5e", r0: 2, r1: 7, ms: 900, op: 0.6, dy: -8 } : { color: "#ffd166", r0: 1.5, r1: 3, ms: 500, op: 0.9 });
      }
    }
    prev[name] = now;
    live[name] = list;
    alerts(name, gd, meta);
    start();
  }

  // pulsing rings for infiltrators (orange dashed = militants, red = enemy military), coup watch and coup (magenta)
  const alertFx = {};
  function alerts(name, gd, meta) {
    for (const item of alertFx[name] || []) { item.end(); const i = fx.indexOf(item); if (i >= 0) fx.splice(i, 1); }
    alertFx[name] = [];
    for (const a of meta.alerts || []) {
      const [x, y] = px(gd, a.c, a.r), tw = geom(gd).tw;
      const e = mk(gd, "circle", { cx: x, cy: y, r: tw * a.r0, fill: "none", stroke: a.color, "stroke-width": a.w || 2.5, "stroke-dasharray": a.dash || "" });
      if (!e) continue;
      const item = { t0: performance.now(), dur: 1e12, end: () => e.remove(),
        upd: (p, now) => { const k = ((now + a.c * 97 + a.r * 31) % a.period) / a.period; e.setAttribute("r", tw * (a.r0 + a.r1 * k)); e.setAttribute("opacity", 1 - 0.75 * k); } };
      fx.push(item); alertFx[name].push(item);
    }
  }

  function frame(ts) {
    raf = requestAnimationFrame(frame);
    if (ts - lastFrame < 30) return;                      // about 33 frames a second is plenty
    lastFrame = ts;
    const now = performance.now();
    for (const name in live) {
      for (const a of live[name]) {
        const p = Math.min(1, (now - a.t0) / a.dur), e = ease(p);
        const dx = a.from.dx * (1 - e), dy = a.from.dy * (1 - e);
        const ang = a.from.h + turn(a.from.h, a.h) * e;
        let bob = a.ship ? Math.sin(now / 700 + a.phase) : 0;             // ships ride the swell a little
        let lift = 0, sway = 0, scale = 1;
        if (a.mv && a.foot) { const s = Math.sin(now / 120 + a.phase); lift = -Math.abs(s) * 2.2; sway = s * 3.2; }      // marching: a step, a sway
        else if (a.mv && a.rolling) lift = Math.sin(now / 55 + a.phase) * 0.6;                                           // tracks and wheels shudder
        if (a.up) { scale = 1.15 + 0.04 * Math.sin(now / 900 + a.phase); lift += Math.sin(now / 500 + a.phase) * 1.2; }  // aircraft ride high
        a.node.style.transform = `translate(${dx}px, ${dy + bob * 0.9 + lift}px) rotate(${ang + bob * 1.4 + sway}deg) scale(${scale})`;
      }
    }
    for (let i = fx.length - 1; i >= 0; i--) {
      const f = fx[i], p = Math.min(1, (now - f.t0) / f.dur);
      f.upd(p, now);
      if (p >= 1) { f.end && f.end(); fx.splice(i, 1); }
    }
  }
  function start() { if (!raf) raf = requestAnimationFrame(frame); }

  // pulsing rings that point at tiles (hover a report and the map shows where it is about)
  const focused = [];
  function focus(gds, points) {
    unfocus();
    for (const gd of gds) {
      if (!gd._fullLayout || !gd._fullLayout.meta) continue;
      points.forEach((pt, i) => {
        if (!pt) return;
        const [x, y] = px(gd, pt[0], pt[1]), tw = geom(gd).tw;
        const e = mk(gd, "circle", { cx: x, cy: y, r: tw * 0.6, fill: "none", stroke: i ? "#ff5c4d" : "#ffd23f", "stroke-width": 3 });
        if (!e) return;
        const item = { t0: performance.now(), dur: 1e12, upd: (p, now) => { const k = (now % 900) / 900; e.setAttribute("r", tw * (0.55 + 0.35 * k)); e.setAttribute("opacity", 1 - 0.6 * k); }, end: () => e.remove() };
        fx.push(item); focused.push(item);
      });
    }
    start();
  }
  function unfocus() {
    for (const item of focused) { item.end(); const i = fx.indexOf(item); if (i >= 0) fx.splice(i, 1); }
    focused.length = 0;
  }

  return {
    onRender, event, focus, unfocus,
    setSpeed: (s) => { speed = s || 1; },
  };
})();

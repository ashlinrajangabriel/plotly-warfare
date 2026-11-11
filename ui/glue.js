// Browser glue (vanilla JS): live Plotly maps, the General's reports, radio and Morse, chat, optional WebLLM voice.
const $ = (id) => document.getElementById(id);
const maps = { home: $("map-home"), enemy: $("map-enemy") };

const params = new URLSearchParams(location.search);
let side = params.get("side") === "referee" ? "referee" : "blue";
let sym = sessionStorage.getItem("sym") === "tac" ? "tac" : "real";
let callMode = null;                       // set while the General is choosing where reinforcements should arrive
const bound = new Set();
const lastClick = { c: -1, r: -1, t: 0 };
let focusId = null;                        // the report the pointer is over (its place is ringed on the maps)
let busy = false, dirty = false, lastRadioId = null, llm = null, audio = null;

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ side, sym, ...body }),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

// ---------- sound (Web Audio, all synthesized: no files, no licences) ----------
let master = null, noiseBuffer = null, sfxLast = 0;
window.__sfxLog = [];                                    // kinds played, for testing

function ac() {
  if (!audio) {
    audio = new (window.AudioContext || window.webkitAudioContext)();
    master = audio.createGain(); master.gain.value = 0.55; master.connect(audio.destination);
    noiseBuffer = audio.createBuffer(1, audio.sampleRate * 2, audio.sampleRate);
    const d = noiseBuffer.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  }
  if (audio.state === "suspended") audio.resume();
  return audio;
}

function out(a, pan) {                                   // a stereo position from the map column (-1 left .. 1 right)
  if (pan && a.createStereoPanner) { const p = a.createStereoPanner(); p.pan.value = pan; p.connect(master); return p; }
  return master;
}

// a burst of filtered noise: gunfire, explosions, wind, radio static
function noise(t0, dur, { type = "lowpass", f0 = 800, f1 = f0, gain = 0.4, pan = 0 } = {}) {
  const a = ac(), src = a.createBufferSource(), f = a.createBiquadFilter(), g = a.createGain();
  src.buffer = noiseBuffer; f.type = type;
  f.frequency.setValueAtTime(f0, t0); f.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t0 + dur);
  g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(gain, t0 + 0.006);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  src.connect(f); f.connect(g); g.connect(out(a, pan));
  src.start(t0, Math.random()); src.stop(t0 + dur + 0.02);
}

// a pitched tone that can glide: thumps, pings, sirens, chimes
function tone(t0, dur, { type = "sine", f0 = 440, f1 = f0, gain = 0.3, pan = 0 } = {}) {
  const a = ac(), o = a.createOscillator(), g = a.createGain();
  o.type = type; o.frequency.setValueAtTime(f0, t0); o.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t0 + dur);
  g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(gain, t0 + 0.008);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  o.connect(g); g.connect(out(a, pan)); o.start(t0); o.stop(t0 + dur + 0.02);
}

const SFX = {
  gun: (t, p) => { noise(t, 0.09, { type: "highpass", f0: 1800, gain: 0.35, pan: p }); tone(t, 0.05, { f0: 160, f1: 70, gain: 0.25, pan: p }); },
  cannon: (t, p) => { noise(t, 0.35, { f0: 1100, f1: 150, gain: 0.55, pan: p }); tone(t, 0.3, { f0: 110, f1: 40, gain: 0.5, pan: p }); },
  hit: (t, p) => { tone(t, 0.12, { type: "square", f0: 520, f1: 140, gain: 0.18, pan: p }); noise(t, 0.08, { type: "bandpass", f0: 2500, gain: 0.2, pan: p }); },
  boom: (t, p) => { noise(t, 1.0, { f0: 900, f1: 60, gain: 0.8, pan: p }); tone(t, 0.9, { f0: 85, f1: 28, gain: 0.7, pan: p }); },
  // a missile: the roar of the motor while it climbs, then (a second or so before impact) the whistle of its fall
  launch: (t, p, ev) => {
    const flight = Math.max(2, ((ev && ev.dur) || 6) / gameSpeed);
    noise(t, Math.min(flight, 3.2), { type: "bandpass", f0: 250, f1: 1700, gain: 1.0, pan: p });
    noise(t, 1.1, { type: "lowpass", f0: 900, f1: 120, gain: 0.9, pan: p });
    tone(t, Math.min(flight, 3.2), { type: "sawtooth", f0: 70, f1: 230, gain: 0.3, pan: p });
    tone(t + Math.max(0.5, flight - 1.4), 1.3, { type: "sine", f0: 2200, f1: 450, gain: 0.35 });
    noise(t + Math.max(0.5, flight - 1.4), 1.3, { type: "highpass", f0: 1500, f1: 800, gain: 0.25 });
  },
  nuke: (t) => { noise(t, 3.5, { f0: 700, f1: 30, gain: 1.0 }); tone(t, 3.2, { f0: 60, f1: 20, gain: 0.9 }); noise(t + 0.2, 2.5, { type: "bandpass", f0: 200, f1: 40, gain: 0.7 }); },
  chime: (t) => { tone(t, 0.35, { f0: 880, gain: 0.2 }); tone(t + 0.14, 0.45, { f0: 1320, gain: 0.2 }); },
  alarm: (t) => { for (let i = 0; i < 5; i++) tone(t + i * 0.28, 0.26, { type: "square", f0: i % 2 ? 950 : 700, gain: 0.16 }); },
  coup: (t) => { for (let i = 0; i < 4; i++) tone(t + i * 0.5, 0.5, { type: "sawtooth", f0: 180, f1: 90, gain: 0.2 }); noise(t, 2.0, { f0: 300, f1: 50, gain: 0.45 }); },
  squelch: (t) => { noise(t, 0.1, { type: "bandpass", f0: 2200, gain: 0.22 }); tone(t, 0.04, { type: "square", f0: 1300, gain: 0.08 }); },
  miss: (t, p) => { noise(t, 0.35, { type: "bandpass", f0: 1400, f1: 500, gain: 0.25, pan: p }); },
  rumble: (t) => { noise(t, 1.4, { f0: 160, f1: 40, gain: 0.3 }); },
};

let gameSpeed = 0.5;                                       // real seconds per game second, so a missile's sound lasts as long as its flight

function playSfx(kind, c, ev) {
  const a = ac(), fn = SFX[kind];
  if (!fn) return;
  window.__sfxLog.push(kind); window.__sfxLog.splice(0, window.__sfxLog.length - 50);
  fn(a.currentTime + 0.01, c == null ? 0 : ((c / 19) * 2 - 1) * 0.7, ev);
}

function soundEvents(p) {
  const top = p.sfx.length ? p.sfx[p.sfx.length - 1].id : 0;
  if (top < sfxLast) sfxLast = 0;                         // a new game restarted the numbering
  Anim.setSpeed(p.speed);
  gameSpeed = p.speed || 1;
  let played = 0;
  for (const s of p.sfx) {
    if (s.id <= sfxLast) continue;
    if (lastRadioId !== null || sfxLast > 0) {            // not the backlog that arrives with the first page load
      if ($("sound").checked && played++ < 8) playSfx(s.kind, s.c, s);
      for (const name in maps) if (!maps[name].hidden && maps[name].parentElement && !maps[name].parentElement.hidden) Anim.event(maps[name], s);
    }
  }
  sfxLast = Math.max(sfxLast, top);
}

// Morse beeps, 650 Hz, standard timing
function playMorse(code) {
  const a = ac(), unit = 0.075;
  let t = a.currentTime + 0.05;
  for (const tok of code.split(/\s+/)) {
    if (tok === "/") { t += unit * 4; continue; }          // word gap (3 from the letter gap + 4 = 7)
    for (const s of tok) { const len = s === "." ? unit : unit * 3; tone(t, len, { f0: 650, gain: 0.25 }); t += len + unit; }
    t += unit * 2;                                          // letter gap (1 + 2 = 3)
  }
}

// ---------- spoken radio (the browser's built-in speech synthesis) ----------
const VOICE_STYLE = { eager: { rate: 1.12, pitch: 1.1 }, calm: { rate: 0.98, pitch: 0.95 }, cautious: { rate: 0.9, pitch: 0.85 }, hq: { rate: 1.0, pitch: 0.75 } };
let temperaments = {};                                    // callsign -> temperament, from the unit list

let queued = 0;                                           // lines waiting to be spoken; the net never falls far behind

function speak(who, text) {
  if (!("speechSynthesis" in window)) return;
  if (queued >= 4) return;                                // too much traffic: drop this line, never cut the one being spoken
  const style = VOICE_STYLE[temperaments[who]] || VOICE_STYLE.hq;
  const spoken = `${who.replace("-", " ")}. ${text}`.replace(/-(\d)/g, " $1").replace(/\bHP\b/g, "H P").replace(/\bETA\b/g, "E T A").replace(/\bsec\b/g, "seconds");
  const u = new SpeechSynthesisUtterance(spoken);
  Object.assign(u, style, { volume: 1, lang: "en-US" });
  const voices = speechSynthesis.getVoices();                          // may be empty until the browser has loaded them
  const v = voices.find((x) => /en[-_]/i.test(x.lang)) || voices[0];
  if (v) u.voice = v;
  queued++;
  u.onstart = () => { if ($("sound").checked) playSfx("squelch"); };
  u.onend = () => { queued = Math.max(0, queued - 1); if ($("sound").checked) playSfx("squelch"); };
  u.onerror = () => { queued = Math.max(0, queued - 1); };
  if (speechSynthesis.paused) speechSynthesis.resume();                // some browsers get stuck paused
  speechSynthesis.speak(u);
}
if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = () => speechSynthesis.getVoices();

// ---------- panel ----------
function el(tag, props = {}, ...kids) {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids);
  return e;
}

function renderReports(p) {
  const box = $("reports");
  if (!p.reports.length) {
    box.replaceChildren(el("div", { className: "muted", textContent: "Nothing waiting for a decision. Press “Status of all units”, or wait for your units to report." }));
    return;
  }
  box.replaceChildren(...p.reports.map((r) => el("div", {
    className: `card ${r.kind}`, title: "Hover to see on the map where this is. Click the callsign to select the unit.",
    onmouseenter: () => { focusId = r.id; Anim.focus(Object.values(maps), [r.at, r.foe]); },
    onmouseleave: () => { focusId = null; Anim.unfocus(); },
  },
    el("span", { className: "left", textContent: `${r.left}s` }),
    el("b", { textContent: r.callsign, style: "cursor:pointer", onclick: async () => render(await api("/api/select", { uid: r.uid })) }), " reports: " + r.text,
    r.brief.length ? el("ul", { className: "brief" }, ...r.brief.map((t) => el("li", { textContent: t }))) : "",
    el("div", { className: "opts" }, ...r.options.map((o) => el("div", { className: "opt" },
      el("button", {
        textContent: o.label,
        onclick: async () => { focusId = null; Anim.unfocus(); render(await api("/api/choose", { report: r.id, option: o.id })); },
      }), o.info ? el("div", { className: "info", textContent: o.info }) : ""))))));
  const open = p.reports.find((r) => r.id === focusId);            // keep the pointer rings while the list is redrawn
  if (open) Anim.focus(Object.values(maps), [open.at, open.foe]); else Anim.unfocus();
}

function renderRadio(p) {
  const box = $("radio");
  const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 8;
  box.className = $("show-morse").checked ? "" : "nomorse";
  const alert = /MAYDAY|CODE RED|sinking|friendly fire|taking hit|unprepared/i;
  box.replaceChildren(...p.radio.map((e) => el("div", { className: e.dir + (e.dir === "in" && alert.test(e.text) ? " alert" : "") },
    `[${e.time}] ${e.dir === "out" ? "GENERAL → " + e.who : e.who + " → GENERAL"}${e.kind === "morse" ? " (Morse)" : ""}: ${e.text} `,
    el("button", { className: "play", title: "Play the Morse", textContent: "▶", onclick: () => playMorse(e.morse) }),
    el("span", { className: "m", textContent: e.morse }))));
  if (atBottom) box.scrollTop = box.scrollHeight;
  // what just arrived is heard: Morse as beeps, voice as speech, each preceded by a radio squelch
  const newest = p.radio.length ? p.radio[p.radio.length - 1].id : null;
  if (lastRadioId !== null) {
    for (const e of p.radio.filter((x) => x.id > lastRadioId && x.dir === "in")) {
      if (e.kind === "morse") {
        if ($("sound").checked && e.morse.length < 80) playMorse(e.morse);                       // the beeps...
        if ($("voice").checked) speak(e.who, `by Morse: ${e.text}`);                             // ...and the operator reads them out
      } else if ($("voice").checked) speak(e.who, e.text);
      else if ($("sound").checked) playSfx("squelch");
    }
  }
  if (newest !== null) lastRadioId = newest;
}

function renderAgents(p) {
  const sel = $("chat-to").value;
  $("agents").replaceChildren(...p.agents.map((a) => {
    const tr = el("tr", { className: a.id === (p.selected && p.selected.id) ? "sel" : "", onclick: async () => {
      $("chat-to").value = a.id;
      render(await api("/api/select", { uid: a.id }));
    } },
      el("td", { textContent: a.callsign }), el("td", { className: "muted", textContent: a.label }),
      el("td", { textContent: `${a.hp}/${a.max_hp}` }), el("td", { className: "muted", textContent: `${a.pos}` }),
      el("td", { className: "muted", textContent: (a.hold ? "[hold] " : "") + a.order }));
    return tr;
  }));
  const opts = [el("option", { value: "all", textContent: "All units" }), ...p.agents.map((a) => el("option", { value: a.id, textContent: a.callsign }))];
  $("chat-to").replaceChildren(...opts);
  $("chat-to").value = [...$("chat-to").options].some((o) => o.value === sel) ? sel : "all";
}

function renderWar(p) {
  const w = p.war;
  $("verdict").textContent = w.verdict;
  $("verdict").className = w.verdict;
  $("balance-fill").style.width = `${w.balance}%`;
  $("balance-text").textContent = `War balance ${w.balance}% in our favour`;
  $("bars").replaceChildren(...w.bars.map((b) => el("div", { className: "bar" }, el("small", { textContent: b.label }),
    el("div", { className: "meter" }, el("div", { style: `width:${b.pct}%` })), el("small", { style: "width:auto", textContent: b.note }))));
  $("reasons").textContent = w.reasons.join(" ");
  $("howwin").replaceChildren(el("b", { textContent: "To win:" }), ...w.win.map((x) => el("div", { className: "win-item" + (x.done ? " done" : ""), textContent: `${x.done ? "✔" : "○"} ${x.label} — ${x.note}` })));
  $("howlose").replaceChildren(el("b", { textContent: "You lose if:" }), ...w.lose.map((x) => el("div", { className: "win-item", textContent: `${x.risk > .66 ? "⚠" : "·"} ${x.label} — ${x.note}` })));
}

function renderHome(p) {
  const h = p.home;
  $("hf-box").hidden = !h.on;
  if (!h.on) return;
  $("hf-points").textContent = `intelligence ${h.points}/5`;
  const row = (label, v, bad, who) => el("div", { className: "bar" }, el("small", { textContent: label }),
    el("div", { className: "meter" }, el("div", { style: `width:${v}%;background:${(bad ? v > 66 : v < 34) ? "#d85f4a" : (bad ? v > 40 : v < 55) ? "#e0a526" : "#5fb36a"}` })),
    el("small", { style: "width:34px;text-align:right", textContent: String(v) }));
  const names = [["stability", "Government stability", false], ["economy", "Markets and economy", false], ["corruption", "Corruption", true], ["unrest", "Unrest in the streets", true]];
  $("hf").replaceChildren(el("div", { className: "muted", textContent: "Ladooo (ours)" }), ...names.map(([k, l, bad]) => row(l, h.mine[k], bad)),
    el("div", { className: "muted", style: "margin-top:4px", textContent: "Candooo" + (h.enemy ? " (rough picture from our spies)" : " (no intelligence: keep a spy alive)") }),
    ...(h.enemy ? names.map(([k, l, bad]) => row(l, h.enemy[k], bad)) : []));
  const btn = (o) => el("button", { textContent: o.label + (o.cost ? ` (${o.cost})` : ""), disabled: !o.enabled, title: `${o.note}${o.why ? "  —  " + o.why : ""}`,
    onclick: async () => render(await api("/api/home", { name: o.id })) });
  $("hf-internal").replaceChildren(...h.ops.filter((o) => !o.covert).map(btn));
  $("hf-covert").replaceChildren(...h.ops.filter((o) => o.covert).map(btn));
  $("hf-news").replaceChildren(...h.news.map((n) => el("div", { textContent: n })));
}

function renderSupply(p) {
  const s = p.supply;
  for (const k of ["fuel", "food"]) {
    $(`${k}-fill`).style.width = `${s[k]}%`;
    $(`${k}-text`).textContent = `${k === "fuel" ? "Fuel" : "Food"} ${s[k]}%` + (s.enemy ? `  (enemy ${s.enemy[k]}%)` : "");
  }
  $("late").textContent = s.late ? `orders ${s.late} s late` : "";
}

function renderReinforce(p) {
  $("reinf").replaceChildren(...Object.entries(p.reinforce).map(([kind, v]) => el("button", {
    textContent: `${v.label} (${v.left}) · ${v.eta} s`, disabled: v.left <= 0 || side === "referee",
    onclick: async () => {
      if (v.needs_tile) { callMode = kind; $("reinf-hint").textContent = `Click a tile on the map where the ${v.label.toLowerCase()} should arrive (our territory).`; }
      else render(await api("/api/reinforce", { kind }));
    },
  })));
  $("arrivals").textContent = p.arrivals.length ? "On the way: " + p.arrivals.map((a) => `${a.label} at ${a.pos} in ${a.left} s`).join("; ") : "";
}

function renderActions(p) {
  const s = p.selected, acts = (s && s.actions) || [];
  const traps = s && s.armed ? [
    el("button", { textContent: s.ambush ? "In ambush" : "Set an ambush", disabled: s.ambush, title: "Hide and hold fire until the enemy walks close; then everyone nearby fires at once for double damage",
      onclick: async () => render(await api("/api/trap", { uid: s.id, kind: "ambush" })) }),
    el("button", { textContent: s.lure ? "Baiting…" : "Lure into a trap", disabled: s.lure, title: "This unit goes out until the enemy sees it, then runs to the tile you click: put an ambush there",
      onclick: () => { callMode = "lure:" + s.id; $("reinf-hint").textContent = "Click the tile where the trap is (your ambushers should wait there)."; } }),
  ] : [];
  const say = (text) => async () => render(await api("/api/chat", { to: s.id, text }));
  const extra = !s ? [] : s.air
    ? [el("button", { textContent: "Return to base", title: "Fly home to the airfield to refuel and rearm", onclick: say(`${s.callsign} return to base`) }),
       el("span", { className: "chip", textContent: `fuel ${s.fuel}%` })]
    : [el("button", { textContent: s.mask ? "Gas mask: off" : "Gas mask: on", title: "A mask stops gas damage but slows the unit and cuts its sight by a tile", onclick: say(`${s.callsign} ${s.mask ? "masks off" : "masks on"}`) })];
  const tags = s ? [el("span", { className: "chip", textContent: `morale ${s.morale}` }), ...(s.vet ? [el("span", { className: "chip", textContent: "★ veteran" })] : [])] : [];
  $("actions").replaceChildren(...acts.map((a) => el("button", {
    textContent: a.label, title: a.why, disabled: !a.enabled,
    onclick: async () => {
      if (a.id === "air:drop") { callMode = "airdrop:" + s.id; $("reinf-hint").textContent = "Click the tile where the troops should be put down (any land tile, even behind enemy lines)."; return; }
      render(await api("/api/work", { uid: s.id, kind: a.id }));
    },
  })), ...(s && s.cargo && s.cargo.length ? [el("span", { className: "chip", textContent: "aboard: " + s.cargo.join(", ") })] : []), ...traps, ...extra, ...tags, ...(s && s.mines !== null ? [el("span", { className: "chip", textContent: `${s.mines} mines carried` })] : []));
}

function renderMission(p) {
  const lv = p.level;
  if ($("level").options.length !== lv.all.length) $("level").replaceChildren(...lv.all.map((l) => el("option", { value: l.id, textContent: `Level ${l.id}: ${l.name}` })));
  if (document.activeElement !== $("level")) $("level").value = String(lv.id);
  $("level-brief").textContent = lv.briefing + (lv.inspired ? `  ${lv.inspired}` : "");
  $("level-goal").textContent = (p.night ? "[NIGHT: ground and sea units see 1 tile less] " : "") + `Goal: ${lv.goal}. ${lv.progress}`;
  $("level-time").textContent = lv.left === null ? "" : `time left ${Math.floor(lv.left / 60)}:${String(lv.left % 60).padStart(2, "0")}`;
  $("thinkline").textContent = p.think.left > 0 ? `Time to decide: ${p.think.left} s. The clock is waiting for you. Read the map, then choose.` : "";
  if (document.activeElement !== $("think")) $("think").value = String(p.think.secs);
  const st = p.decision_stats;
  $("dec-stats").textContent = st.total ? `${st.good} good · ${st.bad} bad` : "";
  $("decisions").replaceChildren(...(p.decisions.length ? p.decisions.map((d) => el("div", { className: `dec ${d.status}`,
    textContent: `${d.status === "success" ? "✔" : d.status === "failure" ? "✘" : "…"} ${d.callsign}: ${d.label}${d.why ? ` — ${d.why}` : " (waiting to see how it turns out)"}` }))
    : [el("div", { className: "muted", textContent: "Choices you make in reports are judged here, success or failure." })]));
}

function renderDoom(p) {
  $("sites").replaceChildren(...p.sites.map((s) => el("div", { className: "site" },
    `Silo ${s.level === 3 ? "CONFIRMED" : "suspected"} near ${s.pos}. `,
    s.level === 3 ? el("button", {
      textContent: "Fire the last resort", disabled: !!s.error, title: s.error || "",
      onclick: async () => { if (confirm("This cannot be aimed. It ruins every unit within 4 tiles of the silo, yours and theirs, and ends the war. Continue?")) render(await api("/api/last_resort", { site: s.idx })); },
    }) : "", s.error && s.level === 3 ? el("div", { className: "muted", textContent: s.error }) : "")));
  if (p.blast) $("sites").append(el("div", { className: "site", style: "color:#ff7d6e", textContent: `LAST RESORT: detonation at ${p.blast.pos} in ${p.blast.left} s` }));
  if (!p.sites.length) $("sites").replaceChildren(el("div", { className: "muted", textContent: "No clues found yet. Send units and spies around the map." }));
}

function stanceColor(s) { return s === "allied" ? "#5fb36a" : s === "friendly" ? "#8fcf8f" : s === "cool" ? "#9aa5b1" : "#d85f4a"; }

function renderWorld(p) {
  const allies = p.world.filter((n) => n.stance === "allied").map((n) => n.name);
  $("allies").textContent = allies.length ? "allies: " + allies.join(", ") : "no allies yet";
  $("neighbors").replaceChildren(...p.world.map((n) => el("details", { open: n.stance === "hostile" || n.stance === "allied" },
    el("summary", {}, el("b", { textContent: n.name }), el("span", { className: "muted", textContent: ` (${n.dir}) ` }),
      el("span", { className: "chip", style: `color:${stanceColor(n.stance)}`, textContent: `${n.stance} ${n.rel}` }), n.enemy !== null ? el("span", { className: "muted", textContent: `  they: ${n.enemy}` }) : ""),
    el("div", { className: "muted", style: "font-size:12px", textContent: n.blurb }),
    el("div", { className: "row", style: "margin-top:4px" }, ...n.actions.map((a) => el("button", { textContent: a.label, disabled: !a.enabled || side === "referee",
      title: `${a.note}${a.why ? "  —  " + a.why : ""}`, onclick: async () => render(await api("/api/world", { nid: n.id, what: a.id })) }))))));
}

function renderIndustry(p) {
  const i = p.industry;
  $("pp").textContent = `production points ${i.pp}`;
  const tips = ["More production and fuller stores, weaker markets", "Neutral", "Strong markets and friendlier partners, but fuel and food leave the country and production falls"];
  const exp = i.export_names.map((name, k) => el("button", { textContent: name, className: i.export === k ? "on" : "", title: tips[k],
    onclick: async () => render(await api("/api/industry", { what: "export", value: k })) }));
  $("industry").replaceChildren(
    el("div", { textContent: `Factories ${i.factories}/${i.max} · firepower +${i.firepower}%` + (i.enemy_factories !== null ? ` · enemy factories ${i.enemy_factories}` : "") }),
    el("div", { className: "muted", style: "font-size:12px", textContent: `Each extra factory adds production and +6% firepower to every weapon (up to +30%). Select a Builder and press 'Build a factory here' (economy cost ${i.cost}).` }),
    el("div", { className: "muted", style: "font-size:12px;margin-top:4px", textContent: "Export of goods and services" }), el("div", { className: "row" }, ...exp),
    el("div", { className: "muted", style: "font-size:12px;margin-top:4px", textContent: "Arms orders (production points)" }),
    el("div", { className: "row" }, ...i.products.map((x) => el("button", { textContent: `${x.label} (${x.cost})`, disabled: !x.enabled || side === "referee",
      onclick: async () => render(await api("/api/industry", { what: "produce", value: x.id })) }))),
    el("div", { className: "muted", style: "font-size:12px", textContent: i.orders.length ? "On order: " + i.orders.map((o) => `${o.kind} in ${o.left}s`).join(", ") : "" }));
}

function renderOccupation(p) {
  const o = p.occupation, post = async (body) => render(await api("/api/occupy", body));
  $("occ-state").textContent = o.designated ? "enemy designated" : "";
  const kids = [
    el("div", { className: "muted", textContent: "Designating the enemy as a militant group lets allies (relation 70+) join strikes, but their friends cool towards us" + (o.justified ? "." : " and, with no militants of theirs in our rear, it looks like a pretext (bigger penalty).") }),
    el("div", { className: "row", style: "margin:4px 0" }, el("button", { textContent: "Designate enemy as militant group", disabled: o.designated || side === "referee", onclick: () => post({ what: "designate" }) }),
      ...o.strikes.map((s) => el("button", { textContent: `Strike with ${s.name}`, disabled: !s.enabled || side === "referee", title: s.why, onclick: () => post({ what: "strike", nid: s.nid }) }))),
    el("div", { className: "row", style: "margin:4px 0" }, ...o.charges.map((c) => el("button", { textContent: c.label, disabled: c.done || side === "referee",
      title: c.evidence ? "We hold evidence: the world should side with us." : "We have no evidence yet: this would expose us.", onclick: () => post({ what: "accuse", charge: c.id }) })),
      el("span", { className: "muted", textContent: o.charges.map((c) => c.evidence ? "evidence for '" + c.id + "'" : "").filter(Boolean).join(", ") })),
    el("div", { className: "muted", textContent: o.areas.length ? "Captured areas (inclusive: slow, calms the area; forced: fast, but unrest, condemnation and rebels):" : "No captured areas yet. Take enemy ports, cities or facilities and clear them, then resettle." }),
    ...o.areas.map((a) => el("div", { className: "row", style: "margin-top:3px" }, el("span", { textContent: `${a.kind.replace("_", " ")} ${a.pos}` }),
      a.status ? el("span", { className: "chip", textContent: a.status }) : el("button", { textContent: "Settle (inclusive)", disabled: !a.can, title: a.why, onclick: () => post({ what: "settle", c: a.c, r: a.r, mode: "inclusive" }) }),
      a.status ? "" : el("button", { textContent: "Settle (forced)", disabled: !a.can, title: a.why, onclick: () => post({ what: "settle", c: a.c, r: a.r, mode: "forced" }) }))),
  ];
  $("occupation").replaceChildren(...kids);
}

function renderTimeline(p) {
  const tl = p.timeline;
  $("tl-box").hidden = !tl;
  if (!tl) return;
  const post = async (what) => render(await api("/api/timeline", { what }));
  $("tl-state").textContent = tl.tested ? (tl.detected ? "test done (seen)" : "test done (unseen)") : tl.stage === "prep" ? `test prep ${tl.prep}%` : "";
  $("tl-rows").replaceChildren(...tl.rows.map((r) => el("div", { className: r.state === "done" ? "" : "muted",
    textContent: r.state === "done" ? `✔ [${Math.floor(r.when / 60)}:${String(r.when % 60).padStart(2, "0")}] ${r.title}` : r.state === "scheduled" ? `○ ${r.title} in ${r.left} s` : "○ ? (unknown future event)" })));
  const kids = [];
  if (tl.stage !== "idle" && tl.stage !== "done") {
    kids.push(el("div", { className: "row" },
      el("button", { textContent: "Prepare the test", disabled: !tl.can_prepare, onclick: () => post("prepare") }),
      el("button", { textContent: "Run the cover story", disabled: !tl.can_cover, title: "A loud exercise and decoy trucks hide the work from satellites for 25 s (economy -3)", onclick: () => post("cover") })));
    kids.push(el("div", { className: "muted", textContent: tl.orbits.map((o) => o.name + (o.over ? " OVERHEAD" : " in " + o.eta + " s")).join(" · ") + (tl.deterrent ? " · deterrent: +10% firepower, enemy morale shaken" : "") }),
      el("div", { style: tl.sat_left ? "color:#ff7d6e" : "", textContent: (tl.sat_left ? `SATELLITE OVERHEAD for ${tl.sat_left} s` : "No satellite overhead") + (tl.cover_left ? ` · cover story ${tl.cover_left} s` : "") + ` · seen ${tl.seen}/10` }));
  }
  $("tl-test").replaceChildren(...kids);
}

function renderCampaign(p) {
  const c = p.campaign;
  $("camp-btn").textContent = c ? "Leave campaign" : "Start campaign";
  $("camp-btn").classList.toggle("on", !!c);
  $("camp-line").textContent = c ? `${c.act} · mission ${c.level} of ${c.total} · ${c.stars}/${c.max_stars} stars` : "";
  $("camp-results").replaceChildren(...(c ? c.results.map((r) => el("div", { textContent: `✔ ${r.level}. ${r.name}: ${"★".repeat(r.stars)}${"☆".repeat(3 - r.stars)}` })) : []));
}

function renderInfil(p) {
  $("infil-n").textContent = p.infil.length ? `${p.infil.length} spotted` : "";
  const rows = p.infil.length ? p.infil.map((x) => el("div", { style: `color:${x.kind === "militant" ? "#ff9f1c" : "#ff5c4d"}`,
    textContent: `${x.kind === "militant" ? "● militants (irregulars)" : "▲ enemy military"}: ${x.label} at ${x.pos}` }))
    : [el("div", { textContent: "No infiltrators spotted in our half. Militants (orange dashed ring) hide and raid camps; enemy military (red ring) are special forces dropped by air or sent through the lines." })];
  if (p.coup) rows.unshift(el("div", { style: "color:#ff2bd6;font-weight:700", textContent: `COUP: ${p.coup.side === "blue" ? "Ladooo" : "Candooo"}'s government was overthrown.` }));
  $("infil").replaceChildren(...rows);
}

function renderAuto(p) {
  $("auto-btn").textContent = p.autopilot ? "I take over" : "AI take over";
  $("auto-btn").classList.toggle("on", p.autopilot);
  $("auto-line").textContent = p.autopilot ? "The staff is playing: General-Staff, President, Intel-Chief, Economy-Min, Foreign-Min." : "";
}

// keep the whole home map (with the neighbouring countries round it) inside the window, whatever its size
function fitHome() {
  const stage = $("stage"), gd = maps.home;
  const meta = gd._fullLayout && gd._fullLayout.meta, W = meta ? meta.W : 20, H = meta ? meta.H : 14, M = meta ? meta.M : 1.5;
  const intelW = $("box-enemy").classList.contains("big") ? 0 : $("box-enemy").offsetWidth + 10;
  const availW = stage.clientWidth - 16 - intelW, availH = stage.clientHeight - 16 - 26;
  const s = Math.max(10, Math.min((availW - 20) / (W + 2 * M), (availH - 18) / (H + 2 * M)));
  const w = Math.floor((W + 2 * M) * s + 20), h = Math.floor((H + 2 * M) * s + 18);
  if (gd.style.width !== w + "px" || gd.style.height !== h + "px") {
    gd.style.width = w + "px"; gd.style.height = h + "px";
    if (gd._fullLayout) Plotly.Plots.resize(gd);
  }
}
window.addEventListener("resize", () => { fitHome(); if (maps.enemy._fullLayout) Plotly.Plots.resize(maps.enemy); });

function renderPanel(p) {
  for (const a of p.agents) temperaments[a.callsign] = a.temperament;
  soundEvents(p);
  const r = p.resp;
  $("resp").textContent = side === "referee" ? "" : `Your response time: ${r.avg === null ? "no answers yet" : r.avg + " s on average"} · answered ${r.answered} · too late ${r.missed}`
    + (p.pending ? ` · ${p.pending} unit${p.pending > 1 ? "s" : ""} answering…` : "");
  $("rumors").replaceChildren(...p.rumors.map((r) => el("div", { textContent: `❓ ${r.text} (${r.left}s)` })));
  $("storm").textContent = p.storm ? `STORM ${p.storm}s` : "";
  $("ai-line").textContent = p.ai.mode === "llm" ? `Candooo's General: WebLLM${p.ai.age === null ? " (no orders yet)" : `, last orders ${p.ai.age}s ago`}` : "Candooo's General: script";
  for (const s of ["real", "tac"]) $(`sym-${s}`).classList.toggle("on", sym === s);
  renderWar(p); renderHome(p); renderSupply(p); renderReinforce(p); renderActions(p); renderDoom(p); renderMission(p); renderCampaign(p); renderWorld(p); renderTimeline(p); renderOccupation(p); renderIndustry(p); renderInfil(p); renderAuto(p);
  $("ref-btn").classList.toggle("on", side === "referee");
  $("time").textContent = p.time;
  $("wind").textContent = `Wind ${p.wind.arrow} ${p.wind.text}`;
  $("pause").textContent = p.paused ? "Resume" : "Pause";
  $("speed").value = String(p.speed);
  $("nblue").textContent = p.units.blue;
  $("nred").textContent = p.units.red;
  $("oblue").textContent = `${p.objectives.blue}/${p.objective_total}`;
  $("ored").textContent = `${p.objectives.red}/${p.objective_total}`;
  $("intel-line").hidden = p.spotted === null;
  if (p.spotted !== null) { $("spotted").textContent = p.spotted; $("contacts").textContent = p.contacts; }
  $("notice").textContent = p.notice;
  renderReports(p);
  renderRadio(p);
  if (!document.activeElement || document.activeElement.id !== "chat-to") renderAgents(p);
  const log = $("log");
  const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 8;
  log.replaceChildren(...p.log.map((m) => el("div", { textContent: m })));
  if (atBottom) log.scrollTop = log.scrollHeight;
  $("banner").hidden = !p.winner;
  if (p.ending) {
    $("win-title").textContent = p.ending.title;
    $("win-stars").textContent = "★".repeat(p.ending.stars) + "☆".repeat(3 - p.ending.stars);
    $("win-why").textContent = p.ending.text;
    $("win-dec").textContent = `Level ${p.ending.level} · ${p.ending.decisions}`;
    $("win-next").hidden = !p.ending.next_level;
    $("win-next").dataset.level = p.ending.next_level || "";
  }
  $("title-home").textContent = side === "referee" ? "Full truth (referee)" : "Home map";
  $("box-enemy").hidden = side === "referee";
  $("status-all").disabled = side === "referee";
}

async function drawMap(name, fig) {
  if (!fig) return;
  const gd = maps[name];
  if (name === "home" && !gd._fullLayout) { gd.style.width = "900px"; gd.style.height = "660px"; }
  await Plotly.react(gd, fig.data, fig.layout, { displayModeBar: false, responsive: name !== "home", scrollZoom: false });
  if (name === "home") fitHome();
  Anim.onRender(name, gd, fig);                           // glide, turn and bob the unit pictures
  if (!bound.has(name)) {
    bound.add(name);
    // Clicks are turned into a tile from the mouse position itself. (Plotly's own click event only fires if the
    // pointer had already "hovered" a point a moment before, so quick clicks, touch and some browsers were missed.)
    gd.addEventListener("click", async (ev) => {
      if (side === "referee" || !gd._fullLayout || !gd._fullLayout.meta) return;
      const L = gd._fullLayout, svg = gd.querySelector(".main-svg").getBoundingClientRect();
      const px = ev.clientX - svg.left - L.xaxis._offset, py = ev.clientY - svg.top - L.yaxis._offset;
      const c = Math.floor(L.xaxis.p2l(px)), r = L.meta.H - 1 - Math.floor(L.yaxis.p2l(py));
      if (c < 0 || r < 0 || c >= L.meta.W || r >= L.meta.H) return;
      const now = performance.now();
      if (lastClick.c === c && lastClick.r === r && now - lastClick.t < 350) return;     // a doubled click event must not toggle twice
      Object.assign(lastClick, { c, r, t: now });
      if (callMode && callMode.startsWith("airdrop:")) {
        const uid = callMode.slice(8);
        callMode = null; $("reinf-hint").textContent = "";
        return render(await api("/api/work", { uid, kind: "air:drop", c, r }));
      }
      if (callMode && callMode.startsWith("lure:")) {
        const uid = callMode.slice(5);
        callMode = null; $("reinf-hint").textContent = "";
        return render(await api("/api/trap", { uid, kind: "lure", c, r }));
      }
      if (callMode) {
        const kind = callMode;
        callMode = null; $("reinf-hint").textContent = "";
        return render(await api("/api/reinforce", { kind, c, r }));
      }
      render(await api("/api/click", { c, r }));
    });
  }
}

async function render(state) {
  await Promise.all([drawMap("home", state.home), drawMap("enemy", state.enemy)]);
  renderPanel(state.panel);
}

async function refresh() {
  if (busy) { dirty = true; return; }
  busy = true;
  try { await render(await api(`/api/state?side=${side}&sym=${sym}`)); }
  catch (e) { console.error(e); }
  busy = false;
  if (dirty) { dirty = false; refresh(); }
}

// ---------- optional WebLLM voice (runs in this browser, needs WebGPU; downloads a small model once) ----------
async function enableLLM(btn = $("llm-btn"), label = "AI voice") {
  btn.disabled = true; btn.textContent = `Loading ${label}…`;
  try {
    const webllm = await import("https://esm.run/@mlc-ai/web-llm");
    llm = await webllm.CreateMLCEngine("Qwen2.5-0.5B-Instruct-q4f16_1-MLC", {
      initProgressCallback: (p) => { btn.textContent = `Loading ${label}… ${Math.round((p.progress || 0) * 100)}%`; },
    });
    btn.textContent = `${label}: on`;
    return true;
  } catch (e) {
    console.error(e);
    llm = null; btn.disabled = false; btn.textContent = `${label} failed (retry)`;
    return false;
  }
}

// each agent remembers the last few exchanges, so a conversation holds together
const memory = {};
async function askLLM(req) {
  const past = memory[req.agent] || [];
  const out = await llm.chat.completions.create({
    messages: [{ role: "system", content: req.system }, ...past, { role: "user", content: req.user }], max_tokens: 90, temperature: 0.7,
  });
  const reply = out.choices[0].message.content.trim();
  memory[req.agent] = [...past, { role: "user", content: req.user }, { role: "assistant", content: reply }].slice(-8);
  return reply;
}

// ---------- the enemy General: WebLLM plays Candooo in its own tab (?role=general) ----------
const ROLE = params.get("role") === "general" ? "general" : "human";

// find the first JSON object in a model's answer, forgiving about chatter around it and trailing commas
function parseOrders(text) {
  const m = /\{[\s\S]*\}/.exec(text);
  if (!m) return null;
  for (const s of [m[0], m[0].replace(/,\s*([}\]])/g, "$1")]) { try { return JSON.parse(s); } catch (e) { /* try the next form */ } }
  return null;
}

async function runGeneral() {
  const log = (text, cls = "") => { const d = Object.assign(document.createElement("div"), { textContent: text, className: cls }); $("gen-log").prepend(d); while ($("gen-log").children.length > 60) $("gen-log").lastChild.remove(); };
  const control = (value) => fetch("/api/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ side: "blue", action: "red_mode", value }) });
  document.body.classList.add("general");
  let playing = false, bad = 0;
  window.addEventListener("beforeunload", () => navigator.sendBeacon("/api/control", new Blob([JSON.stringify({ side: "blue", action: "red_mode", value: "heuristic" })], { type: "application/json" })));
  $("gen-load").onclick = async () => { if (await enableLLM($("gen-load"), "model")) { $("gen-toggle").disabled = false; $("gen-status").textContent = "Model ready."; } };
  $("gen-toggle").onclick = async () => {
    playing = !playing;
    $("gen-toggle").textContent = playing ? "Stop (the script takes over)" : "Start playing";
    await control(playing ? "llm" : "heuristic");
    while (playing) {
      try {
        const clock = await (await fetch("/api/clock")).json();
        if (clock.winner) { $("gen-status").textContent = "The war is over."; break; }
        if (!clock.paused) {
          $("gen-status").textContent = "Planning…";
          const brief = await (await fetch("/api/general_brief")).json();
          const t0 = performance.now();
          const out = await llm.chat.completions.create({ messages: [{ role: "system", content: brief.system }, { role: "user", content: brief.user }], max_tokens: 260, temperature: 0.3 });
          const raw = out.choices[0].message.content;
          const plan = parseOrders(raw);
          const secs = ((performance.now() - t0) / 1000).toFixed(1);
          if (!plan || !Array.isArray(plan.orders)) { bad++; log(`[${clock.time}] (${secs}s) could not read the plan:\n${raw.slice(0, 300)}`, "bad"); }
          else {
            const res = await (await fetch("/api/general_orders", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ orders: plan.orders, say: plan.say || "" }) })).json();
            log(`[${clock.time}] (${secs}s) ${res.applied} order(s) carried out` + (plan.say ? ` — "${String(plan.say).slice(0, 80)}"` : "") + (res.rejected.length ? `\nrefused: ${res.rejected.join("; ")}` : ""), res.applied ? "good" : "bad");
          }
          $("gen-status").textContent = bad ? `Playing (${bad} unreadable plan${bad > 1 ? "s" : ""}; the script fills the gaps)` : "Playing";
        }
      } catch (e) { console.error(e); log(`error: ${e.message}`, "bad"); }
      await new Promise((r) => setTimeout(r, 9000));
    }
    if (!playing) $("gen-status").textContent = "Stopped.";
  };
}

async function sendChat() {
  const text = $("chat-text").value.trim();
  if (!text || side === "referee") return;
  $("chat-text").value = "";
  const state = await api("/api/chat", { to: $("chat-to").value, text, llm: !!llm });
  render(state);
  if (state.llm && llm) {
    $("thinking").textContent = `${state.llm.callsign} is thinking… (the first answer can take up to a minute)`;
    try { render(await api("/api/chat_reply", { uid: state.llm.agent, text: await askLLM(state.llm) })); }
    catch (e) { console.error(e); }
    $("thinking").textContent = "";
  }
}

// ---------- wiring ----------
if (ROLE === "human") new EventSource("/api/events").onmessage = refresh;
for (const k of ["informant", "defector", "storm"]) {
  $(`sc-${k}`).onclick = async () => { if (side !== "referee") render(await api("/api/chat", { to: "all", text: `HQ scenario ${k}` })); };
}
$("open-general").onclick = () => window.open(`${location.pathname}?role=general`, "_blank");
for (const s of ["real", "tac"]) $(`sym-${s}`).onclick = () => { sym = s; sessionStorage.setItem("sym", s); refresh(); };
$("concede").onclick = async () => { if (side !== "referee" && confirm("Concede the war? Candooo wins.")) render(await api("/api/concede", {})); };
$("ref-btn").onclick = () => { side = side === "referee" ? "blue" : "referee"; refresh(); };
$("enemy-size").onclick = () => {
  const big = $("box-enemy").classList.toggle("big");
  $("enemy-size").textContent = big ? "shrink ⤡" : "expand ⤢";
  setTimeout(() => { Plotly.Plots.resize(maps.enemy); fitHome(); }, 50);
};
$("auto-btn").onclick = async () => render(await api("/api/chat", { to: "all", text: $("auto-btn").textContent === "AI take over" ? "AI take over" : "I take over" }));
$("pause").onclick = async () => render(await api("/api/control", { action: $("pause").textContent === "Pause" ? "pause" : "resume" }));
$("speed").onchange = async () => render(await api("/api/control", { action: "speed", value: Number($("speed").value) }));
const newGame = async (level, campaign) => { lastRadioId = null; render(await api("/api/control", { action: "reset", value: Number(level) || undefined, campaign })); };
$("camp-btn").onclick = () => newGame(1, $("camp-btn").classList.contains("on") ? "stop" : "start");
$("reset").onclick = () => newGame($("level").value);
$("win-new").onclick = () => newGame($("level").value);
$("win-next").onclick = () => newGame($("win-next").dataset.level);
$("think").onchange = async () => render(await api("/api/control", { action: "think", value: Number($("think").value) }));
$("status-all").onclick = async () => render(await api("/api/status", {}));
$("chat-send").onclick = sendChat;
$("chat-text").onkeydown = (e) => { if (e.key === "Enter") sendChat(); };
$("morse-send").onclick = async () => {
  const text = $("morse-text").value.trim();
  if (!text || side === "referee") return;
  $("morse-text").value = "";
  render(await api("/api/morse", { text, to: $("chat-to").value }));
};
$("morse-text").onkeydown = (e) => { if (e.key === "Enter") $("morse-send").click(); };
$("show-morse").onchange = refresh;
$("llm-btn").onclick = enableLLM;
$("sound").onchange = () => { if ($("sound").checked) { ac(); playSfx("chime"); } };
$("voice").onchange = () => { if ($("voice").checked) { ac(); speak("HQ-Radio", "Voice radio is on. Over."); } else if ("speechSynthesis" in window) speechSynthesis.cancel(); };
$("test-sound").onclick = () => {
  ac(); const t = audio.currentTime;
  ["squelch", "gun", "cannon", "hit", "boom", "launch", "chime", "alarm"].forEach((k, i) => setTimeout(() => playSfx(k, i % 2 ? 12 : 4), i * 900));
  playMorse("... --- ...");
};

// speak an order: needs a browser that has speech recognition (Chrome, Edge); it is not available everywhere
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!Recognition) {
  $("mic").disabled = true;
  $("mic").title = "Speech recognition is not available in this browser. Type the order instead.";
} else {
  $("mic").onclick = () => {
    const rec = new Recognition();
    rec.lang = "en-US"; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onresult = (e) => { $("chat-text").value = e.results[0][0].transcript; sendChat(); $("thinking").textContent = ""; };
    rec.onerror = (e) => { $("thinking").textContent = `Microphone: ${e.error}`; };
    rec.onend = () => { if ($("thinking").textContent === "Listening…") $("thinking").textContent = ""; };
    $("thinking").textContent = "Listening…";
    rec.start();
  };
}
document.addEventListener("keydown", async (e) => {
  if (e.key === "Escape" && side !== "referee" && document.activeElement.tagName !== "INPUT") render(await api("/api/deselect", {}));
});

if (ROLE === "general") runGeneral(); else refresh();

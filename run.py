"""Local real-time game server (Python standard library + plotly only).

Routes:
  GET  /                    the page
  GET  /glue.js             browser glue (Plotly events, live updates; WebLLM agents come later)
  GET  /plotly.min.js       Plotly.js bundled inside the plotly Python package (no CDN)
  GET  /icon/<name>.svg     icons; optional ?rot=<degrees> rotates the picture
  GET  /api/state?side=     {figure, panel} for that side's tab
  GET  /api/events          Server-Sent Events: pushes {"v": version} whenever the game changes
  POST /api/click           {side, c, r}   select / move / attack
  POST /api/deselect        {side}
  POST /api/control         {action: pause|resume|speed|reset, value}
"""
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from plotly.offline import get_plotlyjs

from game import agents, campaign, homefront, industry, occupation, timeline, world
from game.state import Game, fmt_time
from ui.figure import build

ROOT = Path(__file__).resolve().parent
ICONS = ROOT / "assets" / "icons"
NAME_RE = re.compile(r"^[a-z0-9_]+$")
SIDES = ("blue", "red")

STATE = {"game": Game()}
COND = threading.Condition(threading.RLock())   # guards the game; notified on every change


def game():
    return STATE["game"]


def clock():
    """One game second per (1 / speed) real seconds; nothing runs while paused or after a win."""
    while True:
        with COND:
            g = game()
            delay = 1.0 / g.speed
        time.sleep(delay)
        with COND:
            g = game()
            if g.thinking_left() > 0:                # an urgent report is open: wait (a limited time) for the General to decide
                g.bump()
                COND.notify_all()
            elif not g.paused and not g.winner:
                g.tick()
                COND.notify_all()


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype, status=200, cache="no-cache"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(json.dumps(obj), "application/json", status)

    def _state(self, side, sym="real"):
        """Both maps for one side's tab. The referee gets a single full-truth map."""
        with COND:
            g = game()
            sym = "tac" if sym == "tac" else "real"
            return {"home": build(g, side, "home", sym), "enemy": build(g, side, "enemy", sym) if side in SIDES else None,
                    "panel": g.panel(side)}

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        last = -1
        try:
            while True:
                with COND:
                    COND.wait_for(lambda: game().version != last, timeout=15)
                    v = game().version
                if v != last:
                    self.wfile.write(f"data: {json.dumps({'v': v})}\n\n".encode())
                    last = v
                else:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_GET(self):
        url = urlparse(self.path)
        p, q = url.path, parse_qs(url.query)
        if p == "/":
            self._send((ROOT / "ui" / "index.html").read_text(encoding="utf-8"), "text/html; charset=utf-8")
        elif p == "/glue.js":
            self._send((ROOT / "ui" / "glue.js").read_text(encoding="utf-8"), "application/javascript")
        elif p == "/anim.js":
            self._send((ROOT / "ui" / "anim.js").read_text(encoding="utf-8"), "application/javascript")
        elif p == "/plotly.min.js":
            self._send(get_plotlyjs(), "application/javascript", cache="max-age=3600")
        elif p == "/api/state":
            side = q.get("side", ["blue"])[0]
            self._json(self._state(side if side in SIDES + ("referee",) else "blue", q.get("sym", ["real"])[0]))
        elif p == "/api/clock":
            with COND:
                g = game()
                self._json(dict(time=fmt_time(g.t), paused=g.paused, winner=g.winner))
        elif p == "/api/general_brief":
            with COND:
                self._json(game().general_brief("red"))
        elif p == "/api/events":
            self._events()
        elif p.startswith("/icon/") and p.endswith(".svg"):
            name = p[len("/icon/"):-len(".svg")]
            f = ICONS / f"{name}.svg"
            if not NAME_RE.match(name) or not f.is_file():
                return self._send("not found", "text/plain", 404)
            svg = f.read_text(encoding="utf-8")
            try:
                rot = float(q.get("rot", ["0"])[0])
            except ValueError:
                rot = 0
            if rot:
                head, rest = svg.split(">", 1)
                svg = f'{head}><g transform="rotate({rot:g} 64 64)">{rest.rsplit("</svg>", 1)[0]}</g></svg>\n'
            self._send(svg, "image/svg+xml", cache="max-age=3600")
        else:
            self._send("not found", "text/plain", 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)
        side = data.get("side", "blue")
        if self.path == "/api/general_orders":              # the AI General (a WebLLM tab) plays Candooo
            with COND:
                g = game()
                result = g.apply_general_orders("red", data.get("orders"), str(data.get("say", "")))
                COND.notify_all()
            return self._json(result)
        if side not in SIDES and not (side == "referee" and self.path == "/api/control"):
            return self._json({"error": "side must be blue or red (the referee can only use the clock controls)"}, 400)
        with COND:
            g = game()
            if self.path == "/api/click":
                try:
                    g.click(side, int(data["c"]), int(data["r"]))
                except (KeyError, TypeError, ValueError):
                    return self._json({"error": "need integer c and r"}, 400)
            elif self.path == "/api/deselect":
                g.deselect(side)
            elif self.path == "/api/select":
                g.select(side, str(data.get("uid", "")))
            elif self.path == "/api/status":
                g.ask_status(side, data.get("uid") or None)
            elif self.path == "/api/choose":
                try:
                    g.choose(side, int(data["report"]), str(data["option"]))
                except (KeyError, TypeError, ValueError):
                    return self._json({"error": "need report and option"}, 400)
            elif self.path == "/api/chat":
                llm = g.chat(side, str(data.get("to", "all")), str(data.get("text", "")), bool(data.get("llm")))
                COND.notify_all()
                return self._json(dict(self._state(side, data.get("sym", "real")), llm=llm))
            elif self.path == "/api/chat_reply":
                g.chat_reply(side, str(data.get("uid", "")), str(data.get("text", "")))
            elif self.path == "/api/home":
                msg = homefront.action(g, side, str(data.get("name", "")))
                agents.radio(g, side, "in", "HQ-Radio", msg)
                g.bump()
            elif self.path == "/api/world":
                msg = world.act(g, side, str(data.get("nid", "")), str(data.get("what", "")))
                g.notice[side] = ""
                agents.radio(g, side, "in", "FOREIGN-MIN", msg)
                g.bump()
            elif self.path == "/api/occupy":
                what = str(data.get("what", ""))
                if what == "designate":
                    msg = occupation.designate(g, side)
                elif what == "accuse":
                    msg = occupation.accuse(g, side, str(data.get("charge", "")))
                elif what == "strike":
                    msg = occupation.ally_strike(g, side, str(data.get("nid", "")))
                else:
                    try:
                        msg = occupation.resettle(g, side, (int(data["c"]), int(data["r"])), str(data.get("mode", "")))
                    except (KeyError, TypeError, ValueError):
                        return self._json({"error": "c and r must be integers"}, 400)
                agents.radio(g, side, "in", "FOREIGN-MIN", msg)
                g.bump()
            elif self.path == "/api/timeline":
                msg = timeline.action(g, side, str(data.get("what", "")))
                agents.radio(g, side, "in", "HQ-Radio", msg)
                g.bump()
            elif self.path == "/api/industry":
                what = str(data.get("what", ""))
                if what == "export":
                    msg = industry.set_export(g, side, int(data.get("value", 1)))
                else:
                    msg = industry.produce(g, side, str(data.get("value", "")))
                agents.radio(g, side, "in", "ECONOMY-MIN", msg)
                g.bump()
            elif self.path == "/api/trap":
                try:
                    c, r = (int(data["c"]), int(data["r"])) if data.get("c") is not None else (None, None)
                except (TypeError, ValueError):
                    return self._json({"error": "c and r must be integers"}, 400)
                g.trap(side, str(data.get("uid", "")), str(data.get("kind", "")), c, r)
            elif self.path == "/api/work":
                at = None
                if data.get("c") is not None and data.get("r") is not None:
                    try:
                        at = (int(data["c"]), int(data["r"]))
                    except (TypeError, ValueError):
                        return self._json({"error": "c and r must be integers"}, 400)
                g.work(side, str(data.get("uid", "")), str(data.get("kind", "")), at)
            elif self.path == "/api/reinforce":
                try:
                    c, r = (int(data["c"]), int(data["r"])) if data.get("c") is not None else (None, None)
                except (TypeError, ValueError):
                    return self._json({"error": "c and r must be integers"}, 400)
                msg = g.reinforce(side, str(data.get("kind", "")), c, r)
                if not msg.startswith(("Paratroopers", "Naval", "Armoured")):
                    g.notice[side] = msg
                else:
                    g.notice[side] = ""
            elif self.path == "/api/concede":
                g.concede(side)
            elif self.path == "/api/last_resort":
                try:
                    g.last_resort(side, int(data.get("site", -1)))
                except (TypeError, ValueError):
                    return self._json({"error": "site must be an integer"}, 400)
            elif self.path == "/api/morse":
                g.send_morse(side, str(data.get("text", "")), str(data.get("to", "all")))
            elif self.path == "/api/control":
                if data.get("action") == "reset":
                    keep = g.speed
                    try:
                        level = int(data.get("value") or g.level_id)
                    except (TypeError, ValueError):
                        level = g.level_id
                    camp = g.campaign
                    if data.get("campaign") == "start":
                        camp, level = campaign.new(), 1
                    elif data.get("campaign") == "stop":
                        camp = None
                    STATE["game"] = Game(level=level)
                    if camp:
                        campaign.start_next(camp, g if data.get("campaign") != "start" else None, STATE["game"])
                    STATE["game"].speed = keep
                    STATE["game"].pause_on_report, STATE["game"].think_secs = g.pause_on_report, g.think_secs
                    STATE["game"].version = g.version + 1
                else:
                    g.control(data.get("action"), data.get("value"))
            else:
                return self._send("not found", "text/plain", 404)
            COND.notify_all()
        self._json(self._state(side, data.get("sym", "real")))

    def log_message(self, fmt, *args):
        pass  # quiet


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    threading.Thread(target=clock, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    print(f"Fleet & Armor running at http://localhost:{port}  (Ctrl+C to stop)", flush=True)
    server.serve_forever()

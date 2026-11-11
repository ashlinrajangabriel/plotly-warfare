"""Real-time game state. Python is the single source of truth.

The server calls `tick()` once per game second. The human General gives orders (click, chat, Morse,
choices in reports); units then act on their own: walk, fire, work, capture.

Fog of war: each side only knows what its units (and held ports/cities) can see (`vis`), what it has
ever seen (`explored`), the enemies it spotted now (`detected`) and aging contacts (`intel`).
"""
import math
import os
import random

import time as _time

from . import agents, ai_red, airlift, campaign, events, homefront, industry, levels, occupation, personas, raid, rules, timeline, tactics, world
from .board import NAMES, Board, ref
from .scenarios import MINES, build_units
from .units import (ABILITIES, ATTACK, JOBS, MINE_DETECT, MISSILE_TYPES, SENSORS, STATS, STEALTH, TEAM_LABEL, TEAM_SHORT,
                    VISION, Unit)

CAPTURE_SECS = 8        # infantry must hold an objective this long
MISSILE_FLIGHT = 6      # seconds between launch and impact
MISSILE_RADIUS = 1      # blast radius in tiles (Manhattan)
INTEL_TTL = 90          # seconds a contact stays on the enemy map after it was last seen
COVERED = {"forest", "tunnel", "trench", "ruins", "mountain"}   # units here are only spotted from 2 tiles
MINE_DAMAGE = 6
SPY_RANGE, SPY_EVERY = 5, 6
DIGGABLE = {"plains", "forest", "hills", "coast"}
OTHER = {"blue": "red", "red": "blue"}
SIDES = ("blue", "red")

# Supply: fuel and food arrive by convoy through the southern strait (cols K-L). Each side has its own lane.
CONVOY_FIRST, CONVOY_EVERY, CARGO = 15, 70, 25
LANES = {"blue": ((10, 13), (6, 11)), "red": ((11, 13), (15, 9))}      # (entrance, unloading tile)
VEHICLES = {"tank", "artillery", "missile_launcher", "minesweeper", "minelayer", "destroyer", "cruiser", "battleship", "submarine",
            "anti_air", "supply_truck"}
PERSONNEL = {"infantry", "digger", "builder", "miner", "spy", "diver", "medic"}

# Reinforcements: limited calls per match, each arrives after a delay
REINFORCE = {
    "air": dict(label="Paratroopers", eta=20, uses=1, needs_tile="land"),
    "sea": dict(label="Naval squadron", eta=30, uses=1, needs_tile="water"),
    "land": dict(label="Armoured convoy", eta=40, uses=2, needs_tile=None),
}

# The last resort: hidden, cannot be aimed, ruins friend and foe alike around its silo
NUKE_SITES, NUKE_RADIUS, NUKE_COUNTDOWN, LOST_BELOW = 2, 4, 15, 25
NUKE_TERRAIN = {"plains", "hills", "forest", "mountain"}


def fmt_time(t):
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class Game:
    def __init__(self, seed=None, level=3):
        self.rng = random.Random(seed)
        self.board = Board()
        self.units = build_units()
        self.t = 0
        self.version = 0
        self.paused = False
        self.speed = 0.5                  # half speed: the General needs time to read the map and think
        self.pause_on_report = True       # the clock waits (for a limited real time) while an urgent report is open
        self.think_secs = 15
        self.think_until = 0.0
        self.level_id = level if level in levels.LEVELS else 3
        self.time_limit = 10 ** 9
        self.passive_until = 8
        self.delivered = {"blue": 0, "red": 0}
        self.delivered_ids = set()
        self.clouds = []                  # chemical clouds {c, r, radius, until, next_drift}
        self.floods = []                  # flood plains about to flood, or flooded
        self.barricade_under = {}         # what a barricade tile was before (restored when breached)
        self.decisions = []               # the General's choices and how they turned out
        self.winner = None
        self.ending = None
        self.win_reason = ""
        self.sel = {"blue": None, "red": None}
        self.notice = {"blue": "", "red": ""}
        self.log = []
        self.impacts = []     # missiles in flight
        self.effects = []     # short-lived explosion markers
        self.human = "blue"   # the human General; the other side is the AI General
        self.seq = 0          # id counter for radio messages and reports
        self.radio = []       # everything said on the radio (see agents.radio)
        self.reports = []     # reports waiting for the General's decision
        self.kia = []         # (callsign, label, place) of the General's units that were just destroyed
        self.prev_detected = set()
        self.contact_seen = {}
        self.latency = os.environ.get("NO_LATENCY") != "1"   # agents answer after a realistic delay (tests switch it off)
        self.radio_queue = [] # replies on their way: (due time, who, text, kind)
        self.sfx = []         # sound events for the browser: {id, kind, c, r}
        self.sfx_seq = 0
        self.resp = dict(answered=0, missed=0, total=0.0)   # how fast the General answers reports
        self.returning = []   # extracted units on their way back: {due, team, type, hp}
        self.code_red_sent = False
        self.wind = (round(self.rng.uniform(-1, 1), 2), round(self.rng.uniform(-1, 1), 2))   # blows towards (+x east, +y south)
        self.wind_base = self.wind
        # live scenarios and the AI General
        self.rumors = []
        self.storm_until = 0
        self.last_ondemand = 0
        self.next_event_at = 10 ** 9 if os.environ.get("NO_EVENTS") == "1" else self.rng.randint(*events.EVENT_RANGE)
        self.red_mode = "heuristic"     # "llm" when a WebLLM General is playing Candooo
        self.general_at = None          # game time of the last orders from the WebLLM General
        self.brief_targets = {"blue": {}, "red": {}}
        mid = self.board.width // 2
        self.objectives = {}  # (c, r) -> {kind, owner, capturer, progress}
        for r in range(self.board.height):
            for c in range(self.board.width):
                kind = self.board.terrain(c, r)
                if kind in ("port", "city"):
                    self.objectives[(c, r)] = dict(kind=kind, owner="blue" if c < mid else "red", capturer=None, progress=0)
        # barracks and training camps: capturable facilities (not win objectives)
        self.facilities = {}  # (c, r) -> {kind, owner, capturer, progress, made_at}
        for r in range(self.board.height):
            for c in range(self.board.width):
                kind = self.board.terrain(c, r)
                if kind in ("barracks", "training_camp", "factory"):
                    self.facilities[(c, r)] = dict(kind=kind, owner="blue" if c < mid else "red", capturer=None, progress=0, made_at=0)
        # engineers, mines, bridges
        self.mines = {(c, r): owner for c, r, owner in MINES}
        self.mines_known = {s: set() for s in SIDES}
        self.new_mines = {s: [] for s in SIDES}
        self.ruined_bridges = set()
        # supply and convoys
        self.supply = {s: dict(fuel=100.0, food=100.0, warned=set(), zero_for=0, notified=-99) for s in SIDES}
        self.convoy_due = {s: False for s in SIDES}
        # reinforcements
        self.reinf_left = {s: {k: v["uses"] for k, v in REINFORCE.items()} for s in SIDES}
        self.arrivals = []
        # hidden last-resort sites, found by clues
        self.nukes = []
        self.nuke_level = {s: {} for s in SIDES}
        self.nuke_fuzzy = {}
        self.blast = None
        self.bridge_event = None
        self.last_enemy_fire = -99        # last time the enemy shot at us (for levels where firing first costs you)
        self.first_shot_news = -99
        self.next_n = {}
        levels.setup(self)                # thin out armies, set supplies and barricades for this level
        homefront.setup(self, levels.LEVELS[self.level_id])      # government, economy and corruption for both sides
        self.campaign = None              # campaign state (set by the server for campaign play)
        self.coup = None                  # {side, t} once a government has been overthrown
        self.autopilot = False           # "AI take over": the staff plays for the human General
        world.setup(self)                 # neighbouring countries
        occupation.setup(self)            # designation of militant groups, resettlement
        raid.setup(self, levels.LEVELS[self.level_id])
        timeline.setup(self, levels.LEVELS[self.level_id])
        industry.setup(self)              # factories, production, exports
        self._place_nukes()
        if self.known_silos:                                  # both sides know where the last resort lies
            for s in SIDES:
                for i, site in enumerate(self.nukes):
                    self.nuke_level[s][i] = 3
        # id counters for units created later (reinforcements, convoys)
        self.next_n = {}
        for u in self.units:
            key = (u.team, u.type)
            self.next_n[key] = max(self.next_n.get(key, 0), int(u.id.rsplit("-", 1)[-1]))
        # each side's supply lane through the strait (public geography)
        self.lanes = {}
        for s, (entrance, goal) in LANES.items():
            probe = Unit(id=f"{s[0]}-probe-0", type="supply_ship", team=s, c=entrance[0], r=entrance[1], hp=1)
            p = rules.find_path(self.board, [], probe, goal)
            self.lanes[s] = [entrance] + [(c, r) for c, r, _ in p] if p else [entrance, goal]
        # fog of war: every side knows its own half of the map and who holds the objectives there
        own_half = {"blue": lambda c: c < mid, "red": lambda c: c >= mid}
        self.vis = {s: set() for s in SIDES}
        self.detected = {s: set() for s in SIDES}
        self.intel = {s: {} for s in SIDES}
        self.explored = {s: {(c, r) for c in range(self.board.width) for r in range(self.board.height) if own_half[s](c)} for s in SIDES}
        self.obj_known = {s: {p: o["owner"] for p, o in self.objectives.items() if own_half[s](p[0])} for s in SIDES}
        self._observe()
        self.say(f"Level {self.level_id}: {levels.LEVELS[self.level_id]['name']}. {levels.LEVELS[self.level_id]['goal']}. "
                 f"Time limit {fmt_time(self.time_limit)}. Keep the strait open for supplies.")

    # ---------- setup helpers ----------
    def _place_nukes(self):
        blocked = [(u.c, u.r) for u in self.units] + list(self.objectives)
        pick = []
        for gap, apart in ((4, 8), (3, 6), (2, 5), (2, 3)):          # relax the spacing if the map is crowded
            cands = [(c, r) for c in range(self.board.width) for r in range(self.board.height)
                     if self.board.terrain(c, r) in NUKE_TERRAIN and all(manhattan((c, r), b) >= gap for b in blocked)]
            self.rng.shuffle(cands)
            pick = []
            for p in cands:
                if all(manhattan(p, q) >= apart for q in pick):
                    pick.append(p)
                if len(pick) == NUKE_SITES:
                    break
            if len(pick) == NUKE_SITES:
                break
        self.nukes = [dict(c=p[0], r=p[1]) for p in pick]
        for s in SIDES:
            self.nuke_level[s] = {i: 0 for i in range(len(self.nukes))}

    def new_unit(self, team, typ, c, r):
        n = self.next_n.get((team, typ), 0) + 1
        self.next_n[(team, typ)] = n
        u = Unit(id=f"{team[0]}-{typ}-{n}", type=typ, team=team, c=c, r=r, hp=STATS[typ]["hp"])
        self.units.append(u)
        return u

    def free_near(self, c, r, typ):
        """Nearest free tile (within 5) where a unit of this type can stand."""
        taken = {(u.c, u.r) for u in self.units}
        spots = sorted(((abs(dc) + abs(dr), c + dc, r + dr) for dc in range(-5, 6) for dr in range(-5, 6)
                        if self.board.inside(c + dc, r + dr)), key=lambda x: x[0])
        for _, cc, rr in spots:
            if (cc, rr) not in taken and rules.step_cost(typ, self.board.terrain(cc, rr)) is not None and (cc, rr) not in self.mines:
                return cc, rr
        return None

    # ---------- helpers ----------
    def bump(self):
        self.version += 1

    def add_sfx(self, kind, c=None, r=None, c2=None, r2=None, dur=0):
        """Tell the browser to make a sound and draw the matching animation (it plays each id once).
        (c, r) is where it happens, (c2, r2) where a shell or missile is going, dur its flight time in game seconds."""
        self.sfx_seq += 1
        self.sfx.append(dict(id=self.sfx_seq, kind=kind, c=c, r=r, c2=c2, r2=r2, dur=dur))
        del self.sfx[:-60]

    def sfx_for(self, side):
        """Sound and animation events this side may see or hear. Things in the fog are not drawn; big bangs are heard as rumbles."""
        if side not in SIDES:
            return self.sfx[-30:]
        vis, out = self.vis[side], []
        for e in self.sfx[-40:]:
            pts = [(e["c"], e["r"])] + ([(e["c2"], e["r2"])] if e["c2"] is not None else [])
            if e["c"] is None or e["kind"] == "nuke" or any(p in vis for p in pts):
                out.append(e)
            elif e["kind"] in ("boom", "launch", "cannon"):
                out.append(dict(e, kind="rumble", c=None, r=None, c2=None, r2=None))
        return out[-30:]

    def wind_info(self):
        wx, wy = self.wind
        knots = round(math.hypot(wx, wy) * 8)
        toward = (math.degrees(math.atan2(wy, wx)) + 90) % 360           # compass bearing the wind blows towards
        names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
        return dict(knots=knots, text=f"{knots} kn from {names[int(round(((toward + 180) % 360) / 45)) % 8]}" if knots else "calm",
                    arrow=arrows[int(round(toward / 45)) % 8] if knots else "·", x=wx, y=wy)

    def reply_delay(self, u):
        """Seconds before an agent answers the General: eager units answer fast, cautious ones think, shortages add lag."""
        base = {"eager": 1, "calm": 2, "cautious": 3}[u.temperament]
        return base + self.rng.randint(0, 2) + (self.late(u.team) // 4)

    def queue_radio(self, delay, who, text, kind="voice"):
        if not self.latency or delay <= 0:
            agents.radio(self, self.human, "in", who, text, kind)
        else:
            self.radio_queue.append((self.t + delay, who, text, kind))

    def eta(self, u, path):
        """Seconds a unit needs to walk this route."""
        return int(round(sum(cost for _, _, cost in path) * rules.secs_per_cost(u) * self.slow(u)))

    def say(self, text):
        self.log.append((self.t, text))
        del self.log[:-80]

    def unit_at(self, c, r):
        return next((u for u in self.units if u.c == c and u.r == r and u.hp > 0), None)

    def unit_by_id(self, uid):
        return next((u for u in self.units if u.id == uid and u.hp > 0), None)

    def selected(self, side):
        return self.unit_by_id(self.sel[side]) if self.sel.get(side) else None

    def avoid_for(self, team):
        """Tiles a team's units walk round: mines they laid or have found."""
        return {p for p, o in self.mines.items() if o == team} | self.mines_known[team]

    def path_for(self, u, goal, allow_goal_occupied=False):
        return rules.find_path(self.board, self.units, u, goal, allow_goal_occupied, avoid=self.avoid_for(u.team))

    def status(self, u):
        t = self.unit_by_id(u.target_id) if u.target_id else None
        if u.job:
            return f"{JOBS[u.job['kind']][0]} ({max(0, int(u.job['done_at'] - self.t))} s left)"
        if t:
            return f"Attacking {t.label}"
        if u.path:
            return f"Moving to {ref(*u.dest)}" if u.dest else "Closing in"
        if u.plan:
            return "Heading out to work"
        return "Holding"

    def late(self, side):
        """Seconds orders take to reach units: grows as fuel or food run low."""
        s = self.supply[side]
        low = min(s["fuel"], s["food"])
        return 0 if low >= 30 else 4 if low >= 10 else 10 if low > 0 else 15

    def slow(self, u):
        """Step-time multiplier from shortages (fuel for vehicles, food for people)."""
        s = self.supply[u.team]
        stock = s["fuel"] if u.type in VEHICLES else s["food"] if u.type in PERSONNEL else 100
        base = 1.0 if stock >= 30 else 1.5 if stock > 0 else 2.5
        base *= 1.5 if self.storm_until and u.stats["domain"] == "sea" else 1.0              # gales slow ships
        base *= 1.6 if self.winter and u.stats["domain"] == "land" else 1.0                  # mud and frost slow everything on the ground
        return base * (1.5 if u.mask else 1.0)                                               # a gas mask slows you down

    def delay_orders(self, side, u, weapon=False):
        d = self.late(side)
        if d:
            u.next_step_at = max(u.next_step_at, self.t + d)
            if weapon:
                u.ready_at = max(u.ready_at, self.t + d)
            if side == self.human and self.t - self.supply[side]["notified"] >= 20:
                self.supply[side]["notified"] = self.t
                agents.radio(self, side, "in", "HQ-Radio", f"Supplies are short. Orders are reaching units {d} s late.")

    # ---------- fog of war ----------
    def is_night(self):
        lv = levels.LEVELS[self.level_id]
        return bool(lv["night"] or (lv["daynight"] and (self.t // 120) % 2 == 1))

    def _observe(self):
        """Recompute what each side sees, which enemies it has spotted, its aging contacts and any mines it feels out."""
        b = self.board
        night = self.is_night()
        for side in SIDES:
            # observers: (column, row, sight radius, is a sensor, is airborne). High ground sees further; the view is blocked by
            # hills, mountains, trees and buildings in the way, except for aircraft, which look down from above.
            obs = []
            for u in self.units:
                if u.team == side and u.hp > 0:
                    rad = VISION[u.type] - (1 if u.mask else 0) + (0 if u.air else rules.sight_bonus(b, u.c, u.r))
                    if night and u.type not in SENSORS:
                        rad = max(1, rad - 1)                      # darkness: ground and sea units see a tile less
                    obs.append((u.c, u.r, rad, u.type in SENSORS, u.air))
            obs += [(c, r, 2, False, False) for (c, r), o in self.objectives.items() if o["owner"] == side]
            vis = set()
            for c, r, rad, _s, flying in obs:
                for dc in range(-rad, rad + 1):
                    span = rad - abs(dc)
                    for dr in range(-span, span + 1):
                        if b.inside(c + dc, r + dr) and (flying or rules.has_los(b, (c, r), (c + dc, r + dr))):
                            vis.add((c + dc, r + dr))
            det = set()
            for e in self.units:
                if e.team == side or e.hp <= 0:
                    continue
                hidden = e.type in STEALTH or e.ambush
                cap = 1 if hidden else 2 if b.terrain(e.c, e.r) in COVERED else 99
                if any(abs(c - e.c) + abs(r - e.r) <= min(rad, 3 if (hidden and sensor) else cap)
                       and (flying or e.air or rules.has_los(b, (c, r), (e.c, e.r))) for c, r, rad, sensor, flying in obs):
                    det.add(e.id)
            self.vis[side], self.detected[side] = vis, det
            self.explored[side] |= vis
            intel = self.intel[side]
            for e in self.units:
                if e.id in det:
                    intel[e.id] = dict(type=e.type, team=e.team, c=e.c, r=e.r, seen=self.t)
            for uid, rec in list(intel.items()):
                if uid not in det and (self.t - rec["seen"] > INTEL_TTL or (rec["c"], rec["r"]) in vis):
                    del intel[uid]      # too old, or we can see the spot and nobody is there
            for pos in vis & self.objectives.keys():
                self.obj_known[side][pos] = self.objectives[pos]["owner"]
            # hidden enemy mines are felt out by engineers
            for u in self.units:
                rad = MINE_DETECT.get(u.type, 0)
                if u.team == side and u.hp > 0 and rad:
                    for pos, owner in self.mines.items():
                        if owner != side and pos not in self.mines_known[side] and manhattan((u.c, u.r), pos) <= rad:
                            self.mines_known[side].add(pos)
                            self.new_mines[side].append((u.id, pos))

    def contacts(self, side):
        """Enemy units we remember but cannot see right now."""
        return [dict(rec, id=uid, age=self.t - rec["seen"]) for uid, rec in self.intel[side].items() if uid not in self.detected[side]]

    # ---------- orders (from the humans) ----------
    def click(self, side, c, r):
        if self.winner or side not in self.sel or not self.board.inside(c, r):
            return
        self._observe()
        self.notice[side] = ""
        u, sel = self.unit_at(c, r), self.selected(side)
        if u and u.team != side and u.id not in self.detected[side]:
            u = None                                   # we cannot see it, so we cannot target it
        if u and u.team == side:
            self.sel[side] = None if (sel and sel.id == u.id) else u.id
        elif u and sel:
            self.order_attack(side, sel, u)
        elif sel and not u:
            self.order_move(side, sel, c, r)
        self.bump()

    def deselect(self, side):
        if side in self.sel:
            self.sel[side] = None
            self.notice[side] = ""
            self.bump()

    def order_move(self, side, u, c, r):
        if u.stats["move"] == 0:
            self.notice[side] = f"{u.label} cannot move."
            return
        path = self.path_for(u, (c, r))
        if not path:
            self.notice[side] = f"No route to {ref(c, r)} for {u.label}."
            return
        u.path, u.dest, u.target_id, u.job, u.plan = path, (c, r), None, None, None
        u.arrive_note = side == self.human
        self.delay_orders(side, u)

    def order_attack(self, side, u, tgt):
        if ATTACK[u.type][0] <= 0 or not rules.can_hit(u, tgt):
            self.notice[side] = f"{u.label} cannot attack {tgt.label}."
        elif u.ammo <= 0:
            self.notice[side] = f"{u.label} is out of ammo."
        elif u.type in MISSILE_TYPES and not rules.in_range(u, tgt):
            self.notice[side] = f"{tgt.label} is out of missile range."
        else:
            u.target_id, u.path, u.dest, u.hold_fire, u.job, u.plan = tgt.id, [], None, False, None, None
            u.mission = u.air                              # an air strike ends with the flight home
            self.delay_orders(side, u, weapon=True)

    def select(self, side, uid):
        u = self.unit_by_id(uid)
        if side in self.sel and u and u.team == side:
            self.sel[side] = u.id
            self.bump()

    # ---------- the General and the agents ----------
    def ask_status(self, side, uid=None):
        for u in agents.own_units(self, side):
            if uid is None or u.id == uid:
                agents.say(self, u, agents.sitrep(self, u))
        self.bump()

    def choose(self, side, report_id, option_id):
        agents.choose(self, side, report_id, option_id)
        self.bump()

    def chat(self, side, to, text, llm=False):
        out = agents.chat(self, side, to, text, llm)
        self.bump()
        return out

    def chat_reply(self, side, uid, text):
        agents.chat_reply(self, side, uid, text)
        self.bump()

    def send_morse(self, side, raw, to="all"):
        agents.send_morse(self, side, raw, to)
        self.bump()

    # ---------- engineers: jobs ----------
    def _neighbour_stand(self, u, target):
        """A free tile next to `target` where this unit can stand."""
        for dc, dr in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            p = (target[0] + dc, target[1] + dr)
            if self.board.inside(*p) and rules.step_cost(u.type, self.board.terrain(*p)) is not None and p not in self.avoid_for(u.team):
                occ = self.unit_at(*p)
                if not occ or occ.id == u.id:
                    return p
        return None

    def job_target(self, side, u, kind, at=None):
        """(error, target tile, tile to stand on) for a job, without starting it."""
        if kind not in ABILITIES.get(u.type, []):
            return "That is not my job, sir.", None, None
        if kind == "clear":
            mines = [p for p in self.mines_known[side] | {p for p, o in self.mines.items() if o == side}]
            if not mines:
                return "No mines known to me, sir.", None, None
            tgt = min(mines, key=lambda p: manhattan((u.c, u.r), p))
            stand = (u.c, u.r) if manhattan((u.c, u.r), tgt) <= 1 else self._neighbour_stand(u, tgt)
            return (None, tgt, stand) if stand else ("I cannot get next to that mine, sir.", None, None)
        if kind == "bridge":
            if not self.ruined_bridges:
                return "There is no ruined bridge, sir.", None, None
            tgt = min(self.ruined_bridges, key=lambda p: manhattan((u.c, u.r), p))
            stand = (u.c, u.r) if manhattan((u.c, u.r), tgt) <= 1 and self.board.terrain(u.c, u.r) != "river" else self._neighbour_stand(u, tgt)
            return (None, tgt, stand) if stand else ("I cannot get next to the bridge, sir.", None, None)
        tgt = at or (u.c, u.r)
        terrain = self.board.terrain(*tgt)
        if kind == "dig" and terrain not in DIGGABLE:
            return "The ground here cannot be dug, sir.", None, None
        if kind == "camp" and terrain not in DIGGABLE:
            return "No room for a camp here, sir.", None, None
        if kind == "barricade" and (terrain not in DIGGABLE | {"road", "bridge"} or tgt in self.objectives):
            return "A barricade cannot go here, sir.", None, None
        if kind == "factory":
            if terrain not in DIGGABLE or tgt in self.objectives or tgt in self.facilities:
                return "No room for a factory here, sir.", None, None
            if industry.factories(self, side) >= industry.MAX_FACTORIES:
                return "We already have the most factories we can run.", None, None
            if homefront.active(self) and self.home[side]["economy"] < industry.FACTORY_COST:
                return "The economy cannot pay for a factory now.", None, None
        if kind == "breach":
            walls =[(c, r) for r in range(self.board.height) for c in range(self.board.width) if self.board.terrain(c, r) == "barricade"
                     and manhattan((c, r), (u.c, u.r)) <= 10]
            if not walls:
                return "No barricade within reach, sir.", None, None
            tgt = min(walls, key=lambda p: manhattan((u.c, u.r), p))
            stand = (u.c, u.r) if manhattan((u.c, u.r), tgt) <= 1 else self._neighbour_stand(u, tgt)
            return (None, tgt, stand) if stand else ("I cannot get next to the barricade, sir.", None, None)
        if kind == "plant":
            if u.stock <= 0:
                return "Out of mines, sir.", None, None
            water = u.stats["domain"] == "sea"
            if tgt in self.mines:
                return "There is already a mine here.", None, None
            if (terrain in rules.SHIP) != water or terrain in ("port", "city") or tgt in self.objectives:
                return "I cannot lay a mine here, sir.", None, None
        return None, tgt, tgt

    def work(self, side, uid, kind, at=None):
        """The General orders an engineer to do a job (walking there first if needed)."""
        u = self.unit_by_id(uid)
        if not u or u.team != side or self.winner:
            return
        if kind.startswith("air:"):
            msg = airlift.command(self, side, u, kind[4:], *(at or (None, None)))
            agents.say(self, u, msg)
            self.bump()
            return
        err, tgt, stand = self.job_target(side, u, kind, at)
        if err:
            self.notice[side] = err
            agents.say(self, u, err)
            self.bump()
            return
        self.notice[side] = ""
        if (u.c, u.r) == stand:
            self._start_job(u, kind, tgt)
        else:
            path = self.path_for(u, stand)
            if not path:
                agents.say(self, u, f"No route to {ref(*stand)}, sir.")
            else:
                u.path, u.dest, u.target_id, u.job, u.plan = path, stand, None, None, (kind, *tgt)
                agents.say(self, u, f"Heading to {ref(*stand)} to {JOBS[kind][0].lower()}.")
                self.delay_orders(side, u)
        self.bump()

    def _start_job(self, u, kind, tgt):
        secs = JOBS[kind][1] * self.slow(u)
        u.path, u.dest, u.target_id, u.plan = [], None, None, None
        u.job = dict(kind=kind, c=tgt[0], r=tgt[1], start=self.t, done_at=self.t + secs)
        agents.say(self, u, f"{JOBS[kind][0]} at {ref(*tgt)}. About {int(secs)} s.")

    def _work(self, u):
        if u.plan and not u.path and not u.job:
            kind, c, r = u.plan
            u.plan = None
            err, tgt, stand = self.job_target(u.team, u, kind, (c, r))
            if err:
                agents.say(self, u, err)
            else:
                self._start_job(u, kind, tgt)
        if not u.job or self.t < u.job["done_at"]:
            return
        kind, c, r = u.job["kind"], u.job["c"], u.job["r"]
        u.job = None
        if kind == "clear":
            gone = [p for p in list(self.mines) if manhattan(p, (c, r)) <= 1 and (p in self.mines_known[u.team] or self.mines[p] == u.team)]
            for p in gone:
                del self.mines[p]
                for s in SIDES:
                    self.mines_known[s].discard(p)
            agents.say(self, u, f"Cleared {len(gone)} mine{'s' if len(gone) != 1 else ''} near {ref(c, r)}." if gone else "Nothing left to clear here.")
        elif kind == "dig":
            self.board.grid[r][c] = "trench"
            agents.say(self, u, f"Trench dug at {ref(c, r)}.")
        elif kind == "camp":
            self.board.grid[r][c] = "camp"
            agents.say(self, u, f"Camp built at {ref(c, r)}.")
        elif kind == "factory":
            self.board.grid[r][c] = "factory"
            self.facilities[(c, r)] = dict(kind="factory", owner=u.team, capturer=None, progress=0, made_at=self.t)
            if homefront.active(self):
                self.home[u.team]["economy"] = max(0, self.home[u.team]["economy"] - industry.FACTORY_COST)
            agents.say(self, u, f"Factory built at {ref(c, r)}. Weapons get better and production goes up.")
        elif kind == "barricade":
            self.barricade_under[(c, r)] = self.board.terrain(c, r)
            self.board.grid[r][c] = "barricade"
            agents.say(self, u, f"Barricade up at {ref(c, r)}. Nothing on wheels or tracks gets through.")
        elif kind == "breach":
            self._remove_barricade(c, r)
            agents.say(self, u, f"Barricade at {ref(c, r)} breached. The way is open.")
        elif kind == "plant" and u.stock > 0:
            self.mines[(c, r)] = u.team
            u.stock -= 1
            agents.say(self, u, f"Mine laid at {ref(c, r)}. {u.stock} left.")
        elif kind == "bridge":
            self.board.grid[r][c] = "bridge"
            self.ruined_bridges.discard((c, r))
            self.say(f"{u.label} rebuilt the bridge at {ref(c, r)}.")
            agents.say(self, u, f"Bridge at {ref(c, r)} is open again.")

    def _remove_barricade(self, c, r):
        if self.board.terrain(c, r) == "barricade":
            self.board.grid[r][c] = self.barricade_under.pop((c, r), "plains")

    # ---------- traps: ambush and lure ----------
    def set_ambush(self, side, u):
        """Lie in wait: hidden (spotted only from 1 tile), holding fire, until the enemy is close or this unit is hit."""
        if ATTACK[u.type][0] <= 0:
            return f"{u.callsign} has no weapon to ambush with, sir."
        u.ambush, u.hold_fire = True, True
        u.path, u.dest, u.target_id, u.plan = [], None, None, None
        return agents.ack(u, "In ambush: hidden, weapons held until they walk into it")

    def trap(self, side, uid, kind, c=None, r=None):
        """UI entry for the two trap orders. The unit answers over the radio."""
        u = self.unit_by_id(uid)
        if not u or u.team != side or self.winner:
            return
        msg = self.set_ambush(side, u) if kind == "ambush" else self.start_lure(side, u, (c, r)) if c is not None else "Where is the trap, sir?"
        agents.say(self, u, msg, urgent=True)
        self.bump()

    def _spring(self, u):
        """The ambush goes off: every ambusher near this one opens fire together with double damage for a few seconds."""
        for m in self.units:
            if m.team == u.team and m.ambush and manhattan((m.c, m.r), (u.c, u.r)) <= 4 and m.hp > 0:
                m.ambush, m.hold_fire = False, False
                m.sprung_until = self.t + 8
                if m.team == self.human:
                    agents.say(self, m, "AMBUSH! Opening fire!", urgent=True)
                    self.add_sfx("alarm")
        self.say(f"{u.label} sprang an ambush at {ref(u.c, u.r)}.")

    def _ambushes(self):
        for u in self.units:
            if u.ambush and u.hp > 0:
                seen = self.detected[u.team]
                reach = max(2, min(u.stats["range"], 3))
                if any(e.id in seen and e.hp > 0 and rules.dist(u, e) <= reach for e in self.units if e.team != u.team):
                    self._spring(u)

    def start_lure(self, side, u, trap):
        """Bait: go towards the nearest spotted enemy until it sees us, then run for the trap where friends lie in ambush."""
        foes = [e for e in self.units if e.team != u.team and e.id in self.detected[u.team]]
        if not foes:
            return "No enemy in sight to lure, sir. Find them first."
        if not self.path_for(u, trap):
            return f"No route to the trap at {ref(*trap)}, sir."
        u.lure = dict(trap=trap, phase="approach", t0=self.t)
        u.ambush, u.hold_fire = False, True
        e = min(foes, key=lambda x: rules.dist(u, x))
        p = self.path_for(u, (e.c, e.r), allow_goal_occupied=True)
        u.path, u.dest, u.target_id = (p[:-1] if p else []), None, None
        return agents.ack(u, f"Playing bait. Going out until they see me, then running for {ref(*trap)}")

    def _lure(self, u):
        if not u.lure:
            return
        foe = "red" if u.team == "blue" else "blue"
        L = u.lure
        if L["phase"] == "approach":
            if u.id in self.detected[foe] or self.t - L["t0"] > 40:
                if u.id in self.detected[foe]:
                    L["phase"] = "retreat"
                    p = self.path_for(u, L["trap"]) or []
                    u.path, u.dest = p, L["trap"]
                    agents.say(self, u, f"They've seen me! Running for {ref(*L['trap'])}. Enemy is following.", urgent=True)
                else:
                    u.lure = None
                    agents.say(self, u, "Nobody took the bait, sir. Calling it off.", urgent=True)
            elif not u.path:
                foes = [e for e in self.units if e.team == foe and e.id in self.detected[u.team]]
                if foes:
                    e = min(foes, key=lambda x: rules.dist(u, x))
                    p = self.path_for(u, (e.c, e.r), allow_goal_occupied=True)
                    u.path = p[:-1] if p else []
        elif not u.path and (u.c, u.r) == tuple(L["trap"]):
            u.lure = None
            agents.say(self, u, "Bait is at the trap. Over to you.", urgent=True)
        elif not u.path:
            u.path = self.path_for(u, L["trap"]) or []
            u.dest = L["trap"]

    # ---------- barracks, training camps, veterans ----------
    def _facilities(self):
        """Barracks train a new rifle squad every 90 s for whoever holds them; units drilling 20 s on a training camp become veterans."""
        for pos, f in self.facilities.items():
            if f["kind"] == "barracks" and self.t - f["made_at"] >= 90 + homefront.slowdown(self, f["owner"]) * 4 and self.t > 0:
                count = sum(1 for u in self.units if u.team == f["owner"] and u.type == "infantry")
                there = self.unit_at(*pos)
                if count < 6 and (there is None or there.team == f["owner"]):
                    spot = self.free_near(pos[0], pos[1], "infantry")
                    f["made_at"] = self.t
                    if spot:
                        n = self.new_unit(f["owner"], "infantry", *spot)
                        self.say(f"{TEAM_SHORT[f['owner']]}'s barracks at {ref(*pos)} trained a new rifle squad.")
                        if f["owner"] == self.human:
                            agents.radio(self, f["owner"], "in", "HQ-Radio", f"The barracks at {ref(*pos)} trained a new squad: {n.callsign} at {ref(*spot)}.")
        for u in self.units:
            f = self.facilities.get((u.c, u.r))
            if f and f["kind"] == "training_camp" and f["owner"] == u.team and not u.air and not u.vet and ATTACK[u.type][0] > 0 and not u.path:
                if u.train_since < 0:
                    u.train_since = self.t
                elif self.t - u.train_since >= 20:
                    u.vet, u.train_since = 1, -1
                    u.hp += 2
                    if u.team == self.human:
                        agents.say(self, u, "Training complete. We are veterans now: tougher and harder-hitting.", urgent=True)
                        self.add_sfx("chime")
            else:
                u.train_since = -1

    # ---------- morale ----------
    def _morale(self, u):
        if u.air or u.type == "supply_ship":
            return
        u.morale = min(u.morale, homefront.morale_ceiling(self, u.team))     # a shaky government shakes its army
        if self.t - u.hurt_at >= 8 and self.t % 5 == 0:
            near = (self.objectives.get((u.c, u.r)) or self.facilities.get((u.c, u.r)) or {}).get("owner") == u.team or self.board.terrain(u.c, u.r) == "camp"
            u.morale = min(100.0, u.morale + (2 if near else 1))
        if self.supply[u.team]["food"] < 20 and self.t % 5 == 0:
            u.morale = max(0.0, u.morale - .5)                      # hungry troops lose heart
        if u.morale < 30 and "shaky" not in u.flags and u.team == self.human:
            u.flags.add("shaky")
            agents.open_report(self, u, "morale", f"Morale is breaking, {int(u.morale)} of 100. We can't keep this up.",
                               [dict(id="fallback", label="Fall back and rest"), dict(id="fight_on", label="Hold the line")])
        if u.morale >= 60:
            u.flags.discard("shaky")
        if u.morale < 12 and u.stats["move"] > 0 and u.extract_at is None and "routed" not in u.flags and not u.job:
            u.flags.add("routed")                                    # it breaks and runs for friendly ground
            p = min([q for q, o in self.objectives.items() if o["owner"] == u.team], key=lambda q: abs(q[0] - u.c) + abs(q[1] - u.r), default=None)
            if p and p != (u.c, u.r):
                u.target_id, u.hold_fire = None, True
                u.path = self.path_for(u, p) or []
                u.dest = p
            self.say(f"{u.label} broke and ran.")
            if u.team == self.human:
                agents.say(self, u, "We're breaking! Can't hold! Falling back!", urgent=True)
        elif u.morale >= 40:
            u.flags.discard("routed")

    # ---------- gas and floods: the General's answers ----------
    def mask_up(self, side, on):
        """Masks on (or off) for every ground unit within 4 tiles of a cloud, or for all if none is near. Returns how many."""
        n = 0
        for u in agents.own_units(self, side):
            if u.air or u.type == "supply_ship":
                continue
            if not self.clouds or any(abs(u.c - cl["c"]) + abs(u.r - cl["r"]) <= cl["radius"] + 4 for cl in self.clouds):
                u.mask = on
                n += 1
        return n

    def evacuate_gas(self, side):
        """Send every ground unit near a cloud five tiles away from it (upwind)."""
        n = 0
        for u in agents.own_units(self, side):
            if u.air or u.stats["move"] == 0 or u.type == "supply_ship":
                continue
            cl = next((x for x in self.clouds if abs(u.c - x["c"]) + abs(u.r - x["r"]) <= x["radius"] + 3), None)
            if not cl:
                continue
            dc = (u.c > cl["c"]) - (u.c < cl["c"]) or 1
            dr = (u.r > cl["r"]) - (u.r < cl["r"])
            c, r = min(max(u.c + 5 * dc, 0), self.board.width - 1), min(max(u.r + 5 * dr, 0), self.board.height - 1)
            spot = self.free_near(c, r, u.type)
            if spot:
                self.order_move(side, u, *spot)
                n += 1
        self.notice[side] = ""
        return n

    def evacuate_flood(self, side):
        """Move ground units standing on (or beside) a flood plain two tiles clear of it."""
        n = 0
        for f in self.floods:
            for u in agents.own_units(self, side):
                if u.air or u.stats["move"] == 0 or abs(u.c - f["c"]) + abs(u.r - f["r"]) > 1:
                    continue
                for dc, dr in ((2, 0), (-2, 0), (0, 2), (0, -2), (3, 0), (-3, 0)):
                    c, r = f["c"] + dc, f["r"] + dr
                    if self.board.inside(c, r) and not any((x["c"], x["r"]) == (c, r) for x in self.floods) and not self.unit_at(c, r) \
                            and rules.step_cost(u.type, self.board.terrain(c, r)) is not None:
                        self.order_move(side, u, c, r)
                        n += 1
                        break
        self.notice[side] = ""
        return n

    # ---------- air: fuel, landing, bombs ----------
    def airfields(self, team):
        mid = self.board.width // 2
        return [(c, r) for r in range(self.board.height) for c in range(self.board.width)
                if self.board.terrain(c, r) == "airfield" and ((c < mid) == (team == "blue"))]

    def _air(self, u):
        """Aircraft burn fuel while flying and refuel, rearm and mend on their own airfield."""
        if not u.air:
            return
        if self.board.terrain(u.c, u.r) == "airfield" and (u.c, u.r) in self.airfields(u.team) and not u.path:
            u.fuel = min(u.max_fuel, u.fuel + 8)
            if self.t % 3 == 0 and u.ammo < u.start_ammo:
                u.ammo += 1
            u.flags.discard("bingo")
            return
        u.fuel -= 1
        if u.hp > 0 and not u.path and not u.target_id and (u.mission or (ATTACK[u.type][0] > 0 and u.ammo <= 0)):
            u.mission = False                                          # the strike is over (or the guns are empty): fly home
            if u.team == self.human:
                agents.say(self, u, agents.pull_back(self, u.team, u))
            else:
                p = agents.nearest_airfield(self, u)
                if p:
                    self.order_move(u.team, u, *p)
        if u.fuel <= 0 and u.hp > 0:
            u.hp = 0
            self.say(f"{u.label} ran out of fuel and crashed at {ref(u.c, u.r)}.")
            self.add_sfx("boom", u.c, u.r)
            if u.team == self.human:
                agents.radio(self, u.team, "in", u.callsign, f"MAYDAY MAYDAY. Out of fuel, going down at {ref(u.c, u.r)}.")

    def _bomb(self, u, tgt):
        """A bombing run: the target tile and its neighbours are hit (friend and foe alike)."""
        self._impact(dict(at=self.t, c=tgt.c, r=tgt.r, dmg=ATTACK[u.type][0], by=u.label, team=u.team))
        u.ammo -= 1
        u.ready_at = self.t + ATTACK[u.type][1]
        if u.team == self.human:
            agents.say(self, u, f"Bombs away on {ref(tgt.c, tgt.r)}!", urgent=True)

    # ---------- support: medics and supply trucks ----------
    def _support(self, u):
        if u.type == "medic" and self.t % 4 == 0:
            for f in self.units:
                if f.team == u.team and f.id != u.id and not f.air and f.hp < f.max_hp and rules.dist(u, f) <= 1:
                    f.hp += 1
                    f.hurt_at = max(f.hurt_at, self.t - 4)
                    if f.hp * 2 > f.max_hp:
                        f.flags.discard("damaged")
                    if f.team == self.human and self.t - f.care_at > 20:
                        f.care_at = self.t
                        agents.say(self, f, f"{u.callsign} is patching me up, HP {f.hp}/{f.max_hp}.")
        if u.type == "supply_truck" and self.t % 5 == 0:
            for f in self.units:
                if f.team == u.team and f.id != u.id and f.start_ammo and f.ammo < f.start_ammo and rules.dist(u, f) <= 1:
                    f.ammo = min(f.start_ammo, f.ammo + 4)
                    if f.ammo * 4 > f.start_ammo:
                        f.flags.discard("lowammo")
                    if f.team == self.human and self.t - f.care_at > 20:
                        f.care_at = self.t
                        agents.say(self, f, f"{u.callsign} is resupplying me, ammo {f.ammo}.")

    # ---------- healing: withdrawing to friendly ground repairs ----------
    def _heal(self, u):
        if u.hp >= u.max_hp or self.t - u.hurt_at < 8 or self.t % 5 or u.extract_at is not None:
            return
        here = (u.c, u.r)
        home = (self.objectives.get(here, {}).get("owner") == u.team or self.board.terrain(*here) == "camp"
                or (u.air and self.board.terrain(*here) == "airfield" and here in self.airfields(u.team)))
        near = any(o["owner"] == u.team and manhattan(here, p) <= 2 for p, o in self.objectives.items())
        if home or (near and self.t % 10 == 0):
            u.hp += 1
            if u.hp * 2 > u.max_hp:
                u.flags.discard("damaged")
            if u.hp * 4 > u.max_hp:
                u.flags.discard("sinking")
            if u.hp >= u.max_hp and u.team == self.human:
                agents.say(self, u, "Repaired and ready for orders, sir.")

    # ---------- spies ----------
    def _spy(self, u):
        if u.type != "spy" or self.t % SPY_EVERY:
            return
        foe = OTHER[u.team]
        fresh = []
        for e in self.units:
            if e.team == foe and e.hp > 0 and manhattan((u.c, u.r), (e.c, e.r)) <= SPY_RANGE:
                self.intel[u.team][e.id] = dict(type=e.type, team=e.team, c=e.c, r=e.r, seen=self.t)
                if e.id not in u.spy_seen:
                    u.spy_seen.add(e.id)
                    fresh.append(e)
        for pos, o in self.objectives.items():
            if manhattan((u.c, u.r), pos) <= SPY_RANGE:
                self.obj_known[u.team][pos] = o["owner"]
        if fresh and u.team == self.human:
            text = "; ".join(f"{STATS[e.type]['label'].upper()} AT {ref(e.c, e.r)}" for e in fresh[:3])
            agents.radio(self, self.human, "in", u.callsign, text, kind="morse")

    # ---------- reinforcements ----------
    def reinforce(self, side, kind, c=None, r=None):
        """Call limited support. Returns a message for the General."""
        spec = REINFORCE.get(kind)
        if self.winner:
            return "The war is over."
        if not spec:
            return "Unknown support. Choose air, sea or land."
        if self.reinf_left[side][kind] <= 0:
            return f"No {spec['label'].lower()} left to call."
        if spec["needs_tile"]:
            if c is None or r is None or not self.board.inside(c, r):
                return f"Give a grid reference, e.g. 'reinforcements {kind} to Delta-7'."
            terrain = self.board.terrain(c, r)
            ok = (terrain in rules.INFANTRY) if spec["needs_tile"] == "land" else (terrain in rules.SHIP)
            if not ok:
                return f"{spec['label']} cannot arrive at {ref(c, r)}: wrong kind of ground."
            if self.territory(side).get((c, r)) != "own":
                return f"{ref(c, r)} is not in our territory."
        else:
            own = [p for p, o in self.objectives.items() if o["owner"] == side]
            if not own:
                return "We hold no port or city to receive a convoy."
            c, r = min(own, key=lambda p: manhattan(p, (8 if side == "blue" else 12, 7)))
        self.reinf_left[side][kind] -= 1
        eta = spec["eta"] + homefront.slowdown(self, side)                # corruption slows everything down
        self.arrivals.append(dict(at=self.t + eta, team=side, kind=kind, c=c, r=r))
        msg = f"{spec['label']} on the way. ETA {eta} sec at {ref(c, r)}."
        if side == self.human:
            agents.radio(self, side, "in", "HQ-Radio", msg)
        self.bump()
        return msg

    def _arrive(self, a):
        team, kind = a["team"], a["kind"]
        pack = {"air": [("infantry", 2)], "sea": [("destroyer", 1)], "land": [("tank", 1), ("infantry", 1)]}[kind]
        placed = []
        for typ, n in pack:
            for _ in range(n):
                spot = self.free_near(a["c"], a["r"], typ)
                if spot:
                    placed.append(self.new_unit(team, typ, *spot))
        if team == self.human:
            agents.radio(self, team, "in", "HQ-Radio", f"{REINFORCE[kind]['label']} have arrived at {ref(a['c'], a['r'])}: "
                         + ", ".join(p.callsign for p in placed) + ".")
        self.say(f"{TEAM_SHORT[team]} reinforcements ({REINFORCE[kind]['label'].lower()}) arrived.")
        if team == self.human:
            self.add_sfx("chime")

    # ---------- the strait: supply convoys ----------
    def _spawn_convoy(self, side):
        entrance, goal = LANES[side]
        if self.unit_at(*entrance):
            self.convoy_due[side] = True               # entrance busy: try again next second
            return
        self.convoy_due[side] = False
        u = self.new_unit(side, "supply_ship", *entrance)
        u.dest = goal
        u.path = self.path_for(u, goal) or []
        u.blocked_since = None if u.path else self.t
        if side == self.human:
            eta = f", ETA {self.eta(u, u.path)} sec" if u.path else ""
            agents.say(self, u, f"Entering the strait with {CARGO} fuel and {CARGO} food for {ref(*goal)}{eta}.", urgent=True)

    def _supply_tick(self):
        for side in SIDES:
            s = self.supply[side]
            own = [u for u in self.units if u.team == side]
            veh = sum(1 for u in own if u.type in VEHICLES)
            ppl = sum(1 for u in own if u.type in PERSONNEL)
            s["fuel"] = max(0.0, s["fuel"] - .03 * veh * (1.5 if self.winter else 1.0))       # engines burn more in the cold
            s["food"] = max(0.0, s["food"] - .03 * ppl - .005 * veh)
            for level in (30, 10, 1):
                key = (level,)
                if min(s["fuel"], s["food"]) < level and key not in s["warned"]:
                    s["warned"].add(key)
                    if side == self.human:
                        agents.radio(self, side, "in", "HQ-Radio", f"WARNING: fuel {int(s['fuel'])}%, food {int(s['food'])}%. "
                                     + ("Units will respond late until the strait is open and convoys get through." if level > 1 else "Supplies are exhausted."))
            if min(s["fuel"], s["food"]) >= 40:
                s["warned"].clear()
            s["zero_for"] = s["zero_for"] + 1 if (s["fuel"] <= 0 and s["food"] <= 0) else 0
            if self.t >= CONVOY_FIRST and ((self.t - CONVOY_FIRST) % self.convoy_every == 0 or self.convoy_due[side]):
                self._spawn_convoy(side)

    def _convoy_arrived(self, u):
        if u.type == "supply_ship" and (u.c, u.r) == LANES[u.team][1]:
            s = self.supply[u.team]
            load = homefront.cargo(self, u.team, CARGO)                 # corruption skims it, a weak economy buys less
            s["fuel"], s["food"] = min(100.0, s["fuel"] + load), min(100.0, s["food"] + load)
            if load < CARGO:
                self.say(f"{TEAM_SHORT[u.team]}'s convoy arrived short: {load} instead of {CARGO} (corruption and a weak economy).")
            homefront.on_convoy(self, u.team)
            u.hp = 0
            self.delivered[u.team] += 1
            self.delivered_ids.add(u.id)
            self.add_sfx("chime")
            self.say(f"{TEAM_SHORT[u.team]} supply convoy unloaded {CARGO} fuel and {CARGO} food.")
            if u.team == self.human:
                agents.radio(self, u.team, "in", u.callsign, f"Convoy delivered. Fuel {int(s['fuel'])}%, food {int(s['food'])}%.")

    # ---------- the clock ----------
    def control(self, action, value=None):
        if action == "pause":
            self.paused = True
        elif action == "resume":
            self.paused = False
        elif action == "speed" and value in (0.25, 0.5, 1, 2, 4):
            self.speed = value
        elif action == "think" and value in (0, 15, 30, 60):
            self.think_secs = value
            self.pause_on_report = value > 0
            self.think_until = 0.0
        elif action == "red_mode" and value in ("llm", "heuristic"):
            self.red_mode = value
        self.bump()

    def thinking_left(self):
        """Real seconds the clock is still waiting for the General to decide (0 = running)."""
        if not self.pause_on_report or not any(r["kind"] in agents.REPORT_TTL for r in self.reports):
            return 0
        return max(0, int(self.think_until - _time.monotonic() + .999))

    def decision_stats(self):
        done = [d for d in self.decisions if d["status"] != "pending"]
        good = sum(1 for d in done if d["status"] == "success")
        r = self.resp
        return dict(total=len(done), good=good, bad=len(done) - good, avg=round(r["total"] / r["answered"], 1) if r["answered"] else None)

    # ---------- the AI General (a WebLLM model in a browser tab plays Candooo through these two calls) ----------
    def general_brief(self, side="red"):
        """What Candooo's General may know (its own fog of war), as text for a language model."""
        units = agents.own_units(self, side)[:16]
        seen = [e for e in (self.unit_by_id(i) for i in self.detected[side]) if e][:8]
        self.brief_targets[side] = {f"E{i + 1}": e.id for i, e in enumerate(seen)}
        targets = [p for p, o in self.objectives.items() if self.obj_known[side].get(p) != side]
        s = self.supply[side]
        lines = [f"Time {fmt_time(self.t)}. We hold {sum(1 for o in self.objectives.values() if o['owner'] == side)} of {len(self.objectives)} ports and cities. "
                 f"Fuel {int(s['fuel'])}%, food {int(s['food'])}%. Wind {self.wind_info()['text']}.",
                 "Enemy objectives to capture (infantry must stand on them): " + (", ".join(ref(*p) for p in targets[:8]) or "none known") + ".",
                 "Our units:"]
        lines += [f"- {u.callsign}: {u.stats['label']} at {ref(u.c, u.r)}, HP {u.hp}/{u.max_hp}, ammo {u.ammo}, {self.status(u).lower()}" for u in units]
        lines.append("Enemies we can see:" + ("" if seen else " none"))
        lines += [f"- E{i + 1}: {e.stats['label']} at {ref(e.c, e.r)}" for i, e in enumerate(seen)]
        system = ("You are the General of Candooo in a wargame. Choose a few orders for your units. Reply with JSON only, no other text: "
                  '{"orders":[{"unit":"<a name from the list>","action":"move","to":"<a grid reference from the lists>"},'
                  '{"unit":"<a name from the list>","action":"attack","target":"<E1, E2...>"}],"say":"<your own short radio line>"}. '
                  "Never copy the placeholders: fill them in with real names and places. "
                  "Allowed actions: move (needs 'to' as a grid reference like Kilo-5), attack (needs 'target' like E1), hold_fire, fire_at_will, fall_back, "
                  "dig, plant, clear, bridge, camp, call (needs 'kind': air, sea or land, and 'to' for air and sea). Use only unit names from the list. "
                  "Capture enemy ports and cities with infantry, protect the supply convoys, and keep tanks near infantry. At most 6 orders.")
        return dict(system=system, user="\n".join(lines), mode=self.red_mode)

    def apply_general_orders(self, side, orders, say=""):
        """Validate and carry out orders from the AI General. Anything illegal is refused with a reason."""
        if side == self.human:
            return dict(applied=0, rejected=["Only the AI General may use this."])
        applied, rejected, said = 0, [], []
        mine = {u.callsign.lower(): u for u in agents.own_units(self, side)}
        for o in (orders or [])[:6]:
            if not isinstance(o, dict):
                rejected.append("order is not an object")
                continue
            u = mine.get(str(o.get("unit", "")).lower())
            act = str(o.get("action", "")).lower()
            if act == "call":
                msg = self.reinforce(side, str(o.get("kind", "")), *(agents.parse_ref(self.board, str(o.get("to", ""))) or (None, None)))
                (rejected if "on the way" not in msg else said).append(msg)
                applied += "on the way" in msg
                continue
            if not u:
                rejected.append(f"unknown unit {o.get('unit')!r}")
                continue
            if act == "move":
                tgt = agents.parse_ref(self.board, str(o.get("to", "")))
                if not tgt:
                    rejected.append(f"{u.callsign}: bad grid reference")
                    continue
                self.order_move(side, u, *tgt)
            elif act == "attack":
                uid = self.brief_targets[side].get(str(o.get("target", "")).upper())
                e = self.unit_by_id(uid) if uid else None
                if not e or e.id not in self.detected[side]:
                    rejected.append(f"{u.callsign}: no such visible target")
                    continue
                self.order_attack(side, u, e)
            elif act in ("hold_fire", "fire_at_will"):
                u.hold_fire = act == "hold_fire"
            elif act == "fall_back":
                agents.pull_back(self, side, u)
            elif act in ("dig", "plant", "clear", "bridge", "camp"):
                self.work(side, u.id, act, agents.parse_ref(self.board, str(o.get("to", ""))))
            else:
                rejected.append(f"{u.callsign}: unknown action {act!r}")
                continue
            if self.notice[side]:
                rejected.append(self.notice[side])
                self.notice[side] = ""
                continue
            applied += 1
            said.append(f"{u.callsign} {act.replace('_', ' ')} {str(o.get('to') or o.get('target') or '').strip()}".strip())
        if applied:
            self.general_at = self.t
            events.intercept(self, "Candooo HQ: " + "; ".join(said[:3]) + (f". {str(say)[:80]}" if say else ""))
        self.bump()
        return dict(applied=applied, rejected=rejected)

    def tick(self):
        if self.winner:
            return
        self.t += 1
        if self.winter_at and not self.winter and self.t >= self.winter_at:
            self.winter = True
            self.say("Winter has come: mud and frost.")
            agents.radio(self, self.human, "in", "HQ-Radio", "WINTER. Mud and frost: every ground unit moves 60% slower and engines burn half as much fuel again. Finish the job or dig in.")
            self.add_sfx("alarm")
        for item in [q for q in self.radio_queue if q[0] <= self.t]:      # replies that are due
            self.radio_queue.remove(item)
            agents.radio(self, self.human, "in", item[1], item[2], item[3])
        self._extractions()
        self._observe()
        self.effects = [e for e in self.effects if e["until"] > self.t]
        due = [i for i in self.impacts if i["at"] <= self.t]
        self.impacts = [i for i in self.impacts if i["at"] > self.t]
        for i in due:
            self._impact(i)
        for a in [a for a in self.arrivals if a["at"] <= self.t]:
            self.arrivals.remove(a)
            self._arrive(a)
        for u in list(self.units):
            if u.hp > 0:
                self._drift(u)
                self._lure(u)
                self._move(u)
                if u.type == "fighter" and self.t % 3 and u.path:         # a fighter is faster than one tile a second
                    u.next_step_at = min(u.next_step_at, self.t)
                    self._move(u)
                self._work(u)
                self._fight(u)
                self._spy(u)
                self._air(u)
                if u.plan_air:
                    airlift.step(self, u)
                self._support(u)
                self._morale(u)
                self._heal(u)
                self._convoy_arrived(u)
        self._ambushes()
        for u in self.units:
            if u.hp <= 0 and u.cargo:
                airlift.lost(self, u)
        self.units = [u for u in self.units if u.hp > 0]
        self._facilities()
        self._supply_tick()
        self._capture()
        self._observe()
        self._nuke_scan()
        if self.blast and self.t >= self.blast["at"]:
            self._detonate()
        ai_red.think(self, "red")
        events.tick(self)
        homefront.tick(self)
        world.tick(self)
        industry.tick(self)
        personas.tick(self)
        timeline.news_tick(self)
        timeline.red_test(self)
        if levels.LEVELS[self.level_id]["daynight"] and self.t and self.t % 120 == 0:
            agents.radio(self, self.human, "in", "HQ-Radio", "NIGHTFALL: ground and sea units see one tile less until dawn." if self.is_night() else "DAWN: visibility is back to normal.")
        occupation.tick(self)
        raid.tick(self)
        timeline.tick(self)
        agents.scan(self)
        if self.t % 10 == 0 and not self.code_red_sent and self.war_status(self.human)["verdict"] == "lost":
            self.code_red_sent = True
            agents.radio(self, self.human, "in", "HQ-Radio", "CODE RED. CODE RED. The war is slipping away. Consider the strait, reinforcements, or the last resort.")
            self.add_sfx("alarm")
        self._check_win()
        self.bump()

    def airlift_say(self, side, u, what, at=None, uid=None):
        msg = airlift.command(self, side, u, what, *(at or (None, None)), uid=uid)
        agents.say(self, u, msg)
        self.bump()
        return msg

    # ---------- extraction ----------
    def request_extraction(self, side, u, eta=None):
        """A unit holds still and is picked up in `eta` seconds (20 with a medevac helicopter, else 45), then rejoins at the
        nearest friendly port or city, patched up."""
        if u.extract_at is not None:
            return
        if u.type in airlift.CARRIED_ALL and not u.air:                 # a free helicopter flies in for the pick-up
            for h in airlift.lifters(self, side):
                if len(h.cargo) < airlift.CAPACITY and h.type == "transport_helicopter":
                    agents.say(self, u, f"Requesting extraction at {ref(u.c, u.r)}. {h.callsign} is coming for us.", urgent=True)
                    airlift.command(self, side, h, "extract", uid=u.id)
                    return
        if eta is None:
            eta = 20 if any(m.type == "medevac_helicopter" and m.team == u.team and m.hp > 0 for m in self.units) and not u.air else 45
        u.extract_at = self.t + eta
        u.path, u.dest, u.target_id, u.job, u.plan = [], None, None, None, None
        agents.say(self, u, f"Extraction at {ref(u.c, u.r)}, ETA {eta} sec. Holding position.", urgent=True)

    def _extractions(self):
        for u in list(self.units):
            if u.extract_at is not None and self.t >= u.extract_at and u.hp > 0:
                self.units.remove(u)
                self.returning.append(dict(due=self.t + 30, team=u.team, type=u.type, hp=u.hp))
                self.say(f"{u.label} was extracted from {ref(u.c, u.r)}.")
                if u.team == self.human:
                    agents.radio(self, u.team, "in", "HQ-Radio", f"{u.callsign} extracted from {ref(u.c, u.r)}. Back in 30 sec.")
        for item in [x for x in self.returning if x["due"] <= self.t]:
            self.returning.remove(item)
            base = [p for p, o in self.objectives.items() if o["owner"] == item["team"]]
            if base:
                spot = self.free_near(*min(base, key=lambda p: manhattan(p, (4 if item["team"] == "blue" else 17, 7))), item["type"])
                if spot:
                    n = self.new_unit(item["team"], item["type"], *spot)
                    n.hp = max(item["hp"], n.max_hp // 2)
                    if n.team == self.human:
                        agents.radio(self, n.team, "in", n.callsign, f"Back in the fight at {ref(*spot)}, HP {n.hp}/{n.max_hp}.")

    def _drift(self, u):
        """A ship that is not under way is carried east by a high current, one tile every 6 seconds."""
        if (u.stats["domain"] != "sea" or u.path or u.job or self.t % 6 or self.board.terrain(u.c, u.r) != "high_current"
                or u.extract_at is not None):
            return
        c, r = u.c + 1, u.r
        if (self.board.inside(c, r) and rules.step_cost(u.type, self.board.terrain(c, r)) is not None
                and not self.unit_at(c, r) and (c, r) not in self.mines):
            u.c = c

    def _target(self, u):
        """The unit's attack target, or None (and the order is dropped) if it died or is no longer spotted."""
        if not u.target_id:
            return None
        t = self.unit_by_id(u.target_id)
        if t and t.id in self.detected[u.team]:
            return t
        if t:
            self.say(f"{u.label} lost contact with its target.")
        u.target_id = None
        return None

    def _move(self, u):
        if u.stats["move"] == 0 or u.job or u.extract_at is not None or u.shaken_until > self.t:
            return
        tgt = self._target(u)
        if tgt and u.type not in MISSILE_TYPES:
            if self.reaches(u, tgt):
                u.path = []
                return
            if not u.path or self.t % 3 == 0:
                p = self.path_for(u, (tgt.c, tgt.r), allow_goal_occupied=True)
                u.path = p[:-1] if p else []
        if not u.path and u.dest and self.t % 3 == 0:     # a route that was blocked: try again
            u.path = self.path_for(u, u.dest) or []
            if not u.path and u.blocked_since is None:
                u.blocked_since = self.t
        if not u.path or self.t < u.next_step_at:
            return
        c, r, cost = u.path[0]
        if any(x.c == c and x.r == r and x.hp > 0 and x.air == u.air and x is not u for x in self.units):   # blocked (aircraft fly over ground units)
            if u.blocked_since is None:
                u.blocked_since = self.t
            if u.dest:
                u.path = self.path_for(u, u.dest) or []
            return
        dc, dr = c - u.c, r - u.r
        u.heading = int(math.degrees(math.atan2(dr, dc))) % 360
        u.c, u.r = c, r
        u.path.pop(0)
        u.blocked_since = None
        u.next_step_at = self.t + cost * rules.secs_per_cost(u) * self.slow(u)
        if not u.path:
            u.dest = None
        owner = self.mines.get((c, r))
        if owner and owner != u.team:               # stepped on a hidden mine
            del self.mines[(c, r)]
            for s in SIDES:
                self.mines_known[s].discard((c, r))
            self.say(f"{u.label} hit a mine at {ref(c, r)}.")
            self.add_sfx("boom", c, r)
            self._hit("A mine", u, MINE_DAMAGE)
            if u.hp > 0 and u.team == self.human:
                agents.say(self, u, f"We hit a mine at {ref(c, r)}! HP {u.hp}/{u.max_hp}.")

    def _fight(self, u):
        dmg, cooldown, _ = ATTACK[u.type]
        if dmg <= 0 or u.ammo <= 0 or self.t < u.ready_at or u.shaken_until > self.t:
            return
        tgt = self._target(u)
        if tgt and not (self.reaches(u, tgt) and rules.can_hit(u, tgt)):
            tgt = None
        if u.type in MISSILE_TYPES:
            if not tgt:
                return                              # missiles only fire on explicit orders
            # wind pushes a missile off target; the longer the flight, the further
            dist = rules.dist(u, tgt)
            ic = min(max(tgt.c + round(self.wind[0] * dist / 6), 0), self.board.width - 1)
            ir = min(max(tgt.r + round(self.wind[1] * dist / 6), 0), self.board.height - 1)
            self.impacts.append(dict(at=self.t + MISSILE_FLIGHT, c=ic, r=ir, dmg=dmg, by=u.label, team=u.team))
            u.ammo -= 1
            u.ready_at = self.t + cooldown
            u.target_id = None
            drift = f" (wind pushes it to {ref(ic, ir)})" if (ic, ir) != (tgt.c, tgt.r) else ""
            self.say(f"{u.label} fired a missile at {ref(tgt.c, tgt.r)}{drift}. Impact in {MISSILE_FLIGHT} s.")
            self.add_sfx("launch", u.c, u.r, ic, ir, MISSILE_FLIGHT)
            agents.missile_alert(self, u, ic, ir)
            self._provocation(u)
            homefront.on_missile(self, u.team)
            return
        if tgt and u.type == "bomber":              # a bombing run: only on an explicit order, over the target
            if rules.dist(u, tgt) <= 1:
                self._bomb(u, tgt)
                u.target_id = None
            return
        if not tgt:                                 # fire at will: nearest spotted enemy in range
            if u.hold_fire or u.type == "bomber":
                return
            seen = self.detected[u.team]
            cands = [e for e in self.units if e.id in seen and e.hp > 0 and self.reaches(u, e) and rules.can_hit(u, e)]
            tgt = min(cands, key=lambda e: (rules.dist(u, e), e.hp), default=None)
        if not tgt:
            return
        u.ammo -= 1
        u.ready_at = self.t + cooldown
        dist = rules.dist(u, tgt)
        kind = "gun" if u.type in ("infantry", "minesweeper", "destroyer") else "cannon"
        chance = max(.55, 1 - .06 * (dist - 2)) - (.15 if self.storm_until else 0)
        if dist > 2 and self.rng.random() > chance:                              # long shots can miss and fall a tile away
            mc = min(max(tgt.c + (round(self.wind[0]) or self.rng.choice((-1, 1))), 0), self.board.width - 1)
            mr = min(max(tgt.r + round(self.wind[1]), 0), self.board.height - 1)
            self.add_sfx(kind, u.c, u.r, mc, mr, .5)
            self.add_sfx("miss", mc, mr)
            return
        self.add_sfx(kind, u.c, u.r, tgt.c, tgt.r, .5)
        self._provocation(u)
        dmg = rules.damage(u, tgt, self.board)
        if u.vet:
            dmg = math.ceil(dmg * 1.25)                          # veterans hit harder
        if u.morale < 30:
            dmg = max(1, round(dmg * .6))                        # a shaken unit shoots wildly
        fp = industry.firepower(self, u.team)                    # factories make every weapon better
        if fp > 1:
            dmg = max(dmg, round(dmg * fp))
        self._hit(u.label, tgt, dmg * (2 if u.sprung_until > self.t else 1), u.team)

    def reaches(self, u, e):
        """Can u's weapon reach e right now? In range, and for direct fire (rifles, tank guns, ships' guns) with a clear line
        of sight. Artillery, missiles and bombers fire on what a spotter sees; guns shooting at aircraft look up, not across."""
        if not rules.in_range(u, e):
            return False
        return u.air or e.air or u.type in rules.INDIRECT or rules.has_los(self.board, (u.c, u.r), (e.c, e.r))

    def _provocation(self, u):
        """On levels with restraint: shooting first, when the enemy has not fired lately, costs the government stability and markets."""
        if not self.restraint or u.team != self.human or not homefront.active(self) or self.t - self.last_enemy_fire <= 30:
            return
        h = self.home[u.team]
        h["stability"] = max(0, h["stability"] - 1.5)
        h["economy"] = max(0, h["economy"] - .5)
        if self.t - self.first_shot_news > 20:
            self.first_shot_news = self.t
            homefront._news(self, "first_shot", u.team)
            agents.radio(self, u.team, "in", "HQ-Radio", "Ladooo is being accused of firing first. The government pays for it at home. Let them shoot first, then answer.")

    def _hit(self, by, tgt, dmg, by_team=None):
        if tgt.shaken_until > self.t:                # caught unprepared: takes +50%
            dmg = math.ceil(dmg * 1.5)
        tgt.hp -= dmg
        tgt.hurt_at = self.t
        if tgt.hp > 0 and dmg >= 2 and not tgt.air:
            tgt.ready_at = max(tgt.ready_at, self.t + 1)          # suppression: a unit under fire shoots slower for a moment
        if by_team and by_team != tgt.team and tgt.team == self.human:
            self.last_enemy_fire = self.t                         # they shot first (or at least shot): our answer is not a provocation
        tgt.morale = max(0.0, tgt.morale - (2 + dmg))          # being hit shakes a unit
        if tgt.ambush:                               # being hit gives the ambush away
            self._spring(tgt)
        if tgt.hp <= 0:                              # seeing a comrade die shakes those nearby
            for f in self.units:
                if f.team == tgt.team and f.id != tgt.id and f.hp > 0 and rules.dist(f, tgt) <= 4:
                    f.morale = max(0.0, f.morale - 8)
        self.effects.append(dict(c=tgt.c, r=tgt.r, until=self.t + 2))
        if tgt.hp <= 0:
            self.say(f"{by} destroyed {tgt.label} at {ref(tgt.c, tgt.r)}.")
            self.add_sfx("boom", tgt.c, tgt.r)
            homefront.on_loss(self, tgt)
            if tgt.team == self.human:
                self.kia.append((tgt.callsign, tgt.stats["label"], ref(tgt.c, tgt.r)))
        else:
            self.add_sfx("hit", tgt.c, tgt.r)
            if tgt.team == self.human:
                agents.hit_report(self, tgt, friendly=by_team == tgt.team)

    def _impact(self, i):
        self.say(f"Missile from {i['by']} hit {ref(i['c'], i['r'])}.")
        if self.board.terrain(i["c"], i["r"]) == "bridge":          # a bridge is a choke point and can be destroyed
            self.board.grid[i["r"]][i["c"]] = "river"
            self.ruined_bridges.add((i["c"], i["r"]))
            self.say(f"The bridge at {ref(i['c'], i['r'])} was destroyed.")
            self.bridge_event = (i["c"], i["r"])
        for dc in range(-MISSILE_RADIUS, MISSILE_RADIUS + 1):                       # shells flatten barricades
            for dr in range(-MISSILE_RADIUS, MISSILE_RADIUS + 1):
                if abs(dc) + abs(dr) <= MISSILE_RADIUS and self.board.inside(i["c"] + dc, i["r"] + dr) and self.board.terrain(i["c"] + dc, i["r"] + dr) == "barricade":
                    self._remove_barricade(i["c"] + dc, i["r"] + dr)
                    self.say(f"The barricade at {ref(i['c'] + dc, i['r'] + dr)} was blown apart.")
        for u in list(self.units):
            d = abs(u.c - i["c"]) + abs(u.r - i["r"])
            if u.hp > 0 and d <= MISSILE_RADIUS:
                dmg = i["dmg"] if d == 0 else math.ceil(i["dmg"] / 2)
                self._hit(f"Missile ({i['by']})", u, max(1, round(dmg * rules.COVER.get(self.board.terrain(u.c, u.r), 1.0))), i["team"])
        self.effects.append(dict(c=i["c"], r=i["r"], until=self.t + 2))
        self.add_sfx("boom", i["c"], i["r"])

    def _capture(self):
        for (c, r), o in list(self.objectives.items()) + list(self.facilities.items()):
            fighters = ("infantry", "rebel", "commando") if o["kind"] in ("barracks", "training_camp", "factory") else ("infantry",)   # rebels seize camps, not cities
            teams = {u.team for u in self.units if u.type in fighters and (u.c, u.r) == (c, r) and u.hp > 0}
            if len(teams) == 1:
                team = next(iter(teams))
                if team == o["owner"]:
                    o["capturer"], o["progress"] = None, 0
                    continue
                if o["capturer"] != team:
                    o["capturer"], o["progress"] = team, 0
                o["progress"] += 1
                if o["progress"] >= CAPTURE_SECS:
                    loser = o["owner"]
                    o["owner"], o["capturer"], o["progress"] = team, None, 0
                    self.say(f"{TEAM_SHORT[team]} captured the {o['kind']} at {ref(c, r)}.")
                    homefront.on_capture(self, loser, o["kind"])
            elif not teams:
                o["progress"] = max(0, o["progress"] - 1)

    # ---------- the last resort ----------
    def _nuke_scan(self):
        """Units near a hidden site pick up clues: rumour (7 tiles), area (4), confirmed (2). Spies sense it from further."""
        for side in SIDES:
            for i, site in enumerate(self.nukes):
                best, who = 99, None
                for u in self.units:
                    if u.team == side and u.hp > 0:
                        d = manhattan((u.c, u.r), (site["c"], site["r"])) - (3 if u.type == "spy" else 0)
                        if d < best:
                            best, who = d, u
                level = 3 if best <= 2 else 2 if best <= 4 else 1 if best <= 7 else 0
                if level > self.nuke_level[side][i]:
                    self.nuke_level[side][i] = level
                    if level == 2:
                        self.nuke_fuzzy[(side, i)] = (min(self.board.width - 1, max(0, site["c"] + self.rng.randint(-2, 2))),
                                                      min(self.board.height - 1, max(0, site["r"] + self.rng.randint(-2, 2))))
                    if side == self.human and who:
                        agents.nuke_clue(self, who, level, site, self.nuke_fuzzy.get((side, i)))

    def war_status(self, side):
        """How the war is going: four measures, an overall balance, why, and what it takes to win or avoid losing."""
        foe = OTHER[side]
        objs = list(self.objectives.values())
        mine = sum(1 for o in objs if o["owner"] == side)
        terr = self.territory("referee")
        own_tiles = sum(1 for v in terr.values() if v == ("own" if side == "blue" else "enemy"))
        hp = {s: sum(u.hp for u in self.units if u.team == s and u.type != "supply_ship") for s in SIDES}
        sup = self.supply[side]
        pol = homefront.active(self)
        hf = self.home[side] if pol else None
        bars = [
            dict(key="objectives", label="Ports and cities held", value=mine / len(objs), weight=.35 if pol else .4, note=f"{mine} of {len(objs)}"),
            dict(key="territory", label="Land held", value=own_tiles / max(1, len(terr)), weight=.15 if pol else .2, note=f"{int(100 * own_tiles / max(1, len(terr)))}% of the map"),
            dict(key="forces", label="Fighting strength", value=hp[side] / max(1, hp[side] + hp[foe]), weight=.3, note=f"{hp[side]} vs {hp[foe]} hit points"),
            dict(key="supply", label="Fuel and food", value=(sup["fuel"] + sup["food"]) / 200, weight=.1, note=f"fuel {int(sup['fuel'])}%, food {int(sup['food'])}%"),
        ]
        if pol:
            bars.append(dict(key="home", label="Home front", value=(hf["stability"] + hf["economy"] + (100 - hf["corruption"])) / 300, weight=.1,
                             note=f"stability {int(hf['stability'])}, economy {int(hf['economy'])}, corruption {int(hf['corruption'])}"))
        balance = int(round(100 * sum(b["value"] * b["weight"] for b in bars)))
        verdict = "winning" if balance >= 65 else "even" if balance >= 40 else "losing" if balance >= LOST_BELOW else "lost"
        ranked = sorted(bars, key=lambda b: b["value"])
        reasons = []
        if ranked[-1]["value"] >= .55:
            reasons.append(f"Winning on: {ranked[-1]['label'].lower()} ({ranked[-1]['note']}).")
        if ranked[0]["value"] < .45:
            reasons.append(f"Losing on: {ranked[0]['label'].lower()} ({ranked[0]['note']}).")
        crossed = any(u.team == side and u.stats["domain"] == "land" and ((u.c >= self.board.width // 2) if side == "blue" else (u.c < self.board.width // 2)) for u in self.units)
        win = [dict(label="Capture every enemy port and city", done=mine == len(objs) or all(o["owner"] == side for o in objs), note=f"{sum(1 for o in objs if o['owner'] == side)} of {len(objs)} held by us"),
               dict(label="Cross over into the enemy half", done=crossed, note="a land unit is across the centre line" if crossed else "no land unit across yet"),
               dict(label="Or destroy every enemy unit", done=False, note=f"{sum(1 for u in self.units if u.team == foe and u.type != 'supply_ship')} enemy units left"),
               dict(label="Or starve them: cut their supply convoys in the strait", done=False,
                    note=f"enemy fuel/food unknown; ours {int(sup['fuel'])}/{int(sup['food'])}")]
        lose = [dict(label="Enemy takes all our ports and cities", risk=sum(1 for o in objs if o["owner"] == foe) / len(objs), note=f"{sum(1 for o in objs if o['owner'] == foe)} of {len(objs)} already lost"),
                dict(label="Our army is destroyed", risk=1 - hp[side] / max(1, hp[side] + hp[foe]), note=f"{sum(1 for u in self.units if u.team == side and u.type != 'supply_ship')} units left"),
                dict(label="Supplies collapse (convoys blocked)", risk=1 - (sup["fuel"] + sup["food"]) / 200, note=f"orders delayed {self.late(side)} s" if self.late(side) else "orders on time"),
                dict(label="We concede, or use the last resort", risk=1.0 if verdict == "lost" else 0.0, note="available when the war is lost" if verdict == "lost" else "not while the war can be won")]
        return dict(balance=balance, verdict=verdict, bars=[dict(b, pct=int(100 * b["value"])) for b in bars], reasons=reasons, win=win, lose=lose)

    def last_resort_check(self, side, idx):
        """Error text if the General cannot fire this site, else None."""
        if self.winner or self.blast:
            return "It is too late for that."
        if idx < 0 or idx >= len(self.nukes) or self.nuke_level[side].get(idx, 0) < 3:
            return "That site has not been confirmed."
        if self.war_status(side)["balance"] >= LOST_BELOW:
            return "Not while the war can still be won. Hold out, or concede."
        site = self.nukes[idx]
        if not any(u.team == side and manhattan((u.c, u.r), (site["c"], site["r"])) <= 3 for u in self.units):
            return "No crew of ours is within 3 tiles of the silo to arm it."
        return None

    def last_resort(self, side, idx):
        err = self.last_resort_check(side, idx)
        if err:
            self.notice[side] = err
            self.bump()
            return
        site = self.nukes[idx]
        self.blast = dict(at=self.t + NUKE_COUNTDOWN, c=site["c"], r=site["r"], by=side)
        self.say(f"LAST RESORT armed at {ref(site['c'], site['r'])}. Everything within {NUKE_RADIUS} tiles will be ruined in {NUKE_COUNTDOWN} s.")
        agents.radio(self, self.human, "in", "HQ-Radio", f"LAST RESORT armed at {ref(site['c'], site['r'])}. Detonation in {NUKE_COUNTDOWN} s. "
                     f"It cannot be aimed: friend and foe within {NUKE_RADIUS} tiles will be lost.")
        self.bump()

    def _detonate(self):
        b = self.blast
        hit = {s: 0 for s in SIDES}
        for u in self.units:
            if u.hp > 0 and manhattan((u.c, u.r), (b["c"], b["r"])) <= NUKE_RADIUS:
                hit[u.team] += 1
                u.hp = 0
        for c in range(self.board.width):
            for r in range(self.board.height):
                if manhattan((c, r), (b["c"], b["r"])) <= NUKE_RADIUS:
                    if self.board.terrain(c, r) in rules.INFANTRY and (c, r) not in self.objectives:
                        self.board.grid[r][c] = "crater"
                    self.mines.pop((c, r), None)
                    self.effects.append(dict(c=c, r=r, until=self.t + 3))
        self.units = [u for u in self.units if u.hp > 0]
        self.add_sfx("nuke", b["c"], b["r"])
        by, foe = b["by"], OTHER[b["by"]]
        self.blast = None
        self._finish(foe, f"{TEAM_SHORT[by]}'s General fired the last resort and conceded. The blast ruined {hit[by]} of its own units and "
                     f"{hit[foe]} of the enemy's. Defeat, but not in dishonour.", title="Mutual ruin")

    def concede(self, side):
        if not self.winner:
            self._finish(OTHER[side], f"{TEAM_SHORT[side]}'s General conceded the war.", title=f"{TEAM_SHORT[side]} conceded")

    def _check_win(self):
        if self.winner:
            return                                  # already decided (for example by the last resort)
        mid = self.board.width // 2
        goal = levels.check(self)
        if goal:
            return self._finish(goal[0], goal[1])
        if self.t >= self.time_limit:               # time is up: some levels are about holding out, the rest are decided on points
            lim = levels.at_limit(self)
            if lim:
                return self._finish(lim[0], lim[1], title=lim[2])
            bal = self.war_status(self.human)["balance"]
            if bal >= 65:
                return self._finish(self.human, f"Time is up and the war balance is {bal}% in our favour: victory on points.", title="Victory on points")
            if bal <= 35:
                return self._finish("red", f"Time is up and the war balance is only {bal}%: defeat on points.", title="Defeat on points")
            return self._finish("draw", f"Time is up with the war balance at {bal}%: a stalemate.", title="Stalemate")
        for team in SIDES:
            foe = OTHER[team]
            if not any(u.team == foe and u.type != "supply_ship" for u in self.units) and not any(x["team"] == foe for x in self.returning):
                return self._finish(team, f"{TEAM_SHORT[foe]} has no units left.")
            if self.supply[foe]["zero_for"] >= 90:
                return self._finish(team, f"{TEAM_SHORT[foe]}'s army collapsed: no fuel and no food for 90 seconds.")
            if any(o["owner"] == foe for o in self.objectives.values()):
                continue
            crossed = any(u.team == team and u.stats["domain"] == "land" and ((u.c >= mid) if team == "blue" else (u.c < mid)) for u in self.units)
            if crossed:
                return self._finish(team, "Total takeover: every enemy port and city captured, and ground forces crossed over.")

    def _finish(self, team, why, title=None):
        self.winner, self.win_reason = team, why
        n = levels.stars(self, team)
        d = self.decision_stats()
        self.ending = dict(title=title or f"{TEAM_SHORT[team]} wins", text=why, stars=n,
                           level=self.level_id, next_level=self.level_id + 1 if team == self.human and self.level_id + 1 in levels.LEVELS else None,
                           decisions=f"{d['good']} good and {d['bad']} bad decisions" if d["total"] else "no decisions rated")
        campaign.on_finish(self)
        why = self.ending["text"]
        self.say(f"{self.ending['title']}. {why} Rating: {'★' * n}{'☆' * (3 - n)}")

    # ---------- views ----------
    def territory(self, side):
        """{(c, r): 'own' | 'enemy'} for the tiles this side knows. Each tile belongs to whoever holds the nearest
        port or city (as far as this side knows), so capturing an objective flips the land around it."""
        truth = side not in SIDES
        owners = {p: (o["owner"] if truth else self.obj_known[side].get(p)) for p, o in self.objectives.items()}
        me = "blue" if truth else side
        out = {}
        for c in range(self.board.width):
            for r in range(self.board.height):
                if not truth and (c, r) not in self.explored[side]:
                    continue
                nearest = min(owners, key=lambda p: abs(p[0] - c) + abs(p[1] - r))
                out[(c, r)] = "own" if owners[nearest] == me else "enemy"
        return out

    def highlights(self, side):
        """(route tiles, in-range spotted enemy tiles, danger tiles) for the side's selected unit and public blasts."""
        u = self.selected(side)
        route = [(c, r) for c, r, _ in u.path] if u else []
        targets = []
        if u:
            seen = self.detected[side]
            targets = [(e.c, e.r) for e in self.units if e.id in seen and self.reaches(u, e) and rules.can_hit(u, e)]
        danger = {(i["c"] + dc, i["r"] + dr) for i in self.impacts for dc in range(-1, 2) for dr in range(-1, 2)
                  if abs(dc) + abs(dr) <= MISSILE_RADIUS and self.board.inside(i["c"] + dc, i["r"] + dr)
                  and (i["team"] == side or (i["c"], i["r"]) in self.vis[side])}
        if self.blast:
            b = self.blast
            danger |= {(c, r) for c in range(self.board.width) for r in range(self.board.height) if manhattan((c, r), (b["c"], b["r"])) <= NUKE_RADIUS}
        return route, targets, sorted(danger)

    def visible_mines(self, side):
        """Mines this side may see: its own and the enemy ones it has found."""
        if side not in SIDES:
            return list(self.mines)
        return [p for p, o in self.mines.items() if o == side or p in self.mines_known[side]]

    def nuke_markers(self, side):
        """[(c, r, level)] what this side knows about the hidden sites: 2 = approximate area, 3 = confirmed."""
        if side not in SIDES:
            return [(s["c"], s["r"], 3) for s in self.nukes]
        out = []
        for i, site in enumerate(self.nukes):
            lvl = self.nuke_level[side][i]
            if lvl == 3:
                out.append((site["c"], site["r"], 3))
            elif lvl == 2:
                f = self.nuke_fuzzy[(side, i)]
                out.append((f[0], f[1], 2))
        return out

    def actions(self, side, u):
        out = []
        if u.type in airlift.LIFTERS and u.team == side:
            full = len(u.cargo) >= airlift.CAPACITY
            out.append(dict(id="air:load", label="Load nearest troops" if u.type == "transport_helicopter" else "Pick up nearest wounded",
                            enabled=not full, why="full (two aboard)" if full else ""))
            out.append(dict(id="air:extract", label="Extract nearest wounded and fly out", enabled=not full, why="full (two aboard)" if full else ""))
            out.append(dict(id="air:drop", label=f"Drop {len(u.cargo)} aboard at a tile (then click it)", enabled=bool(u.cargo), why="" if u.cargo else "nobody aboard"))
        for kind in ABILITIES.get(u.type, []):
            err, _, _ = self.job_target(side, u, kind)
            out.append(dict(id=kind, label=JOBS[kind][0], enabled=err is None, why=err or ""))
        return out

    def _report_view(self, r):
        """A report with its live combat assessment: what each choice would mean, before the General chooses."""
        brief, info = tactics.report_view(self, r)
        return dict(r, left=max(0, r["expires"] - self.t), brief=brief, options=[dict(o, info=info.get(o["id"], "")) for o in r["options"]])

    def panel(self, side):
        truth = side not in SIDES
        u = None if truth else self.selected(side)
        sel = None
        if u:
            s = u.stats
            sel = dict(id=u.id, label=s["label"], team=TEAM_LABEL[u.team], hp=u.hp, max_hp=u.max_hp, ammo=u.ammo, move=s["move"],
                       range=s["range"], vision=VISION[u.type] + (0 if u.air else rules.sight_bonus(self.board, u.c, u.r)), pos=f"{ref(u.c, u.r)} · {NAMES[self.board.terrain(u.c, u.r)]}",
                       order=self.status(u), actions=self.actions(side, u), mines=u.stock if u.type in ("miner", "minelayer") else None,
                       armed=ATTACK[u.type][0] > 0, ambush=u.ambush, lure=bool(u.lure), callsign=u.callsign, air=u.air, mask=u.mask,
                       fuel=int(100 * u.fuel / u.max_fuel) if u.air else None, vet=u.vet, morale=int(u.morale),
                       cargo=[c.callsign for c in u.cargo], lift=u.type in airlift.LIFTERS)
        owned = {t: sum(1 for o in self.objectives.values() if o["owner"] == t) for t in SIDES}
        me = self.human if truth else side
        sites = []
        if not truth:
            for i, site in enumerate(self.nukes):
                lvl = self.nuke_level[side][i]
                if lvl >= 2:
                    pos = ref(site["c"], site["r"]) if lvl == 3 else ref(*self.nuke_fuzzy[(side, i)]) + " (approximate)"
                    sites.append(dict(idx=i, level=lvl, pos=pos, error=self.last_resort_check(side, i) if lvl == 3 else "Not confirmed yet. Send someone closer."))
        return dict(
            time=fmt_time(self.t), paused=self.paused, speed=self.speed, side=side,
            side_label=TEAM_LABEL.get(side, "Referee (full truth)"),
            units={t: sum(1 for x in self.units if x.team == t and x.type != "supply_ship") for t in SIDES}, objectives=owned,
            objective_total=len(self.objectives), selected=sel, notice=self.notice.get(side, ""),
            spotted=len(self.detected[side]) if not truth else None, contacts=len(self.contacts(side)) if not truth else None,
            log=[f"[{fmt_time(t)}] {m}" for t, m in self.log[-14:]],
            reports=[self._report_view(r) for r in reversed(self.reports)] if not truth else [],
            radio=[dict(e, time=fmt_time(e["t"])) for e in self.radio if e["side"] == side][-40:],
            sfx=self.sfx_for(side), pending=len(self.radio_queue), wind=self.wind_info(),
            ai=dict(mode=self.red_mode, age=(self.t - self.general_at) if self.general_at is not None else None),
            home=homefront.panel(self, me),
            world=world.options(self, me), industry=industry.panel(self, me), autopilot=self.autopilot, occupation=occupation.panel(self, me), timeline=timeline.panel(self), night=self.is_night(), campaign=campaign.panel(self), raid=dict(delivered=raid.delivered(self), total=raid.total(self)) if self.raid else None,
            infil=[dict(label=u.stats["label"], callsign=u.callsign, kind=k, pos=ref(u.c, u.r)) for u, k in world.infiltrators(self, me)] if not truth else [],
            coup=dict(side=self.coup["side"]) if self.coup else None,
            storm=max(0, self.storm_until - self.t) if self.storm_until else 0,
            hazards=[dict(kind="gas", pos=ref(c["c"], c["r"]), left=max(0, c["until"] - self.t)) for c in self.clouds]
                    + [dict(kind="flood", pos=ref(f["c"], f["r"]), left=max(0, (f["hits"] if f["stage"] == "warning" else f["until"]) - self.t), stage=f["stage"]) for f in self.floods],
            rumors=[dict(id=r["id"], text=r["text"], left=max(0, r["expires"] - self.t)) for r in self.rumors if r["side"] == me] if not truth else [],
            resp=dict(answered=self.resp["answered"], missed=self.resp["missed"],
                      avg=round(self.resp["total"] / self.resp["answered"], 1) if self.resp["answered"] else None),
            agents=[dict(id=x.id, callsign=x.callsign, label=x.stats["label"], hp=x.hp, max_hp=x.max_hp, ammo=x.ammo,
                         order=self.status(x), hold=x.hold_fire, pos=ref(x.c, x.r), temperament=x.temperament,
                         fuel=int(100 * x.fuel / x.max_fuel) if x.air else None, mask=x.mask, vet=x.vet, morale=int(x.morale))
                    for x in agents.own_units(self, side)] if not truth else [],
            supply=dict(fuel=int(self.supply[me]["fuel"]), food=int(self.supply[me]["food"]), late=self.late(me),
                        enemy=dict(fuel=int(self.supply[OTHER[me]]["fuel"]), food=int(self.supply[OTHER[me]]["food"])) if truth else None),
            war=self.war_status(me),
            reinforce={k: dict(label=v["label"], left=self.reinf_left[me][k], eta=v["eta"], needs_tile=bool(v["needs_tile"])) for k, v in REINFORCE.items()},
            arrivals=[dict(label=REINFORCE[a["kind"]]["label"], left=max(0, a["at"] - self.t), pos=ref(a["c"], a["r"])) for a in self.arrivals if a["team"] == me],
            sites=sites, blast=dict(left=max(0, self.blast["at"] - self.t), pos=ref(self.blast["c"], self.blast["r"])) if self.blast else None,
            winner=TEAM_LABEL.get(self.winner, "Nobody") if self.winner else None, win_reason=self.win_reason,
            ending=self.ending,
            level=dict(id=self.level_id, name=levels.LEVELS[self.level_id]["name"], briefing=levels.LEVELS[self.level_id]["briefing"],
                       goal=levels.LEVELS[self.level_id]["goal"], inspired=levels.LEVELS[self.level_id]["inspired"],
                       left=max(0, self.time_limit - self.t) if self.time_limit < 10 ** 8 else None,
                       progress=levels.progress(self), all=[dict(id=i, name=lv["name"]) for i, lv in levels.LEVELS.items()]),
            think=dict(left=self.thinking_left(), secs=self.think_secs),
            decisions=[dict(id=d["id"], label=d["label"], callsign=d["callsign"], status=d["status"], why=d["why"])
                       for d in self.decisions[-8:]][::-1],
            decision_stats=self.decision_stats(),
        )

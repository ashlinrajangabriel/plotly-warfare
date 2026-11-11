"""Neighbouring countries: who is friendly to whom, what they will do for a friend, and what happens when they turn hostile.

Four fictional neighbours ring the battlefield. Each one has a relationship (0-100) with Ladooo and with Candooo.
Relations are built with diplomacy, aid and defence sales, drift with how each side's war and government are going,
and an ally (70 or more) will give real help: an airlift of soldiers, shared intelligence, or a volunteer brigade.
A hostile neighbour (under 20) lets militants cross the border into your rear.
"""
from . import agents
from .board import ref as grid
from .units import TEAM_SHORT

OTHER = {"blue": "red", "red": "blue"}
NEIGHBORS = {
    "altheia": dict(name="Altheia", dir="west", rel=dict(blue=70, red=20), blurb="a farming kingdom behind Ladooo"),
    "brevik": dict(name="Brevik", dir="east", rel=dict(blue=20, red=70), blurb="a mining republic behind Candooo"),
    "corvane": dict(name="Corvane", dir="north", rel=dict(blue=45, red=45), blurb="a neutral trading state to the north"),
    "dunmark": dict(name="Dunmark", dir="south", rel=dict(blue=50, red=40), blurb="a naval power on the southern coast"),
}
SUPPORT = {
    "airlift": dict(label="Airlift 2 infantry to our airfield", cd=120, need=70),
    "intel": dict(label="Share intelligence on three enemy units", cd=90, need=70),
    "volunteers": dict(label="Send a volunteer brigade (once)", cd=10 ** 6, need=75),
}
DIPLOMACY = dict(
    diplomacy=dict(label="Diplomacy", cost_econ=2, gain=8, cd=30, note="Talks and visits: relation +8, economy -2."),
    aid=dict(label="Send aid", cost_econ=5, gain=15, cd=45, note="Food and medicine: relation +15, economy -5."),
)


def stance(v):
    return "allied" if v >= 70 else "friendly" if v >= 50 else "cool" if v >= 25 else "hostile"


def setup(game):
    game.world = {nid: dict(rel=dict(n["rel"]), cd={}, used=set()) for nid, n in NEIGHBORS.items()}


def relation(game, nid, side):
    return game.world[nid]["rel"][side]


def allies(game, side):
    return [nid for nid in NEIGHBORS if relation(game, nid, side) >= 70]


def shift(game, nid, side, delta):
    r = game.world[nid]["rel"]
    r[side] = max(0.0, min(100.0, r[side] + delta))
    # a neighbour does not love both sides at once: warming to one cools it a little towards the other
    if delta > 0:
        o = OTHER[side]
        r[o] = max(0.0, r[o] - delta * .25)


def tick(game):
    """Relations drift with how each side is doing; hostile neighbours let militants in."""
    if game.t % 10:
        return
    from . import homefront
    for nid in NEIGHBORS:
        for side in ("blue", "red"):
            if homefront.active(game):
                st = game.home[side]["stability"]
                if st < 30:
                    shift(game, nid, side, -.5)                    # nobody backs a government about to fall
                share = sum(1 for o in game.objectives.values() if o["owner"] == side) / max(1, len(game.objectives))
                if share > .6:
                    shift(game, nid, side, .3)                     # everybody likes a winner
            # a hostile neighbour next to your homeland lets militants through, now and then
            home_dir = "west" if side == "blue" else "east"
            if NEIGHBORS[nid]["dir"] == home_dir and relation(game, nid, side) < 20 and game.t % 90 == 0 and game.t > 0 and not game.winner:
                from . import events
                msg = events.militants_cross(game, side, nid)
                if side == game.human and msg:
                    agents.radio(game, side, "in", "HQ-Radio", msg)


def act(game, side, nid, what):
    """The General (or a minister) deals with a neighbour. Returns the line to report."""
    from . import homefront
    n = NEIGHBORS.get(nid)
    if not n:
        return "Unknown country."
    if game.winner:
        return "The war is over."
    key = (nid, what)
    left = game.world[nid]["cd"].get(what, 0) - game.t
    if left > 0:
        return f"{n['name']}: {DIPLOMACY.get(what, SUPPORT.get(what, {})).get('label', what)} is not ready for {left} sec."
    if what in DIPLOMACY:
        d = DIPLOMACY[what]
        if homefront.active(game):
            game.home[side]["economy"] = max(0, game.home[side]["economy"] - d["cost_econ"])
        game.world[nid]["cd"][what] = game.t + d["cd"]
        shift(game, nid, side, d["gain"])
        return f"{n['name']}: {d['label'].lower()} done. Relation now {int(relation(game, nid, side))} ({stance(relation(game, nid, side))})."
    if what == "sale":
        from . import industry
        return industry.defence_sale(game, side, nid)
    if what in SUPPORT:
        s = SUPPORT[what]
        if relation(game, nid, side) < s["need"]:
            return f"{n['name']} will not do that yet: it needs a relation of {s['need']} (now {int(relation(game, nid, side))})."
        if what in game.world[nid]["used"]:
            return f"{n['name']} has already done that."
        game.world[nid]["cd"][what] = game.t + s["cd"]
        if what == "volunteers":
            game.world[nid]["used"].add(what)
            base = [p for p, o in game.objectives.items() if o["owner"] == side]
            if not base:
                return "We hold no port or city for them to land at."
            c, r = min(base, key=lambda p: abs(p[0] - (4 if side == "blue" else 17)) + abs(p[1] - 7))
            made = []
            for typ in ("tank", "infantry", "infantry"):
                spot = game.free_near(c, r, typ)
                if spot:
                    made.append(game.new_unit(side, typ, *spot))
            return f"{n['name']}'s volunteer brigade has landed at {grid(c, r)}: " + ", ".join(m.callsign for m in made) + "."
        if what == "airlift":
            fields = game.airfields(side)
            if not fields:
                return "We have no airfield to land them on."
            c, r = fields[0]
            made = []
            for _ in range(2):
                spot = game.free_near(c, r, "infantry")
                if spot:
                    made.append(game.new_unit(side, "infantry", *spot))
            return f"{n['name']} airlifted {len(made)} infantry to our airfield at {grid(c, r)}: " + ", ".join(m.callsign for m in made) + "."
        if what == "intel":
            foes = [u for u in game.units if u.team == OTHER[side] and u.hp > 0 and u.type != "supply_ship"]
            game.rng.shuffle(foes)
            for e in foes[:3]:
                game.intel[side][e.id] = dict(type=e.type, team=e.team, c=e.c, r=e.r, seen=game.t)
            return f"{n['name']}'s service shared what it knows: " + "; ".join(f"{e.stats['label'].upper()} AT {grid(e.c, e.r)}" for e in foes[:3]) + "."
    return "Nothing happened."


def options(game, side):
    """For the panel: every neighbour, its stance, and what can be asked of it now."""
    out = []
    spies = any(u.team == side and u.type == "spy" and u.hp > 0 for u in game.units)
    for nid, n in NEIGHBORS.items():
        rel = relation(game, nid, side)
        acts = []
        for key, d in DIPLOMACY.items():
            left = game.world[nid]["cd"].get(key, 0) - game.t
            acts.append(dict(id=key, label=d["label"], note=d["note"], enabled=left <= 0, why=f"ready in {left} s" if left > 0 else ""))
        acts.append(dict(id="sale", label="Defence sale", note="Sell arms from your factories (3 production points): economy +6, relation +10.",
                         enabled=game.industry[side]["ip"] >= 3 and not (game.world[nid]["cd"].get("sale", 0) - game.t > 0),
                         why="needs 3 production points (build factories)" if game.industry[side]["ip"] < 3 else ""))
        for key, s in SUPPORT.items():
            left = game.world[nid]["cd"].get(key, 0) - game.t
            used = key in game.world[nid]["used"]
            acts.append(dict(id=key, label=s["label"], note=f"Needs relation {s['need']}.", enabled=rel >= s["need"] and left <= 0 and not used,
                             why="already done" if used else f"needs relation {s['need']}" if rel < s["need"] else f"ready in {left} s" if left > 0 else ""))
        out.append(dict(id=nid, name=n["name"], dir=n["dir"], blurb=n["blurb"], rel=int(rel), stance=stance(rel),
                        enemy=(int(relation(game, nid, OTHER[side])) if spies else None), actions=acts))
    return out


def map_colors(game, side):
    """(neighbour id -> fill colour) for the strips around the map, by how that neighbour feels about us."""
    out = {}
    for nid in NEIGHBORS:
        s = stance(relation(game, nid, side))
        out[nid] = {"allied": "rgba(46,204,113,.38)", "friendly": "rgba(120,200,120,.26)", "cool": "rgba(160,160,160,.22)", "hostile": "rgba(231,76,60,.38)"}[s]
    return out


CAPITAL = {"blue": (4, 2), "red": (17, 2)}          # the seat of government: where a coup shows


def infiltrators(game, side):
    """Enemy units we can see inside our own half of the map: [(unit, 'militant' | 'military')]."""
    mid = game.board.width // 2
    seen = game.detected[side]
    out = []
    for u in game.units:
        if u.team == OTHER[side] and u.hp > 0 and u.id in seen and ((u.c < mid) if side == "blue" else (u.c >= mid)) and not u.air and u.type != "supply_ship":
            out.append((u, "militant" if u.type in MILITANT else "military"))
    return out


from .units import MILITANT_TYPES as MILITANT  # noqa: E402

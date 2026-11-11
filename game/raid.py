"""The raid: seize two principals (a head of state and a spouse) in the enemy capital and fly them out by helicopter.

The pattern is a famous kind of operation: helicopters carry special forces into a capital compound at night, the guards are
overwhelmed, the principals are detained and flown out before the air defences and reinforcements can react. Here:

  1. Insert commandos with a transport helicopter (Airlift: Load, then Drop beside the principals).
  2. Hold the tile next to a principal for 4 seconds with no enemy armed unit beside them: he is detained and joins us.
  3. Load both principals (a helicopter carries two) and land them at one of our airfields.
"""
from . import agents
from .board import ref as grid

OTHER = {"blue": "red", "red": "blue"}
SPOTS = ((17, 1), (18, 1))                       # near the enemy capital (17, 2)
DETAIN_SECS = 4


def setup(game, lv):
    game.raid = None
    if lv["kind"] != "raid":
        return
    made = []
    for i, (c, r) in enumerate(SPOTS):
        spot = game.free_near(c, r, "vip")
        if spot:
            u = game.new_unit("red", "vip", *spot)
            u.hold_fire = True
            made.append(u.id)
    game.raid = dict(ids=made, grip={}, delivered=set(), lost=False)


def _armed_near(game, v):
    return any(u.team == v.team and u.hp > 0 and u.id != v.id and u.type != "vip"
               and u.type not in ("supply_ship", "medic", "supply_truck", "builder", "digger", "miner")
               and abs(u.c - v.c) + abs(u.r - v.r) <= 1 and not u.air for u in game.units)


def _alarm(game, rd, v):
    """A principal with raiders close by calls for help (guards run to him) and backs away from them."""
    threats = [u for u in game.units if u.team == "blue" and u.hp > 0 and not u.air and u.type != "vip" and abs(u.c - v.c) + abs(u.r - v.r) <= 3]
    if not threats:
        return
    if not rd.get("alarm"):
        rd["alarm"] = game.t
        agents.radio(game, "blue", "in", "HQ-Radio", "ALARM: the principals have called for help. Guards in the capital are converging on them.")
        game.add_sfx("alarm")
    if game.t % 3 == 0:
        for g_ in game.units:
            if g_.team == "red" and g_.hp > 0 and not g_.air and g_.type not in ("vip", "supply_ship", "medic", "supply_truck", "builder", "digger", "miner") \
                    and 1 < abs(g_.c - v.c) + abs(g_.r - v.r) <= 8 and not g_.path and game.t >= rd.get("alarm", 0):
                cands = sorted(((abs(dc) + abs(dr), v.c + dc, v.r + dr) for dc in range(-4, 5) for dr in range(-4, 5)), key=lambda x: x[0])
                for _, cc, rr in cands:
                    if game.board.inside(cc, rr) and not game.unit_at(cc, rr) and (cc, rr) != (g_.c, g_.r) and game.path_for(g_, (cc, rr)):
                        game.order_move("red", g_, cc, rr)
                        break
        if not v.path and v.stats["move"] and min(abs(u.c - v.c) + abs(u.r - v.r) for u in threats) >= 2:    # cornered once they are beside him
            near = min(threats, key=lambda u: abs(u.c - v.c) + abs(u.r - v.r))
            best = None
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                c_, r_ = v.c + dc, v.r + dr
                if game.board.inside(c_, r_) and c_ >= 14 and not game.unit_at(c_, r_) and (c_, r_) not in game.mines:
                    from . import rules
                    if rules.step_cost("vip", game.board.terrain(c_, r_)) is not None:
                        d = abs(c_ - near.c) + abs(r_ - near.r)
                        if best is None or d > best[0]:
                            best = (d, c_, r_)
            if best and best[0] > abs(v.c - near.c) + abs(v.r - near.r):
                game.order_move("red", v, best[1], best[2])


def tick(game):
    rd = getattr(game, "raid", None)
    if not rd or game.winner:
        return
    carried = {c.id for h in game.units for c in h.cargo}
    for vid in rd["ids"]:
        v = game.unit_by_id(vid)
        if v is None:
            if vid not in carried and vid not in rd["delivered"] and not any(u.id == vid for u in game.units):
                rd["lost"] = True
            continue
        if v.team == "red":
            _alarm(game, rd, v)
            captors = [u for u in game.units if u.team == "blue" and u.hp > 0 and u.type in ("commando", "infantry", "spy")
                       and abs(u.c - v.c) + abs(u.r - v.r) <= 1]
            if captors and not _armed_near(game, v):
                rd["grip"][vid] = rd["grip"].get(vid, 0) + 1
                if rd["grip"][vid] >= DETAIN_SECS:
                    v.team = "blue"
                    v.hold_fire = True
                    agents.radio(game, "blue", "in", captors[0].callsign, f"Principal detained at {grid(v.c, v.r)}! Request pick-up, bring the helicopter.")
                    game.add_sfx("chime")
            else:
                rd["grip"][vid] = 0
        elif v.team == "blue" and vid not in rd["delivered"]:
            if any(abs(v.c - f[0]) + abs(v.r - f[1]) <= 2 for f in game.airfields("blue")):
                rd["delivered"].add(vid)
                agents.radio(game, "blue", "in", "HQ-Radio", f"{v.callsign} is safe at our airfield.")


def delivered(game):
    rd = getattr(game, "raid", None)
    return len(rd["delivered"]) if rd else 0


def total(game):
    rd = getattr(game, "raid", None)
    return len(rd["ids"]) if rd else 0

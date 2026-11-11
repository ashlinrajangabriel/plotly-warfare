"""A simple AI General for the Candooo (red) side. It plays by the same rules and the same fog of war as the
human: it only attacks what it has spotted and only knows who holds the objectives it has seen.
(A WebLLM-driven AI General can replace `think` later; the orders it gives are the same.)
"""
import random

from . import airlift, rules
from .units import MISSILE_TYPES

THINK_EVERY = 4     # seconds between decisions
START_AFTER = 8     # seconds before it moves
CALL_LAND_AT = 150  # when it calls its armoured convoy


def _near_free_land(game, u, around):
    """A tile next to `around` that the unit can reach."""
    for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1), (0, 0)):
        c, r = around[0] + dc, around[1] + dr
        if game.board.inside(c, r) and rules.step_cost(u.type, game.board.terrain(c, r)) is not None and not game.unit_at(c, r):
            return c, r
    return None


def _engineer(game, side, u, rnd):
    """Engineers, spies and divers: simple useful jobs."""
    if u.type == "builder" and game.ruined_bridges:
        game.work(side, u.id, "bridge")
    elif u.type == "builder" and any(game.board.terrain(c, r) == "barricade" for r in range(game.board.height) for c in range(game.board.width)):
        game.work(side, u.id, "breach")
    elif u.type == "miner" and u.stock > 0:
        mine_here = [p for p, o in game.objectives.items() if o["owner"] == side]
        if mine_here:
            spot = _near_free_land(game, u, rnd.choice(mine_here))
            if spot and spot not in game.mines:
                game.work(side, u.id, "plant", spot)
    elif u.type == "digger":
        own = [p for p, o in game.objectives.items() if o["owner"] == side]
        if own and "dug" not in u.flags:
            spot = _near_free_land(game, u, rnd.choice(own))
            if spot and game.board.terrain(*spot) in ("plains", "forest", "hills", "coast"):
                u.flags.add("dug")
                game.work(side, u.id, "dig", spot)
    elif u.type in ("diver", "minesweeper") and game.mines_known[side]:
        game.work(side, u.id, "clear")
    elif u.type == "minelayer" and u.stock > 0:
        c, r = rnd.randint(7, 14), rnd.randint(1, game.board.height - 3)
        if rules.step_cost("minelayer", game.board.terrain(c, r)) is not None:
            game.work(side, u.id, "plant", (c, r))


def _air(game, side, u, seen, rnd):
    """Fly strikes and scouting, and go home on low fuel."""
    from . import agents
    if u.type in ("transport_helicopter", "medevac_helicopter") or u.mission or u.plan_air:
        return
    if u.fuel <= .4 * u.max_fuel:
        p = agents.nearest_airfield(game, u)
        if p and (u.c, u.r) != p:
            game.order_move(side, u, *p)
        return
    if (u.c, u.r) in game.airfields(side) and u.fuel < u.max_fuel - 5:
        return                                                  # still refuelling
    if u.type == "uav":
        mid = game.board.width // 2
        game.order_move(side, u, rnd.randint(0, mid - 1), rnd.randint(1, game.board.height - 2))     # scout the human half
        return
    targets = sorted((e for e in seen if rules.can_hit(u, e) and (u.type != "bomber" or not e.air)), key=lambda e: rules.dist(u, e))
    if targets and rules.dist(u, targets[0]) <= 14 and u.ammo > 0:
        game.order_attack(side, u, targets[0])


def _rebel(game, side, u, seen):
    """Rebels sit hidden until sprung, then head for the nearest enemy barracks or training camp."""
    if u.ambush:
        return
    near = [e for e in seen if rules.can_hit(u, e) and rules.dist(u, e) <= 5]
    if near:
        game.order_attack(side, u, min(near, key=lambda e: rules.dist(u, e)))
        return
    sites = [p for p, f in game.facilities.items() if f["owner"] != side]
    if sites:
        game.order_move(side, u, *min(sites, key=lambda p: abs(p[0] - u.c) + abs(p[1] - u.r)))


def think(game, side="red"):
    every = 12 if game.red_mode == "llm" else THINK_EVERY       # a WebLLM General leads; the script only fills the gaps
    if game.t < max(START_AFTER, game.passive_until) or game.t % every:
        return
    rnd = random.Random(game.t)
    if game.t == CALL_LAND_AT:
        game.reinforce(side, "land")
    seen = [game.unit_by_id(i) for i in game.detected[side]]
    seen = [e for e in seen if e]
    targets = [p for p, o in game.objectives.items() if game.obj_known[side].get(p) != side]
    if game.posts and side == "red":                                 # standoff levels: the enemy comes for the ridges
        targets = list(game.posts)
    airlift.ai_step(game, side)
    for u in [x for x in game.units if x.team == side and x.hp > 0]:
        if u.path or u.target_id or u.job or u.plan or u.type == "supply_ship":
            continue
        if u.air:
            _air(game, side, u, seen, rnd)
            continue
        if u.type in ("rebel", "commando"):
            _rebel(game, side, u, seen)
            continue
        if u.type in ("builder", "miner", "digger", "diver", "minesweeper", "minelayer"):
            _engineer(game, side, u, rnd)
            if u.job or u.plan or u.path:
                continue
        if u.stats["move"] == 0 and u.type not in MISSILE_TYPES:
            continue
        if u.type in ("medic", "supply_truck", "anti_air"):
            continue                                       # these work where they stand
        shootable = [e for e in seen if rules.can_hit(u, e) and rules.dist(u, e) <= u.stats["range"]]
        if u.type in MISSILE_TYPES:
            if u.ammo > 0 and shootable:
                # prefer land targets (infantry holding objectives first), then the closest
                best = min(shootable, key=lambda e: (e.stats["domain"] != "land", e.type != "infantry", rules.dist(u, e)))
                game.order_attack(side, u, best)
            continue
        if u.type in ("tank", "infantry", "destroyer", "cruiser", "battleship", "minesweeper", "submarine"):
            nearby = sorted((e for e in seen if rules.can_hit(u, e)), key=lambda e: rules.dist(u, e))
            if nearby and rules.dist(u, nearby[0]) <= 8 and u.type != "infantry":
                game.order_attack(side, u, nearby[0])
                continue
        if u.stats["domain"] == "land" and targets and u.type in ("infantry", "tank", "spy"):
            goal = min(targets, key=lambda p: abs(p[0] - u.c) + abs(p[1] - u.r))
            game.order_move(side, u, *goal)
        elif u.stats["domain"] == "sea" and u.type not in ("submarine", "diver", "minelayer", "minesweeper"):
            c, r = rnd.randint(7, 14), rnd.randint(1, game.board.height - 3)
            game.order_move(side, u, c, r)

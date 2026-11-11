"""Airlift: a transport helicopter carries up to two soldiers, drops them behind the lines, and flies them out again.

  load     fly to a soldier and take him aboard
  drop     fly to a tile and put the cargo down there (an insertion for an offensive, or a reserve for a defence)
  extract  fly to a soldier (any tile, even in the enemy rear), take him aboard, patch him up (+50%), fly home and land him
           at the nearest friendly airfield

A helicopter that is shot down loses everyone aboard. Medevac helicopters do the same job for wounded units only.
"""
from . import agents, rules
from .board import ref
from .units import CARRIED

from .units import CARRIED as CARRIED_ALL  # noqa: E402
CAPACITY = 2
LIFTERS = ("transport_helicopter", "medevac_helicopter")


def lifters(game, side, idle_only=True):
    return [h for h in game.units if h.team == side and h.hp > 0 and h.type in LIFTERS and (not idle_only or not h.plan_air)]


def _soldiers(game, side, near=None, wounded=False):
    out = [u for u in game.units if u.team == side and u.hp > 0 and u.type in CARRIED and u.extract_at is None
           and (not wounded or u.hp < u.max_hp)]
    if near:
        out.sort(key=lambda u: abs(u.c - near.c) + abs(u.r - near.r))
    return out


def command(game, side, heli, kind, c=None, r=None, uid=None):
    """Give a helicopter an airlift job. Returns the line the pilot says (or the refusal)."""
    if heli.type not in LIFTERS:
        return "Only a transport or medevac helicopter can do that, sir."
    if kind in ("load", "extract"):
        if len(heli.cargo) >= CAPACITY:
            return "I am full, sir. Two aboard."
        pool = _soldiers(game, side, heli, wounded=(heli.type == "medevac_helicopter" or kind == "extract" and not uid))
        if uid:
            pool = [u for u in pool if u.id == uid]
        elif c is not None:
            pool = [u for u in pool if (u.c, u.r) == (c, r)] or pool
        if not pool:
            return "I see nobody to pick up, sir."
        s = pool[0]
        heli.plan_air = dict(kind=kind, uid=s.id)
        _fly(game, side, heli, (s.c, s.r))
        return f"{'Extraction' if kind == 'extract' else 'Pick-up'} of {s.callsign} at {ref(s.c, s.r)}. Inbound, ETA {game.eta(heli, heli.path) if heli.path else 0} sec."
    if kind == "drop":
        if not heli.cargo:
            return "Nobody aboard to drop, sir. Load troops first."
        if c is None:
            return "Where do I put them down, sir? Give me a grid reference."
        if rules.step_cost("infantry", game.board.terrain(c, r)) is None:
            return f"{ref(c, r)} is not ground we can land on, sir."
        heli.plan_air = dict(kind="drop", c=c, r=r)
        _fly(game, side, heli, (c, r))
        return f"Dropping {len(heli.cargo)} at {ref(c, r)}, ETA {game.eta(heli, heli.path) if heli.path else 0} sec."
    return "Unknown airlift order."


def _fly(game, side, heli, goal):
    heli.target_id, heli.job, heli.plan, heli.mission = None, None, None, False
    if (heli.c, heli.r) == goal:
        heli.path, heli.dest = [], None
        return
    path = game.path_for(heli, goal, True)
    heli.path, heli.dest = (path or []), goal
    heli.arrive_note = False
    game.delay_orders(side, heli)


def step(game, heli):
    """Called every tick for every helicopter: carry out the pending airlift when it has arrived."""
    plan = heli.plan_air
    if not plan or heli.path:
        return
    side = heli.team
    say = (lambda t: agents.say(game, heli, t, urgent=False)) if side == game.human else (lambda t: None)
    if plan["kind"] in ("load", "extract"):
        s = game.unit_by_id(plan["uid"])
        if not s or s.hp <= 0 or s.team != side:
            heli.plan_air = None
            say("The man I was sent for is gone, sir.")
            return
        if abs(heli.c - s.c) + abs(heli.r - s.r) > 1:
            _fly(game, side, heli, (s.c, s.r))                 # he moved: follow him
            if not heli.path:
                heli.plan_air = None
            return
        game.units.remove(s)
        s.path, s.dest, s.target_id, s.job, s.plan, s.ambush = [], None, None, None, None, False
        heli.cargo.append(s)
        game.sel[side] = None if game.sel.get(side) == s.id else game.sel.get(side)
        if plan["kind"] == "extract":
            s.hp = min(s.max_hp, s.hp + max(1, s.max_hp // 2))
            s.flags.discard("damaged")
            fields = game.airfields(side)
            if fields:
                home = min(fields, key=lambda p: abs(p[0] - heli.c) + abs(p[1] - heli.r))
                heli.plan_air = dict(kind="drop", c=home[0], r=home[1], landing=True)
                _fly(game, side, heli, home)
                say(f"{s.callsign} aboard, patched up to {s.hp}/{s.max_hp}. Flying out to {ref(*home)}.")
                return
        heli.plan_air = None
        say(f"{s.callsign} aboard. {len(heli.cargo)} of {CAPACITY}.")
        return
    if plan["kind"] == "drop":
        if (heli.c, heli.r) != (plan["c"], plan["r"]) and abs(heli.c - plan["c"]) + abs(heli.r - plan["r"]) > 0:
            _fly(game, side, heli, (plan["c"], plan["r"]))
            if not heli.path:
                heli.plan_air = None
            return
        put = []
        for s in list(heli.cargo):
            spot = game.free_near(plan["c"], plan["r"], s.type)
            if spot:
                s.c, s.r = spot
                s.next_step_at = game.t + 2
                game.units.append(s)
                heli.cargo.remove(s)
                put.append(s)
        heli.plan_air = None
        if put:
            if side == game.human:
                agents.say(game, heli, f"{', '.join(p.callsign for p in put)} on the ground at {ref(plan['c'], plan['r'])}. Going home.", urgent=False)
            game.add_sfx("chime") if side == game.human else None
        if not plan.get("landing"):
            heli.mission = True                                   # job done: fly back to the airfield


def lost(game, heli):
    """The helicopter is down: everyone aboard is lost with it."""
    if heli.cargo:
        names = ", ".join(c.callsign for c in heli.cargo)
        game.say(f"{heli.label} went down with {len(heli.cargo)} aboard ({names}).")
        if heli.team == game.human:
            agents.radio(game, heli.team, "in", "HQ-Radio", f"{heli.callsign} is down with {names} aboard. No survivors reported.")
        heli.cargo = []


def ai_step(game, side):
    """A simple airlift for an AI side: pick up two soldiers near an airfield, drop them in the enemy rear, fly home."""
    if game.t % 30 or game.t < 60:
        return
    for h in lifters(game, side):
        if h.type != "transport_helicopter":
            continue
        if h.cargo:
            foe = [p for p, o in game.objectives.items() if o["owner"] != side]
            if foe:
                tgt = min(foe, key=lambda p: abs(p[0] - h.c) + abs(p[1] - h.r))
                spot = game.free_near(tgt[0] + (1 if side == "blue" else -1), tgt[1], "commando")
                if spot:
                    command(game, side, h, "drop", *spot)
                    return
        else:
            fields = game.airfields(side)
            pool = [u for u in _soldiers(game, side, h) if fields and min(abs(u.c - f[0]) + abs(u.r - f[1]) for f in fields) <= 4 and u.type in ("commando", "infantry")]
            if pool and game.rng.random() < .5:
                command(game, side, h, "load", uid=pool[0].id)
                return

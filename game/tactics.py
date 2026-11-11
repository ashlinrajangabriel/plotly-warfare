"""Combat assessment: what a staff officer would tell the General before a decision.

For a contact it works out visibility, the exchange of fire (what we deal, what we take, who lasts longer),
range and the time to get into range, which of our guns can bear on the target, and whether the fire
would be in line or a crossfire. All from the real game state, the same numbers the engine uses.
"""
import math

from . import rules
from .board import ref as grid
from .units import ATTACK, STATS, VISION

AIM_SLOP = .06            # accuracy lost per tile beyond 2 (matches the engine)


def hit_chance(game, dist):
    base = 1.0 if dist <= 2 else max(.55, 1 - AIM_SLOP * (dist - 2))
    return max(.3, base - (.15 if game.storm_until else 0))


def dps(game, a, d, dist=None):
    """Expected damage per second of attacker a on defender d, at the given distance (0 if it cannot hit)."""
    if ATTACK[a.type][0] <= 0 or a.ammo <= 0 or not rules.can_hit(a, d):
        return 0.0
    dist = rules.dist(a, d) if dist is None else dist
    dmg = rules.damage(a, d, game.board) * (1.25 if a.vet else 1.0) * (.6 if a.morale < 30 else 1.0)
    return dmg * hit_chance(game, dist) / max(1, ATTACK[a.type][1])


def eta_to_range(game, u, e):
    """Seconds for u to get within weapon range of e (0 if already in range, None if it cannot)."""
    need = max(0, rules.dist(u, e) - u.stats["range"])
    if need == 0:
        return 0
    if u.stats["move"] == 0:
        return None
    path = game.path_for(u, (e.c, e.r), allow_goal_occupied=True)
    if not path:
        return None
    steps = path[:-1][:need]
    return int(round(sum(c for _, _, c in steps) * rules.secs_per_cost(u) * game.slow(u)))


def bearing(a, b):
    """Compass-style angle (degrees, 0 = east, 90 = south) of b as seen from a."""
    return math.degrees(math.atan2(b.r - a.r, b.c - a.c)) % 360


def spread(angles):
    """Widest angular gap between shooters, as seen from the target: small = in line, large = crossfire."""
    if len(angles) < 2:
        return 0
    return max(min(abs(x - y), 360 - abs(x - y)) for x in angles for y in angles)


def assess(game, side, u, e):
    """Numbers and sentences about u engaging enemy e."""
    foe = e.team
    d = rules.dist(u, e)
    ours, theirs = dps(game, u, e, d), dps(game, e, u, d)
    cover = rules.COVER.get(game.board.terrain(e.c, e.r), 1.0)
    ttk_us = e.hp / ours if ours else None
    ttk_them = u.hp / theirs if theirs else None
    ratio = (ours / max(1, e.hp)) / (theirs / max(1, u.hp)) if ours and theirs else (None if not ours else 99.0)
    eta = eta_to_range(game, u, e)
    friends = [f for f in game.units if f.team == side and f.id != u.id and f.hp > 0 and dps(game, f, e) > 0
               and rules.dist(f, e) <= f.stats["range"] + 2]
    now = [f for f in friends if game.reaches(f, e)]                     # in range AND with a line of sight (or indirect fire)
    los = u.air or e.air or u.type in rules.INDIRECT or rules.has_los(game.board, (u.c, u.r), (e.c, e.r))
    blocked_by = None if los else rules.blocker(game.board, (u.c, u.r), (e.c, e.r))
    enemies = [x for x in game.units if x.team == foe and x.id != e.id and x.hp > 0 and x.id in game.detected[side]
               and dps(game, x, u) > 0 and rules.dist(x, u) <= x.stats["range"] + 2]
    shooters = ([u] if ours else []) + now
    gap = spread([bearing(e, s) for s in shooters])
    geometry = "single line (no crossfire)" if len(shooters) < 2 else ("IN LINE: everything fires from one side" if gap < 45 else
                                                                      f"CROSSFIRE: our guns bear from {int(gap)} degrees apart")
    best = max([u] + friends, key=lambda f: dps(game, f, e), default=u)
    return dict(
        dist=d, ours=ours, theirs=theirs, ratio=ratio, ttk_us=ttk_us, ttk_them=ttk_them, eta=eta, cover=cover,
        seen_by_them=u.id in game.detected[foe], in_range=d <= u.stats["range"], friends=len(friends), now=len(now),
        enemies=len(enemies), geometry=geometry, best=best, gap=gap, los=los, blocked_by=blocked_by,
        high_ground=rules.elevation(game.board, u.c, u.r) - rules.elevation(game.board, e.c, e.r),
    )


def _secs(x):
    return "no route" if x is None else f"{int(round(x))} s"


def contact_lines(game, side, u, e):
    """A short briefing for a contact report."""
    a = assess(game, side, u, e)
    lbl = STATS[e.type]["label"].lower()
    sight = VISION[u.type] - (1 if u.mask else 0)
    cover = "" if a["cover"] >= 1 else f" It is in cover (hits do {int(round((1 - a['cover']) * 100))}% less)."
    lines = [
        f"Visibility: the {lbl} is {a['dist']} tiles away; we see {sight} tiles. "
        + ("It can see us." if a["seen_by_them"] else "It has NOT seen us yet.") + cover,
        f"Exchange: we deal {a['ours']:.1f} damage/s" + (f" (kills it in about {_secs(a['ttk_us'])})" if a["ttk_us"] else " (we cannot hurt it)")
        + f"; it deals {a['theirs']:.1f}/s" + (f" (we last about {_secs(a['ttk_them'])})" if a["ttk_them"] else " (it cannot hurt us)") + ".",
    ]
    if a["ratio"] is not None:
        lines.append(f"Ratio {a['ratio']:.1f} to 1 " + ("in our favour." if a["ratio"] >= 1.2 else "against us." if a["ratio"] < .8 else "even."))
    if a["los"]:
        hg = a["high_ground"]
        lines.append("Line of sight: clear" + (f". We hold the high ground (+{hg:g}): we see further and shoot down at it." if hg > 0
                                                else f". It holds the high ground (+{-hg:g}) over us." if hg < 0 else "."))
    else:
        from .board import ref as _ref
        lines.append(f"Line of sight: BLOCKED by the terrain at {_ref(*a['blocked_by'])}. A direct-fire weapon cannot shoot until we move for a clear view; "
                     "artillery and missiles can still fire on it because it has been spotted.")
    need = max(0, a["dist"] - u.stats["range"])
    lines.append("Reach: " + ("in range now." if a["in_range"] and a["los"] else "in range, but no line of sight." if a["in_range"] else
                              f"must close {need} tile{'s' if need != 1 else ''} first" + (", but there is no route for this unit." if a["eta"] is None else f", about {_secs(a['eta'])}.")))
    lines.append(f"Fire geometry: {a['geometry']}. Our guns that can reach it: {a['now'] + (1 if a['ours'] else 0)} now, {a['friends']} within a short move. "
                 f"Enemy guns that can reach us: {a['enemies'] + (1 if a['theirs'] else 0)}.")
    b = a["best"]
    lines.append(f"Best weapon: {b.callsign} ({STATS[b.type]['label'].lower()}, {dps(game, b, e):.1f} dmg/s, {rules.dist(b, e)} tiles away)"
                 + ("" if b.id != u.id else " (this unit)") + ".")
    return lines, a


def option_info(game, side, u, e, opt, a):
    """One line for one option of a contact report."""
    lbl = STATS[e.type]["label"].lower()
    if opt == "engage":
        verdict = ("Favourable" if a["ratio"] and a["ratio"] >= 1.2 else "Risky" if a["ratio"] and a["ratio"] < .8 else "Even") if a["ratio"] is not None else "No fair fight"
        when = ("fires at once" if a["in_range"] and a["los"] else "is in range but cannot see it: it will move for a clear line first" if a["in_range"]
                else "cannot get in range (no route)" if a["eta"] is None else f"fires in about {_secs(a['eta'])}")
        return f"{verdict}. {u.callsign} {when}; ratio {('%.1f' % a['ratio']) if a['ratio'] is not None else 'n/a'} to 1; {a['geometry'].split(':')[0].lower()}."
    if opt == "hold":
        if a["seen_by_them"]:
            return "It already sees us, so holding fire gives it the first shot."
        eta_them = None
        if e.stats["move"] and a["dist"] > e.stats["range"]:
            eta_them = int(round((a["dist"] - e.stats["range"]) * rules.secs_per_cost(e)))
        return "Unseen so far: we keep the surprise" + (f" (it needs about {eta_them} s to reach firing range if it comes)." if eta_them is not None else ".")
    if opt == "withdraw":
        p = None
        if u.air:
            fields = game.airfields(u.team)
            p = min(fields, key=lambda q: abs(q[0] - u.c) + abs(q[1] - u.r), default=None)
        else:
            from .agents import nearest_own_objective
            p = nearest_own_objective(game, u)
        if not p:
            return "No safe ground known."
        path = game.path_for(u, p)
        eta = game.eta(u, path) if path else None
        chase = int(round(a["dist"] * rules.secs_per_cost(e))) if e.stats["move"] else None
        risk = "it cannot chase" if chase is None else (f"it could catch us in about {chase} s" + (", so we may be caught" if eta and chase < eta else ", we should get clear"))
        return f"Safe ground {grid(*p)}, ETA {_secs(eta)}; {risk}."
    if opt == "scramble":
        jets = [f for f in game.units if f.team == side and f.type == "fighter" and f.hp > 0 and f.ammo > 0]
        if not jets:
            return "No fighter ready."
        f = min(jets, key=lambda m: rules.dist(m, e))
        t = eta_to_range(game, f, e)
        return f"{f.callsign} can be on it in about {_secs(t)} (fuel {int(100 * f.fuel / f.max_fuel)}%); it deals {dps(game, f, e):.1f} dmg/s."
    if opt == "aa_free":
        guns = [g for g in game.units if g.team == side and g.type == "anti_air"]
        near = [g for g in guns if rules.dist(g, e) <= g.stats["range"] + 2]
        return f"{len(near)} of {len(guns)} anti-air batteries can reach it within a short move."
    return ""


def report_view(game, rep):
    """(briefing lines, {option id: one-line consequence}) for a report, recomputed from the live game."""
    u = game.unit_by_id(rep["uid"])
    if not u:
        return [], {}
    kind = rep["kind"]
    e = game.unit_by_id(rep["eid"]) if rep.get("eid") else None
    if kind in ("contact", "airraid") and e:
        lines, a = contact_lines(game, u.team, u, e)
        return lines, {o["id"]: option_info(game, u.team, u, e, o["id"], a) for o in rep["options"]}
    if kind == "damaged":
        info = {}
        near = [x for x in game.units if x.team != u.team and x.id in game.detected[u.team] and rules.dist(x, u) <= x.stats["range"] + 2 and dps(game, x, u) > 0]
        lines = [f"HP {u.hp}/{u.max_hp}. {len(near)} enemy unit{'s' if len(near) != 1 else ''} can still reach us. Morale {int(u.morale)}."]
        for o in rep["options"]:
            if o["id"] == "fallback":
                from .agents import nearest_own_objective
                p = nearest_own_objective(game, u)
                path = game.path_for(u, p) if p else None
                info["fallback"] = f"Safe ground {grid(*p)}, ETA {_secs(game.eta(u, path) if path else None)}; it heals there." if p else "No safe ground known."
            elif o["id"] == "extract":
                info["extract"] = "Pick-up in 20 s with a medevac helicopter, else 45 s. We must hold still and survive until then."
            elif o["id"] == "fight_on":
                info["fight_on"] = "Keeps firing, but at HP %d another hit or two may kill it." % u.hp
        return lines, info
    if kind == "bingo":
        field = min(game.airfields(u.team), key=lambda q: abs(q[0] - u.c) + abs(q[1] - u.r), default=None)
        path = game.path_for(u, field) if field else None
        eta = game.eta(u, path) if path else None
        spare = None if eta is None else int(u.fuel - eta)
        return [f"Fuel {int(100 * u.fuel / u.max_fuel)}% = {int(u.fuel)} s of flight. Base {grid(*field) if field else '?'} is {_secs(eta)} away."
                + ("" if spare is None else f" Spare fuel on arrival: {spare} s." if spare >= 0 else " It will NOT make it home.")], \
            {"rtb": "Lands, refuels and rearms." if spare is None or spare >= 0 else "Too late to make it, but it is the only chance.",
             "press_on": f"About {max(0, int(u.fuel))} s of useful flight left."}
    if kind == "gas":
        cl = rep.get("pos")
        inside = [x for x in game.units if x.team == u.team and not x.air and cl and abs(x.c - cl[0]) + abs(x.r - cl[1]) <= 4]
        return [f"{len(inside)} of our ground units are within 4 tiles of the cloud. Masks stop the damage but slow us by half and cost one tile of sight."], \
            {"masks": "No gas damage; units move 50% slower and see 1 tile less until the all-clear.",
             "evacuate": "Units walk out upwind; no mask penalty, but they are exposed until they are clear."}
    return [], {}

"""Campaign: the sixteen missions played in order as one running story, with consequences carried from war to war.

Acts: I Training (1-4), II Long wars (5-8), III Crises (9-12), IV The shadow war (13-16).
What carries over from a won mission to the next:
  * the neighbours' feelings about each side (40% of the way back to where they began, so a hard-won alliance helps but fades)
  * a point of intelligence for every star
  * the General's record (stars, decisions) shown in the campaign panel
A lost mission is replayed; the campaign goes on only through victories.
"""
from . import levels, world
from .homefront import active as homefront_active

ACTS = ((1, 4, "Act I: Training"), (5, 8, "Act II: Long wars"), (9, 12, "Act III: Crises"), (13, 16, "Act IV: The shadow war"))
LAST = max(levels.LEVELS)


def act(level):
    return next((name for lo, hi, name in ACTS if lo <= level <= hi), "")


def new():
    return dict(on=True, results=[], tries=0)


def start_next(camp, old_game, new_game):
    """Carry the consequences of the war just won into the new game."""
    new_game.campaign = camp
    if old_game is None or old_game.winner != old_game.human or new_game.level_id != old_game.level_id + 1:
        return
    for nid, rel in old_game.world.items():
        base = world.NEIGHBORS[nid]["rel"]
        for side in ("blue", "red"):
            new_game.world[nid]["rel"][side] = round(base[side] + (rel["rel"][side] - base[side]) * .4, 1)
    stars = old_game.ending["stars"] if old_game.ending else 0
    new_game.intel_points["blue"] = min(5.0, new_game.intel_points["blue"] + stars)
    notes = [f"neighbours' feelings (partly)", f"{stars} intelligence point(s)"]
    from . import industry, personas
    extra = min(2, max(0, industry.factories(old_game, "blue") - 1))        # factories we built keep working
    built = 0
    for _ in range(extra):
        site = personas._free_site(new_game, "blue")
        if site:
            new_game.facilities[site] = dict(kind="factory", owner="blue", capturer=None, progress=0, made_at=0)
            new_game.board.grid[site[1]][site[0]] = "factory"
            built += 1
    if built:
        notes.append(f"{built} extra factor{'ies' if built > 1 else 'y'}")
    vets = [u for u in old_game.units if u.team == "blue" and u.vet and u.type in ("infantry", "tank", "artillery", "commando")]
    kinds = [u.type for u in vets][:3] or []
    made = 0
    pool = [u for u in new_game.units if u.team == "blue" and u.type in ("infantry", "tank", "artillery", "commando") and not u.vet]
    for u in pool[:max(len(kinds), min(stars, 3))]:
        u.vet = 1
        u.hp = u.max_hp
        made += 1
    if made:
        notes.append(f"{made} veteran unit(s)")
    settled = sum(1 for s in old_game.settled.values() if s["done"] and s["side"] == "blue")
    if settled and homefront_active(new_game):
        new_game.home["blue"]["economy"] = min(100, new_game.home["blue"]["economy"] + 2 * settled)
        notes.append(f"+{2 * settled} economy from resettled land")
    new_game.say("Campaign: carried over from the last war: " + ", ".join(notes) + ".")


def on_finish(game):
    camp = getattr(game, "campaign", None)
    if not camp or not game.ending:
        return
    won = game.winner == game.human
    camp["tries"] += 1
    if won:
        camp["results"] = [r for r in camp["results"] if r["level"] != game.level_id]
        camp["results"].append(dict(level=game.level_id, name=levels.LEVELS[game.level_id]["name"], stars=game.ending["stars"], title=game.ending["title"]))
        if game.level_id >= LAST:
            game.ending["text"] += f" CAMPAIGN COMPLETE: {sum(r['stars'] for r in camp['results'])} of {3 * LAST} stars."
    else:
        game.ending["text"] += " The campaign goes on only through victory: replay this mission."


def panel(game):
    camp = getattr(game, "campaign", None)
    if not camp:
        return None
    return dict(act=act(game.level_id), level=game.level_id, total=LAST, results=camp["results"],
                stars=sum(r["stars"] for r in camp["results"]), max_stars=3 * LAST, tries=camp["tries"])

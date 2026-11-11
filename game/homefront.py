"""The home front: government stability, the economy (markets) and corruption, and the covert "intelligence" war.

Wars are lost at home as often as in the field. The pattern repeats through history: a long war drains the
treasury, supply failures empty the markets and shops, corruption skims what is left, unrest grows, officers
lose faith in the government, and a coup ends the war from the inside (compare the many coups that followed lost
or stalled wars in the twentieth and twenty-first centuries). The same pressure can be applied to the enemy by
sending intelligence officers to fund an opposition, leak scandals, hit the markets, and, at the right moment,
back a coup.

Everything here is a simple model with named causes, so the General can see why a government is shaking:
  stability  (0-100)  how firmly the government holds; coups happen when it stays very low
  economy    (0-100)  markets, trade and the treasury; the strait's convoys feed it
  corruption (0-100)  skims supplies, slows reinforcements and training, and erodes stability
  unrest     (0-100)  strikes and protests; grows with hardship and corruption, falls with a crackdown or with pay
"""
from . import agents
from .units import TEAM_SHORT

OTHER = {"blue": "red", "red": "blue"}
COUP_BELOW, COUP_SECS = 10, 20          # stability under 10 for 20 s: the government falls
COLLAPSE_BELOW, COLLAPSE_SECS = 5, 45   # economy under 5 for 45 s: the army cannot be paid
INTERNAL = {
    "purge": dict(label="Purge corrupt officers", cd=60, note="Corruption -15, stability -4 for a while, officers resent it."),
    "pay": dict(label="Raise pay and rations", cd=45, note="Economy -6, stability +8, morale +10 on every unit."),
    "crackdown": dict(label="Crack down on protests", cd=45, note="Unrest -20, stability -6, corruption +2."),
}
COVERT = {                                # cost in intelligence points (one per spy per 30 s, at most 5)
    "fund": dict(label="Fund their opposition", cost=1, cd=40, note="Enemy unrest +18, stability -3. 70% works; 25% it is exposed."),
    "leak": dict(label="Leak a corruption scandal", cost=1, cd=40, note="Enemy stability -8, unrest +6. 70% works; 25% exposed."),
    "markets": dict(label="Hit their markets", cost=2, cd=60, note="Enemy economy -10. 70% works; 25% exposed."),
    "coup": dict(label="Back a coup", cost=4, cd=90, note="Works only if their stability is low (best under 30). Failure is exposed: our stability -8."),
}
HEADLINES = {
    "markets_down": "Markets open sharply lower in {n} as supply convoys stall.",
    "markets_up": "Markets recover in {n}: the convoys got through.",
    "protest": "Crowds fill the squares of {n}: bread is short and officials are blamed.",
    "strike": "Dock and rail workers strike in {n}.",
    "scandal": "Newspapers in {n} print the story of officers selling fuel on the black market.",
    "rumour": "Rumours of a coup in {n}: officers met in secret last night. The government denies it.",
    "purge": "{n} dismisses a ring of corrupt officers.",
    "pay": "{n} announces higher pay and rations for the troops.",
    "crackdown": "{n}'s police clear the squares. Dozens are arrested.",
    "fund": "{n} accuses a foreign power of funding its opposition.",
    "exposed": "A foreign intelligence plot against {n} is exposed. Its government cries foul.",
    "coup": "Soldiers surround the ministries of {n}. State television goes dark.",
    "first_shot": "{n} is accused of firing the first shots on the border. Its partners ask for restraint.",
    "plot": "Officers in {n} are said to be plotting to remove the government.",
    "plot_end": "{n}'s government announces that a plot has been dealt with.",
    "refuse": "In {n}, soldiers lower their rifles and refuse to fire on the crowds. The government is in trouble.",
    "sanctions": "New sanctions hit {n}'s trade. Shops report shortages.",
    "escalate50": "Markets in {n} and its rival slide as missiles and air strikes multiply.",
    "escalate100": "The crisis is out of control: governments on both sides are shaken.",
}


def _news(game, key, side):
    game.news.append((game.t, HEADLINES[key].format(n=TEAM_SHORT[side])))
    del game.news[:-30]


def setup(game, lv):
    pol = lv.get("politics")
    game.homefront_on = bool(pol)
    base = pol or dict(blue=(70, 70, 25), red=(70, 70, 30))
    game.home = {s: dict(stability=float(base[s][0]), economy=float(base[s][1]), corruption=float(base[s][2]), unrest=10.0,
                         low_stab=0, low_econ=0, last_econ=float(base[s][1]), warned=set()) for s in ("blue", "red")}
    game.intel_points = {"blue": 2.0, "red": 2.0}
    game.home_cd = {}
    game.news = []
    game.next_red_op = 150
    lv_full = lv
    game.pol_rate = lv_full.get("pol_rate", 1.0)
    game.plots = lv_full.get("plots", False)
    game.refusal = lv_full.get("refusal", False)
    ub, ur = lv_full.get("unrest", (10, 10))
    game.home["blue"]["unrest"], game.home["red"]["unrest"] = float(ub), float(ur)
    game.crackdowns = []
    game.plot_active = False
    game.next_plot = 60
    game.sanction_news = False
    if game.pol_rate > 1:
        game.intel_points = {"blue": 4.0, "red": 3.0}


def active(game):
    return getattr(game, "homefront_on", False)


# ---- numbers the rest of the game uses ----
def cargo(game, side, base):
    """A convoy's cargo after corruption skims it and a weak economy cuts what can be bought."""
    if not active(game):
        return base
    h = game.home[side]
    return max(5, int(round(base * (1 - h["corruption"] / 200) * (.6 + h["economy"] / 250))))


def slowdown(game, side):
    """Seconds added to reinforcement and training times by corruption."""
    return int(game.home[side]["corruption"] / 5) if active(game) else 0


def morale_ceiling(game, side):
    return 100.0 if (not active(game) or game.home[side]["stability"] >= 40) else 40 + game.home[side]["stability"]


# ---- events from the war ----
def on_loss(game, unit):
    """A unit was destroyed: the markets flinch and the public mood sours."""
    if not active(game) or unit.type in ("rebel",):
        return
    h = game.home[unit.team]
    f = game.convoy_econ if unit.type == "supply_ship" else 1.0          # on a trade-route level a lost convoy hurts far more
    h["economy"] = max(0, h["economy"] - (3.0 * f if unit.type == "supply_ship" else .4))
    h["stability"] = max(0, h["stability"] - (1.0 * f if unit.type == "supply_ship" else .3))


def on_capture(game, loser, kind):
    if not active(game):
        return
    h = game.home[loser]
    h["stability"] = max(0, h["stability"] - 4)
    h["economy"] = max(0, h["economy"] - 3)
    h["unrest"] = min(100, h["unrest"] + 6)


def on_convoy(game, side):
    if active(game):
        h = game.home[side]
        h["economy"] = min(100, h["economy"] + 1.0 * game.convoy_econ)


def on_missile(game, team):
    """Missiles and strikes raise the escalation meter on crisis levels; at 50 and 100 both governments feel it."""
    if game.escalation is None or not active(game):
        return
    before = game.escalation
    game.escalation = min(100, game.escalation + 12)
    if before < 50 <= game.escalation:
        for s in ("blue", "red"):
            game.home[s]["economy"] = max(0, game.home[s]["economy"] - 10)
        _news(game, "escalate50", game.human)
        agents.radio(game, game.human, "in", "HQ-Radio", "ESCALATION 50: the markets panic on both sides. Every further missile pushes toward ruin.")
    if before < 100 <= game.escalation:
        for s in ("blue", "red"):
            game.home[s]["stability"] = max(0, game.home[s]["stability"] - 15)
        _news(game, "escalate100", game.human)
        agents.radio(game, game.human, "in", "HQ-Radio", "ESCALATION 100: both governments are shaken. The last resort is within reach of both sides.")
        game.add_sfx("alarm")


# ---- the clock ----
def tick(game):
    if not active(game):
        return
    # intelligence officers produce points
    if game.t % 30 == 0:
        for s in ("blue", "red"):
            spies = sum(1 for u in game.units if u.team == s and u.type == "spy" and u.hp > 0)
            game.intel_points[s] = min(5.0, game.intel_points[s] + spies * 1.0)
    if game.t % 5:
        return
    rate = game.pol_rate
    for s in ("blue", "red"):
        h = game.home[s]
        sanc = game.sanctions.get(s, 0) * 1500                      # sanctions pull the whole economy down, all game long
        if sanc:
            if not game.sanction_news:
                game.sanction_news = True
                _news(game, "sanctions", s)
        sup = game.supply[s]
        supply = (sup["fuel"] + sup["food"]) / 2
        objs = [o for o in game.objectives.values() if o["owner"] == s]
        share = len(objs) / max(1, len(game.objectives))
        mine = [u for u in game.units if u.team == s and u.hp > 0 and not u.air and u.type != "supply_ship"]
        avg_morale = sum(u.morale for u in mine) / len(mine) if mine else 50
        # long wars slowly raise corruption; shortages make it worse
        h["corruption"] = min(100, h["corruption"] + .05 + (.1 if supply < 30 else 0))
        # the economy follows supply, territory and corruption
        target_econ = 15 + .5 * supply + 30 * share - .25 * h["corruption"] - sanc
        h["economy"] += .08 * (target_econ - h["economy"])
        floor = game.narco.get(s, 0)                                # cartel money props the markets up until allied strikes cut it
        if floor and game.strikes[OTHER[s]] < 2:
            h["economy"] = max(h["economy"], float(floor))
        # unrest grows with hardship and corruption, and slowly cools
        rebels = sum(1 for u in game.units if u.team == OTHER[s] and u.type == "rebel" and u.hp > 0)       # a cell in the rear feeds unrest
        h["unrest"] = max(0, min(100, h["unrest"] + (.35 if h["economy"] < 40 else -.15) + (.2 if h["corruption"] > 50 else 0) + .15 * rebels))
        # stability follows the economy, the army's mood, corruption and unrest, minus war weariness
        target_stab = 28 + .4 * h["economy"] + .25 * avg_morale - .35 * h["corruption"] - .25 * h["unrest"]
        h["stability"] = max(0, min(100, h["stability"] + rate * (.06 * (target_stab - h["stability"]) - .03)))
        # headlines when things move
        if h["last_econ"] - h["economy"] > 8:
            _news(game, "markets_down", s)
            h["last_econ"] = h["economy"]
        elif h["economy"] - h["last_econ"] > 8:
            _news(game, "markets_up", s)
            h["last_econ"] = h["economy"]
        if h["unrest"] > 60 and "protest" not in h["warned"]:
            h["warned"].add("protest")
            _news(game, "protest", s)
            h["stability"] = max(0, h["stability"] - 3)
        if h["unrest"] < 40:
            h["warned"].discard("protest")
        if h["stability"] < 25 and "rumour" not in h["warned"]:
            h["warned"].add("rumour")
            _news(game, "rumour", s)
            if s == game.human:
                agents.radio(game, s, "in", "HQ-Radio", "CODE RED, POLITICAL: officers are meeting in secret. Coup rumours in the capital. "
                             "Act on the home front now: purge, raise pay, or crack down.")
                game.add_sfx("alarm")
        if h["stability"] > 40:
            h["warned"].discard("rumour")
        # a government that stays this weak falls
        h["low_stab"] = h["low_stab"] + 5 if h["stability"] < COUP_BELOW else max(0, h["low_stab"] - 5)
        h["low_econ"] = h["low_econ"] + 5 if h["economy"] < COLLAPSE_BELOW else max(0, h["low_econ"] - 5)
        if h["low_stab"] >= COUP_SECS and not game.winner:
            _coup(game, s, "The army turned on the government. The war ends in a coup.", "Coup d'état")
        elif h["low_econ"] >= COLLAPSE_SECS and not game.winner:
            _fall(game, s, "The treasury is empty and the army cannot be paid.", "Economic collapse")
    _red_ops(game)
    _plots(game)


def _plots(game):
    """Officers plot against a government that is weak. The General must deal with it in time (a report with choices)."""
    if not game.plots or game.plot_active or game.winner or game.t < game.next_plot:
        return
    h = game.home[game.human]
    if h["stability"] >= 35:
        return
    mine = [u for u in agents.own_units(game, game.human) if not u.air and u.type != "supply_ship"]
    if not mine:
        return
    game.plot_active = True
    game.next_plot = game.t + 120
    u = max(mine, key=lambda m: m.hp)
    _news(game, "plot", game.human)
    agents.open_report(game, u, "plot", "Sir, I hear senior officers are plotting to remove the government. They have met twice this week.",
                       [dict(id="arrest", label="Arrest the plotters (stability -6, corruption -8, small risk it backfires)"),
                        dict(id="pay_off", label="Pay them off (economy -8, stability +10, corruption +6)")])


def plot_resolve(game, choice):
    """The General's answer to an officers' plot."""
    game.plot_active = False
    h = game.home[game.human]
    _news(game, "plot_end", game.human)
    if choice == "arrest":
        h["stability"] = max(0, h["stability"] - 6)
        h["corruption"] = max(0, h["corruption"] - 8)
        h["unrest"] = min(100, h["unrest"] + 5)
        if game.rng.random() < .2:
            h["stability"] = max(0, h["stability"] - 15)
            return "The arrests split the officer corps: some units refused to obey. Stability fell sharply."
        return "The plotters are under arrest. The corps is quiet, for now."
    h["economy"] = max(0, h["economy"] - 8)
    h["stability"] = min(100, h["stability"] + 10)
    h["corruption"] = min(100, h["corruption"] + 6)
    return "The plotters were bought off. Stability is up, corruption is up, and the treasury is lighter."


def plot_ignored(game):
    game.plot_active = False
    h = game.home[game.human]
    h["stability"] = max(0, h["stability"] - 12)
    _news(game, "plot", game.human)
    agents.radio(game, game.human, "in", "HQ-Radio", "The officers' plot grew while the government did nothing. Stability fell by 12.")


def _coup(game, side, why, title):
    _news(game, "coup", side)
    from . import world
    game.coup = dict(side=side, t=game.t)                       # the map highlights the capital
    game.add_sfx("coup", *world.CAPITAL[side])
    game._finish(OTHER[side], f"{TEAM_SHORT[side]}'s government was overthrown. {why}", title=title)


def _fall(game, side, why, title):
    game._finish(OTHER[side], f"{TEAM_SHORT[side]}'s government fell. {why}", title=title)


def _red_ops(game):
    """Candooo runs its own covert operations against us now and then (more when its own affairs are going well)."""
    if game.t < game.next_red_op or game.winner:
        return
    game.next_red_op = game.t + game.rng.randint(130, 210)
    if not any(u.team == "red" and u.type == "spy" and u.hp > 0 for u in game.units) and game.rng.random() < .5:
        return
    op = game.rng.choice(["fund", "leak", "markets"])
    h = game.home[game.human]
    if game.rng.random() < .3:                              # we caught it
        _news(game, "exposed", "red")
        if game.human:
            agents.radio(game, game.human, "in", "HQ-Radio", "Counter-intelligence caught an enemy agent before he could act.")
        return
    if op == "fund":
        h["unrest"] = min(100, h["unrest"] + 14)
        h["stability"] = max(0, h["stability"] - 2)
        _news(game, "fund", game.human)
    elif op == "leak":
        h["stability"] = max(0, h["stability"] - 6)
        h["unrest"] = min(100, h["unrest"] + 5)
        _news(game, "scandal", game.human)
    else:
        h["economy"] = max(0, h["economy"] - 8)
        _news(game, "markets_down", game.human)
    agents.radio(game, game.human, "in", "HQ-Radio", f"Home front under attack: {game.news[-1][1]}")


# ---- the General's orders ----
def cooldown_left(game, key):
    return max(0, game.home_cd.get(key, 0) - game.t)


def action(game, side, name):
    """Run an internal measure or a covert operation. Returns the line the General hears."""
    if not active(game):
        return "The home front is not in play at this level."
    if game.winner:
        return "The war is over."
    if cooldown_left(game, name):
        return f"{(INTERNAL.get(name) or COVERT.get(name))['label']} is not ready for {cooldown_left(game, name)} sec."
    me, foe = game.home[side], game.home[OTHER[side]]
    if name in INTERNAL:
        game.home_cd[name] = game.t + INTERNAL[name]["cd"]
        if name == "purge":
            me["corruption"] = max(0, me["corruption"] - 15)
            me["stability"] = max(0, me["stability"] - 4)
        elif name == "pay":
            me["economy"] = max(0, me["economy"] - 6)
            me["stability"] = min(100, me["stability"] + 8)
            for u in game.units:
                if u.team == side and not u.air:
                    u.morale = min(100.0, u.morale + 10)
        else:
            me["unrest"] = max(0, me["unrest"] - 20)
            me["stability"] = max(0, me["stability"] - 6)
            me["corruption"] = min(100, me["corruption"] + 2)
            game.crackdowns = [t for t in game.crackdowns if game.t - t < 120] + [game.t]
            if game.refusal and len(game.crackdowns) >= 3:           # the army will not fire on its own people any more
                game.crackdowns = []
                me["stability"] = max(0, me["stability"] - 25)
                for u in game.units:
                    if u.team == side and not u.air:
                        u.morale = max(0.0, u.morale - 20)
                _news(game, "refuse", side)
                game.add_sfx("alarm")
                return "THE ARMY REFUSES. " + game.news[-1][1] + " Stability collapsed."
        _news(game, name, side)
        return game.news[-1][1]
    if name not in COVERT:
        return "Unknown operation."
    op = COVERT[name]
    if game.intel_points[side] < op["cost"]:
        return f"Not enough intelligence points ({game.intel_points[side]:.0f} of {op['cost']}). Each spy in the field adds one every 30 sec."
    game.intel_points[side] -= op["cost"]
    game.home_cd[name] = game.t + op["cd"]
    rng = game.rng
    if name == "coup":
        chance = 0.03 if foe["stability"] >= 40 else min(.9, max(.05, (40 - foe["stability"]) / 60 + foe["unrest"] / 200))
        if rng.random() < chance:
            _coup(game, OTHER[side], "Officers moved with our help. We have no comment.", "Coup d'état")
            return "The coup succeeded."
        me["stability"] = max(0, me["stability"] - 8)
        me["corruption"] = min(100, me["corruption"] + 3)
        _news(game, "exposed", side)
        return f"The coup failed and the plot was exposed ({int(chance * 100)}% chance was all it had). Our stability fell."
    if rng.random() < .25:                                     # exposed: a diplomatic row at home
        me["stability"] = max(0, me["stability"] - 4)
        me["economy"] = max(0, me["economy"] - 2)
        _news(game, "exposed", side)
        return "The operation was exposed and caused a row. Our stability and markets took a hit."
    if name == "fund":
        foe["unrest"] = min(100, foe["unrest"] + 18)
        foe["stability"] = max(0, foe["stability"] - 3)
        _news(game, "fund", OTHER[side])
    elif name == "leak":
        foe["stability"] = max(0, foe["stability"] - 8)
        foe["unrest"] = min(100, foe["unrest"] + 6)
        _news(game, "scandal", OTHER[side])
    else:
        foe["economy"] = max(0, foe["economy"] - 10)
        _news(game, "markets_down", OTHER[side])
    return "Operation succeeded: " + game.news[-1][1]


def panel(game, side):
    """Numbers for the screen. The enemy's are only known (roughly) while we have a spy in the field."""
    if not active(game):
        return dict(on=False)
    foe = OTHER[side]
    mine = {k: int(game.home[side][k]) for k in ("stability", "economy", "corruption", "unrest")}
    spies = any(u.team == side and u.type == "spy" and u.hp > 0 for u in game.units)
    enemy = None
    if spies:
        import random
        rnd = random.Random(game.t // 15)                       # a rough picture that changes slowly, never exact
        enemy = {k: max(0, min(100, int(game.home[foe][k]) + rnd.randint(-5, 5))) for k in ("stability", "economy", "corruption", "unrest")}
    ops = []
    for key, op in {**INTERNAL, **COVERT}.items():
        cost = COVERT.get(key, {}).get("cost", 0)
        why = ""
        if cooldown_left(game, key):
            why = f"ready in {cooldown_left(game, key)} s"
        elif cost > game.intel_points[side]:
            why = f"needs {cost} intelligence points"
        ops.append(dict(id=key, label=op["label"], note=op["note"], cost=cost, covert=key in COVERT, enabled=not why, why=why))
    return dict(on=True, mine=mine, enemy=enemy, spies=spies, points=round(game.intel_points[side], 1), ops=ops,
                news=[f"[{int(t) // 60:02d}:{int(t) % 60:02d}] {m}" for t, m in game.news[-6:]][::-1])

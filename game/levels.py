"""Levels: each one is a mission with a goal, a time limit and a star rating, so a game ends.

Levels 1-4 teach the game and play the full war. Levels 5-12 are scenarios INSPIRED BY patterns from history
(the names of the nations stay fictional: Ladooo against Candooo, and the briefings describe the pattern, not a
real country). Each one has its own rule that changes how you must think:

  5  War of Attrition      trenches, drones, sanctions: wear the enemy down until his home front cracks
  6  Strait Crisis         a chokepoint where shipping, mines and fast boats decide an economy
  7  Eastern Offensive     a huge early advance that must finish before winter, mud and an overstretched supply line
  8  Highland Standoff     a tense border: the side that fires first loses the political argument; hold the ridges
  9  Border Crisis         missiles and air strikes between two armed rivals; escalation can end in ruin
  10 Palace Intrigue       a coup war: spies, money and rumours decide who is still in power
  11 Rebels in the Rear    corruption, a thin army, rebel cells and officers who might take power
  12 Streets and Barracks  mass protests: a crackdown that goes too far makes the army change sides
"""
OTHER = {"blue": "red", "red": "blue"}

DEFAULTS = dict(
    passive_until=8, supply_start=100, hazards=(), barricades=[], extra_red=[], extra_blue=[], trenches=[], mines=[],
    politics=None, winter_at=None, restraint=False, posts=[], convoy_every=70, convoys=None, sanctions={}, escalation=False,
    pol_rate=1.0, plots=False, refusal=False, unrest=(10, 10), convoy_econ=1.0, known_silos=False, kind="standard", inspired="", narco={}, timeline=[], news=[], night=False, daynight=False,
)

LEVELS = {
    1: dict(
        inspired="Inspired by: border skirmishes between small forces probing each other before a war, where a first success or a first mistake sets the tone.",
        name="Skirmish", limit=600, passive_until=90, kind="capture2",
        briefing="A small force each. Learn the controls: scout, spot the enemy, make a trap, take two enemy ports or cities. The enemy holds back for the first 90 seconds.",
        goal="Capture 2 enemy ports or cities",
        keep={"infantry": 2, "tank": 1, "artillery": 1, "destroyer": 1, "cruiser": 1, "builder": 1, "spy": 1, "miner": 1, "diver": 1}),
    2: dict(
        inspired="Inspired by: blockade running and convoy battles, where a narrow sea lane decides who can still feed and fuel itself.",
        name="Strait Control", limit=720, passive_until=30, kind="convoys", convoys=(3, 1),
        briefing="Fuel and food come through the southern strait. Get 3 convoys of yours through and let no more than 1 of theirs reach port. Mines and barricades wait on the causeway.",
        goal="Deliver 3 convoys, allow at most 1 enemy convoy", hazards=("flood",), politics=dict(blue=(70, 70, 25), red=(65, 65, 30)),
        drop={"battleship", "missile_silo", "missile_launcher", "coastal_gun", "bomber", "attack_helicopter", "anti_air"},
        barricades=[(9, 0), (14, 0)]),
    3: dict(
        inspired="Inspired by: total wars between two industrial states, with a causeway front, a sea flank and a home front that must hold.",
        name="Total Takeover", limit=1200,
        briefing="The full war. Capture every enemy port and city and cross over, or break the enemy army. Barricades block the causeway; breach them or go round by sea.",
        goal="Capture every enemy port and city and cross over", hazards=("flood", "gas", "rebels"),
        politics=dict(blue=(70, 70, 25), red=(70, 70, 30)), barricades=[(9, 0), (14, 0)]),
    4: dict(
        inspired="Inspired by: wars that were lost on the ground while leaders weighed desperate options, and the question of how to end them with honour.",
        name="The Last Resort", limit=1500, supply_start=60,
        briefing="The full war against a stronger Candooo, with short supplies. Somewhere on the map are hidden silos. If it is lost, you may still go out in honour.",
        goal="Same as the full war: take it all, or survive", hazards=("flood", "gas", "gas", "rebels", "rebels"),
        politics=dict(blue=(55, 55, 45), red=(70, 70, 30)),
        barricades=[(9, 0), (14, 0)], extra_red=[("tank", 17, 7), ("destroyer", 14, 6), ("infantry", 18, 4)]),
    5: dict(
        news=[(200, "Drones strike a depot far behind the lines. Both sides blame the other.", dict(foe_stab=-2)), (500, "A new round of sanctions is announced. Shops in Candooo report shortages.", dict(foe_stab=-3, foe_econ=-3)), (800, "Casualty figures leak: the public is told less than the truth.", dict(stab=-2))],
        name="War of Attrition", limit=1080, passive_until=30, kind="attrition", supply_start=100,
        inspired="Inspired by: a long modern land war of trenches, mines, drones and artillery, with sanctions biting the economy of the aggressor.",
        briefing="Neither side can break through. Dig in, scout with drones, grind the enemy's units, and watch his home front: sanctions drain Candooo's markets all game long. "
                 "Crack his government (stability under 35, you need a spy to see it) or take 2 of his cities.",
        goal="Take 2 enemy cities, or crack Candooo's home front (stability under 35)", hazards=("flood", "gas"),
        politics=dict(blue=(70, 70, 30), red=(65, 65, 38)), sanctions={"red": .012},
        trenches=[(4, 6), (4, 7), (4, 8), (17, 7), (17, 8), (17, 9)], mines=[(6, 0, "blue"), (15, 0, "red"), (8, 4, "red"), (13, 9, "blue")],
        barricades=[(9, 0), (14, 0)], extra_blue=[("uav", 2, 3), ("artillery", 2, 8), ("anti_air", 2, 6)], extra_red=[("uav", 17, 3), ("artillery", 17, 8), ("anti_air", 17, 6)]),
    6: dict(
        news=[(150, "A tanker is hit by a mine at the mouth of the strait. Insurance rates jump.", dict(econ=-3)), (400, "Neighbours call an emergency meeting on freedom of passage.", dict(rel=("dunmark", 5))), (650, "Fast boats are seen shadowing convoys. Markets wobble.", dict(econ=-2))],
        name="Strait Crisis", limit=900, passive_until=20, kind="convoys", convoys=(4, 1), convoy_every=50, convoy_econ=3.0,
        inspired="Inspired by: tanker wars at a narrow chokepoint, where mines, fast boats and missiles decide whether an economy breathes.",
        briefing="Your economy lives on the ships that pass through the strait. Get 4 convoys through and let at most 1 of theirs through. Mines are everywhere, and Candooo has fast boats and missiles. Every convoy lifts your markets; every loss shakes them.",
        goal="Deliver 4 convoys, allow at most 1 enemy convoy", hazards=("storm", "storm"),
        politics=dict(blue=(70, 60, 25), red=(70, 60, 30)), mines=[(8, 4, "red"), (9, 10, "red"), (13, 10, "blue"), (10, 12, "red"), (11, 12, "blue")],
        drop={"battleship", "missile_silo"}, extra_red=[("destroyer", 12, 9), ("destroyer", 13, 9), ("minelayer", 12, 11), ("missile_launcher", 17, 8)]),
    7: dict(
        daynight=True,
        news=[(120, "Tanks cross the frontier at dawn. Foreign ministers call for calm.", dict(rel=("corvane", -3))), (360, "Mud slows the columns; supply lines stretch.", dict(econ=-2)), (600, "Partisans cut a rail line behind the front.", dict(stab=-2))],
        name="Eastern Offensive", limit=960, winter_at=420,
        inspired="Inspired by: a huge early advance that outran its supply and met mud, frost and a stubborn defence.",
        briefing="You have the stronger army and the first move. Take every enemy port and city and cross over before winter (at 7:00): after that mud and frost slow every ground unit by half and fuel burns faster. A long, thin supply line is your weakness.",
        goal="Capture every enemy port and city before winter bites", supply_start=90, hazards=("flood", "rebels"),
        politics=dict(blue=(70, 70, 25), red=(75, 75, 20)), barricades=[(9, 0), (14, 0)],
        extra_blue=[("tank", 3, 5), ("tank", 3, 7), ("tank", 2, 6), ("infantry", 3, 9), ("infantry", 3, 4)]),
    8: dict(
        news=[(100, "Patrols meet on a high pass. Nobody fires.", dict()), (300, "A shot is heard on the ridge; both sides say it was not theirs.", dict(stab=-2)), (480, "Mediators arrive from a neutral state.", dict(rel=("corvane", 5)))],
        name="Highland Standoff", limit=600, passive_until=120, kind="hold", restraint=True,
        inspired="Inspired by: a tense mountain border where the side that fires first loses the argument in the world's eyes.",
        briefing="Both armies face each other on the ridges. Hold three high posts until the clock runs out. Restraint matters: if you fire first, your government pays for it in stability and markets. Make the enemy fire first, then answer.",
        goal="Hold the three ridge posts for the whole mission", hazards=("storm",), posts=[(1, 5), (3, 5), (2, 12)],
        politics=dict(blue=(75, 75, 20), red=(75, 75, 20)),
        keep={"infantry": 4, "tank": 1, "artillery": 1, "anti_air": 1, "uav": 1, "medic": 1, "supply_truck": 1, "builder": 1, "digger": 1, "spy": 1}),
    9: dict(
        news=[(100, "A missile test is announced by Candooo. Ladooo calls it a provocation.", dict(stab=-1)), (300, "Air raid drills in the capital. Stock markets fall.", dict(econ=-3)), (500, "Both capitals open a hotline.", dict(stab=2))],
        name="Border Crisis", limit=720, passive_until=40, escalation=True, known_silos=True,
        inspired="Inspired by: a sharp crisis between two armed rivals, where missiles and air strikes raise the stakes toward something nobody wants.",
        briefing="Missiles and bombers will decide this, and both sides hold the last resort. Every missile fired raises the escalation: at 50 the markets panic, at 100 both governments shake. Win on points before the clock ends, and do not push the war into ruin.",
        goal="Hold the better war balance when the 12 minutes end", hazards=("storm",),
        politics=dict(blue=(65, 65, 30), red=(65, 65, 30)),
        extra_blue=[("missile_launcher", 2, 8), ("bomber", 0, 3)], extra_red=[("missile_launcher", 18, 8), ("missile_launcher", 17, 5), ("bomber", 19, 3)]),
    10: dict(
        news=[(90, "Whispers in the capital: a general has stopped attending cabinet.", dict(stab=-2)),
              (240, "Foreign newspapers report money moving to opposition groups.", dict(foe_stab=-3)),
              (360, "Tanks are seen near the radio building. The ministry calls it an exercise.", dict(stab=-4))],
        name="Palace Intrigue", limit=480, passive_until=60, kind="coup", pol_rate=2.5, plots=True, supply_start=100,
        inspired="Inspired by: the years of coups and counter-coups in which governments fell to their own officers, one after another.",
        briefing="Armies hardly matter here. Both governments are weak and officers whisper. Your spies earn points: fund the opposition, leak scandals, hit their markets, and strike a coup when their stability is low. But watch your own palace: if officers plot, deal with them in time.",
        goal="Make Candooo's government fall by a coup, and keep yours", politics=dict(blue=(45, 50, 45), red=(40, 45, 50)), unrest=(35, 40),
        keep={"spy": 3, "infantry": 2, "tank": 1, "uav": 1, "medic": 1}, extra_blue=[("spy", 2, 4), ("spy", 2, 5)], extra_red=[("spy", 18, 4)]),
    11: dict(
        daynight=True,
        news=[(120, "Officers complain of unpaid wages in the east.", dict(stab=-2)), (330, "Villagers report armed men on the hill roads at night.", dict()), (560, "A garrison town declares loyalty to nobody.", dict(stab=-3))],
        name="Rebels in the Rear", limit=720, passive_until=30, kind="survive", plots=True,
        inspired="Inspired by: regimes that fought rebels in their own territory with a corrupt, thin army, and fell to officers who lost faith.",
        briefing="Your army is thin and your government is corrupt. Rebel cells keep appearing in your rear and officers might take power. Keep stability above 20 and hold 3 of your 4 ports and cities for twelve minutes.",
        goal="Survive 12 minutes: stability above 20 and 3 of our 4 ports and cities held", hazards=("rebels", "rebels", "rebels", "flood"),
        politics=dict(blue=(50, 45, 55), red=(70, 70, 30)), unrest=(30, 10), drop={"battleship", "bomber", "missile_silo"}),
    12: dict(
        news=[(90, "Crowds gather at the central square.", dict(stab=-1)), (270, "Students and dockworkers march together.", dict(stab=-2)), (450, "A colonel tells reporters his soldiers will not fire on crowds.", dict(stab=-3))],
        name="Streets and Barracks", limit=600, passive_until=60, kind="survive2", refusal=True, plots=True, unrest=(55, 20),
        inspired="Inspired by: mass protests against a government, where an army that will not fire on its own people decides the outcome.",
        briefing="Crowds fill the squares and the economy is shaky. A crackdown calms the streets, but every crackdown also costs trust: three in two minutes and the army refuses to obey, and the government falls. Balance pay, purges and force, and see out the ten minutes.",
        goal="Stay in power for 10 minutes without losing the army", hazards=("rebels",),
        politics=dict(blue=(50, 55, 40), red=(70, 70, 30)), drop={"battleship", "bomber", "missile_silo", "coastal_gun"}),
    13: dict(
        name="The Palace Raid", limit=420, passive_until=40, kind="raid", supply_start=100, night=True,
        inspired="Inspired by: night helicopter raids that seize a head of state and a spouse inside their own capital and fly them out before the air defences wake.",
        briefing="Two principals (the head of state and a spouse) are held in Candooo's capital compound. Fly commandos in with the transport helicopter (Load, then Drop next to them), "
                 "hold the tile beside a principal for 4 seconds with no armed guard next to him to detain him, load both and land them at our airfield. Anti-air and guards are waiting.",
        goal="Detain both principals and land them at our airfield", hazards=(),
        politics=dict(blue=(70, 70, 25), red=(55, 55, 40)),
        extra_blue=[("transport_helicopter", 2, 0), ("commando", 3, 2), ("commando", 3, 3), ("commando", 4, 3), ("attack_helicopter", 1, 2), ("fighter", 2, 3)],
        extra_red=[("anti_air", 16, 2), ("anti_air", 18, 3), ("infantry", 17, 3), ("infantry", 16, 1)],
        drop={"battleship", "missile_silo", "missile_launcher", "bomber", "submarine", "cruiser"}),
    14: dict(
        name="Cartel Money", limit=1200, passive_until=45, kind="cartel", narco={"red": 45},
        inspired="Inspired by: a government whose markets were propped up by drug cartels for years, and later the same cartels named as the reason for allied action against it.",
        briefing="Candooo's markets are kept afloat by cartel money: its economy will not fall below 45 while the cartels are paid. Their enforcers raid your rear. Collect the evidence (spot their cells and commandos), "
                 "designate the enemy as a militant group, then have allies strike twice: that cuts the cartels' money and the markets fall. Crack its home front (stability under 35) or take 2 cities. Allies cool if you designate without evidence.",
        news=[(150, "A cartel boss is photographed at a ministry reception in Candooo. The opposition demands answers.", dict(foe_stab=-3)),
              (420, "Investigators in a neighbouring state publish how cartel money flowed through Candooo's banks for years.", dict(foe_stab=-4, rel=("corvane", 4))),
              (700, "Voters at home ask why allied action is needed. Critics say the cartels were a pretext.", dict(stab=-3))],
        goal="Designate with evidence, strike twice with allies, then crack Candooo's home front or take 2 cities", hazards=("rebels", "rebels", "flood"),
        politics=dict(blue=(65, 65, 30), red=(60, 70, 45)), extra_red=[("commando", 18, 5), ("commando", 18, 9)],
        barricades=[(9, 0), (14, 0)]),
    15: dict(
        name="The Pretext", limit=1100, passive_until=45, kind="pretext", known_silos=False,
        inspired="Inspired by: wars justified by public charges of hidden nuclear weapons and of invasion, where the evidence decided whether the world sided with the accuser or turned on it.",
        briefing="Candooo hides silos somewhere on the map and its units may cross our border. You may accuse it of building nuclear weapons or of invading: with confirmed evidence the world sides with you "
                 "(neighbours warm, sanctions hit Candooo). Without it you are exposed: your government loses face and sanctions fall on you. Find a silo (send spies and units) or catch units in our half before you speak.",
        news=[(120, "Candooo's president tells the world that Ladooo is hiding weapons. Ladooo denies it.", dict(stab=-2)),
              (400, "Inspectors report they found nothing yet, but ask for more time. Neighbours split.", dict(rel=("dunmark", -3))),
              (800, "Newspapers abroad ask whether the charges were ever proved.", dict(stab=-2, foe_stab=-2))],
        goal="Take 2 enemy cities, or crack Candooo's home front (stability under 35)", hazards=("rebels", "gas"),
        politics=dict(blue=(65, 65, 30), red=(65, 65, 35)), barricades=[(9, 0), (14, 0)]),
    16: dict(
        name="The Quiet Test", limit=800, passive_until=60, kind="timeline", supply_start=100,
        timeline=["crash", "successor", "test", "summit", "found_dead"],
        inspired="Inspired by: a secret nuclear test hidden from foreign satellites; a leader and his chief scientists lost in a mountain air crash; a successor who pushed the plan through; "
                 "an assassination attempt at a summit stopped by foreign intelligence; and a leader found dead abroad. The nations are fictional and nothing here claims what really happened.",
        briefing="The story runs on a timeline. Early on the Prime Minister and the chief weapons scientists are lost in an air crash. The successor will order the test: prepare it (90 s) and run the cover story "
                 "whenever a foreign satellite is overhead. Later the Prime Minister goes to a summit: keep friendly neighbours (relation 50+, two of them ideally) so their services warn you. "
                 "After the summit comes a succession crisis. Hold the government together.",
        goal="Carry out the test unseen if you can, survive the summit, and keep the government standing to the end", hazards=("rebels",),
        politics=dict(blue=(65, 65, 30), red=(60, 60, 35)), drop={"battleship", "missile_silo", "missile_launcher", "bomber"}),
}

for _lv in LEVELS.values():                       # fill in defaults so every level has every key
    for _k, _v in DEFAULTS.items():
        _lv.setdefault(_k, _v)


def setup(game):
    """Shape a fresh game for its level: thin out armies, add units, set supplies, barricades, trenches, mines and special rules."""
    lv = LEVELS[game.level_id]
    if "keep" in lv:
        counts, kept = {}, []
        for u in game.units:
            key = (u.team, u.type)
            counts[key] = counts.get(key, 0) + 1
            if counts[key] <= lv["keep"].get(u.type, 0):
                kept.append(u)
        game.units = kept
    if "drop" in lv:
        game.units = [u for u in game.units if u.type not in lv["drop"]]
    for team, extras in (("blue", lv["extra_blue"]), ("red", lv["extra_red"])):
        for typ, c, r in extras:
            spot = game.free_near(c, r, typ)
            if spot:
                game.new_unit(team, typ, *spot)
    for s in ("blue", "red"):
        game.supply[s]["fuel"] = game.supply[s]["food"] = float(lv["supply_start"])
    for c, r in lv["barricades"]:
        game.barricade_under[(c, r)] = game.board.terrain(c, r)
        game.board.grid[r][c] = "barricade"
    for c, r in lv["trenches"]:
        if (c, r) not in game.objectives:
            game.board.grid[r][c] = "trench"
    for c, r, owner in lv["mines"]:
        game.mines[(c, r)] = owner
    game.passive_until = lv["passive_until"]
    game.time_limit = lv["limit"]
    game.winter_at = lv["winter_at"]
    game.winter = False
    game.restraint = lv["restraint"]
    game.posts = list(lv["posts"])
    game.convoy_every = lv["convoy_every"]
    game.convoy_econ = lv["convoy_econ"]
    game.sanctions = dict(lv["sanctions"])
    game.escalation = 0 if lv["escalation"] else None
    game.known_silos = lv["known_silos"]
    game.narco = dict(lv["narco"])


def progress(game):
    """Short text on how the General is doing against this level's goal."""
    lv = LEVELS[game.level_id]
    mid = game.board.width // 2
    taken = sum(1 for p, o in game.objectives.items() if o["owner"] == "blue" and p[0] >= mid)
    total = sum(1 for p in game.objectives if p[0] >= mid)
    kind = lv["kind"]
    if kind == "capture2":
        return f"Enemy ports and cities captured: {taken} of 2"
    if kind == "convoys":
        need, allow = lv["convoys"]
        return f"Our convoys delivered: {game.delivered['blue']} of {need} · enemy convoys through: {game.delivered['red']} (limit {allow})"
    if kind == "attrition":
        return f"Enemy cities captured: {taken} of 2 · enemy home front: use a spy to see how close it is to cracking"
    if kind == "timeline":
        tl = game.tl or {}
        return (f"Test: {'done' if tl.get('tested') else 'not yet'}{' (seen by satellites)' if tl.get('detected') else ''} · summit: {tl.get('summit') or 'not yet'} · "
                f"stability {int(game.home['blue']['stability']) if game.homefront_on else 100}")
    if kind == "raid":
        from . import raid
        rd = game.raid or {}
        det = sum(1 for i in rd.get("ids", []) if (game.unit_by_id(i) and game.unit_by_id(i).team == "blue") or i in rd.get("delivered", ()))
        return f"Principals detained: {det} of {raid.total(game)} · landed safe: {raid.delivered(game)} of {raid.total(game)}"
    if kind in ("cartel", "pretext"):
        return (f"Designated: {'yes' if game.designated['blue'] else 'no'} · ally strikes: {game.strikes['blue']} of 2 · cities taken {taken} of 2 · "
                + ("accusations made: " + str(len([a for a in game.accused if a[0] == 'blue'])) if kind == "pretext" else "enemy markets propped up by cartels until 2 strikes land"))
    if kind == "hold":
        held = sum(1 for p in game.posts if _post_held(game, p))
        return f"Ridge posts held: {held} of {len(game.posts)} · restraint: do not fire first"
    if kind == "coup":
        return "Watch both governments: use spies and intelligence points; a coup in Candooo wins, one in Ladooo loses"
    if kind in ("survive", "survive2"):
        own = sum(1 for p, o in game.objectives.items() if o["owner"] == "blue")
        st = int(game.home["blue"]["stability"]) if game.homefront_on else 100
        return f"Stability {st} · ports and cities held {own} of {sum(1 for p in game.objectives if p[0] < mid)}"
    extra = f" · escalation {game.escalation}/100" if game.escalation is not None else ""
    if game.winter_at:
        extra += " · winter has come" if game.winter else f" · winter in {max(0, game.winter_at - game.t)} s"
    return f"Enemy ports and cities captured: {taken} of {total}{extra}"


def _post_held(game, p):
    near_us = any(u.team == "blue" and u.hp > 0 and abs(u.c - p[0]) + abs(u.r - p[1]) <= 2 for u in game.units)
    near_them = any(u.team == "red" and u.hp > 0 and abs(u.c - p[0]) + abs(u.r - p[1]) <= 1 for u in game.units)
    return near_us and not near_them


def check(game):
    """Win conditions that can end a level at any moment. Returns (winning side, reason) or None."""
    lv = LEVELS[game.level_id]
    mid = game.board.width // 2
    kind = lv["kind"]
    if kind == "raid":
        from . import raid
        if raid.delivered(game) >= raid.total(game) > 0:
            return "blue", "Both principals are on our airfield. The raid was a complete success."
        if game.raid and game.raid["lost"]:
            return "red", "A principal was lost in the raid. The operation failed."
        return None
    if kind in ("capture2", "attrition", "cartel", "pretext"):
        for team in ("blue", "red"):
            n = sum(1 for p, o in game.objectives.items() if o["owner"] == team and ((p[0] >= mid) if team == "blue" else (p[0] < mid)))
            if n >= 2:
                return team, f"{'Ladooo' if team == 'blue' else 'Candooo'} captured two of the enemy's ports or cities."
    if kind in ("attrition", "cartel", "pretext") and game.homefront_on:
        if game.home["red"]["stability"] < 35:
            return "blue", "Sanctions, losses and a long war cracked Candooo's home front: its government sued for peace."
        if game.home["blue"]["stability"] < 35:
            return "red", "The long war cracked Ladooo's home front: its government sued for peace."
    if kind == "convoys":
        need, allow = lv["convoys"]
        if game.delivered["blue"] >= need and game.delivered["red"] <= allow:
            return "blue", f"The strait is ours: {need} convoys through, at most {allow} of theirs."
        if game.delivered["red"] >= need:
            return "red", "Candooo's convoys flowed freely through the strait."
    return None


def at_limit(game):
    """What happens when time runs out, for levels that are about surviving or holding. Returns (team, reason, title) or None."""
    kind = LEVELS[game.level_id]["kind"]
    if kind == "hold":
        held = [p for p in game.posts if _post_held(game, p)]
        if len(held) == len(game.posts):
            return "blue", "All three ridge posts held to the end. The standoff is won without a government paying for it.", "Posts held"
        return "red", f"Only {len(held)} of {len(game.posts)} ridge posts were held when time ran out.", "Posts lost"
    if kind == "survive":
        own = sum(1 for o in game.objectives.values() if o["owner"] == "blue")
        st = game.home["blue"]["stability"]
        if st > 20 and own >= 3:
            return "blue", f"Twelve minutes survived: stability {int(st)}, {own} ports and cities held.", "Survived"
        return "red", f"The regime did not hold: stability {int(st)}, {own} ports and cities left.", "Regime falling"
    if kind == "survive2":
        st = game.home["blue"]["stability"]
        if st >= 15:
            return "blue", f"The government saw out the ten minutes with stability {int(st)} and the army still loyal.", "Held power"
        return "red", f"The government limped to the end with stability {int(st)}, too weak to count as holding.", "Power lost"
    if kind == "timeline":
        from . import timeline
        return timeline.outcome(game)
    if kind == "raid":
        return "red", "Time ran out before both principals were safe. The raid failed.", "Raid failed"
    if kind == "coup":
        return "draw", "No government fell. The intrigue goes on, unresolved.", "Stalemate"
    return None


def stars(game, winner):
    """1 star for winning, +1 for winning fast, +1 for good decisions and a quick General."""
    if winner != "blue":
        return 0
    n = 1
    if game.t <= .7 * game.time_limit:
        n += 1
    d = game.decision_stats()
    if d["total"] >= 3 and d["good"] / d["total"] >= .6 and (d["avg"] or 99) <= 25:
        n += 1
    return n

"""Neighbours, industry, airlift (the third feature round)."""
import unittest

import test_engine
from test_engine import U  # noqa: F401  (also sets NO_LATENCY / NO_EVENTS)

from game import airlift, industry, world
from game.state import Game


def keep(g):
    g.units.append(U("far-red", "infantry", "red", 19, 13))
    g.units.append(U("far-blue", "medic", "blue", 0, 13))
    return g


def fresh(units):
    return keep(test_engine.fresh(units))


def run(g, secs):
    for _ in range(secs):
        g.tick()


class Industry(unittest.TestCase):
    def test_start_with_one_factory_each_and_firepower_grows(self):
        g = Game()
        self.assertEqual(industry.factories(g, "blue"), 1)
        self.assertEqual(industry.factories(g, "red"), 1)
        self.assertEqual(industry.firepower(g, "blue"), 1.0)
        g.facilities[(5, 12)] = dict(kind="factory", owner="blue", capturer=None, progress=0, made_at=0)
        g.facilities[(6, 12)] = dict(kind="factory", owner="blue", capturer=None, progress=0, made_at=0)
        self.assertAlmostEqual(industry.firepower(g, "blue"), 1.12)

    def test_a_builder_builds_a_factory(self):
        g = fresh([U("b", "builder", "blue", 3, 7)])
        g.work("blue", "b", "factory")
        run(g, 30)
        self.assertEqual(industry.factories(g, "blue"), 2)
        self.assertEqual(g.board.terrain(3, 7), "factory")

    def test_production_points_buy_a_unit_and_exports_move_the_economy(self):
        g = fresh([U("b", "infantry", "blue", 3, 3)])
        run(g, 25)
        self.assertGreater(g.industry["blue"]["ip"], 2)
        msg = industry.produce(g, "blue", "infantry")
        self.assertIn("Ordered", msg)
        run(g, industry.PRODUCE_SECS + 2)
        self.assertEqual(sum(1 for u in g.units if u.team == "blue" and u.type == "infantry"), 2)
        g.home["blue"]["economy"] = 50
        industry.set_export(g, "blue", 2)
        run(g, 30)
        self.assertGreater(g.home["blue"]["economy"], 50) if g.homefront_on else None

    def test_defence_sale_warms_a_neighbour(self):
        g = fresh([U("b", "infantry", "blue", 3, 3)])
        g.industry["blue"]["ip"] = 10
        before = world.relation(g, "corvane", "blue")
        industry.defence_sale(g, "blue", "corvane")
        self.assertGreater(world.relation(g, "corvane", "blue"), before)


class Neighbours(unittest.TestCase):
    def test_diplomacy_builds_an_alliance_that_gives_help(self):
        g = fresh([U("b", "infantry", "blue", 3, 3)])
        for i in range(8):
            g.t += 100
            world.act(g, "blue", "corvane", "aid")
        self.assertIn("corvane", world.allies(g, "blue"))
        n = len(g.units)
        world.act(g, "blue", "corvane", "airlift")
        self.assertEqual(len(g.units), n + 2)

    def test_cool_neighbours_refuse_help(self):
        g = fresh([U("b", "infantry", "blue", 3, 3)])
        self.assertIn("will not", world.act(g, "blue", "brevik", "airlift"))

    def test_hostile_neighbour_lets_militants_cross(self):
        g = fresh([U("b", "infantry", "blue", 3, 3)])
        self.assertLess(world.relation(g, "brevik", "red"), 100)
        g.world["altheia"]["rel"]["blue"] = 5
        g.t = 89
        g.tick()                                         # t = 90
        self.assertTrue(any(u.type == "rebel" and u.team == "red" for u in g.units))

    def test_panel_lists_neighbours(self):
        g = Game()
        p = g.panel("blue")
        self.assertEqual({n["id"] for n in p["world"]}, {"altheia", "brevik", "corvane", "dunmark"})
        self.assertEqual(p["industry"]["factories"], 1)


class Airlift(unittest.TestCase):
    def test_load_drop_and_fly_home(self):
        g = fresh([U("h", "transport_helicopter", "blue", 2, 0), U("i", "infantry", "blue", 3, 1), U("j", "commando", "blue", 3, 2)])
        airlift.command(g, "blue", g.unit_by_id("h"), "load", uid="i")
        run(g, 12)
        h = g.unit_by_id("h")
        self.assertEqual(len(h.cargo), 1)
        self.assertIsNone(g.unit_by_id("i"))
        airlift.command(g, "blue", h, "drop", 9, 6)
        self.assertFalse(h.plan_air is None)
        run(g, 45)
        self.assertEqual(len(h.cargo), 0)
        i = g.unit_by_id("i")
        self.assertTrue(i and abs(i.c - 9) + abs(i.r - 6) <= 2)

    def test_extract_heals_and_lands_at_the_airfield(self):
        g = fresh([U("h", "transport_helicopter", "blue", 2, 0), U("i", "infantry", "blue", 10, 6)])
        g.unit_by_id("i").hp = 2
        airlift.command(g, "blue", g.unit_by_id("h"), "extract", uid="i")
        run(g, 60)
        i = g.unit_by_id("i")
        self.assertTrue(i)
        self.assertGreater(i.hp, 2)
        self.assertIn((i.c, i.r), [(1 + dc, 1 + dr) for dc in range(-5, 6) for dr in range(-5, 6)])

    def test_capacity_and_loss(self):
        g = fresh([U("h", "transport_helicopter", "blue", 3, 3), U("a", "infantry", "blue", 3, 3), U("b", "infantry", "blue", 3, 4), U("c", "infantry", "blue", 4, 3)])
        h = g.unit_by_id("h")
        for uid in ("a", "b"):
            airlift.command(g, "blue", h, "load", uid=uid)
            run(g, 6)
        self.assertEqual(len(h.cargo), 2)
        self.assertIn("full", airlift.command(g, "blue", h, "load", uid="c"))
        h.hp = 0
        g.tick()
        self.assertEqual(h.cargo, [])
        self.assertIsNone(g.unit_by_id("a"))

    def test_chat_command_and_ui_action(self):
        g = fresh([U("h", "transport_helicopter", "blue", 2, 0), U("i", "infantry", "blue", 3, 1)])
        g.work("blue", "h", "air:load")
        run(g, 10)
        self.assertEqual(len(g.unit_by_id("h").cargo), 1)
        g.chat("blue", "all", "Mule-1 drop at Echo-6")
        self.assertIsNotNone(g.unit_by_id("h").plan_air)


class Autopilot(unittest.TestCase):
    def test_chat_switches_the_staff_on_and_off(self):
        g = fresh([U("i", "infantry", "blue", 3, 3)])
        g.chat("blue", "all", "AI take over")
        self.assertTrue(g.autopilot)
        self.assertTrue(any(m["who"] == "GENERAL-STAFF" for m in g.radio))
        g.chat("blue", "all", "I take over")
        self.assertFalse(g.autopilot)

    def test_staff_answers_reports_and_moves_units(self):
        g = Game(seed=3)
        g.passive_until = 0
        g.chat("blue", "all", "ai take over")
        for _ in range(240):
            g.tick()
        self.assertTrue(g.autopilot)
        self.assertEqual([r for r in g.reports if g.t - r["t"] > 12], [])          # nothing waits long for the General

    def test_ministers_play_the_economy_and_foreign_policy(self):
        g = Game(seed=5)
        g.passive_until = 0
        g.chat("blue", "all", "AI take over")
        g.industry["blue"]["ip"] = 20
        for _ in range(130):
            g.tick()
            if g.winner:
                break
        moved = sum(1 for n in world.NEIGHBORS if g.world[n]["cd"])
        self.assertGreater(moved, 0)                                                # the foreign minister did something
        self.assertLess(g.industry["blue"]["ip"], 20 + 20)                         # the economy minister spent points


class Display(unittest.TestCase):
    def test_infiltrators_are_told_apart_and_listed(self):
        from ui.figure import build
        g = fresh([U("b", "infantry", "blue", 3, 3), U("m", "rebel", "red", 3, 4), U("k", "commando", "red", 4, 3)])
        g._observe()
        g.detected["blue"] |= {"m", "k"}
        alerts = build(g, "blue", "home")["layout"]["meta"]["alerts"]
        colours = {a["color"] for a in alerts}
        self.assertIn("#ff9f1c", colours)            # militants: orange (dashed)
        self.assertIn("#ff3b30", colours)            # enemy military: red
        self.assertEqual({k for _, k in world.infiltrators(g, "blue")}, {"militant", "military"})
        self.assertEqual(len(g.panel("blue")["infil"]), 2)

    def test_coup_watch_and_coup_highlight(self):
        from ui.figure import build
        g = Game(level=11)
        g.home["blue"]["stability"] = 15
        meta = build(g, "blue", "home")["layout"]["meta"]
        self.assertTrue(any(a["color"] == "#ff3b30" and (a["c"], a["r"]) == world.CAPITAL["blue"] for a in meta["alerts"]))
        from game import homefront
        homefront._coup(g, "blue", "test", "Coup d'état")
        self.assertEqual(g.coup["side"], "blue")
        meta = build(g, "blue", "home")["layout"]["meta"]
        self.assertTrue(any(a["color"] == "#ff2bd6" for a in meta["alerts"]))
        self.assertTrue(any(s["kind"] == "coup" for s in g.sfx))

    def test_neighbours_are_drawn_round_the_map(self):
        from ui.figure import build
        g = Game()
        fig = build(g, "blue", "home")
        self.assertEqual(fig["layout"]["meta"]["M"], 1.5)
        texts = " ".join(a["text"] for a in fig["layout"]["annotations"])
        for name in ("ALTHEIA", "BREVIK", "CORVANE", "DUNMARK"):
            self.assertIn(name, texts)
        self.assertEqual(build(g, "blue", "enemy")["layout"]["meta"]["M"], 0)       # the small intel map stays compact


class Occupation(unittest.TestCase):
    def test_designation_has_costs_and_unlocks_ally_strikes(self):
        from game import occupation
        g = fresh([U("b", "infantry", "blue", 3, 3), U("e", "infantry", "red", 6, 3)])
        before = world.relation(g, "corvane", "blue")
        self.assertIn("pretext", occupation.designate(g, "blue"))               # no militants of theirs in our rear
        self.assertLess(world.relation(g, "corvane", "blue"), before)
        self.assertIn("not an ally", occupation.ally_strike(g, "blue", "corvane"))
        g.world["altheia"]["rel"]["blue"] = 80
        g.detected["blue"].add("e")
        self.assertIn("struck", occupation.ally_strike(g, "blue", "altheia"))
        self.assertIn("not ready", occupation.ally_strike(g, "blue", "altheia"))
        self.assertLess(g.unit_by_id("e").hp, 6)

    def test_justified_designation_is_cheaper(self):
        from game import occupation
        g = fresh([U("b", "infantry", "blue", 3, 3), U("c", "commando", "red", 4, 4)])
        self.assertTrue(occupation.justified(g, "blue"))
        before = world.relation(g, "corvane", "blue")
        occupation.designate(g, "blue")
        self.assertGreater(world.relation(g, "corvane", "blue"), before - 4)

    def test_resettlement_inclusive_vs_forced(self):
        from game import occupation
        g = fresh([U("b", "infantry", "blue", 3, 3)])
        pos = (17, 2)                                                       # an enemy city we now hold
        g.objectives[pos]["owner"] = "blue"
        self.assertEqual(dict(occupation.captured_areas(g, "blue")).keys(), {pos})
        e = U("e", "infantry", "red", 17, 3)
        g.units.append(e)
        self.assertIn("Clear", occupation.resettle(g, "blue", pos, "forced"))
        g.units.remove(e)
        econ = g.home["blue"]["economy"]
        occupation.resettle(g, "blue", pos, "inclusive")
        run(g, 70)
        self.assertGreater(g.home["blue"]["economy"], econ - 3) if g.homefront_on else None
        self.assertTrue(g.settled[pos]["done"])
        pos2 = (17, 12) if (17, 12) in g.objectives else None
        g2 = fresh([U("b", "infantry", "blue", 3, 3)])
        g2.objectives[pos]["owner"] = "blue"
        occupation.resettle(g2, "blue", pos, "forced")
        run(g2, 30)
        self.assertTrue(any(u.type == "rebel" for u in g2.units))             # the displaced took up arms
        self.assertLess(world.relation(g2, "corvane", "blue"), 45)

    def test_losing_the_area_ends_the_settlement(self):
        from game import occupation
        g = fresh([U("b", "infantry", "blue", 3, 3)])
        g.objectives[(17, 2)]["owner"] = "blue"
        occupation.resettle(g, "blue", (17, 2), "inclusive")
        g.objectives[(17, 2)]["owner"] = "red"
        run(g, 10)
        self.assertNotIn((17, 2), g.settled)

    def test_levels_1_to_4_are_framed_by_history(self):
        from game import levels
        for i in (1, 2, 3, 4):
            self.assertTrue(levels.LEVELS[i]["inspired"].startswith("Inspired by"))


class HistoricalLevels(unittest.TestCase):
    def test_raid_detain_extract_and_win(self):
        from game import raid
        g = Game(level=13)
        g.passive_until = 10 ** 9
        self.assertEqual(raid.total(g), 2)
        vips = [g.unit_by_id(i) for i in g.raid["ids"]]
        g.units = [u for u in g.units if u.type == "vip" or u.type in ("transport_helicopter",) and u.team == "blue"]
        g.units.append(U("k", "commando", "blue", vips[0].c, vips[0].r + 1))
        g.units.append(U("k2", "commando", "blue", vips[1].c, vips[1].r + 1))
        g.units.append(U("keep", "infantry", "red", 19, 13))
        for _ in range(6):
            g.tick()
        self.assertTrue(all(v.team == "blue" for v in vips))
        h = next(u for u in g.units if u.type == "transport_helicopter")
        h.c, h.r = vips[0].c, vips[0].r
        for v in vips:
            h.plan_air = None
            airlift.command(g, "blue", h, "load", uid=v.id)
            run(g, 6)
        self.assertEqual(len(h.cargo), 2)
        f = g.airfields("blue")[0]
        airlift.command(g, "blue", h, "drop", *f)
        run(g, 60)
        self.assertEqual(raid.delivered(g), 2)
        self.assertEqual(g.winner, "blue")

    def test_raid_guards_stop_detention_and_losing_a_principal_loses(self):
        g = Game(level=13)
        g.passive_until = 10 ** 9
        vips = [g.unit_by_id(i) for i in g.raid["ids"]]
        g.units.append(U("k", "commando", "blue", vips[0].c, vips[0].r + 1))
        g.units.append(U("guard", "infantry", "red", vips[0].c + 1, vips[0].r))
        for _ in range(8):
            g.tick()
        self.assertEqual(vips[0].team, "red")                                   # a guard beside him: no detention
        vips[1].hp = 0
        g.tick()
        self.assertEqual(g.winner, "red")

    def test_cartel_money_holds_markets_until_two_allied_strikes(self):
        from game import occupation
        g = Game(level=14)
        g.passive_until = 10 ** 9
        g.home["red"]["economy"] = 10
        g.t = 4
        for _ in range(12):
            g.tick()
        self.assertGreaterEqual(g.home["red"]["economy"], 45)
        g.strikes["blue"] = 2
        g.home["red"]["economy"] = 10
        run(g, 12)
        self.assertLess(g.home["red"]["economy"], 45)

    def test_accusations_need_evidence(self):
        from game import occupation
        g = fresh([U("b", "infantry", "blue", 3, 3), U("e", "tank", "red", 5, 5)])
        g.detected["blue"].add("e")
        before = world.relation(g, "corvane", "blue")
        self.assertIn("backed by our evidence", occupation.accuse(g, "blue", "invasion"))
        self.assertGreater(world.relation(g, "corvane", "blue"), before)
        self.assertGreater(g.sanctions["red"], 0)
        st = g.home["blue"]["stability"]
        self.assertIn("exposed", occupation.accuse(g, "blue", "nukes"))         # no confirmed silo
        self.assertLess(g.home["blue"]["stability"], st)
        self.assertGreater(g.sanctions["blue"], 0)
        self.assertIn("already", occupation.accuse(g, "blue", "nukes"))

    def test_new_levels_exist_with_framing(self):
        from game import levels
        for i in (13, 14, 15):
            self.assertTrue(levels.LEVELS[i]["inspired"].startswith("Inspired by"))
            Game(level=i).panel("blue")


class Timeline(unittest.TestCase):
    def play(self, g, until):
        while g.t < until and not g.winner:
            g.tick()

    def test_story_runs_in_order_and_the_test_can_be_hidden(self):
        from game import timeline
        g = Game(level=16)
        g.passive_until = 10 ** 9
        g.units.append(U("far", "infantry", "red", 19, 13))
        self.play(g, 135)
        self.assertIn("crash", g.tl["done"])
        self.assertIn("successor", g.tl["done"])
        rep = next(r for r in g.reports if r["kind"] == "timeline")
        g.choose("blue", rep["id"], "tl:press")
        self.assertEqual(g.tl["stage"], "ordered")
        self.assertIn("begins", timeline.action(g, "blue", "prepare"))
        while g.tl["stage"] == "prep" and g.t < 400:
            if timeline.sat_active(g, 0) or timeline.sat_active(g, 3):
                timeline.action(g, "blue", "cover")
            g.tick()
        self.assertTrue(g.tl["tested"])
        self.assertFalse(g.tl["detected"])

    def test_uncovered_prep_is_seen_by_the_satellite(self):
        from game import timeline
        g = Game(level=16)
        g.passive_until = 10 ** 9
        g.units.append(U("far", "infantry", "red", 19, 13))
        g.tl["stage"] = "prep"
        g.tl["next_sat"] = 0
        g.tl["sat_until"] = 10 ** 6
        self.play(g, g.t + 120)
        self.assertTrue(g.tl["detected"])
        self.assertGreater(g.sanctions["blue"], 0)

    def test_summit_depends_on_friendly_services(self):
        g = Game(level=16)
        g.passive_until = 10 ** 9
        g.units.append(U("far", "infantry", "red", 19, 13))
        for n in g.world.values():
            n["rel"]["blue"] = 10
        g.t = 519
        self.play(g, 521)
        self.assertEqual(g.tl["summit"], "killed")
        g2 = Game(level=16)
        g2.passive_until = 10 ** 9
        g2.units.append(U("far", "infantry", "red", 19, 13))
        for n in g2.world.values():
            n["rel"]["blue"] = 60
        g2.t = 519
        self.play(g2, 521)
        self.assertEqual(g2.tl["summit"], "foiled")

    def test_found_dead_and_outcome(self):
        from game import timeline
        g = Game(level=16)
        g.passive_until = 10 ** 9
        g.units.append(U("far", "infantry", "red", 19, 13))
        g.t = 639
        self.play(g, 641)
        self.assertTrue(g.tl["dead"])
        g.tl["tested"] = True
        g.tl["summit"] = "foiled"
        g.home["blue"]["stability"] = 60
        self.assertEqual(timeline.outcome(g)[0], "blue")
        g.home["blue"]["stability"] = 10
        self.assertEqual(timeline.outcome(g)[0], "red")


class Campaign(unittest.TestCase):
    def test_wins_carry_consequences_and_losses_replay(self):
        from game import campaign
        camp = campaign.new()
        g1 = Game(level=1)
        g1.campaign = camp
        g1.world["corvane"]["rel"]["blue"] = 90
        g1._finish("blue", "test win")
        self.assertEqual(len(camp["results"]), 1)
        self.assertEqual(g1.panel("blue")["campaign"]["act"], "Act I: Training")
        g2 = Game(level=2)
        campaign.start_next(camp, g1, g2)
        self.assertGreater(g2.world["corvane"]["rel"]["blue"], 45)             # a hard-won friendship carries on, partly
        self.assertEqual(g2.campaign, camp)
        g2._finish("red", "test loss")
        self.assertIn("replay", g2.ending["text"])
        self.assertEqual(len(camp["results"]), 1)
        g3 = Game(level=2)
        campaign.start_next(camp, g2, g3)
        self.assertAlmostEqual(g3.world["corvane"]["rel"]["blue"], 45)         # nothing carried from a loss

    def test_last_mission_completes_the_campaign(self):
        from game import campaign
        camp = campaign.new()
        g = Game(level=16)
        g.campaign = camp
        g._finish("blue", "done")
        self.assertIn("CAMPAIGN COMPLETE", g.ending["text"])
        self.assertIsNone(Game().panel("blue")["campaign"])


class Regression(unittest.TestCase):
    def test_every_terrain_has_a_name_so_the_page_never_breaks(self):
        from game.board import CODES, NAMES
        from ui.figure import build
        for t in set(CODES.values()) | {"trench", "camp", "ruins", "river", "crater", "barricade", "bridge"}:
            self.assertIn(t, NAMES)
        g = fresh([U("d", "digger", "blue", 3, 3), U("far", "infantry", "red", 19, 13)])
        g.work("blue", "d", "dig")
        run(g, 15)
        self.assertEqual(g.board.terrain(3, 3), "trench")
        build(g, "blue", "home")
        g.panel("blue")


class GapsClosed(unittest.TestCase):
    def test_campaign_carries_factories_veterans_and_settled_land(self):
        from game import campaign, occupation
        camp = campaign.new()
        g1 = Game(level=3)
        g1.campaign = camp
        for pos in ((5, 12), (6, 12)):
            g1.facilities[pos] = dict(kind="factory", owner="blue", capturer=None, progress=0, made_at=0)
        g1.objectives[(17, 2)]["owner"] = "blue"
        g1.settled[(17, 2)] = dict(side="blue", mode="inclusive", done_at=0, done=True, raids=0, next_raid=0)
        g1._finish("blue", "win")
        g1.ending["stars"] = 3
        g2 = Game(level=4)
        campaign.start_next(camp, g1, g2)
        self.assertEqual(industry.factories(g2, "blue"), 3)
        self.assertGreaterEqual(sum(1 for u in g2.units if u.team == "blue" and u.vet), 3)

    def test_red_designates_accuses_and_calls_allies(self):
        from game import occupation
        g = fresh([U("b", "infantry", "blue", 3, 3), U("r", "infantry", "red", 17, 5), U("far", "infantry", "red", 19, 13)])
        g.passive_until = 0
        g.world["brevik"]["rel"]["red"] = 90
        g.units.append(U("m", "infantry", "blue", 15, 5))         # one of ours inside their half, in sight of their units
        g.t = 400
        for _ in range(60):
            g.tick()
        self.assertTrue(g.designated["red"])
        self.assertGreaterEqual(g.strikes["red"], 1)

    def test_principals_call_for_help_and_back_away(self):
        g = Game(level=13)
        g.passive_until = 10 ** 9
        v = g.unit_by_id(g.raid["ids"][0])
        g.units = [u for u in g.units if u.team == "red" and u.type == "vip"]
        guard = U("guard", "infantry", "red", 17, 7)
        g.units.append(guard)
        g.units.append(U("keep", "infantry", "blue", 0, 13))
        g.units.append(U("k", "commando", "blue", v.c - 2, v.r + 1))
        for _ in range(9):
            g.tick()
        self.assertTrue(g.raid.get("alarm"))
        self.assertTrue(guard.path or (guard.c, guard.r) != (17, 7))             # the guard runs to him

    def test_satellites_follow_orbits_and_the_test_changes_the_war(self):
        from game import timeline
        g = Game(level=16)
        g.units.append(U("far", "infantry", "red", 19, 13))
        g.t = 155
        self.assertTrue(timeline.sat_active(g))
        g.t = 175
        self.assertFalse(timeline.sat_active(g) and not timeline.sat_active(g, 10))   # Eye-1 left, Eye-2 arrives at 180
        fp = industry.firepower(g, "blue")
        timeline._test(g, g.tl)
        self.assertGreater(industry.firepower(g, "blue"), fp)

    def test_scripted_news_and_night(self):
        g = Game(level=14)
        g.passive_until = 10 ** 9
        g.units.append(U("far", "infantry", "red", 19, 13))
        g.t = 149
        g.tick()
        self.assertTrue(any("cartel boss" in m for _, m in g.news))
        raid = Game(level=13)
        self.assertTrue(raid.is_night())
        self.assertFalse(Game(level=3).is_night())
        day, night = Game(level=7), Game(level=7)
        night.t = 130
        self.assertTrue(night.is_night() and not day.is_night())

    def test_a_unit_under_fire_is_suppressed_for_a_moment(self):
        g = fresh([U("t", "tank", "blue", 3, 3), U("far", "infantry", "red", 19, 13)])
        t = g.unit_by_id("t")
        t.ready_at = 0
        g._hit("x", t, 3, "red")
        self.assertGreaterEqual(t.ready_at, g.t + 1)


class LastGaps(unittest.TestCase):
    def test_armour_is_thicker_at_the_front(self):
        from game import rules
        g = fresh([U("t", "tank", "blue", 5, 5), U("a", "tank", "red", 7, 5), U("i", "infantry", "red", 5, 7)])
        t = g.unit_by_id("t")
        t.heading = 0                                              # facing east: the enemy tank is ahead
        front = rules.damage(g.unit_by_id("a"), t, g.board)
        t.heading = 180                                            # turned away: now it is hit from behind
        rear = rules.damage(g.unit_by_id("a"), t, g.board)
        self.assertLess(front, rear)
        inf = g.unit_by_id("i")
        self.assertEqual(rules.facing_factor(g.unit_by_id("a"), inf), 1.0)      # only tanks have armour facing

    def test_sector_commanders_pass_orders_on(self):
        g = fresh([U("a", "tank", "blue", 3, 1), U("b", "tank", "blue", 3, 2), U("c", "tank", "blue", 3, 11), U("far", "infantry", "red", 19, 13)])
        g.chat("blue", "all", "north command hold fire")
        self.assertTrue(g.unit_by_id("a").hold_fire and g.unit_by_id("b").hold_fire)
        self.assertFalse(g.unit_by_id("c").hold_fire)
        self.assertTrue(any(m["who"] == "NORTH-CMD" and "2 of 2" in m["text"] for m in g.radio))

    def test_candooo_tests_in_secret_unless_we_watch_the_site(self):
        from game import timeline
        for watch in (False, True):
            g = Game(level=16)
            g.passive_until = 10 ** 9
            g.units = [u for u in g.units if u.team == "blue"]
            far = U("far", "infantry", "red", 19, 13)
            far.hold_fire = True
            g.units.append(far)
            if watch:
                g.units.append(U("s", "spy", "blue", 18, 12))
            g.t = 299
            while g.t < 392 and not g.winner:
                g.tick()
            self.assertIn("red", g.deterrents)
            self.assertEqual(g.tl["red"]["seen"], watch)
            self.assertGreater(industry.firepower(g, "red"), 1.0)

    def test_more_levels_have_story_headlines(self):
        from game import levels
        for i in (5, 6, 7, 8, 9, 10, 11, 12, 14, 15):
            self.assertTrue(levels.LEVELS[i]["news"], i)


class FallBack(unittest.TestCase):
    def test_every_unit_has_a_route_when_told_to_fall_back(self):
        from game import agents
        g = Game(seed=1, level=3)
        g.passive_until = 10 ** 9
        for u in [x for x in g.units if x.team == "blue" and x.stats["move"] and x.type != "supply_ship"]:
            p = agents.nearest_own_objective(g, u)
            self.assertIsNotNone(p, u.type)
            self.assertTrue((u.c, u.r) == p or g.path_for(u, p) or u.air, f"{u.type} has no route to {p}")

    def test_a_damaged_ship_falls_back_and_heals_beside_the_harbour(self):
        g = fresh([U("s", "submarine", "blue", 7, 8), U("far", "infantry", "red", 19, 13)])
        s = g.unit_by_id("s")
        s.hp = 3
        s.hurt_at = -99
        from game import agents
        self.assertNotIn("No safer", agents.pull_back(g, "blue", s))
        run(g, 80)
        self.assertGreater(s.hp, 3)


class AutopilotActs(unittest.TestCase):
    def test_the_clock_does_not_wait_for_a_human_when_the_staff_plays(self):
        import time
        g = fresh([U("s", "submarine", "blue", 7, 8), U("e", "destroyer", "red", 9, 8), U("far", "infantry", "red", 19, 13)])
        g.chat("blue", "all", "AI take over")
        s = g.unit_by_id("s")
        s.hp = 2
        from game import agents
        agents.open_report(g, s, "damaged", "Heavy damage.", [dict(id="fallback", label="Fall back"), dict(id="fight_on", label="Fight on")])
        self.assertLess(g.think_until, time.monotonic())                      # no think pause was started
        run(g, 4)
        self.assertEqual(g.reports, [])                                       # and the staff answered it
        self.assertTrue(s.path or s.dest or (s.c, s.r) != (7, 8))              # and the unit is actually on the move


if __name__ == "__main__":
    unittest.main()

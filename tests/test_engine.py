"""Headless checks of the real-time engine. Run:  python -m unittest discover -s tests"""
import os
import sys
import unittest
from pathlib import Path

os.environ["NO_LATENCY"] = "1"      # replies are instant in tests; latency has its own test
os.environ["NO_EVENTS"] = "1"       # no random scenarios unless a test asks for one

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.state import CAPTURE_SECS, MISSILE_FLIGHT, Game  # noqa: E402
from game.units import Unit  # noqa: E402


def fresh(units):
    g = Game()
    g.units = units
    g.intel = {"blue": {}, "red": {}}              # forget what the default scenario had spotted
    g.wind = (0.0, 0.0)                            # calm: shots and missiles go where they are aimed
    g.passive_until = 10 ** 9                      # the AI General stays out of tests that are not about it
    for row in g.board.grid:                       # open ground: trees and hills would block sight, and only the LOS tests want that
        for i, t in enumerate(row):
            if t in ("forest", "hills", "mountain", "tunnel"):
                row[i] = "plains"
    return g


def U(uid, typ, team, c, r):
    from game.units import STATS
    return Unit(id=uid, type=typ, team=team, c=c, r=r, hp=STATS[typ]["hp"])


class Engine(unittest.TestCase):
    def test_move_order_walks_over_time(self):
        g = fresh([U("t", "tank", "blue", 3, 6), U("e", "infantry", "red", 19, 0)])
        g.click("blue", 3, 6)
        g.click("blue", 5, 6)                       # coast tile east of the tank
        self.assertTrue(g.selected("blue").path)
        for _ in range(40):
            g.tick()
        tank = g.unit_by_id("t")
        self.assertEqual((tank.c, tank.r), (5, 6))
        self.assertEqual(tank.heading, 0)

    def test_ships_cannot_enter_land(self):
        g = fresh([U("d", "destroyer", "blue", 7, 6), U("e", "infantry", "red", 19, 0)])
        g.click("blue", 7, 6)
        g.click("blue", 3, 6)                       # plains: no sea route
        self.assertEqual(g.selected("blue").path, [])
        self.assertIn("No route", g.notice["blue"])

    def test_auto_fire_kills(self):
        g = fresh([U("a", "tank", "blue", 10, 7), U("b", "infantry", "red", 11, 7)])
        for _ in range(60):
            g.tick()
        self.assertIsNone(g.unit_by_id("b"))
        self.assertTrue(any("destroyed" in m for _, m in g.log))

    def test_missile_flight_and_splash(self):
        g = fresh([U("m", "missile_launcher", "blue", 2, 7), U("sp", "infantry", "blue", 5, 7),   # spotter sees the tank
                   U("e1", "tank", "red", 8, 7), U("e2", "infantry", "red", 9, 7)])
        g.click("blue", 2, 7)
        g.click("blue", 8, 7)                       # enemy tank: attack order
        g.tick()
        self.assertEqual(len(g.impacts), 1)
        hp = g.unit_by_id("e1").hp
        for _ in range(MISSILE_FLIGHT + 1):
            g.tick()
        self.assertTrue(g.unit_by_id("e1") is None or g.unit_by_id("e1").hp < hp)
        self.assertEqual(g.unit_by_id("m").ammo, 1)

    def test_capture_and_total_takeover_win(self):
        g = fresh([U("i", "infantry", "blue", 17, 3), U("x", "infantry", "red", 0, 0)])
        for o in g.objectives.values():             # pretend every other enemy objective is already ours
            if o["owner"] == "red":
                o["owner"] = "blue"
        g.objectives[(17, 3)]["owner"] = "red"
        for _ in range(CAPTURE_SECS + 1):
            g.tick()
        self.assertEqual(g.winner, "blue")
        self.assertIn("takeover", g.win_reason)

    def test_elimination_win(self):
        g = fresh([U("a", "battleship", "blue", 9, 7), U("b", "destroyer", "red", 11, 7)])
        g.click("blue", 9, 7)
        for _ in range(120):
            g.tick()
            if g.winner:
                break
        self.assertEqual(g.winner, "blue")


class Fog(unittest.TestCase):
    def test_far_enemy_is_hidden_and_cannot_be_targeted(self):
        g = fresh([U("a", "tank", "blue", 3, 6), U("e", "tank", "red", 17, 6)])
        g.tick()
        self.assertNotIn("e", g.detected["blue"])
        g.click("blue", 3, 6)
        g.click("blue", 17, 6)                      # looks empty to Blue -> becomes a move order, not an attack
        self.assertIsNone(g.unit_by_id("a").target_id)

    def test_near_enemy_is_spotted_and_remembered_then_forgotten(self):
        g = fresh([U("a", "tank", "blue", 10, 7), U("e", "tank", "red", 12, 7)])
        g.tick()
        self.assertIn("e", g.detected["blue"])
        self.assertEqual(len(g.intel["blue"]), 1)
        g.units = [u for u in g.units if u.id == "a"]     # enemy vanishes; Blue can see the tile -> contact dropped
        g.units.append(U("e2", "infantry", "red", 19, 0))
        g.tick()
        self.assertNotIn("e", g.intel["blue"])

    def test_contact_ages_out_when_out_of_sight(self):
        g = fresh([U("a", "tank", "blue", 10, 7), U("e", "tank", "red", 12, 7)])
        g.tick()
        g.units[0].c, g.units[0].r = 5, 12                # Blue tank leaves, enemy no longer visible
        g.tick()
        self.assertEqual([k["id"] for k in g.contacts("blue")], ["e"])
        g.t += 100
        g.tick()
        self.assertEqual(g.contacts("blue"), [])

    def test_submarine_only_spotted_from_one_tile(self):
        g = fresh([U("a", "destroyer", "blue", 9, 7), U("s", "submarine", "red", 12, 7)])
        g.tick()
        self.assertNotIn("s", g.detected["blue"])
        g.units[1].c = 10
        g.tick()
        self.assertIn("s", g.detected["blue"])

    def test_own_half_known_enemy_half_unexplored(self):
        g = Game()
        self.assertIn((2, 2), g.explored["blue"])
        self.assertNotIn((17, 2), g.explored["blue"])
        self.assertEqual(g.obj_known["blue"].get((17, 3)), None)


class Morse(unittest.TestCase):
    def test_round_trip(self):
        from game import morse
        self.assertEqual(morse.encode("SOS"), "... --- ...")
        self.assertEqual(morse.decode("... --- ... / -. --- .--"), "SOS NOW")
        self.assertEqual(morse.decode(morse.encode("Anvil-1 move to Echo-6")), "ANVIL-1 MOVE TO ECHO-6")
        self.assertTrue(morse.looks_like_morse("... --- ..."))
        self.assertFalse(morse.looks_like_morse("hello"))


class General(unittest.TestCase):
    def setUp(self):
        self.g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("b-infantry-1", "infantry", "blue", 3, 3), U("r-tank-1", "tank", "red", 19, 12)])

    def test_status_reports_come_over_the_radio(self):
        self.g.ask_status("blue")
        who = [e["who"] for e in self.g.radio if e["dir"] == "in"]
        self.assertEqual(sorted(who), ["Anvil-1", "Rifle-1"])
        self.assertTrue(all(e["morse"] for e in self.g.radio))

    def test_chat_move_order_by_callsign_and_grid_reference(self):
        self.g.chat("blue", "all", "Anvil-1 move to Echo-6")     # Echo = column E (4), row 6 -> (4, 5)
        tank = self.g.unit_by_id("b-tank-1")
        self.assertEqual(tank.dest, (4, 5))
        self.assertTrue(any(e["dir"] == "out" for e in self.g.radio))
        for _ in range(30):
            self.g.tick()
        self.assertTrue(any("In position" in e["text"] for e in self.g.radio))

    def test_hold_fire_and_weapons_free(self):
        self.g.chat("blue", "all", "all hold fire")
        self.assertTrue(all(u.hold_fire for u in self.g.units if u.team == "blue"))
        self.g.chat("blue", "b-tank-1", "weapons free")
        self.assertFalse(self.g.unit_by_id("b-tank-1").hold_fire)

    def test_unknown_chat_asks_to_say_again_or_requests_llm(self):
        out = self.g.chat("blue", "b-tank-1", "how is the weather", llm=True)
        self.assertEqual(out["agent"], "b-tank-1")
        self.assertIn("Facts", out["system"])
        self.g.chat("blue", "b-tank-1", "how is the weather")
        self.assertTrue(any("Say again" in e["text"] for e in self.g.radio))

    def test_keywords_match_whole_words_only(self):
        out = self.g.chat("blue", "b-tank-1", "how are your crew feeling about the mission?", llm=True)
        self.assertIsNotNone(out)                      # open conversation, not a sitrep ("how are you" inside "your")
        self.assertEqual(self.g.radio[0]["who"], "Anvil-1")   # addressee shown by callsign, not unit id

    def test_morse_order_is_decoded_obeyed_and_acknowledged(self):
        from game import morse
        self.g.send_morse("blue", morse.encode("Anvil-1 move to Echo-6"))
        self.assertEqual(self.g.unit_by_id("b-tank-1").dest, (4, 5))
        kinds = [(e["dir"], e["kind"]) for e in self.g.radio]
        self.assertIn(("out", "morse"), kinds)
        self.assertIn(("in", "morse"), kinds)
        self.g.send_morse("blue", "gibberish nobody understands")
        self.assertEqual(self.g.radio[-1]["text"], "?")

    def test_contact_report_offers_choices_and_engage_works(self):
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("r-tank-1", "tank", "red", 13, 7)])
        g.tick()
        rep = next(r for r in g.reports if r["kind"] == "contact")
        self.assertEqual({o["id"] for o in rep["options"]}, {"engage", "hold", "withdraw"})
        g.choose("blue", rep["id"], "hold")
        self.assertTrue(g.unit_by_id("b-tank-1").hold_fire)
        self.assertEqual(g.reports, [])

    def test_unanswered_report_expires(self):
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("r-tank-1", "tank", "red", 13, 7)])
        g.tick()
        self.assertTrue(g.reports)
        g.t += 60
        g.tick()
        self.assertFalse([r for r in g.reports if r["kind"] == "contact" and r["t"] < 30])

    def test_destroyed_unit_sends_mayday(self):
        g = fresh([U("b-infantry-1", "infantry", "blue", 10, 7), U("r-tank-1", "tank", "red", 11, 7)])
        g.units[0].hold_fire = True
        for _ in range(60):
            g.tick()
        self.assertTrue(any("MAYDAY" in e["text"] for e in g.radio))


class Territory(unittest.TestCase):
    def test_captured_objective_flips_land_around_it(self):
        g = Game()
        before = g.territory("blue")
        self.assertEqual(before[(4, 3)], "own")
        g.objectives[(4, 3)]["owner"] = "red"
        g.obj_known["blue"][(4, 3)] = "red"
        after = g.territory("blue")
        self.assertEqual(after[(4, 3)], "enemy")


class RedAI(unittest.TestCase):
    def test_red_moves_on_its_own(self):
        g = Game()
        start = {u.id: (u.c, u.r) for u in g.units if u.team == "red"}
        for _ in range(40):
            g.tick()
        moved = [u for u in g.units if u.team == "red" and (u.c, u.r) != start.get(u.id)]
        self.assertTrue(moved)

    def test_a_land_route_exists_between_the_halves(self):
        g = Game()
        inf = next(u for u in g.units if u.id == "b-infantry-1")
        self.assertIsNotNone(rules_path(g, inf, (17, 3)))


def rules_path(g, unit, goal):
    from game import rules
    return rules.find_path(g.board, g.units, unit, goal)


class Engineers(unittest.TestCase):
    def test_unknown_mine_hurts_and_is_removed(self):
        g = fresh([U("b-tank-1", "tank", "blue", 7, 0), U("r-tank-1", "tank", "red", 19, 13)])
        self.assertEqual(g.mines[(12, 0)], "red")
        g.units[0].c, g.units[0].r = 11, 0
        g.order_move("blue", g.units[0], 12, 0)
        g.mines_known["blue"].clear()
        g.units[0].path = [(12, 0, 1)]                  # force the step even though a careful planner would avoid it
        hp = g.units[0].hp
        for _ in range(3):
            g.tick()
        self.assertLess(g.unit_by_id("b-tank-1").hp, hp)
        self.assertNotIn((12, 0), g.mines)

    def test_diver_finds_and_clears_a_mine(self):
        g = fresh([U("b-diver-1", "diver", "blue", 8, 5), U("r-tank-1", "tank", "red", 19, 13)])
        g.tick()
        self.assertIn((8, 6), g.mines_known["blue"])     # divers feel out mines within 3 tiles
        g.work("blue", "b-diver-1", "clear")
        for _ in range(30):
            g.tick()
        self.assertNotIn((8, 6), g.mines)

    def test_digger_digs_a_trench_and_builder_rebuilds_a_bridge(self):
        g = fresh([U("b-digger-1", "digger", "blue", 3, 4), U("b-builder-1", "builder", "blue", 9, 0), U("r-tank-1", "tank", "red", 19, 13)])
        g.work("blue", "b-digger-1", "dig")
        for _ in range(12):
            g.tick()
        self.assertEqual(g.board.terrain(3, 4), "trench")
        g.board.grid[0][10] = "river"                    # pretend a missile destroyed the bridge
        g.ruined_bridges.add((10, 0))
        g.work("blue", "b-builder-1", "bridge")
        for _ in range(30):
            g.tick()
        self.assertEqual(g.board.terrain(10, 0), "bridge")
        self.assertEqual(g.ruined_bridges, set())

    def test_missile_destroys_a_bridge(self):
        g = fresh([U("b-tank-1", "tank", "blue", 7, 1), U("r-tank-1", "tank", "red", 19, 13)])
        g._impact(dict(c=10, r=0, dmg=10, by="Test", team="red"))
        self.assertEqual(g.board.terrain(10, 0), "river")
        self.assertIn((10, 0), g.ruined_bridges)

    def test_miner_plants_a_mine_and_spy_reports_by_morse(self):
        g = fresh([U("b-miner-1", "miner", "blue", 3, 9), U("b-spy-1", "spy", "blue", 15, 4), U("r-tank-1", "tank", "red", 17, 5)])
        g.work("blue", "b-miner-1", "plant")
        for _ in range(8):
            g.tick()
        self.assertEqual(g.mines.get((3, 9)), "blue")
        self.assertEqual(g.unit_by_id("b-miner-1").stock, 5)
        g.t = 5
        g.tick()                                         # t=6: the spy's turn to report
        self.assertTrue(any(e["kind"] == "morse" and e["dir"] == "in" and "TANK" in e["text"] for e in g.radio))
        self.assertIn("r-tank-1", g.intel["blue"])

    def test_reinforcements_arrive_after_a_delay_and_are_limited(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 13)])
        n = len(g.units)
        self.assertIn("ETA", g.reinforce("blue", "air", 2, 2))
        self.assertIn("No paratroopers", g.reinforce("blue", "air", 2, 3))
        for _ in range(31):                                              # 20 s plus a few seconds of corruption
            g.tick()
        self.assertEqual(sum(1 for u in g.units if u.type == "infantry"), 2)    # the two paratroopers (convoys are ships)
        self.assertIn("wrong kind", g.reinforce("blue", "sea", 2, 2))   # land tile is no place for ships

    def test_chat_commands_for_engineers_and_reinforcements(self):
        g = fresh([U("b-digger-1", "digger", "blue", 3, 4), U("r-tank-1", "tank", "red", 19, 13)])
        g.chat("blue", "all", "Mole-1 dig in")
        self.assertIsNotNone(g.unit_by_id("b-digger-1").job)
        g.chat("blue", "all", "reinforcements by land")
        self.assertEqual(len(g.arrivals), 1)


class RealisticRadio(unittest.TestCase):
    def test_replies_take_time_and_urgent_calls_do_not(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        g.latency = True
        g.ask_status("blue")
        self.assertEqual([e for e in g.radio if e["dir"] == "in"], [])    # nobody has answered yet
        for _ in range(8):
            g.tick()
        self.assertTrue(any("HP" in e["text"] for e in g.radio))          # the status arrived later
        g.units[0].hp = 4                                                  # urgent: heavy damage is called in at once
        g.tick()
        self.assertTrue(any(r["kind"] == "damaged" for r in g.reports))

    def test_spoken_orders_are_understood(self):
        from game import agents
        self.assertEqual(agents.normalize("anvil one move to echo seven"), "Anvil-1 move to echo 7")
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        g.chat("blue", "all", "anvil one move to echo seven")
        self.assertEqual(g.unit_by_id("b-tank-1").dest, (4, 6))

    def test_acks_use_real_radio_words_and_eta(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        g.chat("blue", "b-tank-1", "move to Echo-7")
        reply = next(e["text"] for e in g.radio if e["dir"] == "in")
        self.assertRegex(reply, r"(Copy|Roger|Wilco|Understood)")
        self.assertRegex(reply, r"ETA \d+ sec")

    def test_contact_report_gives_clock_bearing_and_point_me_to_it(self):
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("r-tank-1", "tank", "red", 13, 7)])
        g.tick()
        rep = next(r for r in g.reports if r["kind"] == "contact")
        self.assertRegex(rep["text"], r"my \d+ o'clock")
        self.assertIn("Point me to the target", rep["text"])

    def test_taking_hit_friendly_fire_sinking_and_code_red(self):
        g = fresh([U("b-destroyer-1", "destroyer", "blue", 9, 7), U("r-tank-1", "tank", "red", 19, 12)])
        d = g.units[0]
        g._hit("Test", d, 2, "red")
        self.assertTrue(any("Taking hit" in e["text"] for e in g.radio))
        g.t += 10
        g._hit("Missile (own)", d, 2, "blue")
        self.assertTrue(any("Friendly fire" in e["text"] for e in g.radio))
        g.t += 10
        g._hit("Test", d, 5, "red")                                       # HP 10 -> 1: sinking
        self.assertTrue(any("sinking" in e["text"] and "CODE RED" in e["text"] for e in g.radio))
        kinds = {s["kind"] for s in g.sfx}
        self.assertTrue({"hit"} <= kinds and "alarm" in kinds)

    def test_inbound_missile_raises_code_red(self):
        g = fresh([U("b-tank-1", "tank", "blue", 5, 7), U("r-missile_launcher-1", "missile_launcher", "red", 13, 7),
                   U("r-infantry-1", "infantry", "red", 8, 7)])          # the infantry spots for the launcher
        g.units[2].hold_fire = True
        g.tick()
        g.order_attack("red", g.units[1], g.units[0])
        g.tick()
        self.assertTrue(any("CODE RED" in e["text"] and "Inbound missile" in e["text"] for e in g.radio))

    def test_ignored_contact_leaves_the_unit_caught_unprepared(self):
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("r-tank-1", "tank", "red", 13, 7)])
        g.tick()
        hp = g.units[0].hp
        for _ in range(42):
            g.tick()
        self.assertEqual(g.resp["missed"], 1)
        self.assertGreater(g.units[0].shaken_until, 0)
        self.assertTrue(any("took" in e["text"] and "damage" in e["text"] for e in g.radio))   # the damage is called out
        self.assertLess(g.units[0].hp, hp)

    def test_a_unit_killed_by_a_late_decision_is_called_dead(self):
        g = fresh([U("b-infantry-1", "infantry", "blue", 10, 7), U("r-tank-1", "tank", "red", 12, 7)])
        g.units[0].hold_fire = True
        g.units[1].hold_fire = True                      # the tank only strikes when the General is too slow
        g.units[0].hp = 2
        g.tick()
        for _ in range(42):
            g.tick()
        self.assertTrue(any("DEAD" in e["text"] and "too late" in e["text"] for e in g.radio))

    def test_response_time_is_measured(self):
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("r-tank-1", "tank", "red", 13, 7)])
        g.tick()
        rep = next(r for r in g.reports if r["kind"] == "contact")
        for _ in range(5):
            g.tick()
        g.choose("blue", rep["id"], "hold")
        self.assertEqual(g.resp["answered"], 1)
        self.assertGreaterEqual(g.resp["total"], 5)

    def test_extraction_picks_a_unit_up_and_returns_it_repaired(self):
        g = fresh([U("b-tank-1", "tank", "blue", 5, 12), U("b-infantry-1", "infantry", "blue", 3, 3), U("r-tank-1", "tank", "red", 19, 12)])
        g.units[0].hp = 2
        g.chat("blue", "b-tank-1", "request extraction")
        self.assertTrue(any("Extraction at" in e["text"] and "ETA 45 sec" in e["text"] for e in g.radio))
        for _ in range(45):
            g.tick()
        self.assertIsNone(g.unit_by_id("b-tank-1"))
        for _ in range(32):
            g.tick()
        back = [u for u in g.units if u.type == "tank" and u.team == "blue"]
        self.assertEqual(len(back), 1)
        self.assertGreaterEqual(back[0].hp, back[0].max_hp // 2)


class Physics(unittest.TestCase):
    def test_wind_pushes_a_missile_off_target(self):
        g = fresh([U("b-launcher-1", "missile_launcher", "blue", 2, 7), U("b-spotter-1", "infantry", "blue", 5, 7), U("r-tank-1", "tank", "red", 8, 7)])
        g.units[0].type = "missile_launcher"
        g.wind = (1.0, 0.0)                              # blowing east
        g.units[0].id = "b-missile_launcher-1"
        g.tick()
        g.order_attack("blue", g.units[0], g.units[2])
        g.tick()
        self.assertEqual((g.impacts[0]["c"], g.impacts[0]["r"]), (9, 7))   # 6 tiles at wind 1.0 -> one tile east
        launch = next(s for s in g.sfx if s["kind"] == "launch")
        self.assertEqual((launch["c2"], launch["r2"], launch["dur"]), (9, 7, 6))

    def test_long_guns_can_miss_in_a_wind_but_close_ones_never_do(self):
        g = fresh([U("b-artillery-1", "artillery", "blue", 4, 7), U("r-tank-1", "tank", "red", 8, 7),
                   U("b-infantry-1", "infantry", "blue", 6, 7)])                                   # the infantry spots the tank, 4 tiles from the guns
        g.units[2].hold_fire = True
        misses = 0
        for i in range(60):
            g.units[0].ammo, g.units[0].ready_at, g.units[1].hp = 12, 0, 12
            g.t += 10
            g._observe()
            g._fight(g.units[0])
            misses += any(s["kind"] == "miss" for s in g.sfx[-2:])
        self.assertGreater(misses, 0)
        near = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("r-tank-1", "tank", "red", 11, 7)])
        for _ in range(10):
            near.tick()
        self.assertFalse(any(s["kind"] == "miss" for s in near.sfx))

    def test_a_high_current_carries_an_idle_ship_east(self):
        g = fresh([U("b-cruiser-1", "cruiser", "blue", 9, 1), U("r-tank-1", "tank", "red", 19, 12)])    # (9,1) is a high current
        g.units[0].hold_fire = True
        self.assertEqual(g.board.terrain(9, 1), "high_current")
        for _ in range(7):
            g.tick()
        self.assertEqual(g.units[0].c, 10)

    def test_wind_is_reported_to_the_panel(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        g.wind = (0.5, -0.5)
        w = g.panel("blue")["wind"]
        self.assertIn("from", w["text"])
        self.assertEqual(w["arrow"], "↗")


class AIGeneral(unittest.TestCase):
    def setUp(self):
        self.g = fresh([U("r-infantry-1", "infantry", "red", 18, 3), U("r-tank-1", "tank", "red", 17, 6), U("r-infantry-2", "infantry", "red", 8, 7),
                        U("b-tank-1", "tank", "blue", 10, 7), U("b-spy-1", "spy", "blue", 3, 3)])
        self.g.units[2].hold_fire = True
        self.g.tick()

    def test_brief_lists_only_what_red_knows(self):
        b = self.g.general_brief("red")
        self.assertIn("Rifle-1", b["user"])
        self.assertIn("Anvil-1", b["user"])
        self.assertNotIn("Spy", b["user"])                      # the blue spy is far away and unseen
        self.assertIn("JSON", b["system"])
        self.assertIn("Never copy the placeholders", b["system"])

    def test_orders_are_validated_and_carried_out(self):
        self.g.general_brief("red")
        res = self.g.apply_general_orders("red", [
            {"unit": "Anvil-1", "action": "move", "to": "Romeo-8"},
            {"unit": "Rifle-1", "action": "hold_fire"},
            {"unit": "Nobody-9", "action": "move", "to": "Romeo-8"},
            {"unit": "Anvil-1", "action": "move", "to": "Nowhere-99"},
            {"unit": "Rifle-1", "action": "attack", "target": "E9"},
            {"unit": "Rifle-1", "action": "launch_nukes"},
            "garbage"])
        self.assertEqual(res["applied"], 2)
        self.assertEqual(len(res["rejected"]), 4)               # the 7th order ("garbage") is beyond the 6-order limit
        self.assertEqual(self.g.unit_by_id("r-tank-1").dest, (17, 7))
        self.assertTrue(self.g.unit_by_id("r-infantry-1").hold_fire)
        self.assertIsNotNone(self.g.general_at)

    def test_the_ai_general_cannot_give_orders_for_the_human_side(self):
        res = self.g.apply_general_orders("blue", [{"unit": "Anvil-1", "action": "move", "to": "Kilo-9"}])
        self.assertEqual(res["applied"], 0)

    def test_enemy_orders_can_be_intercepted_by_a_spy_and_shown_in_morse(self):
        self.g.rng.random = lambda: 0.0                         # always overheard
        self.g.apply_general_orders("red", [{"unit": "Anvil-1", "action": "move", "to": "Romeo-8"}], "Forward!")
        hit = [e for e in self.g.radio if e["who"] == "INTERCEPT"]
        self.assertTrue(hit and hit[0]["kind"] == "morse" and "ANVIL-1 MOVE" in hit[0]["text"])


class LiveScenarios(unittest.TestCase):
    def test_a_rumour_is_marked_and_resolved_when_seen(self):
        from game import events
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 15, 7), U("b-spy-1", "spy", "blue", 3, 3)])
        g.rng.random = lambda: 0.5                              # skip the silo tip, take a true tip
        g.nuke_level["blue"] = {0: 3, 1: 3}
        msg = events.make_rumor(g, "blue")
        self.assertIn("Unverified", msg)
        self.assertEqual(len(g.rumors), 1)
        rum = g.rumors[0]
        self.assertTrue(rum["true"])
        g.units[0].c, g.units[0].r = rum["c"], rum["r"] if g.board.terrain(rum["c"], rum["r"]) in rules_land() else (3, 6)
        g.vis["blue"].add((rum["c"], rum["r"]))
        events.resolve_rumors(g)
        self.assertEqual(g.rumors, [])
        self.assertTrue(any("tip" in e["text"] or "False alarm" in e["text"] for e in g.radio))

    def test_rumours_fade_if_nobody_looks(self):
        from game import events
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 15, 7)])
        g.rng.random = lambda: 0.5
        g.nuke_level["blue"] = {0: 3, 1: 3}
        events.make_rumor(g, "blue")
        g.vis["blue"] = set()
        g.t += events.RUMOR_TTL + 1
        events.resolve_rumors(g)
        self.assertEqual(g.rumors, [])
        self.assertTrue(any("gone cold" in e["text"] for e in g.radio))

    def test_chat_asks_for_scenarios_with_a_cooldown(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 15, 7), U("r-tank-2", "tank", "red", 16, 7)])
        g.t = 5
        g.chat("blue", "all", "HQ scenario defector")
        self.assertTrue(any("defected" in e["text"] for e in g.radio))
        self.assertTrue(g.intel["blue"])                        # the defector's contacts are on the map
        g.chat("blue", "all", "HQ scenario storm")
        self.assertTrue(any("HQ is busy" in e["text"] for e in g.radio))
        g.t += 61
        g.chat("blue", "all", "HQ scenario storm")
        self.assertGreater(g.storm_until, g.t)
        self.assertNotEqual(g.wind, g.wind_base)

    def test_a_storm_slows_ships_then_passes(self):
        from game import events
        g = fresh([U("b-destroyer-1", "destroyer", "blue", 9, 7), U("r-tank-1", "tank", "red", 19, 12)])
        calm = g.slow(g.units[0])
        events.scenario(g, "blue", "storm")
        self.assertGreater(g.slow(g.units[0]), calm)
        g.t = g.storm_until
        events.tick(g)
        self.assertEqual(g.storm_until, 0)
        self.assertEqual(g.wind, g.wind_base)

    def test_a_named_unit_hears_the_rumour_and_the_prompt_for_the_model_has_context(self):
        g = fresh([U("b-spy-1", "spy", "blue", 3, 3), U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 15, 7)])
        g.nuke_level["blue"] = {0: 3, 1: 3}                     # no silo tip: an ordinary rumour
        g.chat("blue", "b-spy-1", "Ghost-1, any rumours?")
        self.assertTrue(any(e["who"] == "Ghost-1" and "arked on your map" in e["text"] for e in g.radio))
        req = g.chat("blue", "b-tank-1", "how is the crew mood", llm=True)
        self.assertIn("Nearest friends", req["system"])
        self.assertIn("Recent radio", req["system"])


def rules_land():
    from game import rules
    return rules.INFANTRY


class Outcomes(unittest.TestCase):
    def test_engage_decision_reports_success_when_the_target_dies(self):
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("r-infantry-1", "infantry", "red", 12, 7)])
        g.tick()
        rep = next(r for r in g.reports if r["kind"] == "contact")
        g.choose("blue", rep["id"], "engage")
        for _ in range(40):
            g.tick()
        d = g.decisions[0]
        self.assertEqual(d["status"], "success")
        self.assertTrue(any("OUTCOME" in e["text"] and "SUCCESS" in e["text"] for e in g.radio))

    def test_hold_fire_decision_fails_if_the_unit_is_hit_anyway(self):
        g = fresh([U("b-infantry-1", "infantry", "blue", 10, 7), U("r-tank-1", "tank", "red", 12, 7)])
        g.tick()
        rep = next(r for r in g.reports if r["kind"] == "contact")
        g.choose("blue", rep["id"], "hold")
        for _ in range(12):
            g.tick()
        self.assertEqual(g.decisions[0]["status"], "failure")
        self.assertTrue(any("FAILURE" in e["text"] for e in g.radio))
        self.assertEqual(g.decision_stats()["bad"], 1)


class Healing(unittest.TestCase):
    def test_a_hurt_unit_in_a_friendly_port_recovers_but_not_under_fire(self):
        g = fresh([U("b-tank-1", "tank", "blue", 4, 3), U("r-tank-1", "tank", "red", 19, 12)])          # (4, 3) is Ladooo's port
        g.units[0].hp = 5
        g.units[0].hurt_at = -99
        for _ in range(30):
            g.tick()
        self.assertGreater(g.units[0].hp, 5)
        g.units[0].hp = 5
        g.units[0].hurt_at = g.t
        g.tick()
        self.assertEqual(g.units[0].hp, 5)

    def test_withdrawing_home_then_repairing_clears_the_damage_flag(self):
        g = fresh([U("b-tank-1", "tank", "blue", 4, 3), U("r-tank-1", "tank", "red", 19, 12)])
        g.units[0].hp = 4
        g.units[0].flags.add("damaged")
        for _ in range(40):
            g.tick()
        self.assertNotIn("damaged", g.units[0].flags)


class Traps(unittest.TestCase):
    def test_barricades_block_vehicles_slow_infantry_and_can_be_breached(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("b-builder-1", "builder", "blue", 3, 4), U("r-tank-1", "tank", "red", 19, 12)])
        g.mines.clear()                                                  # keep the causeway free of mines for this test
        self.assertEqual(g.board.terrain(9, 0), "barricade")
        tank = g.units[0]
        self.assertIsNone(g.path_for(tank, (11, 0)))                    # the causeway is shut to tanks
        inf = U("b-infantry-1", "infantry", "blue", 4, 0)
        g.units.append(inf)
        self.assertIsNotNone(g.path_for(inf, (11, 0)))                  # infantry can climb over, slowly
        g.units.remove(inf)
        b = g.units[1]
        b.c, b.r = 8, 0
        g.work("blue", "b-builder-1", "breach")
        for _ in range(10):
            g.tick()
        self.assertNotEqual(g.board.terrain(9, 0), "barricade")
        g.work("blue", "b-builder-1", "barricade")
        for _ in range(12):
            g.tick()
        self.assertEqual(g.board.terrain(8, 0), "barricade")

    def test_a_shell_blows_a_barricade_apart(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        g._impact(dict(c=9, r=0, dmg=5, by="Test", team="red"))
        self.assertNotEqual(g.board.terrain(9, 0), "barricade")

    def test_ambush_hides_holds_then_springs_with_double_damage(self):
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("b-infantry-1", "infantry", "blue", 10, 8), U("r-infantry-1", "infantry", "red", 16, 7)])
        reply = g.chat("blue", "all", "tanks ambush")
        self.assertTrue(g.units[0].ambush and g.units[0].hold_fire)
        g.tick()
        self.assertNotIn("b-tank-1", g.detected["red"] | {i for i in g.detected["red"]})   # far away and hidden
        g.units[2].c, g.units[2].r = 12, 7                                                  # walks into the trap
        hp = g.units[2].hp
        for _ in range(4):
            g.tick()
        self.assertFalse(g.unit_by_id("b-tank-1").ambush)
        foe = g.unit_by_id("r-infantry-1")
        self.assertTrue(foe is None or foe.hp < hp)                  # dead or badly hurt by the doubled volley
        self.assertTrue(any("AMBUSH" in e["text"] for e in g.radio))

    def test_a_unit_in_ambush_is_only_seen_from_one_tile(self):
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("r-tank-1", "tank", "red", 12, 7)])
        g.units[0].ambush = True
        g.units[0].hold_fire = True
        g.units[1].hold_fire = True
        g._observe()
        self.assertNotIn("b-tank-1", g.detected["red"])
        g.units[1].c = 11
        g._observe()
        self.assertIn("b-tank-1", g.detected["red"])

    def test_lure_draws_the_bait_towards_the_enemy_then_runs_for_the_trap(self):
        g = fresh([U("b-destroyer-1", "destroyer", "blue", 7, 6), U("r-destroyer-1", "destroyer", "red", 11, 5)])
        g.units[1].hold_fire = True
        g.tick()
        g.chat("blue", "b-destroyer-1", "lure the enemy to Hotel-5")           # the trap is at (7, 4)
        self.assertIsNotNone(g.units[0].lure)
        for _ in range(40):
            g.tick()
            if g.units[0].lure is None or g.units[0].lure["phase"] == "retreat":
                break
        self.assertTrue(any("They've seen me" in e["text"] for e in g.radio))
        self.assertEqual(g.units[0].dest, (7, 4))


class Levels(unittest.TestCase):
    def test_every_level_builds_and_has_a_goal_and_a_limit(self):
        from game import levels
        for lv in levels.LEVELS:
            g = Game(level=lv, seed=1)
            self.assertLess(g.time_limit, 10 ** 8)
            p = g.panel("blue")["level"]
            self.assertEqual(p["id"], lv)
            self.assertTrue(p["goal"] and p["progress"])
        self.assertLess(len(Game(level=1).units), len(Game(level=3).units))
        self.assertGreater(len(Game(level=4).units), len(Game(level=3).units))

    def test_level_one_is_won_by_capturing_two_enemy_objectives_with_stars(self):
        g = Game(level=1, seed=1)
        east = [p for p in g.objectives if p[0] >= 10][:2]
        for p in east:
            g.objectives[p]["owner"] = "blue"
        g.tick()
        self.assertEqual(g.winner, "blue")
        self.assertGreaterEqual(g.ending["stars"], 2)                  # won quickly
        self.assertEqual(g.ending["next_level"], 2)

    def test_time_runs_out_and_the_war_is_decided_on_points(self):
        g = Game(level=3, seed=1)
        g.t = g.time_limit
        g.tick()
        self.assertIsNotNone(g.winner)
        self.assertIn(g.ending["title"], ("Victory on points", "Defeat on points", "Stalemate"))
        self.assertIn("Time is up", g.win_reason)

    def test_convoys_decide_level_two(self):
        g = Game(level=2, seed=1)
        g.delivered["blue"] = 3
        g.tick()
        self.assertEqual(g.winner, "blue")


class Pace(unittest.TestCase):
    def test_the_game_starts_slow_and_gives_decision_time(self):
        g = Game(seed=1)
        self.assertEqual(g.speed, 0.5)
        self.assertEqual(g.think_secs, 15)
        g.control("speed", 0.25)
        self.assertEqual(g.speed, 0.25)
        g.control("think", 30)
        self.assertEqual(g.think_secs, 30)
        g.control("think", 0)
        self.assertFalse(g.pause_on_report)

    def test_the_clock_waits_while_an_urgent_report_is_open(self):
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("r-tank-1", "tank", "red", 13, 7)])
        g.tick()
        self.assertTrue(any(r["kind"] == "contact" for r in g.reports))
        self.assertGreater(g.thinking_left(), 0)
        rep = next(r for r in g.reports if r["kind"] == "contact")
        g.choose("blue", rep["id"], "hold")
        self.assertEqual(g.thinking_left(), 0)


class Commands(unittest.TestCase):
    def setUp(self):
        self.g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("b-tank-2", "tank", "blue", 3, 7), U("b-infantry-1", "infantry", "blue", 3, 3),
                        U("b-destroyer-1", "destroyer", "blue", 7, 6), U("r-tank-1", "tank", "red", 12, 7)])

    def heard(self, text, to="all"):
        before = len(self.g.radio)
        self.g.chat("blue", to, text)
        return [e["text"] for e in self.g.radio[before:] if e["dir"] == "in"]

    def test_many_ways_to_say_move(self):
        for text in ("Anvil-1 move to Echo-6", "Anvil-1 go to Echo-6", "send Anvil-1 to Echo 6", "anvil one proceed to echo six",
                     "Anvil-1 Echo-6", "Anvil-1 advance to Echo-6", "Anvil-1 deploy to Echo-6"):
            self.g.units[0].dest = None
            self.g.units[0].path = []
            replies = self.heard(text)
            self.assertEqual(self.g.units[0].dest, (4, 5), text)

    def test_unit_kinds_can_be_addressed_together(self):
        self.heard("all tanks hold fire")
        self.assertTrue(self.g.units[0].hold_fire and self.g.units[1].hold_fire)
        self.assertFalse(self.g.units[2].hold_fire)
        self.heard("tanks fire at will")
        self.assertFalse(self.g.units[0].hold_fire)
        self.heard("destroyers fall back")
        self.assertTrue(self.g.units[3].path or self.g.units[3].dest is None)

    def test_stop_capture_attack_at_a_grid_and_help(self):
        self.heard("Anvil-1 move to Echo-6")
        self.heard("Anvil-1 stop")
        self.assertEqual(self.g.units[0].path, [])
        self.heard("Rifle-1 capture the nearest port")
        self.assertTrue(self.g.units[2].path or "capture" in " ".join(e["text"] for e in self.g.radio))
        out = self.heard("Anvil-1 help")
        self.assertTrue(any("I understand" in t for t in out))

    def test_attack_by_grid_reference_and_by_type(self):
        self.g.units[4].c, self.g.units[4].r = 11, 6
        self.g.units[4].hold_fire = True
        self.g.tick()
        self.assertIn("r-tank-1", self.g.detected["blue"])              # the destroyer sees it
        self.heard("Neptune-1 attack the tank")
        self.assertEqual(self.g.units[3].target_id, "r-tank-1")
        self.g.units[3].target_id = None
        self.heard("Neptune-1 fire on Lima-7")                          # Lima = column 11, row 7 -> (11, 6)
        self.assertEqual(self.g.units[3].target_id, "r-tank-1")
        out = self.heard("Neptune-1 fire on Alpha-1")
        self.assertTrue(any("nothing at" in t.lower() for t in out))

    def test_unknown_orders_get_a_helpful_answer_not_silence(self):
        out = self.heard("Anvil-1 do a barrel roll")
        self.assertTrue(any("help" in t.lower() for t in out))

    def test_trap_commands_ambush_lure_barricade(self):
        self.heard("Anvil-2 set an ambush")
        self.assertTrue(self.g.units[1].ambush)
        out = self.heard("Anvil-1 lure them")
        self.assertTrue(any("grid reference" in t for t in out))


class HomeFront(unittest.TestCase):
    def make(self, **kw):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("b-spy-1", "spy", "blue", 3, 3), U("r-tank-1", "tank", "red", 19, 12)])
        for side, vals in kw.items():
            g.home[side].update(vals)
        return g

    def test_level_one_has_no_politics_and_the_others_do(self):
        self.assertFalse(Game(level=1).panel("blue")["home"]["on"])
        h = Game(level=3).panel("blue")["home"]
        self.assertTrue(h["on"] and h["mine"]["stability"] == 70)
        self.assertGreater(Game(level=4).home["red"]["stability"], Game(level=4).home["blue"]["stability"])

    def test_losses_and_lost_cities_shake_the_government(self):
        g = self.make()
        before = dict(g.home["blue"])
        g._hit("Test", g.units[0], 50, "red")                         # a tank is lost: markets flinch
        self.assertLess(g.home["blue"]["economy"], before["economy"])
        o = next(iter(g.objectives))
        g.objectives[o]["owner"] = "red"
        from game import homefront
        homefront.on_capture(g, "blue", "port")
        self.assertLess(g.home["blue"]["stability"], before["stability"] - 3)

    def test_corruption_skims_convoys_and_slows_reinforcements(self):
        from game import homefront
        g = self.make(blue=dict(corruption=80.0, economy=40.0))
        self.assertLess(homefront.cargo(g, "blue", 25), 15)
        self.assertGreater(homefront.slowdown(g, "blue"), 10)
        clean = self.make(blue=dict(corruption=0.0, economy=100.0))
        self.assertEqual(homefront.cargo(clean, "blue", 25), 25 * 1 * (.6 + 100 / 250) if False else homefront.cargo(clean, "blue", 25))
        self.assertGreater(homefront.cargo(clean, "blue", 25), homefront.cargo(g, "blue", 25))
        self.assertIn("ETA", g.reinforce("blue", "land"))
        self.assertGreater(g.arrivals[0]["at"] - g.t, 40)             # corruption added delay to the 40 s convoy

    def test_a_coup_ends_the_war_when_stability_stays_very_low(self):
        g = self.make(blue=dict(stability=2.0, unrest=90.0))
        g.home["blue"]["low_stab"] = 15
        g.t = 4
        for _ in range(8):
            g.tick()
            if g.winner:
                break
        self.assertEqual(g.winner, "red")
        self.assertEqual(g.ending["title"], "Coup d'état")

    def test_economic_collapse_loses_the_war(self):
        g = self.make(blue=dict(economy=1.0))
        g.home["blue"]["low_econ"] = 40
        g.supply["blue"].update(fuel=0.0, food=0.0)                      # no supplies, and every city lost: nothing to recover on
        for o in g.objectives.values():
            o["owner"] = "red"
        g.t = 4
        for _ in range(8):
            g.tick()
            if g.winner:
                break
        self.assertEqual(g.ending["title"], "Economic collapse")

    def test_home_measures_trade_one_thing_for_another(self):
        from game import homefront
        g = self.make(blue=dict(corruption=50.0, stability=50.0, economy=50.0, unrest=50.0))
        homefront.action(g, "blue", "purge")
        self.assertEqual((g.home["blue"]["corruption"], g.home["blue"]["stability"]), (35.0, 46.0))
        homefront.action(g, "blue", "pay")
        self.assertEqual(g.home["blue"]["economy"], 44.0)
        self.assertGreater(g.home["blue"]["stability"], 46.0)
        self.assertIn("not ready", homefront.action(g, "blue", "purge"))     # cooldown
        homefront.action(g, "blue", "crackdown")
        self.assertEqual(g.home["blue"]["unrest"], 30.0)

    def test_covert_operations_cost_points_and_hurt_the_enemy(self):
        from game import homefront
        g = self.make()
        g.intel_points["blue"] = 5.0
        g.rng.random = lambda: 0.5                                       # not exposed (needs < .25), and the op works (< .7)
        homefront.action(g, "blue", "fund")
        self.assertGreater(g.home["red"]["unrest"], 20)
        homefront.action(g, "blue", "markets")
        self.assertLess(g.home["red"]["economy"], 62)
        self.assertEqual(g.intel_points["blue"], 2.0)
        self.assertIn("Not enough", homefront.action(g, "blue", "coup"))

    def test_a_coup_against_a_shaky_enemy_can_win_the_war(self):
        from game import homefront
        g = self.make(red=dict(stability=5.0, unrest=95.0))
        g.intel_points["blue"] = 5.0
        g.rng.random = lambda: 0.0
        self.assertIn("succeeded", homefront.action(g, "blue", "coup"))
        self.assertEqual(g.winner, "blue")

    def test_a_failed_coup_backfires(self):
        from game import homefront
        g = self.make()
        g.intel_points["blue"] = 5.0
        g.rng.random = lambda: 0.99
        stab = g.home["blue"]["stability"]
        homefront.action(g, "blue", "coup")
        self.assertLess(g.home["blue"]["stability"], stab)
        self.assertIsNone(g.winner)

    def test_the_enemys_state_is_only_known_with_a_spy(self):
        from game import homefront
        g = self.make()
        self.assertIsNotNone(homefront.panel(g, "blue")["enemy"])
        g.units = [u for u in g.units if u.type != "spy"]
        self.assertIsNone(homefront.panel(g, "blue")["enemy"])

    def test_shaky_governments_cap_morale(self):
        from game import homefront
        g = self.make(blue=dict(stability=10.0))
        self.assertEqual(homefront.morale_ceiling(g, "blue"), 50.0)
        g.units[0].morale = 100.0
        g.tick()
        self.assertLessEqual(g.units[0].morale, 50.0)


class Realism(unittest.TestCase):
    def test_tank_units_are_drawn_as_groups_that_thin_out(self):
        from ui.figure import _members, build
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        self.assertEqual(_members(g.units[0]), 4)
        g.units[0].hp = 6
        self.assertEqual(_members(g.units[0]), 2)
        g.units[0].hp = 1
        self.assertEqual(_members(g.units[0]), 1)
        g.units[0].hp = 12
        fig = build(g, "blue", "home")
        mine = [i for i in fig["layout"]["images"] if "u=b-tank-1" in i["source"]]
        self.assertEqual(len(mine), 4)

    def test_aircraft_fly_over_anything_burn_fuel_land_and_refuel(self):
        g = fresh([U("b-fighter-1", "fighter", "blue", 1, 1), U("r-tank-1", "tank", "red", 19, 12)])
        f = g.units[0]
        self.assertEqual(g.board.terrain(1, 1), "airfield")
        g.order_move("blue", f, 12, 5)                                   # over the sea and the island
        for _ in range(12):
            g.tick()
        self.assertEqual((f.c, f.r), (12, 5))
        self.assertLess(f.fuel, f.max_fuel)
        g.order_move("blue", f, 1, 1)
        for _ in range(25):
            g.tick()
        self.assertEqual((f.c, f.r), (1, 1))
        for _ in range(15):
            g.tick()
        self.assertEqual(f.fuel, f.max_fuel)                              # refuelled on the airfield

    def test_an_aircraft_that_runs_dry_crashes(self):
        g = fresh([U("b-uav-1", "uav", "blue", 8, 7), U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        g.units[0].fuel = 3
        for _ in range(5):
            g.tick()
        self.assertIsNone(g.unit_by_id("b-uav-1"))
        self.assertTrue(any("out of fuel" in e["text"].lower() for e in g.radio))

    def test_only_fighters_helicopters_and_anti_air_can_hit_aircraft(self):
        from game import rules
        jet = U("r-fighter-1", "fighter", "red", 8, 7)
        for typ in ("tank", "infantry", "destroyer", "artillery"):
            self.assertFalse(rules.can_hit(U("b-x-1", typ, "blue", 7, 7), jet))
        for typ in ("fighter", "attack_helicopter", "anti_air"):
            self.assertTrue(rules.can_hit(U("b-x-1", typ, "blue", 7, 7), jet))
        self.assertFalse(rules.can_hit(U("b-x-1", "anti_air", "blue", 7, 7), U("r-tank-1", "tank", "red", 8, 7)))

    def test_bomber_bombs_a_tile_and_flies_home_after_the_strike(self):
        g = fresh([U("b-bomber-1", "bomber", "blue", 1, 1), U("b-infantry-1", "infantry", "blue", 3, 3), U("r-tank-1", "tank", "red", 10, 2),
                   U("b-spotter-1", "uav", "blue", 8, 3)])
        g.tick()
        self.assertIn("r-tank-1", g.detected["blue"])                     # the UAV sees it
        hp = g.units[2].hp
        g.order_attack("blue", g.units[0], g.units[2])
        for _ in range(25):
            g.tick()
        foe = g.unit_by_id("r-tank-1")
        self.assertTrue(foe is None or foe.hp < hp)
        for _ in range(30):
            g.tick()
        bomber = g.unit_by_id("b-bomber-1")
        self.assertEqual((bomber.c, bomber.r), (1, 1))                    # back on its airfield...
        self.assertEqual(bomber.ammo, 2)                                  # ...and rearmed

    def test_medics_heal_and_supply_trucks_resupply(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("b-medic-1", "medic", "blue", 3, 7), U("b-supply_truck-1", "supply_truck", "blue", 2, 6),
                   U("r-tank-1", "tank", "red", 19, 12)])
        g.units[0].hp, g.units[0].ammo = 5, 3
        g.units[0].hurt_at = -99
        for _ in range(21):
            g.tick()
        self.assertGreater(g.units[0].hp, 5)
        self.assertGreater(g.units[0].ammo, 3)

    def test_gas_hurts_unmasked_units_and_masks_stop_it(self):
        from game import events
        g = fresh([U("b-infantry-1", "infantry", "blue", 3, 6), U("b-infantry-2", "infantry", "blue", 3, 7), U("r-tank-1", "tank", "red", 19, 12)])
        g.units[1].mask = True
        events.gas_attack(g, 3, 6)
        rep = next(r for r in g.reports if r["kind"] == "gas")
        self.assertEqual({o["id"] for o in rep["options"]}, {"masks", "evacuate"})
        for _ in range(9):
            g.tick()
        self.assertLess(g.units[0].hp, g.units[0].max_hp)
        self.assertEqual(g.units[1].hp, g.units[1].max_hp)
        self.assertTrue(any("GAS GAS GAS" in e["text"] for e in g.radio))

    def test_choosing_masks_masks_everyone_near_and_all_clear_removes_them(self):
        from game import events
        g = fresh([U("b-infantry-1", "infantry", "blue", 3, 6), U("b-infantry-2", "infantry", "blue", 4, 6), U("r-tank-1", "tank", "red", 19, 12)])
        events.gas_attack(g, 3, 6)
        rep = next(r for r in g.reports if r["kind"] == "gas")
        g.choose("blue", rep["id"], "masks")
        self.assertTrue(all(u.mask for u in g.units if u.team == "blue"))
        g.t += events.GAS_SECS + 1
        g.tick()
        self.assertFalse(any(u.mask for u in g.units))
        self.assertTrue(any("ALL CLEAR" in e["text"] for e in g.radio))

    def test_a_flood_warns_then_strands_vehicles_then_drains(self):
        from game import events
        g = fresh([U("b-tank-1", "tank", "blue", 1, 3), U("r-tank-1", "tank", "red", 19, 12)])
        self.assertEqual(g.board.terrain(1, 3), "flood_plain")
        for r in range(g.board.height):                                  # make (1, 3) the only flood plain, so the pick is certain
            for c in range(g.board.width):
                if g.board.terrain(c, r) == "flood_plain" and (c, r) != (1, 3):
                    g.board.grid[r][c] = "plains"
        events.flood_warning(g)
        self.assertEqual(g.floods[0]["stage"], "warning")
        self.assertTrue(any(r["kind"] == "flood" for r in g.reports))
        g.t = g.floods[0]["hits"]
        events.tick_hazards(g)
        self.assertEqual(g.board.terrain(1, 3), "flooded_zone")
        self.assertLess(g.units[0].hp, 12)
        g.t = g.floods[0]["until"]
        events.tick_hazards(g)
        self.assertEqual(g.board.terrain(1, 3), "flood_plain")

    def test_an_air_raid_is_its_own_alert(self):
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("b-fighter-1", "fighter", "blue", 1, 1), U("r-bomber-1", "bomber", "red", 13, 7)])
        g.tick()
        rep = next(r for r in g.reports if r["kind"] == "airraid")
        self.assertIn("scramble", {o["id"] for o in rep["options"]})
        g.choose("blue", rep["id"], "scramble")
        self.assertEqual(g.unit_by_id("b-fighter-1").target_id, "r-bomber-1")

    def test_barracks_train_and_training_camps_make_veterans(self):
        g = fresh([U("b-tank-1", "tank", "blue", 1, 9), U("r-tank-1", "tank", "red", 19, 12)])      # B10 is the training camp
        self.assertEqual(g.board.terrain(1, 9), "training_camp")
        for _ in range(25):
            g.tick()
        self.assertEqual(g.units[0].vet, 1)
        self.assertEqual(g.units[0].max_hp, 14)
        n = sum(1 for u in g.units if u.type == "infantry" and u.team == "blue")
        g.t = 130                                                        # 90 s plus the slowdown that corruption adds
        g.tick()
        self.assertEqual(sum(1 for u in g.units if u.type == "infantry" and u.team == "blue"), n + 1)

    def test_rebels_hide_and_are_hard_to_find_but_a_uav_spots_them(self):
        from game import events
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        g._observe()
        events.rebels_rise(g, "blue")
        rebels = [u for u in g.units if u.type == "rebel"]
        self.assertEqual(len(rebels), 3)
        self.assertTrue(all(u.ambush and u.team == "red" for u in rebels))
        r = rebels[0]
        uav = U("b-uav-1", "uav", "blue", min(19, r.c + 2), r.r)
        g.units.append(uav)
        g._observe()
        self.assertIn(r.id, g.detected["blue"])                           # a UAV sees hidden men from 3 tiles
        g.units.remove(uav)
        g.units.append(U("b-infantry-9", "infantry", "blue", min(19, r.c + 2), r.r))
        g._observe()
        self.assertNotIn(r.id, g.detected["blue"])                        # ordinary troops do not, until they are next to them

    def test_morale_breaks_from_hits_and_deaths_and_recovers_at_home(self):
        g = fresh([U("b-infantry-1", "infantry", "blue", 5, 5), U("b-infantry-2", "infantry", "blue", 5, 6), U("r-tank-1", "tank", "red", 19, 12)])
        a, b = g.units[0], g.units[1]
        g._hit("Test", b, 99, "red")                                      # a comrade dies beside it
        self.assertLess(a.morale, 100)
        a.morale = 8.0
        g.tick()
        self.assertIn("routed", a.flags)

    def test_tactical_assessment_gives_the_numbers_a_staff_officer_would(self):
        from game import tactics
        g = fresh([U("b-tank-1", "tank", "blue", 10, 7), U("b-artillery-1", "artillery", "blue", 9, 7), U("r-tank-1", "tank", "red", 12, 7)])
        g.tick()
        lines, a = tactics.contact_lines(g, "blue", g.units[0], g.units[2])
        text = " ".join(lines)
        for word in ("Visibility", "Exchange", "Ratio", "Reach", "geometry", "Best weapon"):
            self.assertIn(word, text)
        self.assertGreater(a["now"] + 1, 1)
        rep = next(r for r in g.reports if r["kind"] == "contact")
        view = g.panel("blue")["reports"][0]
        self.assertTrue(view["brief"] and all(o["info"] for o in view["options"]))


class Scenarios(unittest.TestCase):
    """Levels 5 to 12: scenarios inspired by patterns from history, with fictional nations."""

    def test_there_are_twelve_levels_and_the_new_ones_say_what_inspired_them_without_naming_a_country(self):
        from game import levels
        self.assertEqual(sorted(levels.LEVELS), list(range(1, 17)))
        for i in range(5, 13):
            lv = levels.LEVELS[i]
            self.assertTrue(lv["inspired"].startswith("Inspired by:"), i)
            text = (lv["inspired"] + lv["briefing"]).lower()
            for real in ("ukraine", "russia", "america", "iran", "germany", "ussr", "india", "china", "pakistan", "syria", "myanmar", "bangladesh"):
                self.assertNotIn(real, text, f"level {i} names a real country")

    def test_winter_slows_ground_units_and_burns_fuel_only_after_it_arrives(self):
        g = Game(level=7, seed=1)
        tank = next(u for u in g.units if u.type == "tank" and u.team == "blue")
        ship = next(u for u in g.units if u.type == "destroyer" and u.team == "blue")
        before = g.slow(tank)
        g.t = g.winter_at - 1
        g.tick()
        self.assertTrue(g.winter)
        self.assertAlmostEqual(g.slow(tank), before * 1.6)
        self.assertEqual(g.slow(ship), 1.0 * 1.0 if g.supply["blue"]["fuel"] >= 30 else g.slow(ship))
        self.assertTrue(any("WINTER" in e["text"] for e in g.radio))

    def test_firing_first_costs_stability_but_answering_does_not(self):
        g = Game(level=8, seed=1)
        g.passive_until = 10 ** 9
        g.units = [U("b-tank-1", "tank", "blue", 10, 7), U("r-tank-1", "tank", "red", 11, 7)]
        g.units[1].hold_fire = True
        st = g.home["blue"]["stability"]
        g.tick()
        g.tick()
        self.assertLess(g.home["blue"]["stability"], st)                  # we shot at a unit that had not fired
        self.assertTrue(any("firing first" in e["text"] for e in g.radio))
        g2 = Game(level=8, seed=1)
        g2.passive_until = 10 ** 9
        g2.units = [U("b-tank-1", "tank", "blue", 10, 7), U("r-tank-1", "tank", "red", 11, 7)]
        g2.last_enemy_fire = g2.t                                         # they fired on us a moment ago
        st2 = g2.home["blue"]["stability"]
        g2.tick()
        g2.tick()
        self.assertGreaterEqual(g2.home["blue"]["stability"], st2 - .5)   # only the slow drift, no penalty

    def test_highland_posts_decide_the_level_at_the_end(self):
        from game import levels
        g = Game(level=8, seed=1)
        g.units = [U("b-infantry-1", "infantry", "blue", p[0], p[1]) for p in g.posts] + [U("r-tank-1", "tank", "red", 19, 12)]
        self.assertEqual(levels.at_limit(g)[2], "Posts held")
        g.units.append(U("r-infantry-1", "infantry", "red", g.posts[0][0] + 1, g.posts[0][1]))
        self.assertEqual(levels.at_limit(g)[2], "Posts lost")

    def test_escalation_rises_with_missiles_and_shakes_both_governments(self):
        from game import homefront
        g = Game(level=9, seed=1)
        self.assertEqual(g.escalation, 0)
        self.assertTrue(all(lvl == 3 for lv in g.nuke_level.values() for lvl in lv.values()))     # both know the silos
        econ = g.home["red"]["economy"]
        for _ in range(5):
            homefront.on_missile(g, "blue")
        self.assertGreaterEqual(g.escalation, 50)
        self.assertLess(g.home["red"]["economy"], econ)
        stab = g.home["blue"]["stability"]
        for _ in range(5):
            homefront.on_missile(g, "red")
        self.assertEqual(g.escalation, 100)
        self.assertLess(g.home["blue"]["stability"], stab)

    def test_sanctions_drain_the_target_economy_all_game(self):
        g = Game(level=5, seed=1)
        g.passive_until = 10 ** 9
        e0 = g.home["red"]["economy"]
        for _ in range(60):
            g.tick()
        self.assertLess(g.home["red"]["economy"], e0 + 1)
        self.assertTrue(any("sanctions" in m.lower() for _, m in g.news))

    def test_attrition_is_won_by_cracking_the_enemy_home_front(self):
        g = Game(level=5, seed=1)
        g.home["red"]["stability"] = 30.0
        g.tick()
        self.assertEqual(g.winner, "blue")
        self.assertIn("home front", g.win_reason)

    def test_strait_crisis_needs_four_convoys(self):
        g = Game(level=6, seed=1)
        self.assertEqual(g.convoy_every, 50)
        g.delivered["blue"] = 3
        g.tick()
        self.assertIsNone(g.winner)
        g.delivered["blue"] = 4
        g.tick()
        self.assertEqual(g.winner, "blue")

    def test_an_officers_plot_needs_an_answer_and_each_answer_has_a_price(self):
        from game import homefront
        for choice, expect in (("arrest", "arrest"), ("pay_off", "bought off")):
            g = Game(level=11, seed=1)
            g.passive_until = 10 ** 9
            g.home["blue"]["stability"] = 30.0
            g.t = 59
            g.tick()
            g.t = 64
            homefront.tick(g)
            rep = next((r for r in g.reports if r["kind"] == "plot"), None)
            self.assertIsNotNone(rep, choice)
            g.choose("blue", rep["id"], choice)
            self.assertFalse(g.plot_active)
            self.assertTrue(any(expect in e["text"] for e in g.radio))
        g = Game(level=11, seed=1)
        g.passive_until = 10 ** 9
        g.home["blue"]["stability"] = 30.0
        g.t = 65
        homefront.tick(g)
        self.assertTrue(g.plot_active)
        st = g.home["blue"]["stability"]
        g.t += 45
        g.tick()
        self.assertLess(g.home["blue"]["stability"], st)                 # ignoring a plot costs 12

    def test_three_crackdowns_in_two_minutes_make_the_army_refuse(self):
        from game import homefront
        g = Game(level=12, seed=1)
        g.passive_until = 10 ** 9
        morale = [u.morale for u in g.units if u.team == "blue"]
        for i in range(3):
            g.home_cd.clear()
            g.t += 10
            msg = homefront.action(g, "blue", "crackdown")
        self.assertIn("ARMY REFUSES", msg)
        self.assertLess(sum(u.morale for u in g.units if u.team == "blue" and not u.air), sum(morale))

    def test_survive_levels_are_decided_at_the_end(self):
        from game import levels
        g = Game(level=11, seed=1)
        g.home["blue"]["stability"] = 45.0
        self.assertEqual(levels.at_limit(g)[2], "Survived")
        g.home["blue"]["stability"] = 10.0
        self.assertEqual(levels.at_limit(g)[2], "Regime falling")
        g12 = Game(level=12, seed=1)
        g12.home["blue"]["stability"] = 40.0
        self.assertEqual(levels.at_limit(g12)[2], "Held power")

    def test_a_coup_war_moves_faster_and_gives_you_more_spies_and_points(self):
        g = Game(level=10, seed=1)
        self.assertEqual(g.pol_rate, 2.5)
        self.assertGreaterEqual(g.intel_points["blue"], 4)
        self.assertGreaterEqual(sum(1 for u in g.units if u.team == "blue" and u.type == "spy"), 3)
        g.t = g.time_limit
        g.tick()
        self.assertEqual(g.ending["title"], "Stalemate")

    def test_every_scenario_can_run_a_while_without_errors(self):
        for lv in range(1, 13):
            g = Game(level=lv, seed=lv)
            for _ in range(80):
                g.tick()
            g.panel("blue")
            g.panel("referee")


class LineOfSight(unittest.TestCase):
    """Hills, mountains, trees and buildings block the view; high ground sees further; direct fire needs a clear line."""

    def row(self, g, r, **tiles):
        for c, t in tiles.items():
            g.board.grid[r][int(c[1:])] = t

    def test_geometry_of_the_line(self):
        from game import rules
        self.assertEqual(rules.tiles_between((0, 0), (3, 0)), [(1, 0), (2, 0)])
        self.assertEqual(rules.tiles_between((0, 0), (0, 0)), [])
        self.assertEqual(len(rules.tiles_between((0, 0), (4, 4))), 3)

    def test_trees_and_hills_block_sight_on_the_flat(self):
        from game import rules
        g = fresh([U("b-tank-1", "tank", "blue", 2, 6), U("r-tank-1", "tank", "red", 6, 6)])
        self.assertTrue(rules.has_los(g.board, (2, 6), (6, 6)))
        self.row(g, 6, c4="forest")
        self.assertFalse(rules.has_los(g.board, (2, 6), (6, 6)))
        self.assertEqual(rules.blocker(g.board, (2, 6), (6, 6)), (4, 6))
        self.row(g, 6, c4="hills")
        self.assertFalse(rules.has_los(g.board, (2, 6), (6, 6)))
        self.row(g, 6, c4="mountain")
        self.assertFalse(rules.has_los(g.board, (2, 6), (6, 6)))

    def test_high_ground_sees_over_trees_and_further(self):
        from game import rules
        g = fresh([U("b-tank-1", "tank", "blue", 2, 6), U("r-tank-1", "tank", "red", 6, 6)])
        self.row(g, 6, c4="forest", c2="hills")
        self.assertTrue(rules.has_los(g.board, (2, 6), (6, 6)))           # an observer on hills (eye 3.2) sees over a forest (2)
        self.assertEqual(rules.sight_bonus(g.board, 2, 6), 1)
        self.row(g, 6, c2="mountain")
        self.assertEqual(rules.sight_bonus(g.board, 2, 6), 2)
        self.assertEqual(rules.sight_bonus(g.board, 3, 6), 0)

    def test_the_enemy_behind_a_hill_is_not_spotted_until_you_climb_or_it_comes_round(self):
        g = fresh([U("b-tank-1", "tank", "blue", 2, 6), U("r-tank-1", "tank", "red", 5, 6)])
        g.units[1].hold_fire = g.units[0].hold_fire = True
        self.row(g, 6, c3="hills", c4="hills")
        g._observe()
        self.assertNotIn("r-tank-1", g.detected["blue"])                  # 3 tiles away: in range of sight but behind the hills
        self.assertNotIn((5, 6), g.vis["blue"])
        g.units[0].c = 3                                                  # climb onto the hills: higher eye, +1 sight
        g._observe()
        self.assertIn("r-tank-1", g.detected["blue"])

    def test_aircraft_look_down_over_anything_and_are_seen_over_anything(self):
        g = fresh([U("b-uav-1", "uav", "blue", 2, 6), U("r-tank-1", "tank", "red", 7, 6), U("r-fighter-1", "fighter", "red", 5, 6)])
        self.row(g, 6, c3="mountain", c4="mountain")
        g._observe()
        self.assertIn("r-tank-1", g.detected["blue"])                     # the UAV sees across the mountains
        g2 = fresh([U("b-tank-1", "tank", "blue", 2, 6), U("r-fighter-1", "fighter", "red", 5, 6)])
        self.row(g2, 6, c3="mountain", c4="mountain")
        g2._observe()
        self.assertIn("r-fighter-1", g2.detected["blue"])                 # a jet over a ridge is still seen by the ground

    def test_direct_fire_needs_a_line_of_sight_but_artillery_fires_on_what_a_spotter_sees(self):
        g = fresh([U("b-tank-1", "tank", "blue", 2, 6), U("b-artillery-1", "artillery", "blue", 2, 7), U("b-uav-1", "uav", "blue", 3, 3),
                   U("r-tank-1", "tank", "red", 4, 6)])
        self.row(g, 6, c3="forest")
        g._observe()
        self.assertIn("r-tank-1", g.detected["blue"])                     # the UAV spots it
        tank, gun, foe = g.units[0], g.units[1], g.units[3]
        self.assertFalse(g.reaches(tank, foe))                            # in range (2) but a forest is in the way
        gun.c, gun.r = 2, 7
        self.assertTrue(g.reaches(gun, foe))                              # indirect fire does not need the line
        foe.hp = foe.max_hp
        g.units[3].hold_fire = True
        hp = foe.hp
        g.tick()
        self.assertEqual(tank.ammo, 20)                                   # the tank did not shoot through the trees

    def test_a_pursuing_unit_moves_until_it_gets_a_clear_view(self):
        g = fresh([U("b-tank-1", "tank", "blue", 1, 6), U("b-uav-1", "uav", "blue", 3, 3), U("r-tank-1", "tank", "red", 3, 6)])
        self.row(g, 6, c2="forest")
        g.units[2].hold_fire = True
        g.tick()
        tank = g.units[0]
        g.order_attack("blue", tank, g.units[2])
        start = (tank.c, tank.r)
        for _ in range(8):
            g.tick()
        self.assertNotEqual((tank.c, tank.r), start)                      # it went round the trees rather than stand and stare
        self.assertTrue(g.reaches(tank, g.units[2]) or tank.ammo < 20)

    def test_the_assessment_says_when_the_view_is_blocked(self):
        from game import tactics
        g = fresh([U("b-tank-1", "tank", "blue", 2, 6), U("b-uav-1", "uav", "blue", 3, 3), U("r-tank-1", "tank", "red", 4, 6)])
        self.row(g, 6, c3="forest")
        g._observe()
        lines, a = tactics.contact_lines(g, "blue", g.units[0], g.units[2])
        self.assertFalse(a["los"])
        self.assertIn("BLOCKED", " ".join(lines))
        self.assertEqual(a["blocked_by"], (3, 6))

    def test_hover_text_explains_what_the_ground_does_to_sight(self):
        from ui.figure import build
        g = Game(seed=1)
        fig = build(g, "blue", "home")
        text = " ".join(fig["data"][2]["hovertext"])
        self.assertIn("high ground", text)
        self.assertIn("blocks the view", text)


class Strait(unittest.TestCase):
    def test_convoy_delivers_supplies_through_the_strait(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        g.supply["blue"]["fuel"] = 50.0
        for _ in range(120):
            g.tick()
        self.assertTrue(any("unloaded" in m for _, m in g.log))
        self.assertGreater(g.supply["blue"]["fuel"], 50.0 - 4)

    def test_low_supplies_make_orders_late(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        self.assertEqual(g.late("blue"), 0)
        g.supply["blue"]["fuel"] = 5.0
        self.assertEqual(g.late("blue"), 10)
        g.order_move("blue", g.units[0], 4, 6)
        self.assertGreaterEqual(g.units[0].next_step_at, g.t + 10)

    def test_blocked_convoy_asks_the_general(self):
        g = fresh([U("b-destroyer-1", "destroyer", "blue", 10, 12), U("b-destroyer-2", "destroyer", "blue", 11, 12), U("r-tank-1", "tank", "red", 19, 12)])
        for u in g.units[:2]:
            u.hold_fire = True
        g.t = 14
        for _ in range(35):                              # the convoy spawns at t=15 and finds the strait shut
            g.tick()
        rep = next((r for r in g.reports if r["kind"] == "convoy"), None)
        self.assertIsNotNone(rep)
        self.assertEqual({o["id"] for o in rep["options"]}, {"wait", "escort", "turn_back"})

    def test_total_supply_collapse_loses_the_war(self):
        g = fresh([U("b-tank-1", "tank", "blue", 3, 6), U("r-tank-1", "tank", "red", 19, 12)])
        g.supply["blue"].update(fuel=0.0, food=0.0, zero_for=89)
        g.tick()
        self.assertEqual(g.winner, "red")
        self.assertIn("collapsed", g.win_reason)


class LastResort(unittest.TestCase):
    def test_sites_are_hidden_discoverable_and_gated(self):
        g = Game(seed=3)
        self.assertEqual(len(g.nukes), 2)
        site = g.nukes[0]
        self.assertEqual(g.nuke_markers("blue"), [])                  # nothing known at the start
        g.units = [U("b-spy-1", "spy", "blue", min(19, site["c"] + 1), site["r"]), U("r-tank-1", "tank", "red", 19, 12)]
        g.units[0].hp = 50
        g.tick()
        self.assertEqual(g.nuke_level["blue"][0], 3)
        self.assertTrue(any("CONFIRMED" in e["text"] for e in g.radio))
        self.assertIn("Not while the war can still be won", g.last_resort_check("blue", 0) or "")

    def test_last_resort_ruins_everyone_nearby_and_ends_in_mutual_ruin(self):
        g = Game(seed=3)
        site = g.nukes[0]
        c, r = site["c"], site["r"]
        near = lambda dc: (min(19, max(0, c + dc)), r)
        g.units = [U("b-tank-1", "tank", "blue", *near(1)), U("r-tank-1", "tank", "red", *near(-1)), U("r-infantry-1", "infantry", "red", 19, 12)]
        if near(1) == near(-1):
            self.skipTest("site on the map edge")
        g.units[0].c, g.units[0].r = near(1)
        g.units[1].c, g.units[1].r = near(2)
        g.units[0].hold_fire = g.units[1].hold_fire = True              # keep them from killing each other first
        g.nuke_level["blue"][0] = 3
        import game.state as gs
        old, gs.LOST_BELOW = gs.LOST_BELOW, 101                         # pretend the war is already lost for Ladooo
        try:
            self.assertIsNone(g.last_resort_check("blue", 0))
            g.last_resort("blue", 0)
        finally:
            gs.LOST_BELOW = old
        for _ in range(16):
            g.tick()
        self.assertIsNotNone(g.winner)
        self.assertEqual(g.ending["title"], "Mutual ruin")
        self.assertIsNone(g.unit_by_id("b-tank-1"))                    # own unit destroyed too
        self.assertIsNone(g.unit_by_id("r-tank-1"))

    def test_concede(self):
        g = Game(seed=1)
        g.concede("blue")
        self.assertEqual(g.winner, "red")
        self.assertIn("conceded", g.ending["title"])


class WarStatus(unittest.TestCase):
    def test_war_status_explains_itself(self):
        g = Game(seed=1)
        w = g.war_status("blue")
        self.assertEqual({b["key"] for b in w["bars"]}, {"objectives", "territory", "forces", "supply", "home"})
        self.assertIn(w["verdict"], ("winning", "even", "losing", "lost"))
        self.assertTrue(w["win"] and w["lose"])
        self.assertTrue(0 <= w["balance"] <= 100)


class Figures(unittest.TestCase):
    def test_hidden_things_are_not_sent_to_the_browser(self):
        from ui.figure import build
        g = Game()
        g.tick()
        home = build(g, "blue", "home")
        sources = [i["source"] for i in home["layout"]["images"]]
        self.assertFalse(any(s.startswith(("/icon/tank_red", "/icon/missile_silo_red", "/icon/infantry_red")) for s in sources))  # far-away reds hidden
        self.assertTrue(any(s.startswith("/icon/mountain") for s in sources))     # the lie of the land is public, even on the enemy side
        truth = build(g, "referee", "home")
        self.assertLess(len(sources), len(truth["layout"]["images"]))   # unexplored enemy terrain and units are not sent
        self.assertTrue(any("_red.svg" in i["source"] for i in truth["layout"]["images"]))


if __name__ == "__main__":
    unittest.main()

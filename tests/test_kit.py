"""Offline tests for the doctrine kit. Run as a plain script or with unittest."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from tic_doctrine import confidence, contract, likelihood, lint, registers, tips, vocab, withhold  # noqa: E402
from tic_doctrine.confidence import Evidence  # noqa: E402

GOOD = json.loads((ROOT / "tests" / "fixtures" / "good.geojson").read_text(encoding="utf-8"))


class Likelihood(unittest.TestCase):
    def test_bands_and_edges(self):
        cases = {0.0: "almost_no_chance", 0.049: "almost_no_chance", 0.05: "very_unlikely", 0.199: "very_unlikely",
                 0.2: "unlikely", 0.449: "unlikely", 0.45: "roughly_even_chance", 0.5: "roughly_even_chance",
                 0.55: "roughly_even_chance", 0.551: "likely", 0.8: "likely", 0.801: "very_likely",
                 0.95: "very_likely", 0.951: "almost_certain", 1.0: "almost_certain"}
        for p, want in cases.items():
            self.assertEqual(likelihood.term_for(p)["id"], want, p)

    def test_symmetry(self):
        # A probability and its complement sit the same number of steps from the middle.
        for i in range(0, 101):
            p = i / 100
            a, b = likelihood.term_for(p)["step"], likelihood.term_for(round(1 - p, 2))["step"]
            self.assertEqual(a - 3, 3 - b, p)

    def test_label_and_rejects(self):
        self.assertEqual(likelihood.label(0.7), "Likely (55-80%)")
        for bad in (-0.1, 1.1, "0.5", None, True):
            with self.assertRaises(ValueError):
                likelihood.term_for(bad)

    def test_normalise_and_change(self):
        n = likelihood.normalise({"a": 0.6, "b": 0.6})
        self.assertAlmostEqual(sum(n.values()), 1.0)
        self.assertEqual(likelihood.change(None, 0.7), "new")
        self.assertEqual(likelihood.change(0.5, 0.7), "raised")
        self.assertEqual(likelihood.change(0.7, 0.6), "unchanged")
        self.assertEqual(likelihood.change(0.9, 0.3), "lowered")


class Confidence(unittest.TestCase):
    def test_lines_set_the_start(self):
        self.assertEqual(confidence.assess(Evidence(independent_lines=1, method_scored=True))["level"], "low")
        self.assertEqual(confidence.assess(Evidence(independent_lines=2, method_scored=True))["level"], "moderate")
        self.assertEqual(confidence.assess(Evidence(independent_lines=3, method_scored=True))["level"], "high")
        self.assertEqual(confidence.assess(Evidence(independent_lines=3, contradicted=True, method_scored=True))["level"], "moderate")

    def test_caps(self):
        base = dict(independent_lines=4, method_scored=True)
        self.assertEqual(confidence.assess(Evidence(**base, data_age_s=3 * 3600, expected_cadence_s=3600))["level"], "low")
        self.assertEqual(confidence.assess(Evidence(**base, coverage_fraction=0.3))["level"], "low")
        self.assertEqual(confidence.assess(Evidence(**base, grades=["B2", "E3"]))["level"], "moderate")
        self.assertEqual(confidence.assess(Evidence(**base, grades=["B5"]))["level"], "moderate")
        self.assertEqual(confidence.assess(Evidence(**base, alternatives_rejected=0))["level"], "moderate")
        self.assertEqual(confidence.assess(Evidence(independent_lines=4))["level"], "moderate")  # no track record
        self.assertEqual(confidence.assess(Evidence(**base, ease_of_faking="high"))["level"], "moderate")
        self.assertEqual(confidence.assess(Evidence(**base, horizon_days=365))["level"], "moderate")
        self.assertEqual(confidence.assess(Evidence(**base, assumption_status="strained"))["level"], "moderate")

    def test_broken_assumption_blocks(self):
        r = confidence.assess(Evidence(independent_lines=4, method_scored=True, assumption_status="broken"))
        self.assertTrue(r["blocked"])
        self.assertEqual(r["level"], "low")

    def test_raise_by_and_fields(self):
        r = confidence.assess(Evidence(independent_lines=1))
        self.assertTrue(r["raise_by"])
        self.assertEqual(r["label"], "Rule-based, not statistical")
        f = confidence.fields(Evidence(independent_lines=3, method_scored=True, alternatives_rejected=1))
        self.assertEqual(f["confidence"], "high")
        self.assertEqual(f["confidence_basis"]["raise_by"], [])


class Contract(unittest.TestCase):
    def problems(self, item):
        return [(s, m) for s, sev, m in contract.check(item) if sev == "error"]

    def test_good_feed_passes(self):
        for f in GOOD["features"]:
            self.assertEqual(self.problems(f), [], f["properties"]["id"])

    def test_each_standard_catches_its_gap(self):
        warning = next(f for f in GOOD["features"] if f["properties"]["tier"] == "warning")
        cases = [
            ("sources", lambda p: p.pop("sources")),
            ("uncertainty", lambda p: p.__setitem__("likelihood_term", "very_likely")),
            ("distinguish", lambda p: p.__setitem__("kind", "observation")),
            ("alternatives", lambda p: p.pop("alternatives")),
            ("relevance", lambda p: (p.pop("requirement_ids"), p.pop("warning_problem_id"))),
            ("argumentation", lambda p: p.pop("summary")),
            ("change", lambda p: p.pop("change_reason")),
            ("accuracy", lambda p: p.pop("resolution")),
        ]
        for std, mutate in cases:
            f = copy.deepcopy(warning)
            mutate(f["properties"])
            self.assertIn(std, [s for s, _ in self.problems(f)], std)
        f = copy.deepcopy(warning)
        f["geometry"] = None
        f["properties"]["precision_class"] = "none"
        self.assertIn("visual", [s for s, _ in self.problems(f)])

    def test_general_rules(self):
        f = copy.deepcopy(GOOD["features"][0])
        p = f["properties"]
        p["us_person_data"] = "some"
        p["data_as_of"] = "2026-10-30 12:00"
        p["ncf"] = ["provide_pnt"]
        p["sector"] = ["energy"]
        p["response_stage"] = "pager:purple"
        msgs = " ".join(m for _, m in self.problems(f))
        for needle in ("us_person_data", "data_as_of", "sector does not match", "response_stage"):
            self.assertIn(needle, msgs)

    def test_data_as_of_precision(self):
        """A date-only or month-only data_as_of is midnight UTC (on the 1st for a month)."""
        def msgs(prec, asof):
            f = copy.deepcopy(GOOD["features"][0])
            f["properties"]["data_as_of_precision"] = prec
            f["properties"]["data_as_of"] = asof
            return " ".join(m for _, m in self.problems(f))
        self.assertNotIn("data_as_of_precision", msgs("day", "2026-10-30T00:00:00Z"))
        self.assertNotIn("data_as_of_precision", msgs("month", "2025-06-01T00:00:00Z"))
        self.assertIn("data_as_of_precision", msgs("day", "2026-10-30T12:00:00Z"))
        self.assertIn("data_as_of_precision", msgs("month", "2025-06-15T00:00:00Z"))
        self.assertIn("data_as_of_precision", msgs("week", "2025-06-01T00:00:00Z"))

    def test_usgs_volcano_ladder(self):
        """USGS Volcano Alert Levels are a response_stage; UNASSIGNED is not a rung."""
        for value in ("normal", "advisory", "watch", "warning"):
            f = copy.deepcopy(GOOD["features"][0])
            f["properties"]["response_stage"] = f"usgs_volcano:{value}"
            self.assertNotIn("response_stage", " ".join(m for _, m in self.problems(f)), value)
        f = copy.deepcopy(GOOD["features"][0])
        f["properties"]["response_stage"] = "usgs_volcano:unassigned"
        self.assertIn("response_stage", " ".join(m for _, m in self.problems(f)))
        rungs = vocab.ladders()["usgs_volcano"]["values"]
        self.assertEqual([rungs[v]["severity"] for v in ("normal", "advisory", "watch", "warning")], [0, 1, 2, 4])

    def test_us_person_data_is_a_label(self):
        for value in ("none", "organizations", "individuals"):
            f = copy.deepcopy(GOOD["features"][0])
            f["properties"]["us_person_data"] = value
            self.assertNotIn("us_person_data", " ".join(m for _, m in self.problems(f)))
        f = copy.deepcopy(GOOD["features"][0])
        del f["properties"]["us_person_data"]
        self.assertIn("us_person_data missing", " ".join(m for _, m in self.problems(f)))

    # Actors: roles as the sources describe them, never friend or foe.
    def actor_item(self):
        return copy.deepcopy(next(f for f in GOOD["features"] if f["properties"].get("actors")))

    def messages(self, item, severity="error"):
        return " ".join(m for _, sev, m in contract.check(item) if sev == severity)

    def test_actor_vocabulary_is_neutral(self):
        never = contract._never_re()
        for k, r in vocab.actor_roles().items():
            self.assertIn(r["frame"], ("unknown", "neutral"), k)
            self.assertIsNone(never.search(" ".join([k.replace("_", " "), r["label"], r["meaning"]])), k)
        for k, t in vocab.actor_types().items():
            self.assertIsNone(never.search(" ".join([k.replace("_", " "), t["label"], t["meaning"]])), k)

    def test_actor_rules(self):
        cases = [
            ("role='hostile'", lambda a, p: a.__setitem__("role", "hostile")),
            ("needs side", lambda a, p: a.pop("side")),
            ("judges friend or foe", lambda a, p: a.__setitem__("side", "Enemy forces")),
            ("status_class must be", lambda a, p: a.__setitem__("status_class", "rumoured")),
            ("not a sources[].id", lambda a, p: a.__setitem__("source_ids", ["nowhere"])),
            ("actor_type='terrorists'", lambda a, p: a.__setitem__("actor_type", "terrorists")),
            ("actors name organizations", lambda a, p: p.__setitem__("us_person_data", "none")),
            ("country must be", lambda a, p: a.__setitem__("country", "Russia")),
            ("designations[0] needs by and label", lambda a, p: a.__setitem__("designations", [{"by": "US Treasury"}])),
        ]
        for needle, mutate in cases:
            f = self.actor_item()
            mutate(f["properties"]["actors"][0], f["properties"])
            self.assertIn(needle, self.messages(f), needle)
        f = self.actor_item()
        f["properties"]["actors"] = "Russia"
        self.assertIn("actors must be a list", self.messages(f))

    def test_friend_or_foe_words_match_whole_words_only(self):
        f = self.actor_item()
        f["properties"]["actors"][0]["side"] = "Friends of the Port Association"
        self.assertNotIn("friend or foe", self.messages(f))

    def test_responsible_needs_evidence_and_a_judgment(self):
        f = self.actor_item()
        a = f["properties"]["actors"][0]
        a["role"] = "responsible"
        a.pop("source_ids")
        self.assertIn("needs source_ids", self.messages(f))
        f = self.actor_item()
        a = f["properties"]["actors"][0]
        a["role"], a["status_class"] = "responsible", "assessed"
        self.assertIn("is a judgment", self.messages(f))
        a["status_class"] = "claimed"  # a group claiming an attack is a reported fact, not the suite's attribution
        self.assertEqual(self.messages(f), "")

    def test_individuals_civilians_and_third_parties(self):
        f = self.actor_item()
        f["properties"]["actors"].append({"name": "A named port official", "role": "affected", "actor_type": "individual",
                                          "status_class": "reported", "source_ids": ["agency-ua"]})
        self.assertIn("us_person_data must be 'individuals'", self.messages(f))
        f["properties"]["us_person_data"] = "individuals"
        self.assertEqual(self.messages(f), "")
        f = self.actor_item()
        f["properties"]["actors"][2]["actor_type"] = "individual"
        self.assertIn("never named individuals", self.messages(f))
        f = self.actor_item()
        f["properties"]["actors"].append({"name": "Monitoring mission", "role": "third_party", "actor_type": "intergovernmental",
                                          "function": "monitor", "side": "Ukraine", "status_class": "reported"})
        self.assertEqual(self.messages(f), "")
        self.assertIn("third party has no side", self.messages(f, "warning"))

    def test_source_owner_and_perspective(self):
        f = self.actor_item()
        f["properties"]["sources"][0]["owner"] = "government"
        f["properties"]["sources"][1]["perspective"] = " "
        msgs = self.messages(f)
        self.assertIn("owner='government'", msgs)
        self.assertIn("perspective must be", msgs)

    def test_derive_sectors(self):
        self.assertEqual(vocab.derive_sectors(["provide_pnt"]), ["communications", "transportation_systems"])
        self.assertEqual(len(vocab.ncf()), 55)
        self.assertEqual(len(vocab.sectors()), 16)
        self.assertEqual(len(vocab.lifelines()["values"]), 8)


class Linter(unittest.TestCase):
    def test_report(self):
        rep = lint.lint_files([ROOT / "tests" / "fixtures" / "good.geojson"])
        self.assertEqual(rep["items"], len(GOOD["features"]))
        self.assertFalse(any(v["error"] for v in rep["standards"].values()), rep)


class Geo(unittest.TestCase):
    def test_points_sit_inside_their_country(self):
        from tic_doctrine import geo
        for cc in ("UA", "US", "DE", "BR", "JP", "ZA", "XK", "TW"):
            lat, lon = geo.point(cc)
            self.assertEqual(geo.country_at(lat, lon), cc)
        self.assertIsNone(geo.point("ZZ"))

    def test_codes_pass_the_feed_contract(self):
        """Every code geo can emit passes the contract's ISO 3166-1 alpha-2 check (Natural Earth's CN-TW did not)."""
        from tic_doctrine import geo
        countries = json.loads(geo.FILE.read_text(encoding="utf-8"))["countries"]
        points = json.loads(geo.POINTS.read_text(encoding="utf-8"))["points"]
        bad = [c["cc"] for c in countries if not contract.COUNTRY_RE.match(c["cc"])]
        bad += [cc for cc in points if not contract.COUNTRY_RE.match(cc)]
        self.assertEqual(bad, [])
        self.assertEqual(sorted({c["cc"] for c in countries}), sorted(points), "one label point per code")
        self.assertEqual(geo.country_at(25.03, 121.56), "TW")       # Taipei
        self.assertEqual(geo.countries_in([(25.03, 121.56), (39.9, 116.4)]), ["CN", "TW"])

    def test_names_are_full(self):
        """Natural Earth's map labels ("S. Sudan", "Dem. Rep. Congo") are written out."""
        from tic_doctrine import geo
        countries = json.loads(geo.FILE.read_text(encoding="utf-8"))["countries"]
        short = [c["name"] for c in countries if "." in c["name"] or c["name"].startswith("St-") or "." in c.get("part", "")]
        self.assertEqual(short, [])
        for cc, want in (("SS", "South Sudan"), ("CD", "Democratic Republic of the Congo"),
                         ("CG", "Republic of the Congo"), ("BA", "Bosnia and Herzegovina"), ("TW", "Taiwan"),
                         ("AU", "Australia"), ("au", "Australia"), ("BR", "Brazil")):
            self.assertEqual(geo.name(cc), want, cc)
        self.assertIsNone(geo.name("ZZ"))
        self.assertIsNone(geo.name(None))

    def test_builder_rules(self):
        """A rebuild from Natural Earth keeps TW and the full names (tools/build_countries.py)."""
        sys.path.insert(0, str(ROOT / "tools"))
        import build_countries as bc
        self.assertEqual(bc.code({"ISO_A2": "CN-TW", "ISO_A2_EH": "-99"}), "TW")
        self.assertEqual(bc.code({"ISO_A2": "CN-TW", "ISO_A2_EH": "TW"}), "TW")
        self.assertEqual(bc.code({"ISO_A2": "-99", "ISO_A2_EH": "FR"}), "FR")
        self.assertIsNone(bc.code({"ISO_A2": "-99", "ISO_A2_EH": "-99"}))
        self.assertEqual(bc.entry("SS", "S. Sudan"), {"cc": "SS", "name": "South Sudan"})
        self.assertEqual(bc.entry("AU", "Ashmore and Cartier Is."),
                         {"cc": "AU", "name": "Australia", "part": "Ashmore and Cartier Islands"})
        self.assertEqual(bc.entry("BR", "Brazil"), {"cc": "BR", "name": "Brazil"})


class Registers(unittest.TestCase):
    def test_template_registers_pass(self):
        errs = registers.check(ROOT / "templates" / "doctrine")
        self.assertEqual(errs, [])


def _bus_item(program, iid, title, countries, tier="routine", **extra):
    p = {"program": program, "id": iid, "title": title, "countries": countries, "tier": tier, "kind": "observation",
         "status_class": "reported", "data_as_of": "2026-11-01T00:00:00Z", "published_at": "2026-11-01T00:05:00Z",
         "sources": [{"publisher": "Upstream", "licence": "x", "lineage_id": f"up:{iid}", "independence_group": "upstream"}]}
    p.update(extra)
    return {"type": "Feature", "geometry": None, "properties": p}


BUS = {"type": "FeatureCollection", "contract": "tic-feed/2", "program": "cop", "features": [
    _bus_item("cordon", "c1", "Ukraine: Level 4, Do Not Travel", ["UA"], response_stage="state_travel_advisory:level_4",
              measures={"level": 4}),
    _bus_item("cordon", "c2", "Poland: Level 1, Exercise Normal Precautions", ["PL"],
              response_stage="state_travel_advisory:level_1", measures={"level": 1}),
    _bus_item("cordon", "c3", "Sudan: US embassy has suspended operations", ["SD"],
              response_stage="state_post_posture:suspended_operations"),
    _bus_item("noisefloor", "n1", "GPS interference newly seen near Kaliningrad", ["RU", "LT"], tier="anomaly"),
    _bus_item("noisefloor", "n2", "GPS interference newly seen near Las Vegas", ["US"], tier="anomaly"),
    _bus_item("vigil", "v1", "Group escalating", [], tier="anomaly"),
    _bus_item("watchfloor", "w1", "Ukraine Conflict: attention 2x normal", ["UA"], tier="anomaly"),
]}
for f in BUS["features"][3:4]:
    f["properties"]["cop_program"] = f["properties"].pop("program")  # the bus may carry only COP's tag
INTERESTS = {"program": "watchfloor",
             "areas": {"WF-WP-Z01": ["UA"], "WF-WP-Z07": ["RU", "PL", "LT"], "WF-WP-Z13": ["SD"]},
             "interests": [
                 {"id": "WF-INT-1", "about": "Advisories at level 3 or 4", "programs": ["cordon"],
                  "response_stage_prefix": ["state_travel_advisory:"],
                  "where": [{"path": "measures.level", "op": "gte", "value": 3}], "fingerprint": ["measures.level"]},
                 {"id": "WF-INT-2", "about": "Embassy posture", "programs": ["cordon"],
                  "response_stage_prefix": ["state_post_posture:"]},
                 {"id": "WF-INT-3", "about": "New GPS interference", "programs": ["noisefloor"], "tiers": ["anomaly"]},
                 {"id": "WF-INT-4", "about": "Cyber surges anywhere", "programs": ["vigil"], "tiers": ["anomaly"],
                  "global": True},
                 {"id": "WF-INT-5", "about": "own items never tip", "programs": ["cordon", "noisefloor", "vigil"],
                  "title_any": ["attention"]}]}
NOW = __import__("datetime").datetime(2026, 11, 1, 3, 0, tzinfo=__import__("datetime").timezone.utc)


class Tips(unittest.TestCase):
    def items(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bus.geojson"
            p.write_text(json.dumps(BUS), encoding="utf-8")
            return tips.load(str(p))[1]

    def test_registry(self):
        reg = tips.registry()
        ids = [p["id"] for p in reg["programs"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(reg["bus"]["url"].startswith("https://"))
        for p in reg["programs"]:
            self.assertIn(p["status"], {"live", "planned"})
            self.assertTrue(p.get("owns"), p["id"])
            if p["status"] == "live":
                self.assertTrue(p["feed"].startswith("https://") and p.get("terms") and p.get("stale_hours"), p["id"])

    def test_matching_areas_and_self(self):
        found = tips.tips(self.items(), INTERESTS, now=NOW)
        got = {(t["interest_id"], t["item_id"], tuple(t["areas"])) for t in found}
        self.assertEqual(got, {("WF-INT-1", "c1", ("WF-WP-Z01",)),          # level 4 in Ukraine; level 1 Poland fails where
                               ("WF-INT-2", "c3", ("WF-WP-Z13",)),
                               ("WF-INT-3", "n1", ("WF-WP-Z07",)),          # Las Vegas is outside every area
                               ("WF-INT-4", "v1", ())})                    # global: no country needed
        self.assertFalse(any(t["program"] == "watchfloor" for t in found))
        self.assertEqual(next(t for t in found if t["item_id"] == "n1")["program"], "noisefloor")  # from cop_program

    def test_gather_reads_programs_the_bus_lacks(self):
        bus_items = self.items()
        verdict_feed = "https://metacog-osint.github.io/verdict/data/calendar.geojson"
        calls = []

        def fetch(src):
            calls.append(src)
            if src == "BUS":
                return {}, bus_items
            if src == verdict_feed:
                return {}, [{"_program": "verdict", "id": "e1", "title": "EASA bulletin expires", "countries": ["UA"]}]
            raise OSError("down")
        doc = copy.deepcopy(INTERESTS)
        doc["interests"].append({"id": "WF-INT-9", "about": "dates", "programs": ["verdict", "elements"]})
        items, problems = tips.gather(doc, bus="BUS", fetch=fetch)
        self.assertIn(verdict_feed, calls)                                   # not on the bus: read directly
        self.assertNotIn(tips.program_entry("cordon")["feed"], calls)       # on the bus: not fetched again
        self.assertEqual([p["source"] for p in problems], ["elements"])     # a failed feed is reported, not hidden
        self.assertIn("e1", {i["id"] for i in items})
        items, problems = tips.gather(doc, bus="DOWN", fetch=fetch)          # bus down: direct feeds for everything
        self.assertEqual(problems[0]["source"], "bus")
        self.assertIn("e1", {i["id"] for i in items})

    def test_anywhere(self):
        doc = {"program": "watchfloor", "areas": INTERESTS["areas"],
               "interests": [{"id": "WF-INT-6", "about": "GPS interference worldwide", "programs": ["noisefloor"],
                              "tiers": ["anomaly"], "anywhere": True}]}
        items = self.items() + [{"_program": "noisefloor", "id": "n3", "title": "no place", "tier": "anomaly",
                                 "countries": []}]
        got = {t["item_id"]: t["areas"] for t in tips.tips(items, doc, now=NOW)}
        self.assertEqual(got, {"n1": ["WF-WP-Z07"], "n2": [], "n3": []})  # inside an area, outside, no country

    def test_geometry_and_boxes_place_offshore_and_land_items(self):
        doc = {"program": "watchfloor",
               "areas": {"WF-WP-Z01": ["UA"], "WF-WP-Z02": ["TW"]},
               "boxes": {"WF-WP-Z02": [117.0, 21.0, 123.5, 26.5]},
               "interests": [{"id": "WF-INT-4", "about": "NGA warnings", "programs": ["cordon"], "anywhere": True}]}
        items = [
            {"_program": "cordon", "id": "g1", "title": "Black Sea / Odesa coast", "tier": "routine", "countries": [],
             "_geometry": {"type": "Point", "coordinates": [30.73, 46.48]}},  # Odesa land point -> UA
            {"_program": "cordon", "id": "g2", "title": "Taiwan Strait firing exercise", "tier": "anomaly",
             "countries": [], "_geometry": {"type": "Polygon", "coordinates": [[[119.5, 24.0], [120.2, 24.0],
                                                                                [120.2, 24.6], [119.5, 24.6],
                                                                                [119.5, 24.0]]]}},  # at sea inside box
            {"_program": "cordon", "id": "g3", "title": "Mid-Atlantic buoy", "tier": "routine", "countries": [],
             "_geometry": {"type": "Point", "coordinates": [-40.0, 30.0]}},
        ]
        got = {t["item_id"]: t["areas"] for t in tips.tips(items, doc, now=NOW)}
        self.assertEqual(got, {"g1": ["WF-WP-Z01"], "g2": ["WF-WP-Z02"], "g3": []})
        self.assertEqual(tips.check_interests(doc), [])

    def test_stale(self):
        items = self.items()
        items[0]["cop_stale"] = True                                # COP kept this feed's last good items
        items[2]["_feed_generated"] = "2026-10-01T00:00:00Z"        # read directly from a feed built a month ago
        items[3]["cop_stale"] = False
        items[3]["data_as_of"] = "2023-05-01T00:00:00Z"             # an old standing notice is still current
        found = {t["item_id"]: t["stale"] for t in tips.tips(items, INTERESTS, now=NOW)}
        self.assertTrue(found["c1"] and found["c3"])
        self.assertFalse(found["n1"])

    def test_diff_ignores_title_counts(self):
        before = tips.tips(self.items(), INTERESTS, now=NOW)
        items = self.items()
        items[0]["title"] = "Ukraine: Level 4, Do Not Travel (text revised)"
        items[0]["measures"] = {"level": 4}
        same = tips.diff(before, tips.tips(items, INTERESTS, now=NOW))
        self.assertEqual((same["new"], same["changed"], same["ended"]), ([], [], []))
        items[3]["tier"] = "routine"  # interference no longer an anomaly: the tip ends
        items[2]["response_stage"] = "state_post_posture:ordered_departure"
        d = tips.diff(before, tips.tips(items, INTERESTS, now=NOW))
        self.assertEqual([t["item_id"] for t in d["changed"]], ["c3"])
        self.assertEqual([t["item_id"] for t in d["ended"]], ["n1"])

    def test_cite_passes_the_contract(self):
        tip = next(t for t in tips.tips(self.items(), INTERESTS, now=NOW) if t["item_id"] == "c1")
        src = tips.cite(tip, accessed_at=NOW)
        self.assertEqual((src["lineage_id"], src["independence_group"]), ("up:c1", "upstream"))  # upstream carried
        self.assertEqual(src["publisher"], "Cordon, The Intelligence Company")
        self.assertEqual(src["url"], "https://cordon.theintelligence.company/data/feed.geojson")  # no item link: the feed
        item = copy.deepcopy(GOOD["features"][0])
        item["properties"]["sources"] = [src]
        self.assertEqual([e for e in contract.check(item) if e[0] == "sources" and e[1] == "error"], [])
        item["properties"]["sources"] = [{"publisher": "x"}]  # the check itself catches a bare source
        self.assertTrue([e for e in contract.check(item) if e[0] == "sources" and e[1] == "error"])
        tip["upstream"] = [{"lineage_id": "a", "independence_group": "g1"}, {"lineage_id": "b", "independence_group": "g2"}]
        src = tips.cite(tip, accessed_at=NOW)
        self.assertEqual((src["lineage_id"], src["independence_group"]), ("cordon:c1", "g1+g2"))

    def test_check_interests(self):
        self.assertEqual(tips.check_interests(INTERESTS), [])
        bad = copy.deepcopy(INTERESTS)
        bad["interests"] += [{"id": "WF-INT-1", "about": "dup", "programs": ["watchfloor", "nosuch"],
                              "areas": ["WF-WP-Z99"], "tiers": ["loud"], "where": [{"path": "x", "op": "~"}]}]
        bad["areas"]["X"] = ["ukr"]
        errs = " | ".join(tips.check_interests(bad))
        for want in ("duplicate id", "unknown program 'nosuch'", "does not tip itself", "unknown area 'WF-WP-Z99'",
                     "tiers has unknown values", "where needs", "ISO alpha-2"):
            self.assertIn(want, errs)

    def test_registers_check_interests(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "doctrine"
            shutil.copytree(ROOT / "templates" / "doctrine", folder)
            doc = copy.deepcopy(INTERESTS)
            doc["interests"][0]["indicator_id"] = "XX-IND-404"
            (folder / "interests.json").write_text(json.dumps(doc), encoding="utf-8")
            errs = registers.check(folder)
            self.assertTrue(any("XX-IND-404" in e for e in errs), errs)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "doctrine"
            folder.mkdir()
            (folder / "interests.json").write_text(json.dumps(INTERESTS), encoding="utf-8")
            bus = Path(d) / "bus.geojson"
            bus.write_text(json.dumps(BUS), encoding="utf-8")
            out = Path(d) / "tips.json"
            self.assertEqual(tips.main([str(folder), "--bus", str(bus), "--json", str(out)]), 0)
            self.assertEqual(len(json.loads(out.read_text(encoding="utf-8"))), 4)


class Withhold(unittest.TestCase):
    def test_counts_only(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "w.jsonl"
            withhold.record(log, "watchfloor", "threat_to_person", "named official, zone 13", "FBI tips", "TB")
            out = withhold.counts(log)
            self.assertEqual(out["months"][0]["total"], 1)
            self.assertNotIn("named official", json.dumps(out))


class Vendoring(unittest.TestCase):
    def test_kitcheck_survives_crlf_and_catches_edits(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            subprocess.run([sys.executable, str(ROOT / "tools" / "sync.py"), str(repo)], check=True,
                           capture_output=True)
            kit = repo / "doctrine" / "kit"
            check = lambda: subprocess.run([sys.executable, str(kit / "tic.py"), "kitcheck"],  # noqa: E731
                                           capture_output=True).returncode
            self.assertEqual(check(), 0)
            doc = kit / "docs" / "language-key.md"
            # what a Windows checkout does: LF first, so a file that is already CRLF stays CRLF, not \r\r\n
            doc.write_bytes(doc.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            self.assertEqual(check(), 0)
            doc.write_bytes(doc.read_bytes() + b"edited\r\n")
            self.assertEqual(check(), 1)


if __name__ == "__main__":
    unittest.main()

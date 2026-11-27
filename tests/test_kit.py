"""Offline tests for the doctrine kit. Run as a plain script or with unittest."""

import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from tic_doctrine import CONTRACT_REV, confidence, contract, ladder, likelihood, lint, registers, tips, vocab, withhold  # noqa: E402
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

    def test_subdivisions(self):
        f = copy.deepcopy(GOOD["features"][0])
        p = f["properties"]
        p["countries"] = ["US"]
        p["subdivisions"] = ["US-HI"]
        self.assertEqual(self.problems(f), [])
        p["subdivisions"] = ["Hawaii"]
        self.assertIn("ISO 3166-2", " ".join(m for _, m in self.problems(f)))
        p["subdivisions"] = ["CA-ON"]
        self.assertIn("also be in countries", " ".join(m for _, m in self.problems(f)))

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

    def test_us_states_at_points(self):
        from tic_doctrine import geo
        for name, lat, lon, want in (("Kilauea", 19.421, -155.287, "US-HI"), ("Great Sitkin", 52.076, -176.13, "US-AK"),
                                     ("Fargo", 46.8772, -96.7898, "US-ND"), ("Moorhead", 46.8738, -96.7676, "US-MN"),
                                     ("Kansas City KS", 39.11, -94.63, "US-KS"), ("San Juan", 18.46, -66.1, None),
                                     ("Windsor ON", 42.30, -83.03, None), ("Gulf of Mexico", 27.0, -90.0, None)):
            self.assertEqual(geo.subdivision_at(lat, lon), want, name)
        ring = {"type": "Polygon", "coordinates": [[[-96.9, 46.8], [-96.6, 46.8], [-96.6, 46.95], [-96.9, 46.95],
                                                    [-96.9, 46.8]]]}
        self.assertEqual(geo.subdivisions_for_geometry(ring), ["US-MN", "US-ND"])
        dc = {"type": "Polygon", "coordinates": [[[-77.34, 38.59], [-76.74, 38.59], [-76.74, 39.19], [-77.34, 39.19],
                                                  [-77.34, 38.59]]]}
        self.assertEqual(geo.subdivisions_for_geometry(dc), ["US-DC", "US-MD", "US-VA"])  # DC holds no vertex
        subs = json.loads(geo.SUBDIVISIONS.read_text(encoding="utf-8"))["subdivisions"]
        self.assertEqual(len(subs), 51)
        self.assertTrue(all(contract.SUBDIVISION_RE.match(s["code"]) for s in subs))

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


GOOD21_PATH = ROOT / "tests" / "fixtures" / "good-2.1.geojson"
GOOD21 = json.loads(GOOD21_PATH.read_text(encoding="utf-8"))


def _by_id(doc, iid):
    return copy.deepcopy(next(f for f in doc["features"] if f["properties"]["id"] == iid))


class Revision21(unittest.TestCase):
    """Kit 0.6.0, contract revision 2.1: new fields are optional; their shape is an error, their absence a notice."""

    def errors(self, item, rev=None):
        return " | ".join(m for s, sev, m in contract.check(item, rev=rev) if sev == "error")

    def notices(self, item, rev=None):
        return [m for s, sev, m in contract.check(item, rev=rev) if s == contract.REVISION]

    def test_the_old_fixture_still_passes_with_notices_only(self):
        rep = lint.lint_files([ROOT / "tests" / "fixtures" / "good.geojson"])
        self.assertFalse(any(v["error"] for v in rep["standards"].values()), rep)
        self.assertGreater(rep["standards"]["revision"]["warning"], 0)
        self.assertEqual(set(rep["coverage"].values()), {0})
        self.assertEqual(lint.main([str(ROOT / "tests" / "fixtures" / "good.geojson")]), 0, "a notice never fails")

    def test_the_2_1_fixture_is_clean_in_strict_mode(self):
        self.assertEqual(GOOD21["contract_rev"], "2.1")
        rep = lint.lint_files([GOOD21_PATH])
        self.assertFalse(any(v["error"] for v in rep["standards"].values()), rep)
        self.assertNotIn("revision", rep["standards"], rep["standards"].get("revision"))
        self.assertEqual(rep["coverage"]["subject_id"], 4)
        for f in GOOD21["features"]:
            self.assertEqual(self.errors(f, rev="2.1"), "", f["properties"]["id"])

    def test_each_field_has_its_shape_checked(self):
        cell = "example-2026-10-29-cell-841f"
        cases = [
            ("last_change", "up", "last_change='up' not in"),
            ("last_change_at", None, "needs last_change_at"),
            ("last_change_at", "2026-10-31T00:00:00Z", "last_change_at is later than published_at"),
            ("last_change_at", "yesterday", "last_change_at='yesterday'"),
            ("event_start", "2026-10-29", "event_start='2026-10-29' is not ISO 8601"),
            ("event_end", "2026-10-28T00:00:00Z", "event_end is before event_start"),
            ("event_start", "2026-10-29T06:00:00Z", "needs event_start at midnight UTC"),
            ("event_time_precision", "week", "event_time_precision='week' not in"),
            ("subject_id", "example cell", "no spaces"),
            ("subject_id", "other:cell:841f", "starting 'example:'"),
            ("subject_id", "example-cell", "program:kind:key"),
            ("signal", 31, "signal must be an object"),
            ("signal", {"value": 1}, "signal.name missing"),
            ("signal", {"name": "x", "value": float("nan")}, "signal.value must be a finite number"),
            ("signal", {"name": "x", "value": True}, "signal.value must be a finite number"),
            ("signal", {"name": "x", "value": 1, "tail": "up"}, "signal.tail='up'"),
            ("signal", {"name": "x", "value": 1, "baseline_n": -1}, "signal.baseline_n"),
            ("signal", {"name": "x", "value": 1, "exceedance": 1.2}, "signal.exceedance must be a share"),
            ("signal", {"name": "x", "value": 1, "baseline_n": 28, "exceedance": 0.01}, "smallest is 1 in 29"),
            ("sea_areas", ["strait-of-hormuz"], "not in the kit's gazetteer"),
            ("sea_areas", "gulf-of-finland", "sea_areas must be a list"),
            ("place_basis", "nearby", "place_basis='nearby' not in"),
        ]
        for key, value, needle in cases:
            f = _by_id(GOOD21, cell)
            if value is None:
                f["properties"].pop(key)
            else:
                f["properties"][key] = value
            self.assertIn(needle, self.errors(f), (key, value))
        f = _by_id(GOOD21, cell)
        f["properties"].pop("last_change")
        self.assertIn("last_change_at without last_change", self.errors(f))
        f = _by_id(GOOD21, cell)
        f["properties"].pop("event_start"), f["properties"].pop("event_end")
        self.assertIn("event_time_precision without event_start", self.errors(f))
        f = _by_id(GOOD21, cell)
        f["properties"]["baseline_ref"]["flag_rate"] = 2
        self.assertIn("flag_rate must be a share", self.errors(f))
        f = _by_id(GOOD21, cell)
        f["properties"]["sources"][0]["lane"] = ""
        self.assertIn("sources[0].lane", self.errors(f))
        f = _by_id(GOOD21, cell)
        f["properties"]["last_change"], f["properties"]["last_change_at"] = "none", None
        f["properties"].pop("last_change_at")
        self.assertEqual(self.errors(f), "", "none needs no time")

    def test_absence_is_a_notice_never_an_error(self):
        for f in GOOD21["features"]:
            f = copy.deepcopy(f)
            for k in contract.REVISION_FIELDS:
                f["properties"].pop(k, None)
            self.assertEqual(self.errors(f, rev="2.1"), "", f["properties"]["id"])
        cell = _by_id(GOOD, "example-2026-10-29-cell-841f")
        got = " | ".join(self.notices(cell))
        for needle in ("last_change absent", "event_start absent", "subject_id absent", "signal absent on an anomaly",
                       "sea_areas absent", "place_basis absent"):
            self.assertIn(needle, got)
        self.assertTrue(all(m.startswith("rev 2.1: ") for m in self.notices(cell)))
        self.assertTrue(all(sev == "warning" for s, sev, m in contract.check(cell) if s == contract.REVISION))

    def test_a_subject_id_with_a_date_is_a_notice(self):
        f = _by_id(GOOD21, "example-2026-10-29-cell-841f")
        f["properties"]["subject_id"] = "example:cell:841f:2026-10-29"
        self.assertEqual(self.errors(f), "")
        self.assertIn("rev 2.1: subject_id carries a date: it names the thing read, not the reading", self.notices(f))
        f["properties"]["subject_id"] = f["properties"]["id"]        # a dated id that is stable is its own subject
        self.assertEqual(self.notices(f), [])

    def test_data_as_of_after_publication_is_an_error_only_when_the_feed_states_2_1(self):
        f = _by_id(GOOD21, "example-kev-2026-10-30")
        f["properties"]["data_as_of"] = "2026-10-30T07:00:00Z"
        self.assertEqual(self.errors(f), "")
        self.assertTrue(any("data_as_of is later than published_at" in m for m in self.notices(f)))
        self.assertIn("data_as_of is later than published_at", self.errors(f, rev="2.1"))

    def test_the_2_1_meaning_of_anomaly_is_noted_not_enforced(self):
        def notes(**props):
            f = _by_id(GOOD21, "example-2026-10-29-cell-841f")
            for k, v in props.items():
                if v is None:
                    f["properties"].pop(k, None)
                else:
                    f["properties"][k] = v
            self.assertEqual(self.errors(f), "")
            return " | ".join(self.notices(f))
        self.assertEqual(notes(), "")
        self.assertIn("flag_rate is over 5%", notes(baseline_ref={"id": "b", "window": "28d", "type": "rolling",
                                                                  "flag_rate": 0.117}))
        self.assertIn("no signal and no rise", notes(signal=None, last_change="none", last_change_at=None))
        self.assertIn("raised more than 72 hours ago", notes(signal=None, last_change_at="2026-10-26T00:00:00Z"))
        self.assertNotIn("72 hours", notes(signal=None, last_change_at="2026-10-28T00:00:00Z"))
        self.assertIn("event ended more than 72 hours", notes(event_start="2026-10-01T00:00:00Z",
                                                              event_end="2026-10-03T00:00:00Z"))

    def test_the_feed_header(self):
        h = {k: v for k, v in GOOD21.items() if k != "features"}
        self.assertEqual(contract.check_header(h), [])
        self.assertEqual(lint.check_header, contract.check_header)
        bad = dict(h, contract_rev="3.0", kit="latest")
        msgs = " | ".join(m for s, sev, m in contract.check_header(bad) if sev == "error")
        self.assertIn("contract_rev='3.0'", msgs)
        self.assertIn("kit='latest'", msgs)
        old = {k: v for k, v in h.items() if k not in ("contract_rev", "kit", "health")}
        self.assertEqual({(s, sev) for s, sev, m in contract.check_header(old)}, {("revision", "warning")})

    def test_health_shapes_live_today_are_notices_and_errors_under_2_1(self):
        lane = {"state": "fresh", "checked_at": "2026-11-16T05:45:30Z", "last_ok": "2026-11-16T05:45:30Z"}
        live = {"nasa-black-marble": dict(lane, state="failed"),          # Blackout, 16 Nov 2026
                "usgs-earthquakes": {k: v for k, v in lane.items() if k != "state"},   # Elements: no state
                "census-trade": dict(lane, data_as_of="2026-09-30"),        # Headwind: a date, not a time
                "gdelt": dict(lane, failures="two"), "x": "up"}
        loose = contract.check_health(live)
        self.assertEqual({(s, sev) for s, sev, m in loose}, {("revision", "warning")})
        self.assertEqual(len(loose), 5)
        strict = contract.check_health(live, strict=True)
        self.assertEqual({sev for s, sev, m in strict}, {"error"})
        self.assertEqual(contract.check_health({"a": lane}, strict=True), [])
        self.assertEqual(contract.check_health({"a": {**lane, "last_ok": None, "state": "never", "vigil_extra": 1}},
                                               strict=True), [], "other keys are allowed; last_ok may be null")
        self.assertTrue(contract.check_health(["a"], strict=True))
        h = dict({k: v for k, v in GOOD21.items() if k != "features"}, health=live)
        self.assertTrue(any(sev == "error" for s, sev, m in contract.check_header(h)))
        h.pop("contract_rev")
        self.assertFalse(any(sev == "error" for s, sev, m in contract.check_header(h)))

    def test_health_report_converts_to_the_contract_shape(self):
        from tic_doctrine import health
        self.assertEqual(set(health.STATES), vocab.enum("health_state"))
        report = {"checked_at": "2026-11-18T12:00:00Z", "sources": {
            "a": {"state": "fresh", "latest": "2026-11-18T11:00:00Z", "last_ok": "2026-11-18T12:00:00Z"},
            "b": {"state": "failing", "error": "HTTP 503", "last_ok": "2026-11-17T00:00:00Z"},
            "c": {"state": "never", "note": "no probe defined", "last_ok": None}}}
        out = health.feed_health(report, previous={"b": {"failures": 2}})
        self.assertEqual(contract.check_health(out, strict=True), [])
        self.assertEqual((out["a"]["data_as_of"], out["a"]["failures"]), ("2026-11-18T11:00:00Z", 0))
        self.assertEqual((out["b"]["last_error"], out["b"]["failures"]), ("HTTP 503", 3))
        self.assertEqual(out["c"]["detail"], "no probe defined")

    def test_the_linter_counts_notices_per_feed_and_reports_coverage(self):
        doc = copy.deepcopy(GOOD21)
        doc["features"][1]["properties"]["subject_id"] = doc["features"][0]["properties"]["subject_id"]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "feed.geojson"
            path.write_text(json.dumps(doc), encoding="utf-8")
            rep = lint.lint_files([path])
        self.assertFalse(any(v["error"] for v in rep["standards"].values()))
        self.assertEqual(rep["standards"]["revision"]["examples"],
                         ["feed.geojson: 1 of 4 items: rev 2.1: a subject_id shared by two or more items of one feed "
                          "(history keeps each under its own id)"])

    def test_event_interval(self):
        def span(**p):
            got = contract.event_interval(p)
            return got and tuple(t and t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in got)
        asof = "2026-11-16T05:45:30Z"
        self.assertIsNone(span(data_as_of=asof))
        self.assertEqual(span(event_start="2026-11-18T14:00:00Z", event_end="2026-11-20T22:00:00Z", data_as_of=asof),
                         ("2026-11-18T14:00:00Z", "2026-11-20T22:00:00Z"))      # Cordon's TFR
        self.assertEqual(span(event_start="2026-11-10T19:45:00Z", data_as_of=asof),
                         ("2026-11-10T19:45:00Z", asof))                         # Blackout: ongoing at the last look
        self.assertEqual(span(event_start="2026-11-18T22:50:00Z", data_as_of=asof),
                         ("2026-11-18T22:50:00Z", "2026-11-18T22:50:00Z"))       # Orbit: a scheduled launch
        self.assertEqual(span(event_start="2026-11-18T22:00:00Z", event_time_precision="hour", data_as_of=asof),
                         ("2026-11-18T22:00:00Z", "2026-11-18T23:00:00Z"))
        self.assertEqual(span(event_start="2026-11-15T00:00:00Z", event_end="2026-11-15T00:00:00Z",
                              event_time_precision="day", data_as_of=asof),
                         ("2026-11-15T00:00:00Z", "2026-11-16T00:00:00Z"))       # one whole day
        self.assertEqual(span(event_start="2026-07-01T00:00:00Z", event_end="2026-12-01T00:00:00Z",
                              event_time_precision="month", data_as_of=asof),
                         ("2026-07-01T00:00:00Z", "2027-01-01T00:00:00Z"))       # Undertow's H2 2026
        self.assertEqual(span(event_end="2026-11-20T22:00:00Z", data_as_of=asof), (None, "2026-11-20T22:00:00Z"))

    def test_vocabulary_schema_and_browser_module_agree(self):
        from tic_doctrine import geo
        e = vocab.load("enums")
        self.assertEqual(e["version"], "1.1")
        for name in ("last_change", "event_time_precision", "place_basis", "signal_tail", "health_state", "contract_rev"):
            self.assertTrue(e[name]["basis"] and e[name]["values"], name)
        self.assertIn(CONTRACT_REV, vocab.enum("contract_rev"))
        import subprocess
        for tool in ("build_schema.py", "build_js.py"):
            r = subprocess.run([sys.executable, str(ROOT / "tools" / tool), "--check"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)
        schema = json.loads((ROOT / "schema" / "feed-item-v2.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(schema["properties"]["sea_areas"]["items"]["enum"]), geo.sea_slugs())
        for k in contract.REVISION_FIELDS:
            self.assertIn(k, schema["properties"])
        self.assertEqual(sorted(schema["$defs"]["feed_header"]["properties"]["health"]["additionalProperties"]
                                ["properties"]), sorted(contract.HEALTH_KEYS))


class Seas(unittest.TestCase):
    """Kit 0.6.0: the sea gazetteer (geo/seas.json, Natural Earth marine areas) and countries by overlap."""

    def test_the_gazetteer(self):
        from tic_doctrine import geo
        doc = json.loads(geo.SEAS.read_text(encoding="utf-8"))
        self.assertIn("Natural Earth", doc["source"])
        self.assertIn("v5.1.2", doc["url"])
        self.assertEqual(doc["licence"], "Public domain (Natural Earth)")
        slugs = [s["slug"] for s in doc["seas"]]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertTrue(all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s) for s in slugs), slugs)
        for slug in ("persian-gulf", "gulf-of-oman", "red-sea", "bab-el-mandeb", "gulf-of-aden", "arabian-sea",
                     "black-sea", "baltic-sea", "south-china-sea", "taiwan-strait", "strait-of-malacca",
                     "north-atlantic-ocean", "south-pacific-ocean", "indian-ocean"):
            self.assertIn(slug, slugs)
        self.assertEqual(geo.sea_name("persian-gulf"), "Persian Gulf")
        self.assertEqual(geo.sea_name("indian-ocean"), "Indian Ocean")
        self.assertIsNone(geo.sea_name("strait-of-hormuz"), "Natural Earth has no separate Strait of Hormuz")

    def test_points_at_sea_and_on_land(self):
        from tic_doctrine import geo
        for name, lat, lon, want in (("Cordon's tug, Hormuz", 26.376, 56.341, "persian-gulf"),
                                     ("Gulf of Oman", 24.5, 58.5, "gulf-of-oman"),
                                     ("Elements' XAVIER-26", -8.1, -160.1, "south-pacific-ocean"),
                                     ("Red Sea", 20.0, 38.0, "red-sea"), ("Gulf of Aden", 12.5, 48.0, "gulf-of-aden"),
                                     ("Sargasso Sea", 28.0, -60.0, "sargasso-sea"), ("Fargo", 46.88, -96.79, None),
                                     ("Suez Canal", 30.5933, 32.4369, None)):
            self.assertEqual(geo.sea_at(lat, lon), want, name)
            got = geo.sea_areas_for_geometry({"type": "Point", "coordinates": [lon, lat]})
            self.assertEqual(got, [want] if want else [], name)
        self.assertEqual(geo.sea_areas_for_geometry(None), [])

    def test_the_areas_do_not_overlap(self):
        from tic_doctrine import geo
        doubles = []
        for lat in range(-75, 85, 3):
            for lon in range(-180, 180, 3):
                hits = [s["slug"] for s in geo._seas() if s["bbox"][0] <= lon <= s["bbox"][2]
                        and s["bbox"][1] <= lat <= s["bbox"][3] and any(geo._in_poly(lon, lat, p) for p in s["polygons"])]
                if len(hits) > 1:
                    doubles.append((lat, lon, hits))
        self.assertEqual(doubles, [])

    def test_countries_by_overlap(self):
        from tic_doctrine import geo
        gulf = {"type": "Polygon", "coordinates": [[[49, 23], [58, 23], [58, 28], [49, 28], [49, 23]]]}
        self.assertEqual(geo.countries_for_geometry(gulf), ["IR", "OM", "SA"], "the corners alone")
        self.assertEqual(geo.countries_overlapping(gulf), ["AE", "BH", "IR", "OM", "QA", "SA"])
        self.assertEqual(geo.sea_areas_for_geometry(gulf), ["gulf-of-oman", "persian-gulf"])
        inside = {"type": "Polygon", "coordinates": [[[50, 20], [57, 20], [57, 30], [50, 30], [50, 20]]]}
        self.assertIn("QA", geo.countries_overlapping(inside), "a country wholly inside the area")
        line = {"type": "LineString", "coordinates": [[46.0, 24.0], [56.0, 24.0]]}   # Riyadh to Oman, across the UAE
        self.assertEqual(geo.countries_overlapping(line), ["AE", "OM", "SA"])
        ring = {"type": "Polygon", "coordinates": [[[49, 23.5], [53, 23.5], [53, 27], [49, 27], [49, 23.5]],
                                                   [[50.6, 24.3], [51.8, 24.3], [51.8, 26.3], [50.6, 26.3], [50.6, 24.3]]]}
        got = geo.countries_overlapping(ring)
        self.assertNotIn("QA", got, "a country wholly inside the shape's hole is not under the shape")
        self.assertIn("BH", got)
        self.assertIn("SA", got)
        self.assertEqual(geo.countries_overlapping({"type": "Point", "coordinates": [-96.79, 46.88]}), ["US"])
        self.assertEqual(geo.countries_overlapping(None), [])

    def test_the_builder_rules(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import build_seas as bs
        self.assertEqual(bs.slug("Golfe du Lion"), "golfe-du-lion")
        self.assertEqual(bs.slug("Øresund"), "oresund")
        self.assertEqual(bs.slug("Gulf of Anadyr'"), "gulf-of-anadyr")
        self.assertEqual(bs.slug("Bahía de Campeche"), "bahia-de-campeche")
        self.assertEqual(bs.display("INDIAN OCEAN"), "Indian Ocean")
        self.assertEqual(bs.display("Gulf of Aden"), "Gulf of Aden")
        src = {"features": [
            {"properties": {"name": "North Atlantic Ocean", "name_en": "Atlantic Ocean", "featurecla": "ocean"},
             "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}},
            {"properties": {"name": "Golfo de California", "name_en": "Gulf of California", "featurecla": "gulf"},
             "geometry": {"type": "Polygon", "coordinates": [[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]]}},
            {"properties": {"name": None, "featurecla": "generic"},
             "geometry": {"type": "Polygon", "coordinates": [[[9, 9], [10, 9], [10, 10], [9, 9]]]}}]}
        self.assertEqual([s["slug"] for s in bs.build(src)], ["gulf-of-california", "north-atlantic-ocean"])


class Kit062(unittest.TestCase):
    """Kit 0.6.2: corroboration (D11) and the kit review's M1, M4, M5 and G3."""

    def setUp(self):
        self.kev = _by_id(GOOD21, "example-kev-2026-10-30")

    def errs(self, item):
        return " | ".join(m for s, sev, m in contract.check(item) if sev == "error")

    def warns(self, item, std):
        return " | ".join(m for s, sev, m in contract.check(item) if sev == "warning" and s == std)

    def test_the_fixture_corroborations_pass(self):
        self.assertEqual(self.errs(self.kev), "")
        self.assertEqual(self.errs(_by_id(GOOD21, "example-strike-2026-10-30-odesa-port")), "")

    def test_corroboration_shape(self):
        c = self.kev["properties"]["corroboration"]
        for change, needle in (
                ({"state": "rumoured"}, "corroboration.state"),
                ({"basis": "rumour"}, "corroboration.basis"),
                ({"origins": 0}, "at least 1"),
                ({"origins": True}, "at least 1"),
                ({"rule": ""}, "corroboration.rule missing"),
                ({"official": None}, "needs official"),
                ({"basis": "origins", "official": None}, "origins of 2 or more"),
                ({"basis": "origins"}, "only when basis is official"),
                ({"basis": None}, "names its basis"),
                ({"verified_at": None}, "needs verified_at"),
                ({"verified_at": "2026-10-29T00:00:00Z"}, "before first_reported_at"),
                ({"verified_at": "2026-10-31T00:00:00Z", "first_reported_at": "2026-10-29T00:00:00Z"},
                 "after published_at"),
                ({"first_reported_at": "yesterday"}, "first_reported_at must be a UTC time"),
                ({"party_claim": "yes"}, "true or false"),
                ({"party_claim": True}, "outside them"),
                ({"state": "reported"}, "a lead has basis")):
            f = copy.deepcopy(self.kev)
            f["properties"]["corroboration"] = dict(c, **change)
            self.assertIn(needle, self.errs(f), change)
        f = copy.deepcopy(self.kev)
        f["properties"]["corroboration"] = "corroborated"
        self.assertIn("must be an object", self.errs(f))

    def test_corroboration_absence_is_not_noted(self):
        self.kev["properties"].pop("corroboration")
        self.assertNotIn("corroboration", " ".join(m for s, sev, m in contract.check(self.kev)))

    def test_credibility_1_on_one_group_is_a_warning(self):
        self.assertEqual(self.warns(self.kev, "sources"), "")
        self.kev["properties"]["sources"][0]["grade"] = "A1"
        self.assertIn("grade it 2 at most", self.warns(self.kev, "sources"))
        self.assertEqual(self.errs(self.kev), "", "never an error")
        two = _by_id(GOOD21, "example-strike-2026-10-30-odesa-port")
        two["properties"]["sources"][0]["grade"] = "B1"     # two independence groups: confirmed is possible
        self.assertNotIn("grade it 2 at most", self.warns(two, "sources"))

    def test_language_key_is_the_kits_public_page(self):
        h = {k: v for k, v in GOOD21.items() if k != "features"}
        self.assertEqual(h["language_key"], contract.LANGUAGE_KEY_URL)
        self.assertFalse([m for s, sev, m in contract.check_header(h) if "language_key" in m])
        h["language_key"] = "https://github.com/metacog-osint/noise-floor/blob/main/doctrine/kit/docs/language-key.md"
        got = [(sev, m) for s, sev, m in contract.check_header(h) if "language_key" in m]
        self.assertEqual([sev for sev, m in got], ["warning"])
        self.assertTrue((ROOT / "docs" / "language-key.md").exists())

    def test_rows_say_not_applicable_when_nothing_was_checked(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            doc = copy.deepcopy(GOOD21)
            doc["features"] = [x for x in doc["features"] if not contract.is_judgment(x["properties"])]
            path = Path(d) / "obs.geojson"
            path.write_text(json.dumps(doc), encoding="utf-8")
            rep = lint.lint_files([path])
            self.assertEqual(rep["examined"], {"judgments": 0, "forecasts": 0, "updates": 0})
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertTrue(lint.print_report(rep))
        text = out.getvalue()
        self.assertIn("[n/a ] 4. ", text)
        self.assertIn("[n/a ] 8. ", text)
        self.assertIn("not whether the", text)
        self.assertIn("the fields it needs", text)
        rep = lint.lint_files([GOOD21_PATH])
        self.assertGreater(rep["examined"]["forecasts"], 0)
        self.assertIsNone(lint.not_applicable("accuracy", rep["examined"]))

    def test_method_scored_from_verdict(self):
        scores = {"skill_min_n": 30, "by_program": {"verdict": {"n": 8, "n_independent": 3.0, "brier": 0.0142},
                                                    "vis": {"n": 40, "n_independent": 31.0, "brier": 0.2}}}
        self.assertFalse(confidence.method_scored(scores, "verdict"))
        self.assertTrue(confidence.method_scored(scores, "vis"))
        self.assertFalse(confidence.method_scored(scores, "vis", min_n=50))
        self.assertFalse(confidence.method_scored(scores, "cordon"))
        self.assertFalse(confidence.method_scored(None, "vis"))
        from tic_doctrine.confidence import Evidence, assess
        ev = Evidence(independent_lines=3, method_scored=confidence.method_scored(scores, "vis"))
        self.assertEqual(assess(ev)["level"], "high")
        self.assertEqual(assess(Evidence(independent_lines=3))["level"], "moderate")


class Kit0613(unittest.TestCase):
    """Kit 0.6.13: the event ladder (lead, confirmed, verified) and the coverage table (docs/event-ladder.md)."""

    def setUp(self):
        self.kev = copy.deepcopy(_by_id(GOOD21, "example-kev-2026-10-30"))
        self.strike = copy.deepcopy(_by_id(GOOD21, "example-strike-2026-10-30-odesa-port"))
        self.assertEqual(self.kev["properties"]["corroboration"]["rule"], ladder.rule())

    def errs(self, item):
        return " | ".join(m for s, sev, m in contract.check(item) if sev == "error")

    def notes(self, item):
        return " | ".join(m for s, sev, m in contract.check(item) if sev == "warning")

    def test_new_names_pass_and_old_names_are_noted(self):
        self.assertEqual(self.errs(self.kev), "")
        self.assertEqual(self.errs(self.strike), "")
        self.assertNotIn("kit 0.6.2 name", self.notes(self.kev))
        old = copy.deepcopy(self.kev)
        c = old["properties"]["corroboration"]
        c.update(state="corroborated", rule="corroborate-1: two independent origins, or one official source within "
                                           "its remit")
        c["corroborated_at"] = c.pop("verified_at")
        self.assertEqual(self.errs(old), "")
        self.assertEqual(ladder.state_of(old), "verified")
        self.assertIn("kit 0.6.2 name of 'verified'", self.notes(old))

    def test_states_read_the_same_under_both_names(self):
        self.assertEqual(ladder.state_of(self.kev), "verified")
        self.assertEqual(ladder.state_of({"corroboration": {"state": "reported"}}), "lead")
        self.assertEqual(ladder.state_of(self.strike), "lead")
        self.assertIsNone(ladder.state_of({"properties": {"tier": "anomaly"}}))
        self.assertTrue(ladder.rests_on_claim(self.strike))
        self.assertFalse(ladder.rests_on_claim(self.kev))

    def test_enums_and_ladder_vocab_agree(self):
        v = vocab.load("event_ladder")
        ids = [s["id"] for s in v["states"]]
        self.assertEqual(ids, ["lead", "confirmed", "verified"])
        self.assertEqual(vocab.enum("corroboration_state"), set(ids) | set(v["earlier_names"]))
        self.assertTrue(v["rule"]["text"].startswith(v["rule"]["id"] + ": "))
        self.assertEqual(set(v["basis_labels"]), vocab.enum("corroboration_basis"))
        self.assertEqual({c["id"] for c in v["coverage"]["classes"]}, vocab.enum("coverage_class"))
        doc = " ".join((ROOT / "docs" / "event-ladder.md").read_text(encoding="utf-8").replace("> ", "").split())
        self.assertIn(v["rule"]["text"].replace("ladder-1: ", "**ladder-1:** "), doc)
        self.assertTrue(v["url"].endswith("/docs/event-ladder.md"))

    def test_confirmed_needs_a_reviewer(self):
        c = self.strike["properties"]["corroboration"]
        c.update(state="confirmed", confirmed_at="2026-10-30T05:00:00Z", party_claim=False)
        self.assertIn("human_review must be 'full'", self.errs(self.strike))
        self.strike["properties"]["human_review"] = "full"
        self.assertEqual(self.errs(self.strike), "")
        c["confirmed_at"] = None
        self.assertIn("needs confirmed_at", self.errs(self.strike))
        c.update(confirmed_at="2026-10-30T05:00:00Z", basis="origins")
        self.assertIn("not verified yet", self.errs(self.strike))

    def test_verified_rules(self):
        for change, needle in (
                ({"basis": "geolocation", "official": None}, "geolocation needs geolocation"),
                ({"basis": "geolocation", "official": None, "geolocation": "nope"}, "geolocation needs geolocation"),
                ({"geolocation": "cisa-kev"}, "only when basis is geolocation"),
                ({"verified_at": None}, "needs verified_at"),
                ({"corroborated_at": "2026-10-30T00:00:00Z"}, "use one"),
                ({"confirmed_at": "soon"}, "confirmed_at must be a UTC time"),
                ({"state_media": True}, "never on official"),
                ({"state_media": "no"}, "state_media must be true or false")):
            f = copy.deepcopy(self.kev)
            f["properties"]["corroboration"].update(change)
            self.assertIn(needle, self.errs(f), change)
        f = copy.deepcopy(self.kev)
        f["properties"]["corroboration"].update(basis="geolocation", official=None, geolocation="cisa-kev")
        self.assertEqual(self.errs(f), "")

    def test_claims_raise_nothing_alone(self):
        self.strike["properties"]["tier"] = "anomaly"
        self.assertIn("raises nothing on its own", self.errs(self.strike))
        c = self.strike["properties"]["corroboration"]
        c.update(state="verified", basis="origins", origins=1, verified_at="2026-10-30T06:00:00Z")
        self.assertIn("origins of 2 or more", self.errs(self.strike))
        c["origins"] = 2
        self.assertNotIn("raises nothing", self.errs(self.strike))
        self.assertFalse(ladder.rests_on_claim(self.strike))

    def test_lead_with_a_basis_fails(self):
        self.strike["properties"]["corroboration"]["basis"] = "origins"
        self.assertIn("a lead has basis", self.errs(self.strike))

    def test_coverage_classes(self):
        self.assertEqual([ladder.coverage_class(n) for n in (0, 1, 2, 3, 9)],
                         ["none", "few", "few", "several", "several"])
        self.assertEqual(ladder.coverage_label("none"), "Not monitored")

    def test_coverage_place_sets_aside_claims_and_state_media(self):
        def item(prog, *srcs, **kw):
            return {"properties": {"program": prog, "sources": list(srcs), **kw}}
        items = [item("cordon", {"id": "a", "publisher": "US State Department", "independence_group": "us-gov"}),
                 item("relief", {"id": "b", "publisher": "IFRC"}),
                 item("watchfloor", {"id": "c", "publisher": "Agency", "owner": "state", "source_type": "news media"}),
                 self.strike["properties"] | {"program": "watchfloor"},
                 item("relief", {"id": "b2", "publisher": "IFRC"})]
        row = ladder.coverage_place("x", "Example", items)
        self.assertEqual(row["independent"], 2)
        self.assertEqual(row["class"], "few")
        self.assertEqual([g["id"] for g in row["groups"]], ["IFRC", "us-gov"])
        self.assertEqual({g["id"]: g["why"] for g in row["set_aside"]},
                         {"Agency": "state_media", "ru-gov": "party_claim", "ua-gov": "party_claim"})
        self.assertEqual(row["programs"], ["cordon", "relief", "watchfloor"])
        self.assertEqual(ladder.coverage_place("y", "Empty", [])["class"], "none")

    def test_coverage_does_not_count_the_suites_own_sources(self):
        def item(prog, *srcs):
            return {"properties": {"program": prog, "sources": list(srcs)}}
        items = [item("context", {"id": "gdelt", "publisher": "The GDELT Project", "source_type": "aggregator"},
                      {"id": "context-ai", "publisher": "Context", "source_type": "machine summary"}),
                 item("wake", {"id": "headwind", "publisher": "Headwind", "source_type": "suite_program"}),
                 item("vis", {"id": "ephemeris", "publisher": "Vis", "source_type": "Derived"}),
                 item("orbit", {"id": "m", "publisher": "Orbit", "source_type": "model"})]
        row = ladder.coverage_place("x", "Example", items)
        self.assertEqual([g["id"] for g in row["groups"]], ["The GDELT Project"])
        self.assertEqual((row["independent"], row["class"], row["set_aside"]), (1, "few", []))
        self.assertTrue(ladder.is_derived({"source_type": "Machine Summary "}))
        self.assertFalse(ladder.is_derived({"source_type": "official notice"}))


class Kit0617(unittest.TestCase):
    """Kit 0.6.17: a place read only through set-aside or suite sources is not "Not monitored"; the two ladder rules
    added in 0.6.13 are notes for feeds that use the 0.6.2 names; no dated quotation in the vocabularies."""

    def setUp(self):
        self.strike = copy.deepcopy(_by_id(GOOD21, "example-strike-2026-10-30-odesa-port"))
        self.kev = copy.deepcopy(_by_id(GOOD21, "example-kev-2026-10-30"))

    @staticmethod
    def item(prog, *srcs, **kw):
        return {"properties": {"program": prog, "sources": list(srcs), **kw}}

    def errs(self, item):
        return " | ".join(m for s, sev, m in contract.check(item) if sev == "error")

    def notes(self, item):
        return " | ".join(m for s, sev, m in contract.check(item) if sev == "warning")

    def test_state_media_only_is_no_independent_source(self):
        row = ladder.coverage_place("x", "Example", [self.item(
            "watchfloor", {"id": "c", "publisher": "Agency", "owner": "state", "source_type": "news wire"})])
        self.assertEqual((row["independent"], row["class"]), (0, "no_independent"))
        self.assertEqual(ladder.coverage_label(row["class"]), "No independent source")
        self.assertEqual(row["programs"], ["watchfloor"])
        self.assertEqual([g["why"] for g in row["set_aside"]], ["state_media"])

    def test_party_claim_only_is_no_independent_source(self):
        row = ladder.coverage_place("x", "Example", [
            self.item("watchfloor", {"id": "mod", "publisher": "Ministry", "independence_group": "x-gov"},
                      corroboration={"state": "lead", "party_claim": True})])
        self.assertEqual((row["independent"], row["class"]), (0, "no_independent"))
        self.assertEqual([g["why"] for g in row["set_aside"]], ["party_claim"])

    def test_suite_sources_only_name_the_program_and_are_listed(self):
        row = ladder.coverage_place("x", "Example", [
            self.item("vis", {"id": "ephemeris", "publisher": "Vis", "source_type": "derived"})])
        self.assertEqual((row["independent"], row["class"], row["set_aside"]), (0, "no_independent", []))
        self.assertEqual(row["programs"], ["vis"])
        self.assertEqual(row["not_counted"], [{"id": "Vis", "label": "Vis", "programs": ["vis"]}])
        mixed = ladder.coverage_place("x", "Example", [
            self.item("vis", {"id": "ephemeris", "publisher": "Vis", "source_type": "derived"}),
            self.item("cordon", {"id": "a", "publisher": "US State Department"})])
        self.assertEqual((mixed["class"], mixed["programs"]), ("few", ["cordon", "vis"]))

    def test_nothing_held_is_still_not_monitored(self):
        row = ladder.coverage_place("y", "Empty", [])
        self.assertEqual((row["class"], row["set_aside"], row["not_counted"]), ("none", [], []))
        self.assertEqual(ladder.coverage_label("none"), "Not monitored")
        self.assertEqual([ladder.coverage_class(0), ladder.coverage_class(0, 2), ladder.coverage_class(2, 5)],
                         ["none", "no_independent", "few"])

    def test_earlier_names_keep_passing_the_two_0613_rules_with_a_note(self):
        c = self.kev["properties"]["corroboration"]
        c.update(party_claim=True, origins=2)
        self.assertIn("never on official", self.errs(self.kev), "an error under the new names")
        c.update(state="corroborated")
        c["corroborated_at"] = c.pop("verified_at")
        self.assertEqual(self.errs(self.kev), "")
        self.assertIn("never on official", self.notes(self.kev))
        s = self.strike["properties"]
        s["tier"] = "anomaly"
        self.assertIn("raises nothing on its own", self.errs(self.strike))
        s["corroboration"]["state"] = "reported"
        self.assertNotIn("raises nothing", self.errs(self.strike))
        self.assertIn("raises nothing on its own", self.notes(self.strike))

    def test_a_state_of_the_wrong_type_is_an_error_not_a_crash(self):
        for bad in (["lead"], {"id": "lead"}):
            self.strike["properties"]["corroboration"]["state"] = bad
            self.assertIn("corroboration.state", self.errs(self.strike))
        self.strike["properties"]["corroboration"].update(state="lead", basis=["origins"])
        self.assertIn("corroboration.basis", self.errs(self.strike))

    def test_no_dated_quotation_in_the_vocabularies_or_schema(self):
        quote = re.compile(r"\(\d{1,2} [A-Z][a-z]{2} \d{4}: ['\"]")
        for path in [*sorted((ROOT / "vocab").glob("*.json")), ROOT / "schema" / "feed-item-v2.schema.json"]:
            self.assertIsNone(quote.search(path.read_text(encoding="utf-8")), path.name)


class Zones(unittest.TestCase):
    """Kit 0.6.1: the shared zone list (D4), built from Watchfloor's catalog."""

    def test_the_list(self):
        from tic_doctrine import geo
        z = vocab.zones()
        doc = vocab.load("zones")
        self.assertEqual(doc["source"]["program"], "watchfloor")
        self.assertRegex(doc["source"]["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(len(z), 16)
        self.assertEqual(z["11_Iran_Red_Sea"]["countries"], ["IR", "YE"])
        self.assertEqual(z["10_Israel_Gaza_Lebanon"]["countries"], ["IL", "LB", "PS"], "FIPS GZ and WE are both PS")
        self.assertEqual(z["07_Russia_NATO"]["countries"], ["BY", "DK", "EE", "FI", "LT", "LV", "NO", "PL", "RU", "SE"])
        for k, v in z.items():
            self.assertRegex(k, r"^\d\d_[A-Za-z_]+$")
            self.assertTrue(all(re.fullmatch(r"[A-Z]{2}", c) and geo.name(c) for c in v["countries"]), (k, v))
        old = vocab.zone("17_Horn_of_Africa")
        self.assertEqual(old["into"], ["18_Ethiopia_Eritrea", "19_Somalia"])
        self.assertEqual(old["countries"], ["DJ", "ER", "ET", "SO"])
        self.assertIsNone(vocab.zone("99_Nowhere"))

    def _warnings(self, sid, program="vis"):
        f = _by_id(GOOD21, "example-2026-10-29-cell-841f")
        f["properties"].update(program=program, id=f"{program}:2026-11-18:zone:x", subject_id=sid)
        return [m for s, sev, m in contract.check(f) if s == contract.GENERAL and sev == "warning" and "zone" in m]

    def test_a_zone_subject_names_a_listed_zone(self):
        self.assertEqual(self._warnings("vis:zone:11_Iran_Red_Sea"), [])
        self.assertEqual(self._warnings("vis:zone:01_Ukraine_Conflict-UKOO"), [], "a station suffix is allowed")
        self.assertEqual(self._warnings("vis:region:99_Nowhere"), [], "only kind zone is checked")
        self.assertIn("not in the shared zone list", " ".join(self._warnings("vis:zone:99_Nowhere")))
        got = " ".join(self._warnings("context:zone:17_Horn_of_Africa", program="context"))
        self.assertIn("retired on 2026-10-27 into 18_Ethiopia_Eritrea, 19_Somalia", got)
        f = _by_id(GOOD21, "example-2026-10-29-cell-841f")
        f["properties"].update(program="vis", id="vis:x:y", subject_id="vis:zone:99_Nowhere")
        self.assertFalse([m for s, sev, m in contract.check(f) if sev == "error"], "never an error")


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
            self.assertFalse((kit / "docs" / "significance.md").exists(), "the draft note is not vendored")
            self.assertTrue((kit / "docs" / "event-ladder.md").exists())
            doc = kit / "docs" / "language-key.md"
            # what a Windows checkout does: LF first, so a file that is already CRLF stays CRLF, not \r\r\n
            doc.write_bytes(doc.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            self.assertEqual(check(), 0)
            doc.write_bytes(doc.read_bytes() + b"edited\r\n")
            self.assertEqual(check(), 1)


if __name__ == "__main__":
    unittest.main()

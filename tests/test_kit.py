"""Offline tests for the doctrine kit. Run as a plain script or with unittest."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from tic_doctrine import confidence, contract, likelihood, lint, registers, vocab, withhold  # noqa: E402
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
            doc.write_bytes(doc.read_bytes().replace(b"\n", b"\r\n"))  # what a Windows checkout does
            self.assertEqual(check(), 0)
            doc.write_bytes(doc.read_bytes() + b"edited\r\n")
            self.assertEqual(check(), 1)


if __name__ == "__main__":
    unittest.main()

"""Every catalog entry matches catalog/schema.json, and the suite's live programs each have one."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog"
SCHEMA = json.loads((CATALOG / "schema.json").read_text(encoding="utf-8"))
REGISTRY = {p["id"]: p for p in json.loads((ROOT / "vocab" / "programs.json").read_text(encoding="utf-8"))["programs"]}
FIELDS = SCHEMA["$defs"]["store"]["required"][2:]
KINDS = {"git", "github-release", "object-store", "document-store", "database", "key-value", "site", "local"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def field_problems(name, f):
    if not isinstance(f, dict):
        return [f"{name}: not an object"]
    if f.get("status") == "measured":
        if set(f) != {"value", "status", "how"} or f["value"] is None or not f["how"]:
            return [f"{name}: measured needs a value and how"]
    elif f.get("status") == "unverified":
        if set(f) != {"value", "status", "why"} or f["value"] is not None or not f["why"]:
            return [f"{name}: unverified needs a null value and why"]
    else:
        return [f"{name}: bad status"]
    return []


def entry_problems(doc, stem):
    out = []
    if set(doc) != set(SCHEMA["required"]):
        return [f"{stem}: wrong top-level keys"]
    if doc["catalog"] != "tic-catalog/1" or doc["program"] != stem:
        out.append(f"{stem}: wrong catalog or program")
    if not re.fullmatch(SCHEMA["properties"]["measured_at"]["pattern"], doc["measured_at"]):
        out.append(f"{stem}: bad measured_at")
    if not doc["stores"]:
        out.append(f"{stem}: no stores")
    for s in doc["stores"]:
        sid = s.get("id", "?")
        if set(s) != set(SCHEMA["$defs"]["store"]["required"]):
            out.append(f"{sid}: wrong keys")
            continue
        for name in FIELDS:
            out += [f"{sid}.{p}" for p in field_problems(name, s[name])]
        if out:
            continue
        if s["location"]["status"] == "measured" and s["location"]["value"].get("kind") not in KINDS:
            out.append(f"{sid}: unknown location kind")
        if s["first_date"]["status"] == "measured" and not DATE.match(s["first_date"]["value"]):
            out.append(f"{sid}: first_date is not a date")
        c = s["independent_copies"]
        if c["status"] == "measured" and (not isinstance(c["value"], int) or c["value"] < 1):
            out.append(f"{sid}: copies must be a whole number of at least 1")
        lic = s["licence"]
        if lic["status"] == "measured" and str(lic["value"]).startswith("registry:"):
            pid = lic["value"].split(":", 1)[1]
            if not REGISTRY.get(pid, {}).get("terms"):
                out.append(f"{sid}: licence points at a program with no terms")
    return out


class Catalog(unittest.TestCase):
    def entries(self):
        return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in CATALOG.glob("*.json") if f.name != "schema.json"}

    def test_one_entry_per_live_program(self):
        live = {k for k, p in REGISTRY.items() if p["status"] == "live"}
        self.assertEqual(set(self.entries()), live)

    def test_every_entry_valid(self):
        for stem, doc in self.entries().items():
            self.assertEqual(entry_problems(doc, stem), [], stem)

    def test_store_ids_unique(self):
        ids = [s["id"] for d in self.entries().values() for s in d["stores"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_validator_rejects_a_bare_value(self):
        doc = json.loads(json.dumps(next(iter(self.entries().values()))))
        doc["stores"][0]["cadence"] = {"value": "daily", "status": "measured"}
        self.assertTrue(entry_problems(doc, doc["program"]))

    def test_validator_rejects_unverified_with_a_value(self):
        doc = json.loads(json.dumps(next(iter(self.entries().values()))))
        doc["stores"][0]["cadence"] = {"value": "daily", "status": "unverified", "why": "guess"}
        self.assertTrue(entry_problems(doc, doc["program"]))


if __name__ == "__main__":
    unittest.main()

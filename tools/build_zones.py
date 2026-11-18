"""Build vocab/zones.json, the suite's shared zone list (decision D4, Tom, 18 Nov 2026), from Watchfloor's catalog.

    python -I tools/build_zones.py path/to/entities.json <commit>

Watchfloor (repo `more-context`) owns the zones: `catalog/entities.json` lists them, first match wins, and Context
and Vis read the same keys (`11_Iran_Red_Sea`). The kit copies the keys, names, map points and countries so COP can
join the three programs on a zone and a `subject_id` such as `vis:zone:11_Iran_Red_Sea` can be checked. The catalog
writes countries as FIPS 10-4 codes (GDELT's); the list gives ISO 3166-1 alpha-2, as the contract's `countries` does.
A zone the catalog has retired stays in the list, marked with the day and the zones it went into, so items and
history lines that still carry its key keep resolving.

The kit never edits the list by hand: change the catalog in Watchfloor, then rebuild here with that commit.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "vocab" / "zones.json"

# FIPS 10-4 to ISO 3166-1 alpha-2, for the codes the catalog uses. A code missing here stops the build.
FIPS_ISO = {
    "BM": "MM", "BO": "BY", "CG": "CD", "CU": "CU", "DA": "DK", "DJ": "DJ", "EN": "EE", "ER": "ER", "ET": "ET",
    "FI": "FI", "GZ": "PS", "IN": "IN", "IR": "IR", "IS": "IL", "KN": "KP", "KS": "KR", "LE": "LB", "LG": "LV",
    "LH": "LT", "ML": "ML", "NG": "NE", "NO": "NO", "PK": "PK", "PL": "PL", "RP": "PH", "RS": "RU", "RW": "RW",
    "SO": "SO", "SU": "SD", "SW": "SE", "TW": "TW", "UP": "UA", "UV": "BF", "VE": "VE", "VM": "VN", "WE": "PS",
    "YM": "YE",
}


def iso(codes) -> list[str]:
    missing = [c for c in codes if c not in FIPS_ISO]
    if missing:
        raise SystemExit(f"no ISO code for FIPS {missing}: add them to FIPS_ISO")
    return sorted({FIPS_ISO[c] for c in codes})


def build(cat: dict, commit: str) -> dict:
    zones = [{"key": z["id"], "name": z["name"], "countries": iso(z["countries"]),
              "map": [round(z["map"][0], 4), round(z["map"][1], 4)]} for z in cat["zones"]]
    keys = {z["key"]: z for z in zones}
    assert len(keys) == len(zones), "duplicate zone key"
    retired = []
    for r in cat.get("retired", []):
        into = r["into"]
        assert all(k in keys for k in into), f"{r['id']} retired into unknown zones {into}"
        retired.append({"key": r["id"], "on": r["on"], "into": into, "why": r["why"],
                        "countries": sorted({c for k in into for c in keys[k]["countries"]})})
    return {
        "vocab": "zones",
        "version": "1.0",
        "note": ("The suite's shared zone keys (D4): Watchfloor owns them, Context and Vis read them, COP joins on "
                 "them. countries are ISO 3166-1 alpha-2; map is the zone's [lat, lon] map point. A retired key "
                 "still resolves, with the day and the zones it went into; its countries are theirs combined. "
                 "Built by tools/build_zones.py; never edit by hand."),
        "source": {"program": "watchfloor", "repo": "metacog-osint/more-context", "file": "catalog/entities.json",
                   "catalog_version": cat["catalog_version"], "commit": commit},
        "zones": zones,
        "retired": retired,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    cat = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = build(cat, sys.argv[2])
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{OUT.name}: {len(out['zones'])} zones, {len(out['retired'])} retired, catalog {cat['catalog_version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

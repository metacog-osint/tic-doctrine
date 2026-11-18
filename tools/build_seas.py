"""Build geo/seas.json, the kit's sea gazetteer, from Natural Earth's marine areas (public domain).

    python -I tools/build_seas.py path/to/ne_10m_geography_marine_polys.geojson

Source: Natural Earth 1:10m Physical, "Geography Regions: Marine Areas", file
geojson/ne_10m_geography_marine_polys.geojson of https://github.com/nvkelso/natural-earth-vector at release v5.1.2
(commit f1890d9f152c896d250a77557a5751a93d494776, released 13 May 2022), downloaded 18 Nov 2026 with Tom's approval,
sha256 53f865e8ffa966cdd402145c82c5cd14ee7ce974cd0eb9a3f59f03a4cfd2d66c. Natural Earth is in the public domain
(naturalearthdata.com/about/terms-of-use: "No permission is needed to use Natural Earth").

Each named area becomes one entry: a slug from its English name ("Persian Gulf" -> persian-gulf), the name, Natural
Earth's class (sea, gulf, bay, strait, ocean ...), and its polygons with their holes (islands and the smaller seas
cut out of a larger one), every vertex rounded to 0.01 degree (about 1 km) and none dropped, so a border two areas
share stays the same line in both (thinning each area on its own let neighbours overlap at the edges). The
areas tile the water without overlapping, so a point at sea lies in one area at most. Unnamed areas (Natural Earth's
"generic" internal waters) are left out, and so is the one reef (the Great Barrier Reef, drawn on top of the Coral
Sea). Two areas with the same name are merged into one entry.

Natural Earth has no polygon for some names a reader might expect: the Strait of Hormuz lies in the Persian Gulf and
the Gulf of Oman, Bab el Mandeb is a small polygon at the strait itself, and canals (Suez, Panama, Kiel) are land.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "geo" / "seas.json"
SKIP = {"reef"}          # the Great Barrier Reef lies on top of the Coral Sea: a feature in a sea, not a sea area
RELEASE = "v5.1.2"
COMMIT = "f1890d9f152c896d250a77557a5751a93d494776"
URL = (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{RELEASE}/geojson/"
       "ne_10m_geography_marine_polys.geojson")


def slug(name: str) -> str:
    """ASCII, lower case, words joined by hyphens: "Golfe du Lion" -> golfe-du-lion, "Øresund" -> oresund."""
    folded = unicodedata.normalize("NFKD", name.replace("Ø", "O").replace("ø", "o"))
    folded = folded.encode("ascii", "ignore").decode("ascii").lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")


def display(name: str) -> str:
    """Natural Earth writes two ocean names in capitals ("INDIAN OCEAN"); every other name is already in title case."""
    return name.title() if name.isupper() else name


def thin(ring):
    """The ring rounded to 0.01 degree, with repeated points dropped; None when that leaves no area."""
    out = []
    for x, y in ring:
        p = [round(x, 2), round(y, 2)]
        if not out or p != out[-1]:
            out.append(p)
    if out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 else None


def source() -> str:
    return (f"Natural Earth 1:10m marine areas (ne_10m_geography_marine_polys.geojson, natural-earth-vector {RELEASE}, "
            f"commit {COMMIT[:7]}), public domain; named areas only, reefs left out, rings and holes rounded to "
            "0.01 deg by tools/build_seas.py")


def build(src: dict) -> list[dict]:
    seas = {}
    for f in src["features"]:
        pr = f["properties"]
        # The English name, except for the oceans: name_en is "Atlantic Ocean" for both the North and the South
        # Atlantic, and the label (name) keeps them apart.
        name = pr.get("name") if pr.get("featurecla") == "ocean" else (pr.get("name_en") or pr.get("name"))
        if not name or pr.get("featurecla") in SKIP:
            continue
        g = f["geometry"]
        for poly in g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]:
            outer = thin(poly[0])
            if not outer:
                continue
            holes = [h for h in (thin(r) for r in poly[1:]) if h]
            e = seas.setdefault(slug(name), {"slug": slug(name), "name": display(name), "kind": pr.get("featurecla"),
                                             "polygons": []})
            e["polygons"].append([outer] + holes)
    out = []
    for e in sorted(seas.values(), key=lambda e: e["slug"]):
        xs = [p[0] for poly in e["polygons"] for p in poly[0]]
        ys = [p[1] for poly in e["polygons"] for p in poly[0]]
        out.append({**e, "bbox": [min(xs), min(ys), max(xs), max(ys)]})
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    seas = build(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"source": source(), "url": URL, "licence": "Public domain (Natural Earth)",
                               "order": "[lon, lat]; polygons are [outer ring, holes...]",
                               "seas": seas}, separators=(",", ":"), ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"wrote {OUT}: {len(seas)} areas, {OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

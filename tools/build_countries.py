"""Build geo/countries.json, a compact country lookup, and geo/points.json, one label point per country, from
Natural Earth admin 0 (public domain).

    python tools/build_countries.py path/to/ne_50m_admin_0_countries.geojson

Keeps the ISO 3166-1 alpha-2 code (ISO_A2_EH where ISO_A2 is -99, as for France and Norway), the name, and each
polygon ring thinned to points at least TOL degrees apart and rounded to 0.01 degree (about 1 km). Good enough to tag
an item with its countries; not for drawing borders. The label point is Natural Earth's LABEL_Y/LABEL_X, placed
inside the country, so every program puts a country-level item in the same place.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "geo" / "countries.json"
POINTS = ROOT / "geo" / "points.json"
TOL = 0.05


def thin(ring):
    out = []
    for x, y in ring:
        p = [round(x, 2), round(y, 2)]
        if not out or abs(p[0] - out[-1][0]) >= TOL or abs(p[1] - out[-1][1]) >= TOL:
            out.append(p)
    if out[0] != out[-1]:
        out.append(out[0])
    if len(out) < 4:                        # small places (Gaza, islands) keep every rounded point instead of vanishing
        out = [[round(x, 2), round(y, 2)] for x, y in ring]
    return out if len(out) >= 4 else None


def main() -> int:
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    countries, points = [], {}
    for f in src["features"]:
        pr = f["properties"]
        cc = pr.get("ISO_A2") if pr.get("ISO_A2") not in (None, "-99") else pr.get("ISO_A2_EH")
        if not cc or cc == "-99":
            continue
        if pr.get("LABEL_Y") is not None and cc not in points:
            points[cc] = [round(pr["LABEL_Y"], 3), round(pr["LABEL_X"], 3)]
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = []
        for poly in polys:
            outer = thin(poly[0])           # holes are rare at this scale and ignored
            if outer:
                rings.append(outer)
        if rings:
            xs = [p[0] for r in rings for p in r]
            ys = [p[1] for r in rings for p in r]
            countries.append({"cc": cc, "name": pr.get("NAME"), "bbox": [min(xs), min(ys), max(xs), max(ys)], "rings": rings})
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "source": f"Natural Earth admin 0 countries ({Path(sys.argv[1]).name}), public domain; rings thinned to {TOL} deg "
                  "and rounded to 0.01 deg by tools/build_countries.py",
        "countries": countries}, separators=(",", ":")), encoding="utf-8")
    POINTS.write_text(json.dumps({
        "source": "Natural Earth admin 0 LABEL_Y/LABEL_X (public domain), by tools/build_countries.py",
        "order": "[lat, lon]",
        "points": dict(sorted(points.items()))}, indent=0, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(countries)} countries, {OUT.stat().st_size // 1024} KB; {POINTS}: {len(points)} points")
    return 0


if __name__ == "__main__":
    sys.exit(main())

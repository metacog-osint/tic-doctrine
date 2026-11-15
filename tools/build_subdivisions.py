"""Build geo/subdivisions.json, a state and province lookup, from Natural Earth admin 1 at 1:10m (public domain).

    python tools/build_subdivisions.py path/to/ne_10m_admin_1_states_provinces.geojson

Keeps the ISO 3166-2 code (`iso_3166_2`), the name and each polygon ring thinned to points at least TOL degrees
apart and rounded to 0.001 degree (about 100 m), for the countries in COUNTRIES only (the United States for now).
Finer than geo/countries.json on purpose: state lines run through cities (the Red River between Fargo, ND and
Moorhead, MN is about 1 km from either downtown), so a 5 km thinning would put a city in the wrong state. Still for
tagging items, not for drawing borders.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "geo" / "subdivisions.json"
TOL = 0.004
COUNTRIES = {"US"}
CODE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")


def thin(ring):
    out = []
    for x, y in ring:
        p = [round(x, 3), round(y, 3)]
        if not out or abs(p[0] - out[-1][0]) >= TOL or abs(p[1] - out[-1][1]) >= TOL:
            out.append(p)
    if out[0] != out[-1]:
        out.append(out[0])
    if len(out) < 4:
        out = [[round(x, 3), round(y, 3)] for x, y in ring]
    return out if len(out) >= 4 else None


def main(path):
    src = json.loads(Path(path).read_text(encoding="utf-8"))
    subs = []
    for f in src["features"]:
        pr = f["properties"]
        code = pr.get("iso_3166_2")
        if pr.get("iso_a2") not in COUNTRIES or not isinstance(code, str) or not CODE.match(code):
            continue
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        rings = [r for r in (thin(p[0]) for p in polys) if r]   # outer rings only; no US state has a hole that matters
        xs = [x for r in rings for x, _ in r]
        ys = [y for r in rings for _, y in r]
        subs.append({"code": code, "name": pr.get("name"), "bbox": [min(xs), min(ys), max(xs), max(ys)],
                     "rings": rings})
    subs.sort(key=lambda s: s["code"])
    doc = {"source": (f"Natural Earth admin 1 states and provinces, 1:10m ({Path(path).name}), public domain; "
                      f"countries {', '.join(sorted(COUNTRIES))} only; outer rings thinned to {TOL} deg and rounded to "
                      "0.001 deg by tools/build_subdivisions.py"),
           "subdivisions": subs}
    OUT.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"{len(subs)} subdivisions, {sum(len(r) for s in subs for r in s['rings'])} points, "
          f"{OUT.stat().st_size // 1024} KB -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])

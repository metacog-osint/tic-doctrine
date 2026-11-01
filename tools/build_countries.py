"""Build geo/countries.json, a compact country lookup, and geo/points.json, one label point per country, from
Natural Earth admin 0 (public domain).

    python tools/build_countries.py path/to/ne_50m_admin_0_countries.geojson

Keeps the ISO 3166-1 alpha-2 code (ISO_A2_EH where ISO_A2 is -99, as for France and Norway, or not a two-letter
code), the full country name, and each polygon ring thinned to points at least TOL degrees apart and rounded to 0.01
degree (about 1 km). Good enough to tag an item with its countries; not for drawing borders. The label point is
Natural Earth's LABEL_Y/LABEL_X, placed inside the country, so every program puts a country-level item in the same
place.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "geo" / "countries.json"
POINTS = ROOT / "geo" / "points.json"
TOL = 0.05
ISO2 = re.compile(r"^[A-Z]{2}$")             # the feed contract's country check (XK for Kosovo passes)

# Natural Earth codes that are not ISO 3166-1 alpha-2. Its ISO_A2 for Taiwan is "CN-TW", which the feed contract rejects.
CODES = {"CN-TW": "TW"}

# Natural Earth's NAME is a short map label ("S. Sudan", "Dem. Rep. Congo"). Items and titles use the full name.
# "Congo" becomes "Republic of the Congo" so it cannot be read as the Democratic Republic of the Congo.
NAMES = {
    "AG": "Antigua and Barbuda", "AU": "Australia", "BA": "Bosnia and Herzegovina", "BL": "Saint Barthélemy",
    "CD": "Democratic Republic of the Congo", "CF": "Central African Republic", "CG": "Republic of the Congo",
    "CK": "Cook Islands", "DO": "Dominican Republic", "EH": "Western Sahara", "FK": "Falkland Islands",
    "FO": "Faroe Islands", "GQ": "Equatorial Guinea", "GS": "South Georgia and the South Sandwich Islands",
    "HM": "Heard Island and McDonald Islands", "IO": "British Indian Ocean Territory", "KN": "Saint Kitts and Nevis",
    "KY": "Cayman Islands", "MF": "Saint Martin", "MH": "Marshall Islands", "MP": "Northern Mariana Islands",
    "PF": "French Polynesia", "PM": "Saint Pierre and Miquelon", "PN": "Pitcairn Islands", "SB": "Solomon Islands",
    "SS": "South Sudan", "SZ": "Eswatini", "TC": "Turks and Caicos Islands",
    "TF": "French Southern and Antarctic Lands", "TW": "Taiwan", "VC": "Saint Vincent and the Grenadines",
    "VG": "British Virgin Islands", "VI": "US Virgin Islands", "WF": "Wallis and Futuna",
}

# Places Natural Earth files under another country's code. The entry keeps that country's name, so geo.name("AU") is
# "Australia" whichever entry comes first, and names the place in "part".
PARTS = {"Indian Ocean Ter.": "Australian Indian Ocean Territories", "Ashmore and Cartier Is.": "Ashmore and Cartier Islands"}


def code(pr) -> str | None:
    """ISO 3166-1 alpha-2 code for a Natural Earth feature, or None (Somaliland, Northern Cyprus and the like)."""
    for key in ("ISO_A2", "ISO_A2_EH"):
        v = CODES.get(pr.get(key), pr.get(key))
        if isinstance(v, str) and ISO2.match(v):
            return v
    return None


def entry(cc: str, ne_name: str) -> dict:
    """The code, full name and (for a place filed under another country's code) the place's name."""
    out = {"cc": cc, "name": NAMES.get(cc) or ne_name}
    if ne_name in PARTS:
        out["part"] = PARTS[ne_name]
    return out


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


def source(src_name: str) -> str:
    return (f"Natural Earth admin 0 countries ({src_name}), public domain; rings thinned to {TOL} deg and rounded to "
            "0.01 deg, codes made ISO 3166-1 alpha-2 (Taiwan TW) and short names made full by tools/build_countries.py")


def main() -> int:
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    countries, points = [], {}
    for f in src["features"]:
        pr = f["properties"]
        cc = code(pr)
        if not cc:
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
            countries.append({**entry(cc, pr.get("NAME")), "bbox": [min(xs), min(ys), max(xs), max(ys)], "rings": rings})
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "source": source(Path(sys.argv[1]).name),
        "countries": countries}, separators=(",", ":")), encoding="utf-8")
    POINTS.write_text(json.dumps({
        "source": "Natural Earth admin 0 LABEL_Y/LABEL_X (public domain), by tools/build_countries.py",
        "order": "[lat, lon]",
        "points": dict(sorted(points.items()))}, indent=0, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(countries)} countries, {OUT.stat().st_size // 1024} KB; {POINTS}: {len(points)} points")
    return 0


if __name__ == "__main__":
    sys.exit(main())

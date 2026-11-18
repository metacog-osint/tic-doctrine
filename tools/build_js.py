"""Write the vocabulary block of js/tic-doctrine.js from vocab/*.json.

    python tools/build_js.py          # rewrite the block
    python tools/build_js.py --check  # exit 1 if the block is out of date (CI)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "js" / "tic-doctrine.js"
BEGIN, END = "// BEGIN GENERATED VOCAB", "// END GENERATED VOCAB"


def vocab(name):
    return json.loads((ROOT / "vocab" / f"{name}.json").read_text(encoding="utf-8"))


def block() -> str:
    conf = vocab("confidence")
    infra = vocab("infrastructure")
    data = {
        "version": {"likelihood": vocab("likelihood")["version"], "confidence": conf["version"]},
        "likelihood": [
            {k: t[k] for k in ("id", "step", "term", "synonym", "lower", "upper", "band_label", "uk")}
            for t in vocab("likelihood")["terms"]
        ],
        "confidence": {lv["id"]: {"term": lv["term"], "meaning": lv["meaning"]} for lv in conf["levels"]},
        "confidence_label": conf["label"],
        "lifeline_status": infra["lifelines"]["status"],
        "lifelines": {k: {"name": v["name"], "abbr": v["abbr"]} for k, v in infra["lifelines"]["values"].items()},
        "points": json.loads((ROOT / "geo" / "points.json").read_text(encoding="utf-8"))["points"],
        "actor_roles": {k: {"label": r["label"], "frame": r["frame"]}
                        for k, r in vocab("actors")["roles"]["values"].items()},
        "actor_types": {k: t["label"] for k, t in vocab("actors")["types"]["values"].items()},
        "ladders": {
            k: {"name": v["name"], "values": v["values"]}
            for k, v in vocab("grading")["response_stage"]["ladders"].items()
        },
        "last_change": vocab("enums")["last_change"]["values"],
        "place_basis": vocab("enums")["place_basis"]["values"],
        "seas": {s["slug"]: s["name"]
                 for s in json.loads((ROOT / "geo" / "seas.json").read_text(encoding="utf-8"))["seas"]},
    }
    return f"{BEGIN}\nexport const VOCAB = {json.dumps(data, indent=2, ensure_ascii=False)};\n{END}"


def main() -> int:
    text = JS.read_text(encoding="utf-8")
    start, end = text.index(BEGIN), text.index(END) + len(END)
    new = text[:start] + block() + text[end:]
    if "--check" in sys.argv:
        if new != text:
            print("js/tic-doctrine.js vocabulary block is out of date: run python tools/build_js.py")
            return 1
        print("js/tic-doctrine.js vocabulary block is current")
        return 0
    JS.write_text(new, encoding="utf-8", newline="\n")
    print("wrote", JS)
    return 0


if __name__ == "__main__":
    sys.exit(main())

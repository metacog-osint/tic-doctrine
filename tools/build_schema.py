"""Write schema/feed-item-v2.schema.json (JSON Schema 2020-12) from the vocab files.

The schema is the published, machine-readable form of feed contract v2 for anyone
consuming the feeds. The kit's own linter (python/tic_doctrine/contract.py) does the
checking, including the conditional rules a schema expresses poorly.

    python tools/build_schema.py [--check]
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "schema" / "feed-item-v2.schema.json"


def v(name):
    return json.loads((ROOT / "vocab" / f"{name}.json").read_text(encoding="utf-8"))


def enum(name):
    return {"enum": sorted(v("enums")[name]["values"]), "description": v("enums")[name]["basis"]}


def schema() -> dict:
    fw, infra, grading, actors = v("frameworks"), v("infrastructure"), v("grading"), v("actors")
    seas = [s["slug"] for s in json.loads((ROOT / "geo" / "seas.json").read_text(encoding="utf-8"))["seas"]]
    utc = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?Z$"}
    tags = lambda name: {"type": "array", "items": {"enum": sorted(fw[name]["values"])}}  # noqa: E731
    stages = sorted(f"{l}:{val}" for l, d in grading["response_stage"]["ladders"].items() for val in d["values"])
    props = {
        "contract": {"const": "tic-feed/2"},
        "id": {"type": "string", "minLength": 1},
        "program": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1, "description": "What happened, one line."},
        "summary": {"type": "string", "description": "Bottom line up front; required for judgments."},
        "kind": enum("kind"), "tier": enum("tier"), "status": enum("status"), "msg_type": enum("msg_type"),
        "human_review": enum("human_review"), "status_class": enum("status_class"),
        "precision_class": enum("precision_class"), "product_category": enum("product_category"),
        "us_person_data": enum("us_person_data"),
        "supersedes": {"type": "string"},
        "data_as_of": utc | {"description": "When the information was true (UTC)."},
        "data_as_of_precision": enum("data_as_of_precision"),
        "published_at": utc | {"description": "When this item was published (UTC)."},
        "valid_until": utc,
        "countries": {"type": "array", "items": {"type": "string", "pattern": "^[A-Z]{2}$"}},
        "subdivisions": {"type": "array", "items": {"type": "string", "pattern": "^[A-Z]{2}-[A-Z0-9]{1,3}$"}},
        "coverage_fraction": {"type": "number", "minimum": 0, "maximum": 1},
        "baseline_ref": {"type": "object", "required": ["id", "window", "type"],
                         "properties": {"type": {"enum": ["fixed", "rolling", "both"]}}},
        "method_version": {"type": "string"},
        "requirement_ids": {"type": "array", "items": {"type": "string"}},
        "warning_problem_id": {"type": "string"}, "hypothesis_id": {"type": "string"},
        "indicator_id": {"type": "string"},
        "direction": enum("direction"), "indicator_state": enum("indicator_state"),
        "probability": {"type": "number", "minimum": 0, "maximum": 1, "description": "Stored number; the source of truth."},
        "likelihood_term": {"enum": [t["id"] for t in v("likelihood")["terms"]]},
        "confidence": {"enum": ["low", "moderate", "high"]},
        "confidence_basis": {"type": "object"},
        "change_from_prior": enum("change_from_prior"), "change_reason": {"type": "string"},
        "alternatives": {"type": "array", "items": {"type": "object", "required": ["hypothesis", "tell_apart"]}},
        "resolution": {"type": "object", "required": ["rule", "source", "resolve_by"]},
        "evidence_hash": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "archive_url": {"type": "string"},
        "visual": {"type": "object", "required": ["type", "url"]},
        "sources": {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["publisher", "licence"],
            "properties": {"grade": {"type": "string", "pattern": "^[A-F][1-6]$"},
                           "author": {"type": "string"}, "title": {"type": "string"},
                           "outlet": {"type": "string"}, "source_type": {"type": "string"},
                           "descriptor": {"type": "string"}, "lineage_id": {"type": "string"},
                           "independence_group": {"type": "string"},
                           "owner": {"enum": sorted(actors["source_owner"]["values"]),
                                     "description": actors["source_owner"]["basis"]},
                           "perspective": {"type": "string", "minLength": 1,
                                           "description": "The program's source group: the perspective the source "
                                                          "speaks from (e.g. russian_state), so coverage splits by side. "
                                                          "Labels go in the feed header's perspectives map."},
                           "accessed_at": utc, "published_at": utc}}},
        "actors": {"type": "array", "description": actors["note"], "items": {
            "type": "object", "required": ["name", "role", "status_class"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "role": {"enum": sorted(actors["roles"]["values"]), "description": actors["roles"]["basis"]},
                "actor_type": {"enum": sorted(actors["types"]["values"]), "description": actors["types"]["basis"]},
                "side": {"type": "string", "description": "The party, named as the sources name it. Required for "
                                                          "party and supporter; never a judgment of friend or foe."},
                "function": {"type": "string", "description": "What a third party does: mediator, monitor, aid."},
                "country": {"type": "string", "pattern": "^[A-Z]{2}$"},
                "status_class": enum("status_class"),
                "source_ids": {"type": "array", "items": {"type": "string"},
                               "description": "ids from this item's sources[] that the characterisation rests on."},
                "designations": {"type": "array", "items": {
                    "type": "object", "required": ["by", "label"],
                    "properties": {"by": {"type": "string"}, "label": {"type": "string"},
                                   "source_id": {"type": "string"}}},
                    "description": "Government designations, quoted as published (e.g. a sanctions listing)."},
                "ref": {"type": "string", "description": "A stable id for the actor, e.g. wikidata:Q12345."}}}},
        "ie_aspect": tags("ie_aspect"), "pmesii_pt": tags("pmesii_pt"), "ascope": tags("ascope"),
        "continuum": {"enum": sorted(fw["continuum"]["values"])},
        "ncf": {"type": "array", "items": {"enum": sorted(infra["ncf"])}},
        "sector": {"type": "array", "items": {"enum": sorted(infra["sectors"])},
                   "description": "Derived from ncf through vocab/infrastructure.json."},
        "lifeline": {"type": "array", "items": {"type": "object", "required": ["id", "status"], "properties": {
            "id": {"enum": sorted(infra["lifelines"]["values"])},
            "status": {"enum": sorted(infra["lifelines"]["status"])}}}},
        "response_stage": {"enum": stages},
        "disarm_technique": {"type": "array", "items": {"type": "string", "pattern": "^T[0-9]{4}(\\.[0-9]{3})?$"}},
        # Revision 2.1 (kit 0.6.0): all optional; the linter notes their absence and never fails a build on it.
        "last_change": enum("last_change") | {"description": "Revision 2.1. The most recent change in the state of "
                                                             "the item's subject (tier and response_stage, or the "
                                                             "program's own level)."},
        "last_change_at": utc | {"description": "Revision 2.1. When that change happened, as the source dates it; "
                                                "else the program's first reading in the new state. Absent only with "
                                                "last_change none."},
        "event_start": utc | {"description": "Revision 2.1. When what the item describes began in the world, or is "
                                             "scheduled to; for a notice, when it takes effect."},
        "event_end": utc | {"description": "Revision 2.1. When it ended or is scheduled to end; given only when the "
                                           "source says so. With none, the event runs to data_as_of."},
        "event_time_precision": enum("event_time_precision"),
        "subject_id": {"type": "string", "minLength": 1, "pattern": r"^\S+$",
                       "description": "Revision 2.1. The thing the item is a reading of, with no date or run stamp: "
                                      "the id itself where the id is stable, else program:kind:key. History and COP "
                                      "key on it."},
        "signal": {"type": "object", "required": ["name", "value"],
                   "description": "Revision 2.1. The one number the item's tier rests on, with its baseline.",
                   "properties": {
                       "name": {"type": "string", "minLength": 1, "description": "What is measured."},
                       "value": {"type": "number"}, "unit": {"type": "string"},
                       "expected": {"type": "number", "description": "The baseline's central value."},
                       "tail": enum("signal_tail"),
                       "baseline_n": {"type": "integer", "minimum": 0, "description": "Readings in the baseline."},
                       "exceedance": {"type": "number", "minimum": 0, "maximum": 1,
                                      "description": "Share of this subject's own baseline readings at least as "
                                                     "extreme as this one; no finer than 1/(baseline_n+1)."}}},
        "sea_areas": {"type": "array", "items": {"enum": sorted(seas)},
                      "description": "Revision 2.1. Slugs of the named sea areas the geometry overlaps, from the "
                                     "kit's gazetteer (geo/seas.json, Natural Earth marine areas); [] on land."},
        "place_basis": enum("place_basis"),
        "corroboration": {
            "type": "object", "required": ["state", "origins", "first_reported_at", "rule"],
            "description": "Revision 2.1, F7 (kit 0.6.2, D11). Event items only: reported until two independent "
                           "origins, or one official source within its remit; never moves back.",
            "properties": {
                "state": enum("corroboration_state"),
                "basis": {"oneOf": [enum("corroboration_basis"), {"type": "null"}]},
                "origins": {"type": "integer", "minimum": 1},
                "official": {"type": ["string", "null"]},
                "party_claim": {"type": "boolean"},
                "first_reported_at": utc, "corroborated_at": {"oneOf": [utc, {"type": "null"}]},
                "rule": {"type": "string", "minLength": 1}}},
    }
    props["baseline_ref"]["properties"]["flag_rate"] = {
        "type": "number", "minimum": 0, "maximum": 1,
        "description": "Revision 2.1. Share of baseline readings on which this subject was flagged."}
    props["sources"]["items"]["properties"]["lane"] = {
        "type": "string", "minLength": 1,
        "description": "Revision 2.1. The source lane's key in the feed header's health, when it is not the source id."}
    required = ["contract", "id", "program", "title", "kind", "tier", "status", "msg_type", "human_review",
                "us_person_data", "status_class", "data_as_of", "published_at", "countries", "method_version", "sources"]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://theintelligence.company/schema/feed-item-v2.schema.json",
        "title": "The Intelligence Company feed item, contract v2",
        "description": "Properties of one GeoJSON Feature (or one flat item). Conditional rules (judgments need "
                       "probability, confidence, alternatives and change; forecasts need a resolution rule; every item "
                       "needs a geometry or a visual) are enforced by the kit's tradecraft linter.",
        "type": "object",
        "required": required,
        "properties": props,
        "$defs": {"feed_header": header_schema(utc)},
    }


def header_schema(utc: dict) -> dict:
    """The FeatureCollection's own members (revision 2.1 documents contract_rev, kit and health)."""
    e = v("enums")
    return {
        "type": "object",
        "required": ["contract", "program", "generated_at", "licence", "attribution"],
        "properties": {
            "contract": {"const": "tic-feed/2"},
            "contract_rev": {"enum": sorted(e["contract_rev"]["values"]), "description": e["contract_rev"]["basis"]},
            "kit": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$", "description": "The vendored kit version."},
            "program": {"type": "string"}, "generated_at": utc, "licence": {"type": "string"},
            "attribution": {"type": "string"}, "language_key": {"type": "string"},
            "perspectives": {"type": "object", "additionalProperties": {"type": "string"}},
            "health": {
                "type": "object",
                "description": "One entry per source lane, keyed by lane id, written on every run. A lane counts "
                               "as read when last_ok equals checked_at and its state is fresh, late or up.",
                "additionalProperties": {
                    "type": "object", "required": ["state", "checked_at", "last_ok"],
                    "properties": {
                        "state": {"enum": sorted(e["health_state"]["values"]), "description": e["health_state"]["basis"]},
                        "checked_at": utc, "last_ok": {"anyOf": [utc, {"type": "null"}]},
                        "last_error": {"type": ["string", "null"]}, "failures": {"type": "integer", "minimum": 0},
                        "data_as_of": utc | {"description": "The newest data that source holds."},
                        "detail": {"type": "string"}}}},
        },
    }


def main() -> int:
    text = json.dumps(schema(), indent=2, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("schema", "current" if ok else "out of date: run python tools/build_schema.py")
        return 0 if ok else 1
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

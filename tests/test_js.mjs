// Browser-module tests (Node, no dependencies): node tests/test_js.mjs
import assert from "node:assert/strict";
import { termFor, likelihoodLabel, judgmentChips, lifelineStatus, ladderRung, changeText, indicatorStyle, countryPoint, actorStyle, actorLabel, tips, tipMatches, asOfDateLabel, VOCAB } from "../js/tic-doctrine.js";

const cases = { 0: "almost_no_chance", 0.05: "very_unlikely", 0.2: "unlikely", 0.45: "roughly_even_chance",
  0.55: "roughly_even_chance", 0.551: "likely", 0.8: "likely", 0.801: "very_likely", 0.95: "very_likely", 0.951: "almost_certain", 1: "almost_certain" };
for (const [p, want] of Object.entries(cases)) assert.equal(termFor(Number(p)).id, want, p);
assert.equal(likelihoodLabel(0.7), "Likely (55-80%)");
assert.throws(() => termFor(1.2));
assert.throws(() => termFor("0.5"));

const chips = judgmentChips({ probability: 0.7, confidence: "moderate" });
assert.equal(chips.length, 2, "likelihood and confidence are separate chips");
assert.equal(chips[1].edge, "dashed");
assert.ok(!chips[0].text.includes("onfidence"), "likelihood chip never mentions confidence");

assert.equal(lifelineStatus("significant").hex, "#C52038");
assert.equal(lifelineStatus("nonsense").letter, "U", "unknown status falls back to grey");
assert.equal(ladderRung("pager:orange").severity, 3);
assert.equal(ladderRung("state_travel_advisory:level_4").meaning, "Do not travel.");
assert.equal(ladderRung("pager:purple"), null);
assert.equal(ladderRung("usgs_volcano:warning").severity, 4);
assert.equal(ladderRung("usgs_volcano:unassigned"), null, "UNASSIGNED is not a rung");
assert.equal(changeText({ change_from_prior: "raised", probability: 0.7 }, 0.5).text, "Up from Roughly even chance to Likely");
assert.ok(indicatorStyle(undefined).grey, "missing state draws as no data");
assert.equal(Object.keys(VOCAB.lifelines).length, 8);
assert.deepEqual(countryPoint("ua"), [49.725, 32.141], "label point, lower-case code accepted");
assert.equal(countryPoint("ZZ"), null);
assert.ok(countryPoint("TW"), "Taiwan has a label point under its ISO code");
assert.equal(countryPoint("CN-TW"), null, "Natural Earth's CN-TW is not a code the kit emits");
for (const cc of Object.keys(VOCAB.points)) assert.match(cc, /^[A-Z]{2}$/, cc);

// Actors: frames are unknown or neutral only; claims draw hollow.
for (const [k, r] of Object.entries(VOCAB.actor_roles)) assert.ok(["unknown", "neutral"].includes(r.frame), k);
assert.equal(actorStyle({ role: "party", status_class: "reported" }).frame, "unknown");
assert.equal(actorStyle({ role: "civilians", status_class: "reported" }).frame, "neutral");
assert.ok(actorStyle({ role: "responsible", status_class: "claimed" }).hollow, "a claim draws hollow");
assert.ok(!actorStyle({ role: "party", status_class: "assessed" }).hollow);
assert.equal(actorStyle({ role: "nonsense" }).frame, "unknown", "unknown role falls back to unknown");
assert.equal(actorLabel({ name: "Armed forces of Country A", role: "party", side: "Country A" }), "Armed forces of Country A · Party (Country A)");
assert.equal(actorLabel({ name: "Group X", role: "responsible", status_class: "claimed" }), "Group X · Claims responsibility");
assert.equal(actorLabel({ name: "Country B", role: "supporter", side: "Country A" }), "Country B · Supporter of Country A");
assert.equal(actorLabel({ name: "Monitoring mission", role: "third_party", function: "monitor", side: "ignored" }), "Monitoring mission · Third party (monitor)");
// Tips: the same matching rules as python/tic_doctrine/tips.py.
const bus = [
  { program: "cordon", id: "c1", title: "Ukraine: Level 4, Do Not Travel", countries: ["UA"], tier: "routine", response_stage: "state_travel_advisory:level_4", measures: { level: 4 } },
  { program: "cordon", id: "c2", title: "Poland: Level 1", countries: ["PL"], tier: "routine", response_stage: "state_travel_advisory:level_1", measures: { level: 1 } },
  { cop_program: "noisefloor", id: "n1", title: "GPS interference near Kaliningrad", countries: ["RU"], tier: "anomaly", cop_stale: true },
  { program: "noisefloor", id: "n2", title: "GPS interference near Las Vegas", countries: ["US"], tier: "anomaly" },
  { program: "vigil", id: "v1", title: "Group escalating", countries: [], tier: "anomaly" },
  { program: "watchfloor", id: "w1", title: "Ukraine attention", countries: ["UA"], tier: "anomaly" },
];
const interests = { program: "watchfloor", areas: { "WF-WP-Z01": ["UA"], "WF-WP-Z07": ["RU", "PL"] }, interests: [
  { id: "WF-INT-1", programs: ["cordon"], response_stage_prefix: ["state_travel_advisory:"], where: [{ path: "measures.level", op: "gte", value: 3 }] },
  { id: "WF-INT-3", programs: ["noisefloor"], tiers: ["anomaly"] },
  { id: "WF-INT-4", programs: ["vigil", "watchfloor"], tiers: ["anomaly"], global: true },
] };
const got = tips(bus, interests).map((t) => `${t.interest_id}:${t.item.id}:${t.areas.join(",")}:${t.stale}`);
assert.deepEqual(got, ["WF-INT-1:c1:WF-WP-Z01:false", "WF-INT-3:n1:WF-WP-Z07:true", "WF-INT-4:v1::false"],
  "level filter, areas, stale bus items, global items, and never the program's own items");
assert.ok(!tipMatches(bus[1], interests.interests[0]), "level 1 fails the where test");
const anywhere = { ...interests, boxes: { "WF-WP-Z01": [22, 44, 41, 53] }, interests: [{ id: "WF-INT-6", programs: ["noisefloor"], tiers: ["anomaly"], anywhere: true }] };
const geomItem = { program: "noisefloor", id: "n3", title: "Black Sea jamming", countries: [], tier: "anomaly", geometry: { type: "Point", coordinates: [31.5, 45.2] } };
assert.deepEqual(tips([...bus, geomItem], anywhere).map((t) => `${t.item.id}:${t.areas.join(",")}`), ["n1:WF-WP-Z07", "n2:", "n3:WF-WP-Z01"],
  "anywhere keeps matches outside every area, labelled when inside one by country or bbox");
assert.equal(asOfDateLabel({ data_as_of: "2025-06-01T00:00:00Z", data_as_of_precision: "month" }, "en-GB"), "June 2025");
assert.equal(asOfDateLabel({ data_as_of: "2026-10-30T00:00:00Z", data_as_of_precision: "day" }, "en-GB"), "30 Oct 2026",
  "a date-only item reads in UTC, never the evening before");
assert.equal(asOfDateLabel({ data_as_of: "2026-10-30T09:12:00Z" }), null, "an exact time is left to the page");
console.log("test_js.mjs: all passed");

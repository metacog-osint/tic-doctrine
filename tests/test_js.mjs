// Browser-module tests (Node, no dependencies): node tests/test_js.mjs
import assert from "node:assert/strict";
import { termFor, likelihoodLabel, judgmentChips, lifelineStatus, ladderRung, changeText, indicatorStyle, countryPoint, actorStyle, actorLabel, VOCAB } from "../js/tic-doctrine.js";

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
assert.equal(changeText({ change_from_prior: "raised", probability: 0.7 }, 0.5).text, "Up from Roughly even chance to Likely");
assert.ok(indicatorStyle(undefined).grey, "missing state draws as no data");
assert.equal(Object.keys(VOCAB.lifelines).length, 8);
assert.deepEqual(countryPoint("ua"), [49.725, 32.141], "label point, lower-case code accepted");
assert.equal(countryPoint("ZZ"), null);

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
console.log("test_js.mjs: all passed");

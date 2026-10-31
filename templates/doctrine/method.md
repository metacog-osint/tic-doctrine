# Method (template)

Replace each section with the program's own words. Keep it short; link to longer write-ups.

## What it measures
One paragraph: the measurement, its unit, and where the data come from.

## Baselines
Fixed reference window and rolling window, side by side (JP 2-01.3 warns that an adversary can condition analysts to
accept unusual activity as normal). Name the version of each.

## Anomaly versus warning
An anomaly is a measurement outside the baseline. A warning is a judgment with likelihood, confidence, alternatives and
what would change it. Say which rules turn one into the other.

## Confidence
Computed by the kit's rubric (rule-based, not statistical). Name the program's independence groups and any overrides.

## Gaps and no-data
What happens when a source fails or coverage drops: the layer turns grey and says "no data", never quiet.

## Human review
none, sampled or full, and who does it.

## Change log
Method versions with dates and what changed.

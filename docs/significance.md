# Significance of closures and official warnings (tic-significance-0.1, draft)

**Status: draft (25 Nov 2026).** Nothing here is built yet. Cordon is under a change freeze to 12 Dec 2026,
so its part waits until then; COP's part follows Cordon's.

## Why

A closure or an official warning is the **footprint** of an event: a flight restriction, a navigation warning, a
safety zone, an evacuation order, a travel advisory. The suite reads many footprints, but it rates each one by its own
shape. Cordon's flight-restriction `impact`, for example, measures what a restriction does to air traffic (distance to
the 30 busiest US airports, size, height). That is the right measure for aviation and the wrong one for the event.

**The case that started this.** On 25 Nov 2026 the US Army detonated about 5 tons of degraded lead azide at the Iowa
Army Ammunition Plant, Middletown, Iowa, after a federal court allowed it; residents within 5 miles were urged to
leave, and the date had slipped from 20 Nov. Cordon held every FAA restriction for it: 6/8596 (for 20 Nov, first seen
18 Nov), 6/9186 (23-25 Nov, after the date moved) and its re-issue 6/9722, a 4 NM circle from the surface to 4,000 ft
under 14 CFR 91.137(a)(1), text "CONTROLLED DETONATION". Every one was rated **routine, impact low**: small, low and
301 km from O'Hare, and the later ones counted as re-issues, which Cordon's anomaly rule does not treat as new. No
other program placed anything in Iowa, no non-weather alert came through the National Weather Service for Des Moines
County, and FEMA's public alert archive held nothing for it through 24 Nov. Two official publishers did carry it,
in feeds no program reads: EPA's emergency-response site "IAAAP Lead Azide" (response.epa.gov, Region 7, an
emergency removal assessment with a point location), whose dated updates start on 18 Nov with EPA's emergency permit
for the 68 drums; and the Army's announcements on DVIDS (24 Nov, about 11 hours before the detonation).

So significance has to be measured from the **event**: what caused the footprint, how rare that is here, what else is
happening at the same place and time, and what lies inside it.

## Words used here

- **Footprint:** one official notice with a place and a time: a TFR, a NOTAM, a navigation warning, a safety zone, a
  public alert, an advisory.
- **Chain:** the footprints that are readings of one restriction over time (re-issues, extensions, date changes).
  Cordon already keys this as the feed's `subject_id`.
- **Event:** what the footprints are about. Footprints from different publishers (the FAA and a county, say) join into
  one event when they meet the joining rule below.
- **Significance:** how much an event stands out, as a measured rank: `routine`, `notable` or `significant`. It is
  **not a warning and not a prediction**. It never says anything will happen; it says this event is unusual, many
  separate sources are talking about it, or many people or important sites are inside it.

## The steps

```
footprints -> chains -> cause -> rarity and dynamics -> events (joining) -> coincidence -> consequence -> tier
                (program)                                                 (COP)
```

Each program that reads footprints does the first part for its own items (Cordon for official notices; Launch keeps
space operations; Elements keeps weather). COP joins footprints across programs into events and adds coincidence,
because only COP sees every program. Every step writes its reasons, so the tier can always be explained in a sentence.

### 1. Footprints

The inputs, by kind. "Have" means a program reads it today. The sources section gives each new one's terms, access,
measured lag and a verdict (build, build later, don't).

| Kind | National | Local |
|---|---|---|
| Air | FAA TFRs and NOTAMs (Cordon, have) | the same: most local hazards reach the FAA as a 91.137 TFR |
| Sea | NGA NAVAREA and HYDROPAC warnings (Cordon, have) | Coast Guard notices to mariners and Federal Register safety zones |
| Ground | DHS NTAS bulletins, FEMA declarations, EPA response sites, NRC event reports | IPAWS public alerts (evacuation, shelter in place, civil danger, hazardous materials), state road closures |
| Abroad | State, FCDO, Canada, NZ, CDC, EASA (Cordon, have) | national civil-protection alert feeds |
| Official releases | DVIDS (the Defense Department's release service), Federal Register rules | EPA emergency-response sites (response.epa.gov), installation and agency releases |

Official releases are footprints too when they name a place and a time: EPA opens a response site with a point
location for an emergency, and the Army announced the Iowa detonation and its relocation zone on DVIDS.

### 2. Cause

Every footprint gets one cause from a fixed list, from its legal basis first and its words second, with `cause_basis`
naming what matched. The legal basis is the stronger signal, because the publisher chose it.

| Cause group | Causes | Legal basis that sets it (examples) | Words that set it when the basis does not |
|---|---|---|---|
| Hazard to people | detonation or demolition, hazardous materials, chemical, radiological or nuclear, civil danger, evacuation, shelter in place | TFR 91.137(a)(1) with these words; CAP events Evacuation Immediate, Shelter In Place Warning, Hazardous Materials Warning, Civil Danger Warning, Radiological Hazard Warning, Nuclear Power Plant Warning | DETONATION, EXPLOSIVE, DEMOLITION, HAZMAT, CHEMICAL, RADIOLOGICAL, EVACUAT, SHELTER IN PLACE, TOXIC, PLUME |
| Disaster response | fire, flood, relief operations, search and rescue | TFR 91.137(a)(2) and (a)(3); Fire Warning | FIRE FIGHTING, RELIEF, DISASTER, SEARCH AND RESCUE |
| Security and law enforcement | security area, law enforcement operation | TFR 99.7; CAP Law Enforcement Warning | LAW ENFORCEMENT, SECURITY |
| Military and test | military operation, weapons test, exercise | NGA military, missile and gunnery warnings | MILITARY, MISSILE, GUNNERY, EXERCISE |
| Space operations | launch, reentry | TFR SPACE OPERATIONS (Launch's), NGA launch warnings | (Launch's own rules) |
| Scheduled and routine | VIP movement, sports and air shows, stadiums, public gatherings | TFR 91.141, 91.145, the statutory stadium rule, 49 USC 44812 | (none) |
| Advisory | travel advisory, health notice, conflict-zone bulletin | the advisory's own level | (the program's own level rules) |
| Unknown | none of the above | | |

Two CAP events say little on their own: Local Area Emergency (in November 2026 mostly state road-closure notices)
and Civil Emergency Message. Their cause comes from their words, and with no match they are `unknown`.

A word match never overrides a legal basis from a different group, and words are matched in the notice's own text, not
in a news story about it.

### 3. Rarity and dynamics (each program, against its own history)

**Rarity** is how often this cause appears at this place. It is counted over the program's history at the narrowest
scope that has enough history: the state or province (ISO 3166-2), then the country, then the cause anywhere. A scope
is usable when it holds at least 90 days of history. Rarity is reported as the count and the window ("first detonation
restriction in Iowa in the history held, which starts 2006"), never as a bare score.

- `rare`: no footprint of this cause in this scope in the last 365 days (or in the whole history, if shorter).
- `uncommon`: at most two in the last 365 days.
- `common`: the rest.

**History to count against.** Cordon's own TFR history starts in November 2026, too short. The Internet Archive holds
32,627 distinct FAA TFR detail pages captured between 2006 and 8 Nov 2026 (CDX index, checked 25 Nov 2026), and the
FAA's NMS-API store Cordon keeps from 18 Nov 2026 is permanent. A one-time backfill from the archived pages (cause and
state only, no new claims) gives a multi-year base rate; Cordon's own store takes over as it grows. The archive is
incomplete, so a backfilled count is a lower bound and the item says so.

**Dynamics** are changes along a chain, which often mean an event is drawing attention or is not going to plan:

- `date_slips`: how many times the start moved later (Iowa: two, 20 Nov to 23 Nov to 25 Nov).
- `enlarged`: the footprint grew (Cordon already records this on re-issues).
- `extended`: the end moved later.
- `cancelled_early`: the chain ended before its stated end.

A re-issue is not a new restriction (Cordon's rule stays), but the chain's dynamics now count instead of being dropped.

### 4. Events: joining footprints (COP)

Two footprints are the same event when all of these hold:

- their causes are in the same group, or one is `unknown`;
- they overlap in space, or their nearest edges are within 10 km;
- their times overlap, or one starts within 72 hours of the other ending.

A chain is always one event. The event keeps every footprint, so a reader can see each publisher's own words.

### 5. Coincidence (COP)

How many **independent lines** say something is happening at this place and time, counted by the confidence rubric's
independence rule (`docs/confidence-rubric.md`): two footprints from the same government body, aggregator or sensor
network are one line. Lines that count:

- a second official footprint from a different body (the FAA and FEMA's IPAWS; the FAA and a county; NGA and the Coast
  Guard);
- another program's item inside the event (Elements, Blackout, Vigil, Wake, Relief, Noisefloor);
- press attention: the place's name with the event's dates in Context's or Watchfloor's stories, or a jump in GDELT's
  headline count for the place against its own 30-day level, as Blackout already counts headlines.

Press attention is one line however many outlets carry the story, because outlets copy each other.

### 6. Consequence (each program, from published layers)

What is inside the footprint or, when the notice states one, the announced radius (Iowa: 5 miles):

- **people:** population inside, summed from a gridded population layer;
- **listed sites:** military installations, chemical facilities, nuclear and power plants, ports, from published lists;
- **its own field's impact:** for air, Cordon's existing `impact`; for sea, chokepoints and ports from Wake.

Consequence is measured, not guessed: an item without a layer says "population not measured", not zero.

### 7. Tier

Rule-based, like the confidence rubric: the rules are published so they can be checked and argued with. The thresholds
are this draft's, to be set against the case file (step 8) before anything is built.

| Tier | Rule |
|---|---|
| significant | a **hazard to people** or **disaster response** cause, and at least one of: `rare`; two or more independent lines; 1,000 or more people inside. Or any cause with three or more independent lines, one of them official. |
| notable | any of: `rare` for its cause and place; two or more date slips, or enlarged, in one chain; two or more independent lines; a hazard-to-people cause on its own. |
| routine | the rest. |

**Caps:** a scheduled-and-routine cause (VIP, sports, stadiums, gatherings) is never above notable unless three or more
independent lines agree. An `unknown` cause is never above notable. A stale source counts for nothing.

**Replay of the Iowa case under these rules:** cause hazard to people (91.137(a)(1), "CONTROLLED DETONATION");
`rare` (one detonation restriction in the 43 TFRs Cordon held from 14 to 25 Nov 2026, and the first in Iowa in that
history; the multi-year count waits on the backfill); two date slips; independent lines: the FAA, EPA's emergency
response site (from 18 Nov) and the Army's DVIDS releases (the Army asked for the TFR, so the FAA and Army lines may
share an upstream; counted as one until the rubric says otherwise), and the press. Tier: **significant** from
18 Nov, when the first TFR appeared (a hazard-to-people cause that is rare here), with EPA's site as a second
reason the same day and no need for the press line. In fact no program ranked it above routine. The same 11 days held 26 security restrictions under
99.7 and 6 VIP restrictions; under these rules they stay routine unless they are rare for their place.

### 8. Recall check

A case file of events the suite should rank notable or significant, kept as `cases.jsonl` (one line per event: date,
place, cause, the footprints that should have caught it, the tier expected, and sources). Each method change is
replayed against it, and the method note reports how many cases reached their expected tier. A miss found in daily
use becomes a new case. Case 1 is Iowa, 25 Nov 2026. Cases are added only with dated sources; no case is added from
memory.

The replay also counts the other way: how many routine footprints the rules would lift, so the tier does not drift into
calling everything significant.

## Output

On each item, inside `measures` first, so no feed contract change is needed to start:

```json
"significance": {
  "tier": "significant",
  "method": "tic-significance-0.1",
  "cause": "detonation", "cause_group": "hazard_to_people",
  "cause_basis": ["14 CFR 91.137(a)(1)", "text: CONTROLLED DETONATION"],
  "rarity": "rare", "rarity_basis": "0 in US-IA in 365 days (Cordon history and archived FAA pages, a lower bound)",
  "dynamics": {"date_slips": 2, "enlarged": false, "extended": false},
  "lines": 2, "lines_basis": ["FAA TFR", "press: 4 outlets, one line"],
  "consequence": {"population": null, "sites": ["Iowa Army Ammunition Plant"]},
  "basis": "detonation restriction, rare in Iowa, date moved twice, in the press"
}
```

The reader-facing line is `basis`, written plainly ("detonation restriction, rare in Iowa, date moved twice, in the
press"). Programs put `significant` and `notable` items in their `anomaly` tier (unusual against the program's own
baseline, which is what rarity measures), and COP may make them picks. A promoted field in the feed contract can follow
once two programs use it.

## Who does what

| Step | Owner | Notes |
|---|---|---|
| Footprints, chains, cause, rarity, dynamics, consequence | each program for its own items: Cordon (official notices), Launch (space operations), Elements (weather) | Same cause list and rules, from this kit |
| Non-weather public alerts (IPAWS) | **proposed: Cordon** | They are official warnings, not weather. Elements keeps NWS weather alerts (the NWS API carried none of the non-weather types in November 2026). Needs a decision, as the boundary between Noisefloor and Wake did |
| Joining, coincidence, the final tier across programs | COP | COP already computes direction of concern; Verdict only scores |
| Rules, thresholds, the case file and replay | tic-doctrine | This note; `cases.jsonl` beside it |

## Sources

Checked 25 Nov 2026 between 16:50 and 17:30 UTC with plain scripts (no key, no account, no browser disguise). "Terms
not found" means no statement was found, not that use is barred. Lag is measured: the newest record against the clock.
Quotes marked (fetch) were read through a fetch tool and should be checked against the live page before building.

**US local alerts**

| Source | Access | Terms as stated | Lag | Use | Verdict |
|---|---|---|---|---|---|
| FEMA OpenFEMA `IpawsArchivedAlerts` (fema.gov/api/open/v1/IpawsArchivedAlerts) | OData JSON, no key; raw CAP in `originalMessage`; 4.87 million records | (fetch) attribution required: "This product uses the Federal Emergency Management Agency's OpenFEMA API, but is not endorsed by FEMA"; no explicit redistribution grant, and a line limiting use "solely for statistical research or as a reporting record" to be checked on the live terms page (fema.gov/about/openfema/terms-conditions) | about 24 h (newest 24 Nov 16:37 UTC at 25 Nov 16:54 UTC) | 1-24 Nov 2026: 971 records, about 290 tests or lab traffic (filter by event text and sender name; status is "Actual" on all). Real events: Local Area Emergency 249 (mostly state DOT road closures), Law Enforcement Warning 15, Shelter in Place 13, Civil Emergency Message 10, Evacuation Immediate 7, Hazardous Materials 4, Civil Danger 2. Event names are free text: normalise. Nothing for the Iowa counties 1-24 Nov | **Build** (backfill and next-day layer), once the terms line is checked |
| FEMA IPAWS All-Hazards Information Feed (real time) | registration on the IPAWS User Portal and a Memorandum of Agreement with the IPAWS Office; free | in the agreement, not read | real time | the same alerts, same day | **Decide** (open question 2) |
| NWS API non-weather events (api.weather.gov/alerts) | JSON, no key, needs a User-Agent | (fetch) "in the public domain, unless specifically noted otherwise", any lawful use, no endorsement implied (weather.gov/disclaimer) | minutes | 0 alerts of 12 non-weather types active or since 1 Nov 2026, while IPAWS held hundreds: the API appears to carry only NWS-issued alerts (an inference) | **Don't** for these types; Elements keeps weather |
| USDOT WZDx feed registry (datahub.transportation.gov, 69qe-yiui) | JSON, no key; 45 feeds, 29 without a key (some registry URLs embed tokens: never republish those) | per feed; Iowa DOT's carries none | Iowa DOT under 1 min | work zones only (Iowa: 687, 336 with lanes closed, no full or incident closures) | **Build later**, for context; would not have caught Iowa |
| Iowa 511 (511ia.org) | JavaScript app; no documented API found | terms not found | | | **Don't** until an incident feed and terms are found |
| Alert Iowa, Des Moines County Emergency Management | sign-up text and app alerts only; no feed or archive found | | | | **Don't** (sign-up only); reachable only if the county sends through IPAWS |

**Abroad**

| Source | Access | Terms as stated | Lag | Use | Verdict |
|---|---|---|---|---|---|
| Germany federal warning API (warnung.bund.de/api31: mowas, dwd, katwarn, biwapp, lhp, police) | JSON, no key | terms not found (the legal page is script-rendered) | minutes (MoWaS newest minutes old) | MoWaS held 9 active civil warnings: drinking-water contamination, a WWII bomb, odour, a siren test. Active items only, so history needs our own polling | **Build**, after the terms are found or BBK confirms reuse |
| WMO alert hub source list (severeweather.wmo.int/json/sources.json) | JSON, 156 sources with their CAP feed URLs and an official flag | per source, none found | | Open feeds with civil authorities: Alberta Emergency Alert, India NDMA Sachet (minutes old), Barbados, Syria, Afghanistan, BVI, Turks and Caicos, Anguilla. Most are weather-led | **Build later**, source by source, terms first |
| Japan JMA (jma.go.jp/bosai, data.jma.go.jp developer XML) | JSON and Atom, no key | terms not checked | minutes | earthquakes, volcanoes, tsunamis (natural hazards, Elements' field); J-Alert itself has no public feed found | **Build later**, in Elements |
| Ukraine air-raid alerts (alerts.in.ua; ukrainealarm) | alerts.in.ua needs a token on request; ukrainealarm answers scripts 403 | terms not found | | | **Don't** for now (a token is an account) |
| Israel Home Front Command (oref.org.il) | 403 from outside Israel | terms not found | | | **Don't** |
| Netherlands NL-Alert | no public feed or archive found | | | | **Don't** (unverified; ask the operator before concluding) |

**Consequence layers**

| Layer | Access | Terms as stated | Detail | Verdict |
|---|---|---|---|---|
| GHSL GHS-POP R2023A (European Commission JRC) | open download, no registration | "reuse is authorised, provided the source is acknowledged" (European Commission reuse notice, on the JRC data catalogue record, read 25 Nov 2026) | 100 m and 1 km, 1975-2030 in 5-year steps; sum cells inside a circle or polygon | **Build** (world) |
| US Census 2020 block population | api.census.gov and TIGER files | US federal data (statement not re-read) | block level | **Build** (US) |
| WorldPop | open download | CC BY 4.0 per country licence files; products built on OSM or building footprints are ODbL | 100 m | Alternative only |
| LandScan | licence page refused scripts | not read | 1 km | **Don't**; GHSL covers it |
| DoD MIRTA military installations (DISDI) | ArcGIS feature service; release notes 2 Sep 2025 | not found (US federal work, unverified) | points and boundaries, "publicly-releasable" | **Build** |
| EPA FRS facilities | state CSV downloads | not found (US federal data) | all regulated facilities; RMP facility list usable, never RMP offsite-consequence data | **Build** |
| EIA-860 power plants | annual spreadsheets with coordinates | not read (EIA asks for citation, unverified) | every US plant over 1 MW | **Build** |
| NGA World Port Index | msi.nga.mil (503 at test, as Cordon already sees) | not checked | world ports | **Build later** (retry) |
| HIFLD Open | taken offline 26 Aug 2025; archives at DataLumos and Source Cooperative | | frozen copies | **Don't depend** on it; use the originating agencies |
| OpenStreetMap | ODbL | attribution "© OpenStreetMap contributors"; publishing extracted facts as a dataset makes it ODbL (share-alike) | | Use for checking places only, not as a published layer |

**US national, maritime and official releases**

| Source | Access | Terms as stated | Lag | Use | Verdict |
|---|---|---|---|---|---|
| EPA emergency response sites (response.epa.gov) | per-site RSS (`/svc/rss/site.ashx?site_id=`) with address and latitude/longitude, per-site KML, regional HTML lists (name, city, state, updated, response type, field activity); no key | terms not found | the site feed updated the morning of 25 Nov | **Carried Iowa from 18 Nov** ("IAAAP Lead Azide", Region 7, Emergency, CERCLA removal assessment, field activity yes). Trigger: a new Emergency or Time-Critical site with field activity | **Build** (best early signal found). Pages name EPA staff: keep names out of the feed |
| DVIDS releases (dvidshub.net) | keyless RSS (general news, minutes behind; unit feeds). The API needs an account | API terms: "free for commercial use" (api.dvidshub.net/docs/tos); RSS terms not read | minutes | **Carried Iowa on 24 Nov**: "Army announces controlled detonation of degraded explosive material at Iowa Army Ammunition Plant" and a US Government update. The unit feed returned 433 items, mostly from other units, so its filter is loose | **Build** (RSS only, place matching by text) |
| Federal Register API (federalregister.gov/api/v1) | JSON, no key | terms not found (federal content, unverified) | same day: of 22 safety-zone rules since 1 Oct with an effective date, none was published more than a day late | 33 CFR 165 rules: about 3.6 a week, place in the title; many are fireworks and events, so filter on cause. Nothing on lead azide | **Build** |
| OpenFEMA disaster declarations (v2 DisasterDeclarationsSummaries) | JSON, no key | as OpenFEMA above | about 1 day | county FIPS, incident type, declaration type; none for Iowa in November | **Build**, for aftermath, not detection |
| National Response Center (nrc.uscg.mil) yearly spreadsheet | `CY26.xlsx`, no key | only "INITIAL incident data that has not been validated" | about 1.7 days | about 420 reports a week, mostly small spills; city, state, material | **Build later**, for county clusters |
| Coast Guard notices to mariners (navcen.uscg.gov) | subpages refused scripts (403) after the first page | not found | | | **Build later**; Federal Register rules cover safety zones meanwhile |
| NRC event notification reports (nrc.gov) | refused scripts (403) | not found | | | **Don't** unless an open route is found; never go round the block |
| DHS NTAS (dhs.gov/national-terrorism-advisory-system) | HTML, no feed | not found | | "There are no current advisories" (last bulletin 22 Jun 2025) | **Build later**, a trivial check |
| Background: FAA TFR history in the Internet Archive | CDX index, no key | FAA content is a US Government work; the Archive's own terms apply to bulk access | | 32,627 TFR detail pages, 2006 to 8 Nov 2026 | **Build** the one-time rarity backfill |

### What the vetting changes

- Two of the three official lines that carried Iowa (EPA, DVIDS) are **releases, not alerts**, so the footprint list
  now includes official releases with a place and a time.
- FEMA's public alert archive is the only open source of local US alerts, and it is a day behind. Same-day local alerts
  need FEMA's agreement-based feed (open question 2).
- The National Weather Service API does not carry the local non-weather alerts, so nothing is gained by widening
  Elements' NWS lane.

## Outside the United States

The method is the same everywhere: cause, rarity and dynamics, events, coincidence, consequence, tier. What changes
abroad is where the footprints come from, what sets the cause, how rarity is counted and what counts as independent.
Measured and vetted 25 Nov 2026.

### Air: worldwide NOTAMs, already held

Cordon keeps every NOTAM it pulls from the FAA's NMS-API in a permanent archive (since 18 Nov 2026). The day file for
19 Nov 2026 holds **49,004 international NOTAMs** under 413 distinct flight-information-region or location codes. Each
carries an ICAO Q-code whose second and third letters name the subject, which sets the cause the way a US regulation
number does. Counts on that day, restriction and warning subjects only:

| Q-code subject | Meaning (ICAO) | Count | Cause group |
|---|---|---|---|
| RT | temporary restricted area | 3,375 | from the words (security, VIP, hazard, military) |
| WU | unmanned aircraft | 3,257 | military and test, or scheduled, from the words |
| RD | danger area active | 1,176 | military and test |
| RR | restricted area | 967 | military and test, or from the words |
| RA | airspace reservation | 870 | military and test |
| WE | exercises | 413 | military and test |
| WM | missile, gun or rocket firing | 335 | military and test |
| WH | blasting | 129 | hazard to people |
| RP | prohibited area | 110 | security, from the words |
| WD | demolition of explosives | 36 | hazard to people, unless the words say fireworks |
| WR | radioactive materials or toxic chemicals | 2 | hazard to people |

Examples from that day: a 5 NM prohibited area over the state government palace in Toluca, Mexico (RP); 81 mm mortar
firing on Japan's Higashi-Fuji range (WM); an airspace closure polygon in the Yekaterinburg region (RT). Words still
matter: the WD example drawn was a fireworks display in Sabah, Malaysia.

Rarity abroad is counted per Q-code subject and flight-information region, the region taking the place of the US
state. The FAA's terms say NMS is not the authoritative source for NOTAMs issued outside the United States, so coverage
may be partial and every item says so (Cordon's `SOURCE_NOTE` already does).

### Sea

NGA's NAVAREA and HYDROPAC warnings (Cordon, have) are the worldwide layer. National coastal warnings were mostly closed
to scripts on 25 Nov 2026: China's Maritime Safety Administration (where PLA live-fire closures are published)
answered "ACCESS DENIED", Russia's navigation-warning hosts did not connect, Japan's coast guard is barred by its
robots file (an existing Cordon decision), Taiwan's port bureau answered "ACCESS DENIED", and no Korean warning feed
was found. Military firing and exercise areas usually also appear as NOTAMs (WM, WE, RD), so the air layer covers part
of the gap; that is expected, not measured.

### Ground: civil-protection alerts

CAP's own `category` (Geo, Met, Safety, Security, Rescue, Fire, Health, Env, Transport, Infra, CBRNE, Other) is an
international, language-neutral cause signal; event names are in the local language and are used second.

| Source | Access | Terms as stated | Lag | Verdict |
|---|---|---|---|---|
| Germany federal warning API (warnung.bund.de/api31) | JSON, no key | not found; ask the federal civil protection office (BBK) | minutes | **Build**, once terms are confirmed |
| Victoria, Australia: VicEmergency events GeoJSON | no key; point and polygon, CAP category, agency | "Creative Common Attribution 3.0 Australia", with a link to the notice and the last update time (search snippet; notice page refused scripts) | under 20 min | **Build**, after the licence page is read |
| New South Wales Rural Fire Service major incidents | JSON, no key; geometry, alert level | CC BY 4.0 by the RFS's own statement (search result; page behind a challenge) | hours | **Build** |
| India NDMA Sachet CAP | RSS, no key | per source, not found | minutes | **Build**, terms first |
| WMO register of alerting authorities (156 CAP sources) | per source | per source | per source | **Build later**, source by source |
| Canada NAAD archive (Pelmorex) | public archive page; live TCP stream for registered distributors | no reuse licence found | minutes (archive's own claim) | **Build later**, after asking Pelmorex |
| Taiwan NCDR CAP alerts | needs a member login; 3 s rate limit | not found | | **Build later** (an account) |
| UK Emergency Alerts past alerts (gov.uk/alerts/past-alerts) | HTML, a few a year | Open Government Licence | | **Build later** (tiny) |
| Israel Home Front Command | refused outside Israel | not found | | **Don't** |
| Ukraine air-raid alerts | token on request | not found | | **Don't** for now (an account) |
| France FR-Alert, Netherlands NL-Alert, Korea | no feed or archive found | | | **Don't** for now |

### National guidance

Cordon reads five governments' advice (US State Department, UK FCDO, Canada, New Zealand, CDC). Add:

- **Japan's foreign ministry overseas-safety open data** (ezairyu.mofa.go.jp/opendata): XML, no key, refreshed every
  5 minutes, about 20 minutes behind when checked, with country and area codes. Its "spot" notices are local
  (demonstrations, attacks, unrest in a named city). Free for any use with a source line, per a summary of its terms
  page; read the page in full before building. **Build.**
- **Netherlands travel advice API** (opendata.nederlandwereldwijd.nl): XML, no key, colour code per country, changes
  rarely. CC0 is stated on the government open-data listing, not on the API itself. **Build**, after confirming.

Each government is its own independence group, so advisory changes by several governments in the same week count as
several lines.

### Media

Local media is the coincidence line abroad: Context's and Watchfloor's stories, GDELT's translated headline counts for
a place against its own 30-day level (as Blackout already counts), and the local press found by place name. ReliefWeb's
API needs an approved app name, which the suite already holds (Relief uses it), and its terms allow "personal,
non-commercial use, without any right to resell or redistribute", so it gives links and headlines only.

### Consequence

GHSL population works worldwide (European Commission reuse notice: "reuse is authorised, provided the source is
acknowledged"). Listed sites are harder: the US lists (MIRTA, EPA, EIA) have no worldwide equivalent found yet, HIFLD
went offline in 2025, and OpenStreetMap is ODbL, so it is used to check places, not published as a layer. NGA's World
Port Index covers ports, and Wake's chokepoints cover sea lanes.

### What changes in the rules

- **Rarity is counted per source and region, never per country alone.** Coverage differs widely; a country with no
  open feed is not quiet, and items say which sources were read.
- **Independence:** where the press is state-controlled, state media and the government's own notices are one line.
- **In closed states the closure is the signal:** a sudden prohibited area, an unusually large or long danger area, a
  closure along a border or coast, counted against the same region's own NOTAM history.
- **Codes before words:** ICAO Q-codes, NAVAREA categories and CAP categories first; word lists per language later,
  starting with the languages of the regions the suite watches most.
- **Blocked sources stay unread.** No source is read round a block, and a restriction is quoted from the source's own
  terms before a source is dropped.

### Order

1. Cause, rarity and dynamics on international NOTAMs, from the archive Cordon already keeps (no new source).
2. Japan's and the Netherlands' travel advice in Cordon.
3. Civil-protection alerts: Germany, Victoria, New South Wales, India, then the WMO list.
4. Media matching by place name in COP.

Decisions that need the owner: an account for Taiwan's NCDR; whether to ask for an alerts.in.ua token; notes asking
Pelmorex and BBK about terms.

## Open questions

1. Should non-weather public alerts from FEMA's IPAWS archive (evacuation, shelter in place, civil danger, hazardous
   materials) live in Cordon (recommended: they are official warnings) or Elements (weather and natural hazards)?
2. The archive is a day behind. Same-day alerts need FEMA's IPAWS All-Hazards Information Feed, which is free but needs
   a registration and a Memorandum of Agreement with the IPAWS Office. Decided 25 Nov 2026: hold. The agreement text
   is not published; revisit once it is seen, and after checking whether any IPAWS alert went out for the Iowa case.
3. Should press attention count as a line? Recommended yes, as one line at most, because the press often knows about a
   local event before any feed does. Iowa reaches significant without it (a rare hazard-to-people cause), but many
   events abroad will have no second official line.
4. The thresholds in the tier table (1,000 people, 365 days, 10 km and 72 hours for joining) are first guesses to be
   set against the case file. Keep them as defaults until the replay?

## Versions

- tic-significance-0.1 (25 Nov 2026): this draft.
- tic-significance-0.1, same day: section on the rest of the world (international NOTAMs, sea, civil-protection
  alerts, national guidance, media, consequence).

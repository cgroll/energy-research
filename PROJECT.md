# Project State

Tracks the current state, roadmap, and lessons learned for this project.
See [AGENTS.md](AGENTS.md) for structure/tooling conventions.

## Current State

Freshly initialized from the project-book-template (package `erx`) as the
exploratory-research member of `energy-platform` (see the platform's root
`AGENTS.md`). The template's example download/analyse pair is still in
place as a working reference (untouched).

**Research topic:** how well PECD wind/solar capacity factors match
real-world generation for individual power plants.

**2026-09-28 — Kelmarsh (UK) sub-topic: validated and promoted.** Rather
than wait on the ENTSO-E token (see Next Steps below, still pending), a
parallel UK wind farm dataset was tried first: Kelmarsh (Zenodo record
5841834, Cubico Sustainable Investments, CC-BY-4.0) publishes real
10-minute grid-meter export directly, no ENTSO-E ≥100 MW reporting
threshold involved. Built here as `pipeline/01_download_kelmarsh.py` +
`02_compare_kelmarsh_pecd.py`, validated (PECD zone UK03 vs. Kelmarsh's
grid-meter MW: monthly-mean r=0.81 raw, r=0.96 after correcting for
measured downtime — see Lessons Learned), then **promoted** into the
stable platform now that it looks sound:
- `energy-data-hub`: new `kelmarsh` asset group (`edh/kelmarsh.py`,
  `edh_dagster/assets/kelmarsh.py`) — `kelmarsh_wt_static` +
  `kelmarsh_grid_meter`, `full_refresh` load pattern.
- `energy-insights`: new page `pages/12_kelmarsh_vs_pecd.py`
  (`page_kelmarsh_vs_pecd` asset), rebuilt against the hub's own outputs
  rather than re-reading this repo's copy.

This repo's own `data/downloads/kelmarsh_*` files are now superseded by
the hub's copy — kept here only as the original prototype/scratch record,
not read by anything downstream anymore.

## Next Steps

1. Optional stretch goal for the promoted Kelmarsh page: break the
   farm-level comparison down to per-turbine SCADA (not downloaded here —
   the ~1.5 GB `Kelmarsh_SCADA_*.zip` files were deliberately skipped) to
   see whether October 2018's apparent outage affected one turbine or the
   whole farm.
2. A PV-equivalent of the Kelmarsh check (a single plant with public
   metered generation, PECD solar vs. real MW) hasn't been found/tried
   yet — natural next sub-topic, same pattern as Kelmarsh.
3. The original ENTSO-E/German-plant angle is still open, now lower
   priority since Kelmarsh already delivers a validated plant-level
   result: Register for ENTSO-E Transparency Platform REST API access
   (account exists; API token doesn't yet) — email
   `transparency@entsoe.eu` with subject "RESTful API access" and the
   registered address in the body; ENTSO-E typically replies within 3
   working days. Token is then generated under "My Account Settings" on
   the platform.
4. Once the token is available: query the "Production and Generation
   Units" master data for bidding zone `DE_LU`, filtered by `psr_type`
   Wind Onshore (B19) / Wind Offshore (B18) / Solar (B16), to see
   empirically which — if any — individual German wind/PV plants have a
   registered generation unit (see Lessons Learned below for why this
   isn't a given).
5. Pick one wind and one PV candidate from that list (or confirm none
   qualify and fall back to an operator-published dataset — see below).
6. Pull `Actual Generation per Generation Unit [16.1.A]` for the chosen
   unit(s), inspect the shape of the data (resolution, EIC identifiers,
   confirmed vs. estimated flag), and write it up as a first pipeline
   script + notebook here.
7. Compare against the hub's PECD capacity-factor series
   (`hub_file("pecd", ...)`) for the matching region/technology.
8. Only once this comparison looks sound: promote into `energy-data-hub`
   as a Dagster asset (new domain, e.g. `entsoe.py`) and into
   `energy-insights` as a page — same pattern as Kelmarsh above.

## Lessons Learned

### 2026-09-25 — Public per-plant generation data: what's actually available

- The relevant public source for real (measured) generation at the
  individual-plant level is the **ENTSO-E Transparency Platform**, view
  "Actual Generation per Generation Unit [16.1.A]", mandated by EU
  Regulation 543/2013. It's a genuine measured value, not an estimate —
  distinct from SMARD (only aggregated by production type / TSO area, never
  per plant) and from MaStR (unit master data — capacity, location,
  commissioning date — but no generation time series).
- **Hard cutoff: only generation units ≥100 MW net capacity are required to
  report.** This is a regulatory floor, not a "top N plants" curation — any
  qualifying unit above it reports, nothing below it does.
- **Likely gap for German renewables:** multiple independent sources (Open
  Power System Data's data-source notes, the EEX Transparency wind/solar
  feed-in view) indicate Germany reports wind/solar generation to
  ENTSO-E/EEX only in *aggregate* (quarter-hourly, country-level, split
  onshore/offshore/solar) rather than per named plant — because most German
  wind/PV capacity is thousands of small EEG-driven installations, not
  discrete ≥100 MW units the way conventional (coal/gas/nuclear/pumped
  storage) blocks are. This is not yet empirically confirmed (needs the API
  token + an actual query of the DE_LU unit master list, per Next Steps) —
  treat the user's original assumption ("top 100/1000 plants have this")
  as unverified for wind/PV specifically until that check is done. It likely
  holds for conventional plants.
  Candidate large-enough German wind/PV plants to check first if any
  individual unit *does* show up: offshore wind farms (each a single grid
  connection, e.g. Veja Mate 402 MW, Amrumbank West 288 MW, Gode Wind 1/2)
  are the most plausible wind candidates; utility-scale PV parks like
  Witznitz (605 MWp) or Weesow-Willmersdorf (187 MWp) are the most plausible
  PV candidates — but none of these are confirmed present in ENTSO-E's
  per-unit view yet.
- Practical note: the ENTSO-E **web UI** (transparency.entsoe.eu, logged in)
  allows manual CSV/XLS export without an API token — only the REST API
  needs one. Useful for a first manual look while the token request is
  pending.
- `entsoe-py` (PyPI) is the standard Python client; for Germany use bidding
  zone code `DE_LU` (the old `DE_AT_LU` zone split in 2018).

### 2026-09-28 — Kelmarsh (UK) vs. PECD: validated, then promoted

- Kelmarsh (Zenodo record 5841834) publishes a wind farm's real generation
  at two levels: per-turbine SCADA (not downloaded — the ~1.5 GB
  `Kelmarsh_SCADA_*.zip` files) and the site's own fiscal/grid meter export
  (`Kelmarsh_Grid_3088.zip`, ~1.5 MB) — the true metered value at the grid
  connection point, used here as ground truth.
- Kelmarsh's coordinates (52.40°N, 0.94°W, Northamptonshire) map to PECD
  onshore wind zone **UK03** via nearest-grid-cell lookup against the
  hub's `peon_region_mask.nc` (~70% UK03 / ~30% UK01 at that cell — close
  enough to a clean UK03 assignment).
- Comparing PECD's UK03 capacity factor x Kelmarsh's 12.3 MW installed
  capacity against the real grid-meter MW (not capacity factors directly —
  translating to MW keeps both series on Kelmarsh's own physical scale):
  monthly-mean correlation **0.81**, mean bias **-0.09 MW** over the full
  2016-01 to 2021-07 window.
- The two biggest monthly mismatches were explainable, not PECD errors:
  Feb/Mar 2016 is the pre-commissioning period (turbines' Commercial
  Operations Date is 2016-04-15, confirmed by `Energy meter based
  availability` averaging only 17-28% those months vs. a typical month's
  ~94%); October 2018 (availability 67%, third-lowest month in the whole
  record) looks like a real outage/maintenance event.
- **`Energy meter based availability` is a binary (0/1) per-10-minute
  flag at the whole-farm grid-meter level, not a per-turbine fractional
  signal** — confirmed tautological with `Export > 0` in this file
  (availability==0 iff export==0, exactly, no exceptions). It cannot
  distinguish "one turbine down" from "all six down", or "down" from
  "no wind" at the 10-minute level — only its hourly *average* becomes a
  meaningful downtime signal, for hours where PECD implies output should
  have been nonzero.
- Scaling PECD's implied MW by that hourly availability fraction lifts
  the monthly-mean correlation to **0.96** and nearly eliminates both
  outlier months — strong evidence the residual gap is mostly Kelmarsh's
  own downtime, not a PECD weather-modeling error. Side effect: mean bias
  gets slightly *worse* (-0.09 → -0.28 MW), because average hourly
  availability across the whole record is ~90%, not 100%, so the
  correction nudges every month down a little, not just the two problem
  months.
- Promoted into the stable platform the same day (see Current State) —
  `energy-data-hub`'s `kelmarsh` asset group and `energy-insights`'
  `page_kelmarsh_vs_pecd`, both rebuilt against hub-native data rather
  than reusing this repo's downloaded copies.

# Project State

Tracks the current state, roadmap, and lessons learned for this project.
See [AGENTS.md](AGENTS.md) for structure/tooling conventions.

## Current State

Freshly initialized from the project-book-template (package `erx`) as the
exploratory-research member of `energy-platform` (see the platform's root
`AGENTS.md`). No real pipeline yet — the template's example
download/analyse pair is still in place as a working reference.

**Current research topic:** how well PECD wind/solar capacity factors match
real-world generation for individual German power plants. Plan: find one
wind and one PV plant with publicly available actual-generation data,
compare their measured output against PECD's capacity factors for the
corresponding region/technology.

## Next Steps

1. Register for ENTSO-E Transparency Platform REST API access (account
   exists; API token doesn't yet) — email `transparency@entsoe.eu` with
   subject "RESTful API access" and the registered address in the body;
   ENTSO-E typically replies within 3 working days. Token is then generated
   under "My Account Settings" on the platform.
2. Once the token is available: query the "Production and Generation Units"
   master data for bidding zone `DE_LU`, filtered by `psr_type` Wind
   Onshore (B19) / Wind Offshore (B18) / Solar (B16), to see empirically
   which — if any — individual German wind/PV plants have a registered
   generation unit (see Lessons Learned below for why this isn't a given).
3. Pick one wind and one PV candidate from that list (or confirm none
   qualify and fall back to an operator-published dataset — see below).
4. Pull `Actual Generation per Generation Unit [16.1.A]` for the chosen
   unit(s), inspect the shape of the data (resolution, EIC identifiers,
   confirmed vs. estimated flag), and write it up as a first pipeline
   script + notebook here.
5. Compare against the hub's PECD capacity-factor series
   (`hub_file("pecd", ...)`) for the matching region/technology.
6. Only once this comparison looks sound: promote into `energy-data-hub` as
   a Dagster asset (new domain, e.g. `entsoe.py`) and into `energy-insights`
   as a page.

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

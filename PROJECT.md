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

This repo's own `data/downloads/kelmarsh_grid_*` / `kelmarsh_wt_static.csv`
files are now superseded by the hub's copy — kept here only as the
original prototype/scratch record, not read by anything downstream
anymore.

**2026-09-29 — Kelmarsh sub-topic, round 2: does real wind speed beat
PECD's weather input?** The hourly (not monthly) comparison in
`02_compare_kelmarsh_pecd.py` stayed visibly noisy even after the
availability correction (r=0.86 hourly vs. r=0.96 monthly). Hypothesis:
PECD's single large-area reanalysis grid cell is the limiting factor, not
its wind-to-power conversion approach. Tested by pulling in the per-
turbine SCADA data explicitly skipped before (`03_download_kelmarsh_scada.py`,
all 6 years/turbines, ~1.5 GB of raw zips, kept only wind speed + power +
availability afterward) and converting each turbine's own real nacelle
wind speed to power via `windpowerlib`'s real MM92/2050 power curve
(`04_compare_windspeed_reconstruction.py`). Result, full 2016-2021 window,
hourly: correlation **0.99** and NMAE **7.7%** (availability-adjusted),
vs. PECD's 0.86 / 35.8% — see Lessons Learned. Confirms the hypothesis
clearly. Not yet promoted into the hub/book — `windpowerlib` is a new
dependency and the SCADA download is a much heavier pull (~1.5 GB vs.
~1.5 MB for the grid meter), so this stays here pending a decision on
whether it's worth that cost for the stable platform.

**2026-09-30 — New sub-topic: long-run PECD capacity factors vs a constant
demand baseline.** A different angle from the Kelmarsh/ENTSO-E plant-level
validation work above, prompted by comparing `energy-insights`' `09` page
(`09_re_buildout_battery_residual_load`, ~7-year real-SMARD-demand window)
against `world-of-energy`'s `41_demand_coverage` (47-year PECD-ERA5 window,
reconstructed demand) — the two showed similar demand/capacity magnitudes
but a ~10-15pp gap in average RE coverage, plausibly from PECD's raw
capacity-factor level rather than the demand side. Built here as
`pipeline/05_pecd_de_capacity_factors_vs_constant_demand.py`
(`book/notebooks/05_...ipynb`), using the hub's `pecd_country_capacity_factors_simple_de`
asset (DE-only, technology-mix "simple" aggregation, **1980-2025**, the same
non-MaStR-weighted product `09` uses) against a **constant** demand
reference (mean of 2025's 365 daily peak SMARD loads, 61.5 GW) instead of
an hourly demand series — isolating the supply side from any particular
demand time series entirely.
- Long-run (1980-2025) mean capacity factors: solar 10.7% (all hours) /
  20.9% (Berlin daylight hours only, via `astral`, sunrise/sunset computed
  directly in UTC to match PECD's UTC timestamps), wind onshore 23.6%,
  wind offshore 43.0%.
- These land within ~1pp of the same technology's mean capacity factor over
  `09`'s much shorter 2018-2025 window (solar 10.9%, onshore 23.1%,
  offshore 42.8%) — the 46-year record doesn't change the picture
  qualitatively, which also means the `09` vs `41` coverage gap is **not**
  explained by `09`'s shorter window sampling an unrepresentative slice of
  weather history. The likely explanation still points to `41` using a
  higher effective capacity-factor level than this "simple" DE product
  (not yet directly confirmed — would need to open `41`'s own capacity
  factor source line by line).
- Not a validation-against-real-generation result (no plant/meter ground
  truth involved here, unlike Kelmarsh) — purely a supply-side
  characterization + a first constant-demand-baseline visualization.
  `astral` added as a new dependency for this.

**Same day, same script — extended to the full `09` replication.** Ported
`09`'s entire buildout-multiplier + battery-size sweep (direct use /
curtailed / residual decomposition, battery decomposition at 2x, delivered-
vs-multiplier, RE-share + curtailment two-panel, peak residual load, worst
multi-day drawdown, residual duration curve, four-scenario summary table)
into the same script, run against the full 1980-2025 weather record with
the constant 61.5 GW demand reference substituted for `09`'s real hourly
SMARD series throughout. Nine chart PNGs total now (`05_*.png`).
- Headline numbers land in the same shape as `09` despite the very
  different demand treatment: e.g. today's fleet (1x) covers ~52% of the
  constant demand directly (`09`: 56% of real demand); a 24h battery at 2x
  buildout reaches ~91% average coverage (`09`: ~94%); only the 168h/10.3
  TWh battery ever fully closes the peak-residual and worst-drawdown tails,
  and only from ~4x buildout on (`09`: similar, ~4x-5x). Battery capacities
  come out ~11% larger than `09`'s (168h now 10.33 TWh vs. 9.3 TWh) simply
  because the constant reference (61.5 GW, a peak-load mean) sits above
  `09`'s real average-hourly-demand figure (55.4 GW) by construction.
- **Real bug caught and fixed:** the worst-drawdown metric
  (`worst_drawdown_days`, a `np.cumsum` over ~400k hourly terms) hit
  float64 cancellation noise once a battery fully closed the gap — printed
  fine when rounded for display, but on the log-scale chart a scenario's
  "true" result of 0 came out as ~1e-18, which log-scale renders as a
  nonsensical vertical plunge to the bottom of the axis, wrecking
  readability of every other series. Fixed by flooring any drawdown below
  10 MWh (utterly negligible at this system's GW scale, but far above the
  float-noise floor) to an exact zero, then masking exact zeros to `NaN`
  for that one plot so the line simply stops where the gap is closed,
  documented in the figure caption. Worth remembering generally: a
  `cumsum`-based metric over hundreds of thousands of terms needs an
  explicit near-zero floor before it's plotted on a log scale.
- Kept `09`'s own "chronic deficit" caveat (1.0x-1.5x buildout: the
  "episode" is effectively the whole record, not a discrete weather event)
  — even more pronounced here (thousands of demand-days vs. single digits
  from 2x on) since the record is 46 years instead of 7.

**2026-09-30 — New sub-topic: country-level vs. within-country capacity
factor spread.** Checked the intuitive hypothesis "solar in Italy beats
solar in Denmark on average" directly against the hub's
`pecd_country_capacity_factors_simple` (confirmed: 14.4% vs. 10.5%, Italy
37% higher, 1980-2025), then asked what's underneath a single
country-level number. Built here as
`pipeline/06_pecd_country_and_regional_capacity_factors.py`
(`book/notebooks/06_...ipynb`).
- **Resolution check first, before computing anything:** true Eurostat
  NUTS2 exists in this hub only for Germany's solar
  (`pecd_solar_capacity_factors`, 38 regions) — no other country was ever
  requested at that granularity for solar, and PECD's wind product has no
  NUTS2/country-level option at all (confirmed against the live CDS API,
  see `energy-data-hub/docs/pecd_data_availability.md`), only its own
  coarser zone partition (`peon`/`peof`, already downloaded full-Europe).
  So a genuine NUTS2, all-of-Europe, both-technology comparison isn't
  possible with what's on disk today.
- **Real finding, not just a caveat:** solar's cross-country spread
  (~9-12 pts, Finland to Cyprus/Egypt depending on domain) dwarfs
  Germany's own internal NUTS2 spread (2.0 pts, Hamburg to Freiburg) — a
  single country-level solar number is a safe summary. Wind onshore is
  the opposite: several countries' own PECD zones (Spain, France, and
  outside the EU, Turkey at 31 pts across 13 zones) span a wider range
  internally than separates many country-mean *pairs* — a single national
  wind capacity factor hides much more than the equivalent solar number.
- Also surfaced a specific, correctable gap while writing this up: the
  hub's DE-only solar NUTS2 pull (`process_solar_capacity_factors`)
  requests `spatial_resolution=nuts_2` for the *full* PECD domain (no
  country filter in the CDS request itself), then keeps only Germany's
  columns and deletes the raw zip — every other country's NUTS2 columns
  already passed through this pipeline once and were discarded, not
  something PECD refuses to provide. Extending to NUTS2-everywhere would
  mean re-running that same request without the DE filter, not a new kind
  of download.
- Deliberately overlaps `energy-insights`' `08_pecd_country_comparison`
  (country-level bars/choropleths, same hub asset) only far enough to
  anchor the Italy/Denmark check in the full European context; everything
  from the resolution question onward is new content that page doesn't
  cover.

**Same day, follow-ups.** Three small additions on top of the two
2026-09-30 sub-topics above, each requested separately after the initial
build:
- `06_pecd_country_and_regional_capacity_factors` gained a choropleth map
  (solar/onshore/offshore-country-mean) alongside its existing bar chart,
  Italy/Denmark called out on the solar map — the bar chart ranks countries
  precisely, the map makes the geographic pattern (south-north solar,
  Atlantic/North Sea wind) visible at a glance. Pulled in `cartopy` +
  `shapely` as new dependencies (same Natural Earth country-geometry
  approach as `energy-insights`' `08`).
- All four real analysis notebooks (`02_compare_kelmarsh_pecd`,
  `04_compare_windspeed_reconstruction`, `05_...constant_demand`,
  `06_...capacity_factors`) were built under `book/notebooks/` from the
  start but never added to `book/myst.yml`'s `toc` — the published book
  only ever rendered the original template example. Fixed; verified with
  `myst build --check-links`.
- `05_pecd_de_capacity_factors_vs_constant_demand` gained one more bar
  chart, purely for orders-of-magnitude intuition: average consumption
  (61.5 GW) next to a 1h battery (61.5 GWh) and a 4h battery (246 GWh) next
  to today's total installed RE capacity (192 GW, stacked by technology).
  No new simulation — GW and GWh deliberately share one axis here, since a
  battery sized at "N hours of average demand" has a GWh figure that's by
  construction N times the GW demand figure, so the bars are scale-comparable
  despite the unit difference. Headline: today's fleet is already ~3x
  demand in nameplate GW, but a 4h battery is still only ~17% of one day's
  demand (246 GWh vs. ~1,475 GWh/day) — context for why the existing sweep
  needs 24h/168h batteries before storage alone meaningfully closes the gap.
- The notebook's section order was reshuffled into a clearer narrative
  (demand -> capacity/battery sizes -> capacity factors -> buildout alone
  -> 2x battery decomposition -> coverage/curtailment -> the remaining
  sweeps -> peak residual load + duration curve, kept together at the end
  -> summary -> takeaways) — pure reordering, numbers unchanged.
- Added a heatmap to the coverage/curtailment chapter: average residual
  load (GW) over a finer buildout x battery-duration grid than the
  four-scenario chart it sits next to, restricted to the near-term-relevant
  range (1x-5x buildout, 0h-4h battery, 0.5x / 1h steps). Confirms
  numerically that within this short-duration range, buildout dominates —
  e.g. at 0h battery, going 1x->5x drops residual ~25 GW, while at any
  fixed multiplier, going 0h->4h battery only shaves off ~1-3 GW — battery
  duration would need to go well beyond 4h (as the existing 24h/168h
  scenarios do) before it rivals buildout's effect.
- The heatmap's colormap was switched to a red-yellow-green "traffic light"
  ramp (`RdYlGn_r` -- reversed so red = high/bad residual, green = low/good),
  a deliberate one-off deviation from the platform's usual single-hue
  sequential magnitude encoding. Needed a luminance-based per-cell text
  color (rather than a simple high/low split) since a 3-hue ramp's light
  and dark ends both need white text while its yellow middle needs dark
  text.
- **Trimmed and promoted into `energy-insights` as the new `09` page,
  2026-09-30.** Removed everything from "Does the worst multi-day shortfall
  ever go away?" through the end of this notebook (that section, the
  near-ideal-case look, peak residual load, the residual-load duration
  curve, the four-scenario summary, and takeaways) -- the page now ends
  after "does storage's marginal value hold up across the whole buildout
  range?". The trimmed content then fully replaced `energy-insights`'
  `pages/09_re_buildout_battery_residual_load.py` (previously the
  real-hourly-SMARD-demand / ~7-year version) -- ported with its
  `{figure}`/`savefig` blocks stripped out to match that repo's plain
  `plt.show()` + prose convention, interpretive paragraphs rewritten with
  numbers pulled from an actual run rather than guessed, and its Dagster
  asset's `deps`/description updated (`pecd_country_capacity_factors_simple_de`
  instead of the all-country asset). The real-demand/~7-year version and the
  peak-residual/worst-drawdown analysis dropped in the trim now live only
  here in `energy-research` (this file, pre-trim, in git history) -- not
  duplicated anywhere else.

**2026-09-30 — New sub-topic: first look at the hub's new balancing-market
data.** `energy-data-hub` just gained reBAP (netztransparenz.de, 15-min,
since 2014) and FCR/aFRR capacity prices (regelleistung.net, daily x 4h
block, since 2021/2018-10) as `data_derived_watermark` assets. Built
`pipeline/07_balancing_market_prices.py` (`book/notebooks/07_...ipynb`):
for each series, a time-series plot, a boxplot by 4-hour time-of-day
block, average-by-calendar-month (seasonality), average-by-year (trend),
weekday vs. weekend, and a per-year data-completeness check.
- **Timezone care carried over from the hub's own README:** FCR/aFRR's
  4-hour block columns are German local time (CET/CEST), not UTC, but
  reBAP's own timestamps are naive UTC (hub convention) -- converted
  reBAP to `Europe/Berlin` before every block/weekday/month/year grouping
  here so the three series' time-of-day views are genuinely comparable,
  not just superficially similar.
- **Completeness check needed a two-sided fix, not just one:** a first
  version only capped the *current* (incomplete) year at each series' own
  max timestamp -- correct for avoiding a fake "gap" in 2026, but it also
  showed aFRR's 2018 as ~75% missing, since aFRR genuinely only starts
  2018-10-01 and the check was still comparing against a full
  Jan-1-to-Dec-31 expectation. Fixed by capping the *first* year at the
  series' own min timestamp too -- 2018 now correctly shows ~0% missing
  (no real gap within the period aFRR actually covers). All three series
  land at >99.9% complete in every full year; FCR's one known gap
  (2021-10-03, German Unity Day) is too small to move the yearly number
  much.

**2026-09-30 — New sub-topic: does reBAP actually track the real system
imbalance?** Prompted by a question about what reBAP's relationship to
the day-ahead price actually means: reBAP should sit above day-ahead when
the system is short and below it when long, so the spread
`reBAP - day-ahead` is a plausible *indirect* proxy for imbalance
direction. netztransparenz.de separately publishes the direct, ground-
truth figure for this -- the **NRV-Saldo** (Netzregelverbund-Saldo),
Germany's aggregate imbalance in MW, positive when under-supplied and
negative when over-supplied.
- **`pipeline/08_download_nrv_saldo.py`** (experimental, not yet promoted
  to `energy-data-hub`): same `CsvDownloadHandler.ashx` LotesCharts
  mechanism as `edh/rebap.py`, discovered the same way (reading the
  chart's own inline JSON config, this time embedded directly in the page
  HTML rather than needing `DownloadHandler.js`). `ProduktId=6` /
  `WebApiRoute=NrvSaldo/nrvsaldo/qualitaetsgesichert` is the
  quality-assured series, `TsoIds=[0]` gives the single national
  aggregate. Same 2014-01-01 start and ~2-week quality-assurance lag as
  reBAP (same underlying settlement process).
- **Real, multi-month gaps found -- not a download bug.** Unlike reBAP
  (near-perfectly complete), NRV-Saldo has substantial missing stretches:
  2014/2015 (~8.5% each), 2016 (a single unbroken gap 02-11 to 10-31,
  ~72% of the year), 2018 (three gaps, ~33% total), 2022 (a single gap
  02-28 to 05-31, ~25%). 2017, 2019-2021, and 2023-2026 are each ≥99.99%
  complete. `09_nrv_saldo_vs_rebap.py` restricts to those clean years.
- **The proxy story holds up against the real thing.** Joined reBAP,
  `smard_price_de_lu` (day-ahead, forward-filled hourly->15min), and
  NRV-Saldo on their shared 15-min grid, clean years only (~235k
  quarter-hours): the spread has the same sign as NRV-Saldo 93.7% of the
  time, and mean spread rises monotonically across NRV-Saldo quintiles
  (-70 EUR/MWh most-over-supplied -> +85 EUR/MWh most-under-supplied,
  no reversals) -- despite only a moderate linear correlation (Pearson r
  ≈ 0.35), since reBAP moves in sharp merit-order jumps rather than
  scaling smoothly with imbalance volume. Conclusion: the price spread is
  a solid *directional* signal, not a precise stand-in for the real MW
  figure -- NRV-Saldo is still the more honest variable when direction
  specifically matters, gaps notwithstanding.

**Same day, follow-ups from exploratory discussion (no new downloads).**
Three things investigated conversationally that turned up real,
non-obvious findings, one of which became a new page:
- **`pipeline/10_balancing_timeline.py`** -- a pure reference diagram (no
  data), mapping when each piece (day-ahead, Fahrplan, redispatch,
  intraday trading, IP-Index, FCR/aFRR/mFRR, RZ-/NRV-Saldo, reBAP
  publication tiers, billing) actually happens relative to one delivered
  quarter-hour. Corrects two easy-to-assume-wrong orderings: redispatch is
  not a single D-1-only planning step (it keeps updating in parallel with
  intraday trading, up to real-time ad-hoc calls per TenneT's own
  Redispatch 2.0 FAQ), and the IP-Index is computed *before* the
  NRV-Saldo/reBAP for the same quarter-hour can even exist (IP-Index needs
  only the last trades before T; NRV-Saldo needs real metered values
  *after* T, then ~2 weeks to go "qualitätsgesichert").
- **RZ-Saldo (the four per-TSO-zone balances NRV-Saldo is summed from) is
  also downloadable** -- same LotesCharts mechanism, `ProduktId=34` /
  `WebApiRoute=NrvSaldo/rzsaldo/qualitaetsgesichert` instead of NRV-Saldo's
  `6`/`nrvsaldo`, starts 2014-04-30 (later than NRV-Saldo's 2014-01-01),
  same gap-year profile. A one-week spot check (2024-01-08 to -14, not
  yet fully downloaded) already shows a striking structural pattern:
  TenneT's zone was negative (over-supplied) 93% of the quarter-hours that
  week, while the other three zones were positive (under-supplied) most of
  the time -- plausibly the north/south wind-vs-load split, not yet
  investigated further. Sum of the four zones matches the already-
  downloaded NRV-Saldo to float-rounding precision.
- **SMARD's "realisierte Erzeugung" for wind/solar is not a clean "what
  was physically fed in" number.** Directly-telemetered (larger) plants:
  real actual output. The many small, non-telemetered plants: a regulated
  "Online-Hochrechnung" that, since January 2015, is *legally required to
  exclude* grid-driven curtailment (Einspeisemanagement/Redispatch) --
  netztransparenz.de's own wording: "als theoretisch höchstmögliche
  Erzeugungsleistung... zu interpretieren." Inherited from EEG
  Einspeisemanagement-compensation methodology (operators are paid for
  what they *would* have produced), not designed for market-transparency
  purposes, but SMARD's public figures carry it through regardless --
  likely a slight over-statement of true net feed-in whenever curtailment
  is material. Also confirmed: SMARD's generation forecast (day-ahead
  wind/solar) is not redispatch-adjusted and isn't a "Fahrplan" (it
  predates both logically); SMARD does have an official load forecast
  ("Prognostizierter Stromverbrauch") per its own user manual, but it's
  not yet in this hub's migrated `edh/smard.py` Variable catalog -- a real
  gap, not yet filled. No TSO publishes a forward-looking "expected
  NRV-Saldo" -- the closest thing, the `AEP-Schätzer`, estimates the price
  for a quarter-hour that has *already* ended (within 30 minutes), not a
  predictive tool.

## Next Steps

1. Decide whether the wind-speed-reconstruction result (round 2, above)
   is worth promoting into `energy-data-hub` + `energy-insights` the same
   way the PECD comparison was — would mean adding `windpowerlib` as a
   hub/insights dependency and a much heavier per-turbine SCADA ingestion
   (~1.5 GB raw) than the grid-meter asset. If promoted: also revisit
   whether October 2018's apparent outage affected one turbine or the
   whole farm, now that per-turbine data is already on hand here.
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

### 2026-09-29 — Real wind speed + a real power curve beats PECD by a wide margin

- Kelmarsh's per-turbine SCADA data (the ~1.5 GB `Kelmarsh_SCADA_*.zip`
  files, one per year 2016-2021, one CSV per turbine per year inside)
  really does include a genuine 10-minute nacelle wind speed per turbine
  (`Wind speed (m/s)`, plus a `Density adjusted wind speed (m/s)` variant
  that wasn't populated for at least one turbine/year and wasn't pursued
  further) — confirmed directly, not just inferred from the signal-mapping
  doc. `03_download_kelmarsh_scada.py` pulls all 6 years/turbines,
  discards the raw zips/full ~250-column CSVs after parsing, and keeps
  only `Wind speed (m/s)`, `Density adjusted wind speed (m/s)`,
  `Power (kW)`, `Data Availability` — a deliberately narrow extraction,
  not a full production-grade SCADA ingestion.
- **`windpowerlib` (PyPI) really exists** and its bundled turbine database
  (`oedb/turbine_data.csv` + `power_curves.csv`) has an exact nameplate
  match for Kelmarsh's turbines: `MM92/2050`, 2050 kW rated (matches
  Kelmarsh's static data exactly), a real (not calculated/generic)
  published power curve, hub heights listed include 68.5 m (one of
  Kelmarsh's two actual hub heights exactly; the other, 78.5 m, isn't
  listed but is close to windpowerlib's 80.0 m option) — no need for a
  generic/estimated power curve.
- Setup used: each turbine's own 10-minute wind speed -> `windpowerlib`'s
  `power_output.power_curve()` against the real MM92/2050 curve directly
  (no `ModelChain`, no hub-height wind extrapolation -- the nacelle
  anemometer already measures at ~hub height) -> summed across all 6
  turbines -> resampled to hourly -> same availability adjustment as the
  PECD comparison (multiply by the hour's fraction of available
  10-minute intervals). No wake-loss model -- each turbine's own
  anemometer already implicitly reflects any wake-slowed air it sees.
- Full 2016-2021 window, hourly resolution, vs. Kelmarsh's real
  grid-meter MW:

  | method | corr | MAE (MW) | NMAE | bias (MW) |
  |---|---|---|---|---|
  | PECD, raw | 0.810 | 1.341 | 40.6% | -0.10 |
  | PECD, availability-adj. | 0.855 | 1.181 | 35.8% | -0.26 |
  | wind-speed reconstruction, raw | 0.953 | 0.370 | 11.2% | +0.01 |
  | wind-speed reconstruction, availability-adj. | **0.989** | **0.253** | **7.7%** | -0.11 |

  Even the *raw* (non-availability-adjusted) wind-speed reconstruction
  beats *availability-adjusted* PECD by a wide margin on every metric.
- At every aggregation level (hourly through monthly), the
  availability-adjusted wind-speed reconstruction's correlation
  (0.989-0.996) stays far above and far more stable than PECD's
  (0.855-0.959) — strong evidence that PECD's hourly-scale error is
  dominated by its *weather input* (one large reanalysis grid cell
  standing in for one specific farm's exact location), not by its
  wind-to-power conversion methodology. Not a fully clean isolation of
  that question, though — PECD's own raw wind-speed field (as opposed to
  its finished capacity-factor product) was not pulled in for comparison,
  so "PECD's conversion formula specifically" still isn't tested in
  isolation, only strongly implicated by elimination.
- Not yet promoted to the hub/book (see Next Steps) — `windpowerlib` and
  the much larger per-turbine SCADA pull are a bigger commitment than the
  grid-meter-only asset already promoted.
- **Follow-up same day: two more signals were already sitting in the
  downloaded SCADA data and worth checking.** `Density adjusted wind
  speed (m/s)` (a Greenbyte-computed, site-corrected variant of plain
  wind speed) and each turbine's own real metered `Power (kW)` (as
  opposed to the substation-level grid meter used as ground truth
  throughout). Both added to `04_compare_windspeed_reconstruction.py`:
  - **Density-adjusted wind speed initially looked like a big
    improvement raw** (corr 0.99 vs. plain wind speed's 0.96) — but this
    turned out to be a data-coverage artifact, not a real one: its ~8%
    missing rows are concentrated almost exactly in low-availability
    hours (mean `Data Availability` 0.67 when missing vs. 1.00 when
    present), so the hardest hours were silently excluded from that
    "raw" number rather than well predicted. Once compared fairly
    (availability-adjusted both), plain and density-adjusted wind speed
    land within 0.01 percentage points of NMAE (7.33% vs. 7.33%) — the
    density correction adds nothing measurable once downtime is handled
    properly. Worth remembering generally: check *why* two series
    disagree before crediting either one.
  - **Summing each turbine's own real metered Power (kW) (no wind speed,
    no power curve at all) still misses the grid-meter reading by NMAE
    4.0%**, bias +0.11 MW — ordinary transformer/house-load/cabling loss
    between individual turbine meters and the actual grid connection
    point. This sets a real ceiling: the wind-speed reconstruction's
    7.3% NMAE is roughly half unavoidable physical loss and half genuine
    power-curve/modeling imprecision, useful context for judging how
    much further any better conversion model could plausibly close the
    remaining gap.
  - Also fixed a real bug caught while adding these: the original
    wind-speed-to-MW conversion silently summed turbines with
    `skipna=True` (a missing turbine's reading just drops out of the sum
    rather than invalidating it), understating the farm total whenever
    any turbine was missing — worse for the ~8%-missing density-adjusted
    column than the ~3%-missing plain one. Fixed with `min_count=6`
    (requires all 6 turbines present, else the farm-level result is
    correctly `NaN`) for every per-turbine sum in this pipeline.

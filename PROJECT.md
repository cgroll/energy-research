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
clearly: with the right weather data for the right place and a real power
curve, this farm's output is reconstructable almost perfectly — PECD only
approximates it for lack of station-specific weather data.

**Promoted the same day, 2026-09-29** (this note originally said "not yet
promoted" — stale, fixed 2026-10-05): `windpowerlib` added as a hub/insights
dependency, `kelmarsh_turbine_scada` added to `energy-data-hub`'s
`kelmarsh` asset group, and the full wind-speed-reconstruction comparison
merged directly into `energy-insights`' existing `pages/12_kelmarsh_vs_pecd.py`
(not a separate page) alongside the PECD comparison from round 1. The two
calibration side-checks that didn't change the conclusion (density-adjusted
wind speed: no measurable difference once compared fairly; real per-turbine
metered power as a model-free ceiling: ~4% NMAE from ordinary transformer/
cabling loss) were dropped from that page 2026-10-05 to keep its message
focused on the one finding that matters. Both Kelmarsh sub-topics' own
prototype files (`01`/`02`/`03`/`04`, their downloaded data, notebooks, and
images) have since been fully removed from this repo — fully superseded by
the hub + insights versions, no remaining reason to keep a local copy
(see `energy-research/AGENTS.md`'s research-repo-as-scratch-space
convention, tightened 2026-10-05 to "remove once promoted and verified"
rather than "keep as a scratch record").

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

**2026-10-04 — New sub-topic: how negative day-ahead prices in Germany are
evolving.** A different kind of question from everything else in this repo
so far — not a validation-against-ground-truth exercise, just a first
descriptive look at the hub's `smard_price_de_lu` (EPEX day-ahead auction,
hourly, naive UTC, since 2018-09-30). Built as
`pipeline/11_negative_day_ahead_prices.py`
(`book/notebooks/11_...ipynb`), four views: hours/year (level + trend),
hour-of-day/month-of-year seasonality pooled across years, a year x month
heatmap to see whether the seasonal pattern itself is shifting, and the
distribution of how many consecutive hours a negative-price spell lasts.
- **Clear upward trend**, 2,530 negative hours total out of 69,984. Fit
  on full calendar years only (2019-2025, to avoid the partial 2018/2026
  edge years biasing a raw-count trend): negative-hour share rises
  roughly +1.4 percentage points per year, from under 1% in 2019 to
  several percent by 2024-2025; 2026 (partial, through September) is
  already running at a similarly elevated share.
- **Seasonality is unambiguously a solar-oversupply signature:** negative
  hours concentrate in the late-morning-to-mid-afternoon window (UTC) and
  in the spring-through-early-autumn months — not a wind- or
  winter-driven pattern.
- **The year x month heatmap adds something the pooled seasonality chart
  can't show on its own:** the pattern isn't just intensifying within a
  fixed window, it's widening. Early years (2019-2021) show a handful of
  isolated bright months clustered around spring/summer; 2024-2026 show
  most months of the year lit up, including some autumn/winter months
  that were essentially zero before.
- **Duration distribution, somewhat counter to a "scattered single-hour
  blip" mental model:** a single isolated negative hour is one of the
  *least* common episode lengths, not the typical case. 488 episodes
  total, median length 5 hours, longest a 36-hour unbroken stretch. The
  ~5% of episodes running past 10 hours in a row account for roughly a
  sixth of all negative hours on their own — negative prices mostly
  arrive as multi-hour midday/afternoon blocks.
- Pure descriptive/exploratory, no promotion decision pending — unlike
  the Kelmarsh or balancing-market sub-topics above, this one doesn't
  depend on any new data (the hub's existing `price_de_lu` asset already
  covers it fully) and isn't tied to a validation question, so there's no
  obvious "next step" gate before it could go into `energy-insights` if
  wanted.

**2026-10-04 — New sub-topic: can a conventional-fleet merit order be
built from scratch, cheaply?** Triggered by a conversation about the
Lion Hirth curtailment paper (`literature/`) and whether we could build
*synthetic* merit-order curves for hypothetical market states (more
capacity, more batteries, different support schemes) — which first needed
answering a narrower question: can today's real conventional-fleet merit
order be reproduced at all from public data, without paying for EPEX's
aggregated bid-curve data? Found the Energiewirtschaftliches Institut at
Universität zu Köln (EWI)'s own "EWI Merit-Order Tool 2025" publishes its
full methodology (fetched and read directly,
`Dokumentation_EWI_Merit_Order_Tool_v2025.pdf`): marginal cost per plant
block = (fuel price + transport cost) / efficiency + EUA price × emission
factor / efficiency + other variable costs, available capacity = net
capacity × (1 − outage share), fleet from MaStR, all assumption tables
sourced and published. Replicated it here as a first attempt.

- **`pipeline/12_download_conventional_mastr.py`** — the hub's `edh/mastr.py`
  only harmonizes wind/solar/storage so far (combustion/nuclear were never
  requested from open-mastr); pulling them turned up a real bug, not a
  version issue: `open-mastr`'s own XML→SQL ingestion throws
  `Failed to parse string: '2467 2473' as a scalar of type int64` on
  `EinheitenVerbrennung.xml` and silently leaves that table empty —
  reproduced identically on open-mastr 1.0.0 and 0.17.4 (the hub's pinned
  version). Worked around by letting `Mastr().download()` fetch the raw
  zip (that part succeeds) and then parsing `EinheitenVerbrennung.xml` /
  `EinheitenKernkraft.xml` / `Katalogwerte.xml` directly with
  `lxml.etree.iterparse` (streaming — combustion alone is ~285MB
  uncompressed), picking only the handful of fields a merit order needs
  rather than every column open-mastr tries to type-check. 94,222 raw
  records in, 80,755 operational after filtering `EinheitBetriebsstatus ==
  "In Betrieb"`, 77.6 GW net capacity — in the right ballpark for
  Germany's current conventional fleet (hard coal ~15 GW, lignite ~15 GW,
  gas ~34 GW, oil ~5 GW), first sanity check passed.
- Confirmed MaStR net capacity is in kW throughout, same as the hub's
  wind/solar convention (cross-checked against Grohnde nuclear's real 1360
  MW, decommissioned but still on record).
- `pipeline/13_merit_order_replication.py` — classifies each unit into
  EWI's seven fuel categories (Kernenergie/Braunkohle/Steinkohle/Erdgas/
  Öl/Sonstige/Abfall) via a many-to-one mapping from MaStR's much
  finer-grained `main_fuel` free-text-like codes, further splits gas into
  GuD/Gasturbine via MaStR's `Technologie` field (mirroring EWI's own
  split) plus a third "Erdgas BHKW" bucket this notebook had to add
  because most gas *units* are small decentral combustion engines/fuel
  cells in neither EWI category. Aggregates everything under 10 MW into
  one pseudo-block per category, same convention EWI's documentation
  states for its own tool. Fuel/transport/variable-cost/outage/emission-
  factor assumptions are EWI (2025)'s own published values, reused
  directly, not re-sourced.
- **Real gap, not just a simplification:** MaStR has no efficiency field
  for *any* technology — confirmed both by this pull and by EWI's own
  documentation, which says it carries forward a manually-curated,
  block-level efficiency table from an older tool version rather than
  reading one from MaStR. This notebook instead assigns one textbook
  efficiency per fuel/technology class (e.g. CCGT 58%, lignite 38%, hard
  coal 40%), which is why its boxplot-by-category shows zero within-
  category spread — a visibly coarser result than EWI's own chart, worth
  remembering as the one piece neither tool can get from the registry
  itself.
- **Resulting merit order lands in a plausible shape**, sorted ascending:
  Abfall (~1 EUR/MWh, zero fuel/CO2 cost) → Braunkohle (~83) → Erdgas GuD
  (~96) → Steinkohle (~99) → Erdgas BHKW (~138) → Erdgas Gasturbine (~157)
  → Öl (~304) → Sonstige (~368) — including gas CCGT undercutting hard
  coal at today's EUA price (69.35 EUR/tCO2), a real and well-documented
  coal-to-gas switching effect, not a bug.
- Promoted straight into the book (`book/myst.yml`'s "Merit order" section)
  since it's a complete, self-contained finding — unlike the
  validation-pending sub-topics elsewhere in this file, there's no
  "promote to hub" decision pending yet because the clear next step (see
  below) changes the shape of what would get promoted.
- **Explicitly not yet built:** storage/batteries, cross-border flows,
  the renewables-side curtailment-threshold layer from the Hirth paper,
  and — the actual validation step — checking whether this merit order,
  combined with a real historical residual-load series, predicts actual
  SMARD day-ahead prices on hours without strong renewable oversupply.

**2026-10-05 — reBAP sub-topic chain fully promoted; prototypes removed.**
The balancing-market/reBAP investigation chain (`09`, `14`, `16`, `17` --
see the balancing-market reconstruction work above) is now fully reflected
in `energy-insights`: the calculation-logic finding (`max`/`min` of three
published AEP modules reconstructs real reBAP to 99.99% exact match) lives
in `page_rebap_formula_reconstruction`, and the NRV-Saldo/intraday-price
relationship (`reBAP - ID-AEP` same-sign agreement 93%->100% vs. NRV-Saldo,
with a one-week time-series view) was rebuilt as a new page,
`page_rebap_intraday_signal` (`pages/15_rebap_intraday_signal.py`).
`09`/`14`/`16`/`17` and their notebooks/images removed from this repo
accordingly -- explicit decision: keep only the calculation-logic finding
and the NRV-Saldo/intraday-price relationship from this whole chain,
nothing else (the SAMAWATT-chart reconstruction in `14` and the
intermediate Module-2-only reconstruction in `17` were not carried
forward). `10_balancing_timeline.py` (reference diagram) stays.

Also removed in the same pass:
- `11_negative_day_ahead_prices.py` (+ notebook + 4 images) -- a separate
  topic, found to be a word-for-word structural duplicate of
  `energy-insights`' `page_negative_day_ahead_prices` (same four section
  headings, same four questions), nothing left depending on it here.
- `07_balancing_market_prices.py` (+ notebook + 7 images) -- first look at
  reBAP **and** FCR/aFRR together (boxplot/seasonality/trend/weekday/
  completeness views for all three series). Not a duplicate -- no
  insights page covers FCR/aFRR at all yet -- but removed anyway on an
  explicit call: FCR/aFRR will get their own proper cleanup pass later,
  this exploratory page isn't worth keeping around in the meantime.

**2026-10-06 — Empirical follow-up: is SMARD's wind/solar generation before or
after Engpassmanagement?** The 2026-09-30 finding on this (SMARD's
"realisierte Erzeugung" for non-telemetered plants is a regulated
Online-Hochrechnung required since Jan 2015 to *exclude* curtailment) was
purely textual, from netztransparenz.de's own documentation. User pointed
at a real-numbers way to check it: the EEG annual settlement
("Jahresabrechnung") movement data the four UENBs publish with a ~9-month
lag (2025's data released 2026-09-04) -- the actual metered basis EEG
compensation is paid on, not an estimate. Built `23_download_eeg_bewegungsdaten.py`
(downloads + DuckDB-joins+aggregates all four UENBs' Bewegungsdaten +
Anlagenstammdaten CSVs, ~10M raw rows -> ~1k-row parquet) and
`24_eeg_realized_generation_vs_smard.py` (the comparison + chart, promoted
straight to the book toc). Three independent 2025 numbers per technology:
SMARD's reported generation; the EEG settlement's unambiguous
actual-delivered quantity (`Veraeusserungsform` 1+2+3); and real curtailment
from the hub's already-ingested `smard_redispatch_by_source` (SMARD's own
official redispatch-by-source series -- the EEG settlement's own
`Veraeusserungsform=4`/Ausfallverguetung turned out to capture only a tiny
fraction of real curtailment, a few GWh/year nationally vs. the few-TWh/year
everyone else reports, presumably because modern market-premium-route
turbines' curtailment compensation isn't booked under that category).
**Result, confirmed with real numbers, then stress-tested against an older,
seemingly contradictory finding (user recalled correctly that
`pecd-power-validity-DE` found *subtracting* redispatch from PECD-potential
improved its match against SMARD -- which on its face reads as "SMARD is
already net of curtailment", the opposite conclusion):** for all of onshore
wind, offshore wind, and solar, SMARD's reported 2025 generation sits above
the EEG settlement's clean, unambiguous actual-delivered quantity
(`Veraeusserungsform` 1+2+3), and adding real curtailment (from the hub's own
`smard_redispatch_by_source`, since the EEG settlement's own
`Veraeusserungsform=4`/Ausfallverguetung captures only a tiny fraction of
real curtailment) always *narrows* that gap, never overshoots it -- the one
clean, assumption-light signal against SMARD being net-of-curtailment
anywhere. But curtailment's own *share* of that gap is modest for two of the
three: ~15% for onshore, ~18% for solar -- the other 80%+ is the EEG
settlement's broader "Sonstiges" bucket (plausibly `ausgefoerdert`/merchant
real generation `Einspeiseverguetung`'s own definition explicitly excludes,
nothing to do with curtailment). Only once both are added does the
reconciled total land within ~1% of SMARD for onshore/solar. **Offshore is
the outlier in the other direction:** curtailment alone closes ~48% of its
gap -- the largest share of any technology -- and its `Ausfallverguetung`
settlement category is *exactly zero* across the whole dataset (offshore is
~100% Marktpraemie/direct-marketed, never uses that FIT-era category),
meaning its real curtailment compensation is very likely booked inside
"Sonstiges" instead, so offshore's true curtailment-explained share is
probably even higher than 48%. Checked this against `pecd-power-validity-DE`
directly (pulled the hub's `pecd.de_potential_historic` for 2025 too):
PECD's potential sits 6-22 TWh above SMARD, 2-8x the curtailment volume
itself, so curtailment can only ever be a *minority* contributor to *that*
gap -- matching its own published explained-shares (33% onshore, 71%
offshore, 11% solar) and confirming the two findings don't actually
conflict: PECD's potential carries independent upward bias (no outage
modeling, no self-consumption modeling, weather-model error) large enough to
swamp the curtailment-sized effect, so "subtracting redispatch improves the
PECD match somewhat" doesn't actually prove SMARD nets curtailment out --
that project's own README states "SMARD reports net generation" as an
*assumed* premise in its processing diagram, never tested against ground
truth before now. Where the two analyses do converge: offshore is the
technology where curtailment explains the most of the gap in *both*.
**Bottom line, more hedged than an earlier draft of this finding:** SMARD's
generation series leans pre-curtailment/theoretical-max for all three
technologies -- clearest for offshore wind, where curtailment is the
dominant driver; for onshore/solar the same directional conclusion holds,
but curtailment itself is a smaller, supporting factor next to broader
settlement-coverage effects. Caveat noted in the notebook: EEG settlement
only covers EEG-support-eligible plants, and "Sonstiges" mixes several
real-quantity and financial-only line items that aren't separable here --
the reconciliation holds up well in aggregate, not as a precise
per-category audit.

**2026-10-06 — Same-day follow-up: decomposed `Veraeusserungsform`, and
revised the finding above for offshore.** Built
`25_eeg_veraeusserungsform_categories.py`, re-reading the raw Bewegungsdaten
(not just `23`'s aggregate) to settle two things `24` left unexplained:
- `Veraeusserungsform=4` ("Ausfallverguetung") captures 0-5% of real
  curtailment by technology (vs. SMARD's own redispatch numbers) and is
  exactly 0% for offshore — confirmed it's a FIT-era line current
  market-premium plants don't use.
- "Sonstiges" (5, 41.6 TWh nationally) is **two unrelated things sharing
  one code**: ~35 TWh of zero-EEG-payment merchant generation (plausibly
  `ausgefoerdert` plants, sub-codes `SO-DV`/`SV`) plus a small-quantity
  grab-bag of real payments (biomass flex premia, avoided grid fees,
  corrections, ~470 Mio EUR). Also surfaced a sixth, undocumented bucket —
  blank `Veraeusserungsform` in the raw export, 12.4 TWh / >1 Bn EUR
  nationally — already silently included in `24`'s "all buckets" total via
  a `pivot.get("<NA>", 0.0)` without being called out.
- **Revises `24`'s own bottom line.** Comparing SMARD directly to the
  *full* EEG total (all categories, not just the narrow 1+2+3 slice `24`'s
  main test used) flips the offshore read: onshore/solar still sit close
  to *full EEG total + real curtailment* (within ~1%, gross/pre-curtailment
  reading holds), but **offshore's SMARD figure sits almost exactly on the
  full EEG total alone — adding real curtailment on top overshoots it by
  ~3.3 TWh (~13% above SMARD's own number)**. So offshore is the one
  technology that looks net-of-curtailment, not gross — the opposite of
  `24`'s "offshore is the clearest pre-curtailment case" framing (that
  framing was about curtailment's *share of a gap measured against the
  narrow slice*, not against the fuller real-generation benchmark).
  Plausible reason: offshore is a handful of large, fully telemetered
  parks (SMARD likely gets real already-curtailed meter values), while
  onshore/solar are dominated by small, non-telemetered plants where SMARD
  must use the curtailment-blind extrapolation from the original
  2026-09-30 textual finding.
- Cross-checked magnitudes against the open web: published 2024
  Einspeisemanagement volumes (pv-magazine/cleanthinking, citing
  TSO/Bundesnetzagentur data) — onshore ~3.38 TWh, offshore ~4.56 TWh,
  solar ~1.39 TWh (+97% y/y) — are the same order of magnitude as this
  notebook's 2025 figures (3.33/3.35/2.70 TWh), and the reported ~554 Mio
  EUR total 2024 curtailment compensation lines up with the ~470 Mio EUR
  found hiding in category 5 rather than category 4. Also noted: the much
  larger ~30 TWh "total redispatch" headline (Bundesnetzagentur
  Monitoringbericht) is dominated by conventional-plant redispatch, not
  renewable curtailment — not the right benchmark here.

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
9. **Merit-order replication (2026-10-04 sub-topic above) — backtest
   against real prices.** Join the replicated conventional merit order
   with a real historical residual-load series (hub's `smard` load +
   wind/solar generation) and check whether the resulting
   price-at-intersection prediction tracks actual `smard_price_de_lu` on
   hours *without* strong renewable oversupply (the hours the merit order
   is actually meant to explain) — this is the free alternative to paying
   for EPEX's own aggregated day-ahead bid curves, discussed as the way to
   validate a from-scratch merit order without that data.
10. Add a renewables-side layer: the curtailment-threshold-per-cohort
    logic from the Lion Hirth paper (`literature/`) — feed-in tariff vs.
    market premium vs. merchant, per vintage/size class — so wind/solar
    enter the merit order below zero where applicable instead of being
    ignored entirely, as they are in the 2026-10-04 sub-topic above.
11. Add a storage/battery layer — explicitly out of scope for both EWI's
    own tool and this replication so far, but the main point of interest
    for the synthetic/counterfactual market-state scenarios (more
    capacity, more batteries, different support schemes) this whole
    sub-topic was started to eventually support.
12. Separately (same conversation, not yet started): look at Fraunhofer
    ISE's published behind-the-meter PV self-consumption methodology
    (MaStR + TSO data, 44 self-consumption groups by commissioning
    date/power class/system type) as the next building block for a
    synthetic merit order — covers the "we don't know behind-the-meter
    usage" gap flagged earlier in that conversation.
13. **Explicit promotion gate for the whole merit-order sub-topic**
    (2026-10-04, user decision): keep iterating entirely within
    `energy-research` — backtest (9), renewables layer (10), storage layer
    (11), behind-the-meter (12) — until the result feels good and stable
    end to end. Only then consider promoting any of it into
    `energy-data-hub` (as new Dagster assets, e.g. a `conventional_mastr`
    domain) and `energy-insights` (as a page), same promotion pattern as
    Kelmarsh, deliberately not started early this time.

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

# ---
# jupytext:
#   text_representation:
#     format_name: percent
# kernelspec:
#   display_name: Python 3
#   language: python
#   name: python3
# ---

# %% [markdown]
# # Capacity factors across Europe: country averages vs. within-country spread
#
# Starting hypothesis: a solar plant in Italy should have a higher average
# capacity factor than one in Denmark -- more sun, simple as that. This
# checks that directly against PECD data, then asks a follow-up the
# hypothesis doesn't address: PECD is a *spatial* dataset, so before
# reducing it to one number per country, what resolution does it actually
# offer below the country level, and how much does capacity factor vary
# *within* a country compared to *between* countries?
#
# **This overlaps by design with `energy-insights`' [`08_pecd_country_comparison`]
# (../../energy-insights/book/notebooks/08_pecd_country_comparison.ipynb)**,
# which already builds the full cross-country bar-chart + choropleth
# treatment off the hub's `pecd_country_capacity_factors_simple` asset. That
# page is reproduced here only far enough to check the Italy-vs-Denmark
# hypothesis directly; everything after that -- the within-country
# resolution question -- is new, exploratory content that page doesn't
# cover.
#
# **Solar's cross-country caveat still applies.** Every country's solar
# number blends PECD's 4 solar technologies using *Germany's* own
# market-derived weights (`edh/pecd.py::DEFAULT_SOLAR_COUNTRY_WEIGHTS`) --
# no other country has sourced weights yet. Treat cross-country solar
# comparisons as illustrative, not authoritative (see `08`'s own docstring
# and `energy-data-hub/README.md`). This caveat does *not* apply to the
# Germany-only NUTS2 case study in the last section below -- there, Germany's
# own weights are exactly the market they were derived from.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

# House palette, matching energy-insights' 08_pecd_country_comparison so the
# two pages read as one continuous story.
SOLAR_COLOR = "#f4b942"
ONSHORE_COLOR = "#4a90d9"
OFFSHORE_COLOR = "#1a5fa8"
NEUTRAL = "#898781"
HIGHLIGHT = "#e34948"

# %% [markdown]
# ## What resolution does the hub actually have?
#
# Before computing anything, worth being precise about what "NUTS2" would
# even mean here, because the honest answer is: mostly not available.
#
# - **Solar** has PECD's true `nuts_0` (country-level) product for every
#   country in its domain (`pecd_country_capacity_factors_simple`,
#   1980-2025) -- but genuine Eurostat **NUTS2** solar resolution only
#   exists for **Germany**, because that's the only country the hub
#   requested at that granularity (`pecd_solar_capacity_factors`, 38 real
#   NUTS2 regions, 2015-2025). No other country has a NUTS2 solar file at
#   all.
# - **Wind** (onshore + offshore) has no `nuts_0` option in PECD at all --
#   confirmed directly against the CDS API (see
#   `energy-data-hub/docs/pecd_data_availability.md`). It's only offered at
#   PECD's own zone partition (`peon`/`p2of`), which is downloaded
#   full-Europe, 1980-2025. These zones are *not* NUTS2 -- they're PECD's
#   own, coarser scheme: Germany gets 7 onshore zones (`DE01`-`DE07`)
#   against 38 real NUTS2 regions, Italy gets 7, Denmark 2. Still, it's the
#   finest sub-national resolution PECD's wind product offers, already
#   sitting on disk, so that's what the within-country wind section below
#   uses.
#
# So a genuinely NUTS2-level, all-of-Europe, both-technologies comparison
# isn't possible with what's downloaded today. What follows instead: the
# country-level headline (both technologies, every PECD country), then
# within-country spread at whatever the finest *available* resolution
# actually is for each technology -- PECD's own zones for wind, real NUTS2
# for Germany's solar specifically.

# %% [markdown]
# ## Data

# %%
country_simple = pd.read_parquet(hub_file("pecd", "pecd_country_capacity_factors_simple.parquet"))
YEAR_RANGE = f"{country_simple.index.min().year}–{country_simple.index.max().year}"

mean_solar = country_simple["solar"].mean().dropna().sort_values()
mean_onshore = country_simple["wind_onshore"].mean().dropna().sort_values()
mean_offshore = country_simple["wind_offshore"].mean().dropna().sort_values()

print(f"PECD {YEAR_RANGE}: {len(mean_solar)} countries (solar), {len(mean_onshore)} (wind onshore), {len(mean_offshore)} (wind offshore)")

# %% [markdown]
# ## The hypothesis: Italy vs. Denmark, solar

# %%
it_solar, dk_solar = mean_solar["IT"], mean_solar["DK"]
print(f"Solar mean capacity factor, {YEAR_RANGE}:")
print(f"  Italy:   {it_solar:.1%}")
print(f"  Denmark: {dk_solar:.1%}")
print(f"  Italy is {(it_solar / dk_solar - 1):.0%} higher than Denmark")

# %% [markdown]
# Confirmed, as expected. The rest of this notebook is about what's
# underneath that one number.

# %% [markdown]
# ## Country-level averages, all three technologies
#
# Reproducing `08`'s headline bars (not its choropleths -- see that page for
# the map view) far enough to see Italy/Denmark in the full European
# context, not just as an isolated pair.

# %%
fig, axes = plt.subplots(1, 3, figsize=(16, 9))

for ax, series, color, label in [
    (axes[0], mean_solar, SOLAR_COLOR, "Solar PV"),
    (axes[1], mean_onshore, ONSHORE_COLOR, "Wind onshore"),
    (axes[2], mean_offshore, OFFSHORE_COLOR, "Wind offshore (country mean)"),
]:
    bar_colors = [HIGHLIGHT if c in ("IT", "DK") and label == "Solar PV" else color for c in series.index]
    ax.barh(series.index, series.values, color=bar_colors, edgecolor="white", linewidth=0.4)
    ax.set_xlabel("Long-run mean capacity factor")
    ax.set_title(f"{label}\n(PECD {YEAR_RANGE})", fontsize=10)
    ax.xaxis.grid(True, linewidth=0.4, alpha=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", labelsize=6.5)

fig.suptitle("PECD — long-run mean capacity factors by country (IT/DK highlighted for solar)", fontsize=12)
fig.tight_layout()
fig.savefig(paths.images_path / "06_country_mean_cf_bars.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/06_country_mean_cf_bars.png
# :name: fig-06-country-mean-cf-bars
# Long-run mean capacity factor by country, all PECD countries with
# non-null data, sorted ascending. Italy and Denmark highlighted in the
# solar panel. Same underlying data and result as `08`'s equivalent chart.
# ```

# %%
NON_EUROPE = {"MA", "DZ", "TN", "LY", "EG", "IL", "JO", "LB", "SY", "TR", "EH", "PS"}
solar_europe = mean_solar[~mean_solar.index.isin(NON_EUROPE)]
solar_full_range = mean_solar.max() - mean_solar.min()
solar_europe_range = solar_europe.max() - solar_europe.min()

print(f"Solar range, full PECD domain ({mean_solar.idxmin()} → {mean_solar.idxmax()}): {solar_full_range:.1%} pts")
print(f"Solar range, geographic Europe only ({solar_europe.idxmin()} → {solar_europe.idxmax()}): {solar_europe_range:.1%} pts")

# %% [markdown]
# PECD's domain reaches into North Africa/the Middle East (see
# `pecd_data_availability.md`), which stretches the "full domain" range
# further than a strictly European comparison would. Both numbers are kept
# below as reference points for the within-country spreads that follow.

# %% [markdown]
# ## Within-country spread: wind onshore, at PECD's own zone resolution
#
# Every PEON zone across the full downloaded domain (1980-2025), collapsed
# to its long-run mean, then grouped by the zone code's 2-letter country
# prefix (e.g. `DE01`-`DE07` → `DE`, `DKE1`/`DKW1` → `DK`) -- not
# NUTS2, but the finest resolution PECD's wind product actually offers, and
# a look at whether "one country, one capacity factor" hides real internal
# variation.

# %%
_ONSHORE_DECADES = ["1980-1989", "1990-1999", "2000-2009", "2010-2019", "2020-2025"]
_onshore_parts = [
    pd.read_parquet(hub_file("pecd", "capacity_factors_europe", f"pecd_wind_onshore_tech30_{label}.parquet"))
    for label in _ONSHORE_DECADES
]
onshore_zones = pd.concat(_onshore_parts).sort_index()
mean_zone_cf = onshore_zones.mean().dropna()

zone_country = pd.Series({zone: zone[:2] for zone in mean_zone_cf.index})
zone_df = pd.DataFrame({"capacity_factor": mean_zone_cf, "country": zone_country})

by_country = (
    zone_df.groupby("country")["capacity_factor"]
    .agg(mean="mean", min="min", max="max", zones="count")
    .sort_values("mean")
)
print(f"{len(mean_zone_cf)} onshore zones with data, across {len(by_country)} countries")
print(f"Widest internal spread: {by_country['max'].sub(by_country['min']).idxmax()} "
      f"({by_country['max'].sub(by_country['min']).max():.1%} pts, "
      f"{by_country.loc[by_country['max'].sub(by_country['min']).idxmax(), 'zones']:.0f} zones)")

# %%
spread = (by_country["max"] - by_country["min"]).sort_values()
fig, ax = plt.subplots(figsize=(9, 12))
y = np.arange(len(by_country))

for i, (country, row) in enumerate(by_country.iterrows()):
    ax.plot([row["min"], row["max"]], [i, i], color=NEUTRAL, linewidth=1.5, zorder=1)
    ax.scatter([row["min"], row["max"]], [i, i], color=ONSHORE_COLOR, s=22, zorder=2, edgecolors="white", linewidths=0.4)
    ax.scatter([row["mean"]], [i], color=HIGHLIGHT, marker="|", s=140, zorder=3)

ax.set_yticks(y)
ax.set_yticklabels([f"{c} ({int(n)})" for c, n in zip(by_country.index, by_country["zones"])], fontsize=7)
ax.set_xlabel("Onshore wind capacity factor (min–max across the country's PEON zones)")
ax.set_title(f"Within-country spread, wind onshore\n(PECD zones, {YEAR_RANGE}; red tick = country mean; zone count in parentheses)", fontsize=10)
ax.xaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(paths.images_path / "06_wind_onshore_zone_spread.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/06_wind_onshore_zone_spread.png
# :name: fig-06-wind-onshore-zone-spread
# Each country's onshore wind zones, min to max long-run mean capacity
# factor (blue dots), red tick marking the country mean. Countries with a
# single zone show as one dot with no line. Some countries (Spain, France,
# Turkey) span a wider range internally than separates many *pairs* of
# countries at the country-mean level -- "one country, one number" can hide
# as much as it reveals.
# ```

# %% [markdown]
# ## Case study: true NUTS2 resolution, Germany's solar
#
# The one place in this dataset with real Eurostat NUTS2 granularity.
# Blended from PECD's 4 solar technologies using Germany's own
# market-derived weights (`edh/pecd.py::DEFAULT_SOLAR_COUNTRY_WEIGHTS`,
# sourced from BSW-Solar/BNetzA/pv-magazine figures for
# `energy-insights/pages/06_pecd_simple_vs_mastr_weighted.py`) -- unlike the
# cross-country solar numbers above, this is the one country these weights
# were actually derived for, so the caveat above doesn't apply here.

# %%
DE_SOLAR_WEIGHTS = {"62": 0.31, "63": 0.02, "61": 0.39, "60": 0.28}

# Eurostat NUTS2 region names, for readable axis labels only (not used in
# any computation).
DE_NUTS2_NAMES = {
    "DE11": "Stuttgart", "DE12": "Karlsruhe", "DE13": "Freiburg", "DE14": "Tübingen",
    "DE21": "Oberbayern", "DE22": "Niederbayern", "DE23": "Oberpfalz", "DE24": "Oberfranken",
    "DE25": "Mittelfranken", "DE26": "Unterfranken", "DE27": "Schwaben", "DE30": "Berlin",
    "DE40": "Brandenburg", "DE50": "Bremen", "DE60": "Hamburg", "DE71": "Darmstadt",
    "DE72": "Gießen", "DE73": "Kassel", "DE80": "Mecklenburg-Vorpommern",
    "DE91": "Braunschweig", "DE92": "Hannover", "DE93": "Lüneburg", "DE94": "Weser-Ems",
    "DEA1": "Düsseldorf", "DEA2": "Köln", "DEA3": "Münster", "DEA4": "Detmold",
    "DEA5": "Arnsberg", "DEB1": "Koblenz", "DEB2": "Trier", "DEB3": "Rheinhessen-Pfalz",
    "DEC0": "Saarland", "DED2": "Dresden", "DED4": "Chemnitz", "DED5": "Leipzig",
    "DEE0": "Sachsen-Anhalt", "DEF0": "Schleswig-Holstein", "DEG0": "Thüringen",
}

solar_de_nuts2 = pd.read_parquet(hub_file("pecd", "pecd_solar_capacity_factors.parquet"))
de_regions = solar_de_nuts2.columns.get_level_values("region").unique()

de_blended = pd.Series(
    {region: sum(solar_de_nuts2[(tech, region)] * weight for tech, weight in DE_SOLAR_WEIGHTS.items()).mean()
     for region in de_regions}
).sort_values()

de_range = de_blended.max() - de_blended.min()
print(f"Germany NUTS2 solar, {len(de_blended)} regions:")
print(f"  lowest:  {de_blended.idxmin()} ({DE_NUTS2_NAMES[de_blended.idxmin()]}) = {de_blended.min():.1%}")
print(f"  highest: {de_blended.idxmax()} ({DE_NUTS2_NAMES[de_blended.idxmax()]}) = {de_blended.max():.1%}")
print(f"  internal range: {de_range:.1%} pts")
print()
print(f"For comparison, the full cross-country solar range was {solar_full_range:.1%} pts "
      f"(geographic Europe only: {solar_europe_range:.1%} pts)")
print(f"Germany's own north-south spread is only {de_range / solar_europe_range:.0%} of the European range")

# %%
fig, ax = plt.subplots(figsize=(8, 10))
labels = [f"{code} — {DE_NUTS2_NAMES[code]}" for code in de_blended.index]
colors = [HIGHLIGHT if code in (de_blended.idxmin(), de_blended.idxmax()) else SOLAR_COLOR for code in de_blended.index]
ax.barh(labels, de_blended.values * 100, color=colors, edgecolor="white", linewidth=0.4)
ax.set_xlabel("Blended solar PV capacity factor (%)")
ax.set_title(f"Germany's 38 NUTS2 regions, solar capacity factor\n(PECD 2015-2025, DE technology-mix weights)", fontsize=10)
ax.xaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
ax.tick_params(axis="y", labelsize=6.5)
fig.tight_layout()
fig.savefig(paths.images_path / "06_de_solar_nuts2_bar.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/06_de_solar_nuts2_bar.png
# :name: fig-06-de-solar-nuts2-bar
# Germany's 38 real NUTS2 regions, sorted by blended solar capacity factor.
# Lowest and highest highlighted. The gap top-to-bottom is a real,
# physically sensible south-north (Bavaria/Baden-Württemberg vs. the
# coastal north) gradient -- just a much smaller one than separates Finland
# from Cyprus.
# ```

# %% [markdown]
# ## Takeaway
#
# The Italy-vs-Denmark hypothesis holds, and holds generally: cross-country
# differences in solar capacity factor across Europe are large (roughly
# 9-12 percentage points end to end, depending on whether North
# Africa/the Middle East are included). But "one number per country" isn't
# equally safe for every technology:
#
# - **Solar within one country stays comparatively tame** -- Germany's own
#   real NUTS2 spread is a small fraction of the cross-country range, so a
#   single country-level solar figure is a reasonable summary of that
#   country.
# - **Onshore wind can vary as much *within* some countries as *between*
#   many country pairs** -- Spain, France, and (well outside the EU)
#   Turkey each span a wider range across their own PECD zones than
#   separates several country means from each other. A single national
#   wind capacity factor is a much leakier summary than the equivalent
#   solar number, and siting *within* a country matters more for wind than
#   for solar.
#
# Neither wind zone data nor Germany's NUTS2 solar data generalizes the
# other. Getting a genuine NUTS2-level, all-of-Europe solar comparison
# wouldn't even need a new *kind* of PECD request -- `edh/pecd.py`'s solar
# pull already asks CDS for `spatial_resolution=nuts_2` across the full
# domain (`download_capacity_factor_zip`, no country filter in the
# request itself); the raw zip already contained every country's NUTS2
# columns once. `process_solar_capacity_factors` just keeps Germany's
# columns and the raw zip is deleted afterward (this hub's normal
# raw-download cleanup policy) -- so the other countries' NUTS2 columns
# already passed through this pipeline once and were discarded, not
# something PECD refuses to provide. Re-extracting them means re-running
# that same CDS request without the DE filter, not requesting new data.
# Wind has no NUTS2 equivalent to extend to -- PECD's wind product simply
# doesn't offer country-level or NUTS2 spatial resolution at all, at any
# request (see `pecd_data_availability.md`); its own zone scheme above is
# the finest it gets.

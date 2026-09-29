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
# # Does real local wind speed + a real power curve beat PECD?
#
# `02_compare_kelmarsh_pecd.py` found PECD's onshore wind capacity factor
# (zone UK03, scaled to Kelmarsh's installed capacity) tracks Kelmarsh's
# real metered generation reasonably well once corrected for measured
# downtime -- but the hourly scatter stayed noticeably diffuse (r=0.86 at
# hourly resolution vs. r=0.96 at monthly).
#
# This asks: is that hourly noise mainly PECD's *weather input* (one large
# reanalysis grid cell standing in for one specific farm) or its *wind-to-
# power conversion*? Tested by swapping in something PECD doesn't have:
# Kelmarsh's own real, per-turbine nacelle wind speed (from the SCADA data
# skipped in `01_download_kelmarsh.py`, now pulled in
# `03_download_kelmarsh_scada.py`), converted to power via `windpowerlib`'s
# real, published Senvion MM92/2050 power curve (an exact nameplate match
# for Kelmarsh's turbines -- rated power, and hub heights close to the two
# values Kelmarsh's turbines actually use).

# %%
import matplotlib.pyplot as plt
import pandas as pd
from windpowerlib import WindTurbine, power_output

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

INSTALLED_CAPACITY_MW = 12.3
PECD_ZONE = "UK03"

# %% [markdown]
# ## Real generation + availability (same as 02_compare_kelmarsh_pecd.py)

# %%
with open(paths.kelmarsh_grid_meter_file) as f:
    lines = f.readlines()
header_idx = next(i for i, line in enumerate(lines) if line.startswith("# Date and time"))
grid = pd.read_csv(paths.kelmarsh_grid_meter_file, skiprows=header_idx)
grid.columns = [c.lstrip("# ").strip() for c in grid.columns]
grid["Date and time"] = pd.to_datetime(grid["Date and time"], utc=True)
grid = grid.set_index("Date and time")

actual_hourly_mw = (
    grid["Grid Meter Energy Export (kWh)"].resample("h").sum(min_count=6).div(1000).rename("actual")
)
hourly_availability = grid["Energy meter based availability"].resample("h").mean()

# %% [markdown]
# ## PECD onshore wind capacity factor for zone UK03, scaled to MW

# %%
pecd_decade_files = [
    hub_file("pecd", "capacity_factors_europe", "pecd_wind_onshore_tech30_2010-2019.parquet"),
    hub_file("pecd", "capacity_factors_europe", "pecd_wind_onshore_tech30_2020-2025.parquet"),
]
pecd_cf = pd.concat(
    [pd.read_parquet(p, columns=[PECD_ZONE])[PECD_ZONE] for p in pecd_decade_files]
).sort_index()
pecd_cf.index = pecd_cf.index.tz_localize("UTC")
pecd_raw_mw = (pecd_cf * INSTALLED_CAPACITY_MW).rename("pecd_raw")

# %% [markdown]
# ## Wind-speed reconstruction: real per-turbine wind speed -> MM92/2050 power curve
#
# Each turbine's own 10-minute nacelle wind speed goes through
# `windpowerlib`'s real published MM92/2050 power curve (not derived or
# generic -- the exact model Kelmarsh uses, sourced from
# windenergie-im-binnenland.de via windpowerlib's turbine database). No
# hub-height extrapolation needed -- the nacelle anemometer already
# measures at (approximately) hub height. Summed across all 6 turbines,
# then resampled to hourly, matching the actual/PECD series above. No
# wake-loss modeling -- each turbine already reflects its own locally
# measured wind speed, wake effects included implicitly (if a turbine's
# anemometer sees wake-slowed air, that's already in its number).

# %%
windspeed_long = pd.read_parquet(paths.downloads_path / "kelmarsh_turbine_windspeed_power.parquet")

wt = WindTurbine(turbine_type="MM92/2050", hub_height=78.5)
power_curve = wt.power_curve


def farm_mw_from_wind_speed(column: str) -> pd.Series:
    """Pivot one wind-speed column to wide (turbine x timestamp), run each
    turbine's series through the MM92/2050 power curve, and sum to a farm
    total. `min_count=6` requires all 6 turbines present before summing --
    otherwise a missing turbine would silently understate the farm total
    rather than correctly propagate as unknown (matters more for the
    density-adjusted column below, ~9% missing per turbine vs. ~3% for
    plain wind speed)."""
    wide = windspeed_long.pivot(index="timestamp", columns="turbine", values=column)
    wide.index = wide.index.tz_localize("UTC")
    modeled_w = wide.apply(
        lambda ws: power_output.power_curve(
            wind_speed=ws,
            power_curve_wind_speeds=power_curve["wind_speed"],
            power_curve_values=power_curve["value"],
        )
    )
    return (modeled_w.sum(axis=1, min_count=6) / 1_000_000).resample("h").mean()  # W -> MW


windspeed_raw_mw = farm_mw_from_wind_speed("Wind speed (m/s)").rename("windspeed_raw")

# %% [markdown]
# ## Variant: the *density-adjusted* wind speed column instead
#
# Power curves are defined for a reference air density; `Density adjusted
# wind speed (m/s)` (Greenbyte's own site-corrected signal, ~91% coverage
# per turbine vs. ~97% for plain wind speed) should in principle line up
# with the power curve more accurately than the uncorrected measurement.

# %%
windspeed_densityadj_raw_mw = farm_mw_from_wind_speed("Density adjusted wind speed (m/s)").rename(
    "windspeed_densityadj_raw"
)

# %% [markdown]
# ## Variant: sum of each turbine's own *real measured* Power (kW)
#
# Not a model at all -- this sums Kelmarsh's own per-turbine metered
# output directly, with no wind speed or power curve involved. Ground
# truth for how much of the actual-vs-PECD/wind-speed gap is just normal
# transformer/house-load/cabling loss between the turbines' own meters and
# the grid connection point actually measured by `actual` -- an upper
# bound on how close any wind-speed-based reconstruction could plausibly
# get without modeling those losses explicitly.

# %%
turbine_power_wide = windspeed_long.pivot(index="timestamp", columns="turbine", values="Power (kW)")
turbine_power_wide.index = turbine_power_wide.index.tz_localize("UTC")
turbine_power_sum_mw = (
    (turbine_power_wide.sum(axis=1, min_count=6) / 1000).resample("h").mean().rename("turbine_power_sum")
)

# %% [markdown]
# ## Availability-adjust the wind-speed-based methods (not PECD-only rule)
#
# Same correction as `02_compare_kelmarsh_pecd.py` for PECD and both
# wind-speed reconstructions: scale by the hour's fraction of 10-minute
# intervals flagged available, so known downtime isn't unfairly counted
# against a method's *weather* accuracy. **Not** applied to
# `turbine_power_sum` -- that's real measured output, downtime already
# baked in correctly; adjusting it again would double-count.

# %%
comparison = pd.concat(
    [
        actual_hourly_mw,
        pecd_raw_mw,
        windspeed_raw_mw,
        windspeed_densityadj_raw_mw,
        turbine_power_sum_mw,
        hourly_availability.rename("hourly_availability"),
    ],
    axis=1,
    sort=True,
)
valid_range = actual_hourly_mw.dropna()
comparison = comparison.loc[valid_range.index.min() : valid_range.index.max()]
comparison["pecd_adj"] = comparison["pecd_raw"] * comparison["hourly_availability"]
comparison["windspeed_adj"] = comparison["windspeed_raw"] * comparison["hourly_availability"]
comparison["windspeed_densityadj_adj"] = (
    comparison["windspeed_densityadj_raw"] * comparison["hourly_availability"]
)

print(comparison.describe())

# %% [markdown]
# ## Headline stats: correlation, MAE, normalized MAE

# %%
def stats(actual: pd.Series, other: pd.Series) -> dict:
    joined = pd.concat([actual, other], axis=1).dropna()
    a, b = joined.iloc[:, 0], joined.iloc[:, 1]
    err = b - a
    return {
        "corr": a.corr(b),
        "mae_mw": err.abs().mean(),
        "nmae_pct": err.abs().mean() / a.mean() * 100,
        "bias_mw": err.mean(),
    }


summary = pd.DataFrame(
    {
        col: stats(comparison["actual"], comparison[col])
        for col in [
            "pecd_raw",
            "pecd_adj",
            "windspeed_raw",
            "windspeed_adj",
            "windspeed_densityadj_raw",
            "windspeed_densityadj_adj",
            "turbine_power_sum",
        ]
    }
).T
print(summary.round(3))
print(f"\nn hours, plain wind speed methods:           {comparison[['actual', 'windspeed_adj']].dropna().shape[0]:,}")
print(f"n hours, density-adjusted wind speed methods: {comparison[['actual', 'windspeed_densityadj_adj']].dropna().shape[0]:,}")
print(f"n hours, turbine_power_sum:                   {comparison[['actual', 'turbine_power_sum']].dropna().shape[0]:,}")

# %% [markdown]
# ## Is density-adjusted wind speed actually better, or just missing the hard hours?
#
# `windspeed_densityadj_raw` looks dramatically better than `windspeed_raw`
# above (corr 0.992 vs. 0.955) -- suspiciously close to `windspeed_raw`'s
# *availability-adjusted* number already, without any adjustment applied.
# Checked directly: is `Density adjusted wind speed`'s ~8% missingness
# random, or concentrated exactly in the low-availability hours that make
# the raw comparison hard in the first place?

# %%
is_missing = windspeed_long["Density adjusted wind speed (m/s)"].isna()
print("Mean `Data Availability` when density-adjusted wind speed is present:", round(windspeed_long.loc[~is_missing, "Data Availability"].mean(), 4))
print("Mean `Data Availability` when density-adjusted wind speed is missing:", round(windspeed_long.loc[is_missing, "Data Availability"].mean(), 4))

# %% [markdown]
# Confirmed: `Data Availability` averages ~1.00 when the density-adjusted
# signal is present, but only ~0.67 when it's missing -- its ~8% of
# missing rows are heavily concentrated in downtime, not random. That
# means `windspeed_densityadj_raw`'s good "raw" score is largely a
# data-coverage artifact (the hard, low-availability hours are simply
# dropped by `.dropna()` in `stats()`, not correctly predicted) rather
# than genuinely better power-curve accuracy. Once both are fairly
# compared on equal footing -- availability-adjusted -- the two converge
# to virtually the same result (`windspeed_adj` NMAE 7.33% vs.
# `windspeed_densityadj_adj` 7.33%), confirming the density correction
# itself adds essentially nothing here once downtime is handled properly.

# %% [markdown]
# ## Daily-mean overlay: actual vs. both availability-adjusted methods

# %%
fig, ax = plt.subplots(figsize=(14, 4))
comparison[["actual", "pecd_adj", "windspeed_adj"]].resample("D").mean().plot(ax=ax)
ax.set_ylabel("MW")
ax.set_ylim(0, INSTALLED_CAPACITY_MW)
ax.set_title("Kelmarsh: actual vs. availability-adjusted PECD vs. availability-adjusted wind-speed reconstruction")
fig.savefig(paths.images_path / "04_windspeed_reconstruction_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/04_windspeed_reconstruction_daily.png
# :name: fig-04-windspeed-reconstruction-daily
# Daily mean MW: Kelmarsh actual vs. availability-adjusted PECD vs.
# availability-adjusted wind-speed reconstruction.
# ```

# %% [markdown]
# ## Hourly scatter: PECD, wind-speed reconstruction, and the real-power ceiling
#
# A third panel alongside the usual two: `turbine_power_sum` is not a
# model at all, just the sum of each turbine's own real metered Power
# (kW) -- no wind speed, no power curve. It shows how much of the
# remaining gap in the wind-speed reconstruction is genuine power-curve
# imprecision vs. simply the normal transformer/house-load/cabling loss
# between individual turbine meters and the grid connection point that
# *any* turbine-level method, however accurate, would still show.

# %%
hourly = comparison[["actual", "pecd_adj", "windspeed_adj", "turbine_power_sum"]].dropna()

panels = [
    ("pecd_adj", "PECD (availability-adj.)"),
    ("windspeed_adj", "Wind-speed reconstruction (availability-adj.)"),
    ("turbine_power_sum", "Sum of real per-turbine Power (kW) -- no model"),
]
fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.5), sharex=True, sharey=True)
for ax, (col, title) in zip(axes, panels):
    ax.scatter(hourly[col], hourly["actual"], s=2, alpha=0.1, rasterized=True)
    lims = [0, INSTALLED_CAPACITY_MW]
    ax.plot(lims, lims, "k--", linewidth=1)
    ax.set_xlabel(f"{title} (hourly MW)")
    s = stats(hourly["actual"], hourly[col])
    ax.set_title(f"{title}\nr={s['corr']:.2f}, MAE={s['mae_mw']:.2f} MW, NMAE={s['nmae_pct']:.1f}%")
axes[0].set_ylabel("Kelmarsh actual MW (hourly)")
fig.tight_layout()
fig.savefig(paths.images_path / "04_windspeed_reconstruction_scatter.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/04_windspeed_reconstruction_scatter.png
# :name: fig-04-windspeed-reconstruction-scatter
# Hourly scatter, all availability-adjusted except the real-power sum:
# PECD vs. actual (left), wind-speed reconstruction vs. actual (middle),
# sum of real per-turbine power vs. actual grid-meter reading (right, the
# no-modeling ceiling).
# ```

# %% [markdown]
# ## Correlation vs. aggregation level, both methods

# %%
AGGREGATIONS = [("h", "hourly"), ("3h", "3-hourly"), ("6h", "6-hourly"), ("D", "daily"), ("W", "weekly"), ("MS", "monthly")]
agg_labels = [label for _, label in AGGREGATIONS]
agg_corr = pd.DataFrame(
    {
        "pecd_adj": [comparison.resample(f).mean().dropna()["actual"].corr(comparison.resample(f).mean().dropna()["pecd_adj"]) for f, _ in AGGREGATIONS],
        "windspeed_adj": [comparison.resample(f).mean().dropna()["actual"].corr(comparison.resample(f).mean().dropna()["windspeed_adj"]) for f, _ in AGGREGATIONS],
    },
    index=agg_labels,
)
print(agg_corr.round(3))

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(agg_corr.index, agg_corr["pecd_adj"], marker="o", label="PECD (availability-adj.)")
ax.plot(agg_corr.index, agg_corr["windspeed_adj"], marker="o", label="Wind-speed reconstruction (availability-adj.)")
ax.set_ylim(0.8, 1.0)
ax.set_ylabel("Correlation vs. Kelmarsh actual MW")
ax.set_title("Wind-speed reconstruction leads at every aggregation level")
ax.legend()
plt.show()

# %% [markdown]
# ## Takeaways
#
# - Real per-turbine wind speed run through a real MM92/2050 power curve,
#   summed to farm level and availability-adjusted the same way as PECD,
#   beats availability-adjusted PECD at every aggregation level tested,
#   most dramatically at native hourly resolution (NMAE 7.3% vs. 35.8%).
# - This points squarely at PECD's *weather input* as the main source of
#   hourly-scale error, not its wind-to-power conversion approach: once
#   the weather input is a real, local, farm-specific measurement instead
#   of one large reanalysis grid cell, a comparably simple power-curve
#   conversion already reconstructs generation far more closely.
# - **The density-adjusted wind speed variant taught a methodology
#   lesson, not a modeling one:** it looked much better *raw* (corr 0.99
#   vs. plain wind speed's 0.96), but that's a data-coverage artifact --
#   its ~8% missing rows are concentrated almost exactly in low-
#   availability hours (mean `Data Availability` 0.67 when missing vs.
#   1.00 when present), so the hard hours were silently dropped rather
#   than well predicted. Once both variants are compared fairly
#   (availability-adjusted), they land within 0.01 percentage points of
#   each other -- the density correction itself adds nothing measurable
#   here. A reminder to check *why* two series disagree before crediting
#   either one.
# - **The real per-turbine power sum sets a ceiling:** summing Kelmarsh's
#   own metered per-turbine output (no wind speed, no power curve at all)
#   still misses the grid-meter reading by NMAE 4.0% -- ordinary
#   transformer/house-load/cabling loss between individual turbines and
#   the grid connection point. The wind-speed reconstruction's 7.3% is
#   roughly half attributable to that same unavoidable physical gap and
#   half to genuine power-curve/measurement imprecision -- meaningful
#   context for how much further a better conversion model could
#   plausibly close the gap.
# - Caveat: this still isn't a fully controlled comparison of "PECD's
#   conversion formula" in isolation -- PECD's own raw wind-speed field
#   (not just its finished capacity factor product) isn't pulled into
#   this hub yet, so the weather-input-vs-conversion-formula question
#   isn't cleanly separated, only strongly suggested by this result.
# - The wind-speed reconstruction still isn't free of its own
#   simplifications -- no explicit wake-loss model -- yet still
#   outperforms PECD by a wide margin, suggesting there's headroom even
#   PECD's own methodology improvements wouldn't close as long as it's
#   tied to a coarse weather grid.
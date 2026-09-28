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
# # Kelmarsh vs PECD: capacity factor translated to MW
#
# Kelmarsh wind farm (UK, 6x Senvion MM92, 12.3 MW installed) publishes its
# actual metered grid-point generation (Zenodo record 5841834, CC-BY-4.0).
# We compare that against the hub's PECD onshore wind capacity factor for
# zone `UK03` (the PECD zone covering Northamptonshire/the English
# Midlands, see `erx/paths.py` and the platform's PECD zone mask).
#
# Deliberately **not** comparing capacity factors directly: instead the
# PECD capacity factor is translated into MW using Kelmarsh's own installed
# capacity, so both series end up on the same physical axis (MW) that can
# be read against Kelmarsh's actual nameplate output.

# %%
import matplotlib.pyplot as plt
import pandas as pd

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

INSTALLED_CAPACITY_MW = 12.3  # 6 x Senvion MM92 @ 2.05 MW (kelmarsh_wt_static_file)
PECD_ZONE = "UK03"

# %% [markdown]
# ## Load Kelmarsh grid meter data, convert to hourly MW
#
# The raw export is 10-minute `Grid Meter Energy Export (kWh)` -- energy
# delivered in each 10-minute interval. Summing six consecutive intervals
# gives the energy delivered in that hour (kWh), which is numerically the
# same as the average power over that hour in kW (since the interval is
# exactly 1 hour) -- divide by 1000 for MW.

# %%
with open(paths.kelmarsh_grid_meter_file) as f:
    lines = f.readlines()
header_idx = next(i for i, line in enumerate(lines) if line.startswith("# Date and time"))

grid = pd.read_csv(paths.kelmarsh_grid_meter_file, skiprows=header_idx)
grid.columns = [c.lstrip("# ").strip() for c in grid.columns]
grid["Date and time"] = pd.to_datetime(grid["Date and time"], utc=True)
grid = grid.set_index("Date and time")

kelmarsh_hourly_mw = (
    grid["Grid Meter Energy Export (kWh)"]
    .resample("h")
    .sum(min_count=6)  # require all six 10-min readings present, else NaN
    .div(1000)
    .rename("kelmarsh_actual_mw")
)

# %% [markdown]
# ## Hourly availability, from the same grid meter file
#
# `Energy meter based availability` is a binary (0/1) flag per 10-minute
# interval, at the whole-farm grid-meter level (not per turbine) -- see the
# PROJECT.md lessons-learned entry. It is in fact tautological with
# `Grid Meter Energy Export (kWh) > 0` (confirmed: availability==0 implies
# export==0 always, and vice versa in this file), so it doesn't distinguish
# "turbine down" from "no wind" at the 10-minute level. Averaged over an
# hour, though, the fraction of the hour flagged available becomes a real
# downtime signal for hours where PECD says there *should* have been wind:
# if PECD implies output but the farm was down for part of the hour, this
# fraction captures that, which is exactly the effect seen in Feb/Mar 2016
# (pre-commissioning) and Oct 2018 (looked like a real outage).

# %%
hourly_availability = (
    grid["Energy meter based availability"]
    .resample("h")
    .mean()  # fraction of the hour's six 10-min readings flagged available
    .rename("hourly_availability")
)

# %% [markdown]
# ## Load PECD onshore wind capacity factor for zone UK03, scale to MW

# %%
pecd_decade_files = [
    hub_file("pecd", "capacity_factors_europe", "pecd_wind_onshore_tech30_2010-2019.parquet"),
    hub_file("pecd", "capacity_factors_europe", "pecd_wind_onshore_tech30_2020-2025.parquet"),
]
pecd_cf = pd.concat(
    [pd.read_parquet(p, columns=[PECD_ZONE])[PECD_ZONE] for p in pecd_decade_files]
).sort_index()
pecd_cf.index = pecd_cf.index.tz_localize("UTC")

pecd_implied_mw = (pecd_cf * INSTALLED_CAPACITY_MW).rename("pecd_implied_mw")

# %% [markdown]
# ## Align to Kelmarsh's actual reporting window and compare in MW

# %%
comparison = pd.concat(
    [kelmarsh_hourly_mw, pecd_implied_mw, hourly_availability], axis=1, sort=True
)
valid_range = kelmarsh_hourly_mw.dropna()
comparison = comparison.loc[valid_range.index.min() : valid_range.index.max()]

comparison["pecd_implied_mw_availability_adjusted"] = (
    comparison["pecd_implied_mw"] * comparison["hourly_availability"]
)

print(comparison.describe())
print(
    "\nMean actual MW:", round(comparison["kelmarsh_actual_mw"].mean(), 3),
    "| Mean PECD-implied MW:", round(comparison["pecd_implied_mw"].mean(), 3),
    "| Mean PECD-implied MW (availability-adjusted):",
    round(comparison["pecd_implied_mw_availability_adjusted"].mean(), 3),
)

# %%
fig, ax = plt.subplots(figsize=(14, 4))
comparison.resample("D").mean().plot(ax=ax)
ax.set_ylabel("MW")
ax.set_ylim(0, INSTALLED_CAPACITY_MW)
ax.set_title("Kelmarsh: actual grid-point generation vs PECD-implied MW (daily mean)")
fig.savefig(paths.images_path / "02_kelmarsh_vs_pecd_mw_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/02_kelmarsh_vs_pecd_mw_daily.png
# :name: fig-02-kelmarsh-vs-pecd-mw-daily
# Daily mean MW: Kelmarsh's actual metered grid-point generation vs PECD's
# onshore wind capacity factor (zone UK03) scaled to Kelmarsh's 12.3 MW
# installed capacity.
# ```

# %%
monthly = comparison.resample("MS").mean().dropna()
corr = monthly["kelmarsh_actual_mw"].corr(monthly["pecd_implied_mw"])
bias_mw = (monthly["pecd_implied_mw"] - monthly["kelmarsh_actual_mw"]).mean()
corr_adj = monthly["kelmarsh_actual_mw"].corr(monthly["pecd_implied_mw_availability_adjusted"])
bias_adj_mw = (
    monthly["pecd_implied_mw_availability_adjusted"] - monthly["kelmarsh_actual_mw"]
).mean()
print(f"Monthly-mean correlation, raw PECD:          {corr:.3f}  bias={bias_mw:+.3f} MW")
print(f"Monthly-mean correlation, availability-adj.: {corr_adj:.3f}  bias={bias_adj_mw:+.3f} MW")

fig, ax = plt.subplots(figsize=(6, 6))
ax.scatter(monthly["pecd_implied_mw"], monthly["kelmarsh_actual_mw"], label="raw PECD", alpha=0.7)
ax.scatter(
    monthly["pecd_implied_mw_availability_adjusted"],
    monthly["kelmarsh_actual_mw"],
    label="availability-adjusted PECD",
    alpha=0.7,
)
lims = [0, INSTALLED_CAPACITY_MW]
ax.plot(lims, lims, "k--", linewidth=1, label="1:1")
ax.set_xlabel("PECD-implied MW (monthly mean)")
ax.set_ylabel("Kelmarsh actual MW (monthly mean)")
ax.set_title(f"Raw r={corr:.2f} vs availability-adj. r={corr_adj:.2f}")
ax.legend()
fig.savefig(paths.images_path / "02_kelmarsh_vs_pecd_mw_scatter.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/02_kelmarsh_vs_pecd_mw_scatter.png
# :name: fig-02-kelmarsh-vs-pecd-mw-scatter
# Monthly-mean MW, Kelmarsh actual vs PECD-implied -- raw and
# availability-adjusted -- with 1:1 reference line.
# ```

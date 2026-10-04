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
# # Balancing-market prices: reBAP, FCR, aFRR
#
# First look at the three balancing-market series just added to the hub
# (`energy-data-hub`'s `balancing_market` asset group, migrated from
# `~/research/vpp-learning` 2026-09-30): **reBAP** (Ausgleichsenergiepreis /
# balancing energy price, 15-min, since 2014), **FCR** (Frequency Containment
# Reserve / Primärregelleistung capacity price, daily x 4h block, since 2021),
# and **aFRR** (automatic Frequency Restoration Reserve / Sekundärregelleistung
# capacity price, daily x direction x 4h block, since 2018-10).
#
# Same six views for each series: the raw time series, a boxplot by
# time-of-day block (which blocks are structurally more/less expensive),
# average by calendar month across all years (seasonality), average by
# calendar year (is anything trending), weekday vs. weekend, and a look at
# how complete each series actually is, year by year.
#
# **⚠️ Timezone note, carried over from the hub's own README:** FCR/aFRR's
# 4-hour block columns (`negpos_00_04`, `neg_00_04`, `pos_00_04`, ...) are
# German local clock time (CET/CEST), not UTC -- confirmed via
# regelleistung.net's own documentation (block duration is "usually 4
# hours, subject to daylight saving time shift"). reBAP's own timestamps
# are naive UTC (hub convention). To make the block-boxplot and
# weekday/seasonality views genuinely comparable across all three series,
# reBAP is converted to German local time (`Europe/Berlin`) below before
# any block/weekday/month/year grouping -- not just for display.

# %%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

# Reference palette (energy-platform house style): fixed categorical hues,
# never cycled. One hue per series; time-of-day blocks within a series get
# a single-hue sequential ramp instead (ordinal, not a separate identity).
REBAP_COLOR = "#8e44ad"
FCR_COLOR = "#2a78d6"
AFRR_NEG_COLOR = "#1baf7a"
AFRR_POS_COLOR = "#e34948"
NEUTRAL = "#898781"

BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]
BLOCK_EDGES = [0, 4, 8, 12, 16, 20, 24]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def block_shades(cmap_name: str, n: int = 6, lo: float = 0.35, hi: float = 0.9):
    cmap = plt.colormaps[cmap_name]
    return [cmap(x) for x in np.linspace(lo, hi, n)]


def missing_pct_by_year(index: pd.DatetimeIndex, freq: str) -> pd.Series:
    """Share of expected timestamps missing, one row per calendar year the
    series covers. Both the *first* year (if the series starts mid-year,
    e.g. aFRR in Oct 2018) and the *current* (incomplete) year are capped
    at the series' own min/max timestamp, not calendar year-end -- so a
    series simply not having started yet, or not yet reaching today,
    doesn't get misread as a real gap in coverage."""
    data_min, data_max = index.min(), index.max()
    rows = {}
    for year in range(data_min.year, data_max.year + 1):
        year_start = max(pd.Timestamp(year=year, month=1, day=1), data_min)
        year_end = min(pd.Timestamp(year=year + 1, month=1, day=1), data_max + pd.Timedelta(seconds=1))
        if year_end <= year_start:
            continue
        expected = pd.date_range(year_start, year_end, freq=freq, inclusive="left")
        actual = index[(index >= year_start) & (index < year_end)]
        rows[year] = (len(expected) - actual.nunique()) / len(expected) * 100
    return pd.Series(rows)

# %% [markdown]
# ## Data

# %%
rebap = pd.read_parquet(hub_file("balancing_market", "rebap_price.parquet"))
rebap.index = pd.to_datetime(rebap.index)

# Convert to German local time for every grouping below -- see the
# timezone note above. `.tz_localize(None)` afterward keeps a plain naive
# index (now representing Europe/Berlin wall-clock, not UTC) so the rest
# of this notebook can group by .hour/.month/.year/.dayofweek directly.
rebap_local = rebap.copy()
rebap_local.index = rebap_local.index.tz_localize("UTC").tz_convert("Europe/Berlin").tz_localize(None)

fcr = pd.read_parquet(hub_file("balancing_market", "fcr_capacity_price.parquet"))
fcr.index = pd.to_datetime(fcr.index)

afrr = pd.read_parquet(hub_file("balancing_market", "afrr_capacity_price.parquet"))
afrr.index = pd.to_datetime(afrr.index)

print(f"reBAP: {len(rebap):>7,} rows  {rebap.index.min()} -> {rebap.index.max()}  (UTC)")
print(f"FCR:   {len(fcr):>7,} rows  {fcr.index.min()} -> {fcr.index.max()}  (local calendar day)")
print(f"aFRR:  {len(afrr):>7,} rows  {afrr.index.min()} -> {afrr.index.max()}  (local calendar day)")

# %% [markdown]
# ## reBAP (Ausgleichsenergiepreis)

# %% [markdown]
# ### Over time

# %%
rebap_monthly = rebap_local["rebap_eur_mwh"].resample("MS").mean()

fig, ax = plt.subplots(figsize=(13, 5))
ax.plot(rebap_monthly.index, rebap_monthly.values, color=REBAP_COLOR, linewidth=1.5)
ax.axhline(0, color=NEUTRAL, linewidth=0.8)
ax.set_ylabel("reBAP [EUR/MWh]")
ax.set_title("reBAP, monthly mean, full history")
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(paths.images_path / "07_rebap_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/07_rebap_timeseries.png
# :name: fig-07-rebap-timeseries
# reBAP, monthly mean, full history since 2014.
# ```

# %% [markdown]
# ### Block, seasonal, yearly, and weekday/weekend views

# %%
block_idx = pd.cut(rebap_local.index.hour, bins=BLOCK_EDGES, labels=BLOCK_LABELS, right=False, include_lowest=True)
month_avg = rebap_local.groupby(rebap_local.index.month)["rebap_eur_mwh"].mean().reindex(range(1, 13))
year_avg = rebap_local.groupby(rebap_local.index.year)["rebap_eur_mwh"].mean()
is_weekend = rebap_local.index.dayofweek >= 5

fig, axes = plt.subplots(2, 2, figsize=(13, 10))

box_data = [rebap_local.loc[block_idx == b, "rebap_eur_mwh"].dropna() for b in BLOCK_LABELS]
bp = axes[0, 0].boxplot(box_data, tick_labels=BLOCK_LABELS, patch_artist=True, showfliers=False, medianprops=dict(color="#0b0b0b"))
for patch, color in zip(bp["boxes"], block_shades("Purples")):
    patch.set_facecolor(color)
axes[0, 0].set_title("By time-of-day block (local time)")
axes[0, 0].set_ylabel("reBAP [EUR/MWh]")

axes[0, 1].bar(MONTH_NAMES, month_avg.values, color=REBAP_COLOR)
axes[0, 1].set_title("Average by calendar month, all years")
axes[0, 1].set_ylabel("reBAP [EUR/MWh]")

year_colors = [REBAP_COLOR if y < rebap_local.index.year.max() else "#c9a8dd" for y in year_avg.index]
axes[1, 0].bar(year_avg.index.astype(str), year_avg.values, color=year_colors)
axes[1, 0].set_title("Average by year (lightest bar = partial year)")
axes[1, 0].set_ylabel("reBAP [EUR/MWh]")
axes[1, 0].tick_params(axis="x", rotation=45)

weekday_mean = rebap_local.loc[~is_weekend, "rebap_eur_mwh"].mean()
weekend_mean = rebap_local.loc[is_weekend, "rebap_eur_mwh"].mean()
axes[1, 1].bar(["Weekday", "Weekend"], [weekday_mean, weekend_mean], color=[REBAP_COLOR, "#c9a8dd"])
axes[1, 1].set_title("Weekday vs. weekend")
axes[1, 1].set_ylabel("reBAP [EUR/MWh]")

for ax in axes.flat:
    ax.axhline(0, color=NEUTRAL, linewidth=0.6, zorder=0)
    ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
    ax.set_axisbelow(True)

fig.suptitle("reBAP -- block / seasonal / yearly / weekday patterns", fontsize=12)
fig.tight_layout()
fig.savefig(paths.images_path / "07_rebap_analysis.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/07_rebap_analysis.png
# :name: fig-07-rebap-analysis
# reBAP by time-of-day block, calendar month, calendar year, and
# weekday/weekend.
# ```

# %% [markdown]
# ## FCR (Frequency Containment Reserve / Primärregelleistung)

# %% [markdown]
# ### Over time

# %%
fcr_mean = fcr.mean(axis=1)
fcr_monthly = fcr_mean.resample("MS").mean()

fig, ax = plt.subplots(figsize=(13, 5))
ax.plot(fcr_monthly.index, fcr_monthly.values, color=FCR_COLOR, linewidth=1.5)
ax.set_ylabel("FCR settlement capacity price [EUR/MW/h]")
ax.set_title("FCR, monthly mean across all 4h blocks, full history")
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(paths.images_path / "07_fcr_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/07_fcr_timeseries.png
# :name: fig-07-fcr-timeseries
# FCR capacity price, monthly mean across all 4h blocks, full history
# since 2021.
# ```

# %% [markdown]
# ### Block, seasonal, yearly, and weekday/weekend views

# %%
fcr_long = fcr.melt(var_name="block", value_name="price", ignore_index=False)
fcr_long["block"] = fcr_long["block"].str.replace("negpos_", "").str.replace("_", "-")

month_avg = fcr_mean.groupby(fcr_mean.index.month).mean().reindex(range(1, 13))
year_avg = fcr_mean.groupby(fcr_mean.index.year).mean()
is_weekend = fcr_mean.index.dayofweek >= 5

fig, axes = plt.subplots(2, 2, figsize=(13, 10))

box_data = [fcr_long.loc[fcr_long["block"] == b, "price"].dropna() for b in BLOCK_LABELS]
bp = axes[0, 0].boxplot(box_data, tick_labels=BLOCK_LABELS, patch_artist=True, showfliers=False, medianprops=dict(color="#0b0b0b"))
for patch, color in zip(bp["boxes"], block_shades("Blues")):
    patch.set_facecolor(color)
axes[0, 0].set_title("By 4h block (German local time)")
axes[0, 0].set_ylabel("FCR price [EUR/MW/h]")

axes[0, 1].bar(MONTH_NAMES, month_avg.values, color=FCR_COLOR)
axes[0, 1].set_title("Average by calendar month, all years")
axes[0, 1].set_ylabel("FCR price [EUR/MW/h]")

year_colors = [FCR_COLOR if y < fcr_mean.index.year.max() else "#a7c6ee" for y in year_avg.index]
axes[1, 0].bar(year_avg.index.astype(str), year_avg.values, color=year_colors)
axes[1, 0].set_title("Average by year (lightest bar = partial year)")
axes[1, 0].set_ylabel("FCR price [EUR/MW/h]")
axes[1, 0].tick_params(axis="x", rotation=45)

weekday_mean = fcr_mean.loc[~is_weekend].mean()
weekend_mean = fcr_mean.loc[is_weekend].mean()
axes[1, 1].bar(["Weekday", "Weekend"], [weekday_mean, weekend_mean], color=[FCR_COLOR, "#a7c6ee"])
axes[1, 1].set_title("Weekday vs. weekend")
axes[1, 1].set_ylabel("FCR price [EUR/MW/h]")

for ax in axes.flat:
    ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
    ax.set_axisbelow(True)

fig.suptitle("FCR -- block / seasonal / yearly / weekday patterns", fontsize=12)
fig.tight_layout()
fig.savefig(paths.images_path / "07_fcr_analysis.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/07_fcr_analysis.png
# :name: fig-07-fcr-analysis
# FCR by 4h block, calendar month, calendar year, and weekday/weekend.
# ```

# %% [markdown]
# ## aFRR (automatic Frequency Restoration Reserve / Sekundärregelleistung)
#
# Shown throughout as two series -- negative (downward) and positive
# (upward) capacity -- since they're economically distinct products with
# very different price levels, not two readings of the same thing.

# %%
neg_cols = [c for c in afrr.columns if c.startswith("neg_")]
pos_cols = [c for c in afrr.columns if c.startswith("pos_")]
afrr_neg_mean = afrr[neg_cols].mean(axis=1)
afrr_pos_mean = afrr[pos_cols].mean(axis=1)

# %% [markdown]
# ### Over time

# %%
fig, ax = plt.subplots(figsize=(13, 5))
ax.plot(afrr_neg_mean.resample("MS").mean(), color=AFRR_NEG_COLOR, linewidth=1.5, label="Negative (downward)")
ax.plot(afrr_pos_mean.resample("MS").mean(), color=AFRR_POS_COLOR, linewidth=1.5, label="Positive (upward)")
ax.set_ylabel("aFRR marginal capacity price [EUR/MW/h]")
ax.set_title("aFRR, monthly mean across all 4h blocks, full history")
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
ax.legend(fontsize=9)
fig.tight_layout()
fig.savefig(paths.images_path / "07_afrr_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/07_afrr_timeseries.png
# :name: fig-07-afrr-timeseries
# aFRR negative (downward) vs. positive (upward) capacity price,
# monthly mean across all 4h blocks, full history since 2018-10.
# ```

# %% [markdown]
# ### Block, seasonal, yearly, and weekday/weekend views

# %%
afrr_long = afrr.melt(var_name="col", value_name="price", ignore_index=False)
afrr_long["direction"] = np.where(afrr_long["col"].str.startswith("neg_"), "neg", "pos")
afrr_long["block"] = afrr_long["col"].str.replace("neg_", "").str.replace("pos_", "").str.replace("_", "-")

month_avg_neg = afrr_neg_mean.groupby(afrr_neg_mean.index.month).mean().reindex(range(1, 13))
month_avg_pos = afrr_pos_mean.groupby(afrr_pos_mean.index.month).mean().reindex(range(1, 13))
year_avg_neg = afrr_neg_mean.groupby(afrr_neg_mean.index.year).mean()
year_avg_pos = afrr_pos_mean.groupby(afrr_pos_mean.index.year).mean()
is_weekend = afrr_neg_mean.index.dayofweek >= 5

fig, axes = plt.subplots(2, 2, figsize=(13, 10))

# Grouped boxplot: neg/pos pairs per block, small gap between pairs.
positions, box_data, box_colors = [], [], []
for i, b in enumerate(BLOCK_LABELS):
    for j, (direction, color) in enumerate([("neg", AFRR_NEG_COLOR), ("pos", AFRR_POS_COLOR)]):
        positions.append(i * 3 + j)
        box_data.append(afrr_long.loc[(afrr_long["block"] == b) & (afrr_long["direction"] == direction), "price"].dropna())
        box_colors.append(color)
bp = axes[0, 0].boxplot(box_data, positions=positions, widths=0.8, patch_artist=True, showfliers=False, medianprops=dict(color="#0b0b0b"))
for patch, color in zip(bp["boxes"], box_colors):
    patch.set_facecolor(color)
axes[0, 0].set_xticks([i * 3 + 0.5 for i in range(6)])
axes[0, 0].set_xticklabels(BLOCK_LABELS)
axes[0, 0].set_title("By 4h block (German local time)")
axes[0, 0].set_ylabel("aFRR price [EUR/MW/h]")

width = 0.35
x = np.arange(12)
axes[0, 1].bar(x - width / 2, month_avg_neg.values, width, color=AFRR_NEG_COLOR, label="Negative")
axes[0, 1].bar(x + width / 2, month_avg_pos.values, width, color=AFRR_POS_COLOR, label="Positive")
axes[0, 1].set_xticks(x)
axes[0, 1].set_xticklabels(MONTH_NAMES)
axes[0, 1].set_title("Average by calendar month, all years")
axes[0, 1].set_ylabel("aFRR price [EUR/MW/h]")
axes[0, 1].legend(fontsize=8)

years = year_avg_neg.index
x = np.arange(len(years))
axes[1, 0].bar(x - width / 2, year_avg_neg.values, width, color=AFRR_NEG_COLOR, label="Negative")
axes[1, 0].bar(x + width / 2, year_avg_pos.reindex(years).values, width, color=AFRR_POS_COLOR, label="Positive")
axes[1, 0].set_xticks(x)
axes[1, 0].set_xticklabels(years.astype(str), rotation=45)
axes[1, 0].set_title("Average by year")
axes[1, 0].set_ylabel("aFRR price [EUR/MW/h]")
axes[1, 0].legend(fontsize=8)

weekday_means = [afrr_neg_mean.loc[~is_weekend].mean(), afrr_pos_mean.loc[~is_weekend].mean()]
weekend_means = [afrr_neg_mean.loc[is_weekend].mean(), afrr_pos_mean.loc[is_weekend].mean()]
x = np.arange(2)
axes[1, 1].bar(x - width / 2, weekday_means, width, color=[AFRR_NEG_COLOR, AFRR_POS_COLOR], label="Weekday")
axes[1, 1].bar(x + width / 2, weekend_means, width, color=[AFRR_NEG_COLOR, AFRR_POS_COLOR], alpha=0.55, label="Weekend")
axes[1, 1].set_xticks(x)
axes[1, 1].set_xticklabels(["Negative", "Positive"])
axes[1, 1].set_title("Weekday (solid) vs. weekend (faded)")
axes[1, 1].set_ylabel("aFRR price [EUR/MW/h]")

for ax in axes.flat:
    ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
    ax.set_axisbelow(True)

fig.suptitle("aFRR -- block / seasonal / yearly / weekday patterns", fontsize=12)
fig.tight_layout()
fig.savefig(paths.images_path / "07_afrr_analysis.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/07_afrr_analysis.png
# :name: fig-07-afrr-analysis
# aFRR (negative vs. positive) by 4h block, calendar month, calendar
# year, and weekday/weekend.
# ```

# %% [markdown]
# ## How complete is each series? Missing observations by year
#
# Share of expected timestamps missing, per calendar year -- 15-min
# intervals for reBAP, calendar days for FCR/aFRR. Both a series' first
# year (if it starts mid-year, e.g. aFRR in Oct 2018) and the current year
# are capped at its own min/max timestamp rather than calendar year
# boundaries, so a series simply not having started yet -- or not yet
# reaching today -- isn't shown as mostly "missing".
#
# **reBAP is checked against its original naive-UTC index (`rebap`), not
# the German-local-time version (`rebap_local`) used everywhere else in
# this notebook.** A first version used `rebap_local` here too, and found
# an apparent 4-quarter-hour "gap" every single year, always on the same
# calendar day -- the last Sunday in March. That's not a real gap: it's
# the DST spring-forward transition, where 02:00-02:59 local time simply
# doesn't exist that day. Building the "expected" grid in naive local time
# doesn't know that and expects a uniform 96 quarter-hours anyway, so it
# flags four slots that were never supposed to exist as "missing". Checked
# against the real, physical, DST-immune UTC grid instead, reBAP is 100%
# complete in every year (matching the hub's own `rebap_gap_check`, which
# already does exactly this).

# %%
rebap_missing = missing_pct_by_year(rebap.index, "15min")
fcr_missing = missing_pct_by_year(fcr.index, "D")
afrr_missing = missing_pct_by_year(afrr.index, "D")

print("Missing share by year (%):")
print(pd.DataFrame({"reBAP": rebap_missing, "FCR": fcr_missing, "aFRR": afrr_missing}).round(2).to_string())

all_years = sorted(set(rebap_missing.index) | set(fcr_missing.index) | set(afrr_missing.index))
x = np.arange(len(all_years))
width = 0.25

fig, ax = plt.subplots(figsize=(13, 5.5))
ax.bar(x - width, rebap_missing.reindex(all_years).values, width, color=REBAP_COLOR, label="reBAP (15-min)")
ax.bar(x, fcr_missing.reindex(all_years).values, width, color=FCR_COLOR, label="FCR (daily)")
ax.bar(x + width, afrr_missing.reindex(all_years).values, width, color=AFRR_NEG_COLOR, label="aFRR (daily)")
ax.set_xticks(x)
ax.set_xticklabels([str(y) for y in all_years], rotation=45)
ax.set_ylabel("Missing [% of expected observations]")
ax.set_title("Data completeness by year (partial start/current year capped at each series' own coverage)")
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
ax.legend(fontsize=9)
fig.tight_layout()
fig.savefig(paths.images_path / "07_missing_observations.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/07_missing_observations.png
# :name: fig-07-missing-observations
# Share of expected timestamps missing, per calendar year, for each of
# the three series.
# ```

# %% [markdown]
# reBAP and aFRR are 100% complete in every year. FCR has exactly one
# missing day in its entire history -- 2021-10-03 (German Unity Day) --
# 0.27% of that one year, visible as the only non-zero bar above; every
# other FCR year is also 100% complete (see `energy-data-hub` README's
# "Known data-quality caveats" for the source-side confirmation). No
# unexplained gaps anywhere.

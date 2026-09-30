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
# # RE buildout + battery storage vs. a constant demand baseline, 1980-2025
#
# `energy-insights`' [`09_re_buildout_battery_residual_load`](../../energy-insights/book/notebooks/09_re_buildout_battery_residual_load.ipynb)
# runs a buildout-multiplier + battery-size sweep against **real, hourly
# SMARD demand**, but only over the ~7 years (since 2018-10) that SMARD's
# DE-LU load series is considered reliable. The hub's "simple" PECD
# capacity-factor product for Germany (`pecd_country_capacity_factors_simple_de.parquet`
# — the same plain, non-MaStR-weighted area/technology-mix average `09`
# uses) actually goes back to **1980**, i.e. 46 years of weather variability
# rather than 7 — but there's no matching 46-year hourly demand series to
# pair it with.
#
# This notebook redoes `09`'s exact analysis — same buildout multipliers,
# same battery scenarios, same decomposition into direct use / curtailed /
# residual load — but swaps its real hourly demand for a single **constant**
# reference instead: the mean of 2025's daily peak SMARD loads (61.5 GW,
# built and visualized in the section below). That trades away real demand's
# own weather/weekday/seasonal shape, but in exchange unlocks the full
# 46-year PECD weather record rather than SMARD's 7-year window — a
# different, complementary way to ask "does this result hold up across more
# weather years," isolating supply-side weather variability from
# demand-side variability entirely.
#
# **What this does *not* model:** transmission constraints, other
# flexibility (demand response, hydro, interconnectors), a multi-technology
# battery/gas cost trade-off, or demand's own year-to-year growth/shape — see
# `09` for the shorter, real-demand picture, and `world-of-energy`'s `54` for
# a full cost-optimised dispatch.

# %%
from datetime import timezone

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from astral import LocationInfo
from astral.sun import sun

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

# Reference palette (energy-platform house style, see energy-insights'
# notebooks): fixed categorical hues, never cycled.
BLUE = "#2a78d6"           # wind onshore / direct RE use / the hourly demand line
YELLOW = "#eda100"         # solar (both variants)
AQUA = "#1baf7a"           # wind offshore / delivered-via-battery
RED = "#e34948"            # curtailed (wasted)
NEUTRAL = "#898781"        # reference lines / residual load / non-data ink

MULTIPLIERS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
BATTERY_COLORS = {
    "No battery": "#a9a8a2",
    "4h battery": "#9ec5f4",
    "24h battery": "#3987e5",
    "168h battery": "#0d366b",
}

# %% [markdown]
# ## Data
#
# DE capacity factors (`pecd_country_capacity_factors_simple_de`, 1980-2025,
# hourly, UTC), real hourly demand (`smard_load`, used only to build the
# *constant* 2025 reference below, not as a time series to simulate
# against), and today's installed capacity (`capacity_by_region_year`,
# latest year-end snapshot).

# %%
cf = pd.read_parquet(hub_file("pecd", "pecd_country_capacity_factors_simple_de.parquet"))
cf.index = pd.to_datetime(cf.index).tz_localize("UTC")

load = pd.read_parquet(hub_file("smard", "load.parquet"))["total_load"]
load.index = pd.to_datetime(load.index)

print(f"PECD capacity-factor record: {cf.index.min()} -> {cf.index.max()}  ({len(cf):,} hours)")
print(f"SMARD load record:           {load.index.min()} -> {load.index.max()}  ({len(load):,} hours)")

# %% [markdown]
# ## A constant, realistic demand reference: mean of 2025's daily peaks
#
# Rather than an hourly demand series, this notebook uses one constant
# number throughout: the average across 2025's 365 daily *peak* loads (not
# the average of hourly demand itself, which would understate what the grid
# actually has to be able to serve at any given hour). That single value
# then stands in for demand in **every one of the 46 years** of PECD weather
# data below — the weather varies year to year, demand does not.

# %%
load_2025 = load.loc["2025"]
daily_peak_2025 = load_2025.resample("D").max()
constant_demand_mw = daily_peak_2025.mean()
avg_demand_mw = constant_demand_mw

print(f"2025 mean hourly demand:        {load_2025.mean() / 1000:.1f} GW")
print(f"2025 mean of daily peak demand: {constant_demand_mw / 1000:.1f} GW  <- used as demand throughout")
print(f"2025 single highest hour:       {load_2025.max() / 1000:.1f} GW")

# %% [markdown]
# ### The constant reference against 2025's actual hourly demand

# %%
fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(load_2025.index, load_2025.values / 1000, linewidth=0.6, color=BLUE, label="Hourly demand (2025)")
ax.axhline(constant_demand_mw / 1000, color=NEUTRAL, linewidth=1.5, linestyle="--", zorder=3)
ax.text(
    load_2025.index.max(), constant_demand_mw / 1000,
    f" = mean daily peak ({constant_demand_mw / 1000:.1f} GW)",
    color=NEUTRAL, fontsize=9, va="bottom", ha="right",
    bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1.5),
)
ax.set_xlabel("2025")
ax.set_ylabel("Demand [GW]")
ax.set_title("Constant demand reference vs. real hourly demand, 2025")
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(paths.images_path / "05_demand_2025_vs_constant_peak.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/05_demand_2025_vs_constant_peak.png
# :name: fig-05-demand-2025-vs-constant-peak
# 2025's real hourly SMARD demand (blue) against the constant reference used
# throughout the rest of this notebook: the mean of 2025's 365 daily peak
# loads (dashed gray). The constant line sits above most hours by
# construction — it tracks peak days, not the average hour — but still
# below 2025's single highest hour.
# ```

# %% [markdown]
# ## Today's fleet and battery sizes, in context
#
# Before running any buildout/battery sweep, three numbers worth having
# side by side: today's actual installed RE capacity, how the battery
# scenarios below are sized, and how all of that compares in scale to the
# constant demand reference just introduced.

# %% [markdown]
# ### Today's installed capacity
#
# Same source and method as `09`: latest year-end snapshot from
# `capacity_by_region_year`, offshore identified by region code prefix
# `DEZZ`.

# %%
capacity_annual = pd.read_parquet(hub_file("capacity", "capacity_by_region_year.parquet"))
is_offshore = capacity_annual["region_code"].str.startswith("DEZZ")
latest_year = capacity_annual["year"].max()
latest = capacity_annual[capacity_annual["year"] == latest_year]

CURRENT_CAPACITY_MW = {
    "solar": latest.loc[latest["technology"] == "solar", "capacity_mw"].sum(),
    "wind_onshore": latest.loc[(latest["technology"] == "wind") & ~is_offshore.reindex(latest.index, fill_value=False), "capacity_mw"].sum(),
    "wind_offshore": latest.loc[(latest["technology"] == "wind") & is_offshore.reindex(latest.index, fill_value=False), "capacity_mw"].sum(),
}
total_current_gw = sum(CURRENT_CAPACITY_MW.values()) / 1000

print(f"Current installed capacity ({latest_year} snapshot):")
for tech, mw in CURRENT_CAPACITY_MW.items():
    print(f"  {tech:15s}  {mw / 1000:6.1f} GW")
print(f"  {'total':15s}  {total_current_gw:6.1f} GW")


TECHS = ["solar", "wind_onshore", "wind_offshore"]


def re_generation(buildout_multiplier: float) -> np.ndarray:
    return sum(cf[t].values * CURRENT_CAPACITY_MW[t] * buildout_multiplier for t in TECHS)


demand = np.full(len(cf), constant_demand_mw)

# %% [markdown]
# ### Battery scenarios
#
# Same battery model as `09`: unlimited charge/discharge power, sized purely
# by energy capacity as `N` hours of (now constant) average demand, 90%
# round-trip efficiency split via `sqrt`.

# %%
BATTERY_ROUND_TRIP_EFFICIENCY = 0.90
EFF = np.sqrt(BATTERY_ROUND_TRIP_EFFICIENCY)

BATTERY_SCENARIOS = {"No battery": 0.0, "4h battery": 4.0, "24h battery": 24.0, "168h battery": 168.0}

print("Battery scenarios (unlimited power; energy capacity = N hours of constant demand):")
for label, duration_h in BATTERY_SCENARIOS.items():
    cap_gwh = duration_h * avg_demand_mw / 1000
    print(f"  {label:14s}  {duration_h:5.0f} h of demand   {cap_gwh:9,.0f} GWh  ({cap_gwh / 1000:.2f} TWh)")

# %% [markdown]
# ### A quick scale check
#
# Consumption, battery sizes, and installed capacity all just got
# introduced separately above -- easy to lose a feel for how big any of
# these numbers actually are relative to each other. One more bar chart,
# purely for orders of magnitude, no simulation involved: average
# consumption (GW, a power quantity) next to a 1h and a 4h battery (GWh, an
# energy quantity) next to today's total installed RE capacity (GW again).
# GW and GWh are deliberately placed on the same axis here -- a battery
# sized at "N hours of average demand" has a GWh capacity that is, by
# construction, the same number as N times the GW consumption figure, so
# the bars are directly comparable in scale even though the units differ.

# %%
SCALE_CHECK_LABELS = ["Avg.\nconsumption\n(GW)", "1h battery\n(GWh)", "4h battery\n(GWh)", "Installed RE\ncapacity (GW)"]
scale_check_simple_values = [
    avg_demand_mw / 1000,
    1.0 * avg_demand_mw / 1000,
    BATTERY_SCENARIOS["4h battery"] * avg_demand_mw / 1000,
]
scale_check_simple_colors = [NEUTRAL, "#cfe3fa", BATTERY_COLORS["4h battery"]]

fig, ax = plt.subplots(figsize=(8, 6))
x = np.arange(len(SCALE_CHECK_LABELS))
width = 0.6

bars = ax.bar(x[:3], scale_check_simple_values, width, color=scale_check_simple_colors, edgecolor="white", linewidth=0.5)
for bar, value in zip(bars, scale_check_simple_values):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2, f"{value:,.0f}", ha="center", va="bottom", fontsize=10)

install_bottom = 0.0
for tech, color, tech_label in [("solar", YELLOW, "Solar"), ("wind_onshore", BLUE, "Wind onshore"), ("wind_offshore", AQUA, "Wind offshore")]:
    value_gw = CURRENT_CAPACITY_MW[tech] / 1000
    ax.bar(x[3], value_gw, width, bottom=install_bottom, color=color, edgecolor="white", linewidth=0.5, label=tech_label)
    install_bottom += value_gw
ax.text(x[3], install_bottom + 2, f"{install_bottom:,.0f}", ha="center", va="bottom", fontsize=10)

ax.set_xticks(x)
ax.set_xticklabels(SCALE_CHECK_LABELS)
ax.set_ylabel("GW (power) or GWh (energy) -- see caption")
ax.set_title("Orders of magnitude: consumption, battery sizes, installed capacity (today)")
ax.set_ylim(0, install_bottom * 1.2)
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
ax.legend(fontsize=9, loc="upper left")
fig.tight_layout()
fig.savefig(paths.images_path / "05_scale_check_bars.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/05_scale_check_bars.png
# :name: fig-05-scale-check-bars
# Average consumption (GW), a 1h and a 4h battery's energy capacity (GWh),
# and today's total installed RE capacity (GW, stacked by technology).
# Today's fleet is already ~3x average demand in nameplate GW -- but with
# solar's ~11% and wind's ~24-43% capacity factors (see the capacity-factor
# bar chart below), that nameplate figure doesn't translate directly into
# average output. A 4h battery, at ~246 GWh, is a small fraction of a single
# day's ~1,475 GWh of demand -- context for why the sweep below needs
# 24h/168h batteries before storage alone can meaningfully close the gap.
# ```

# %%
def simulate(buildout_multiplier: float, duration_h: float) -> dict[str, np.ndarray]:
    """Hourly (generation, direct, delivered, curtailed, residual) arrays for one scenario."""
    gen = re_generation(buildout_multiplier)
    cap_mwh = duration_h * avg_demand_mw

    n = len(gen)
    soc = 0.0
    residual = np.empty(n)
    curtailed = np.empty(n)
    delivered = np.empty(n)
    for i in range(n):
        net = gen[i] - demand[i]
        if net > 0:
            can_take = min(net, (cap_mwh - soc) / EFF) if cap_mwh > 0 else 0.0
            soc += can_take * EFF
            curtailed[i] = net - can_take
            residual[i] = 0.0
            delivered[i] = 0.0
        else:
            deficit = -net
            can_give = min(deficit / EFF, soc) if cap_mwh > 0 else 0.0
            soc -= can_give
            delivered[i] = can_give * EFF
            residual[i] = deficit - delivered[i]
            curtailed[i] = 0.0

    return {
        "gen": gen,
        "direct": np.minimum(gen, demand),
        "delivered": delivered,
        "curtailed": curtailed,
        "residual": residual,
    }

# %% [markdown]
# ## Average capacity factors by technology, full 1980-2025 record
#
# Simple hourly mean of each technology's capacity factor over the full
# 46-year PECD record — the long-run counterpart to `09`'s ~7-year figures.

# %%
mean_cf_all_hours = {tech: cf[tech].mean() for tech in TECHS}

for tech, value in mean_cf_all_hours.items():
    print(f"{tech:15s}  mean CF (all hours, 1980-2025): {value:.1%}")

# %% [markdown]
# ## PV over potential sunshine hours only
#
# Averaging solar's capacity factor over *all* hours (including every night)
# mixes a real physical ceiling (PV cannot produce after dark, so half its
# hours are structural zeros) into what looks like a "poor" capacity factor.
# To separate that from actual daytime performance, this recomputes solar's
# mean capacity factor restricted to hours that fall within Berlin's
# sunrise-sunset window on each day — using `astral` for the sun geometry
# (52.52°N, 13.405°E), computed directly in UTC to match PECD's own hourly
# UTC timestamps (verified against the raw data: on 2025-06-21, PECD's
# nonzero solar hours start around 02:00-03:00 UTC, matching Berlin's ~02:43
# UTC sunrise that day).
#
# An hour is counted as a "potential sunshine hour" if its midpoint (`HH:30`)
# falls between that day's sunrise and sunset — a simple, symmetric rule for
# assigning each hourly bucket to day or night.

# %%
BERLIN = LocationInfo("Berlin", "Germany", "UTC", 52.52, 13.405)

unique_dates = pd.Series(cf.index.normalize().unique())
sun_times = pd.DataFrame(
    [
        {"date": d, "sunrise": sun(BERLIN.observer, date=d.date(), tzinfo=timezone.utc)["sunrise"],
         "sunset": sun(BERLIN.observer, date=d.date(), tzinfo=timezone.utc)["sunset"]}
        for d in unique_dates
    ]
).set_index("date")

hour_date = cf.index.normalize()
sunrise = pd.DatetimeIndex(sun_times.loc[hour_date, "sunrise"])
sunset = pd.DatetimeIndex(sun_times.loc[hour_date, "sunset"])
hour_midpoint = cf.index + pd.Timedelta(minutes=30)

is_daylight = (hour_midpoint >= sunrise) & (hour_midpoint <= sunset)
print(f"Potential sunshine hours: {is_daylight.sum():,} of {len(cf):,} ({is_daylight.mean():.1%})")

mean_cf_solar_daylight = cf.loc[is_daylight, "solar"].mean()
print(f"solar            mean CF (all hours):       {mean_cf_all_hours['solar']:.1%}")
print(f"solar            mean CF (daylight only):   {mean_cf_solar_daylight:.1%}")

# %% [markdown]
# ## Average capacity factors, by technology

# %%
bar_labels = ["Solar\n(all hours)", "Solar\n(daylight only)", "Wind onshore", "Wind offshore"]
bar_values = [
    mean_cf_all_hours["solar"],
    mean_cf_solar_daylight,
    mean_cf_all_hours["wind_onshore"],
    mean_cf_all_hours["wind_offshore"],
]
bar_colors = [YELLOW, YELLOW, BLUE, AQUA]
bar_hatches = ["", "///", "", ""]

fig, ax = plt.subplots(figsize=(8, 5.5))
x = np.arange(len(bar_labels))
bars = ax.bar(x, [v * 100 for v in bar_values], width=0.6, color=bar_colors, edgecolor="white", linewidth=0.5)
for bar, hatch in zip(bars, bar_hatches):
    bar.set_hatch(hatch)

for bar, value in zip(bars, bar_values):
    ax.text(
        bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.6,
        f"{value:.1%}", ha="center", va="bottom", fontsize=10, color="#0b0b0b",
    )

ax.set_xticks(x)
ax.set_xticklabels(bar_labels)
ax.set_ylabel("Average capacity factor [%]")
ax.set_title("Average capacity factor by technology (DE, 1980-2025)")
ax.set_ylim(0, max(bar_values) * 100 * 1.25)
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(paths.images_path / "05_pecd_de_capacity_factors_bar.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/05_pecd_de_capacity_factors_bar.png
# :name: fig-05-pecd-de-capacity-factors-bar
# Average capacity factor per technology, full 1980-2025 PECD "simple"
# record for Germany. Solar's daylight-only bar (hatched) restricts the
# average to hours within Berlin's sunrise-sunset window, removing the
# structural zeros from every night.
# ```

# %% [markdown]
# ## RE buildout alone, no storage
#
# Same four numbers per hour as `09`, by construction:
#
# - `direct use = min(generation, demand)`
# - `curtailed = max(generation - demand, 0)`
# - `residual load = max(demand - generation, 0)`
# - always: `direct use + residual load = demand`, and `direct use + curtailed = generation`
#
# Averaged over the full 46-year record, with demand held constant at 61.5 GW.

# %%
baseline_rows = []
for multiplier in MULTIPLIERS:
    gen = re_generation(multiplier)
    direct = np.minimum(gen, demand)
    curtailed = np.maximum(gen - demand, 0.0)
    residual = np.maximum(demand - gen, 0.0)
    baseline_rows.append({
        "multiplier": multiplier,
        "avg_demand_gw": demand.mean() / 1000,
        "avg_generated_gw": gen.mean() / 1000,
        "avg_direct_use_gw": direct.mean() / 1000,
        "avg_curtailed_gw": curtailed.mean() / 1000,
        "avg_residual_gw": residual.mean() / 1000,
        "curtailed_pct_of_generated": curtailed.mean() / gen.mean(),
        "residual_pct_of_demand": residual.mean() / demand.mean(),
    })

baseline = pd.DataFrame(baseline_rows)
pd.set_option("display.float_format", lambda v: f"{v:.2f}")
print(baseline.to_string(index=False))

# %%
fig, ax = plt.subplots(figsize=(10, 6))
x = np.arange(len(MULTIPLIERS))
width = 0.6

ax.bar(x, baseline["avg_direct_use_gw"], width, color=BLUE, label="Direct RE use")
ax.bar(x, baseline["avg_residual_gw"], width, bottom=baseline["avg_direct_use_gw"], color=NEUTRAL, label="Residual load (gas/import)")
ax.bar(x, baseline["avg_curtailed_gw"], width, bottom=baseline["avg_demand_gw"], color=RED, alpha=0.75, label="Curtailed (wasted)")

ax.axhline(avg_demand_mw / 1000, color="#0b0b0b", linewidth=1, linestyle="--", zorder=0)
ax.text(len(MULTIPLIERS) - 0.3, avg_demand_mw / 1000, " = constant demand", va="bottom", ha="right", fontsize=8)

ax.set_xticks(x)
ax.set_xticklabels([f"{m:g}x" for m in MULTIPLIERS])
ax.set_xlabel("RE buildout multiplier (x today's fleet)")
ax.set_ylabel("Average power [GW]")
ax.set_title("No battery: what happens to demand as RE buildout grows (1980-2025, constant demand)")
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
ax.legend(fontsize=9, loc="upper left")
fig.tight_layout()
fig.savefig(paths.images_path / "05_buildout_no_battery_bars.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/05_buildout_no_battery_bars.png
# :name: fig-05-buildout-no-battery-bars
# Direct RE use, residual load, and curtailment as RE buildout scales up,
# no battery, full 1980-2025 weather record against the constant demand
# reference.
# ```

# %% [markdown]
# ## Adding a battery: where the extra energy goes, at 2x buildout
#
# Same battery model introduced above. At one fixed buildout level (2x),
# how does the surplus/deficit split between direct use, battery-delivered,
# still-curtailed, and still-residual, as battery size grows?

# %%
DEMO_MULTIPLIER = 2.0

decomposition_rows = []
for label, duration_h in BATTERY_SCENARIOS.items():
    r = simulate(DEMO_MULTIPLIER, duration_h)
    decomposition_rows.append({
        "battery": label,
        "direct_gw": r["direct"].mean() / 1000,
        "delivered_gw": r["delivered"].mean() / 1000,
        "curtailed_gw": r["curtailed"].mean() / 1000,
        "residual_gw": r["residual"].mean() / 1000,
    })
decomposition = pd.DataFrame(decomposition_rows)
print(f"Decomposition at {DEMO_MULTIPLIER:g}x buildout (GW, averaged over 1980-2025):")
print(decomposition.to_string(index=False))

fig, ax = plt.subplots(figsize=(8, 6))
x = np.arange(len(decomposition))
width = 0.55

bottom = np.zeros(len(decomposition))
for col, color, label in [
    ("direct_gw", BLUE, "Direct RE use"),
    ("delivered_gw", AQUA, "Delivered via battery"),
    ("residual_gw", NEUTRAL, "Residual load (gas/import)"),
]:
    ax.bar(x, decomposition[col], width, bottom=bottom, color=color, label=label)
    bottom += decomposition[col].values
ax.bar(x, decomposition["curtailed_gw"], width, bottom=bottom, color=RED, alpha=0.75, label="Still curtailed (wasted)")

ax.axhline(avg_demand_mw / 1000, color="#0b0b0b", linewidth=1, linestyle="--", zorder=0)
ax.set_xticks(x)
ax.set_xticklabels(decomposition["battery"])
ax.set_xlabel("Battery size")
ax.set_ylabel("Average power [GW]")
ax.set_title(f"Storage's marginal value at {DEMO_MULTIPLIER:g}x buildout (1980-2025, constant demand)")
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
ax.legend(fontsize=9, loc="upper left")
fig.tight_layout()
fig.savefig(paths.images_path / "05_battery_decomposition_2x.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/05_battery_decomposition_2x.png
# :name: fig-05-battery-decomposition-2x
# At 2x buildout, how the surplus/deficit splits between direct use,
# battery-delivered, still-curtailed, and still-residual, by battery size.
# ```

# %% [markdown]
# ## Average renewable share and curtailment, with batteries

# %%
share_rows = []
for multiplier in MULTIPLIERS:
    for label, duration_h in BATTERY_SCENARIOS.items():
        r = simulate(multiplier, duration_h)
        share_rows.append({
            "multiplier": multiplier,
            "battery": label,
            "avg_re_share": 1 - r["residual"].mean() / avg_demand_mw,
            "curtailment_share": r["curtailed"].sum() / r["gen"].sum(),
            "peak_residual_frac": r["residual"].max() / avg_demand_mw,
            "battery_capacity_twh": duration_h * avg_demand_mw / 1e6,
        })
results = pd.DataFrame(share_rows)

fig, (ax_share, ax_curt) = plt.subplots(1, 2, figsize=(13, 5.5), sharex=True)
for label in BATTERY_SCENARIOS:
    sub = results[results["battery"] == label].sort_values("multiplier")
    ax_share.plot(sub["multiplier"], sub["avg_re_share"] * 100, marker="o", markersize=4,
                  linewidth=1.8, color=BATTERY_COLORS[label], label=label)
    ax_curt.plot(sub["multiplier"], sub["curtailment_share"] * 100, marker="o", markersize=4,
                 linewidth=1.8, color=BATTERY_COLORS[label], label=label)

for target, style in [(90, "--"), (95, ":")]:
    ax_share.axhline(target, color=NEUTRAL, linewidth=1, linestyle=style, zorder=0)
    ax_share.text(MULTIPLIERS[-1], target, f" {target}%", color=NEUTRAL, fontsize=8, va="center")

ax_share.set_ylabel("Average RE + battery share of demand [%]")
ax_share.set_xlabel("RE buildout multiplier (x today's fleet)")
ax_share.set_title("How much of demand gets covered, on average")
ax_share.set_ylim(50, 101)
ax_share.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax_share.set_axisbelow(True)
ax_share.legend(fontsize=8, loc="lower right")

ax_curt.set_ylabel("Curtailed share of RE production [%]")
ax_curt.set_xlabel("RE buildout multiplier (x today's fleet)")
ax_curt.set_title("...and how much of it still gets thrown away")
ax_curt.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax_curt.set_axisbelow(True)
ax_curt.legend(fontsize=8, loc="upper left")

fig.suptitle("RE + battery coverage and curtailment, full 1980-2025 weather record, constant demand")
fig.tight_layout()
fig.savefig(paths.images_path / "05_re_share_and_curtailment.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/05_re_share_and_curtailment.png
# :name: fig-05-re-share-and-curtailment
# Left: average share of (constant) demand covered by RE + battery, by
# buildout multiplier and battery size. Right: the matching curtailed share
# of RE production.
# ```

# %% [markdown]
# ### Average residual load, buildout x battery duration
#
# The chart above only samples four battery sizes (`No battery`, `4h`,
# `24h`, `168h`) against the full `MULTIPLIERS` list. Zooming into the
# range where most near-term buildout/battery decisions would actually
# land -- buildout up to 5x today's fleet, battery duration up to 4h --
# and filling in a finer grid on both axes shows how average residual load
# moves as a smooth surface rather than at four scattered points.

# %%
HEATMAP_MULTIPLIERS = np.arange(1.0, 5.01, 0.5)
HEATMAP_BATTERY_HOURS = np.arange(0.0, 4.01, 1.0)

residual_heatmap_gw = np.array([
    [simulate(multiplier, duration_h)["residual"].mean() / 1000 for multiplier in HEATMAP_MULTIPLIERS]
    for duration_h in HEATMAP_BATTERY_HOURS
])

fig, ax = plt.subplots(figsize=(10, 5.5))
# "RdYlGn_r" (reversed): high residual load (bad, more backup needed) ->
# red; low residual load (good) -> green. Note this is a 3-hue "traffic
# light" map, not a single-hue sequential ramp -- a deliberate deviation
# from the house style's usual single-hue magnitude encoding, requested
# specifically for this chart's intuitive good/bad reading. Not colorblind
# -safe the way a single-hue ramp is; the cell-value labels below carry the
# actual reading regardless of color perception.
im = ax.imshow(residual_heatmap_gw, origin="lower", cmap="RdYlGn_r", aspect="auto")

ax.set_xticks(np.arange(len(HEATMAP_MULTIPLIERS)))
ax.set_xticklabels([f"{m:g}x" for m in HEATMAP_MULTIPLIERS])
ax.set_yticks(np.arange(len(HEATMAP_BATTERY_HOURS)))
ax.set_yticklabels([f"{h:g}h" for h in HEATMAP_BATTERY_HOURS])
ax.set_xlabel("RE buildout multiplier (x today's fleet)")
ax.set_ylabel("Battery duration")
ax.set_title("Average residual load [GW] (1980-2025, constant demand)")

# Text color per cell from the actual rendered color's perceptual
# luminance, not just "value > midpoint" -- RdYlGn_r's green and red ends
# are both dark enough to need white text, while its yellow middle needs
# dark text, so a simple high/low split would get the middle wrong.
for i in range(residual_heatmap_gw.shape[0]):
    for j in range(residual_heatmap_gw.shape[1]):
        value = residual_heatmap_gw[i, j]
        r, g, b, _ = im.cmap(im.norm(value))
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        text_color = "white" if luminance < 0.6 else "#3a2a26"
        ax.text(j, i, f"{value:.1f}", ha="center", va="center", fontsize=8, color=text_color)

fig.colorbar(im, ax=ax, label="Average residual load [GW]", fraction=0.046, pad=0.04)
fig.tight_layout()
fig.savefig(paths.images_path / "05_residual_load_heatmap.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/05_residual_load_heatmap.png
# :name: fig-05-residual-load-heatmap
# Average residual load (GW) across a finer buildout x battery-duration
# grid than the four-scenario chart above, restricted to the 1x-5x /
# 0h-4h range. Reading down any column: within this narrow 0-4h range, a
# battery still buys comparatively little -- most of the improvement
# visible here comes from moving right (more buildout), not down (a
# bigger, but still short-duration, battery). The bigger batteries (24h,
# 168h) needed to close the picture further live outside this grid, in the
# four-scenario chart above.
# ```

# %% [markdown]
# ## Does storage's marginal value hold up across the whole buildout range?

# %%
delivered_rows = []
for multiplier in MULTIPLIERS:
    row = {"multiplier": multiplier}
    for label, duration_h in BATTERY_SCENARIOS.items():
        if duration_h == 0:
            continue
        row[label] = simulate(multiplier, duration_h)["delivered"].mean() / 1000
    delivered_rows.append(row)
delivered_df = pd.DataFrame(delivered_rows)

fig, ax = plt.subplots(figsize=(9, 5.5))
for label in ["4h battery", "24h battery", "168h battery"]:
    ax.plot(delivered_df["multiplier"], delivered_df[label], marker="o", markersize=4,
            linewidth=1.8, color=BATTERY_COLORS[label], label=label)
ax.set_xlabel("RE buildout multiplier (x today's fleet)")
ax.set_ylabel("Average energy delivered from storage [GW]")
ax.set_title("Storage's average contribution peaks, then fades (1980-2025, constant demand)")
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
ax.legend(fontsize=9, loc="upper right")
fig.tight_layout()
fig.savefig(paths.images_path / "05_battery_delivered_vs_multiplier.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/05_battery_delivered_vs_multiplier.png
# :name: fig-05-battery-delivered-vs-multiplier
# Average energy delivered from storage across the buildout range, one line
# per battery size.
# ```

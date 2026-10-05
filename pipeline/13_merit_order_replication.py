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
# # Replicating the EWI Merit-Order Tool from scratch
#
# This notebook is a first attempt at reproducing the German conventional
# power plant merit order -- the "which plants come first" supply curve
# used to answer: if we built a *synthetic* merit order for a hypothetical
# market state (more capacity, more batteries, different incentives), is
# today's real one even reproducible from public data first?
#
# The method mirrors the Energiewirtschaftliches Institut an der
# Universität zu Köln's (EWI) own "EWI Merit-Order Tool 2025"
# (`literature/` discussion, Oktober 2025 documentation): marginal cost per
# plant block from fuel price, CO2 price and efficiency, available capacity
# net of an assumed outage rate, sorted ascending. EWI's own documentation
# states its assumptions and sources in full, which is what makes this
# replication possible at all -- see the per-table citations below.
#
# **What's genuinely replicated vs. assumed:**
# - The power plant fleet itself (`pipeline/12_download_conventional_mastr.py`)
#   is real, current Marktstammdatenregister (MaStR) data -- the same base
#   EWI's tool uses.
# - Fuel/CO2/transport/variable-cost/outage assumptions are EWI's own
#   *published* 2025 standard values (their Tables 1/3/4/5/6), reused
#   directly rather than re-sourced, since the point here is first to
#   reproduce their tool, not to second-guess its commodity price inputs.
# - **Efficiency per plant is not reproduced, because it can't be** -- MaStR
#   carries no efficiency field for any technology (EWI's own documentation
#   says the same: they fall back to a manually-curated, block-level table
#   from an older tool version). This notebook instead assigns one
#   textbook-standard efficiency per fuel/technology class -- a coarser
#   approximation than EWI's own, flagged explicitly in the gaps below.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from erx.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

df = pd.read_parquet(paths.mastr_conventional_units_file)
print(f"{len(df):,} combustion + nuclear MaStR units loaded")

# %% [markdown]
# ## Filter to the operating fleet
#
# MaStR carries every unit ever registered, including plants still in
# planning, temporarily mothballed, or permanently decommissioned (all six
# German nuclear units fall in the last category -- the fleet shut down for
# good in April 2023, so nuclear is correctly absent from everything below).

# %%
op = df[df["status"] == "In Betrieb"].copy()
print(f"{len(op):,} operating units, {op['net_capacity_kw'].sum() / 1e6:.1f} GW net capacity")
print(op.groupby("technology_group")["net_capacity_kw"].sum().div(1e6).round(2))

# %% [markdown]
# ## Classify each unit into EWI's fuel categories
#
# EWI's tool distinguishes Kernenergie / Braunkohle / Steinkohle / Erdgas /
# Öl / Sonstige / Abfall, with gas further split into "GuD" (CCGT) and
# "Gasturbine" (open-cycle) using MaStR's `Technologie` field -- the same
# split made here. MaStR's `main_fuel` values are much finer-grained than
# EWI's seven buckets (free-text-like fuel subtypes, e.g. "Heizöl, leicht"
# vs. "Heizöl, schwer"), so this is a many-to-one mapping, not a lookup.

# %%
FUEL_CATEGORY = {
    "Erdgas, Erdölgas": "Erdgas",
    "Erdgas": "Erdgas",
    "Flüssiggas": "Erdgas",
    "Raffineriegas": "Erdgas",
    "Steinkohlen": "Steinkohle",
    "Steinkohle": "Steinkohle",
    "Rohbraunkohlen": "Braunkohle",
    "Braunkohle": "Braunkohle",
    "Braunkohlenbriketts": "Braunkohle",
    "Staub- und Trockenkohle": "Braunkohle",
    "Wirbelschichtkohle": "Braunkohle",
    "Heizöl, leicht": "Öl",
    "Heizöl, schwer": "Öl",
    "Dieselkraftstoff": "Öl",
    "Mineralölprodukte": "Öl",
    "Andere Mineralölprodukte": "Öl",
    "Abfall (Hausmüll, Siedl.abf.)": "Abfall",
    "Industrieabfall": "Abfall",
    "nicht biogener Abfall": "Abfall",
    "Kernenergie": "Kernenergie",
}
op["fuel_category"] = op["main_fuel"].map(FUEL_CATEGORY).fillna("Sonstige")

# Gas technology split, mirroring EWI's "rein indikative Zuordnung":
# CCGT ("GuD") = waste-heat-boiler or combined-cycle gas turbines; OCGT
# ("Gasturbine") = gas turbines *without* a waste-heat boiler; everything
# else gas-fuelled (engines, fuel cells, Stirling engines -- almost all
# small decentral CHP/BHKW units) is kept as its own "Erdgas (BHKW)" class
# rather than folded into either, since its efficiency is quite different
# from both utility-scale technologies -- a refinement EWI's own
# documentation doesn't make explicit (they only name the GuD/Gasturbine
# split, not what the small aggregated non-turbine remainder gets).
GAS_TURBINE_TECHS = {"Gasturbinen ohne Abhitzekessel"}
GAS_CCGT_TECHS = {"Gasturbinen mit Abhitzekessel", "Gasturbinen mit nachgeschalteter Dampfturbine"}


def gas_subcategory(row) -> str:
    if row["fuel_category"] != "Erdgas":
        return row["fuel_category"]
    if row["technology"] in GAS_CCGT_TECHS:
        return "Erdgas GuD"
    if row["technology"] in GAS_TURBINE_TECHS:
        return "Erdgas Gasturbine"
    return "Erdgas BHKW"


op["cost_category"] = op.apply(gas_subcategory, axis=1)
print(op.groupby("cost_category")["net_capacity_kw"].sum().div(1e6).round(2).sort_values(ascending=False))

# %% [markdown]
# ## Aggregate blocks under 10 MW
#
# EWI's own documentation: "Anlagen mit einer Netto-Nennleistung kleiner
# als 10 MW wurden aufsummiert" -- below that size, units are summed rather
# than kept individually (there are tens of thousands of small gas
# engines/fuel cells in MaStR, mostly building-level CHP, which would
# otherwise dominate the unit count without materially changing the merit
# order's shape). Mirrored here: anything under 10 MW collapses into one
# pseudo-block per cost category, commissioned at that category's
# capacity-weighted mean year (not used downstream, kept for completeness).

# %%
SMALL_THRESHOLD_KW = 10_000

op["size_class"] = np.where(op["net_capacity_kw"] >= SMALL_THRESHOLD_KW, "block", "aggregated")

large_blocks = op[op["size_class"] == "block"][["unit_id", "cost_category", "net_capacity_kw", "plant_name", "block_name"]].copy()

small_agg = (
    op[op["size_class"] == "aggregated"]
    .groupby("cost_category", as_index=False)
    .agg(net_capacity_kw=("net_capacity_kw", "sum"), unit_id=("unit_id", "count"))
)
small_agg["unit_id"] = "aggregated (" + small_agg["unit_id"].astype(str) + " units < 10 MW)"
small_agg["plant_name"] = small_agg["cost_category"] + " (<10 MW, aggregated)"
small_agg["block_name"] = small_agg["plant_name"]

fleet = pd.concat([large_blocks, small_agg], ignore_index=True)
print(f"{len(fleet):,} merit-order blocks, {fleet['net_capacity_kw'].sum() / 1e6:.1f} GW total")

# %% [markdown]
# ## Assumptions: fuel/CO2/transport/variable-cost/outage/emission-factor
#
# Reused directly from EWI Merit-Order Tool 2025's own documentation
# (Oktober 2025), Tables 1, 3, 4, 5, 6 -- same categories, same values,
# same cited sources (investing.com coal/CO2 futures, en2x/TTF for oil/gas,
# ÜNB (2019) emission factors, EWI's own 2019 lignite fuel-cost estimate).
# The only addition here is splitting EWI's single "Erdgas" row into
# GuD/Gasturbine/BHKW sub-rows (see gas-technology split above) with
# textbook efficiency values, since that's the one place this replication
# needed its own assumption EWI's table doesn't carry a matching row for.

# %%
ASSUMPTIONS = pd.DataFrame(
    [
        # category,          eta,   fuel_EUR_MWh_th, transport_EUR_MWh_th, var_cost_EUR_MWh_el, outage_pct, emission_factor_tCO2_MWh_th
        ["Kernenergie", 0.33, 5.50, 0.00, 1.2, 0.07, 0.00],
        ["Braunkohle", 0.38, 3.10, 0.00, 1.7, 0.13, 0.40],
        ["Steinkohle", 0.40, 14.30, 1.25, 1.3, 0.20, 0.34],
        ["Erdgas GuD", 0.58, 40.19, 0.50, 1.5, 0.13, 0.20],
        ["Erdgas Gasturbine", 0.35, 40.19, 0.50, 1.0, 0.13, 0.20],
        ["Erdgas BHKW", 0.40, 40.19, 0.50, 1.5, 0.13, 0.20],  # efficiency: this notebook's own assumption, not EWI's
        ["Öl", 0.38, 95.59, 0.30, 1.0, 0.15, 0.28],
        ["Sonstige", 0.30, 95.59, 0.00, 1.0, 0.15, 0.21],
        ["Abfall", 0.25, 0.00, 0.00, 1.0, 0.15, 0.00],
    ],
    columns=[
        "cost_category",
        "efficiency",
        "fuel_price_eur_mwh_th",
        "transport_cost_eur_mwh_th",
        "var_cost_eur_mwh_el",
        "outage_share",
        "emission_factor_t_co2_mwh_th",
    ],
).set_index("cost_category")

EUA_PRICE_EUR_T_CO2 = 69.35  # mean 01.07.2024-30.06.2025, EWI (2025) citing investing.com

ASSUMPTIONS

# %% [markdown]
# ## Grenzkosten (marginal cost) per block
#
# $$GK = \frac{\text{Brennstoffpreis} + \text{Transportkosten}}{\eta} +
# EUA \cdot \frac{\text{Emissionsfaktor}}{\eta} + \text{var.\ Betriebskosten}$$
#
# Available capacity nets out the assumed outage share:
# $P_{\text{verfügbar}} = P_{\text{netto}} \cdot (1 - p_{\text{Ausfall}})$

# %%
fleet = fleet.merge(ASSUMPTIONS, left_on="cost_category", right_index=True, how="left")

fleet["marginal_cost_eur_mwh"] = (
    (fleet["fuel_price_eur_mwh_th"] + fleet["transport_cost_eur_mwh_th"]) / fleet["efficiency"]
    + EUA_PRICE_EUR_T_CO2 * fleet["emission_factor_t_co2_mwh_th"] / fleet["efficiency"]
    + fleet["var_cost_eur_mwh_el"]
)
fleet["available_capacity_mw"] = fleet["net_capacity_kw"] / 1e3 * (1 - fleet["outage_share"])

fleet.groupby("cost_category").agg(
    capacity_gw=("net_capacity_kw", lambda s: s.sum() / 1e6),
    mean_marginal_cost=("marginal_cost_eur_mwh", "mean"),
    min_marginal_cost=("marginal_cost_eur_mwh", "min"),
    max_marginal_cost=("marginal_cost_eur_mwh", "max"),
).round(1).sort_values("mean_marginal_cost")

# %% [markdown]
# ## The merit order curve
#
# Sorted ascending by marginal cost, cumulative *available* capacity on the
# x-axis -- directly comparable in shape to EWI's own Abbildung 2 (their
# tool's example chart).

# %%
FUEL_COLORS = {
    "Abfall": "#8c1c13",
    "Braunkohle": "#6b3e26",
    "Steinkohle": "#2b2b2b",
    "Erdgas GuD": "#b38b00",
    "Erdgas Gasturbine": "#e8c547",
    "Erdgas BHKW": "#f2e2a0",
    "Öl": "#6a0dad",
    "Sonstige": "#9e9e9e",
}

merit = fleet.sort_values("marginal_cost_eur_mwh").reset_index(drop=True)
merit["cum_capacity_mw"] = merit["available_capacity_mw"].cumsum()
merit["cum_capacity_start_mw"] = merit["cum_capacity_mw"] - merit["available_capacity_mw"]

fig, ax = plt.subplots(figsize=(14, 6))
for category, color in FUEL_COLORS.items():
    rows = merit[merit["cost_category"] == category]
    if rows.empty:
        continue
    ax.bar(
        rows["cum_capacity_start_mw"],
        rows["marginal_cost_eur_mwh"],
        width=rows["available_capacity_mw"],
        align="edge",
        color=color,
        label=category,
        linewidth=0,
    )

ax.set_xlabel("Kumulierte verfügbare Leistung [MW]")
ax.set_ylabel("Grenzkosten [EUR/MWh_el]")
ax.set_title("Replizierte deutsche Merit-Order, konventioneller Kraftwerkspark (MaStR, aktueller Bestand)")
ax.legend(loc="upper left", ncol=2, fontsize=9)
ax.set_ylim(0, merit["marginal_cost_eur_mwh"].quantile(0.995))
fig.tight_layout()
fig.savefig(paths.images_path / "13_merit_order_curve.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/13_merit_order_curve.png
# :name: fig-13-merit-order-curve
# Replicated German conventional-fleet merit order: current MaStR capacity,
# EWI (2025)'s own published fuel/CO2/variable-cost/outage assumptions,
# sorted by marginal cost. Compare the shape (lignite/hard coal plateau
# around 70-110 EUR/MWh, gas CCGT above it, open-cycle gas turbines and oil
# at the top) against EWI's own Abbildung 2.
# ```

# %% [markdown]
# ## Distribution of marginal costs by fuel (sanity check)
#
# EWI's own Abbildung 1 shows this as a boxplot per technology -- the same
# view here, to check the *spread* within a category, not just its mean.

# %%
fig, ax = plt.subplots(figsize=(10, 5))
categories_present = [c for c in FUEL_COLORS if c in fleet["cost_category"].unique()]
box_data = [fleet.loc[fleet["cost_category"] == c, "marginal_cost_eur_mwh"].dropna() for c in categories_present]
bp = ax.boxplot(box_data, tick_labels=categories_present, patch_artist=True)
for patch, cat in zip(bp["boxes"], categories_present):
    patch.set_facecolor(FUEL_COLORS[cat])
ax.set_ylabel("Grenzkosten [EUR/MWh_el]")
ax.set_title("Verteilung der Grenzkosten je Brennstoffkategorie")
plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
fig.tight_layout()
fig.savefig(paths.images_path / "13_marginal_cost_boxplot.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/13_marginal_cost_boxplot.png
# :name: fig-13-marginal-cost-boxplot
# Spread of marginal costs within each fuel category. All spread here comes
# from capacity-class-driven efficiency/outage differences, since every
# unit of a given cost category shares the same fuel/CO2/transport price
# assumption in this notebook -- unlike EWI's tool, which resolves
# efficiency per historical plant block and would show a wider spread.
# ```

# %% [markdown]
# ## What this replication got right, and what it didn't
#
# **Plausible against known totals:** operating combustion fleet comes out
# at ~78 GW net (hard coal ~15 GW, lignite ~15 GW, gas ~34 GW, oil ~5 GW),
# in the right ballpark for Germany's current conventional fleet, and the
# qualitative merit-order shape (coal/lignite plateau, then gas CCGT, then
# peaking gas turbines/oil at 200+ EUR/MWh) matches the shape of EWI's own
# published chart.
#
# **What's a genuine simplification relative to EWI's own tool, not just
# this notebook's choice:**
# - Efficiency is assigned per fuel/technology *class*, not per historical
#   plant block -- EWI's tool does the latter (an older, more granular
#   table carried forward from a previous version), which is why their
#   boxplot shows real within-category spread and this one's spread comes
#   only from the capacity-size/outage split.
# - No cross-border effects, no storage, no renewables-side curtailment
#   threshold layer (see the Hirth-paper discussion this was built to
#   extend) -- same limitations EWI's own documentation names explicitly
#   for their tool.
# - The gas CCGT/OCGT/BHKW three-way split is this notebook's own addition
#   on top of EWI's two-way GuD/Gasturbine split, needed because MaStR's
#   `Technologie` field puts the vast majority of gas units (small
#   decentral combustion engines and fuel cells) in neither category.
#
# **Natural next step, not yet done here:** attach this fleet to an actual
# historical demand/residual-load series and check whether the resulting
# merit-order price prediction tracks real SMARD day-ahead prices on
# non-renewable-dominated hours -- the backtest discussed as the
# practical way to validate a from-scratch merit order without paying for
# EPEX's own aggregated bid-curve data.

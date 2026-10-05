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
# # Is reBAP vs. intraday price a tighter imbalance signal than reBAP vs. day-ahead?
#
# `09_nrv_saldo_vs_rebap.py` found a real but only moderate relationship
# between `reBAP - day-ahead` and the actual system imbalance (NRV-Saldo):
# same sign 93.7% of the time, but Pearson r only ≈ 0.35. The spread mixes
# two different gaps: day-ahead is fixed ~12-36h before delivery, so part of
# `reBAP - day-ahead` is just "the system re-balanced on the intraday market
# using information day-ahead didn't have" -- nothing to do with real-time
# imbalance -- while only the rest is genuine last-minute surprise.
#
# The **ID-AEP** (netztransparenz.de's own English name: "IP-Index";
# promoted into `energy-data-hub` as the `id_aep` asset, `balancing_market`
# group, 2026-10-05) is a volume-weighted average of the *last* continuous-
# intraday trades before delivery (closes 5 minutes before T) -- a much
# later, more complete information set than day-ahead. This notebook asks
# directly: is `reBAP - ID-AEP` a tighter proxy for the real imbalance than
# `reBAP - day-ahead`?

# %%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

DA_COLOR = "#2a78d6"
REBAP_COLOR = "#8e44ad"
NRV_COLOR = "#d35400"
ID_AEP_COLOR = "#1b8a5a"
NEUTRAL = "#898781"

# %% [markdown]
# ## Data
#
# Same join as `09`, with ID-AEP added. ID-AEP only starts 2020-07-01 (vs.
# reBAP/NRV-Saldo's 2014-01-01) -- a newer market product -- so the clean-year
# list is `09`'s own gap-year exclusions intersected with ID-AEP's coverage.

# %%
rebap = pd.read_parquet(hub_file("balancing_market", "rebap_price.parquet"))
rebap.index = pd.to_datetime(rebap.index)

day_ahead = pd.read_parquet(hub_file("smard", "price_de_lu.parquet"))
day_ahead.index = pd.to_datetime(day_ahead.index)
day_ahead_15min = day_ahead.reindex(
    pd.date_range(day_ahead.index.min(), day_ahead.index.max() + pd.Timedelta(minutes=45), freq="15min")
).ffill()

nrv = pd.read_parquet(hub_file("balancing_market", "nrv_saldo.parquet"))
nrv.index = pd.to_datetime(nrv.index)

id_aep = pd.read_parquet(hub_file("balancing_market", "id_aep.parquet"))
id_aep.index = pd.to_datetime(id_aep.index)

panel = pd.DataFrame({
    "rebap": rebap["rebap_eur_mwh"],
    "day_ahead": day_ahead_15min["price_de_lu"],
    "id_aep": id_aep["id_aep_eur_mwh"],
    "nrv_saldo": nrv["nrv_saldo_mw"],
}).dropna()

ID_AEP_CLEAN_YEARS = [2020, 2021, 2023, 2024, 2025, 2026]  # 09's clean years, intersected with ID-AEP's 2020-07+ coverage
clean = panel[panel.index.year.isin(ID_AEP_CLEAN_YEARS)].copy()
clean["spread_da"] = clean["rebap"] - clean["day_ahead"]
clean["spread_id"] = clean["rebap"] - clean["id_aep"]

print(f"n = {len(clean):,} quarter-hours ({clean.index.min()} -> {clean.index.max()})")

# %% [markdown]
# ## The result: sign agreement goes to 100%, but magnitude correlation barely moves

# %%
stats = {}
for name, col in [("reBAP - day-ahead", "spread_da"), ("reBAP - ID-AEP", "spread_id")]:
    r = clean[col].corr(clean["nrv_saldo"])
    same_sign = (np.sign(clean[col]) == np.sign(clean["nrv_saldo"])).mean()
    stats[name] = {"r": r, "same_sign": same_sign, "mean_abs": clean[col].abs().mean()}
    print(f"{name:20s}  Pearson r = {r:.3f}   same-sign = {same_sign:.1%}   mean|spread| = {clean[col].abs().mean():.1f} EUR/MWh")

print()
print(f"corr(reBAP, day-ahead) = {clean['rebap'].corr(clean['day_ahead']):.3f}")
print(f"corr(reBAP, ID-AEP)    = {clean['rebap'].corr(clean['id_aep']):.3f}")

# %% [markdown]
# **Same-sign agreement jumps from 93.0% to 100.0% (not 99.x -- exactly
# 100.0% across all ~180k clean-year quarter-hours) when switching the
# reference price from day-ahead to ID-AEP. Pearson r barely moves (0.367 →
# 0.353, if anything slightly lower). Both results have a real, mechanical
# explanation, not just an empirical coincidence -- see below.**

# %% [markdown]
# ## Why: reBAP's own published formula uses ID-AEP directly, with the sign
# ## of the system balance built in by construction
#
# netztransparenz.de publishes the exact reBAP calculation
# ("Calculation of the uniform imbalance price (reBAP) across Germany's 4 LFC
# areas -- Model description", in force since 2023-11-01). reBAP is the
# **max** of three modules if the system was short that quarter-hour (GCC
# balance > 0), or the **min** of the same three modules if long (< 0):
#
# - **Module 1 (base component):** built from PICASSO/MARI aFRR/mFRR
#   activation prices -- the actual balancing-energy merit order. This is the
#   sharp, jumpy, nonlinear part `09` already flagged.
# - **Module 2 (incentivising component):** built **directly from ID-AEP**:
#   `AEP_Module2 = ID-AEP + ΔP` if the GCC balance is positive (short),
#   `ID-AEP - ΔP` if negative (long), `= ID-AEP` exactly if the balance is
#   zero -- where `ΔP` is a minimum distance (≥10 EUR/MWh or 25% of ID-AEP,
#   scaling linearly up to that floor as `|balance|` grows from 0 to 500 MW
#   average power, i.e. 125 MWh per quarter-hour, then **capped, not growing
#   further**). **The sign of the GCC balance (= NRV-Saldo's sign) directly
#   picks addition vs. subtraction here -- this is exactly why the empirical
#   same-sign match against `reBAP - ID-AEP` comes out at a clean 100.0%, not
#   just "usually right."**
# - **Module 3 (scarcity component):** only switches on once `|balance|`
#   reaches 80% of dimensioned FRR capacity -- a parabolic function of the
#   balance that can reach tens of thousands of EUR/MWh in extreme
#   quarter-hours (this is the source of the >10,000 EUR/MWh outlier days
#   found while picking examples for `14_imbalance_signal_days.py` -- a real,
#   documented mechanism, not a data error).
#
# **This also explains why Pearson r barely improved.** Module 2's own
# contribution -- the smooth, ID-AEP-anchored part -- saturates at a small,
# capped `ΔP` once `|balance|` passes 500 MW average power. Whatever happens
# beyond that point is governed by Module 1 (noisy merit-order jumps) or
# Module 3 (a parabola, structurally unrelated to ID-AEP at all) -- neither
# of which gets any more linear in the balance just because the reference
# price changed. ID-AEP fixes the *sign* question by construction; it does
# not, and structurally cannot, fix the *magnitude* question for the large
# quarter-hours that dominate a linear-correlation metric.

# %% [markdown]
# ## Visual: reBAP tracks ID-AEP far more tightly than it tracks day-ahead

# %%
fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
for ax, (name, col, color) in zip(axes, [("Day-ahead", "day_ahead", DA_COLOR), ("ID-AEP", "id_aep", ID_AEP_COLOR)]):
    hb = ax.hist2d(clean[col], clean["rebap"], bins=100, range=[[-200, 400], [-200, 400]], cmap="Purples", cmin=1)
    ax.plot([-200, 400], [-200, 400], color=NEUTRAL, linewidth=0.8, linestyle="--")
    ax.set_xlabel(f"{name} [EUR/MWh]")
    r = clean["rebap"].corr(clean[col])
    ax.set_title(f"reBAP vs. {name}\nPearson r = {r:.2f}", fontsize=11)
axes[0].set_ylabel("reBAP [EUR/MWh]")
fig.tight_layout()
fig.savefig(paths.images_path / "16_rebap_vs_reference_price.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/16_rebap_vs_reference_price.png
# :name: fig-16-rebap-vs-reference
# reBAP against day-ahead (left) vs. against ID-AEP (right), same axis
# range and bin size on both -- the ID-AEP panel visibly hugs the diagonal
# far more tightly.
# ```

# %% [markdown]
# ## Quintile view: same-sign vs. magnitude, side by side
#
# Left: mean spread by NRV-Saldo quintile, both reference prices (`09`'s own
# chart, reproduced here for direct comparison). Right: share of quarter-hours
# in each quintile where the spread's sign matches the balance's sign.

# %%
clean["nrv_quintile"] = pd.qcut(
    clean["nrv_saldo"], 5,
    labels=["Q1\n(most over-supplied)", "Q2", "Q3\n(near-balanced)", "Q4", "Q5\n(most under-supplied)"],
)
q_mean = clean.groupby("nrv_quintile", observed=True)[["spread_da", "spread_id"]].mean()
q_samesign = clean.groupby("nrv_quintile", observed=True).apply(
    lambda g: pd.Series({
        "spread_da": (np.sign(g["spread_da"]) == np.sign(g["nrv_saldo"])).mean(),
        "spread_id": (np.sign(g["spread_id"]) == np.sign(g["nrv_saldo"])).mean(),
    }),
    include_groups=False,
)

fig, (ax_mean, ax_sign) = plt.subplots(1, 2, figsize=(13, 5.5))
x = np.arange(len(q_mean))
width = 0.36
ax_mean.bar(x - width / 2, q_mean["spread_da"], width, color=DA_COLOR, label="vs. day-ahead")
ax_mean.bar(x + width / 2, q_mean["spread_id"], width, color=ID_AEP_COLOR, label="vs. ID-AEP")
ax_mean.axhline(0, color=NEUTRAL, linewidth=0.8)
ax_mean.set_xticks(x)
ax_mean.set_xticklabels(q_mean.index, fontsize=8.5)
ax_mean.set_ylabel("Mean spread [EUR/MWh]")
ax_mean.set_title("Mean spread by NRV-Saldo quintile")
ax_mean.legend(fontsize=9)
ax_mean.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax_mean.set_axisbelow(True)

ax_sign.bar(x - width / 2, q_samesign["spread_da"], width, color=DA_COLOR, label="vs. day-ahead")
ax_sign.bar(x + width / 2, q_samesign["spread_id"], width, color=ID_AEP_COLOR, label="vs. ID-AEP")
ax_sign.axhline(1.0, color=NEUTRAL, linewidth=0.8, linestyle="--")
ax_sign.set_ylim(0, 1.05)
ax_sign.set_xticks(x)
ax_sign.set_xticklabels(q_mean.index, fontsize=8.5)
ax_sign.set_ylabel("Share with spread sign == NRV-Saldo sign")
ax_sign.set_title("Same-sign rate by NRV-Saldo quintile")
ax_sign.legend(fontsize=9, loc="lower right")
ax_sign.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax_sign.set_axisbelow(True)

fig.tight_layout()
fig.savefig(paths.images_path / "16_quintile_comparison.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/16_quintile_comparison.png
# :name: fig-16-quintile-comparison
# Mean spread (left) and same-sign rate (right) by NRV-Saldo quintile, both
# reference prices. The magnitude staircase looks similar either way; the
# same-sign rate is visibly higher for the ID-AEP spread throughout, reaching
# 100% even in the near-balanced middle quintile.
# ```

# %% [markdown]
# ## Over time: does the spread visibly track the Saldo?
#
# The views above are aggregate statistics across ~180k quarter-hours. This
# section looks at one sample week directly -- the same week
# `09_nrv_saldo_vs_rebap.py` used for its own day-ahead-based overlay, for
# direct comparability: `reBAP - ID-AEP` (top) against the imbalance volume
# itself (bottom, same definition as `14_imbalance_signal_days.py`: average
# MW x 0.25h).

# %%
sample = clean.loc["2024-01-08":"2024-01-15"].copy()
sample["imbalance_volume_mwh"] = sample["nrv_saldo"] * 0.25

fig, (ax_spread, ax_vol) = plt.subplots(2, 1, figsize=(13, 7), sharex=True, height_ratios=[2, 1])

n_clipped = (sample["spread_id"].abs() > 500).sum()
ax_spread.step(sample.index, sample["spread_id"], where="post", color=REBAP_COLOR, linewidth=1.3)
ax_spread.axhline(0, color=NEUTRAL, linewidth=0.8)
ax_spread.set_ylim(-500, 500)  # a handful of KapRes-driven spikes this week reach 4,000-8,000 EUR/MWh --
# clipped from view (not from the data) so the everyday-range pattern stays readable; see `17`'s own
# discussion of the KapRes override for what those rare spikes are.
ax_spread.set_ylabel("reBAP - ID-AEP [EUR/MWh]")
ax_spread.set_title(
    f"reBAP - ID-AEP spread (top) vs. imbalance volume / NRV-Saldo (bottom), one sample week\n"
    f"(y-axis clipped to ±500 EUR/MWh -- {n_clipped} of {len(sample)} quarter-hours this week exceed that, "
    f"up to {sample['spread_id'].abs().max():.0f} EUR/MWh, see KapRes discussion in `17`)",
    fontsize=10.5,
)
ax_spread.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax_spread.set_axisbelow(True)

ax_vol.fill_between(sample.index, sample["imbalance_volume_mwh"], 0, color=NRV_COLOR, alpha=0.8, step="post")
ax_vol.axhline(0, color=NEUTRAL, linewidth=0.8)
ax_vol.set_ylabel("Imbalance volume\n[MWh/15min]")
ax_vol.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax_vol.set_axisbelow(True)

fig.tight_layout()
fig.savefig(paths.images_path / "16_spread_vs_saldo_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/16_spread_vs_saldo_timeseries.png
# :name: fig-16-spread-vs-saldo-timeseries
# `reBAP - ID-AEP` (top) vs. imbalance volume / NRV-Saldo (bottom), one
# sample week (2024-01-08 to 2024-01-15) -- every swing in the bottom panel
# has a same-direction counterpart directly above it, the time-series view
# of the 100% same-sign result found above.
# ```

# %% [markdown]
# ## Takeaways
#
# - **The original question -- "shouldn't reBAP vs. intraday be a tighter
#   imbalance signal than reBAP vs. day-ahead?" -- was right, but the
#   improvement shows up in *direction*, not in *magnitude*.** Same-sign
#   agreement: 93.0% → 100.0%. Pearson r: 0.367 → 0.353 (essentially
#   unchanged, if anything slightly lower).
# - **Both effects trace back to reBAP's own published calculation formula**,
#   not just an empirical pattern this notebook happened to find: Module 2 is
#   built as `ID-AEP ± ΔP` with the `±` chosen by the balance's sign (exact
#   mechanism for the 100% same-sign result), while the large-magnitude tail
#   is dominated by Module 1 (merit-order) and Module 3 (a scarcity
#   parabola), neither of which is linear in the balance at all.
# - **Practical implication for `14_imbalance_signal_days.py`'s chart:**
#   switching that chart's blue reference line from day-ahead to ID-AEP would
#   make the "reBAP decouples from the reference price" story mechanically
#   closer to "the system was out of balance" (literal sign agreement)
#   rather than a loose directional tendency -- worth doing if that page is
#   revisited, now that ID-AEP is downloaded here too.
# - ID-AEP's own history is shorter than reBAP/NRV-Saldo's (2020-07-01
#   onward, vs. 2014-01-01) -- not a limitation for this question, but means
#   it can't extend any analysis that specifically needs the earlier years.

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
# # Reconstructing reBAP from its own published formula — how far can we get?
#
# `16_id_aep_vs_rebap_spread.py` found reBAP's official calculation formula
# (netztransparenz.de, "Calculation of the uniform imbalance price (reBAP)
# across Germany's 4 LFC areas — Model description", in force since
# 2023-11-01): reBAP = **max** of three modules if the system was short that
# quarter-hour, **min** if long.
#
# - **Module 1** (base): needs PICASSO/MARI **activation** prices for
#   aFRR/mFRR — not the same thing as `energy-data-hub`'s
#   `afrr_capacity_price`/`fcr_capacity_price` (those are *capacity
#   procurement* prices, a different market; activation prices aren't in this
#   platform yet).
# - **Module 2** (incentivising): built directly from **ID-AEP + NRV-Saldo**
#   — both `energy-data-hub` assets now (`balancing_market` group).
#   **Fully reconstructable right now.**
# - **Module 3** (scarcity): needs dimensioned FRR capacity, contracted
#   disconnectable loads (AbLa), and capacity reserve (KapRes) volumes — none
#   of which this platform has. A separate, fixed-cap override also applies
#   during actual KapRes activation (reBAP capped at 2 x the max intraday bid
#   price, currently 19,998 EUR/MWh) — this is the exact mechanism behind the
#   >15,000 EUR/MWh outlier days found while picking examples for
#   `14_imbalance_signal_days.py`.
#
# At the time this notebook was first written, full reBAP wasn't
# reconstructable yet -- only Module 2 was, from data already on disk. This
# notebook builds just that, and checks how much of real reBAP it alone
# explains (formula correctness implies a hard directional constraint --
# `AEP_Module2` can never be on the "wrong side" of actual reBAP -- which
# doubles as a validation of both the formula and this reconstruction).
#
# **Update, same day:** it turned out netztransparenz.de publishes all three
# modules directly, pre-computed -- no reconstruction of Module 1/3 needed
# at all. The full picture (`max`/`min(Module1, Module2, Module3)`,
# reconstructing real reBAP to a 99.99% exact match) is now in
# `energy-data-hub` (`aep_modules` asset) and `energy-insights`'
# `page_rebap_formula_reconstruction`. This notebook is kept as the
# intermediate step in that investigation -- the answer to "how far can we
# get with just Module 2 alone" is a real, separate finding (~23% exact
# match, see below), not superseded by the fuller answer found afterward.

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
# ## Data + Module 2 formula
#
# `ΔP = max(10 EUR/MWh, |ID-AEP| x 0.25) x min(125 MWh, |Balance_GCC|) / 125 MWh`
# (Formula 3) — a minimum distance that scales linearly from 0 up to that
# floor as `|Balance_GCC|` (the GCC's own quarter-hour energy imbalance, MWh)
# grows from 0 to 125 MWh (= 500 MW average power), then stays capped.
#
# `AEP_Module2 = ID-AEP + ΔP` if `Balance_GCC > 0` (short), `ID-AEP - ΔP` if
# `< 0` (long), `= ID-AEP` exactly if `== 0` (Formula 4) — defined whenever
# ID-AEP itself is defined (>= 500 MW continuous-intraday volume traded; our
# downloaded window has 0% undefined quarter-hours, so this never blocks the
# calculation here).

# %%
rebap = pd.read_parquet(hub_file("balancing_market", "rebap_price.parquet"))
rebap.index = pd.to_datetime(rebap.index)

nrv = pd.read_parquet(hub_file("balancing_market", "nrv_saldo.parquet"))
nrv.index = pd.to_datetime(nrv.index)

id_aep = pd.read_parquet(hub_file("balancing_market", "id_aep.parquet"))
id_aep.index = pd.to_datetime(id_aep.index)

panel = pd.DataFrame({
    "rebap": rebap["rebap_eur_mwh"],
    "id_aep": id_aep["id_aep_eur_mwh"],
    "nrv_saldo_mw": nrv["nrv_saldo_mw"],
}).dropna()
panel["balance_gcc_mwh"] = panel["nrv_saldo_mw"] * 0.25  # MW -> MWh over a 15-min settlement period

scale = (panel["balance_gcc_mwh"].abs().clip(upper=125) / 125)
delta_p = np.maximum(10.0, panel["id_aep"].abs() * 0.25) * scale

aep_module2 = pd.Series(panel["id_aep"], index=panel.index)
short = panel["balance_gcc_mwh"] > 0
long_ = panel["balance_gcc_mwh"] < 0
aep_module2 = aep_module2.where(~short, panel["id_aep"] + delta_p)
aep_module2 = aep_module2.where(~long_, panel["id_aep"] - delta_p)
panel["aep_module2"] = aep_module2.round(2)  # commercial rounding to 2 decimals, per the spec

print(f"n = {len(panel):,} quarter-hours ({panel.index.min()} -> {panel.index.max()})")
print(panel[["rebap", "id_aep", "balance_gcc_mwh", "aep_module2"]].head())

# %% [markdown]
# ## Sanity check: the formula's own directional constraint
#
# Because reBAP is the **max** of all three modules when short and the
# **min** when long, `AEP_Module2` can mathematically never land on the wrong
# side of the real reBAP: `reBAP >= AEP_Module2` whenever short, `reBAP <=
# AEP_Module2` whenever long. If this is violated anywhere (beyond tiny
# rounding noise), either this reconstruction has a bug or a quarter-hour hit
# the separate KapRes override (`Formula 6`, not modeled here).

# %%
panel["excess_over_module2"] = np.where(
    short, panel["rebap"] - panel["aep_module2"],
    np.where(long_, panel["aep_module2"] - panel["rebap"], 0.0),
)
# should be >= 0 everywhere (up to rounding); negative values are genuine violations
violations = panel[panel["excess_over_module2"] < -0.02]
print(f"Violations of the max/min constraint (tolerance 0.02 EUR/MWh): {len(violations):,} / {len(panel):,} "
      f"({len(violations) / len(panel):.3%})")
if len(violations):
    print(violations[["rebap", "aep_module2", "balance_gcc_mwh", "excess_over_module2"]].describe())

# %% [markdown]
# ## How much of reBAP does Module 2 alone explain?

# %%
exact_match = (panel["excess_over_module2"].abs() < 0.02)
print(f"Quarter-hours where reBAP == AEP_Module2 (Module 2 is the binding/winning module): "
      f"{exact_match.mean():.1%}")
print()
print("Distribution of 'excess' (how far Module 1/3 pushed reBAP beyond Module 2), EUR/MWh:")
print(panel["excess_over_module2"].describe())
print()
for q in [0.5, 0.9, 0.99, 0.999]:
    print(f"  {q:.1%} quantile: {panel['excess_over_module2'].quantile(q):.1f} EUR/MWh")

# %% [markdown]
# ## Visual: reconstructed Module 2 vs. actual reBAP

# %%
fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))

hb = axes[0].hist2d(panel["aep_module2"], panel["rebap"], bins=100, range=[[-200, 400], [-200, 400]],
                     cmap="Purples", cmin=1)
axes[0].plot([-200, 400], [-200, 400], color=NEUTRAL, linewidth=0.8, linestyle="--")
r = panel["rebap"].corr(panel["aep_module2"])
axes[0].set_xlabel("Reconstructed AEP_Module2 [EUR/MWh]")
axes[0].set_ylabel("Actual reBAP [EUR/MWh]")
axes[0].set_title(f"Actual reBAP vs. reconstructed Module 2\nPearson r = {r:.3f}", fontsize=11)

axes[1].hist(panel["excess_over_module2"].clip(upper=200), bins=100, color=REBAP_COLOR, alpha=0.75)
axes[1].axvline(0, color=NEUTRAL, linewidth=0.8)
axes[1].set_xlabel("reBAP excess over Module 2 [EUR/MWh] (clipped at 200)")
axes[1].set_ylabel("Quarter-hours")
axes[1].set_title(f"How far Module 1/3 push beyond Module 2\n{exact_match.mean():.1%} exact matches", fontsize=11)
axes[1].set_yscale("log")

fig.tight_layout()
fig.savefig(paths.images_path / "17_module2_reconstruction.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/17_module2_reconstruction.png
# :name: fig-17-module2-reconstruction
# Left: reconstructed `AEP_Module2` vs. actual reBAP (diagonal = perfect
# match). Right: distribution of how far actual reBAP exceeds the
# reconstructed Module 2 in the imbalance direction (log-scale count axis —
# most quarter-hours cluster at/near zero, with a long tail where Module 1 or
# 3 took over).
# ```

# %% [markdown]
# ## Takeaways
#
# - **Module 2 alone, built entirely from data already in this platform
#   (ID-AEP + NRV-Saldo), reconstructs a large share of actual reBAP exactly**
#   (see the printed match rate above) — and never violates the formula's own
#   max/min directional constraint beyond rounding noise, which is a genuine
#   validation that both the published formula and this reconstruction are
#   right, not just a plausible-looking approximation.
# - **The remaining gap is structurally Module 1 and Module 3's territory**,
#   and neither is reconstructable with data this platform currently has:
#   - Module 1 needs real PICASSO/MARI balancing-energy **activation**
#     prices/volumes (a genuinely different market/data source than the
#     `afrr_capacity_price`/`fcr_capacity_price` **capacity** assets already
#     in `energy-data-hub`).
#   - Module 3 needs dimensioned FRR capacity, AbLa, and KapRes volumes,
#     none of which are downloaded anywhere in this platform yet, plus the
#     separate KapRes-activation override (fixed cap, currently 19,998
#     EUR/MWh) for the rare extreme quarter-hours.
# - ~~Next step, if a full reconstruction is wanted: find out whether
#   netztransparenz.de also publishes PICASSO/MARI activation prices and the
#   FRR dimensioning/AbLa/KapRes volumes Module 1 and 3 need~~ -- resolved
#   the same day: netztransparenz.de publishes all three modules directly,
#   pre-computed, no reconstruction of Module 1/3 needed at all. See the
#   "Update" note at the top of this notebook, `energy-data-hub`'s
#   `aep_modules` asset, and `energy-insights`' `page_rebap_formula_reconstruction`.

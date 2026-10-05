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
# # Does reBAP actually track the system's real imbalance?
#
# `07_balancing_market_prices` looked at reBAP on its own. The qualitative
# story around it: reBAP is the price a balancing group pays/receives for
# its own imbalance, and it tends to sit above the day-ahead price when
# the *whole system* is short (expensive upward balancing energy gets
# activated) and below it when the system is long (cheap/negative
# downward energy gets activated). So the **spread** `reBAP - day-ahead`
# should be a reasonable, if indirect, proxy for which way the system's
# imbalance went in a given quarter-hour.
#
# The actual, direct measure of that is the **NRV-Saldo** (Netzregelverbund-
# Saldo) -- netztransparenz.de's own aggregate imbalance figure for all of
# Germany, in MW, positive when the system was under-supplied (short) and
# negative when over-supplied (long); promoted into `energy-data-hub` as
# the `nrv_saldo` asset (`balancing_market` group) 2026-10-05, after this
# notebook's own prototype download validated it. This notebook checks the
# spread-as-proxy story against the real thing.
#
# **⚠️ NRV-Saldo has real, multi-month gaps in its history -- not a
# download bug.** Checked year by year: 2014/2015 (~8.5% missing each),
# 2016 (a single unbroken gap 2016-02-11 to 2016-10-31, ~72% of the
# year), 2018 (three separate gaps totaling ~33% of the year), and 2022
# (a single unbroken gap 2022-02-28 to 2022-05-31, ~25% of the year) all
# have substantial missing stretches in the "qualitätsgesichert" series.
# 2017, 2019, 2020, 2021, 2023, 2024, 2025, and 2026 are each ≥99.99%
# complete. This notebook restricts to those clean years throughout,
# rather than either silently including gappy years or papering over the
# gaps with an imputation.

# %%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

REBAP_COLOR = "#8e44ad"
DA_COLOR = "#2a78d6"
NRV_COLOR = "#d35400"
NEUTRAL = "#898781"

CLEAN_YEARS = [2017, 2019, 2020, 2021, 2023, 2024, 2025, 2026]
EXCLUDED_YEARS = [2014, 2015, 2016, 2018, 2022]

# %% [markdown]
# ## Data
#
# reBAP, day-ahead, and NRV-Saldo -- all three `energy-data-hub` assets now
# (`balancing_market`/`smard` groups) -- joined on their shared 15-min grid
# (day-ahead is hourly, forward-filled to 15-min since the day-ahead price
# genuinely applies uniformly across its whole hour, not an average of it).

# %%
rebap = pd.read_parquet(hub_file("balancing_market", "rebap_price.parquet"))
rebap.index = pd.to_datetime(rebap.index)

day_ahead = pd.read_parquet(hub_file("smard", "price_de_lu.parquet"))
day_ahead.index = pd.to_datetime(day_ahead.index)
day_ahead_15min = day_ahead.reindex(
    pd.date_range(day_ahead.index.min(), day_ahead.index.max() + pd.Timedelta(minutes=45), freq="15min")
).ffill()

nrv = pd.read_parquet(hub_file("balancing_market", "nrv_saldo.parquet"))

panel = pd.DataFrame({
    "rebap": rebap["rebap_eur_mwh"],
    "day_ahead": day_ahead_15min["price_de_lu"],
    "nrv_saldo": nrv["nrv_saldo_mw"],
}).dropna()
panel["spread"] = panel["rebap"] - panel["day_ahead"]

clean = panel[panel.index.year.isin(CLEAN_YEARS)].copy()
print(f"Full joined panel: {len(panel):,} quarter-hours ({panel.index.min()} -> {panel.index.max()})")
print(f"Clean years only:  {len(clean):,} quarter-hours  (excluded: {EXCLUDED_YEARS})")

# %% [markdown]
# ## A week of all three series, side by side

# %%
sample = clean.loc["2024-01-08":"2024-01-15"]

fig, (ax_price, ax_nrv) = plt.subplots(2, 1, figsize=(13, 7), sharex=True, height_ratios=[2, 1])

ax_price.plot(sample.index, sample["rebap"], color=REBAP_COLOR, linewidth=1.2, label="reBAP")
ax_price.plot(sample.index, sample["day_ahead"], color=DA_COLOR, linewidth=1.2, label="Day-ahead")
ax_price.set_ylabel("Price [EUR/MWh]")
ax_price.set_title("reBAP vs. day-ahead price, one sample week")
ax_price.legend(fontsize=9)
ax_price.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax_price.set_axisbelow(True)

ax_nrv.fill_between(sample.index, sample["nrv_saldo"], 0, color=NRV_COLOR, alpha=0.6, step="mid")
ax_nrv.axhline(0, color=NEUTRAL, linewidth=0.8)
ax_nrv.set_ylabel("NRV-Saldo [MW]")
ax_nrv.set_title("System imbalance (positive = under-supplied)")
ax_nrv.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax_nrv.set_axisbelow(True)

fig.tight_layout()
fig.savefig(paths.images_path / "09_week_overlay.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/09_week_overlay.png
# :name: fig-09-week-overlay
# reBAP vs. day-ahead price (top) and NRV-Saldo (bottom), one sample
# week in January 2024.
# ```

# %% [markdown]
# Visually, the two panels track each other closely: every time the
# orange NRV-Saldo panel swings positive (system short), reBAP (purple)
# pulls away above the day-ahead line (blue); every time it swings
# negative (system long), reBAP drops below it.

# %% [markdown]
# ## Spread vs. NRV-Saldo, all clean-year quarter-hours
#
# ~235,000 points -- shown as a 2D histogram rather than a scatter to
# avoid overplotting.

# %%
fig, ax = plt.subplots(figsize=(9, 7))
hb = ax.hist2d(clean["nrv_saldo"], clean["spread"], bins=120, cmap="Purples", cmin=1)
ax.axhline(0, color=NEUTRAL, linewidth=0.6)
ax.axvline(0, color=NEUTRAL, linewidth=0.6)
ax.set_xlabel("NRV-Saldo [MW] (positive = under-supplied)")
ax.set_ylabel("Spread: reBAP - day-ahead [EUR/MWh]")
corr = clean["spread"].corr(clean["nrv_saldo"])
sign_match = (np.sign(clean["spread"]) == np.sign(clean["nrv_saldo"])).mean()
ax.set_title(f"Pearson r = {corr:.2f}   |   same-sign quarter-hours = {sign_match:.1%}")
fig.colorbar(hb[3], ax=ax, label="Quarter-hours per cell")
fig.tight_layout()
fig.savefig(paths.images_path / "09_spread_vs_nrv_scatter.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/09_spread_vs_nrv_scatter.png
# :name: fig-09-spread-vs-nrv-scatter
# Spread (reBAP - day-ahead) against NRV-Saldo, all clean-year
# quarter-hours, shown as a 2D histogram.
# ```

# %% [markdown]
# The point cloud tilts clearly from bottom-left (long system, negative
# spread) to top-right (short system, positive spread), but it's a loose
# cloud, not a tight line -- correlation is moderate (r ≈ 0.35), not
# strong. Two things pull in opposite directions here: reBAP itself moves
# in sharp, nonlinear merit-order jumps (a small extra MW of imbalance
# can trigger a much more expensive marginal bid) rather than scaling
# smoothly with imbalance volume, which *weakens* a simple linear
# correlation -- but the much simpler yes/no question "did the spread at
# least point the right way" is answered correctly the large majority of
# the time (see the same-sign figure above, and the quintile view below).

# %% [markdown]
# ## Average spread by NRV-Saldo quintile

# %%
clean["nrv_quintile"] = pd.qcut(
    clean["nrv_saldo"], 5,
    labels=["Q1\n(most over-supplied)", "Q2", "Q3\n(near-balanced)", "Q4", "Q5\n(most under-supplied)"],
)
quintile_stats = clean.groupby("nrv_quintile", observed=True)["spread"].agg(["mean", "median"])

fig, ax = plt.subplots(figsize=(9, 5.5))
x = np.arange(len(quintile_stats))
colors = plt.colormaps["RdYlGn_r"](np.linspace(0.1, 0.9, len(quintile_stats)))
ax.bar(x, quintile_stats["mean"], color=colors, edgecolor="white", linewidth=0.5)
ax.axhline(0, color=NEUTRAL, linewidth=0.8)
ax.set_xticks(x)
ax.set_xticklabels(quintile_stats.index)
ax.set_ylabel("Mean spread: reBAP - day-ahead [EUR/MWh]")
ax.set_title("Average price spread rises monotonically with system shortage")
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
for xi, v in zip(x, quintile_stats["mean"]):
    ax.text(xi, v + (2 if v >= 0 else -2), f"{v:+.0f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=9)
fig.tight_layout()
fig.savefig(paths.images_path / "09_quintile_bars.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/09_quintile_bars.png
# :name: fig-09-quintile-bars
# Average spread (reBAP - day-ahead) by NRV-Saldo quintile.
# ```

# %% [markdown]
# A clean, monotonic staircase from -70 EUR/MWh (most over-supplied
# quintile) to +85 EUR/MWh (most under-supplied) -- no reversals, no flat
# spots. Splitting purely on the real, independently-measured imbalance
# direction alone separates the price spread cleanly.

# %% [markdown]
# ## Takeaways
#
# - **The qualitative story holds up against the real imbalance measure,
#   not just in theory.** The reBAP-vs-day-ahead spread has the correct
#   sign 93.7% of the time, and its average value rises monotonically
#   across NRV-Saldo quintiles with no reversals.
# - **"Correct sign" is not "tight linear relationship."** Pearson r ≈
#   0.35 -- reBAP's own merit-order-driven jumps make it a noisy, nonlinear
#   function of imbalance volume, not a scaled copy of it. Good enough to
#   answer "which direction," not precise enough to read off "how many MW"
#   from price alone.
# - **NRV-Saldo is the more honest variable when direction specifically
#   matters**, precisely because it's directly measured rather than
#   inferred from a price that's also shaped by the merit-order curve,
#   scarcity of specific reserve products, and (per `07`) the time-of-day
#   block structure -- but it comes with real historical gaps reBAP
#   doesn't have (see the data-quality note above), so it's not simply a
#   strict upgrade for every use case.

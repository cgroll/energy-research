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
# # Does a steep merit order amplify forecast-error-driven intraday corrections?
#
# **The theory being tested** (user hypothesis, 2026-10-04): on days/hours
# where the day-ahead merit order is locally *steep* at the point where
# residual load clears the price, the system should be more sensitive to
# surprises. If the wind/solar forecast turns out wrong, the resulting
# volume correction (via intraday trading) lands on a steep part of the
# supply curve and should move the price more than the same-size correction
# would on a flat part. Testable prediction: `|ID-AEP - day-ahead|` should
# scale with `|forecast error| x local slope`, not just with either alone.
#
# **We don't have real merit-order bid curves** (EPEX's aggregated
# supply/demand curves aren't free -- the same constraint
# `13_merit_order_replication.py` worked around by building a synthetic
# fuel-cost-based curve). Instead of that structural approach, this notebook
# estimates the merit order **empirically** ("revealed", not structural):
# the historical scatter of (residual load, day-ahead price) itself traces
# out the real curve's shape, noise and all (strategic bidding, imports/
# exports, must-run, storage -- none of that is separated out, it's all
# folded into one reduced-form relationship). The **local slope** of that
# empirical relationship is the steepness proxy -- standard econometric
# practice for estimating a supply curve's shape from realized
# price/quantity pairs when the actual bid curve isn't observed.

# %%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

DA_COLOR = "#2a78d6"
REBAP_COLOR = "#8e44ad"
NRV_COLOR = "#d35400"
ID_AEP_COLOR = "#1b8a5a"
NEUTRAL = "#898781"

# %% [markdown]
# ## Data: residual load, day-ahead price, forecast error, intraday correction
#
# All hourly (SMARD's native resolution; ID-AEP is resampled from 15-min to
# hourly by averaging its 4 quarter-hours, to match). Residual load = total
# load - wind onshore - wind offshore - solar, the standard simplification
# (ignores storage, imports/exports, must-run) used throughout this
# platform's own merit-order work. Forecast error = realized wind+solar
# generation minus SMARD's own day-ahead wind+solar forecast.

# %%
load = pd.read_parquet(hub_file("smard", "load.parquet"))
wind_on = pd.read_parquet(hub_file("smard", "generation_wind_onshore.parquet"))
wind_off = pd.read_parquet(hub_file("smard", "generation_wind_offshore.parquet"))
solar = pd.read_parquet(hub_file("smard", "generation_solar.parquet"))
f_on = pd.read_parquet(hub_file("smard", "forecast_onshore.parquet"))
f_off = pd.read_parquet(hub_file("smard", "forecast_offshore.parquet"))
f_solar = pd.read_parquet(hub_file("smard", "forecast_solar.parquet"))
day_ahead = pd.read_parquet(hub_file("smard", "price_de_lu.parquet"))
id_aep = pd.read_parquet(hub_file("balancing_market", "id_aep.parquet"))

for df in [load, wind_on, wind_off, solar, f_on, f_off, f_solar, day_ahead, id_aep]:
    df.index = pd.to_datetime(df.index)

id_aep_hourly = id_aep["id_aep_eur_mwh"].resample("1h").mean().rename("id_aep")

panel = pd.DataFrame({
    "load": load["total_load"],
    "wind_onshore": wind_on["wind_onshore"],
    "wind_offshore": wind_off["wind_offshore"],
    "solar": solar["solar"],
    "f_onshore": f_on["forecast_onshore"],
    "f_offshore": f_off["forecast_offshore"],
    "f_solar": f_solar["forecast_solar"],
    "day_ahead": day_ahead["price_de_lu"],
    "id_aep": id_aep_hourly,
}).dropna()

panel["residual_load"] = panel["load"] - panel["wind_onshore"] - panel["wind_offshore"] - panel["solar"]
panel["re_forecast"] = panel["f_onshore"] + panel["f_offshore"] + panel["f_solar"]
panel["re_actual"] = panel["wind_onshore"] + panel["wind_offshore"] + panel["solar"]
panel["forecast_error"] = panel["re_actual"] - panel["re_forecast"]  # + = more RE than expected (price-lowering surprise)
panel["intraday_correction"] = panel["id_aep"] - panel["day_ahead"]
panel["year"] = panel.index.year

print(f"n = {len(panel):,} hours ({panel.index.min()} -> {panel.index.max()})")
print(panel[["residual_load", "forecast_error", "day_ahead", "id_aep", "intraday_correction"]].describe())

# %% [markdown]
# ## Step 1: the revealed merit order, and how it's shifted over time
#
# Pooled hexbin of all hours (grey density) with one binned-median curve per
# year overlaid (40 residual-load quantile bins per year, median day-ahead
# price per bin) -- shows both the curve's actual shape and how much it has
# moved year to year (fuel/CO2 prices, capacity mix), which is exactly why
# the slope below is estimated **separately per year**, not pooled across
# the whole window.

# %%
YEARS = sorted(panel["year"].unique())
YEARS = [y for y in YEARS if (panel["year"] == y).sum() >= 1000]  # drop near-empty partial years

cmap = plt.colormaps["viridis"]
year_norm = Normalize(vmin=min(YEARS), vmax=max(YEARS))

N_BINS = 40


def binned_curve(sub: pd.DataFrame, n_bins: int = N_BINS) -> pd.DataFrame:
    """Quantile-bin residual_load, return (bin center, median price, median id_aep) per bin."""
    edges = np.quantile(sub["residual_load"], np.linspace(0, 1, n_bins + 1))
    edges[0] -= 1  # include the minimum
    bin_id = pd.cut(sub["residual_load"], edges, labels=False)
    g = sub.groupby(bin_id, observed=True).agg(
        resload=("residual_load", "mean"),
        price=("day_ahead", "median"),
        n=("residual_load", "size"),
    )
    return g[g["n"] >= 10].sort_values("resload")


fig, ax = plt.subplots(figsize=(10, 7))
ax.hexbin(panel["residual_load"], panel["day_ahead"], gridsize=70, cmap="Greys", bins="log", mincnt=1, alpha=0.55)
for y in YEARS:
    curve = binned_curve(panel[panel["year"] == y])
    ax.plot(curve["resload"], curve["price"], color=cmap(year_norm(y)), linewidth=1.6, label=str(y))
ax.set_xlabel("Residual load [MW] (load - wind - solar)")
ax.set_ylabel("Day-ahead price [EUR/MWh]")
ax.set_title("Revealed merit order: day-ahead price vs. residual load, by year")
ax.legend(fontsize=8.5, ncol=2, title="year (median curve)")
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(paths.images_path / "18_revealed_merit_order.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/18_revealed_merit_order.png
# :name: fig-18-revealed-merit-order
# Day-ahead price against residual load, all hours (grey density) with one
# median curve per year -- the empirical "revealed" merit order and its
# year-to-year drift (2021-2022's gas-price shock is clearly visible as the
# curve sitting far above every other year).
# ```

# %% [markdown]
# ## Step 2: local slope, per year
#
# Centered finite differences on each year's own binned curve -- flat where
# the curve is flat (mid-load, base/mid-merit plateau), steep at both tails
# (oversupply/negative-price zone and the scarce, peaker-driven high-load
# tail), as the classic merit-order "hockey stick" shape predicts.

# %%
def slope_lookup(curve: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    x = curve["resload"].to_numpy()
    y = curve["price"].to_numpy()
    slope = np.gradient(y, x)  # centered differences interior, one-sided at edges
    return x, slope


fig, ax = plt.subplots(figsize=(10, 6))
year_curves = {}
for y in YEARS:
    curve = binned_curve(panel[panel["year"] == y])
    x, slope = slope_lookup(curve)
    year_curves[y] = (x, np.clip(slope, 0, None))  # clip tiny negative noise -- a real supply curve isn't downward-sloping
    ax.plot(x, np.clip(slope, 0, None), color=cmap(year_norm(y)), linewidth=1.4, label=str(y))
ax.set_xlabel("Residual load [MW]")
ax.set_ylabel("Local slope dPrice/dResidualLoad [EUR/MWh per MW]")
ax.set_title("Estimated local merit-order steepness, by year")
ax.legend(fontsize=8.5, ncol=2)
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(paths.images_path / "18_merit_order_slope.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/18_merit_order_slope.png
# :name: fig-18-merit-order-slope
# Local merit-order slope vs. residual load, by year -- steep at both tails,
# flatter in the middle, consistent with the textbook merit-order shape.
# ```

# %%
panel["slope"] = np.nan
for y, (x, slope) in year_curves.items():
    mask = panel["year"] == y
    panel.loc[mask, "slope"] = np.interp(panel.loc[mask, "residual_load"], x, slope)

print(panel["slope"].describe())

# %% [markdown]
# ## Step 3: the actual test
#
# Binned-scatter view first (assumption-light, no regression functional form
# imposed): split hours into slope terciles, then within each tercile, plot
# mean `|intraday correction|` against bins of `|forecast error|`. The
# hypothesis predicts the high-slope line should rise faster (steeper) than
# the low-slope line, not just sit uniformly higher.

# %%
panel["abs_fe"] = panel["forecast_error"].abs()
panel["abs_correction"] = panel["intraday_correction"].abs()
panel["slope_tercile"] = pd.qcut(panel["slope"], 3, labels=["Low slope", "Mid slope", "High slope"])

FE_BINS = 12
panel["fe_bin"] = pd.qcut(panel["abs_fe"], FE_BINS, duplicates="drop")
fe_bin_mid = panel.groupby("fe_bin", observed=True)["abs_fe"].mean()

fig, ax = plt.subplots(figsize=(9.5, 6.5))
tercile_colors = {"Low slope": DA_COLOR, "Mid slope": NEUTRAL, "High slope": REBAP_COLOR}
for tercile, color in tercile_colors.items():
    sub = panel[panel["slope_tercile"] == tercile]
    g = sub.groupby("fe_bin", observed=True)["abs_correction"].mean()
    x = fe_bin_mid.reindex(g.index)
    ax.plot(x, g, marker="o", markersize=4, color=color, linewidth=1.6, label=tercile)
ax.set_xlabel("|Forecast error| (wind+solar), binned [MW]")
ax.set_ylabel("Mean |ID-AEP - day-ahead| [EUR/MWh]")
ax.set_title("Intraday correction vs. forecast error, by merit-order-slope tercile")
ax.legend(fontsize=9.5)
ax.yaxis.grid(True, linewidth=0.4, alpha=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(paths.images_path / "18_correction_vs_forecast_error_by_slope.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/18_correction_vs_forecast_error_by_slope.png
# :name: fig-18-correction-vs-forecast-error
# Mean intraday price correction against binned forecast-error size, split
# by merit-order-slope tercile -- the hypothesis predicts the three lines
# should fan out (high-slope rising fastest), not run parallel.
# ```

# %% [markdown]
# ## Step 4: a simple interaction regression (manual OLS, numpy -- no new
# ## dependency), as a second, complementary check
#
# `|correction| ~ |forecast error| (z) + slope (z) + |forecast error| x slope (z-z)`,
# both regressors standardized first so the interaction coefficient is
# directly interpretable. **Caveat upfront:** standard errors below are
# classical OLS (homoskedastic) -- electricity-price residuals are known to
# be heteroskedastic, so treat the t-stats as indicative, not final. The
# binned-scatter view above is the more assumption-light check; this
# regression is a complementary, more quantitative second look, not a
# replacement.

# %%
z = lambda s: (s - s.mean()) / s.std()
fe_z = z(panel["abs_fe"])
slope_z = z(panel["slope"])
y_var = panel["abs_correction"].to_numpy()

X = np.column_stack([np.ones(len(panel)), fe_z, slope_z, fe_z * slope_z])
beta, _, _, _ = np.linalg.lstsq(X, y_var, rcond=None)
resid = y_var - X @ beta
n, k = X.shape
sigma2 = (resid @ resid) / (n - k)
cov = sigma2 * np.linalg.inv(X.T @ X)
se = np.sqrt(np.diag(cov))
t_stats = beta / se
r2 = 1 - (resid @ resid) / ((y_var - y_var.mean()) @ (y_var - y_var.mean()))

labels = ["const", "|forecast_error| (z)", "slope (z)", "|forecast_error| x slope (z*z)"]
print(f"R^2 = {r2:.4f}   n = {n:,}")
for lbl, b, s, t in zip(labels, beta, se, t_stats):
    print(f"  {lbl:32s}  beta={b:8.3f}  se={s:6.3f}  t={t:7.2f}")

# %% [markdown]
# ## Takeaways
#
# **The hypothesis as stated -- a steep merit order *amplifies* the price
# reaction to a given forecast-error size -- is not confirmed.** The
# interaction term comes out small and *negative* (β ≈ -1.12, t ≈ -3.25):
# if anything, an extra unit of forecast error moves the price slightly
# *less* on steep-slope hours than on flat-slope hours, not more.
#
# **But a different, real pattern showed up instead: a strong *level* effect,
# not an *amplification* effect.** In the binned-scatter view, the three
# slope-tercile lines start far apart even at near-zero forecast error
# (high-slope hours ≈ 35 EUR/MWh mean correction, low-slope hours ≈ 17) and
# *converge* rather than fan out as forecast error grows -- high-slope hours
# are already volatile regardless of forecast error size, but each
# additional MW of forecast error buys less extra correction there than on a
# calm, flat-slope hour. Plausible reasons, not distinguished by this
# notebook:
# - **Steep-slope hours cluster at the residual-load tails** (near-zero or
#   very high, see `18_merit_order_slope.png`) -- exactly where day-ahead
#   prices are already closer to their technical bounds (floor currently
#   -500 EUR/MWh, seen in the data's own min), which mechanically caps how
#   much *further* an incremental forecast-error MW can still move the price.
# - **Steep-slope hours may simply be volatile for reasons unrelated to
#   wind/solar forecast error specifically** -- plant outages, demand
#   surprises, cross-border flow changes -- all folded into ID-AEP but not
#   into this notebook's `forecast_error` variable, which only covers
#   wind+solar.
# - **Diminishing marginal sensitivity**: a market already pricing in a lot
#   of uncertainty (steep/extreme hours) may react relatively less to one
#   more piece of surprise than a calm market reacting to its first.
# - **R² = 0.02 throughout** -- forecast error and merit-order slope
#   together explain very little of `|ID-AEP - day-ahead|`'s total variance.
#   ID-AEP absorbs everything that happens between gate closure and T-5min,
#   not just renewable forecast error -- treat every number above as a real
#   but modest signal within a much noisier whole, not a tight relationship.
# - **Not addressed here**: the year-to-year merit-order drift is visible
#   and economically sensible (2022's gas-price-shock curve sits visibly
#   above every other year in `18_revealed_merit_order.png`), which is
#   exactly why slope was estimated per-year rather than pooled -- but no
#   further check was done on whether 40 quantile bins/year is the "right"
#   smoothing choice, or how sensitive the result is to that.

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
# # When the balancing market sends a "non-fundamental" price signal
#
# Inspired by a SAMAWATT marketing chart (`literature/imbalance_price_signal.jpeg`)
# that highlights days where the German balancing-energy price (reBAP) swings
# far above or below the day-ahead price within a single day — a signal driven
# by real-time system imbalance, not by day-ahead fundamentals. This notebook
# asks: can we find and plot the same kind of day from data this platform
# already has?
#
# **Answer: yes, closely.** `09_nrv_saldo_vs_rebap.py` already joins the three
# series this needs — reBAP, day-ahead price (`smard_price_de_lu`, hourly,
# forward-filled to 15-min — the day-ahead price genuinely applies uniformly
# across its whole hour), and NRV-Saldo (Germany's aggregate real-time
# imbalance in MW) — all three `energy-data-hub` assets (`balancing_market`/
# `smard` groups) — this notebook just picks specific days and lays them out
# the way the SAMAWATT chart does, instead of looking at the whole
# clean-year panel at once.
#
# **Two honest differences from the original, not hidden:**
# - The original's red line is explicitly a *provisional* ("Schätzer",
#   published within ~30 minutes) reBAP estimate, current to within days. We
#   only have the *quality-assured* ("qualitätsgesichert") reBAP, which carries
#   a real ~2-week publication lag — so the three days below are deliberately
#   picked from the past, not "the last two weeks" the way the original frames
#   it. Building a page that works on near-real-time data would need a new
#   downloader for netztransparenz.de's early-estimate endpoint, not yet built
#   anywhere in this platform.
# - Day-ahead price here is hourly (forward-filled to a 15-min grid), not a
#   genuine 15-min auction price — `energy-data-hub`'s SMARD asset hardcodes
#   `resolution="hour"` by design (see its own docstring); getting real 15-min
#   day-ahead prices would mean changing that asset, not something this
#   exploratory notebook does.
#
# The three days below were selected, not randomly sampled: out of every
# complete clean-year day (see `09`'s own gap-year exclusions), these are
# among the largest reBAP swings that still stay within a plausible,
# non-capacity-reserve-outlier price range (reBAP bounded to roughly
# [-700, +900] EUR/MWh, matching the original chart's own axis) — a small
# number of quarter-hours (capacity-reserve/"KapRes" activations) spike
# reBAP into the thousands of EUR/MWh and were excluded as a different
# phenomenon, not a sharper example of the same one.

# %%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

# Same series identity colors as `07_balancing_market_prices.py` /
# `09_nrv_saldo_vs_rebap.py` -- reused unchanged so the same series reads as
# the same color everywhere in this book (color follows the entity, not the
# page it appears on).
DA_COLOR = "#2a78d6"
REBAP_COLOR = "#8e44ad"
NRV_COLOR = "#d35400"
NEUTRAL = "#898781"

# Picked from the full clean-year panel (see markdown above) -- diverse
# seasons/years, all with a complete 96-quarter-hour day on all three series.
SELECTED_DAYS = ["2023-01-10", "2024-07-05", "2024-12-10"]

# %% [markdown]
# ## Data
#
# Same join as `09_nrv_saldo_vs_rebap.py`: reBAP and NRV-Saldo are natively
# 15-min; day-ahead is forward-filled from hourly onto the same grid.

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

panel = pd.DataFrame({
    "day_ahead": day_ahead_15min["price_de_lu"],
    "rebap": rebap["rebap_eur_mwh"],
    "nrv_saldo_mw": nrv["nrv_saldo_mw"],
}).dropna()
# "Imbalance volume" the way the SAMAWATT chart defines it: average imbalance
# power (MW) x 0.25h -- an energy quantity per quarter-hour, not a power level.
panel["imbalance_volume_mwh"] = panel["nrv_saldo_mw"] * 0.25

for day in SELECTED_DAYS:
    n = len(panel.loc[day:day])
    assert n == 96, f"{day}: expected 96 complete quarter-hours, got {n}"

print(f"Panel: {len(panel):,} quarter-hours ({panel.index.min()} -> {panel.index.max()})")
print(f"Selected days: {SELECTED_DAYS}")

# %% [markdown]
# ## Three days, side by side
#
# Top row: day-ahead price (blue) vs. reBAP (purple), same EUR/MWh axis,
# shared across all three panels so the days are visually comparable, not
# just individually readable. Bottom row: the imbalance-volume bars, same
# MWh/15min axis across all three. Each column gets its own DA/IB high/low
# header, the same four numbers the SAMAWATT chart leads with.
#
# **One deliberate deviation from the original, following this platform's
# own chart conventions (`references/anti-patterns.md`'s "never a dual-axis
# chart"):** price and imbalance volume are two stacked panels with their own
# axis each, not one panel with two y-axes — the same choice `09`'s own
# price/NRV-Saldo overlay already made.

# %%
day_frames = {day: panel.loc[day:day] for day in SELECTED_DAYS}

price_lo = min(min(df["day_ahead"].min(), df["rebap"].min()) for df in day_frames.values())
price_hi = max(max(df["day_ahead"].max(), df["rebap"].max()) for df in day_frames.values())
price_pad = 0.08 * (price_hi - price_lo)
vol_lo = min(df["imbalance_volume_mwh"].min() for df in day_frames.values())
vol_hi = max(df["imbalance_volume_mwh"].max() for df in day_frames.values())
vol_pad = 0.12 * (vol_hi - vol_lo)

fig, axes = plt.subplots(
    2, 3, figsize=(15, 7), sharex="col", height_ratios=[2, 1],
    gridspec_kw={"hspace": 0.08, "wspace": 0.12},
)

for col, day in enumerate(SELECTED_DAYS):
    df = day_frames[day]
    ax_price, ax_vol = axes[0, col], axes[1, col]

    ax_price.step(df.index, df["day_ahead"], where="post", color=DA_COLOR, linewidth=1.6, label="Day-ahead")
    ax_price.step(df.index, df["rebap"], where="post", color=REBAP_COLOR, linewidth=1.6, label="reBAP")
    ax_price.axhline(0, color=NEUTRAL, linewidth=0.7)
    ax_price.set_ylim(price_lo - price_pad, price_hi + price_pad)
    ax_price.yaxis.grid(True, linewidth=0.4, alpha=0.6)
    ax_price.set_axisbelow(True)

    da_hi_t, da_lo_t = df["day_ahead"].idxmax(), df["day_ahead"].idxmin()
    ib_hi_t, ib_lo_t = df["rebap"].idxmax(), df["rebap"].idxmin()
    for t, series_col, color in [(da_hi_t, "day_ahead", DA_COLOR), (da_lo_t, "day_ahead", DA_COLOR),
                                  (ib_hi_t, "rebap", REBAP_COLOR), (ib_lo_t, "rebap", REBAP_COLOR)]:
        ax_price.scatter([t], [df.loc[t, series_col]], color=color, s=28, zorder=3, edgecolor="white", linewidth=0.8)

    header = (
        f"{pd.Timestamp(day):%a, %d %b %Y}\n"
        f"DA high {df['day_ahead'].max():.0f} ({da_hi_t:%H:%M})  ·  DA low {df['day_ahead'].min():.0f} ({da_lo_t:%H:%M})\n"
        f"IB high {df['rebap'].max():.0f} ({ib_hi_t:%H:%M})  ·  IB low {df['rebap'].min():.0f} ({ib_lo_t:%H:%M})"
    )
    ax_price.set_title(header, fontsize=9.3, color="#3a3a36", linespacing=1.5)

    bar_colors = np.where(df["imbalance_volume_mwh"] >= 0, NRV_COLOR, NRV_COLOR)
    ax_vol.bar(df.index, df["imbalance_volume_mwh"], width=1 / 96, color=bar_colors, alpha=0.75, align="edge")
    ax_vol.axhline(0, color=NEUTRAL, linewidth=0.7)
    ax_vol.set_ylim(vol_lo - vol_pad, vol_hi + vol_pad)
    ax_vol.yaxis.grid(True, linewidth=0.4, alpha=0.6)
    ax_vol.set_axisbelow(True)
    ax_vol.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax_vol.set_xlim(pd.Timestamp(day), pd.Timestamp(day) + pd.Timedelta(days=1))

    if col == 0:
        ax_price.set_ylabel("Price [EUR/MWh]")
        ax_vol.set_ylabel("Imbalance volume\n[MWh/15min]")
    else:
        ax_price.tick_params(labelleft=False)
        ax_vol.tick_params(labelleft=False)

handles, labels = axes[0, 0].get_legend_handles_labels()
fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.04), fontsize=10)
fig.suptitle(
    "Three days where reBAP decoupled sharply from the day-ahead price",
    fontsize=13.5, y=1.12, fontweight="bold",
)
fig.tight_layout()
fig.savefig(paths.images_path / "14_imbalance_signal_days.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/14_imbalance_signal_days.png
# :name: fig-14-imbalance-signal-days
# Day-ahead price vs. reBAP (top) and imbalance volume (bottom), three
# selected days. Dots mark each day's own DA/IB high and low.
# ```

# %% [markdown]
# ## Reading the three days
#
# All three show the same qualitative pattern the original SAMAWATT chart
# is built to highlight: the imbalance-volume bars swing hard in one
# direction for a stretch of hours, and reBAP (purple) pulls away from the
# day-ahead price (blue) in the matching direction at the same time — exactly
# the spread-tracks-imbalance relationship `09_nrv_saldo_vs_rebap.py`
# quantified across the full clean-year panel (93.7% same-sign quarter-hours,
# r ≈ 0.35). None of these three needed cherry-picking beyond the plausible-
# range filter described above — large reBAP/day-ahead decoupling on a given
# day is not a rare curiosity in this dataset, it shows up reliably once
# NRV-Saldo swings far enough from zero.

# %% [markdown]
# ## What it would take to match the original exactly
#
# - **Near-real-time instead of ~2-weeks-old:** build a downloader for
#   netztransparenz.de's early "Schätzer" reBAP/NRV-Saldo endpoints (same
#   `CsvDownloadHandler.ashx` LotesCharts mechanism as `edh/rebap.py`,
#   different `ProduktId`/`WebApiRoute` — not yet identified). Not the same
#   as ID-AEP's own near-zero lag (see `16_id_aep_vs_rebap_spread.py`) --
#   that's a different series with a genuinely different publication
#   timeline, not a faster version of reBAP/NRV-Saldo itself.
# - **True 15-min day-ahead price:** change `energy-data-hub`'s
#   `smard_price_de_lu` asset to request `resolution="quarterhour"` instead
#   of the hardcoded `"hour"` (the underlying client already supports the
#   parameter, see `edh/smard.py`).
# - ~~Promote NRV-Saldo into the hub as a real Dagster asset~~ -- done
#   2026-10-05 (`nrv_saldo`, `balancing_market` group, `data_derived_watermark`
#   load pattern, gap check WARN-severity for its known multi-month missing
#   stretches); this notebook already reads it from there.

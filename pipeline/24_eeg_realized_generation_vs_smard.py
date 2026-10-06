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
# # Is SMARD's wind/solar generation before or after Engpassmanagement?
#
# **Follow-up to the 2026-09-30 finding** (see `PROJECT.md`): netztransparenz.de's
# own documentation says SMARD's "realisierte Erzeugung" for wind/solar leans on
# a regulated "Online-Hochrechnung" for the many small, non-telemetered plants
# that is legally required (since Jan 2015) to **exclude** grid-driven
# curtailment (Einspeisemanagement/Redispatch) -- i.e. it reports
# theoretical-max output, not real net feed-in, for that segment. That finding
# was textual. This notebook checks it against real numbers, using a data
# source that only exists with a ~9-month lag: the EEG annual settlement
# ("Jahresabrechnung") movement data the four transmission operators (UENBs)
# publish for the electricity they actually paid EEG compensation on --
# downloaded and aggregated in `23_download_eeg_bewegungsdaten.py` (see that
# script's docstring for the full source/column breakdown).
#
# **Three independent 2025, Germany-wide numbers, per technology:**
# 1. **SMARD's own reported generation** (`hub_file("smard", "generation_*")`,
#    summed over the year) -- the number under test.
# 2. **EEG settlement, "clean" actual-delivered** (`Veraeusserungsform` 1+2+3:
#    Einspeiseverguetung + Marktpraemie + Mieterstromzuschlag) -- unambiguously
#    real, metered, already-happened feed-in.
# 3. **EEG settlement, all quantity-bearing rows** (adds `Veraeusserungsform` 5,
#    "Sonstiges" -- a mixed bucket that, per netztransparenz.de's legend,
#    includes real generation from `ausgefoerdert` (expired-support) plants
#    doing merchant sales, not just financial-only line items; `(1)` above
#    explicitly bills itself as "ohne Wertersatz fuer ausgefoerderte Anlagen",
#    so that volume is genuinely missing from `(2)`, not just hard to quantify).
# 4. **Real curtailment volume**: not taken from the EEG settlement's own
#    `Veraeusserungsform=4` ("Ausfallverguetung") -- that number turned out to
#    be two orders of magnitude below published curtailment statistics (a few
#    GWh/year nationally, vs. the few-TWh/year everyone else reports), implying
#    most modern (market-premium-route) turbines' curtailment compensation
#    isn't booked under that category. Used instead: the hub's own
#    `smard_redispatch_by_source` asset -- SMARD's *official* monthly
#    redispatch-by-source series, already ingested, direction="reduction".
#
# **The test:** does SMARD's reported generation sit closer to (2)+(curtailment)
# excluded i.e. just the clean actual, or closer to (3)+(4) -- the full
# reconciled gross/theoretical-max figure?

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

SMARD_COLOR = "#2a78d6"      # "official" reported number
EEG_CLEAN_COLOR = "#1b8a5a"  # unambiguous real metered quantity
EEG_GROSS_COLOR = "#d35400"  # reconciled: all settlement buckets + curtailment
NEUTRAL = "#898781"

TECHS = ["wind_onshore", "wind_offshore", "solar"]
TECH_LABELS = {"wind_onshore": "Wind Onshore", "wind_offshore": "Wind Offshore", "solar": "Solar"}
SMARD_FILES = {
    "wind_onshore": "generation_wind_onshore.parquet",
    "wind_offshore": "generation_wind_offshore.parquet",
    "solar": "generation_solar.parquet",
}
REDISPATCH_SOURCE = {"wind_onshore": "Wind_Onshore", "wind_offshore": "Wind_Offshore", "solar": "Photovoltaik"}
YEAR = 2025

# %% [markdown]
# ## 1. SMARD's own reported generation, full-year 2025

# %%
smard_generation_twh = {}
for tech, fname in SMARD_FILES.items():
    df = pd.read_parquet(hub_file("smard", fname))
    year_data = df.loc[f"{YEAR}-01-01":f"{YEAR}-12-31 23:00"]
    smard_generation_twh[tech] = year_data.iloc[:, 0].sum() / 1e6  # hourly MW -> MWh -> TWh

print(pd.Series(smard_generation_twh, name="SMARD reported (TWh)").round(2))

# %% [markdown]
# ## 2. EEG settlement: actual-delivered vs. all quantity-bearing buckets
#
# Loads `23_download_eeg_bewegungsdaten.py`'s aggregate (one row per UENB x
# `Energietraeger` x `Veraeusserungsform` x `Monat`) and collapses it to one
# annual TWh figure per technology, per settlement bucket.

# %%
eeg = pd.read_parquet(paths.eeg_bewegungsdaten_aggregated_file)
eeg_tech = eeg[eeg["energietraeger_label"].isin(TECHS)]

pivot = (
    eeg_tech.groupby(["energietraeger_label", "veraeusserungsform"], dropna=False)["strommenge_kwh"]
    .sum()
    .unstack()
    .reindex(TECHS)
    .fillna(0.0)
    / 1e9  # kWh -> TWh (1 TWh = 1e9 kWh)
)
pivot.columns = [str(c) for c in pivot.columns]

eeg_clean_twh = (pivot[["1", "2", "3"]].sum(axis=1)).to_dict()
# "Sonstiges" (5) + join-unmatched rows, both real quantity, see module docstring
eeg_all_buckets_twh = (pivot[["1", "2", "3", "5"]].sum(axis=1) + pivot.get("<NA>", 0.0)).to_dict()

print(pd.DataFrame({"eeg_clean_1_2_3": eeg_clean_twh, "eeg_all_buckets": eeg_all_buckets_twh}).round(2))

# %% [markdown]
# ## 3. Real curtailment: SMARD's own redispatch-by-source series
#
# Already ingested in the hub (`edh_dagster/assets/redispatch.py`) -- SMARD's
# official monthly curtailment-by-energy-source breakdown, `direction="reduction"`.

# %%
redispatch = pd.read_parquet(hub_file("redispatch", "smard_redispatch_by_source.parquet"))
r_year = redispatch[
    (redispatch["month"] >= f"{YEAR}-01-01")
    & (redispatch["month"] < f"{YEAR + 1}-01-01")
    & (redispatch["direction"] == "reduction")
]
curtailment_twh = (r_year.groupby("energy_source")["gwh"].sum() / 1e3).to_dict()
curtailment_by_tech = {tech: curtailment_twh[REDISPATCH_SOURCE[tech]] for tech in TECHS}

print(pd.Series(curtailment_by_tech, name="Curtailed, reduction (TWh)").round(2))

# %% [markdown]
# ## 4. Reconciliation table

# %%
table = pd.DataFrame({
    "smard_reported": smard_generation_twh,
    "eeg_clean_actual": eeg_clean_twh,
    "eeg_all_buckets": eeg_all_buckets_twh,
    "curtailed_redispatch": curtailment_by_tech,
}).reindex(TECHS)
table["eeg_reconciled_gross"] = table["eeg_all_buckets"] + table["curtailed_redispatch"]
table["smard_vs_clean_actual_pct"] = (table["smard_reported"] / table["eeg_clean_actual"] - 1) * 100
table["smard_vs_reconciled_gross_pct"] = (table["smard_reported"] / table["eeg_reconciled_gross"] - 1) * 100
print(table.round(2).to_string())

# %% [markdown]
# ## 5. Chart: three independent estimates, per technology

# %%
fig, ax = plt.subplots(figsize=(10, 6))

x = np.arange(len(TECHS))
width = 0.26

bars_smard = ax.bar(x - width, table["smard_reported"], width, label="SMARD reported", color=SMARD_COLOR)
bars_clean = ax.bar(x, table["eeg_clean_actual"], width, label="EEG settlement: clean actual-delivered", color=EEG_CLEAN_COLOR)
bars_gross = ax.bar(x + width, table["eeg_reconciled_gross"], width, label="EEG settlement: reconciled gross (+ curtailment)", color=EEG_GROSS_COLOR)

for bars in (bars_smard, bars_clean, bars_gross):
    ax.bar_label(bars, fmt="%.1f", padding=2, fontsize=9, color="#3a3a3a")

ax.set_xticks(x)
ax.set_xticklabels([TECH_LABELS[t] for t in TECHS])
ax.set_ylabel("2025 annual volume [TWh]")
ax.set_title("SMARD's reported generation vs. EEG-settlement-based real quantities, 2025")
ax.legend(frameon=False, loc="upper left")
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", color=NEUTRAL, alpha=0.25)

fig.tight_layout()
fig.savefig(paths.images_path / "24_smard_vs_eeg_settlement.png", dpi=150)
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/24_smard_vs_eeg_settlement.png
# :name: fig-24-smard-vs-eeg-settlement
# SMARD's reported 2025 generation (blue) against two EEG-settlement-based
# real quantities: the unambiguous actual-delivered feed-in (green) and that
# figure reconciled up with the harder-to-categorize settlement buckets plus
# SMARD's own officially reported curtailment (orange). For onshore wind and
# solar, SMARD's number lines up with the *reconciled gross* bar, not the
# clean actual-delivered one. For offshore wind, it's the other way round.
# ```

# %% [markdown]
# ## 6. The more careful test: does adding curtailment close the gap, or not?
#
# The chart above compares SMARD against a *reconciled* EEG figure that
# already includes the ambiguous "Sonstiges" bucket, which makes the three
# technologies look inconsistent (onshore/solar need curtailment added back
# to match; offshore already matches without it). That's misleading, because
# it conflates two different questions. The cleaner test: starting from the
# **unambiguous** actual-delivered quantity alone (`Veraeusserungsform`
# 1+2+3, no "Sonstiges"), does adding real curtailment move *towards* SMARD
# or *away* from it -- for every technology, not just two of them?

# %%
gap_table = pd.DataFrame({
    "smard_reported": table["smard_reported"],
    "eeg_clean_actual": table["eeg_clean_actual"],
    "eeg_clean_plus_curtailment": table["eeg_clean_actual"] + table["curtailed_redispatch"],
})
gap_table["gap_clean_only"] = gap_table["smard_reported"] - gap_table["eeg_clean_actual"]
gap_table["gap_after_curtailment"] = gap_table["smard_reported"] - gap_table["eeg_clean_plus_curtailment"]
gap_table["pct_of_gap_closed_by_curtailment"] = (
    100 * (1 - gap_table["gap_after_curtailment"] / gap_table["gap_clean_only"])
)
print(gap_table.round(2).to_string())

# %% [markdown]
# **For all three technologies, adding curtailment shrinks the gap to
# SMARD -- it never overshoots or reverses it.** Onshore closes ~15% of the
# gap, solar ~18%, offshore ~48% (the most, not the least). SMARD's reported
# generation is *never* at or below "actual-delivered + curtailment" for any
# of the three -- which is exactly what you'd expect if SMARD excludes
# curtailment everywhere, and never what you'd expect if it were already
# net-of-curtailment for any of them.
#
# Offshore's remaining post-curtailment gap (~3.7 TWh, the largest share
# still unexplained) has a likely explanation specific to this technology:
# `Veraeusserungsform=4` ("Ausfallverguetung", the settlement's own
# curtailment-compensation line) is **exactly zero** for offshore wind in
# this entire dataset -- offshore is ~100% Marktpraemie (direct-marketed),
# never Einspeiseverguetung, and Ausfallverguetung is the older FIT-era
# category. Its real curtailment compensation has to be booked somewhere,
# and with category 4 empty, "Sonstiges" (category 5) is the only place left
# -- which is also why offshore's *clean-actual + Sonstiges* figure already
# lands almost exactly on SMARD's number in the chart above: that comparison
# was accidentally already curtailment-inclusive for this technology,
# not curtailment-free.

# %% [markdown]
# ## 7. Cross-check against PECD potential -- does this contradict the
#    older `pecd-power-validity-DE` finding?
#
# That project compared PECD-capacity-factor-derived "potential" output
# against SMARD observed generation and found that *subtracting* reported
# redispatch curtailment from potential measurably improved the match
# (e.g. onshore nMAE 13.9% -> 6.7%, redispatch "explaining" 33.3% of the
# gap; offshore 24.8% -> 8.0%/70.7%). Taken at face value that look like
# the opposite conclusion from this notebook's: if subtracting curtailment
# from the *higher* number (potential) gets closer to SMARD, doesn't that
# mean SMARD is already net of curtailment? Worth checking directly rather
# than leaving the two notebooks disagreeing.

# %%
pecd_potential_twh = {}
for tech, col in [
    ("wind_onshore", "potential_wind_onshore_mw"),
    ("wind_offshore", "potential_wind_offshore_mw"),
    ("solar", "potential_solar_mw"),
]:
    pecd_df = pd.read_parquet(hub_file("pecd", "de_potential_historic.parquet"))
    pecd_year = pecd_df.loc[f"{YEAR}-01-01":f"{YEAR}-12-31 23:00"]
    pecd_potential_twh[tech] = pecd_year[col].sum() / 1e6

cross_check = pd.DataFrame({
    "pecd_potential": pecd_potential_twh,
    "smard_reported": table["smard_reported"],
    "eeg_reconciled_gross": table["eeg_reconciled_gross"],
    "curtailment": table["curtailed_redispatch"],
}).reindex(TECHS)
cross_check["pecd_minus_smard"] = cross_check["pecd_potential"] - cross_check["smard_reported"]
cross_check["pecd_minus_smard_plus_curtailment"] = cross_check["pecd_potential"] - cross_check["smard_reported"] - cross_check["curtailment"]
print(cross_check.round(2).to_string())

# %% [markdown]
# **PECD's potential sits 6-22 TWh above SMARD -- 2 to 8x the curtailment
# volume itself.** Curtailment can only ever be a *minority* contributor to
# the PECD-vs-SMARD gap (consistent with `pecd-power-validity-DE`'s own
# published explained-shares: 33% onshore, 71% offshore, 11% solar -- they
# never claimed curtailment closed the whole gap; the rest was attributed to
# unavailability/outages and, for solar, behind-the-meter self-consumption).
# Subtracting any real, positive quantity that correlates with high-output
# hours (curtailment binds hardest exactly when potential output is
# highest) will *mechanically* shrink an already-oversized gap's MAE/nMAE
# somewhat, regardless of whether SMARD's own accounting nets curtailment
# out or not -- that project's "subtracting redispatch improves the match"
# result is real, but it is not a clean test of SMARD's net-vs-gross status
# the way this notebook's EEG-settlement comparison is: PECD's own
# potential carries independent upward bias (no outage modeling, no
# self-consumption modeling, weather-model error) large enough to swamp the
# curtailment-sized signal this notebook is trying to isolate. Its README's
# own processing diagram states "SMARD reports net generation" as an
# **assumed premise**, not something it set out to test against ground
# truth -- this notebook's EEG settlement data is the first ground-truth
# check of that specific assumption.
#
# Where the two analyses *do* agree, notably: **offshore wind is the
# technology where curtailment explains the most of any gap, in both**
# (71% of the PECD-vs-SMARD gap there; 48% of the SMARD-vs-EEG-clean gap
# here) -- genuine convergence, not a conflict.

# %% [markdown]
# ## Takeaways
#
# - **Curtailment alone is a modest, not dominant, driver of why SMARD sits
#   above the EEG settlement's clean actual-delivered quantity -- except for
#   offshore, where it's the main driver.** It closes only ~15% of the
#   onshore gap and ~18% of solar's; the other 80%+ is the settlement's
#   broader "Sonstiges" bucket (plausibly `ausgefoerdert`/merchant real
#   generation that `Einspeiseverguetung`'s own definition explicitly
#   excludes, nothing to do with curtailment). For offshore, curtailment
#   closes ~48% of the gap -- by far the largest share of any technology,
#   and offshore's `Ausfallverguetung` settlement category being *exactly
#   zero* suggests its curtailment compensation is booked inside "Sonstiges"
#   instead, meaning the true curtailment-explained share there is probably
#   even higher than 48%.
# - **But no technology shows evidence of SMARD being net-of-curtailment.**
#   The one clean, assumption-light test: adding real curtailment on top of
#   the fullest real-generation estimate available (`eeg_all_buckets`, i.e.
#   clean actual-delivered + "Sonstiges") never overshoots SMARD's reported
#   number for any of the three technologies -- it lands within ~1% for
#   onshore and solar, and still ~2.7 TWh short for offshore. If SMARD were
#   already net of curtailment, adding real curtailment on top of a
#   reasonably complete real-generation estimate should overshoot it
#   noticeably; it doesn't, anywhere.
# - **Cross-checked against the older `pecd-power-validity-DE` finding
#   (section 7) -- no actual contradiction, once magnitudes are compared
#   side by side.** That project's "subtracting redispatch improves the
#   PECD-vs-SMARD match" result is real, but redispatch explains only a
#   minority of *that* gap too (33% onshore, 11% solar, 71% offshore, by
#   its own numbers) -- PECD's potential carries its own independent
#   upward bias (no outage modeling, no self-consumption modeling, weather
#   bias) large enough to swamp the curtailment-sized effect, so an
#   improved fit there doesn't actually prove SMARD nets curtailment out;
#   it's equally consistent with SMARD being gross and PECD simply being
#   biased further high for unrelated reasons. That project's own
#   "SMARD reports net generation" diagram was a stated assumption, not a
#   tested result -- this notebook's EEG settlement data is the first
#   ground-truth check of it. Offshore is where both analyses most clearly
#   agree: curtailment explains the largest share of the gap there in both.
# - **Overall reading: SMARD's wind/solar generation series leans
#   pre-curtailment / theoretical-max, most clearly so for offshore wind**,
#   with onshore/solar's evidence pointing the same direction but with
#   curtailment itself playing a smaller, supporting role next to broader
#   settlement-coverage effects.
# - **Caveat:** the EEG settlement only covers EEG-support-eligible plants,
#   and "Sonstiges" mixes several things (ausgefoerdert-plant merchant sales,
#   flexibility premia, non-compensated self-consumption, and apparently
#   offshore's curtailment compensation) that aren't individually separable
#   here -- the reconciliation holds up well in aggregate, not as a precise
#   per-category audit.
#
# **Update 2026-10-06, see `25_eeg_veraeusserungsform_categories.py`:** that
# follow-up decomposes `Veraeusserungsform` further and revises the
# "offshore is the clearest pre-curtailment case" framing above. Measured
# against the *full* EEG settlement total (all categories) rather than the
# narrow 1+2+3 slice used here, offshore's SMARD figure sits almost exactly
# on the full EEG total *alone* -- adding real curtailment on top
# overshoots it by ~13%. Offshore turns out to be the one technology that
# looks net-of-curtailment, not gross; onshore/solar's gross/pre-curtailment
# reading still holds against that fuller benchmark. See `25`'s own
# Takeaways for the full argument.

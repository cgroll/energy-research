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
# # What's actually inside the EEG settlement's `Veraeusserungsform` categories?
#
# **Follow-up to `24_eeg_realized_generation_vs_smard.py`** (conversation
# 2026-10-06, continued). That notebook compared SMARD's reported 2025
# generation against the EEG annual settlement ("Jahresabrechnung")
# Bewegungsdaten, bucketed by `Veraeusserungsform` (1 Einspeiseverguetung, 2
# Marktpraemie, 3 Mieterstromzuschlag, 4 Ausfallverguetung, 5 "Sonstiges").
# Two things it used without digging in stayed unexplained: why `4`
# (Ausfallverguetung, nominally the settlement's *own* curtailment-
# compensation line) is two orders of magnitude below real curtailment, and
# what the large "Sonstiges" (5) bucket -- bigger than categories 1 and 4
# combined -- actually consists of. This notebook digs into both, re-reads
# the raw per-UENB Bewegungsdaten CSVs (not just `23_download_...`'s
# aggregate, which drops the payment columns and the `Verguetungskategorie`
# sub-code) to decompose them, and **revises one of `24`'s own headline
# conclusions** in the process (see Takeaways).

# %%
import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from erx.paths import ProjPaths, hub_file

paths = ProjPaths()
paths.ensure_directories()

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"
MAGENTA = "#e87ba4"
GREEN = "#008300"
VIOLET = "#4a3aa7"
RED = "#e34948"
NEUTRAL = "#898781"

YEAR = 2025
TECHS = ["wind_onshore", "wind_offshore", "solar"]
TECH_LABELS = {"wind_onshore": "Wind Onshore", "wind_offshore": "Wind Offshore", "solar": "Solar"}

BEWEG_GLOB = str(paths.eeg_bewegungsdaten_raw_dir / "*" / "bewegungsdaten" / "**" / "*.csv")

# %% [markdown]
# ## 1. What each `Veraeusserungsform` code actually settles
#
# Re-reads the raw Bewegungsdaten (not the aggregate, which drops
# `EEG_Zahlung`/`EEG_Einnahmen`) and sums quantity *and* both payment
# columns per code, nationally, across all four UENBs.

# %%
con = duckdb.connect()

by_code = con.sql(f"""
    SELECT
        Veraeusserungsform AS code,
        sum(CAST(replace(Strommenge, ',', '.') AS DOUBLE)) / 1e9 AS strommenge_twh,
        sum(CAST(replace(EEG_Zahlung, ',', '.') AS DOUBLE)) / 1e6 AS zahlung_mio_eur,
        sum(CAST(replace(EEG_Einnahmen, ',', '.') AS DOUBLE)) / 1e6 AS einnahmen_mio_eur,
        count(*) AS n_rows
    FROM read_csv(
        '{BEWEG_GLOB}', delim=';', header=true, union_by_name=true,
        quote='"', escape='"', ignore_errors=true,
        types={{'Veraeusserungsform': 'VARCHAR', 'Strommenge': 'VARCHAR',
                'EEG_Zahlung': 'VARCHAR', 'EEG_Einnahmen': 'VARCHAR'}}
    )
    GROUP BY 1
    ORDER BY 1
""").df()

CODE_LABELS = {
    "1": "1 Einspeiseverguetung (Festverguetung)",
    "2": "2 Marktpraemie (gefoerderte Direktvermarktung)",
    "3": "3 Mieterstromzuschlag",
    "4": "4 Ausfallverguetung (Abregelungsentschaedigung, alt)",
    "5": "5 Sonstiges (siehe Abschnitt 3)",
    None: "ohne Angabe (leeres Feld in den Rohdaten)",
}
by_code["label"] = by_code["code"].map(CODE_LABELS)
print(by_code[["label", "strommenge_twh", "zahlung_mio_eur", "einnahmen_mio_eur", "n_rows"]]
      .round(2).to_string(index=False))

# %% [markdown]
# Five numbered codes plus a sixth, undocumented bucket: rows where
# `Veraeusserungsform` is simply blank in the raw export. That blank bucket
# is not nothing -- nationally it is bigger (by quantity *and* payment) than
# categories 3 and 4 combined. `23_download_eeg_bewegungsdaten.py`'s
# aggregate silently keeps it (as a `NaN` group after `CAST ... AS INTEGER`);
# `24`'s `eeg_all_buckets` metric already included it via
# `pivot.get("<NA>", 0.0)`, just without calling it out explicitly.

# %% [markdown]
# ## 2. Category 4 ("Ausfallverguetung") vs. real curtailment
#
# `24` already found category 4 implausibly small next to published
# curtailment statistics. Here's the direct comparison, per technology,
# against SMARD's own official redispatch-by-source series (already used in
# `24` as the real-curtailment benchmark).

# %%
eeg = pd.read_parquet(paths.eeg_bewegungsdaten_aggregated_file)
ausfall_twh = (
    eeg[(eeg["veraeusserungsform"] == 4) & (eeg["energietraeger_label"].isin(TECHS))]
    .groupby("energietraeger_label")["strommenge_kwh"].sum().reindex(TECHS).fillna(0.0) / 1e9
)

redispatch = pd.read_parquet(hub_file("redispatch", "smard_redispatch_by_source.parquet"))
REDISPATCH_SOURCE = {"wind_onshore": "Wind_Onshore", "wind_offshore": "Wind_Offshore", "solar": "Photovoltaik"}
r_year = redispatch[
    (redispatch["month"] >= f"{YEAR}-01-01")
    & (redispatch["month"] < f"{YEAR + 1}-01-01")
    & (redispatch["direction"] == "reduction")
]
redispatch_twh = (r_year.groupby("energy_source")["gwh"].sum() / 1e3)
redispatch_by_tech = pd.Series({tech: redispatch_twh[REDISPATCH_SOURCE[tech]] for tech in TECHS})

fig, ax = plt.subplots(figsize=(8, 5.5))
x = np.arange(len(TECHS))
width = 0.32
bars_a = ax.bar(x - width / 2, redispatch_by_tech.values, width,
                 label="Redispatch gesamt (SMARD)", color=BLUE)
bars_b = ax.bar(x + width / 2, ausfall_twh.values, width,
                 label="davon mit Ausfallverguetung (EEG Kat. 4)", color=ORANGE)
ax.bar_label(bars_a, fmt="%.2f", padding=3, fontsize=10, color="#3a3a3a")
ax.bar_label(bars_b, fmt="%.2f", padding=3, fontsize=10, color="#3a3a3a")
ax.set_xticks(x)
ax.set_xticklabels([TECH_LABELS[t] for t in TECHS])
ax.set_ylabel("2025, Jahresvolumen [TWh]")
ax.set_title("Reale Abregelung (SMARD) vs. EEG-Ausfallverguetungsmenge, 2025")
ax.legend(frameon=False, loc="upper right")
ax.spines[["top", "right"]].set_visible(False)
ax.spines[["left", "bottom"]].set_color(NEUTRAL)
ax.grid(axis="y", color=NEUTRAL, alpha=0.25)
ax.set_ylim(0, redispatch_by_tech.max() * 1.25)
fig.tight_layout()
fig.savefig(paths.images_path / "25_ausfallverguetung_vs_redispatch.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/25_ausfallverguetung_vs_redispatch.png
# :name: fig-25-ausfallverguetung-vs-redispatch
# Real curtailment (SMARD's own redispatch-by-source statistic) vs. the
# EEG settlement's own curtailment-compensation line (`Veraeusserungsform`
# 4), 2025. The two have essentially nothing to do with each other --
# category 4 is one to two orders of magnitude too small, and exactly zero
# for offshore wind.
# ```
#
# Category 4 captures roughly 1.5% of real onshore curtailment, 5% of real
# solar curtailment, and 0% of real offshore curtailment. It is a FIT-era
# ("Einspeiseverguetung") settlement line; today's market-premium-route
# plants' curtailment compensation is clearly not booked under it.

# %% [markdown]
# ## 3. What's inside "Sonstiges" (category 5)?
#
# Category 5 is bigger than it looks (41.6 TWh nationally, more than
# category 1). Breaking it down by its `Verguetungskategorie` sub-code
# (stripping the 2-letter energy-carrier prefix, e.g. `Bi`=Biomasse,
# `So`=Solar) splits it into two almost entirely disjoint groups.

# %%
sub = con.sql(f"""
    SELECT
        Verguetungskategorie AS vk,
        CAST(replace(Strommenge, ',', '.') AS DOUBLE) AS strommenge_kwh,
        CAST(replace(EEG_Zahlung, ',', '.') AS DOUBLE) AS zahlung_eur,
        CAST(replace(EEG_Einnahmen, ',', '.') AS DOUBLE) AS einnahmen_eur
    FROM read_csv(
        '{BEWEG_GLOB}', delim=';', header=true, union_by_name=true,
        quote='"', escape='"', ignore_errors=true,
        types={{'Veraeusserungsform': 'VARCHAR', 'Strommenge': 'VARCHAR',
                'EEG_Zahlung': 'VARCHAR', 'EEG_Einnahmen': 'VARCHAR'}}
    )
    WHERE Veraeusserungsform = '5'
""").df()
sub["subcode"] = sub["vk"].str.slice(2)

by_sub = sub.groupby("subcode").agg(
    strommenge_twh=("strommenge_kwh", lambda s: s.sum() / 1e9),
    zahlung_mio_eur=("zahlung_eur", lambda s: s.sum() / 1e6),
    einnahmen_mio_eur=("einnahmen_eur", lambda s: s.sum() / 1e6),
).sort_values("strommenge_twh", ascending=False)

volume_group = by_sub[by_sub["strommenge_twh"] > 0.01]
money_group = by_sub[(by_sub["strommenge_twh"] <= 0.01)
                      & ((by_sub["zahlung_mio_eur"].abs() > 0.01) | (by_sub["einnahmen_mio_eur"].abs() > 0.01))]

print("-- volume-bearing sub-codes (quantity, ~zero payment) --")
print(volume_group.round(2).to_string())
print(f"\nsubtotal: {volume_group['strommenge_twh'].sum():.2f} TWh, "
      f"{volume_group['zahlung_mio_eur'].sum():.2f} Mio EUR Zahlung")

print("\n-- payment-bearing sub-codes (~zero quantity, real EUR) --")
print(money_group.round(2).to_string())
print(f"\nsubtotal: {money_group['zahlung_mio_eur'].sum():.2f} Mio EUR Zahlung, "
      f"{money_group['einnahmen_mio_eur'].sum():.2f} Mio EUR Einnahmen")

# %% [markdown]
# **The ~41.6 TWh of quantity and the ~473 Mio EUR of payments in category 5
# are almost entirely different line items, not the same transactions seen
# from two sides.** Two sub-codes alone -- `K33b3--SO-DV` ("sonstige
# Direktvermarktung") and `K33a2-----SV` ("sonstige Veraeusserung") --
# account for ~35 of the 41.6 TWh, with **zero EEG payment attached**: real,
# physically delivered electricity from plants selling merchant, outside any
# EEG subsidy (plausibly `ausgefoerdert`, support-expired plants, consistent
# with `24`'s hypothesis). The payment side is a grab-bag of specific
# financial-only mechanisms with negligible associated quantity: a biomass
# flexibility premium/surcharge (`FLP`/`FLZ`, >160 Mio EUR), something
# resembling "vermiedene Netznutzungsentgelte" (avoided grid-usage fees,
# `vNNe--SpE*`, >220 Mio EUR on its own), several `SZ`-coded items, and a
# sizeable negative correction (`AB`, -33 Mio EUR). **"Sonstiges" is really
# two unrelated categories sharing one code**, not one coherent bucket.

# %% [markdown]
# ## 4. The headline comparison: SMARD vs. the full EEG picture vs. real redispatch
#
# Puts all three numbers side by side per technology: SMARD's reported
# generation, the EEG settlement's full quantity (stacked by category, incl.
# the "ohne Angabe" bucket from section 1), and real curtailment from
# SMARD's own redispatch statistic.

# %%
smard_twh = {}
SMARD_FILES = {
    "wind_onshore": "generation_wind_onshore.parquet",
    "wind_offshore": "generation_wind_offshore.parquet",
    "solar": "generation_solar.parquet",
}
for tech, fname in SMARD_FILES.items():
    gdf = pd.read_parquet(hub_file("smard", fname))
    year_data = gdf.loc[f"{YEAR}-01-01":f"{YEAR}-12-31 23:00"]
    smard_twh[tech] = year_data.iloc[:, 0].sum() / 1e6

eeg_tech = eeg[eeg["energietraeger_label"].isin(TECHS)]
pivot = (
    eeg_tech.groupby(["energietraeger_label", "veraeusserungsform"], dropna=False)["strommenge_kwh"]
    .sum().unstack().reindex(TECHS) / 1e9
)
pivot.columns = [str(c) for c in pivot.columns]

cat_order = ["1", "2", "3", "4", "5", "<NA>"]
cat_display = ["1  Einspeiseverguetung", "2  Marktpraemie", "3  Mieterstromzuschlag",
               "4  Ausfallverguetung", "5  Sonstiges", "—  ohne Angabe"]
cat_colors = [ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET]

x = np.arange(len(TECHS))
width = 0.26

fig, ax = plt.subplots(figsize=(10.5, 6.4))

bars_smard = ax.bar(x - width, [smard_twh[t] for t in TECHS], width,
                     label="SMARD", color=BLUE, edgecolor="white", linewidth=0.6)
ax.bar_label(bars_smard, fmt="%.1f", padding=3, fontsize=9.5, color="#3a3a3a")

bottoms = np.zeros(len(TECHS))
for code, disp, color in zip(cat_order, cat_display, cat_colors):
    vals = pivot[code].fillna(0.0).values if code in pivot.columns else np.zeros(len(TECHS))
    bars = ax.bar(x, vals, width, bottom=bottoms, label=disp, color=color,
                   edgecolor="white", linewidth=0.6)
    for rect, v in zip(bars, vals):
        if v >= 3.5:
            ax.text(rect.get_x() + rect.get_width() / 2, rect.get_y() + v / 2,
                     f"{v:.1f}", ha="center", va="center", fontsize=8, color="white")
    bottoms += vals
for xi, tot in zip(x, bottoms):
    ax.text(xi, tot + 1.5, f"{tot:.1f}", ha="center", va="bottom", fontsize=9.5, color="#3a3a3a")

bars_redispatch = ax.bar(x + width, redispatch_by_tech.values, width,
                          label="Redispatch (SMARD-Statistik)", color=RED,
                          edgecolor="white", linewidth=0.6)
ax.bar_label(bars_redispatch, fmt="%.2f", padding=3, fontsize=9.5, color="#3a3a3a")

ax.set_xticks(x)
ax.set_xticklabels([TECH_LABELS[t] for t in TECHS])
ax.set_ylabel("2025, Jahresvolumen [TWh]")
ax.set_title("SMARD-Erzeugung vs. volle EEG-Daten (gestapelt) vs. Redispatch-Menge, 2025")
ax.legend(frameon=False, loc="upper left", fontsize=8.5, ncol=1, bbox_to_anchor=(1.01, 1.0))
ax.spines[["top", "right"]].set_visible(False)
ax.spines[["left", "bottom"]].set_color(NEUTRAL)
ax.grid(axis="y", color=NEUTRAL, alpha=0.25)
ax.set_ylim(0, max(smard_twh.values()) * 1.25)
fig.tight_layout()
fig.savefig(paths.images_path / "25_smard_vs_eeg_vs_redispatch.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/25_smard_vs_eeg_vs_redispatch.png
# :name: fig-25-smard-vs-eeg-vs-redispatch
# SMARD's reported 2025 generation, the full EEG settlement total (stacked
# by `Veraeusserungsform`), and real curtailment (SMARD's redispatch
# statistic), per technology.
# ```

# %%
gap = pd.Series(smard_twh) - bottoms
print("SMARD minus full EEG total (TWh):")
print(gap.round(2))
print("\nreal curtailment (TWh):")
print(redispatch_by_tech.round(2))
print("\ngap, net of curtailment (TWh) -- negative means curtailment overshoots:")
print((gap - redispatch_by_tech).round(2))

# %% [markdown]
# ## Takeaways
#
# - **The five `Veraeusserungsform` codes settle genuinely different legal
#   mechanisms**, not five slices of the same pie: 1/2/3 are real,
#   currently-subsidized, actually-metered feed-in (Festverguetung /
#   Marktpraemie / Mieterstrom); 4 is a FIT-era curtailment-compensation
#   line that today's market-premium plants evidently don't use (0-5% of
#   real curtailment, by technology, vs. SMARD's own redispatch numbers);
#   5 ("Sonstiges") turns out to be **two unrelated things sharing one
#   code** -- ~35 TWh of zero-payment, support-expired merchant generation,
#   plus a separate, small-quantity grab-bag of real payments (biomass
#   flex premia, avoided grid fees, corrections) worth several hundred
#   million EUR. A sixth, undocumented "ohne Angabe" bucket (blank field in
#   the raw export) is non-trivial too (bigger than categories 3+4
#   combined) and was already silently folded into `24`'s "all buckets"
#   total.
# - **Revises `24`'s own headline conclusion: the gross/pre-curtailment
#   reading does *not* hold uniformly across technologies.** Comparing
#   SMARD directly to the *full* EEG total (all categories, section 4)
#   rather than to the narrower "clean" 1+2+3 slice `24` used for its main
#   test: for onshore wind and solar, SMARD sits close to
#   *full EEG total + real curtailment* (within ~1%), consistent with a
#   gross/theoretical-max reading. **For offshore wind, SMARD sits almost
#   exactly on the full EEG total *alone* -- adding real curtailment on top
#   overshoots SMARD by ~3.3 TWh, ~13% above SMARD's own figure.** That is
#   the opposite pattern:
#   offshore's SMARD figure already behaves like a net-of-curtailment,
#   actually-delivered number. `24`'s own takeaway called offshore "the
#   clearest pre-curtailment case" based on curtailment explaining the
#   *largest share of a gap* -- true, but the gap it was closing (vs. the
#   narrow 1+2+3 slice) wasn't the full real-generation benchmark; against
#   that fuller benchmark, offshore is the one technology that looks net,
#   not gross. A plausible reason: offshore wind is a handful of large,
#   fully telemetered parks (SMARD likely receives real metered,
#   already-curtailed values), while onshore/solar are dominated by vast
#   numbers of small, non-telemetered plants, for which SMARD is legally
#   required to use a curtailment-blind extrapolation (the original
#   2026-09-30 textual finding this whole investigation set out to check).
# - **External sanity check (web search, 2026-10-06):** published 2024
#   Einspeisemanagement volumes (pv-magazine/cleanthinking, citing the
#   TSOs/Bundesnetzagentur) -- onshore ~3.38 TWh, offshore ~4.56 TWh, solar
#   ~1.39 TWh (PV curtailment +97% y/y) -- are the same order of magnitude
#   as this notebook's 2025 SMARD-redispatch-based figures (3.33 / 3.35 /
#   2.70 TWh), and the ~554 Mio EUR of total 2024 curtailment compensation
#   reported in the press lines up reasonably with this notebook's finding
#   that the real compensation hides in category 5, not category 4 (~11
#   Mio EUR in 4 vs. ~470 Mio EUR combined Zahlung+Einnahmen in 5). Also
#   worth separating from the much larger ~30 TWh "total redispatch"
#   headline number (Bundesnetzagentur Monitoringbericht 2024) -- that
#   figure is dominated by conventional-plant redispatch, not renewable
#   curtailment, and is not the right benchmark for this comparison.

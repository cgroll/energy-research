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
# # From day-ahead to settlement: the timeline behind reBAP, NRV-Saldo, and IP-Index
#
# `07`-`09` looked at reBAP, FCR/aFRR capacity prices, NRV-Saldo, and the
# IP-Index one at a time. This page is a pure reference diagram, no data --
# it maps out *when*, relative to a single delivered quarter-hour, each of
# those pieces actually gets decided, traded, measured, or published. Useful
# because several of them sound like they should happen in a similar place
# in the sequence but don't (see the two corrections below).
#
# **Two things that are easy to get backwards:**
# - **Redispatch is not a single D-1 planning step that finishes before
#   intraday trading starts.** An initial congestion forecast and
#   (precautionary) redispatch plan does happen on D-1, based on the first
#   schedules -- but redispatch keeps being updated after that, in parallel
#   with intraday trading, right through to ad-hoc, real-time calls during
#   delivery itself (confirmed via Redispatch 2.0's own FAQ: calls range
#   from planned, with lead time, up to real-time ad-hoc calls).
# - **The IP-Index is calculated *before* the NRV-Saldo/reBAP for the same
#   quarter-hour can even exist, not after.** The IP-Index is a
#   volume-weighted average of the *last* continuous-intraday trades before
#   delivery (German continuous intraday trading closes 5 minutes before
#   delivery start) -- it's known right at T. The NRV-Saldo for that same
#   quarter-hour can only be computed from real metered values *after* T,
#   and takes roughly 2 weeks to reach its final "qualitätsgesichert" form
#   (see `08_download_nrv_saldo.py`'s own module docstring for why that lag
#   isn't even perfectly monotonic).
#
# Sourced points on the diagram: EPEX day-ahead gate closure (12:00) and
# continuous intraday open (15:00)/close (-5min) are EPEX's own published
# trading hours; the Fahrplan change deadline (-45min) is from the German
# TSOs' joint `Fahrplananmeldung`-process documentation; the
# "Abrufe...bis zu Ad-hoc-Abrufen in Echtzeit möglich" redispatch-timing
# language is from TenneT's Redispatch 2.0 FAQ. The three-tier reBAP/
# NRV-Saldo publication timing (an early "Schätzer" within 30 minutes,
# "betrieblich" the next day, "qualitätsgesichert" after ~2 weeks) combines
# netztransparenz.de's own `AEP-Schätzer` page with this repo's own
# empirical download experience in `08_download_nrv_saldo.py`.

# %%
import matplotlib.pyplot as plt

from erx.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

MARKT_COLOR = "#2a78d6"
FAHRPLAN_COLOR = "#f39c12"
NETZ_COLOR = "#16a085"
REGEL_COLOR = "#c0392b"
MESSUNG_COLOR = "#8e44ad"

LANES = {
    "Markt / Handel": 5,
    "Fahrplan / Bilanzkreise": 4,
    "Netzbetrieb / Redispatch": 3,
    "Regelleistung (FCR/aFRR/mFRR)": 2,
    "Messung & Abrechnung": 1,
}

LABELS = {
    0: "D-1\n12:00",
    1: "D-1\n~13:00",
    2: "D-1\n15:00",
    2.7: "T -45min",
    3: "T -5min",
    4: "T\n(Lieferung)",
    5: "T +1 Tag",
    6: "T +~14 Tage",
    7: "T +Wochen",
}

# %% [markdown]
# ## The diagram
#
# Stage positions on the x-axis are categorical (evenly spaced for
# readability), **not** linear in real elapsed time -- the real gap between
# "T +1 Tag" and "T +~14 Tage" is obviously far larger than between
# "D-1 12:00" and "D-1 ~13:00", but drawing it to scale would compress
# everything interesting (the whole D-1-to-delivery sequence) into an
# unreadable sliver.

# %%
fig, ax = plt.subplots(figsize=(16, 9))

for lane_name, y in LANES.items():
    ax.axhline(y, color="#e5e3dc", linewidth=10, zorder=0, solid_capstyle="round", xmin=0.03, xmax=0.985)
    ax.text(-0.35, y, lane_name, ha="right", va="center", fontsize=10.5, fontweight="bold")


def point(x, y, color, label, dy=0.22):
    ax.scatter([x], [y], s=90, color=color, zorder=3, edgecolor="white", linewidth=1.2)
    ax.annotate(
        label, (x, y), xytext=(0, dy * 72), textcoords="offset points",
        ha="center", va="bottom" if dy > 0 else "top", fontsize=8.7, color="#2b2b28", linespacing=1.3,
    )


def span(x0, x1, y, color, label, dy=-0.22):
    ax.plot([x0, x1], [y, y], color=color, linewidth=6, solid_capstyle="round", zorder=2, alpha=0.85)
    ax.annotate(
        label, ((x0 + x1) / 2, y), xytext=(0, dy * 72), textcoords="offset points",
        ha="center", va="top" if dy < 0 else "bottom", fontsize=8.3, color="#5a5a55",
        linespacing=1.3, style="italic",
    )


# --- Markt / Handel ---
y = LANES["Markt / Handel"]
point(0, y, MARKT_COLOR, "Day-Ahead\nGate Closure\n(12:00)")
point(1, y, MARKT_COLOR, "Day-Ahead-Preis\nveröffentlicht")
point(2, y, MARKT_COLOR, "Intraday-Auktion +\nkont. Handel öffnet\n(15:00)")
span(2, 3, y, MARKT_COLOR, "laufender kontinuierlicher\nIntraday-Handel")
point(3, y, MARKT_COLOR, "Handel schließt (-5min)\nID-AEP / IP-Index\nberechnet", dy=0.32)

# --- Fahrplan / Bilanzkreise ---
y = LANES["Fahrplan / Bilanzkreise"]
point(1, y, FAHRPLAN_COLOR, "erste Fahrplan-\nAnmeldung", dy=-0.22)
span(1, 2.7, y, FAHRPLAN_COLOR, "laufende Fahrplan-\nAnpassungen")
point(2.7, y, FAHRPLAN_COLOR, "letzte Änderung\nmöglich (-45min)", dy=0.22)

# --- Netzbetrieb / Redispatch ---
y = LANES["Netzbetrieb / Redispatch"]
point(1, y, NETZ_COLOR, "erste Engpass-\nprognose", dy=-0.22)
span(1, 4, y, NETZ_COLOR, "laufende / ad-hoc Redispatch-Anweisungen -- bis in Echtzeit")

# --- Regelleistung ---
y = LANES["Regelleistung (FCR/aFRR/mFRR)"]
point(4, y, REGEL_COLOR, "FCR: automatisch\n(Frequenz)\naFRR: automatisch (AGC)\nmFRR: Abruf (kurzer Vorlauf)", dy=-0.4)

# --- Messung & Abrechnung ---
y = LANES["Messung & Abrechnung"]
point(4, y, MESSUNG_COLOR, "Messung Ist-Werte\n(-> RZ-/NRV-Saldo)", dy=0.22)
point(5, y, MESSUNG_COLOR, "reBAP / NRV-Saldo\n\"betrieblich\"", dy=-0.35)
point(6, y, MESSUNG_COLOR, "reBAP / NRV-Saldo\n\"qualitätsgesichert\"\n(das, was wir nutzen)", dy=0.22)
point(7, y, MESSUNG_COLOR, "Abrechnung der\nBilanzkreise", dy=-0.35)

ax.axvline(4, color="#2b2b28", linewidth=1.3, linestyle="--", zorder=1, ymin=0.03, ymax=0.97)
ax.text(4, 5.85, "T = Lieferbeginn der betrachteten Viertelstunde", ha="center", fontsize=9.5,
        fontweight="bold", color="#2b2b28")

xt = sorted(set(LABELS.keys()))
ax.set_xticks(xt)
ax.set_xticklabels([LABELS[x] for x in xt], fontsize=9)
ax.set_xlim(-1.6, 7.6)
ax.set_ylim(0.3, 6.1)
ax.set_yticks([])
for side in ["top", "right", "left"]:
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color("#cfcdc4")

ax.set_title(
    "Vom Day-Ahead-Handel bis zur Abrechnung: der zeitliche Ablauf\n"
    "(Achse zeigt Reihenfolge der Stufen, nicht linear in realer Zeit -- reale Abstände variieren stark)",
    fontsize=12.5, pad=18,
)

fig.tight_layout()
fig.savefig(paths.images_path / "10_balancing_timeline.png", dpi=160, bbox_inches="tight", facecolor="white")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/10_balancing_timeline.png
# :name: fig-10-balancing-timeline
# From day-ahead trading to final settlement: when each of market,
# schedule, redispatch, control-reserve, and metering/billing events
# happens relative to delivery time T.
# ```

# %% [markdown]
# ## Reading the diagram, stage by stage
#
# 1. **D-1, 12:00** -- EPEX day-ahead auction gate closure.
# 2. **D-1, ~13:00** -- day-ahead price published; balancing groups submit
#    their first `Fahrplan` (schedule) for day D; TSOs run a first
#    congestion forecast against that schedule and may issue precautionary
#    redispatch for day D.
# 3. **D-1, 15:00** -- intraday auction + continuous intraday trading opens
#    for day D.
# 4. **D-1 through T** -- intraday trading, `Fahrplan` revisions, and
#    redispatch instructions all run in parallel and keep updating, not in
#    strict sequence.
# 5. **T -45min** -- last regular `Fahrplan` change allowed.
# 6. **T -5min** -- continuous intraday trading closes for the product
#    starting at T; the IP-Index is computed from the last trades reaching
#    500 MW cumulative volume (see `09`'s discussion).
# 7. **T** -- physical delivery: FCR responds automatically to frequency,
#    aFRR is dispatched automatically via AGC, mFRR is called with a short
#    lead time if needed, redispatch can still be called ad-hoc; metering
#    of actual values begins -- this is what RZ-Saldo/NRV-Saldo for this
#    exact quarter-hour will be built from.
# 8. **T +1 day** -- "betrieblich" (preliminary) reBAP/NRV-Saldo published
#    (an even earlier "Schätzer" exists too, within 30 minutes of T, but
#    estimates rather than measures).
# 9. **T +~14 days** -- "qualitätsgesichert" (final, revised) reBAP/
#    NRV-Saldo published -- this is the version `07`-`09` use throughout.
# 10. **T +weeks** -- balancing groups get billed based on the final reBAP
#     and their own individual imbalance.

"""Download the German NRV-Saldo (Netzregelverbund-Saldo) from
netztransparenz.de -- an experiment, not yet promoted to `energy-data-hub`.

**What it is** (netztransparenz.de's own definition): for each of the four
German TSOs, the sum of all balancing measures employed gives that TSO's
own Regelzonen-Saldo (RZ-Saldo) -- the aggregate deviation between
consumption and generation across every balancing group in that TSO's
zone. The sum of the four RZ-Salden is the NRV-Saldo for Germany as a
whole. It is **not** simply "real load minus day-ahead auction volume" --
the "scheduled" side it's measured against is each balancing group's own
nomination (fed by day-ahead trades, intraday trades, and bilateral
contracts together), not day-ahead volume alone.

**Sign convention** (confirmed on the source page): positive = the NRV
was, on average across that quarter-hour, **under-supplied** (net short,
positive/upward balancing energy needed); negative = **over-supplied**
(net long, negative/downward balancing energy needed). This is the
*direct* counterpart to inferring system-imbalance direction indirectly
from how far reBAP diverges from the day-ahead price.

**Source mechanism**, discovered the same way as `energy-data-hub`'s
`edh/rebap.py` (reading the page's own inline chart-config JSON rather
than `DownloadHandler.js` this time -- both lead to the same
`CsvDownloadHandler.ashx` endpoint reBAP uses):
https://www.netztransparenz.de/de-de/Regelenergie/NRV-und-RZ-Saldo/NRV-Saldo-viertelstuendlich
embeds two chart configs, "NRV-Saldo betrieblich" (`ProduktId=5`, near
real-time/preliminary) and "NRV-Saldo qualitätsgesichert" (`ProduktId=6`,
revised/final) -- this script uses the quality-assured one, matching
reBAP's own choice. `TsoIds=[0]` returns a single `Deutschland` column
(the national aggregate), not a per-TSO breakdown.

**Availability confirmed empirically:** earliest data 2014-01-01 (server
silently clips anything requested before that, same behavior as reBAP) --
consistent with reBAP, since both are computed from the same underlying
settlement process. Quality-assured data has a publication lag of
roughly 2 weeks (empirically: ~15 days back returned data, the most
recent ~10-14 days did not) -- same order of magnitude as reBAP's own
lag, not independently confirmed to follow the identical schedule.

Output: `data/downloads/netztransparenz/nrv_saldo.parquet`
  index: timestamp (interval start, naive, represents true UTC)
  nrv_saldo_mw: float64 (MW; positive = under-supplied, negative = over-supplied)
"""

import base64
import io
import json
import urllib.parse
from datetime import date

import pandas as pd
import requests

from erx.paths import ProjPaths

BASE_URL = "https://www.netztransparenz.de/DesktopModules/LotesCharts/CsvDownloadHandler.ashx"
START_YEAR = 2014  # earliest year the server accepts, confirmed empirically (same as reBAP)
END_YEAR = date.today().year

SETTINGS = {
    "DataType": 20,
    "ProduktId": 6,  # "NRV-Saldo qualitätsgesichert" -- revised/final, matching reBAP's own choice
    "CultureName": "de-DE",
    "Title": "NRV-Saldo qualitätsgesichert",
    "DiagramType": "line",
    "TimeInterval": 15,
    "DataUnit": "MW",
    "CsvColumns": ["50Hertz", "Amprion", "TenneT TSO", "TransnetBW"],
    "TsoIds": [0],  # 0 = national aggregate (returns a single "Deutschland" column)
    "NrvDirection": 6,
    "WebApiRoute": "NrvSaldo/nrvsaldo/qualitaetsgesichert",
    "WebApiBaseUri": "https://lotes-UNB-svc-netzt.corp.transmission-it.de/StatistikApi/",
}

TZ_OFFSET = {"CET": "+01:00", "CEST": "+02:00"}

paths = ProjPaths()
paths.ensure_directories()
paths.nrv_saldo_file.parent.mkdir(parents=True, exist_ok=True)


def _build_url(local_from: str, local_to: str) -> str:
    request = {
        "LocalFrom": local_from,
        "LocalTo": local_to,
        "ResultTimeZone": "cet",
        "Settings": SETTINGS,
    }
    json_str = json.dumps(request, separators=(",", ":"))
    b64 = base64.b64encode(json_str.encode("utf-8")).decode("ascii")
    return f"{BASE_URL}?request={urllib.parse.quote(b64)}"


def _download_year(year: int) -> pd.DataFrame:
    local_from = f"{year}-01-01"
    local_to = f"{year + 1}-01-01"  # endpoint is exclusive; use Jan 1 next year to include Dec 31
    url = _build_url(local_from, local_to)
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig")
    if not text.lstrip().startswith("Datum;"):
        raise RuntimeError(f"Unexpected response for {year}: {text[:200]!r}")

    return pd.read_csv(
        io.StringIO(text),
        sep=";",
        decimal=",",
        na_values=["N.A."],
        dtype={"Datum": str, "Zeitzone": str, "von": str, "bis": str},
    )


all_years: list[pd.DataFrame] = []
for year in range(START_YEAR, END_YEAR + 1):
    print(f"Downloading NRV-Saldo {year} ...", end=" ", flush=True)
    df = _download_year(year)
    print(f"{len(df):,} rows")
    all_years.append(df)

raw = pd.concat(all_years, ignore_index=True)
print(f"\nTotal raw rows: {len(raw):,}")

# --- Build a naive-UTC timestamp from Datum + von + Zeitzone (CET/CEST) ----
offset = raw["Zeitzone"].map(TZ_OFFSET)
if offset.isna().any():
    unknown = sorted(raw.loc[offset.isna(), "Zeitzone"].unique())
    raise RuntimeError(f"Unknown Zeitzone label(s): {unknown}")

naive_local = pd.to_datetime(raw["Datum"] + " " + raw["von"], format="%d.%m.%Y %H:%M")
ts_str = naive_local.dt.strftime("%Y-%m-%d %H:%M:%S") + offset
timestamp = pd.to_datetime(ts_str, utc=True).dt.tz_localize(None)  # true UTC, naive

out = pd.DataFrame({"nrv_saldo_mw": raw["Deutschland"].to_numpy()}, index=timestamp).sort_index()
out.index.name = "timestamp"

n_before = len(out)
out = out[~out.index.duplicated(keep="first")]
if len(out) < n_before:
    print(f"Dropped {n_before - len(out):,} duplicate timestamps at year boundaries")

# Drop trailing not-yet-quality-assured rows (see module docstring) rather
# than persist them as NaN placeholders -- same reasoning as
# energy-data-hub's rebap_price asset.
n_before_trim = len(out)
last_valid = out["nrv_saldo_mw"].last_valid_index()
out = out.loc[:last_valid] if last_valid is not None else out.iloc[0:0]
if len(out) < n_before_trim:
    print(f"Dropped {n_before_trim - len(out):,} trailing not-yet-published rows")

print(
    f"\nFinal: {len(out):,} rows  ({out.index[0]} -> {out.index[-1]})  "
    f"mean={out['nrv_saldo_mw'].mean():+.1f}  std={out['nrv_saldo_mw'].std():.1f} MW  "
    f"share positive (under-supplied)={100 * (out['nrv_saldo_mw'] > 0).mean():.1f}%"
)

out_path = paths.nrv_saldo_file
out.to_parquet(out_path)
print(f"Saved to {out_path}  ({out_path.stat().st_size / 1e6:.2f} MB)")

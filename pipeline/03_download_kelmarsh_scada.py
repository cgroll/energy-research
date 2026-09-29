"""Download Kelmarsh's per-turbine SCADA data (Zenodo record 5841834) and
extract just the signals needed to test a wind-speed-based reconstruction
of generation: `Wind speed (m/s)`, `Density adjusted wind speed (m/s)`
(where present), `Power (kW)`, `Data Availability`. Used by
`04_compare_windspeed_reconstruction.py`.

Pure data script -- no visualizations. The raw per-year zips
(`Kelmarsh_SCADA_<year>_*.zip`, ~1.5 GB combined across 2016-2021) are
treated as disposable intermediates -- downloaded to memory, parsed, and
discarded; only the parsed result (10-minute, long format: one row per
turbine per timestamp) is written to disk. This is deliberately narrower
than the ~250-column per-turbine table the source publishes -- energy-
research only needs wind speed + power here, not a full production
migration of every SCADA signal.
"""

import io
import zipfile
import urllib.request

import pandas as pd

from erx.paths import ProjPaths

RECORD_FILES_BASE = "https://zenodo.org/api/records/5841834/files"
SCADA_ZIPS = {
    2016: "Kelmarsh_SCADA_2016_3082.zip",
    2017: "Kelmarsh_SCADA_2017_3083.zip",
    2018: "Kelmarsh_SCADA_2018_3084.zip",
    2019: "Kelmarsh_SCADA_2019_3085.zip",
    2020: "Kelmarsh_SCADA_2020_3086.zip",
    2021: "Kelmarsh_SCADA_2021_3087.zip",
}
COLUMNS_TO_KEEP = [
    "Wind speed (m/s)",
    "Density adjusted wind speed (m/s)",
    "Power (kW)",
    "Data Availability",
]

paths = ProjPaths()
paths.ensure_directories()

OUTPUT_FILE = paths.downloads_path / "kelmarsh_turbine_windspeed_power.parquet"


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def _parse_turbine_csv(raw_bytes: bytes) -> tuple[str, pd.DataFrame]:
    lines = raw_bytes.decode("utf-8").splitlines()
    turbine_name = next(l for l in lines if l.startswith("# Turbine:")).split(":", 1)[1].strip()
    header_idx = next(i for i, l in enumerate(lines) if l.startswith("# Date and time"))

    df = pd.read_csv(io.BytesIO(raw_bytes), skiprows=header_idx)
    df.columns = [c.lstrip("# ").strip() for c in df.columns]
    df["Date and time"] = pd.to_datetime(df["Date and time"], utc=True).dt.tz_localize(None)
    df = df.set_index("Date and time")

    keep = [c for c in COLUMNS_TO_KEEP if c in df.columns]
    return turbine_name, df[keep]


if OUTPUT_FILE.exists():
    print(f"Already present, skipping: {OUTPUT_FILE}")
else:
    frames = []
    for year, zip_name in SCADA_ZIPS.items():
        print(f"Downloading {zip_name} ...")
        zip_bytes = _download(f"{RECORD_FILES_BASE}/{zip_name}/content")
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            turbine_files = [n for n in zf.namelist() if n.startswith("Turbine_Data_")]
            for name in turbine_files:
                turbine_name, df = _parse_turbine_csv(zf.read(name))
                df = df.reset_index().rename(columns={"Date and time": "timestamp"})
                df["turbine"] = turbine_name
                frames.append(df)
        print(f"  parsed {len(turbine_files)} turbine files for {year}")

    combined = pd.concat(frames, ignore_index=True).sort_values(["turbine", "timestamp"]).reset_index(drop=True)
    combined.to_parquet(OUTPUT_FILE, index=False)
    print(f"Saved {len(combined):,} rows -> {OUTPUT_FILE}")

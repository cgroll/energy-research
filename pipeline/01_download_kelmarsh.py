"""Download Kelmarsh wind farm data (Zenodo record 5841834).

Pure data script — no visualizations. Fetches just the two files needed for
the first PECD-vs-reality check:

- `Kelmarsh_WT_static.csv` — per-turbine coordinates, rated power, hub
  height, rotor diameter for the 6 Senvion MM92 units.
- `Kelmarsh_Grid_3088.zip` — the site's fiscal/grid meter export, 10-minute
  resolution, 2016-01-01 to 2021-07-01, UTC. This is the actual metered
  generation at the grid connection point, i.e. real net energy injected
  into the grid — the ground truth to compare against PECD's onshore wind
  capacity factors for hub zone `UK03` (see `erx/paths.py::hub_file`).

Full per-turbine SCADA (`Kelmarsh_SCADA_*.zip`, ~1.5 GB total) is not
downloaded here — add it later if the grid-meter-level comparison raises
questions that need turbine-level detail.

Source: https://zenodo.org/records/5841834 (CC-BY-4.0, Cubico Sustainable
Investments Ltd).
"""

import io
import urllib.request
import zipfile

from erx.paths import ProjPaths

RECORD_FILES_BASE = "https://zenodo.org/api/records/5841834/files"
STATIC_URL = f"{RECORD_FILES_BASE}/Kelmarsh_WT_static.csv/content"
GRID_ZIP_URL = f"{RECORD_FILES_BASE}/Kelmarsh_Grid_3088.zip/content"

paths = ProjPaths()
paths.ensure_directories()


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url) as resp:
        return resp.read()


# ── Turbine static data ─────────────────────────────────────────────────────
if paths.kelmarsh_wt_static_file.exists():
    print(f"Already present, skipping: {paths.kelmarsh_wt_static_file}")
else:
    data = _download(STATIC_URL)
    paths.kelmarsh_wt_static_file.write_bytes(data)
    print(f"Saved {len(data):,} bytes → {paths.kelmarsh_wt_static_file}")

# ── Grid meter data (zip: Device_Data + Status CSVs) ────────────────────────
if paths.kelmarsh_grid_meter_file.exists() and paths.kelmarsh_grid_status_file.exists():
    print(f"Already present, skipping: {paths.kelmarsh_grid_meter_file}")
else:
    zip_bytes = _download(GRID_ZIP_URL)
    paths.kelmarsh_grid_zip.write_bytes(zip_bytes)
    print(f"Saved {len(zip_bytes):,} bytes → {paths.kelmarsh_grid_zip}")

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        device_data_name = next(n for n in names if n.startswith("Device_Data_"))
        status_name = next(n for n in names if n.startswith("Status_"))

        paths.kelmarsh_grid_meter_file.write_bytes(zf.read(device_data_name))
        print(f"Extracted → {paths.kelmarsh_grid_meter_file}")

        paths.kelmarsh_grid_status_file.write_bytes(zf.read(status_name))
        print(f"Extracted → {paths.kelmarsh_grid_status_file}")

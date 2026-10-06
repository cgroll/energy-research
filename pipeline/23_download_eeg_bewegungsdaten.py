"""Download + aggregate the EEG-Jahresabrechnung "Bewegungsdaten" (netztransparenz.de).

Pure data acquisition script (mirrors `12_download_conventional_mastr.py`'s
pattern: downloads raw files, but also does the one necessary reduction --
a join + groupby over ~10M rows -- before writing a small, analysis-ready
parquet, since keeping the raw join/groupby out of every downstream
notebook run matters here more than usual).

**Why this data, and what it's for** (conversation 2026-10-06, following up
on `PROJECT.md`'s 2026-09-30 finding): SMARD's "realisierte Erzeugung" for
wind/solar leans on a regulated "Online-Hochrechnung" for the many small,
non-telemetered plants that -- per netztransparenz.de's own wording -- is
legally required (since Jan 2015) to *exclude* grid-driven curtailment
(Einspeisemanagement/Redispatch), i.e. it reports theoretical-max output,
not real net feed-in. That finding was textual (netztransparenz.de's own
documentation), not yet checked against real numbers. The EEG annual
settlement ("Jahresabrechnung") movement data is the real-numbers check:
it's the metered basis the four UENBs (transmission operators) actually
pay EEG compensation on, published with a ~9-month lag per law (§51 Abs. 5
EnFG) -- 2025's data was released 2026-09-04, matching the user's "ca. 1
Jahr Verzoegerung" description. Specifically:

- `Veraeusserungsform` 1/2/3 (Einspeiseverguetung, Marktpraemie,
  Mieterstromzuschlag) are paid on electricity *actually metered as fed
  in* -- after curtailment, whatever happened really happened.
- `Veraeusserungsform` 4 (Ausfallverguetung) is the curtailment
  *compensation* itself -- paid for energy a plant would have produced
  but didn't, because a grid operator curtailed it. Its `Strommenge` is
  the empirical curtailment volume, by energy carrier.
- So (1+2+3) is the real net-of-curtailment quantity, and (1+2+3+4) is the
  real gross/theoretical-max quantity -- exactly the two numbers needed to
  tell which one SMARD's generation series actually tracks.

**Source:** netztransparenz.de > Erneuerbare Energien und Umlagen > EEG >
EEG-Abrechnungen > EEG-Jahresabrechnungen > EEG-Bewegungsdaten /
EEG-Anlagenstammdaten. Per-UENB ZIPs of CSVs (`;`-delimited, UTF-8 BOM,
CRLF), plus a shared `Legende` workbook per dataset explaining the code
columns. URLs change their GUID per release -- re-discover via
`curl -s <section URL> | grep -oE 'href="[^"]*\\.(zip|xlsx)"'` if this
script 404s on a future year.

**Monthly granularity caveat, found while exploring this data:** the
`Monat` column (1-12, or 0 = "Jahreswert"/no monthly split) is populated
inconsistently by `Veraeusserungsform` -- Marktpraemie (2) is ~98% genuinely
monthly, but Einspeiseverguetung (1) and Ausfallverguetung (4) are almost
entirely `Monat=0` (annual lump sums). A monthly comparison against SMARD
is therefore not reliable for the curtailment check; this script keeps
`Monat` in the aggregate (cheap to keep), but the downstream analysis
(`24_eeg_realized_generation_vs_smard.py`) compares **annual totals**.

**Join key:** `EEG_Mastr_Nr` links Bewegungsdaten rows to Anlagenstammdaten
(for `Energietraeger`, the fuel/technology code) -- verified empirically
every Bewegungsdaten `EEG_Mastr_Nr` exists in the matching Anlagenstammdaten
export (50Hertz zone spot check), and only 1 of ~551k plants in that zone
has an inconsistent `Energietraeger` across its (rare) duplicate
Anlagenstammdaten rows -- deduped via `any_value` before joining, fan-out
risk from those duplicates is otherwise negligible.
"""

import zipfile
from pathlib import Path

import duckdb
import requests

from erx.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

YEAR = 2025
RAW_DIR = paths.eeg_bewegungsdaten_raw_dir
OUT_FILE = paths.eeg_bewegungsdaten_aggregated_file

# GUIDs scraped 2026-10-06 from the two netztransparenz.de section pages
# above -- see module docstring for how to re-discover these if they've
# rotated by the time this runs again.
UENBS: dict[str, dict[str, str]] = {
    "50hertz": {
        "stammdaten": "https://www.netztransparenz.de/cdn/files/22b1ed13-39ab-43c0-29ca-08defc51206b/50hertz%20transmission%20gmbh%20eeg-zahlungen%20anlagenstammdaten%202025.zip",
        "bewegungsdaten": "https://www.netztransparenz.de/cdn/files/0687a707-cf7c-45c1-29cf-08defc51206b/50hertz%20transmission%20gmbh%20eeg-zahlungen%20bewegungsdaten%202025.zip",
    },
    "amprion": {
        "stammdaten": "https://www.netztransparenz.de/cdn/files/61f62098-ff56-4ce7-29fe-08defc51206b/amprion%20gmbh%20eeg-zahlungen%20anlagenstammdaten%202025.zip",
        "bewegungsdaten": "https://www.netztransparenz.de/cdn/files/56b98c32-4c16-44ed-29d0-08defc51206b/amprion%20gmbh%20eeg-zahlungen%20bewegungsdaten%202025.zip",
    },
    "tennet": {
        "stammdaten": "https://www.netztransparenz.de/cdn/files/5356665b-8b4e-4181-29cc-08defc51206b/tennet%20tso%20gmbh%20eeg-zahlungen%20stammdaten%202025.zip",
        "bewegungsdaten": "https://www.netztransparenz.de/cdn/files/ff4ee575-7857-431e-f919-08def218fc48/tennet%20tso%20gmbh%20eeg-zahlungen%20bewegungsdaten%202025.zip",
    },
    "transnetbw": {
        "stammdaten": "https://www.netztransparenz.de/cdn/files/96fbf4b0-1763-4a48-29cd-08defc51206b/transnetbw%20gmbh%20eeg-zahlungen%20anlagenstammdaten%202025.zip",
        "bewegungsdaten": "https://www.netztransparenz.de/cdn/files/a43d4021-c55e-420b-29d2-08defc51206b/transnetbw%20gmbh%20eeg-zahlungen%20bewegungsdaten%202025.zip",
    },
}

# Energietraeger code -> label, from `anlagenstammdaten_legende.xlsx`'s
# `Legende` sheet.
ENERGIETRAEGER_LABELS = {
    1: "wasser",
    2: "deponiegas",
    3: "klaergas",
    4: "grubengas",
    5: "biomasse",
    6: "geothermie",
    7: "wind_onshore",
    8: "wind_offshore",
    9: "solar",
}

HEADERS = {"User-Agent": "Mozilla/5.0"}


def _download(url: str, dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, headers=HEADERS, timeout=120)
    response.raise_for_status()
    dest.write_bytes(response.content)


def _normalize_encoding(csv_path: Path) -> None:
    """Some UENBs export UTF-8 (with BOM), others ISO-8859-1 (e.g. Amprion's
    "VORL.UFIG" row, 0xC4 for 'Ä') -- found via DuckDB's CSV reader
    rejecting an invalid-UTF-8 byte sequence. Normalize every extracted
    CSV to plain UTF-8 up front so DuckDB (and everything downstream)
    only ever has to deal with one encoding."""
    raw = csv_path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    csv_path.write_text(text, encoding="utf-8")


def _extract(zip_path: Path, dest_dir: Path) -> None:
    # Idempotent: skip if dest_dir already has csv files from a previous run.
    if dest_dir.exists() and any(dest_dir.rglob("*.csv")):
        return
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    for csv_path in dest_dir.rglob("*.csv"):
        _normalize_encoding(csv_path)


def main() -> None:
    con = duckdb.connect()
    per_uenb_tables = []

    for uenb, urls in UENBS.items():
        uenb_dir = RAW_DIR / uenb
        stamm_zip = uenb_dir / "anlagenstammdaten.zip"
        beweg_zip = uenb_dir / "bewegungsdaten.zip"
        stamm_dir = uenb_dir / "anlagenstammdaten"
        beweg_dir = uenb_dir / "bewegungsdaten"

        print(f"[{uenb}] downloading...")
        _download(urls["stammdaten"], stamm_zip)
        _download(urls["bewegungsdaten"], beweg_zip)

        print(f"[{uenb}] extracting...")
        _extract(stamm_zip, stamm_dir)
        _extract(beweg_zip, beweg_dir)

        stamm_glob = str(stamm_dir / "**" / "*.csv")
        beweg_glob = str(beweg_dir / "**" / "*.csv")

        print(f"[{uenb}] joining + aggregating...")
        # `any_value(Energietraeger)` collapses the rare duplicate-row
        # plants (see module docstring) without a fan-out risk -- NULL
        # EEG_Mastr_Nr rows (plants without one) never match the join, by
        # ordinary SQL NULL semantics.
        query = f"""
            WITH stamm AS (
                SELECT EEG_Mastr_Nr, any_value(Energietraeger) AS energietraeger
                FROM read_csv(
                    '{stamm_glob}', delim=';', header=true, union_by_name=true,
                    quote='"', escape='"', ignore_errors=true
                )
                WHERE EEG_Mastr_Nr IS NOT NULL
                GROUP BY EEG_Mastr_Nr
            ),
            beweg AS (
                -- Strommenge's decimal format is inconsistent across
                -- UENBs/files (50Hertz: plain integers; Amprion: German
                -- comma-decimal) -- read everything as VARCHAR and parse
                -- explicitly rather than let each file's auto-detected
                -- type collide on UNION.
                SELECT
                    EEG_Mastr_Nr,
                    CAST(Veraeusserungsform AS INTEGER) AS veraeusserungsform,
                    CAST(Monat AS INTEGER) AS monat,
                    CAST(replace(Strommenge, ',', '.') AS DOUBLE) AS strommenge_kwh
                FROM read_csv(
                    '{beweg_glob}', delim=';', header=true, union_by_name=true,
                    quote='"', escape='"', ignore_errors=true,
                    types={{'Veraeusserungsform': 'VARCHAR', 'Strommenge': 'VARCHAR', 'Monat': 'VARCHAR'}}
                )
            )
            SELECT
                '{uenb}' AS uenb,
                s.energietraeger,
                b.veraeusserungsform,
                b.monat,
                sum(b.strommenge_kwh) AS strommenge_kwh,
                count(*) AS n_rows
            FROM beweg b
            LEFT JOIN stamm s ON b.EEG_Mastr_Nr = s.EEG_Mastr_Nr
            GROUP BY 1, 2, 3, 4
        """
        per_uenb_tables.append(con.sql(query))

    print("combining + writing aggregate...")
    combined = per_uenb_tables[0]
    for t in per_uenb_tables[1:]:
        combined = combined.union(t)

    df = combined.df()
    df["energietraeger_label"] = df["energietraeger"].map(ENERGIETRAEGER_LABELS)
    df["year"] = YEAR
    df = df.sort_values(["uenb", "energietraeger", "veraeusserungsform", "monat"]).reset_index(drop=True)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_FILE, index=False)
    print(f"wrote {len(df)} rows to {OUT_FILE}")
    print(df.groupby("energietraeger_label")["strommenge_kwh"].sum().sort_values(ascending=False))


if __name__ == "__main__":
    main()

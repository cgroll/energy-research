"""Download + extract conventional (combustion + nuclear) MaStR units.

Pure data script -- no visualizations, mirrors the hub's `edh/mastr.py`
pattern but stays self-contained in this repo (the hub currently only
harmonizes wind/solar/storage, see `energy-data-hub/edh/mastr.py` module
docstring -- conventional thermal/nuclear units are a new technology pull,
not something to bolt onto the hub before it's been validated here, per
this repo's own promotion workflow).

**Why this script parses the raw XML itself instead of letting open-mastr
do it:** `Mastr().download(data=["combustion", "nuclear"])` successfully
fetches and caches the MaStR zip (`EinheitenVerbrennung.xml` /
`EinheitenKernkraft.xml`, both from marktstammdatenregister.de), but
open-mastr's own XML-to-SQL step throws on `EinheitenVerbrennung.xml`:
`Failed to parse string: '2467 2473' as a scalar of type int64` -- at least
one combustion unit has a space-separated *list* in a column open-mastr's
schema expects as a scalar int, which aborts that file's entire SQL
ingestion (confirmed empty table afterwards). Reproduced identically on
both open-mastr 1.0.0 and 0.17.4 (the hub's own pinned version), so this is
a live MaStR data quirk, not a resolvable version-pinning issue. Since the
raw zip download itself succeeds regardless (the crash is purely in
processing), this script re-parses the cached zip directly with
`lxml.etree.iterparse` (streaming, forward-only -- combustion alone is
~285MB uncompressed), picking only the handful of fields needed for a
merit-order marginal-cost calculation and skipping whatever column breaks
open-mastr's stricter typing.

**Scope, matching EWI Merit-Order-Tool 2025's own stated base data
(Bundesnetzagentur MaStR, see `literature/` + the chat discussion that
prompted this script):** `EinheitMastrNummer`, `Energietraeger` (fuel
category), `Hauptbrennstoff` (specific main fuel, defaults to
`Energietraeger` when absent), `Technologie` (generation technology code --
used downstream to split gas units into CCGT/"GuD" vs. open-cycle
"Gasturbine", same distinction EWI's tool makes), `Nettonennleistung` (net
capacity, kW throughout MaStR -- confirmed against Grohnde nuclear's real
1360 MW), `Inbetriebnahmedatum`, `EinheitBetriebsstatus`, `Bundesland`.
Catalog codes (fuel/technology/status/state) are decoded via
`Katalogwerte.xml`, bundled in the same zip.

No efficiency field exists anywhere in MaStR for any technology -- EWI's
own documentation says the same (carries forward a manually-curated,
block-level efficiency table rather than reading it from MaStR). This
script leaves `efficiency` for the downstream analysis script to attach as
a per-fuel-type assumption, same gap, same workaround.
"""

import os

from erx.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

# open-mastr reads OUTPUT_PATH at import time -- must be set before the
# import, same convention as edh/mastr.py.
MASTR_HOME_DIR = paths.downloads_path / "mastr_conventional"
os.environ["OUTPUT_PATH"] = str(MASTR_HOME_DIR)

import zipfile  # noqa: E402

import pandas as pd  # noqa: E402
from lxml import etree  # noqa: E402
from open_mastr import Mastr  # noqa: E402

XML_DOWNLOAD_DIR = MASTR_HOME_DIR / "data" / "xml_download"

# Fields kept from each `<EinheitVerbrennung>` / `<EinheitKernkraft>`
# record -- deliberately narrow (see module docstring on why iterparse
# instead of open-mastr's own SQL ingestion).
WANTED_FIELDS = [
    "EinheitMastrNummer",
    "Energietraeger",
    "Hauptbrennstoff",
    "Technologie",
    "Nettonennleistung",
    "Bruttoleistung",
    "Inbetriebnahmedatum",
    "DatumEndgueltigeStilllegung",
    "EinheitBetriebsstatus",
    "Bundesland",
    "NameKraftwerk",
    "NameKraftwerksblock",
]


def cached_zip_path() -> "str | None":
    """Path to an already-downloaded Gesamtdatenexport zip, if any --
    avoids re-downloading on every pipeline re-run (same snapshot-pinning
    idea as edh/mastr.py, simplified since this repo's own zip only ever
    holds what *this* script has requested so far)."""
    if not XML_DOWNLOAD_DIR.exists():
        return None
    existing = sorted(XML_DOWNLOAD_DIR.glob("Gesamtdatenexport_*.zip"))
    return str(existing[-1]) if existing else None


def download_conventional_zip() -> str:
    """Fetch combustion + nuclear XML members via open-mastr (download
    only -- its own SQL ingestion is not used, see module docstring).
    Idempotent: skipped if a zip is already cached locally."""
    existing = cached_zip_path()
    if existing is not None:
        print(f"Using already-downloaded zip: {existing}")
        return existing

    db = Mastr()
    db.download(data=["combustion", "nuclear"], keep_old_downloads=True)

    zip_path = cached_zip_path()
    if zip_path is None:
        raise RuntimeError("open-mastr download did not produce a cached Gesamtdatenexport zip")
    return zip_path


def parse_katalogwerte(zip_file: zipfile.ZipFile) -> dict[int, str]:
    """`{Id: Wert}` lookup for every MaStR catalog code (fuel type,
    technology, operational status, state, ...) -- all catalogs share one
    flat `Katalogwerte.xml` file, disambiguated by `KatalogKategorieId`
    only when a given Id collides across categories (not handled here,
    not observed to matter for the codes this script actually decodes)."""
    lookup: dict[int, str] = {}
    with zip_file.open("Katalogwerte.xml") as f:
        for _, elem in etree.iterparse(f, tag="Katalogwert"):
            id_text = elem.findtext("Id")
            wert_text = elem.findtext("Wert")
            if id_text is not None and wert_text is not None:
                lookup[int(id_text)] = wert_text
            elem.clear()
    return lookup


def parse_units(zip_file: zipfile.ZipFile, xml_name: str, record_tag: str, technology_group: str) -> pd.DataFrame:
    """Stream `record_tag` elements out of `xml_name`, keeping only
    `WANTED_FIELDS` -- forward-only iterparse + `elem.clear()` keeps peak
    memory low regardless of the source file's size (combustion alone is
    ~285MB uncompressed)."""
    rows = []
    with zip_file.open(xml_name) as f:
        for _, elem in etree.iterparse(f, tag=record_tag):
            row = {field: elem.findtext(field) for field in WANTED_FIELDS}
            row["technology_group"] = technology_group
            rows.append(row)
            elem.clear()
            # Drop now-empty preceding siblings too -- iterparse alone
            # still accumulates the parent's children in memory otherwise.
            parent = elem.getparent()
            if parent is not None:
                while parent[0] is not elem:
                    del parent[0]
    df = pd.DataFrame(rows)
    print(f"{xml_name}: {len(df):,} records")
    return df


def main() -> None:
    zip_path = download_conventional_zip()

    with zipfile.ZipFile(zip_path) as zf:
        catalog = parse_katalogwerte(zf)
        combustion = parse_units(zf, "EinheitenVerbrennung.xml", "EinheitVerbrennung", "combustion")
        nuclear = parse_units(zf, "EinheitenKernkraft.xml", "EinheitKernkraft", "nuclear")

    df = pd.concat([combustion, nuclear], ignore_index=True)

    df = df.rename(
        columns={
            "EinheitMastrNummer": "unit_id",
            "Energietraeger": "energy_source_code",
            "Hauptbrennstoff": "main_fuel_code",
            "Technologie": "technology_code",
            "Nettonennleistung": "net_capacity_kw",
            "Bruttoleistung": "gross_capacity_kw",
            "Inbetriebnahmedatum": "commissioning_date",
            "DatumEndgueltigeStilllegung": "final_shutdown_date",
            "EinheitBetriebsstatus": "status_code",
            "Bundesland": "state_code",
            "NameKraftwerk": "plant_name",
            "NameKraftwerksblock": "block_name",
        }
    )

    for col in ["net_capacity_kw", "gross_capacity_kw"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Main fuel falls back to the broader energy-source code when a unit
    # doesn't report its own (observed for a minority of combustion
    # records) -- both share the same Katalogwerte code space.
    df["main_fuel_code"] = df["main_fuel_code"].fillna(df["energy_source_code"])

    for code_col, label_col in [
        ("energy_source_code", "energy_source"),
        ("main_fuel_code", "main_fuel"),
        ("technology_code", "technology"),
        ("status_code", "status"),
        ("state_code", "state"),
    ]:
        df[label_col] = df[code_col].apply(lambda v: catalog.get(int(v)) if pd.notna(v) else None)

    df["commissioning_date"] = pd.to_datetime(df["commissioning_date"], errors="coerce")
    df["final_shutdown_date"] = pd.to_datetime(df["final_shutdown_date"], errors="coerce")

    df.to_parquet(paths.mastr_conventional_units_file, index=False)
    print(f"Saved {len(df):,} rows → {paths.mastr_conventional_units_file}")
    print(df["main_fuel"].value_counts(dropna=False))
    print(df["status"].value_counts(dropna=False))


if __name__ == "__main__":
    main()

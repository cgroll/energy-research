"""Project paths configuration.

All paths are resolved relative to the project root, making scripts runnable
from any working directory. Add a @property for each new data file introduced
in the pipeline.

Research topics in this repo may also read data that energy-data-hub already
provides (SMARD, MaStR, PECD, ...) instead of re-downloading it — see
`hub_file()` below. Same convention as `energy-insights/insights/paths.py`:
an absolute path into the sibling hub checkout, fail loudly if it's missing
rather than silently continuing without the data.
"""

from pathlib import Path

HUB_DATA = Path.home() / "research" / "energy-platform" / "energy-data-hub" / "data"


def hub_file(*parts: str) -> Path:
    """Path to a hub data file, e.g. `hub_file("pecd", "de_capacity_factors.parquet")`."""
    path = HUB_DATA.joinpath(*parts)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- is energy-data-hub cloned at "
            f"~/research/energy-platform/energy-data-hub, with its "
            f"`{'/'.join(parts[:-1]) or '.'}` asset(s) materialized?"
        )
    return path


class ProjPaths:
    """Centralized project paths.

    The root is inferred from the location of this file (erx/), so scripts
    run correctly regardless of the working directory they are invoked from.
    """

    def __init__(self):
        self._pkg_path = Path(__file__).resolve().parent  # erx/
        self._project_path = self._pkg_path.parent        # project root

    # ------------------------------------------------------------------ #
    # Top-level directories                                                #
    # ------------------------------------------------------------------ #

    @property
    def project_path(self) -> Path:
        """Root project directory."""
        return self._project_path

    @property
    def pkg_path(self) -> Path:
        """Source package directory (erx/)."""
        return self._pkg_path

    @property
    def pipeline_path(self) -> Path:
        """Pipeline scripts directory."""
        return self._project_path / "pipeline"

    # ------------------------------------------------------------------ #
    # Data directories                                                     #
    # ------------------------------------------------------------------ #

    @property
    def data_path(self) -> Path:
        """Main data directory."""
        return self._project_path / "data"

    @property
    def downloads_path(self) -> Path:
        """Raw downloaded data."""
        return self.data_path / "downloads"

    @property
    def processed_data_path(self) -> Path:
        """Processed/transformed data."""
        return self.data_path / "processed"

    # ------------------------------------------------------------------ #
    # Output directories                                                   #
    # ------------------------------------------------------------------ #

    @property
    def output_path(self) -> Path:
        """Generated outputs root."""
        return self._project_path / "output"

    @property
    def images_path(self) -> Path:
        """Chart/figure images saved by pipeline scripts."""
        return self.output_path / "images"

    @property
    def reports_path(self) -> Path:
        """Report files."""
        return self.output_path / "reports"

    # ------------------------------------------------------------------ #
    # Example data files — replace with project-specific paths            #
    # ------------------------------------------------------------------ #

    @property
    def example_raw_file(self) -> Path:
        """Raw example dataset (parquet)."""
        return self.downloads_path / "example_data.parquet"

    @property
    def example_processed_file(self) -> Path:
        """Processed example dataset (parquet)."""
        return self.processed_data_path / "example_processed.parquet"

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def ensure_directories(self) -> None:
        """Create all standard directories if they do not yet exist."""
        dirs = [
            self.downloads_path,
            self.processed_data_path,
            self.images_path,
            self.reports_path,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

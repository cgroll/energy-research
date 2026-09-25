# Energy Research

Exploratory research playground for the `energy-platform` stack. Where
[`energy-data-hub`](https://github.com/cgroll/energy-data-hub) ("the hub")
and [`energy-insights`](https://github.com/cgroll/energy-insights) ("the
book") are the production-grade, Dagster-orchestrated parts of the platform,
this repo is where a new data source or analysis idea gets tried out first —
messy, one-off, DVC/jupytext-based — before it's decided whether it's worth
promoting into the hub as a Dagster asset and into `energy-insights` as a
published page.

Published as a [MyST](https://mystmd.org/) Jupyter Book to GitHub Pages. The
pipeline is orchestrated by [DVC](https://dvc.org/); dependencies are managed
by [uv](https://docs.astral.sh/uv/). See [AGENTS.md](AGENTS.md) for full
tooling conventions and [PROJECT.md](PROJECT.md) for current state and
findings.

## Relationship to the rest of `energy-platform`

This repo owns its own `data/downloads/` and `data/processed/` for whatever
it's currently investigating, but a research topic can also read data the
hub has already ingested (SMARD, MaStR, PECD, ...) instead of re-downloading
it — see `hub_file()` in [`erx/paths.py`](erx/paths.py). It resolves an
absolute path into the sibling `energy-data-hub` checkout and fails loudly if
that data isn't there yet, the same convention `energy-insights` uses.

```
~/research/energy-platform/
  energy-data-hub/    # shared data ingestion layer (Dagster)
  energy-insights/    # explanatory pages/book, reads the hub's data
  energy-research/    # this repo — exploratory research, promotes into the above
```

## Setup

```bash
uv sync
make dry-run   # preview what the pipeline would run
make run       # execute it (dvc repro)
make serve     # open http://localhost:3000 — live book preview
```

## Project layout

```
project-root/
├── erx/                  # Python package — shared utilities
│   └── paths.py          # project paths + hub_file() into energy-data-hub
├── pipeline/              # Pipeline scripts
│   ├── 01_download_*     # Data acquisition
│   └── 02_analyse_*      # Analysis → notebook
├── book/                  # MyST book source
│   ├── notebooks/         # Executed notebooks (DVC output)
│   ├── markdown/          # Static content
│   └── myst.yml           # TOC and site settings
├── data/                  # Git-ignored data (cached by DVC)
├── output/images/         # Figures (tracked in git)
├── dvc.yaml               # Pipeline DAG
├── dvc.lock               # Pipeline state (checksums) — tracked in git
├── AGENTS.md              # Conventions for contributors/AI
└── PROJECT.md              # Current state, roadmap, lessons learned
```

## Common DVC commands

| Command | Effect |
|---------|--------|
| `dvc repro --dry` | Dry run — show what would execute |
| `dvc repro` | Run pipeline (only rebuilds what's out of date) |
| `dvc repro -f <stage>` | Force-re-run a specific stage |
| `dvc repro <stage>` | Build one specific stage (and its dependencies) |
| `dvc repro --force` | Re-run everything unconditionally |
| `dvc dag` | Print the pipeline DAG |

# Start here — Steam Genre Forecast

## Current project

The active workflow is `fixed_sources_v2`: a fixed cohort of 519 games with
complete February 2021–January 2026 history. The January 2026 cutoff supplies
a provisional 23-month forecast through December 2027. Categories overlap;
the target is average concurrent activity within this cohort.

Start with [Notebook 20](notebooks/20_fixed_cohort_2027_forecast.ipynb) and the
[portfolio summary](reports/PORTFOLIO_SUMMARY.md) to review saved results.
The [scope config](config/project_scope.json) and
[frozen source registry](reports/fixed_sources_v2/source_registry.json) define
the current inputs. Earlier notebooks and `database/steam.sqlite` preserve v1.

## Environment and notebook kernel

Open the repository folder in VS Code. The tested environment
is Windows with Python 3.14.3; other Python versions and operating systems have
not been verified.

From the repository root:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
```

For every notebook, use **Select Kernel → Python Environments** and choose this
repository's `.venv/Scripts/python.exe`. A generic `python3` kernel name does
not prove that the project environment is selected. If using the registered
**Steam Forecast (.venv)** kernel, verify that its interpreter points to the
current checkout; moving the repository can leave an old absolute path.

Register that environment for the notebook metadata used in this repository:

```powershell
.\.venv\Scripts\python.exe -m ipykernel install --user --name steam-forecast --display-name "Steam Forecast (.venv)"
```

Repeat registration after moving the checkout. All 20 notebooks now name this
kernel; registration is local and does not change their calculations or outputs.

The lock file records the tested package versions. It does not include
`nbformat`/`nbclient` for automated notebook execution. Saved outputs can be
reviewed without executing cells. Running all notebook cells is not a read-only
check: several cells rebuild data, fit models or write reports.

Only rebuilding the supplemental DuckDB snapshot stage requires:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-audit.txt
```

That optional dependency is used by `src/incorporate_enrichment.py`, not by the
current forecast when its frozen supplemental Parquet input is already present.

## Data required for v2 reproduction

A fresh Git checkout does not contain every raw input, processed table or
database. Some upstream redistribution terms remain unresolved, so this guide
does not provide a fully automated public v2 restoration route. Preserve the
frozen local copies and verify them against the registry before rebuilding.
See [source and reuse notes](data/raw/README.md).

The integration stage requires these repository-relative inputs:

| Input | Purpose |
|---|---|
| `database/steam.sqlite` | Frozen original v1 monthly history |
| `data/raw/fronkon_metadata/games.parquet` | Frozen metadata and retrospective category labels |
| `data/raw/fixed_sources_v2/aanomali_monthly.csv` | Frozen multiplayer history |
| `data/raw/fixed_sources_v2/liu_monthly.csv` | Frozen giveaway-research history |
| `data/processed/supplemental_monthly_validated.parquet` | Previously validated supplemental history |
| `reports/steamcharts_pilot/20261025T085419Z_52879d/monthly_players.csv` | Existing bounded pilot history |

The integration script also verifies the original v1 forecast through
`src/project_2027.py`, so retain its recorded inputs and evidence under
`reports/forecast_2027/`. Preserve the existing v2 manifests, frozen policy
and diagnostic CSVs: they are part of the reproduction checks.

The v1 downloader uses only `data/raw/sources.json`. It restores the original
metadata and lunthu player snapshot; it does not retrieve the additional v2
sources, validated supplement or pilot cache. A checksum mismatch stops
restoration instead of replacing different existing bytes.

## Rebuilding the research

These commands write generated artifacts. Evaluation and projection commands
fit models; run them only when a deliberate rebuild is intended, not to inspect
the existing forecast. Frozen fingerprints are checked, and changed sources,
policy or outputs require a separately reviewed version.

If the original v1 inputs/database need restoration, the historical sequence is:

```powershell
.\.venv\Scripts\python.exe src\download_data.py
.\.venv\Scripts\python.exe src\check_setup.py
.\.venv\Scripts\python.exe src\prepare_data.py
```

`check_setup.py` writes setup reports. This sequence alone does not recreate
every later v1 evaluation/forecast artifact needed by v2 integration; retain
those existing frozen artifacts and inspect the historical pipeline in
`src/project_2027.py` before rebuilding them.

With the prerequisite inputs and v1 evidence present, the current v2 stages are:

| Order | Entry point | Main generated artifacts |
|---|---|---|
| 1 | `src/integrate_fixed_sources.py` | `database/steam_v2.sqlite`, `data/processed/fixed_sources_v2/`, `reports/fixed_sources_v2/` |
| 2 | `src/evaluate_fixed_cohort.py` | `reports/fixed_cohort_evaluation/` |
| 3 | `src/investigate_fixed_cohort.py` | `reports/fixed_cohort_diagnostics/` |
| 4 | `src/project_fixed_cohort.py` | `reports/fixed_cohort_forecast_2027/` |
| 5 | `src/portfolio_visuals.py` | `outputs/final_figures/` |

Run each entry point with `.\.venv\Scripts\python.exe` from the repository
root. Notebooks 17–20 present the same integration, comparison, error-review and
projection stages, including their prerequisites and limits:

- [Fixed-source integration](notebooks/17_fixed_sources_integration.ipynb)
- [Model comparison](notebooks/18_fixed_cohort_model_comparison.ipynb)
- [Error review](notebooks/19_fixed_cohort_error_review.ipynb)
- [2027 projection](notebooks/20_fixed_cohort_2027_forecast.ipynb)

## Tests and verification

Run the research tests without the historical HTML-builder tests:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests --ignore=tests/test_retro_chart.py -q -p no:cacheprovider
```

Tests use synthetic model inputs and temporary fixtures; they do not establish
that the real-data models reproduce in a clean environment. If temporary-folder
creation is blocked, use `--basetemp` with a new, writable scratch directory
outside the repository. Pytest can clear an existing base directory, so do not
point it at a folder containing files you need.

The 27 October 2026 A004 run passed 263 research tests, with four historical
HTML-builder tests excluded. The same 263 tests also passed in a newly created
Windows/Python 3.14.3 environment installed from `requirements-lock.txt` and
`requirements-audit.txt`; `pip check` passed. All 59 locked package versions
matched. This verifies environment installation and the synthetic test suite,
not a clean-machine rebuild of restricted raw inputs or execution of all
research notebooks. Other operating systems remain untested. Earlier suite
counts in the technical audit reports refer to their respective stages.

Pinned config and CSV/JSON evidence use `-text` Git attributes so checkout does
not change the bytes used by SHA-256 checks. Preserve these attributes when
copying or distributing the research.

## Finding evidence in VS Code

Use `database/steam_v2.sqlite` for the current archive and
`database/steam.sqlite` for historical v1. The current category inputs are
`reports/fixed_sources_v2/category_monthly.csv`; final forecast CSVs and the
frozen policy are under `reports/fixed_cohort_forecast_2027/`.

CSV files can be opened in Data Wrangler with the project environment selected.
The notebook Outline helps navigate longer analyses. Optional editor themes and
icons are not reproduction dependencies.

The [final audit](reports/FINAL_PROJECT_AUDIT.md) records earlier verification
and its limitations. Source data and forecasts remain frozen; new collection,
retuning and methodology changes are separate work.

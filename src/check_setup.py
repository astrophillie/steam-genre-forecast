"""Repeatable setup smoke check and initial source profile; no model training."""
from datetime import datetime, timezone
from importlib import import_module, metadata
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    versions = {}
    for package, module in [
        ("pandas", "pandas"), ("numpy", "numpy"), ("matplotlib", "matplotlib"),
        ("seaborn", "seaborn"), ("statsmodels", "statsmodels.api"),
        ("scikit-learn", "sklearn"), ("ipykernel", "ipykernel"),
        ("pytest", "pytest"), ("requests", "requests"), ("pyarrow", "pyarrow"),
    ]:
        import_module(module)
        versions[package] = metadata.version(package)
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)

    import pandas as pd
    import pyarrow.parquet as pq
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.linear_model import LinearRegression
    from statsmodels.tsa.holtwinters import SimpleExpSmoothing

    # Tiny synthetic inputs verify library execution only, never forecast evidence.
    LinearRegression().fit([[0], [1], [2]], [0, 1, 2]).predict([[3]])
    SimpleExpSmoothing(
        [1.0, 2.0, 3.0, 4.0], initialization_method="estimated"
    ).fit().forecast(1)
    fig = plt.figure()
    fig.canvas.draw()
    plt.close(fig)
    with sqlite3.connect(":memory:") as connection:
        assert connection.execute("SELECT 1 + 1").fetchone()[0] == 2

    raw = ROOT / "data" / "raw"
    manifest = json.loads((raw / "sources.json").read_text(encoding="utf-8"))
    for source in manifest["sources"]:
        for entry in source["files"]:
            path = ROOT / entry["path"]
            with path.open("rb") as handle:
                actual = hashlib.file_digest(handle, "sha256").hexdigest()
            if actual != entry["sha256"]:
                raise ValueError(f"Checksum mismatch: {path}")

    metadata_path = raw / "fronkon_metadata" / "games.parquet"
    parquet = pq.ParquetFile(metadata_path)
    games = pd.read_parquet(metadata_path, columns=["appID", "name", "genres"])
    players = pd.read_csv(raw / "monthly_players" / "steamcharts.csv")
    import numpy as np

    if games.empty or players.empty:
        raise ValueError("Source tables must contain observations")
    dates = pd.to_datetime(players["month"], format="%b-%y", errors="raise")
    game_ids = pd.to_numeric(games["appID"], errors="raise").astype("Int64")
    player_ids = pd.to_numeric(players["steam_appid"], errors="raise").astype("Int64")
    average_players = pd.to_numeric(players["avg_players"], errors="raise")
    if dates.isna().any() or game_ids.isna().any() or player_ids.isna().any():
        raise ValueError("App IDs and month labels must not be missing")
    if not np.isfinite(average_players.to_numpy(dtype=float, na_value=np.nan)).all():
        raise ValueError("Average player activity must be finite and nonmissing")
    if (average_players < 0).any():
        raise ValueError("Average player activity must be nonnegative")
    duplicates = int(players.assign(app_id=player_ids, date=dates).duplicated(["app_id", "date"]).sum())
    if game_ids.duplicated().any() or duplicates:
        raise ValueError("Source keys must be unique at the expected grain")
    matched = set(player_ids).intersection(set(game_ids))
    invalid_dates = 0
    negative = 0


    profile = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0], "executable": sys.executable,
        "packages": versions, "smoke_checks": "passed",
        "metadata_rows": parquet.metadata.num_rows,
        "metadata_unique_ids": int(game_ids.nunique()),
        "metadata_duplicate_ids": int(game_ids.duplicated().sum()),
        "player_rows": len(players), "player_unique_games": int(player_ids.nunique()),
        "player_date_min": str(dates.min().date()), "player_date_max": str(dates.max().date()),
        "invalid_month_rows": invalid_dates,
        "duplicate_player_game_month_rows": duplicates,
        "negative_average_player_rows": negative,
        "missing_average_player_rows": int(players["avg_players"].isna().sum()),
        "matched_player_game_ids": len(matched),
        "match_rate": len(matched) / player_ids.nunique(),
        "checksum_verification": "passed",
    }
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "setup_check.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    table = "\n".join(f"| {name} | {version} |" for name, version in versions.items())
    report = f"""# Setup check

Verified at {profile['checked_at_utc']}.

## Environment

- Python {profile['python']}; interpreter: `{profile['executable']}`.
- All ten requested package imports passed; `pip check` passed.
- SQLite in-memory query, plot rendering, and tiny synthetic statistical/ML smoke checks passed.
- Source file SHA-256 checks passed. No project model was trained.
- Editor extensions, selected kernel, and workspace trust are not inspected by this script.

| Package | Installed version |
|---|---|
{table}

## Downloaded source profile

| Check | Observed result |
|---|---|
| Metadata rows | {len(games):,} |
| Unique metadata app IDs | {game_ids.nunique():,} |
| Monthly-player rows | {len(players):,} |
| Unique player-history app IDs | {player_ids.nunique():,} |
| Parsed monthly range | {profile['player_date_min']} to {profile['player_date_max']} |
| Unparsed month rows | {invalid_dates:,} |
| Duplicate app/month rows | {duplicates:,} |
| Negative average-player rows | {negative:,} |
| Missing average-player rows | {profile['missing_average_player_rows']:,} |
| Player-history games matched to metadata | {len(matched):,} ({profile['match_rate']:.1%}) |

These are setup checks, not a full data audit. Original files remain unchanged.

## What needs attention before modelling

- **Freshness — high importance:** player observations end in {profile['player_date_max']}. A current 2027 forecast needs newer history or an explicitly historical exercise with a longer horizon.
- **Coverage:** results describe the observed source catalog; whole-Steam representativeness is not established.
- **Join coverage:** unmatched IDs need a documented handling rule.
- **Labels and gaps:** refer to the notebook audit for category availability and per-app time coverage.
- Current project-stage decisions are documented in `START_HERE.md`.

## Evidence and reproduction

- `data/raw/sources.json`: versions, source URLs, licenses as reported, sizes, checksums.
- `data/raw/*/dataset_info.json`: saved publisher metadata.
- `reports/setup_check.json`: machine-readable checks.
- `src/check_setup.py`: exact checks; rerun with the project's Python interpreter.
- `requirements-lock.txt`: environment versions.

For the current analysis and next decisions, see `START_HERE.md` and the initial audit notebook.
"""
    (reports / "SETUP_CHECK.md").write_text(report, encoding="utf-8")
    print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    main()

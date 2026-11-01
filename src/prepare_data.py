"""Prepare the recorded Steam snapshot and build a local analytical database."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GAME_LABELS = {"Action", "Adventure", "Casual", "Simulation", "Strategy", "RPG", "Sports", "Racing"}
SOFTWARE_LABELS = {
    "Utilities", "Design & Illustration", "Animation & Modeling", "Video Production",
    "Audio Production", "Game Development", "Software Training", "Photo Editing",
    "Web Publishing", "Accounting", "Movie", "Documentary", "Episodic", "Short", "360 Video",
}
CATEGORIES = ["Action", "Massively Multiplayer", "Indie", "RPG", "Strategy"]


def integer_ids(values):
    """Reject missing, nonpositive, fractional, or nonnumeric app identifiers."""
    ids = pd.to_numeric(values, errors="raise")
    numbers = ids.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(numbers).all() or (numbers <= 0).any() or (numbers % 1 != 0).any():
        raise ValueError("App IDs must be positive integers without missing values")
    return ids.astype("int64")


def normalise_labels(labels):
    """Keep explicit label lists; do not infer a type from a title."""
    if not isinstance(labels, (list, tuple, np.ndarray)):
        raise ValueError("Genres must be a list-like collection")
    if any(not isinstance(label, str) or not label.strip() for label in labels):
        raise ValueError("Genre labels must be nonempty strings")
    return sorted({label.strip() for label in labels})


def review_group(labels):
    has_game = bool(set(labels) & GAME_LABELS)
    has_software = bool(set(labels) & SOFTWARE_LABELS)
    if has_game and has_software:
        return "Mixed game/software labels"
    if has_software:
        return "Software/media labels only"
    if has_game:
        return "Game-related labels only"
    return "No decisive label"


def prepare_tables(games, players):
    """Preserve all tracked apps/history; record eligibility as an explicit flag."""
    metadata = games[["appID", "name", "genres"]].copy().rename(columns={"appID": "app_id"})
    history = players[["steam_appid", "name", "month", "avg_players"]].copy()
    history = history.rename(columns={"steam_appid": "app_id"})
    if metadata.empty or history.empty:
        raise ValueError("Source tables must contain observations")
    metadata["app_id"] = integer_ids(metadata["app_id"])
    history["app_id"] = integer_ids(history["app_id"])
    if metadata["app_id"].duplicated().any():
        raise ValueError("Duplicate metadata app IDs are not allowed")
    metadata["genres"] = metadata["genres"].map(normalise_labels)
    dates = pd.to_datetime(history["month"], format="%b-%y", errors="raise")
    if dates.isna().any():
        raise ValueError("Month labels must not be missing")
    history["month"] = dates.dt.strftime("%Y-%m-01")
    activity = pd.to_numeric(history["avg_players"], errors="raise")
    if not np.isfinite(activity.to_numpy(dtype=float, na_value=np.nan)).all() or (activity < 0).any():
        raise ValueError("Activity must be finite, nonnegative, and nonmissing")
    history["avg_players"] = activity.astype(float)
    if history.duplicated(["app_id", "month"]).any():
        raise ValueError("Duplicate app/month keys are not allowed")

    names = history.sort_values("month").drop_duplicates("app_id", keep="last")[["app_id", "name"]]
    catalog = names.merge(metadata, on="app_id", how="left", validate="one_to_one",
                          suffixes=("_history", ""), indicator=True)
    catalog["metadata_available"] = catalog["_merge"].eq("both").astype(int)
    catalog["name"] = catalog["name"].fillna(catalog["name_history"])
    if catalog["name"].isna().any():
        raise ValueError("Every tracked app needs an identifiable name")
    catalog["review_group"] = "Missing metadata"
    matched = catalog["metadata_available"].eq(1)
    catalog.loc[matched, "review_group"] = catalog.loc[matched, "genres"].map(review_group)
    catalog["eligible"] = catalog["review_group"].eq("Game-related labels only").astype(int)
    reasons = {
        "Game-related labels only": "Included: game-related label and no software/media flag",
        "Mixed game/software labels": "Held out: mixed game and software/media labels",
        "Software/media labels only": "Held out: software/media labels without game-related labels",
        "No decisive label": "Held out: labels do not establish game-related scope",
        "Missing metadata": "Held out: metadata unavailable",
    }
    catalog["eligibility_reason"] = catalog["review_group"].map(reasons)

    labels = catalog.loc[matched, ["app_id", "genres"]].explode("genres")
    labels = labels.dropna(subset=["genres"]).rename(columns={"genres": "genre"})
    labels = labels.drop_duplicates(["app_id", "genre"]).sort_values(["app_id", "genre"])
    return {
        "games": catalog[["app_id", "name", "metadata_available", "review_group", "eligible", "eligibility_reason"]]
                        .sort_values("app_id").reset_index(drop=True),
        "game_genres": labels.reset_index(drop=True),
        "monthly_players": history[["app_id", "month", "avg_players"]]
                           .sort_values(["app_id", "month"]).reset_index(drop=True),
    }


def build_database(tables, manifest, database_path):
    """Build a constrained database separately, then publish it after validation."""
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = database_path.with_name(f".building-{uuid.uuid4().hex}.sqlite.part")
    sources_by_role = {}
    for source in manifest["sources"]:
        names = {Path(entry["path"]).name for entry in source.get("files", [])}
        role = "metadata" if "games.parquet" in names else "players" if "steamcharts.csv" in names else None
        if role is None or role in sources_by_role or {"games.parquet", "steamcharts.csv"} <= names:
            raise ValueError("Expected distinct recorded metadata and player-history sources")
        sources_by_role[role] = source
    if set(sources_by_role) != {"metadata", "players"}:
        raise ValueError("Expected the recorded metadata and player-history sources")
    try:
        with closing(sqlite3.connect(temporary)) as connection, connection:
            connection.executescript((ROOT / "sql/schema.sql").read_text(encoding="utf-8"))
            source_rows = [
                (index, source["name"], source["source"],
                 str(source.get("revision", source.get("version", "unknown"))),
                 manifest["downloaded_at_utc"], json.dumps(source, ensure_ascii=False))
                for index, source in enumerate(
                    [sources_by_role["metadata"], sources_by_role["players"]], start=1)
            ]
            connection.executemany("INSERT INTO source_runs VALUES (?, ?, ?, ?, ?, ?)", source_rows)
            catalog = tables["games"].copy()
            catalog["metadata_source_id"] = catalog["metadata_available"].map({1: 1, 0: None})
            rows = catalog.astype(object).where(pd.notna(catalog), None).itertuples(index=False, name=None)
            connection.executemany("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            connection.executemany("INSERT INTO game_genres VALUES (?, ?)",
                                   tables["game_genres"].itertuples(index=False, name=None))
            connection.executemany(
                "INSERT INTO monthly_players (app_id, month, avg_players) VALUES (?, ?, ?)",
                tables["monthly_players"].itertuples(index=False, name=None),
            )
            connection.executemany("INSERT INTO analysis_categories VALUES (?)", [(x,) for x in CATEGORIES])
            query = (ROOT / "sql/category_monthly.sql").read_text(encoding="utf-8").rstrip().rstrip(";")
            connection.execute("CREATE VIEW category_monthly AS " + query)
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Database contains orphan records")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Database integrity check failed")
            for table, frame in tables.items():
                if connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] != len(frame):
                    raise ValueError(f"Import row count mismatch: {table}")
        temporary.replace(database_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    raw = ROOT / "data/raw"
    manifest = json.loads((raw / "sources.json").read_text(encoding="utf-8"))
    for source in manifest["sources"]:
        for entry in source["files"]:
            with (ROOT / entry["path"]).open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() != entry["sha256"]:
                    raise ValueError(f"Source checksum mismatch: {entry['path']}")
    games = pd.read_parquet(raw / "fronkon_metadata/games.parquet", columns=["appID", "name", "genres"])
    players = pd.read_csv(raw / "monthly_players/steamcharts.csv",
                          usecols=["steam_appid", "name", "month", "avg_players"])
    tables = prepare_tables(games, players)
    build_database(tables, manifest, ROOT / "database/steam.sqlite")
    processed = ROOT / "data/processed"
    processed.mkdir(parents=True, exist_ok=True)
    for table, frame in tables.items():
        frame.to_parquet(processed / f"{table}.parquet", index=False)
    with sqlite3.connect(ROOT / "database/steam.sqlite") as connection:
        category = pd.read_sql_query("SELECT * FROM category_monthly", connection)
        scope = pd.read_sql_query((ROOT / "sql/scope_impact.sql").read_text(encoding="utf-8"), connection)
    if (category["observed_apps"] > category["expected_apps"]).any():
        raise ValueError("Observed app counts exceed the recorded-span denominator")
    category.to_csv(ROOT / "reports/category_monthly_prepared.csv", index=False)
    scope.to_csv(ROOT / "reports/preparation_scope_impact.csv", index=False)
    print(f"Prepared {len(tables['games']):,} apps and {len(tables['monthly_players']):,} observations.")
    print(f"Eligible apps: {tables['games']['eligible'].sum():,}; category/month rows: {len(category):,}.")


if __name__ == "__main__":
    main()

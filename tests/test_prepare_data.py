"""Offline preparation contracts: preserve observations and hold out ambiguous apps."""
import importlib.util
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_data", ROOT / "src/prepare_data.py")
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


@pytest.fixture
def raw_tables():
    games = pd.DataFrame({
        "appID": [10, 20, 99],
        "name": ["Metadata name", "Tool", "Untracked"],
        "genres": [["Action", "Indie", "Action"], ["Utilities"], ["RPG"]],
    })
    players = pd.DataFrame({
        "steam_appid": [10, 10, 20, 30],
        "name": ["Old name", "Old name", "Tool", "History-only title"],
        "month": ["Jan-24", "Mar-24", "Jan-24", "Feb-24"],
        "avg_players": [0.0, 12.5, 8.0, 3.0],
    })
    return games, players


def test_every_tracked_app_survives_and_untracked_metadata_is_ignored(raw_tables):
    tables = preparation.prepare_tables(*raw_tables)
    games = tables["games"].set_index("app_id")
    assert set(games.index) == {10, 20, 30}
    assert games.index.is_unique
    assert games.loc[10, "name"] == "Metadata name"
    assert games.loc[30, "name"] == "History-only title"
    assert games["metadata_available"].to_dict() == {10: 1, 20: 1, 30: 0}
    assert bool(games.loc[10, "eligible"])
    assert games.loc[10, "review_group"] == "Game-related labels only"
    for app_id in (20, 30):
        assert not bool(games.loc[app_id, "eligible"])
        assert isinstance(games.loc[app_id, "eligibility_reason"], str)
        assert games.loc[app_id, "eligibility_reason"].strip()


def test_genres_are_unique_pairs_only_for_tracked_metadata(raw_tables):
    genres = preparation.prepare_tables(*raw_tables)["game_genres"]
    assert set(map(tuple, genres[["app_id", "genre"]].to_numpy())) == {
        (10, "Action"), (10, "Indie"), (20, "Utilities"),
    }
    assert not genres.duplicated(["app_id", "genre"]).any()


def test_history_preserves_observed_zero_and_does_not_fill_internal_gap(raw_tables):
    history = preparation.prepare_tables(*raw_tables)["monthly_players"]
    assert set(map(tuple, history[["app_id", "month", "avg_players"]].to_numpy())) == {
        (10, "2024-01-01", 0.0), (10, "2024-03-01", 12.5),
        (20, "2024-01-01", 8.0), (30, "2024-02-01", 3.0),
    }
    assert len(history) == len(raw_tables[1])


@pytest.mark.parametrize("label", [
    "Action", "Adventure", "Casual", "Simulation", "Strategy", "RPG", "Sports", "Racing",
])
def test_each_gameplay_label_qualifies_with_generic_labels(raw_tables, label):
    games, players = raw_tables
    games.at[0, "genres"] = [label, "Indie", "MMO", "Early Access"]
    row = preparation.prepare_tables(games, players)["games"].set_index("app_id").loc[10]
    assert row["review_group"] == "Game-related labels only"
    assert bool(row["eligible"])


@pytest.mark.parametrize("labels", [
    [], ["Indie"], ["MMO"], ["Early Access"], ["Indie", "MMO", "Early Access"],
    ["Unknown label"], ["Action", "Utilities"],
])
def test_ambiguous_empty_generic_or_mixed_labels_are_held_out(raw_tables, labels):
    games, players = raw_tables
    games.at[0, "genres"] = labels
    row = preparation.prepare_tables(games, players)["games"].set_index("app_id").loc[10]
    assert not bool(row["eligible"])
    assert row["review_group"] != "Game-related labels only"
    assert isinstance(row["eligibility_reason"], str) and row["eligibility_reason"].strip()


@pytest.mark.parametrize("label", [
    "Utilities", "Design & Illustration", "Animation & Modeling", "Video Production",
    "Audio Production", "Game Development", "Software Training", "Photo Editing",
    "Web Publishing", "Accounting", "Movie", "Documentary", "Episodic", "Short", "360 Video",
])
@pytest.mark.parametrize("with_gameplay", [False, True])
def test_software_and_video_labels_never_qualify_even_with_gameplay(raw_tables, label, with_gameplay):
    games, players = raw_tables
    games.at[0, "genres"] = ["Action", label] if with_gameplay else [label]
    row = preparation.prepare_tables(games, players)["games"].set_index("app_id").loc[10]
    assert not bool(row["eligible"])


@pytest.mark.parametrize("container", [None, float("nan"), "Action", {"genre": "Action"}, 42])
def test_null_or_non_list_genre_containers_fail_clearly(raw_tables, container):
    games, players = raw_tables
    games.at[0, "genres"] = container
    with pytest.raises(ValueError, match="(?i)genre|label"):
        preparation.prepare_tables(games, players)


def test_numpy_label_array_from_parquet_is_accepted(raw_tables):
    games, players = raw_tables
    games.at[0, "genres"] = np.array(["Action", "Indie"])
    result = preparation.prepare_tables(games, players)
    assert bool(result["games"].set_index("app_id").loc[10, "eligible"])


@pytest.mark.parametrize("table,column", [(0, "appID"), (1, "steam_appid")])
@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), 0, -1, 1.5, "bad"])
def test_missing_nonfinite_nonpositive_or_fractional_ids_are_rejected(raw_tables, table, column, value):
    frame = raw_tables[table]
    frame[column] = frame[column].astype(object)
    frame.at[0, column] = value
    with pytest.raises(ValueError):
        preparation.prepare_tables(*raw_tables)


def test_duplicate_metadata_id_is_rejected(raw_tables):
    games, players = raw_tables
    games = pd.concat([games, games.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="(?i)duplicat"):
        preparation.prepare_tables(games, players)


def test_duplicate_app_month_is_rejected_after_date_parsing(raw_tables):
    games, players = raw_tables
    players = pd.concat([players, players.iloc[[0]]], ignore_index=True)
    players.loc[len(players) - 1, "month"] = "JAN-24"
    with pytest.raises(ValueError, match="(?i)duplicat"):
        preparation.prepare_tables(games, players)


@pytest.mark.parametrize("month", [None, "", "Feb-30-24", "Not-24", "2024-01-01", "Jan-2024"])
def test_invalid_source_month_is_rejected(raw_tables, month):
    games, players = raw_tables
    players.at[0, "month"] = month
    with pytest.raises(ValueError):
        preparation.prepare_tables(games, players)


@pytest.mark.parametrize("activity", [None, float("nan"), float("inf"), -float("inf"), -0.01, "bad"])
def test_missing_nonfinite_or_negative_activity_is_rejected(raw_tables, activity):
    games, players = raw_tables
    players["avg_players"] = players["avg_players"].astype(object)
    players.at[0, "avg_players"] = activity
    with pytest.raises(ValueError):
        preparation.prepare_tables(games, players)


@pytest.fixture
def source_manifest():
    return {
        "downloaded_at_utc": "2026-10-19T20:00:00+00:00",
        "sources": [
            {"name": "Metadata fixture", "source": "https://example.invalid/metadata", "revision": "abc123",
             "files": [{"path": "data/raw/fronkon_metadata/games.parquet"}]},
            {"name": "Players fixture", "source": "https://example.invalid/players", "version": 2,
             "files": [{"path": "data/raw/monthly_players/steamcharts.csv"}]},
        ],
    }


@pytest.fixture
def database(tmp_path, raw_tables, source_manifest):
    tables = preparation.prepare_tables(*raw_tables)
    path = tmp_path / "steam.sqlite"
    preparation.build_database(tables, source_manifest, path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection


def test_database_contains_all_prepared_rows_and_source_records(database):
    assert database.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 3
    assert database.execute("SELECT COUNT(*) FROM game_genres").fetchone()[0] == 3
    assert database.execute("SELECT COUNT(*) FROM monthly_players").fetchone()[0] == 4
    assert database.execute("SELECT COUNT(*) FROM source_runs").fetchone()[0] == 2
    assert database.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("category", ["Action", "Indie"])
def test_category_monthly_distinguishes_observed_zero_from_internal_missing(database, category):
    database.execute("INSERT OR IGNORE INTO analysis_categories (genre) VALUES (?)", (category,))
    database.row_factory = sqlite3.Row
    query = (ROOT / "sql/category_monthly.sql").read_text(encoding="utf-8")
    rows = {
        row["month"]: dict(row)
        for row in database.execute(query)
        if row["category"] == category
    }
    assert set(rows) == {"2024-01-01", "2024-02-01", "2024-03-01"}
    january, february, march = (rows[month] for month in sorted(rows))
    assert january["avg_players"] == 0
    assert january["observed_apps"] == january["expected_apps"] == 1
    assert january["coverage_rate"] == 1
    assert february["expected_apps"] == 1
    assert february["observed_apps"] == 0
    assert february["internal_missing_apps"] == 1
    assert february["avg_players"] is None
    assert february["coverage_rate"] == 0
    assert march["avg_players"] == 12.5
    assert march["observed_apps"] == march["expected_apps"] == 1
    assert march["coverage_rate"] == 1


@pytest.mark.parametrize("category", ["Action", "Indie"])
def test_category_calendar_includes_month_absent_from_all_source_observations(
    tmp_path, raw_tables, source_manifest, category,
):
    games, players = raw_tables
    players = players[players["steam_appid"] == 10].copy()
    tables = preparation.prepare_tables(games, players)
    path = tmp_path / "global-gap.sqlite"
    preparation.build_database(tables, source_manifest, path)
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM monthly_players WHERE month = '2024-02-01'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT month, avg_players, expected_apps, observed_apps, coverage_rate "
            "FROM category_monthly WHERE category = ? ORDER BY month", (category,),
        ).fetchall() == [
            ("2024-01-01", 0.0, 1, 1, 1.0),
            ("2024-02-01", None, 1, 0, 0.0),
            ("2024-03-01", 12.5, 1, 1, 1.0),
        ]


def test_reversed_manifest_preserves_metadata_and_history_source_attribution(
    tmp_path, raw_tables, source_manifest,
):
    source_manifest["sources"].reverse()
    path = tmp_path / "reversed-sources.sqlite"
    preparation.build_database(preparation.prepare_tables(*raw_tables), source_manifest, path)
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT source_run_id, source_name, source_url, snapshot FROM source_runs ORDER BY source_run_id"
        ).fetchall() == [
            (1, "Metadata fixture", "https://example.invalid/metadata", "abc123"),
            (2, "Players fixture", "https://example.invalid/players", "2"),
        ]
        assert connection.execute(
            "SELECT DISTINCT s.source_name FROM games g "
            "JOIN source_runs s ON g.metadata_source_id = s.source_run_id "
            "WHERE g.metadata_available = 1"
        ).fetchall() == [("Metadata fixture",)]
        assert connection.execute(
            "SELECT metadata_source_id FROM games WHERE app_id = 30"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT DISTINCT s.source_name FROM monthly_players p "
            "JOIN source_runs s ON p.source_run_id = s.source_run_id"
        ).fetchall() == [("Players fixture",)]


@pytest.mark.parametrize("table", ["games", "game_genres", "monthly_players"])
def test_database_rejects_duplicate_primary_keys(database, table):
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(f"INSERT INTO {table} SELECT * FROM {table} LIMIT 1")


@pytest.mark.parametrize("statement", [
    "INSERT INTO game_genres (app_id, genre) VALUES (999, 'Action')",
    "INSERT INTO monthly_players (app_id, month, avg_players) VALUES (999, '2024-01-01', 2)",
])
def test_database_rejects_orphan_genres_and_observations(database, statement):
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(statement)


@pytest.mark.parametrize("statement", [
    "INSERT INTO games (app_id, name, metadata_available, review_group, eligible, eligibility_reason) SELECT 0, name, metadata_available, review_group, eligible, eligibility_reason FROM games WHERE app_id = 10",
    "INSERT INTO games (app_id, name, metadata_available, review_group, eligible, eligibility_reason) SELECT -1, name, metadata_available, review_group, eligible, eligibility_reason FROM games WHERE app_id = 10",
    "INSERT INTO games (app_id, name, metadata_available, review_group, eligible, eligibility_reason) SELECT 1.5, name, metadata_available, review_group, eligible, eligibility_reason FROM games WHERE app_id = 10",
    "UPDATE games SET metadata_available = 2 WHERE app_id = 10",
    "UPDATE games SET eligible = 2 WHERE app_id = 10",
    "UPDATE monthly_players SET avg_players = -1 WHERE app_id = 10",
    "UPDATE monthly_players SET avg_players = NULL WHERE app_id = 10",
])
def test_database_enforces_value_constraints(database, statement):
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(statement)

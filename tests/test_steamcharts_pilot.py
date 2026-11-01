"""Offline parsing checks for the bounded SteamCharts history pilot."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from steamcharts_pilot import parse_monthly_html


HEADERS = ("Month", "Avg. Players", "Gain", "% Gain", "Peak Players")


def monthly_html(rows, prefix=""):
    header = "".join(f"<th>{value}</th>" for value in HEADERS)
    body = "".join(
        "<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"{prefix}<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def parse(rows, as_of="2026-10-25"):
    return parse_monthly_html(monthly_html(rows), app_id=730, as_of=as_of)


def test_completed_months_have_expected_values_and_types():
    result = parse([
        ("September 2026", "1,234.50", "+20", "+1%", "2,345"),
        ("August 2026", "900.25", "-10", "-1%", "1,800"),
    ])
    assert list(result.columns) == ["app_id", "month", "avg_players", "peak_players"]
    records = result.set_index("month").to_dict("index")
    assert records == {
        "2026-09-01": {"app_id": 730, "avg_players": 1234.5, "peak_players": 2345},
        "2026-08-01": {"app_id": 730, "avg_players": 900.25, "peak_players": 1800},
    }
    assert pd.api.types.is_float_dtype(result["avg_players"])
    assert pd.api.types.is_integer_dtype(result["peak_players"])


@pytest.mark.parametrize("as_of", ["2026-10-25", pd.Timestamp("2026-10-25")])
def test_rolling_window_and_current_partial_month_are_excluded(as_of):
    result = parse([
        ("Last 30 Days", "100", "+1", "+1%", "200"),
        ("October 2026", "90", "+1", "+1%", "180"),
        ("September 2026", "80", "+1", "+1%", "160"),
    ], as_of=as_of)
    assert result["month"].tolist() == ["2026-09-01"]
    assert result["avg_players"].tolist() == [80.0]


def test_observed_zero_and_calendar_gaps_are_preserved():
    result = parse([
        ("March 2025", "10", "", "", "20"),
        ("January 2025", "0", "", "", "0"),
    ])
    records = result.set_index("month").to_dict("index")
    assert set(records) == {"2025-01-01", "2025-03-01"}
    assert records["2025-01-01"]["avg_players"] == 0.0
    assert records["2025-01-01"]["peak_players"] == 0


def test_unrelated_tables_are_ignored_and_nested_text_is_parsed():
    prefix = "<table><tr><th>Metric</th><th>Value</th></tr><tr><td>Now</td><td>999</td></tr></table>"
    html = monthly_html([
        ("<span>September</span> <strong>2026</strong>", "<span>12.50</span>", "", "", "<b>25</b>"),
    ], prefix=prefix)
    result = parse_monthly_html(html, app_id=440, as_of="2026-10-25")
    assert result.to_dict("records") == [
        {"app_id": 440, "month": "2026-09-01", "avg_players": 12.5, "peak_players": 25},
    ]


def test_duplicate_months_are_rejected():
    with pytest.raises(ValueError):
        parse([
            ("September 2026", "10", "", "", "20"),
            ("September 2026", "11", "", "", "21"),
        ])


@pytest.mark.parametrize("average", ["-1", "nan", "NaN", "inf", "-inf", "unknown", ""])
def test_invalid_average_is_rejected(average):
    with pytest.raises(ValueError):
        parse([("September 2026", average, "", "", "20")])


@pytest.mark.parametrize("peak", ["-1", "2.5", "nan", "inf", "unknown", ""])
def test_invalid_peak_is_rejected(peak):
    with pytest.raises(ValueError):
        parse([("September 2026", "1", "", "", peak)])


def test_average_above_peak_is_rejected():
    with pytest.raises(ValueError):
        parse([("September 2026", "21", "", "", "20")])


@pytest.mark.parametrize("html", [
    "<html><body>No history available</body></html>",
    "<table><tr><th>Month</th><th>Price</th></tr><tr><td>September 2026</td><td>10</td></tr></table>",
])
def test_missing_monthly_table_is_rejected(html):
    with pytest.raises(ValueError):
        parse_monthly_html(html, app_id=730, as_of="2026-10-25")


def test_future_month_is_rejected():
    with pytest.raises(ValueError):
        parse([("November 2026", "10", "", "", "20")])


@pytest.mark.parametrize("month", ["Septober 2026", "2026-09", "September", "September 20xx"])
def test_malformed_month_label_is_rejected(month):
    with pytest.raises(ValueError):
        parse([(month, "10", "", "", "20")])


@pytest.mark.parametrize("row", [
    ("September 2026", "10", "", "20"),
    ("September 2026", "10", "", "", "20", "extra"),
])
def test_malformed_monthly_row_is_rejected(row):
    with pytest.raises(ValueError):
        parse([row])

def test_recent_release_probe_uses_complete_month_boundary(monkeypatch):
    import steamcharts_pilot as pilot

    games = pd.DataFrame([dict(app_id=730, name="Anchor", eligible=1,
                              review_group="Game-related labels only")])
    players = pd.DataFrame([dict(app_id=730, month="2025-09-01", avg_players=100.)])
    labels = pd.DataFrame([dict(app_id=730, genre="Action")])
    metadata = pd.DataFrame([
        dict(appID="1001", name="September release", release_date="Sep 25, 2025", peak_ccu=200),
        dict(appID="1002", name="October release", release_date="Oct 1, 2025", peak_ccu=100),
    ])
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: metadata)
    cohort = pilot.select_cohort(games, players, labels, "2026-10-25")
    assert 1001 not in {row["app_id"] for row in cohort}
    assert 1002 in {row["app_id"] for row in cohort}


def test_replay_rejects_changed_source_manifest_before_network(tmp_path, monkeypatch):
    import json
    import steamcharts_pilot as pilot

    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    (tmp_path / "database").mkdir()
    (tmp_path / "database/steam.sqlite").write_bytes(b"baseline")
    (tmp_path / "data/raw").mkdir(parents=True)
    (tmp_path / "data/raw/sources.json").write_text('{"changed": true}')
    folder = tmp_path / "data/raw/steamcharts_pilot/test-run"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({
        "baseline_database_sha256": pilot.digest(tmp_path / "database/steam.sqlite"),
        "baseline_sources_sha256": "previous-source-hash",
    }))
    monkeypatch.setattr(pilot, "load_baseline", lambda: (None, None, None))
    def reject_network(*a, **k):
        raise AssertionError("Source mismatch must fail before constructing an HTTP session")
    monkeypatch.setattr(pilot.requests, "Session", reject_network)
    with pytest.raises(ValueError, match="source"):
        pilot.collect(run_id="test-run", offline=True)


def test_offline_partial_snapshot_cannot_start_network_session(tmp_path,monkeypatch):
    import json
    import steamcharts_pilot as pilot
    folder=tmp_path/"data/raw/steamcharts_pilot/partial"
    folder.mkdir(parents=True)
    (folder/"manifest.json").write_text(json.dumps({"baseline_database_sha256":"same","baseline_sources_sha256":"same"}))
    monkeypatch.setattr(pilot,"ROOT",tmp_path)
    monkeypatch.setattr(pilot,"digest",lambda path:"same")
    monkeypatch.setattr(pilot,"load_baseline",lambda:(None,None,None))
    monkeypatch.setattr(pilot.requests,"Session",lambda:pytest.fail("Offline replay must not construct a network session"))
    with pytest.raises(FileNotFoundError,match="cached robots"):
        pilot.collect(run_id="partial",offline=True)

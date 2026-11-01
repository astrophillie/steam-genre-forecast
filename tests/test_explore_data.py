"""Regression checks for concentration and observed-total accounting."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from explore_data import concentration, observation_bridge


def test_concentration_is_within_each_label_and_ties_are_deterministic():
    panel = pd.DataFrame([
        ["Action", "2025-01", 2, 50.0], ["Action", "2025-01", 1, 50.0],
        ["RPG", "2025-01", 1, 50.0],
    ], columns=["category", "month", "app_id", "avg_players"])
    shares, ordered = concentration(panel)
    action = shares.set_index("category").loc["Action"]
    assert action["top1_share"] == .5
    assert action["top5_share"] == 1
    assert shares.set_index("category").loc["RPG", "top1_share"] == 1
    assert ordered.loc[ordered["category"].eq("Action") & ordered["rank"].eq(1), "app_id"].item() == 1


def test_zero_total_has_unknown_concentration():
    panel = pd.DataFrame([["Action", "2025-01", 1, 0.0]],
                         columns=["category", "month", "app_id", "avg_players"])
    shares, _ = concentration(panel)
    assert shares[["top1_share", "top5_share"]].isna().all().all()


def test_bridge_reconciles_without_imputing_missing_activity():
    panel = pd.DataFrame([
        ["Action", "before", 1, 100.0], ["Action", "after", 1, 80.0],
        ["Action", "before", 2, 40.0], ["Action", "after", 3, 15.0],
        ["Action", "before", 4, 0.0], ["Action", "after", 4, 0.0],
    ], columns=["category", "month", "app_id", "avg_players"])
    original = panel.copy(deep=True)
    bridge, pairs = observation_bridge(panel, "before", "after")
    components = bridge.set_index("component")
    assert components.loc["Observed in both months", "activity_change"] == -20
    assert components.loc["Observed only in comparison month", "activity_change"] == -40
    assert components.loc["Observed only in latest month", "activity_change"] == 15
    assert bridge["activity_change"].sum() == pytest.approx(95 - 140)
    assert pd.isna(pairs.set_index("app_id").loc[2, "avg_players_after"])
    assert pd.isna(pairs.set_index("app_id").loc[3, "avg_players_before"])
    pd.testing.assert_frame_equal(panel, original)


def test_bridge_zero_observation_is_present_not_absent():
    panel = pd.DataFrame([["Action", "before", 1, 0.0], ["Action", "after", 1, 10.0]],
                         columns=["category", "month", "app_id", "avg_players"])
    bridge, _ = observation_bridge(panel, "before", "after")
    assert bridge["component"].tolist() == ["Observed in both months"]
    assert bridge["activity_change"].item() == 10

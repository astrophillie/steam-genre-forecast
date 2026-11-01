import numpy as np
import pandas as pd
import pytest

from src.cohort_sensitivity import archive_coverage, select_leaders, exclusion_scenarios, SCENARIOS


@pytest.fixture
def panel():
    dates = pd.date_range("2021-02-01", "2026-01-01", freq="MS").strftime("%Y-%m-%d")
    return pd.concat([
        pd.DataFrame({"category": category, "app_id": app, "name": str(app),
                      "month": dates, "avg_players": value})
        for category, app, value in [("A", 1, 300.), ("A", 3, 100.), ("B", 2, 200.), ("B", 3, 100.)]
    ], ignore_index=True)


def test_shared_union_removes_games_from_every_category(panel):
    leaders = select_leaders(panel)
    monthly, summary = exclusion_scenarios(panel, leaders, sorted(panel.month.unique()))
    retained = monthly.loc[monthly.scenario.eq(SCENARIOS[1])]
    assert retained.avg_players.eq(100).all()
    assert retained.retained_games.eq(1).all()
    assert retained.excluded_union_games.eq(2).all()
    assert len(monthly) == 3 * 2 * 60
    assert summary.loc[summary.scenario.eq(SCENARIOS[1]), "cutoff_rank"].eq(1).all()
    baseline = monthly.loc[monthly.scenario.eq(SCENARIOS[0])].set_index(["category", "month"])
    expected = panel.groupby(["category", "month"]).avg_players.sum()
    pd.testing.assert_series_equal(baseline.avg_players, expected)


def test_overlapping_leader_is_removed_outside_its_selection_category(panel):
    data = panel.copy()
    data.loc[data.app_id.eq(1), "avg_players"] = 500.
    data.loc[data.app_id.eq(3), "avg_players"] = 400.
    leaders = select_leaders(data)
    monthly, _ = exclusion_scenarios(data, leaders, sorted(data.month.unique()))
    removed = monthly.loc[monthly.scenario.eq(SCENARIOS[1])]
    assert removed.loc[removed.category.eq("A"), "avg_players"].eq(0).all()
    assert removed.loc[removed.category.eq("B"), "avg_players"].eq(200).all()


def test_leader_ties_are_deterministic_and_unions_nested(panel):
    tied = panel.assign(avg_players=100.)
    leaders = select_leaders(tied.sample(frac=1, random_state=7))
    top = leaders.loc[leaders.category_position.eq(1)].set_index("category")
    assert top.loc["A", "app_id"] == 1
    assert top.loc["B", "app_id"] == 2
    assert set(top.app_id) <= set(leaders.app_id)


def test_missing_cutoff_observation_is_not_zero_activity():
    history = pd.DataFrame({"app_id": [1, 2], "month": ["2026-01-01"] * 2, "avg_players": [0., 50.]})
    members = pd.DataFrame({"app_id": [1, 2, 3], "category": ["A"] * 3, "in_cohort": [1, 0, 0]})
    result = archive_coverage(history, members).iloc[0]
    assert result.eligible_archive_games == 3
    assert result.cutoff_observed_games == 2
    assert result.cutoff_missing_games == 1
    assert result.observed_archive_activity == 50.
    assert result.cohort_observed_activity_share_pct == 0.
    with pytest.raises(ValueError, match="missing at cutoff"):
        archive_coverage(history.iloc[1:], members)


def test_zero_denominators_and_exhausted_categories_are_explicit(panel):
    zero = panel.assign(avg_players=0.)
    history = zero[["app_id", "month", "avg_players"]].drop_duplicates()
    members = zero[["app_id", "category"]].drop_duplicates().assign(in_cohort=1)
    assert archive_coverage(history, members).cohort_observed_activity_share_pct.isna().all()
    monthly, summary = exclusion_scenarios(zero, select_leaders(zero), sorted(zero.month.unique()))
    empty = monthly.loc[monthly.scenario.eq(SCENARIOS[2])]
    assert empty.empty_category.all() and empty.avg_players.eq(0).all()
    assert summary.cutoff_activity_retained_pct.isna().all()
    assert summary.start_to_cutoff_change_pct.isna().all()
    assert summary.loc[summary.scenario.eq(SCENARIOS[2]), "cutoff_rank"].isna().all()


@pytest.mark.parametrize("issue", ["gap", "duplicate", "negative", "nonfinite"])
def test_invalid_panel_cannot_be_filled_into_a_scenario(panel, issue):
    data = panel.copy()
    if issue == "gap":
        data = data.drop(0)
    elif issue == "duplicate":
        data = pd.concat([data, data.iloc[:1]], ignore_index=True)
    else:
        data.loc[0, "avg_players"] = -1. if issue == "negative" else np.inf
    with pytest.raises(ValueError):
        exclusion_scenarios(data, select_leaders(panel), sorted(panel.month.unique()))


@pytest.mark.parametrize("issue", ["reversed", "gap", "partial_year"])
def test_calendar_order_and_complete_annual_mean_are_required(panel, issue):
    data = panel.copy()
    if issue == "gap":
        data = data.loc[~data.month.eq("2025-06-01")]
    if issue == "partial_year":
        data = data.loc[data.month.ge("2025-02-01")]
    dates = sorted(data.month.unique(), reverse=issue == "reversed")
    with pytest.raises(ValueError, match="calendar"):
        exclusion_scenarios(data, select_leaders(data), dates)


def test_category_overlap_cannot_change_an_apps_measurement(panel):
    data = panel.copy()
    data.loc[data.category.eq("B") & data.app_id.eq(3), "avg_players"] += 1.
    with pytest.raises(ValueError, match="same activity"):
        exclusion_scenarios(data, select_leaders(data), sorted(data.month.unique()))

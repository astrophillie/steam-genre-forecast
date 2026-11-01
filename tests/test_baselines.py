"""Offline checks for fixed-origin monthly forecasting baselines."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from baselines import backtest, forecast_baselines, score_forecasts


def training_history():
    return pd.Series(
        np.arange(1, 25, dtype=float),
        index=pd.date_range("2019-07-01", periods=24, freq="MS"),
        name="avg_players",
    )


def category_history():
    months = pd.date_range("2020-01-01", periods=72, freq="MS")
    return pd.concat([
        pd.DataFrame({
            "category": category,
            "month": months,
            "avg_players": np.arange(1, 73, dtype=float) + offset,
        })
        for category, offset in [("Action", 0), ("Strategy", 100)]
    ], ignore_index=True)


def test_forecasts_use_last_value_and_repeat_last_annual_cycle_for_27_steps():
    train = training_history()
    original = train.copy(deep=True)
    forecasts = forecast_baselines(train, 27)
    assert set(forecasts) == {"Last value", "Seasonal naive"}
    np.testing.assert_array_equal(forecasts["Last value"], np.repeat(24.0, 27))
    # June origin: July repeats the preceding July, including in later forecast years.
    np.testing.assert_array_equal(forecasts["Seasonal naive"],
                                  np.concatenate([np.arange(13, 25), np.arange(13, 25), [13, 14, 15]]))
    pd.testing.assert_series_equal(train, original)


def test_twelve_month_history_and_observed_zero_are_valid():
    train = training_history().iloc[-12:] * 0
    forecasts = forecast_baselines(train, 1)
    assert forecasts["Last value"].tolist() == [0]
    assert forecasts["Seasonal naive"].tolist() == [0]


@pytest.mark.parametrize("horizon", [0, -1, 1.5, "12", True, None])
def test_invalid_horizon_is_rejected(horizon):
    with pytest.raises((ValueError, TypeError)):
        forecast_baselines(training_history(), horizon)


def test_less_than_one_annual_cycle_is_rejected():
    with pytest.raises(ValueError):
        forecast_baselines(training_history().iloc[-11:], 27)


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf, -1.0])
def test_unknown_nonfinite_and_negative_training_activity_is_rejected(bad_value):
    train = training_history()
    train.iloc[5] = bad_value
    with pytest.raises(ValueError):
        forecast_baselines(train, 27)


@pytest.mark.parametrize("calendar_problem", ["duplicate", "missing", "out_of_order", "not_month_start"])
def test_training_calendar_must_be_unique_continuous_ordered_month_starts(calendar_problem):
    train = training_history()
    if calendar_problem == "duplicate":
        dates = train.index.to_list()
        dates[5] = dates[4]
        train.index = pd.DatetimeIndex(dates)
    elif calendar_problem == "missing":
        train = train.drop(train.index[5])
    elif calendar_problem == "out_of_order":
        order = list(range(len(train)))
        order[4], order[5] = order[5], order[4]
        train = train.iloc[order]
    else:
        train.index = train.index + pd.Timedelta(days=1)
    with pytest.raises(ValueError):
        forecast_baselines(train, 27)


def test_backtest_targets_start_after_origin_and_reconcile_errors():
    monthly = category_history()
    origins = [pd.Timestamp("2021-12-01"), pd.Timestamp("2022-12-01")]
    result = backtest(monthly, origins, horizon=27)
    required = {"category", "origin", "month", "lead", "model", "actual", "prediction", "error"}
    assert required <= set(result.columns)
    assert len(result) == 2 * 2 * 2 * 27
    assert not result.duplicated(["category", "origin", "month", "model"]).any()
    assert (pd.to_datetime(result["month"]) > pd.to_datetime(result["origin"])).all()
    assert result["lead"].min() == 1
    assert result["lead"].max() == 27
    np.testing.assert_allclose(result["error"], result["actual"] - result["prediction"])
    first = result.loc[
        result["category"].eq("Action")
        & pd.to_datetime(result["origin"]).eq(origins[0])
        & result["lead"].eq(1)
    ].set_index("model")
    assert pd.Timestamp(first.loc["Last value", "month"]) == pd.Timestamp("2022-01-01")
    assert first.loc["Last value", "actual"] == 25
    assert first.loc["Last value", "prediction"] == 24
    assert first.loc["Seasonal naive", "prediction"] == 13
    assert first.loc["Last value", "error"] == 1


def test_future_actual_changes_do_not_change_fixed_origin_predictions():
    monthly = category_history()
    origin = pd.Timestamp("2021-12-01")
    first = backtest(monthly, [origin], horizon=27)
    changed = monthly.copy(deep=True)
    changed.loc[changed["month"].gt(origin), "avg_players"] += 1_000_000
    second = backtest(changed, [origin], horizon=27)
    keys = ["category", "origin", "month", "lead", "model"]
    first = first.sort_values(keys).reset_index(drop=True)
    second = second.sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(first[keys + ["prediction"]], second[keys + ["prediction"]])
    np.testing.assert_allclose(second["actual"] - first["actual"], 1_000_000)
    np.testing.assert_allclose(second["error"] - first["error"], 1_000_000)


@pytest.mark.parametrize("missing_month", ["2020-06-01", "2022-02-01"])
def test_backtest_rejects_gaps_in_training_or_evaluation_months(missing_month):
    monthly = category_history()
    monthly = monthly.loc[~(
        monthly["category"].eq("Action") & monthly["month"].eq(pd.Timestamp(missing_month))
    )]
    with pytest.raises(ValueError):
        backtest(monthly, [pd.Timestamp("2021-12-01")], horizon=27)


def test_backtest_rejects_incomplete_horizon_instead_of_scoring_fewer_months():
    monthly = category_history()
    with pytest.raises(ValueError):
        backtest(monthly, [pd.Timestamp("2024-12-01")], horizon=27)


def test_backtest_rejects_duplicate_category_month_records():
    monthly = category_history()
    monthly = pd.concat([monthly, monthly.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError):
        backtest(monthly, [pd.Timestamp("2021-12-01")], horizon=27)


def test_scores_match_hand_calculation_and_keep_long_leads_separate():
    errors = np.concatenate([np.ones(15), np.repeat(3.0, 12)])
    predictions = pd.DataFrame({
        "category": "Action",
        "model": "Last value",
        "origin": pd.Timestamp("2021-12-01"),
        "lead": np.arange(1, 28),
        "actual": np.repeat(10.0, 27),
        "prediction": 10.0 - errors,
        "error": errors,
    })
    scores = score_forecasts(predictions).set_index("window")
    all_leads = scores.loc["All 27 leads"]
    long_leads = scores.loc["Leads 16 to 27"]
    assert all_leads["mae"] == pytest.approx(51 / 27)
    assert all_leads["rmse"] == pytest.approx(np.sqrt(123 / 27))
    assert all_leads["wape_pct"] == pytest.approx(100 * 51 / 270)
    assert all_leads["mean_error"] == pytest.approx(51 / 27)
    assert all_leads["scored_predictions"] == 27
    assert all_leads["origins"] == 1
    assert long_leads["mae"] == 3
    assert long_leads["rmse"] == 3
    assert long_leads["wape_pct"] == 30
    assert long_leads["scored_predictions"] == 12


def test_scores_leave_zero_denominator_wape_unknown_and_preserve_error_sign():
    predictions = pd.DataFrame({
        "category": "Action",
        "model": "Last value",
        "origin": pd.Timestamp("2021-12-01"),
        "lead": np.arange(1, 28),
        "actual": np.zeros(27),
        "prediction": np.ones(27),
        "error": -np.ones(27),
    })
    scores = score_forecasts(predictions)
    assert scores["wape_pct"].isna().all()
    assert scores["mae"].eq(1).all()
    assert scores["rmse"].eq(1).all()
    assert scores["mean_error"].eq(-1).all()

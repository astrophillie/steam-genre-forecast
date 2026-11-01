"""Versioned development comparison on the frozen, retrospectively selected cohort."""
from pathlib import Path
import hashlib
import json
import sqlite3
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
try:
    from .baselines import validate_series, forecast_baselines
    from .statistical_models import CONFIGS, forecast_statistical
    from .gradient_boosting import PARAMS, training_features, recursive_predict
    from .audit_validation import validate_predictions, require_same_targets
except ImportError:
    from baselines import validate_series, forecast_baselines
    from statistical_models import CONFIGS, forecast_statistical
    from gradient_boosting import PARAMS, training_features, recursive_predict
    from audit_validation import validate_predictions, require_same_targets

ROOT = Path(__file__).resolve().parents[1]
HORIZON = 23
ORIGINS = pd.to_datetime(["2024-01-01", "2024-02-01"])
MODELS = ["Last value", "Seasonal naive", *CONFIGS, "Gradient boosting"]


def evaluate(monthly, origins=ORIGINS):
    required = {"category", "month", "avg_players"}
    if not required <= set(monthly) or monthly.empty:
        raise ValueError("Required category/month/activity observations missing")
    data = monthly.copy()
    data["month"] = pd.to_datetime(data.month, errors="raise")
    if data.category.isna().any() or data.duplicated(["category", "month"]).any():
        raise ValueError("Missing category or duplicate category/month")
    origins = pd.DatetimeIndex(origins)
    if origins.empty or origins.hasnans or not origins.is_unique or not origins.is_month_start.all():
        raise ValueError("Unique month-start origins required")
    rows, fits = [], []
    for category, frame in data.groupby("category"):
        series = frame.set_index("month").avg_players.sort_index()
        validate_series(series)
        for origin in origins:
            train = series.loc[:origin]
            dates = pd.date_range(origin + pd.offsets.MonthBegin(), periods=HORIZON, freq="MS")
            actual = series.reindex(dates)
            if origin not in series.index or len(train) < 36 or actual.isna().any():
                raise ValueError("Each fold needs 36 training months and 23 observed future months")
            predictions = forecast_baselines(train, HORIZON)
            for model in CONFIGS:
                values, info = forecast_statistical(train, HORIZON, model)
                predictions[model] = values
                fits.append({"category": category, "origin": origin, "model": model, "training_months": len(train), **info})
            X, y = training_features(train)
            fitted = GradientBoostingRegressor(**PARAMS).fit(X, y)
            predicted, clipped = recursive_predict(fitted, train.to_numpy(), dates[0], HORIZON)
            predictions["Gradient boosting"] = predicted
            fits.append({"category": category, "origin": origin, "model": "Gradient boosting", "training_months": len(train), "training_rows": len(y), "training_mae": float(np.abs(y-fitted.predict(X)).mean()), "clipped_predictions": clipped})
            for model, values in predictions.items():
                rows.append(pd.DataFrame({"category": category, "origin": origin, "month": dates, "lead": np.arange(1,HORIZON+1), "model": model, "actual": actual.to_numpy(), "prediction": values}))
    predictions = pd.concat(rows, ignore_index=True)
    predictions["error"] = predictions.actual - predictions.prediction
    predictions = validate_predictions(predictions)
    require_same_targets(predictions, predictions)
    return predictions, pd.DataFrame(fits)


def summarise(predictions):
    data = validate_predictions(predictions)
    if "Last value" not in set(data.model) or data.lead.max() != HORIZON:
        raise ValueError("A complete 23-month last-value reference is required")
    require_same_targets(data, data)
    rows = []
    for window, low, high in [("All 23 leads", 1, 23), ("Leads 12 to 23", 12, 23)]:
        selected = data.loc[data.lead.between(low, high)].copy()
        for (category, model, origin), frame in selected.groupby(["category", "model", "origin"]):
            error = frame.error.to_numpy()
            magnitude = float(np.abs(error).max())
            actual_scale = float(frame.actual.max())
            unsafe = magnitude > np.sqrt(np.finfo(float).max / len(frame)) or actual_scale > np.finfo(float).max / len(frame)
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                try:
                    if unsafe:
                        mae = magnitude * np.mean(np.abs(error) / magnitude) if magnitude else 0.
                        rmse = magnitude * np.sqrt(np.mean((error / magnitude)**2)) if magnitude else 0.
                        mean_error = magnitude * np.mean(error / magnitude) if magnitude else 0.
                        actual_mean = actual_scale * np.mean(frame.actual / actual_scale) if actual_scale else 0.
                        wape = 100 * (mae / actual_mean) if actual_mean else np.nan
                    else:
                        denominator = frame.actual.sum()
                        mae, rmse, mean_error = np.abs(error).mean(), np.sqrt(np.mean(error**2)), error.mean()
                        wape = 100*np.abs(error).sum()/denominator if denominator else np.nan
                except FloatingPointError as exc:
                    raise ValueError("Unrepresentable forecast metric") from exc
            if not np.isfinite([mae, rmse, mean_error]).all() or (actual_scale and not np.isfinite(wape)):
                raise ValueError("Unrepresentable forecast metric")
            rows.append({"window": window, "category": category, "model": model, "origin": origin, "mae": mae, "rmse": rmse, "mean_error": mean_error, "wape_pct": wape, "worst_absolute_error": magnitude, "observations": len(frame)})
    folds = pd.DataFrame(rows)
    reference = folds.loc[folds.model.eq("Last value"), ["window", "category", "origin", "mae"]].rename(columns={"mae": "last_value_mae"})
    folds = folds.merge(reference, on=["window", "category", "origin"], how="left", validate="many_to_one")
    if folds.last_value_mae.isna().any():
        raise ValueError("Missing baseline fold")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        folds["skill_vs_last_value_pct"] = np.where(folds.last_value_mae.gt(0), 100*(1-folds.mae/folds.last_value_mae.replace(0,np.nan)), np.nan)
    if not np.isfinite(folds.loc[folds.last_value_mae.gt(0), "skill_vs_last_value_pct"]).all():
        raise ValueError("Unrepresentable relative forecast skill")
    # Suppress numerical near-ties: a win requires more than 0.1 percent lower MAE.
    scores = folds.groupby(["window", "category", "model"], as_index=False).agg(mae=("mae", "mean"), rmse=("rmse", "mean"), mean_error=("mean_error", "mean"), wape_pct=("wape_pct", "mean"), worst_fold_mae=("mae", "max"), wins_vs_last_value=("skill_vs_last_value_pct", lambda x: int(x.gt(0.1).sum())), folds=("origin", "nunique"))
    # pandas group means may overflow even when their finite mean is representable.
    for index, row in scores.iterrows():
        group = folds.loc[folds.window.eq(row.window) & folds.category.eq(row.category) & folds.model.eq(row.model)]
        for column in ["mae", "rmse", "mean_error", "wape_pct"]:
            if not np.isfinite(row[column]):
                values = group[column].dropna().to_numpy(dtype=float)
                if not len(values) and column == "wape_pct":
                    continue
                magnitude = float(np.abs(values).max())
                scores.at[index, column] = magnitude * np.mean(values / magnitude) if magnitude else 0.
                if not np.isfinite(scores.at[index, column]):
                    raise ValueError("Unrepresentable aggregate forecast metric")
    return folds, scores


def run(root=ROOT):
    root = Path(root)
    scope_path = root/"config/project_scope.json"
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    if scope["active_dataset"] != "fixed_sources_v2" or scope["forecast_horizon"] != HORIZON or scope["target_leads"] != [12,23]:
        raise ValueError("Evaluation scope changed; define another version")
    source = root/scope["category_input"]
    registry = root/scope["source_registry"]
    monthly = pd.read_csv(source)
    registered = json.loads(registry.read_text(encoding="utf-8"))
    if registered["cohort_apps"] != 519 or registered["modelling_cutoff"] != "2026-01-01" or registered["window_start"] != "2021-02-01":
        raise ValueError("Frozen cohort registry changed")
    connection = sqlite3.connect((root/scope["database"]).resolve().as_uri()+"?mode=ro", uri=True)
    try:
        database_monthly = pd.read_sql_query("SELECT * FROM category_monthly", connection)
    finally:
        connection.close()
    columns = ["category", "month", "avg_players", "observed_apps"]
    pd.testing.assert_frame_equal(monthly[columns].sort_values(columns[:2]).reset_index(drop=True), database_monthly[columns].sort_values(columns[:2]).reset_index(drop=True), check_dtype=False, rtol=1e-12, atol=1e-7)
    expected_dates = pd.date_range("2021-02-01", "2026-01-01", freq="MS")
    expected_categories = {"Action", "Indie", "Massively Multiplayer", "RPG", "Strategy"}
    if set(monthly.category) != expected_categories or len(monthly) != 300:
        raise ValueError("Frozen category inventory changed")
    for _, frame in monthly.groupby("category"):
        if not pd.DatetimeIndex(pd.to_datetime(frame.month)).sort_values().equals(expected_dates):
            raise ValueError("Frozen monthly window changed")
    predictions, fits = evaluate(monthly)
    folds, scores = summarise(predictions)
    worst = predictions.assign(absolute_error=lambda x: x.error.abs()).sort_values("absolute_error", ascending=False).groupby(["category", "model"]).head(3)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"input_sha256": digest(source), "registry_sha256": digest(registry), "scope_sha256": digest(scope_path), "origins": [str(x.date()) for x in ORIGINS], "horizon": HORIZON, "target_leads": [12,23], "models": MODELS, "boosting_parameters": PARAMS, "statistical_configs": CONFIGS, "training_months": [36,37], "scope": "Retrospective development comparison of the frozen 519-game cohort selected with October 2026 knowledge; overlapping test periods; no independent test or final selection", "error_sign": "actual minus prediction; positive means underprediction", "metric_note": "Scores average two fold metrics; WAPE unavailable if observed total is zero; no inferential confidence from overlapping folds"}
    folder = root/"reports/fixed_cohort_evaluation"
    folder.mkdir(exist_ok=True)
    for name, frame in [("predictions",predictions),("fit_diagnostics",fits),("fold_scores",folds),("scores",scores),("worst_errors",worst)]:
        frame.to_csv(folder/f"{name}.csv", index=False)
    manifest["predictions_sha256"] = digest(folder/"predictions.csv")
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return predictions, scores, fits, folds


if __name__ == "__main__":
    _, scores, _, _ = run()
    print(scores.loc[scores.window.eq("Leads 12 to 23")].sort_values(["category","mae"]).to_string(index=False))

"""Fixed-origin historical benchmarks for recorded category activity."""
from contextlib import closing
from numbers import Integral
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

try:
    from .audit_validation import validate_predictions, require_lineage, require_same_targets
except ImportError:
    from audit_validation import validate_predictions, require_lineage, require_same_targets
ROOT = Path(__file__).resolve().parents[1]
ORIGINS = pd.to_datetime(["2020-06-01", "2021-06-01", "2022-06-01", "2023-06-01"])
HORIZON = 27
MODEL_COLORS = {"Last value": "#9c83cc", "Seasonal naive": "#cf8d79"}


def validate_series(series):
    """Require an ordered, complete monthly series with observed nonnegative values."""
    if not isinstance(series, pd.Series) or not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError("Expected a pandas Series with a monthly DatetimeIndex")
    if series.empty or not series.index.is_unique or not series.index.is_monotonic_increasing:
        raise ValueError("Monthly observations must be nonempty, unique, and ordered")
    expected = pd.date_range(series.index.min(), series.index.max(), freq="MS")
    if not series.index.equals(expected):
        raise ValueError("Month-start observations must be continuous without missing months")
    values = pd.to_numeric(series, errors="raise").to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Observed activity must be finite, nonnegative, and nonmissing")
    return values


def forecast_baselines(train, horizon):
    """Freeze last-value and annual-cycle predictions using training values only."""
    if isinstance(horizon, bool) or not isinstance(horizon, Integral) or horizon <= 0:
        raise ValueError("The forecast horizon must be a positive integer")
    values = validate_series(train)
    if len(values) < 12:
        raise ValueError("Both benchmarks require at least 12 observed months")
    return {
        "Last value": np.repeat(values[-1], horizon),
        "Seasonal naive": values[-12:][np.arange(horizon) % 12],
    }


def backtest(monthly, origins, horizon=HORIZON):
    """Evaluate frozen multi-step predictions; actuals never update within a fold."""
    required = {"category", "month", "avg_players"}
    if not required <= set(monthly.columns):
        raise ValueError("Missing required category/month/activity columns")
    if monthly.empty or monthly["category"].isna().any():
        raise ValueError("Categories must be present")
    data = monthly.copy()
    data["month"] = pd.to_datetime(data["month"], errors="raise")
    if data["month"].isna().any() or data.duplicated(["category", "month"]).any():
        raise ValueError("Missing dates or repeated category/month keys")
    origins = pd.DatetimeIndex(origins)
    if origins.empty or origins.hasnans or not origins.is_unique:
        raise ValueError("Forecast origins must be present and unique")
    rows = []
    for category, frame in data.groupby("category"):
        series = frame.set_index("month")["avg_players"].sort_index()
        validate_series(series)
        for origin in origins:
            if origin not in series.index:
                raise ValueError("Every origin must be an observed month")
            train = series.loc[:origin]
            predictions = forecast_baselines(train, horizon)
            dates = pd.date_range(origin + pd.offsets.MonthBegin(), periods=horizon, freq="MS")
            actual = series.reindex(dates)
            if actual.isna().any():
                raise ValueError("All evaluation months must have observed category activity")
            for model, values in predictions.items():
                rows.append(pd.DataFrame({
                    "category": category, "origin": origin, "month": dates,
                    "lead": np.arange(1, horizon + 1), "model": model,
                    "actual": actual.to_numpy(dtype=float), "prediction": values,
                }))
    result = pd.concat(rows, ignore_index=True)
    result["error"] = result["actual"] - result["prediction"]
    if not (result["month"] > result["origin"]).all():
        raise ValueError("Evaluation dates must follow the forecast origin")
    return result


def score_forecasts(predictions):
    """Scores by category/model and lead range; overlapping folds stay explicit."""
    predictions = validate_predictions(predictions)
    rows = []
    for window, low, high in [("All 27 leads", 1, 27), ("Leads 16 to 27", 16, 27)]:
        selected = predictions.loc[predictions["lead"].between(low, high)]
        for (category, model), group in selected.groupby(["category", "model"]):
            error = group["error"].to_numpy()
            magnitude = float(np.max(np.abs(error)))
            mae = magnitude * np.mean(np.abs(error)/magnitude) if magnitude else 0.
            rmse = magnitude * np.sqrt(np.mean(np.square(error/magnitude))) if magnitude else 0.
            mean_error = magnitude * np.mean(error/magnitude) if magnitude else 0.
            actual_scale = float(group["actual"].max())
            actual_mean = actual_scale * np.mean(group["actual"]/actual_scale) if actual_scale else 0.
            wape = (mae/actual_mean)*100 if actual_mean else np.nan
            if actual_mean and not np.isfinite(wape): raise ValueError("Unrepresentable percentage error")
            rows.append({
                "category": category, "model": model, "window": window,
                "origins": group["origin"].nunique(), "scored_predictions": len(group),
                "mae": mae, "rmse": rmse,
                "wape_pct": wape,
                "mean_error": mean_error,
            })
    return pd.DataFrame(rows)


def run_evaluation():
    database = ROOT / "database/steam.sqlite"
    if not database.exists():
        raise FileNotFoundError("Run src/prepare_data.py before baseline evaluation")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        monthly = pd.read_sql_query("SELECT * FROM category_monthly ORDER BY category, month", connection)
    monthly["month"] = pd.to_datetime(monthly["month"])
    predictions = backtest(monthly, ORIGINS)
    scores = score_forecasts(predictions)
    fold_scores = predictions.assign(absolute_error=predictions["error"].abs()).groupby(
        ["category", "model", "origin"], as_index=False
    ).agg(mae=("absolute_error", "mean"), scored_predictions=("lead", "size"))
    lead_scores = predictions.assign(absolute_error=predictions["error"].abs()).groupby(
        ["category", "model", "lead"], as_index=False
    ).agg(mae=("absolute_error", "mean"), origins=("origin", "nunique"))
    target_window = predictions.loc[predictions["lead"].between(16, 27)]
    annual_means = target_window.groupby(["category", "model", "origin"], as_index=False).agg(
        actual_mean=("actual", "mean"), predicted_mean=("prediction", "mean"),
        scored_months=("lead", "size"),
    )
    annual_means["mean_error"] = annual_means["actual_mean"] - annual_means["predicted_mean"]
    annual_means["absolute_mean_error"] = annual_means["mean_error"].abs()
    if not annual_means["scored_months"].eq(12).all():
        raise ValueError("Target comparison windows must contain 12 months")
    report = ROOT / "reports"
    for name, frame in [
        ("predictions", predictions), ("scores", scores), ("fold_scores", fold_scores),
        ("lead_scores", lead_scores), ("target_means", annual_means),
    ]:
        frame.to_csv(report / f"baseline_{name}.csv", index=False)
    return monthly, predictions, scores, fold_scores, lead_scores, annual_means


def plot_forecasts(monthly, predictions):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    origin = predictions["origin"].max()
    categories = sorted(monthly["category"].unique())
    fig, axes = plt.subplots(3, 2, figsize=(12, 10))
    last = predictions["month"].max()
    for ax, category in zip(axes.flat, categories):
        observed = monthly.loc[monthly["category"].eq(category) & monthly["month"].ge(origin - pd.DateOffset(months=12))]
        ax.plot(observed["month"], observed["avg_players"], color="#514b65", lw=1.5, label="Recorded activity")
        selected = predictions.loc[predictions["category"].eq(category) & predictions["origin"].eq(origin)]
        for model, group in selected.groupby("model"):
            ax.plot(group["month"], group["prediction"], label=model, color=MODEL_COLORS[model],
                    ls="--" if model == "Last value" else ":")
        ax.axvline(origin, color="#777777", lw=.8);ax.set_title(category, loc="left")
        ax.set_ylim(bottom=0);ax.grid(axis="y", alpha=.2)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v/1e6:.2f}m"))
        dates = [observed["month"].min(), origin, last]
        ax.set_xticks(dates, [d.strftime("%b %Y") for d in dates])
        ax.tick_params(axis="x", labelsize=9)
    axes.flat[-1].axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.suptitle("Frozen forecasts from June 2023", x=.06, ha="left", fontsize=16)
    fig.supylabel("Recorded category average concurrent activity")
    fig.text(.06, .05, "27-month historical evaluation | Each panel uses its own vertical scale; labels overlap.", fontsize=9)
    fig.tight_layout(rect=(0, .085, 1, .95))
    return fig


def plot_scores(scores):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    selected = scores.loc[scores["window"].eq("Leads 16 to 27")]
    categories = sorted(selected["category"].unique())
    fig, ax = plt.subplots(figsize=(11, 5))
    positions = np.arange(len(categories))
    for offset, model in zip([-.18, .18], MODEL_COLORS):
        values = selected.loc[selected["model"].eq(model)].set_index("category").reindex(categories)["mae"]
        bars = ax.barh(positions + offset, values, height=.34, label=model, color=MODEL_COLORS[model])
        for bar, value in zip(bars, values):
            ax.text(value + selected["mae"].max() * .012, bar.get_y() + bar.get_height()/2,
                    f"{value:,.0f}", va="center", fontsize=9)
    ax.set_yticks(positions, categories);ax.invert_yaxis();ax.set_xlim(0, selected["mae"].max()*1.21)
    ax.set_xlabel("Mean absolute error in category activity units");ax.grid(axis="x", alpha=.2)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v,_:f"{v/1000:.0f}k"))
    ax.set_title("Long-lead monthly error across four historical origins", loc="left")
    ax.legend(frameon=False, loc="lower right")
    fig.text(.04, .02, "Leads 16–27 | Lower error is better; absolute errors reflect category scale.", fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    return fig


def plot_lead_errors(lead_scores):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    categories = sorted(lead_scores["category"].unique())
    fig, axes = plt.subplots(3, 2, figsize=(12, 9))
    for ax, category in zip(axes.flat, categories):
        for model, group in lead_scores.loc[lead_scores["category"].eq(category)].groupby("model"):
            ax.plot(group["lead"], group["mae"], color=MODEL_COLORS[model],
                    ls="--" if model == "Last value" else "-", label=model)
        ax.axvspan(16, 27, color="#f0e9f7", alpha=.7)
        ax.set_title(category, loc="left");ax.set_ylim(bottom=0);ax.set_xlim(1, 27)
        ax.set_xticks([1, 6, 12, 16, 21, 27]);ax.grid(axis="y", alpha=.2)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_:f"{v/1000:.0f}k"))
    axes.flat[-1].axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False)
    fig.suptitle("Error by forecast lead", x=.06, ha="left", fontsize=16)
    fig.supxlabel("Months after the forecast origin", y=.04)
    fig.supylabel("Mean absolute error")
    fig.text(.06, .08, "Four overlapping historical evaluation windows; shading marks leads 16–27. Panel scales differ.", fontsize=9)
    fig.tight_layout(rect=(0, .10, 1, .95))
    return fig

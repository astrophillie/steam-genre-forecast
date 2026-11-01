"""Descriptive diagnostics for the prepared historical Steam cohort."""
from contextlib import closing
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ["Action", "Indie", "Massively Multiplayer", "RPG", "Strategy"]
COLORS = dict(zip(CATEGORIES, ["#9c83cc", "#cf8d79", "#6eaa96", "#7d9fca", "#c9809e"]))


def calendar_ticks(ax, monthly):
    """Keep the first and last reviewed month visible on the temporal axis."""
    dates = [monthly["month"].min(), pd.Timestamp("2015-01-01"),
             pd.Timestamp("2020-01-01"), monthly["month"].max()]
    dates = sorted(set(d for d in dates if monthly["month"].min() <= d <= monthly["month"].max()))
    ax.set_xticks(dates, [d.strftime("%b %Y") for d in dates])
    ax.set_xlim(monthly["month"].min(), monthly["month"].max())



def concentration(panel):
    """Activity concentration among observed eligible apps in each category/month."""
    ordered = panel.sort_values(
        ["category", "month", "avg_players", "app_id"],
        ascending=[True, True, False, True],
    ).copy()
    ordered["rank"] = ordered.groupby(["category", "month"]).cumcount() + 1
    totals = ordered.groupby(["category", "month"])["avg_players"].sum()
    top_one = ordered.loc[ordered["rank"].eq(1)].set_index(["category", "month"])["avg_players"]
    top_five = ordered.loc[ordered["rank"].le(5)].groupby(["category", "month"])["avg_players"].sum()
    denominator = totals.replace(0, np.nan)
    result = pd.DataFrame({"top1_share": top_one / denominator, "top5_share": top_five / denominator})
    return result.reset_index(), ordered


def observation_bridge(panel, before, after):
    """Reconcile observed totals across two dates without treating absent facts as zero.

    Contribution accounting uses zero only for a period's absent contribution to
    the observed total; it does not impute an app's unobserved activity.
    """
    earlier = panel.loc[panel["month"].eq(before), ["category", "app_id", "avg_players"]]
    later = panel.loc[panel["month"].eq(after), ["category", "app_id", "avg_players"]]
    pairs = earlier.merge(later, on=["category", "app_id"], how="outer",
                          suffixes=("_before", "_after"), validate="one_to_one", indicator=True)
    pairs["component"] = pairs["_merge"].map({
        "both": "Observed in both months",
        "right_only": "Observed only in latest month",
        "left_only": "Observed only in comparison month",
    }).astype(str)
    both = pairs["_merge"].eq("both")
    pairs["contribution"] = np.nan
    pairs.loc[both, "contribution"] = pairs.loc[both, "avg_players_after"] - pairs.loc[both, "avg_players_before"]
    pairs.loc[pairs["_merge"].eq("right_only"), "contribution"] = pairs.loc[pairs["_merge"].eq("right_only"), "avg_players_after"]
    pairs.loc[pairs["_merge"].eq("left_only"), "contribution"] = -pairs.loc[pairs["_merge"].eq("left_only"), "avg_players_before"]
    bridge = pairs.groupby(["category", "component"], observed=True).agg(
        activity_change=("contribution", "sum"), apps=("app_id", "nunique")
    ).reset_index()
    return bridge, pairs


def load_analysis():
    database = ROOT / "database/steam.sqlite"
    if not database.exists():
        raise FileNotFoundError("Run src/prepare_data.py before exploratory analysis")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        category = pd.read_sql_query("SELECT * FROM category_monthly ORDER BY category, month", connection)
        panel = pd.read_sql_query((ROOT / "sql/category_app_month.sql").read_text(encoding="utf-8"), connection)
    for frame in [category, panel]:
        frame["month"] = pd.to_datetime(frame["month"], format="%Y-%m-%d")
    if panel.duplicated(["category", "app_id", "month"]).any():
        raise ValueError("Repeated category/app/month observations")
    activity = panel.groupby(["category", "month"])["avg_players"].sum()
    observed = panel.groupby(["category", "month"])["app_id"].nunique()
    indexed = category.set_index(["category", "month"])
    pd.testing.assert_series_equal(indexed["avg_players"], activity.reindex(indexed.index),
                                   check_names=False, rtol=1e-10, atol=1e-6)
    pd.testing.assert_series_equal(indexed["observed_apps"], observed.reindex(indexed.index, fill_value=0),
                                   check_names=False, check_dtype=False)
    shares, ordered = concentration(panel)
    monthly = category.merge(shares, on=["category", "month"], how="left", validate="one_to_one")
    monthly = monthly.sort_values(["category", "month"])
    latest = monthly["month"].max()
    comparison = latest - pd.DateOffset(years=1)
    bridge, pairs = observation_bridge(panel, comparison, latest)
    latest_summary = monthly.loc[monthly["month"].eq(latest)].set_index("category")
    previous = monthly.loc[monthly["month"].eq(comparison)].set_index("category")
    latest_summary["comparison_activity"] = previous["avg_players"]
    latest_summary["year_over_year_pct"] = (
        latest_summary["avg_players"] / previous["avg_players"].replace(0, np.nan) - 1
    ) * 100
    latest_summary["comparison_observed_apps"] = previous["observed_apps"]
    latest_summary = latest_summary.reset_index()
    change = latest_summary.set_index("category")["avg_players"] - previous["avg_players"]
    pd.testing.assert_series_equal(change.sort_index(),
        bridge.groupby("category")["activity_change"].sum().reindex(change.index).sort_index(),
        check_names=False, rtol=1e-10, atol=1e-6)
    assert monthly["coverage_rate"].between(0, 1).all()
    assert monthly["top5_share"].dropna().between(0, 1 + 1e-12).all()
    return monthly, ordered, latest_summary, bridge, pairs


def save_tables(monthly, ordered, summary, bridge, pairs):
    folder = ROOT / "reports"
    monthly.to_csv(folder / "exploration_monthly.csv", index=False)
    summary.to_csv(folder / "exploration_latest_summary.csv", index=False)
    ordered.loc[ordered["month"].eq(monthly["month"].max()) & ordered["rank"].le(5)].to_csv(
        folder / "exploration_top_games.csv", index=False)
    bridge.to_csv(folder / "exploration_year_over_year_bridge.csv", index=False)
    # Inspectable app-level evidence behind each accounting contribution.
    names = ordered[["app_id", "name"]].drop_duplicates("app_id")
    pairs.merge(names, on="app_id", how="left", validate="many_to_one").to_csv(
        folder / "exploration_bridge_apps.csv", index=False)


def plot_activity(monthly):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), sharex=True, sharey=True)
    maximum = monthly["avg_players"].max() * 1.05
    for ax, category in zip(axes.flat, CATEGORIES):
        frame = monthly.loc[monthly["category"].eq(category)].set_index("month")
        continuous = frame.reindex(pd.date_range(monthly["month"].min(), monthly["month"].max(), freq="MS"))
        ax.plot(continuous.index, continuous["avg_players"], color=COLORS[category], lw=1.5)
        ax.set_title(category, loc="left")
        ax.set_ylim(0, maximum)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v/1e6:.1f}m"))
        ax.grid(axis="y", alpha=.2)
        calendar_ticks(ax, monthly)
        ax.tick_params(axis="x", rotation=0)
    axes.flat[-1].axis("off")
    fig.suptitle("Observed category activity", x=.08, ha="left", fontsize=16)
    fig.supylabel("Summed average concurrent activity")
    fig.text(.08, .025, "Eligible tracked apps, July 2012–September 2025 | Shared vertical scale; labels overlap.", fontsize=10)
    fig.tight_layout(rect=(0, .055, 1, .95))
    return fig


def plot_coverage(monthly):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    styles = ["-", "--", "-.", ":", (0, (4, 1, 1, 1))]
    for category, style in zip(CATEGORIES, styles):
        frame = monthly.loc[monthly["category"].eq(category)]
        axes[0].plot(frame["month"], frame["observed_apps"], color=COLORS[category], ls=style, label=category)
        axes[1].plot(frame["month"], frame["coverage_rate"], color=COLORS[category], ls=style)
    axes[0].set(title="Observed eligible apps", ylabel="App count")
    axes[1].set(title="Coverage within first-to-last recorded app spans", ylabel="Internal coverage", ylim=(0, 1.03))
    axes[0].set_ylim(bottom=0)
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    for ax in axes:
        ax.grid(axis="y", alpha=.2)
        calendar_ticks(ax, monthly)
    axes[0].legend(ncol=3, frameon=False, fontsize=10, loc="upper left")
    fig.text(.08, .025, "Internal coverage excludes time outside recorded spans; 100% at the endpoint follows from this definition.", fontsize=9)
    fig.tight_layout(rect=(0, .055, 1, 1))
    return fig


def plot_concentration(summary):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    frame = summary.set_index("category").reindex(CATEGORIES)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.barh(frame.index, frame["top5_share"], color="#9c83cc", label="Five largest observed apps")
    ax.barh(frame.index, 1 - frame["top5_share"], left=frame["top5_share"],
            color="#ebe5f1", label="Other observed apps")
    for i, value in enumerate(frame["top5_share"]):
        ax.text(value / 2, i, f"{value:.1%}", va="center", ha="center", color="#292335", weight="bold")
    ax.set(xlim=(0, 1), xlabel="Share of category activity", title="Top five app concentration in September 2025")
    ax.xaxis.set_major_formatter(PercentFormatter(1));ax.invert_yaxis()
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.15), ncol=2, frameon=False)
    fig.text(.04, .02, "Within-category shares of observed eligible activity; categories overlap.", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, 1))
    return fig


def plot_bridge(bridge):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    components = ["Observed in both months", "Observed only in latest month", "Observed only in comparison month"]
    labels = ["Both months: activity change", "Latest month only: added contribution", "Comparison month only: removed contribution"]
    fig, axes = plt.subplots(5, 1, figsize=(12, 12), sharex=True)
    limit = max(abs(bridge["activity_change"]).max() * 1.18, 1)
    for ax, category in zip(axes, CATEGORIES):
        frame = bridge.loc[bridge["category"].eq(category)].set_index("component").reindex(components)
        values = frame["activity_change"].fillna(0)
        ax.barh(labels, values, color=["#9c83cc" if v >= 0 else "#cf8d79" for v in values])
        for i, value in enumerate(values):
            ax.annotate(f"{value:+,.0f}", (value, i), xytext=(4 if value >= 0 else -4, 0),
                        textcoords="offset points", ha="left" if value >= 0 else "right", va="center", fontsize=9)
        ax.axvline(0, color="#555555", lw=.8);ax.set_xlim(-limit, limit)
        ax.set_title(category, loc="left");ax.invert_yaxis()
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    axes[-1].set_xlabel("Contribution to change in summed average concurrent activity")
    fig.suptitle("September 2024 to September 2025 observed-total change", x=.04, ha="left", fontsize=15)
    fig.text(.04, .015, "Accounting of observed totals; presence in one month does not establish a release, closure, or tracking cause.", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .96))
    return fig

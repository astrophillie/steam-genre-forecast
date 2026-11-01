"""Descriptive archive coverage and shared-leader exclusions; no model fitting."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
START = "2021-02-01"
CUTOFF = "2026-01-01"
CATEGORIES = ["Action", "Indie", "Massively Multiplayer", "RPG", "Strategy"]
SCENARIOS = ["Full cohort", "Without shared top-1 union", "Without shared top-5 union"]


def archive_coverage(history, members, cutoff=CUTOFF):
    """Denominators are eligible labelled archive games, not the Steam market."""
    if history.duplicated(["app_id", "month"]).any() or members.duplicated(["app_id", "category"]).any():
        raise ValueError("Repeated history or category membership key")
    observed = history.loc[history.month.eq(cutoff), ["app_id", "avg_players"]]
    joined = members.merge(observed, on="app_id", how="left", validate="many_to_one")
    rows = []
    for category, group in joined.groupby("category"):
        cohort = group.loc[group.in_cohort.eq(1)]
        if cohort.avg_players.isna().any():
            raise ValueError("Cohort member missing at cutoff")
        observed_total = group.avg_players.sum(min_count=1)
        cohort_total = cohort.avg_players.sum()
        rows.append({
            "category": category, "eligible_archive_games": len(group),
            "cutoff_observed_games": int(group.avg_players.notna().sum()),
            "cutoff_missing_games": int(group.avg_players.isna().sum()),
            "cohort_games": len(cohort), "cohort_game_share_pct": 100 * len(cohort) / len(group),
            "observed_archive_activity": observed_total, "cohort_activity": cohort_total,
            "cohort_observed_activity_share_pct": 100 * cohort_total / observed_total if observed_total > 0 else np.nan,
        })
    return pd.DataFrame(rows)


def select_leaders(panel, cutoff=CUTOFF):
    """Select once on original cutoff activity; ties use ascending AppID."""
    leaders = panel.loc[panel.month.eq(cutoff)].sort_values(
        ["category", "avg_players", "app_id"], ascending=[True, False, True]
    ).copy()
    if leaders.duplicated(["category", "app_id"]).any():
        raise ValueError("Repeated cutoff membership")
    leaders["category_position"] = leaders.groupby("category").cumcount() + 1
    return leaders.loc[leaders.category_position.le(5),
                       ["category", "app_id", "name", "avg_players", "category_position"]].reset_index(drop=True)


def exclusion_scenarios(panel, leaders, months):
    """Remove each shared union from every category over the complete calendar."""
    dates = pd.Index(months)
    if dates.empty or not dates.is_unique or panel.empty:
        raise ValueError("Nonempty unique calendar and panel required")
    calendar = pd.DatetimeIndex(pd.to_datetime(dates, format="%Y-%m-%d", errors="raise"))
    expected = pd.date_range(calendar.min(), calendar.max(), freq="MS")
    if not calendar.equals(expected) or (calendar.year == 2025).sum() != 12:
        raise ValueError("Ordered complete monthly calendar and all twelve 2025 months required")
    values = panel.avg_players.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Activity must be observed, finite and nonnegative")
    if panel.duplicated(["category", "app_id", "month"]).any():
        raise ValueError("Repeated cohort observation")
    if panel.groupby(["app_id", "month"]).avg_players.nunique().gt(1).any():
        raise ValueError("An app must have the same activity in every category")
    for _, group in panel.groupby(["category", "app_id"]):
        if set(group.month) != set(dates):
            raise ValueError("Every cohort member needs the complete calendar")
    categories = sorted(panel.category.unique())
    grid = pd.MultiIndex.from_product([categories, dates], names=["category", "month"])
    exclusions = [set(), set(leaders.loc[leaders.category_position.eq(1), "app_id"]), set(leaders.app_id)]
    if not exclusions[1] <= exclusions[2] or not exclusions[2] <= set(panel.app_id):
        raise ValueError("Leader inventories must be nested cohort subsets")
    monthly = []
    for scenario, removed in zip(SCENARIOS, exclusions):
        retained = panel.loc[~panel.app_id.isin(removed)]
        totals = retained.groupby(["category", "month"]).agg(
            avg_players=("avg_players", "sum"), retained_games=("app_id", "nunique")
        ).reindex(grid)
        # Missing aggregate rows can only mean an intentionally exhausted category:
        # complete per-game calendars were required above. No input values are filled.
        totals = totals.fillna({"avg_players": 0., "retained_games": 0}).reset_index()
        totals["retained_games"] = totals.retained_games.astype(int)
        totals["empty_category"] = totals.retained_games.eq(0)
        totals["scenario"] = scenario
        totals["excluded_union_games"] = len(removed)
        monthly.append(totals)
    monthly = pd.concat(monthly, ignore_index=True)
    rows = []
    for (scenario, category), group in monthly.groupby(["scenario", "category"], sort=False):
        first = group.loc[group.month.eq(dates[0]), "avg_players"].iloc[0]
        last = group.loc[group.month.eq(dates[-1]), "avg_players"].iloc[0]
        rows.append({
            "scenario": scenario, "category": category,
            "excluded_union_games": int(group.excluded_union_games.iloc[0]),
            "retained_games": int(group.retained_games.iloc[0]),
            "start_activity": first, "cutoff_activity": last,
            "observed_2025_mean": group.loc[group.month.str.startswith("2025-"), "avg_players"].mean(),
            "start_to_cutoff_change_pct": 100 * (last / first - 1) if first > 0 else np.nan,
        })
    summary = pd.DataFrame(rows)
    base = summary.loc[summary.scenario.eq(SCENARIOS[0]), ["category", "cutoff_activity"]].rename(
        columns={"cutoff_activity": "full_cutoff_activity"})
    summary = summary.merge(base, on="category", validate="many_to_one")
    summary["cutoff_activity_retained_pct"] = 100 * summary.cutoff_activity / summary.full_cutoff_activity.replace(0, np.nan)
    for value, rank in [("cutoff_activity", "cutoff_rank"), ("observed_2025_mean", "observed_2025_rank")]:
        summary[rank] = summary[value].where(summary.retained_games.gt(0)).groupby(summary.scenario).rank(
            method="min", ascending=False).astype("Int64")
    return monthly, summary


def run(root=ROOT):
    root = Path(root)
    digest = lambda p: hashlib.file_digest(p.open("rb"), "sha256").hexdigest()
    inputs = {"scope": root / "config/project_scope.json"}
    scope = json.loads(inputs["scope"].read_text())
    if scope["active_dataset"] != "fixed_sources_v2" or scope["training_cutoff"] != CUTOFF:
        raise ValueError("Expected the frozen v2 scope")
    inputs.update(database=root / scope["database"], category_input=root / scope["category_input"],
                  registry=root / scope["source_registry"])
    pins = {name: digest(path) for name, path in inputs.items()}
    evaluation = json.loads((root / "reports/fixed_cohort_evaluation/manifest.json").read_text())
    diagnostics = json.loads((root / "reports/fixed_cohort_diagnostics/manifest.json").read_text())
    if any(evaluation[key] != pins[name] for key, name in [
        ("input_sha256", "category_input"), ("registry_sha256", "registry"), ("scope_sha256", "scope")
    ]) or diagnostics["database_sha256"] != pins["database"]:
        raise ValueError("Frozen input lineage mismatch")
    with closing(sqlite3.connect(inputs["database"].resolve().as_uri() + "?mode=ro", uri=True)) as con:
        history = pd.read_sql_query(
            "SELECT app_id,month,avg_players FROM monthly_players WHERE month BETWEEN ? AND ?",
            con, params=[START, CUTOFF])
        members = pd.read_sql_query(
            "SELECT g.app_id,g.name,gg.genre category,c.in_cohort FROM games g "
            "JOIN game_genres gg USING(app_id) JOIN cohort_membership c USING(app_id) "
            "WHERE g.eligible=1 AND gg.genre IN (?,?,?,?,?)", con, params=CATEGORIES)
    selected = members.loc[members.in_cohort.eq(1)]
    if selected.app_id.nunique() != 519 or set(selected.category) != set(CATEGORIES):
        raise ValueError("Frozen cohort inventory changed")
    panel = history.merge(selected, on="app_id", validate="many_to_many")
    months = pd.date_range(START, CUTOFF, freq="MS").strftime("%Y-%m-%d").tolist()
    leaders = select_leaders(panel)
    monthly, summary = exclusion_scenarios(panel, leaders, months)
    baseline = monthly.loc[monthly.scenario.eq(SCENARIOS[0]), ["category", "month", "avg_players", "retained_games"]]
    frozen = pd.read_csv(inputs["category_input"]).rename(columns={"observed_apps": "retained_games"})
    pd.testing.assert_frame_equal(baseline.sort_values(["category", "month"]).reset_index(drop=True),
                                  frozen[baseline.columns].sort_values(["category", "month"]).reset_index(drop=True),
                                  check_dtype=False, rtol=1e-12, atol=1e-6)
    coverage = archive_coverage(history, members)
    if any(digest(path) != pins[name] for name, path in inputs.items()):
        raise ValueError("Inputs changed during analysis")
    out = root / "reports/fixed_cohort_sensitivity"
    out.mkdir(parents=True, exist_ok=True)
    outputs = {"archive_coverage": coverage, "excluded_leaders": leaders,
               "scenario_monthly": monthly, "scenario_summary": summary}
    for name, frame in outputs.items():
        frame.to_csv(out / (name + ".csv"), index=False, float_format="%.12g")
    manifest = {
        "analysis": "Descriptive cohort coverage and shared-leader exclusions; no 2027 forecasts or model fitting",
        "history": [START, CUTOFF], "cohort_games": 519, "inputs_sha256": pins,
        "input_paths": {name: path.relative_to(root).as_posix() for name, path in inputs.items()},
        "libraries": {"pandas": pd.__version__, "numpy": np.__version__},
        "script_sha256": digest(Path(__file__)),
        "outputs_sha256": {name + ".csv": digest(out / (name + ".csv")) for name in outputs},
        "coverage_denominator": "Eligible selected-label games in this archive only; activity share conditional on records observed at cutoff",
        "exclusions": "Union of original January 2026 cohort top one/top five games per category, removed from every category for every month; ties use AppID ascending",
        "rank_rule": "Descending activity, minimum rank for ties; exhausted categories unranked",
        "missingness": "No unavailable input activity filled; empty scenario groups explicitly zero by construction; zero-denominator percentages unavailable",
        "limitations": ["Retrospectively selected leaders and cohort", "Archive is not the Steam market",
                        "Endpoint-selected exclusions mechanically affect growth", "No causal or predictive-accuracy claim",
                        "Overlapping labels; category values cannot be added as distinct audiences"],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return coverage, summary


if __name__ == "__main__":
    coverage, summary = run()
    print(coverage.round(2).to_string(index=False))
    print(summary.round(2).to_string(index=False))

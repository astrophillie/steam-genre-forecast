"""Review fixed-cohort residuals, cutoff sensitivity and observed game contributions."""
from pathlib import Path
import hashlib
import json
import sqlite3
import numpy as np
import pandas as pd
try:
    from .audit_validation import validate_predictions, require_same_targets
    from .evaluate_fixed_cohort import summarise, MODELS, ORIGINS
except ImportError:
    from audit_validation import validate_predictions, require_same_targets
    from evaluate_fixed_cohort import summarise, MODELS, ORIGINS

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ["Action", "Indie", "Massively Multiplayer", "RPG", "Strategy"]


def cutoff_sensitivity(predictions):
    """Compare predictions on identical calendar months from consecutive origins."""
    data = validate_predictions(predictions)
    origins = sorted(data.origin.unique())
    if len(origins) != 2:
        raise ValueError("Two origins required for the paired cutoff diagnostic")
    keys = ["category", "model", "month"]
    first = data.loc[data.origin.eq(origins[0]) & data.lead.between(12,23)]
    second = data.loc[data.origin.eq(origins[1]) & data.lead.between(12,23)]
    paired = first.merge(second, on=keys, suffixes=("_first", "_second"), validate="one_to_one")
    if paired.empty or not np.allclose(paired.actual_first, paired.actual_second, rtol=1e-12, atol=1e-7):
        raise ValueError("Paired actuals must agree")
    paired["absolute_forecast_shift"] = (paired.prediction_second-paired.prediction_first).abs()
    paired["first_absolute_error"] = paired.error_first.abs()
    paired["second_absolute_error"] = paired.error_second.abs()
    return paired.groupby(["category", "model"], as_index=False).agg(
        shared_months=("month", "nunique"), average_forecast_shift=("absolute_forecast_shift", "mean"),
        max_forecast_shift=("absolute_forecast_shift", "max"),
        first_cutoff_mae=("first_absolute_error", "mean"), second_cutoff_mae=("second_absolute_error", "mean"))


def app_contributions(panel, category, origin, month):
    """Exact observed changes; no invented app-level allocation of an ETS forecast."""
    origin, month = pd.Timestamp(origin), pd.Timestamp(month)
    previous_year = month-pd.DateOffset(years=1)
    selected = panel.loc[panel.category.eq(category)].copy()
    if selected.duplicated(["app_id", "month"]).any():
        raise ValueError("Duplicate app/month membership")
    dates = [origin, month, previous_year]
    pivot = selected.loc[selected.month.isin(dates)].pivot(index="app_id", columns="month", values="avg_players")
    ids = set(selected.app_id.unique())
    if set(pivot.index) != ids or not set(dates) <= set(pivot.columns) or pivot.isna().any().any():
        raise ValueError("Every member needs all comparison months")
    values = pivot.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values<0).any():
        raise ValueError("Invalid app activity")
    result = pd.DataFrame({"app_id":pivot.index, "origin_activity":pivot[origin].to_numpy(),
                           "target_activity":pivot[month].to_numpy(), "prior_year_activity":pivot[previous_year].to_numpy()})
    result = result.merge(selected[["app_id", "name"]].drop_duplicates(), on="app_id", validate="one_to_one")
    result["change_since_origin"] = result.target_activity-result.origin_activity
    result["year_over_year_change"] = result.target_activity-result.prior_year_activity
    total = result.target_activity.sum()
    result["target_share_pct"] = 100*result.target_activity/total if total else np.nan
    result["category"], result["origin"], result["month"] = category, origin, month
    return result


def run(root=ROOT):
    root = Path(root)
    scope = json.loads((root/"config/project_scope.json").read_text(encoding="utf-8"))
    folder = root/"reports/fixed_cohort_evaluation"
    manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    for key, path in [("input_sha256",root/scope["category_input"]),("registry_sha256",root/scope["source_registry"]),("scope_sha256",root/"config/project_scope.json")]:
        if manifest[key] != digest(path):
            raise ValueError("Stale comparison inputs")
    if manifest.get("predictions_sha256") != digest(folder/"predictions.csv"):
        raise ValueError("Model predictions changed since evaluation")
    predictions = validate_predictions(pd.read_csv(folder/"predictions.csv"))
    require_same_targets(predictions, predictions)
    if set(predictions.model) != set(MODELS) or set(predictions.category) != set(CATEGORIES) or set(predictions.origin) != set(ORIGINS) or predictions.lead.max()!=23:
        raise ValueError("Unexpected comparison inventory")
    connection = sqlite3.connect((root/scope["database"]).resolve().as_uri()+"?mode=ro", uri=True)
    try:
        panel = pd.read_sql_query("""SELECT g.genre AS category, m.app_id, c.name, m.month, m.avg_players
            FROM monthly_players m JOIN cohort_membership c ON c.app_id=m.app_id AND c.in_cohort=1
            JOIN game_genres g ON g.app_id=m.app_id
            WHERE m.month BETWEEN '2021-02-01' AND '2026-01-01'
            AND g.genre IN ('Action','Indie','Massively Multiplayer','RPG','Strategy')""", connection)
        monthly = pd.read_sql_query("SELECT category, month, avg_players FROM category_monthly", connection)
    finally:
        connection.close()
    for frame in [panel,monthly]: frame["month"] = pd.to_datetime(frame.month)
    computed = panel.groupby(["category","month"],as_index=False).avg_players.sum()
    pd.testing.assert_frame_equal(computed.sort_values(["category","month"]).reset_index(drop=True), monthly.sort_values(["category","month"]).reset_index(drop=True), check_dtype=False, rtol=1e-12, atol=1e-7)
    actuals = predictions.merge(monthly.rename(columns={"avg_players":"database_actual"}),on=["category","month"],how="left",validate="many_to_one")
    if actuals.database_actual.isna().any() or not np.allclose(actuals.actual,actuals.database_actual,rtol=1e-12,atol=1e-7):
        raise ValueError("Prediction actuals disagree with frozen database")
    folds, scores = summarise(predictions)
    target_scores = scores.loc[scores.window.eq("Leads 12 to 23")]
    leaders = target_scores.sort_values(["mae","model"]).groupby("category").head(1)
    targets = predictions.loc[predictions.lead.between(12,23)].merge(leaders[["category","model"]],on=["category","model"],validate="many_to_one")
    cases = targets.assign(absolute_error=lambda x:x.error.abs()).sort_values("absolute_error",ascending=False).groupby("category").head(3).reset_index(drop=True)
    cases["case_id"] = np.arange(1,len(cases)+1)
    parts=[]
    for case in cases.itertuples():
        part=app_contributions(panel,case.category,case.origin,case.month)
        baseline=predictions.loc[predictions.category.eq(case.category)&predictions.origin.eq(case.origin)&predictions.month.eq(case.month)&predictions.model.eq("Last value")].iloc[0]
        if not np.isclose(part.change_since_origin.sum(),baseline.error,rtol=1e-12,atol=1e-6):
            raise ValueError("Game-level changes fail baseline residual reconciliation")
        # Seasonal naive repeats the final training cycle even beyond twelve leads.
        reference_month=case.origin-pd.DateOffset(months=11)+pd.DateOffset(months=(int(case.lead)-1)%12)
        reference=panel.loc[panel.category.eq(case.category)&panel.month.eq(reference_month),["app_id","avg_players"]].rename(columns={"avg_players":"seasonal_reference_activity"})
        part=part.merge(reference,on="app_id",how="left",validate="one_to_one")
        if part.seasonal_reference_activity.isna().any():raise ValueError("Missing seasonal reference observations")
        part["seasonal_reference_month"]=reference_month
        part["seasonal_residual_contribution"]=part.target_activity-part.seasonal_reference_activity
        seasonal=predictions.loc[predictions.category.eq(case.category)&predictions.origin.eq(case.origin)&predictions.month.eq(case.month)&predictions.model.eq("Seasonal naive")].iloc[0]
        if not np.isclose(part.seasonal_residual_contribution.sum(),seasonal.error,rtol=1e-12,atol=1e-6):raise ValueError("Seasonal residual reconciliation failed")
        part["case_id"]=case.case_id
        parts.append(part)
    contributions=pd.concat(parts,ignore_index=True)
    top_changes=contributions.assign(absolute_change=lambda x:x.change_since_origin.abs()).sort_values("absolute_change",ascending=False).groupby("case_id").head(3)
    top_seasonal_changes=contributions.assign(absolute_change=lambda x:x.seasonal_residual_contribution.abs()).sort_values("absolute_change",ascending=False).groupby("case_id").head(3)
    concentration=[]
    for (category,month), frame in panel.groupby(["category","month"]):
        total=frame.avg_players.sum()
        ordered=frame.sort_values("avg_players",ascending=False)
        concentration.append({"category":category,"month":month,"total_activity":total,"top_game":ordered.iloc[0]["name"],"top1_share_pct":100*ordered.avg_players.iloc[0]/total if total else np.nan,"top5_share_pct":100*ordered.avg_players.head(5).sum()/total if total else np.nan})
    concentration=pd.DataFrame(concentration)
    sensitivity=cutoff_sensitivity(predictions)
    stability=folds.loc[folds.window.eq("Leads 12 to 23")].copy()
    stability["fold_rank"]=stability.groupby(["category","origin"]).mae.rank(method="min")
    stability=stability.merge(leaders[["category","model"]],on=["category","model"],validate="many_to_one")
    bias=targets.groupby(["category","model"],as_index=False).agg(underpredicted_cases=("error",lambda x:int(x.gt(0).sum())),overpredicted_cases=("error",lambda x:int(x.lt(0).sum())),mean_error=("error","mean"))
    out=root/"reports/fixed_cohort_diagnostics";out.mkdir(exist_ok=True)
    outputs={"leading_models":leaders,"leader_fold_stability":stability,"cutoff_sensitivity":sensitivity,"largest_leader_errors":cases,"case_app_contributions":contributions,"top_case_changes":top_changes,"top_seasonal_changes":top_seasonal_changes,"category_concentration":concentration,"leader_bias":bias}
    frozen_forecast=root/"reports/fixed_cohort_forecast_2027/manifest.json"
    if frozen_forecast.exists():
        pins=json.loads(frozen_forecast.read_text(encoding="utf-8")).get("diagnostic_outputs", {})
        if set(pins)!={name+".csv" for name in outputs}:
            raise ValueError("Frozen diagnostic evidence inventory missing or changed")
        for name,frame in outputs.items():
            if hashlib.sha256(frame.to_csv(index=False).encode("utf-8")).hexdigest()!=pins.get(name+".csv"):
                raise ValueError("Diagnostic evidence changed; preserve the frozen forecast version")
    for name,frame in outputs.items():frame.to_csv(out/f"{name}.csv",index=False)
    record={"predictions_sha256":digest(folder/"predictions.csv"),"evaluation_manifest_sha256":digest(folder/"manifest.json"),"database_sha256":digest(root/scope["database"]),"cases":len(cases),"case_policy":"Three largest lead12–23 errors per category; repeated calendar months at different origins remain separate forecast cases", "interpretation":"App changes exactly decompose last-value and seasonal-naive residuals using their respective historical references. ETS residuals have no app-level forecast allocation. Observed changes and concentration are descriptive, not causal. Two overlapping retrospective folds, no independent validation or final model choice."}
    (out/"manifest.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
    return outputs


if __name__=="__main__":
    result=run()
    print(result["leader_fold_stability"][["category","model","origin","mae","fold_rank","skill_vs_last_value_pct"]].to_string(index=False))
    print(result["category_concentration"].groupby("category").tail(1).to_string(index=False))

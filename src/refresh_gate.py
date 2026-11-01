"""Validate refresh evidence without silently promoting a partial cohort."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,re
from urllib.parse import urlparse
import numpy as np
import pandas as pd
try:
    from .prepare_data import integer_ids
    from .project_2027 import run as verify_frozen
except ImportError:
    from prepare_data import integer_ids
    from project_2027 import run as verify_frozen
ROOT=Path(__file__).resolve().parents[1]

def validate_import(frame,as_of):
    required={"app_id","month","avg_players","source_url"}
    if frame.empty or not required<=set(frame):raise ValueError("Refresh requires rows and app/month/activity/source fields")
    result=frame.copy()
    if result.app_id.map(lambda x:isinstance(x,(bool,np.bool_))).any():raise ValueError("Boolean app ID")
    result["app_id"]=integer_ids(result.app_id)
    if not result.month.map(lambda x:isinstance(x,str) and bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-01",x))).all():raise ValueError("Expected YYYY-MM-01 calendar months")
    dates=pd.to_datetime(result.month,format="%Y-%m-%d",errors="raise")
    complete=(pd.Timestamp(as_of).to_period("M")-1).to_timestamp()
    if dates.gt(complete).any():raise ValueError("Partial or future calendar month")
    if result.avg_players.map(lambda x:isinstance(x,(bool,np.bool_))).any():raise ValueError("Boolean activity")
    result["avg_players"]=pd.to_numeric(result.avg_players,errors="raise").astype(float)
    if not np.isfinite(result.avg_players).all() or result.avg_players.lt(0).any():raise ValueError("Invalid refresh activity")
    if result.duplicated(["app_id","month"]).any():raise ValueError("Repeated refresh key")
    if not result.source_url.map(lambda x:isinstance(x,str) and urlparse(x).scheme in {"http","https"} and bool(urlparse(x).netloc)).all():raise ValueError("Missing source provenance")
    return result

def assess_refresh(frame,baseline,games,labels,target_month):
    if games.app_id.duplicated().any() or baseline.duplicated(["app_id","month"]).any() or labels.duplicated(["app_id","category"]).any():raise ValueError("Duplicate baseline keys")
    eligible=games.loc[games.eligible.eq(1),["app_id"]]
    accepted=frame.merge(eligible,on="app_id",how="inner",validate="many_to_one")
    overlap=accepted.merge(baseline,on=["app_id","month"],suffixes=("_refresh","_baseline"),validate="one_to_one")
    overlap["mismatch"]=(overlap.avg_players_refresh-overlap.avg_players_baseline).abs().gt(.011)
    seen=set(accepted.loc[accepted.month.eq(target_month),"app_id"])
    old_cutoff=baseline.month.max()
    weights=baseline.loc[baseline.month.eq(old_cutoff),["app_id","avg_players"]].rename(columns={"avg_players":"baseline_activity"})
    members=labels.merge(eligible,on="app_id",validate="many_to_one").merge(weights,on="app_id",how="left",validate="many_to_one")
    members["observed_at_target"]=members.app_id.isin(seen)
    rows=[]
    for category,group in members.groupby("category"):
        total=group.baseline_activity.sum(min_count=1)
        captured=group.loc[group.observed_at_target,"baseline_activity"].sum(min_count=1)
        rows.append({"category":category,"cohort_apps":len(group),"observed_apps_at_target":int(group.observed_at_target.sum()),"app_coverage_pct":100*group.observed_at_target.mean(),"baseline_activity_coverage_pct":100*captured/total if total>0 and pd.notna(captured) else np.nan})
    missing=eligible.loc[~eligible.app_id.isin(seen)].copy()
    refresh_months=pd.date_range(pd.Timestamp(old_cutoff)+pd.offsets.MonthBegin(),pd.Timestamp(target_month),freq="MS").strftime("%Y-%m-%d")
    if len(refresh_months)==0:raise ValueError("Target must extend the baseline cutoff")
    expected=pd.MultiIndex.from_product([eligible.app_id,refresh_months],names=["app_id","month"])
    observed=pd.MultiIndex.from_frame(accepted.loc[accepted.month.isin(refresh_months),["app_id","month"]])
    missing_months=len(expected.difference(observed))
    no_overlap=len(set(eligible.app_id)-set(overlap.app_id))
    summary={"target_month":target_month,"eligible_apps":len(eligible),"eligible_import_apps":accepted.app_id.nunique(),"observed_eligible_apps_at_target":len(seen),"missing_eligible_apps_at_target":len(missing),"overlap_rows":len(overlap),"overlap_mismatches":int(overlap.mismatch.sum()),"outside_cohort_rows":len(frame)-len(accepted),"missing_refresh_app_months":missing_months,"apps_without_overlap_evidence":no_overlap,"promotion_ready":bool(missing_months==0 and no_overlap==0 and not overlap.mismatch.any()),"gate":"Strict full-cohort monthly refresh completeness and per-app compatible overlap; separate access/eligibility review still required"}
    return summary,pd.DataFrame(rows),overlap,missing

def run():
    verify_frozen()
    source=ROOT/"reports/steamcharts_pilot/20261025T085419Z_52879d/monthly_players.csv"
    frame=validate_import(pd.read_csv(source),"2026-10-26")
    with closing(sqlite3.connect((ROOT/"database/steam.sqlite").as_uri()+"?mode=ro",uri=True)) as con:
        baseline=pd.read_sql_query("SELECT app_id,month,avg_players FROM monthly_players",con)
        games=pd.read_sql_query("SELECT app_id,eligible FROM games",con)
        labels=pd.read_sql_query("SELECT gg.app_id,gg.genre AS category FROM game_genres gg JOIN analysis_categories ac ON ac.genre=gg.genre",con)
    summary,coverage,overlap,missing=assess_refresh(frame,baseline,games,labels,"2026-09-01")
    folder=ROOT/"reports/refresh_gate";folder.mkdir(exist_ok=True)
    for name,table in [("category_coverage",coverage),("overlap",overlap),("missing_target_apps",missing)]:table.to_csv(folder/f"{name}.csv",index=False)
    manifest={**summary,"as_of":"2026-10-26","source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"baseline_sha256":hashlib.sha256((ROOT/"database/steam.sqlite").read_bytes()).hexdigest(),"scope":"Existing pilot used to exercise import gate; no new collection or target promotion"}
    (folder/"assessment.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    protocol={"registered_on":"2026-10-26","version":"v1","forecast_checksums":json.loads((ROOT/"reports/forecast_2027/checksums.json").read_text()),"database_sha256":manifest["baseline_sha256"],"cohort":"Existing6094 eligible apps with pinned snapshot category labels","target_months":[str(x.date()) for x in pd.date_range("2027-01-01","2027-12-01",freq="MS")],"primary_metric":"Per-category monthly MAE","secondary_metrics":["RMSE","signed bias","annual mean error and category rank error after all12 months"],"rules":["Freeze forecasts and cohort before2027 outcomes","Do not retune using evaluation outcomes","Require explicit missing-observation handling; never zero-fill unavailable activity","Do not score incomplete category totals as full-cohort actuals","Newly obtained pre-registration history remains retrospective validation, not an untouched test","A changed cohort,source,cutoff or policy requires a separate forecast version"],"availability":"Future observations not yet collected; this local registration is not an externally timestamped preregistration"}
    path=folder/"evaluation_protocol_v1.json"
    if path.exists():
        if json.loads(path.read_text())!=protocol:raise ValueError("Protocol frozen; create a new version")
    else:path.write_text(json.dumps(protocol,indent=2)+"\n",encoding="utf-8")
    return summary,coverage

if __name__=="__main__":
    summary,coverage=run();print(json.dumps(summary,indent=2));print(coverage.round(2).to_string(index=False))

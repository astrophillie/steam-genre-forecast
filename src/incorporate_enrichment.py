"""Validate supplemental history and create forecast-ready calendar features."""
from pathlib import Path
import hashlib
import json
import sqlite3
from contextlib import closing
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
SNAPSHOT_SHA="ccb6257ae46617a9dd077b8fb5db1afabacb4b522359a06a10e85229ec4f3c6e"
URL="https://github.com/Aakash-1107/Game-Market-Intelligence/releases/download/data-2026-10-07/game_market_snapshot.duckdb"

def calendar_features(start="2012-07-01", end="2027-12-01"):
    months=pd.date_range(start,end,freq="MS")
    return pd.DataFrame({"month":months.strftime("%Y-%m-%d"),"calendar_month":months.month,
        "days_in_month":months.days_in_month,
        "month_sin":np.sin(2*np.pi*(months.month-1)/12),
        "month_cos":np.cos(2*np.pi*(months.month-1)/12)})

def validate_history(frame):
    if frame.empty or frame.duplicated(["app_id","month"]).any():
        raise ValueError("Empty or duplicate supplemental history")
    dates=pd.to_datetime(frame.month,format="%Y-%m-%d",errors="raise")
    if not dates.dt.is_month_start.all():
        raise ValueError("Expected calendar-month starts")
    if not np.isfinite(frame[["avg_players","peak_players"]].to_numpy()).all():
        raise ValueError("Nonfinite activity")
    if (frame.avg_players.lt(0)|frame.peak_players.lt(frame.avg_players)).any():
        raise ValueError("Invalid average or peak")

def run():
    import duckdb  # Optional snapshot-reader dependency; not used by modelling.
    path=ROOT/"data/raw/external_snapshot_20261007/game_market_snapshot.duckdb"
    if hashlib.sha256(path.read_bytes()).hexdigest()!=SNAPSHOT_SHA:
        raise ValueError("Supplemental snapshot checksum mismatch")
    with duckdb.connect(str(path),read_only=True,config={"enable_external_access":"false","autoload_known_extensions":"false","autoinstall_known_extensions":"false"}) as con:
        fresh=con.execute("SELECT steam_app_id AS app_id, CAST(activity_month AS VARCHAR) AS month, avg_players,peak_players,source FROM marts.fact_player_activity_monthly").fetchdf()
        metadata=con.execute("SELECT steam_app_id AS app_id,name,app_type,steam_genres FROM marts.dim_game").fetchdf()
    validate_history(fresh)
    if not fresh.source.eq("steamcharts").all():
        raise ValueError("Unexpected measurement source")
    with closing(sqlite3.connect((ROOT/"database/steam.sqlite").as_uri()+"?mode=ro",uri=True)) as con:
        old=pd.read_sql_query("SELECT app_id,month,avg_players FROM monthly_players",con)
        games=pd.read_sql_query("SELECT app_id,eligible FROM games",con)
    overlap=old.merge(fresh,on=["app_id","month"],suffixes=("_baseline","_supplemental"),validate="one_to_one")
    overlap["absolute_difference"]=(overlap.avg_players_baseline-overlap.avg_players_supplemental).abs()
    overlap["within_tolerance"]=overlap.absolute_difference.le(.011)
    per_app=fresh.groupby("app_id").agg(first_month=("month","min"),last_month=("month","max"),rows=("month","size")).reset_index().merge(metadata,on="app_id",validate="one_to_one").merge(games,on="app_id",how="left",validate="one_to_one")
    cutoff=old.month.max()
    # Only completed months at the release's collection cutoff; October is partial.
    completed=fresh.loc[fresh.month.le("2026-09-01")].copy()
    completed["snapshot_sha256"]=SNAPSHOT_SHA
    folder=ROOT/"reports/enrichment";folder.mkdir(exist_ok=True)
    overlap.to_csv(folder/"supplemental_overlap.csv",index=False)
    per_app.to_csv(folder/"supplemental_app_audit.csv",index=False)
    processed=ROOT/"data/processed"
    completed.to_parquet(processed/"supplemental_monthly_validated.parquet",index=False)
    calendar=calendar_features()
    calendar.to_csv(folder/"calendar_features.csv",index=False)
    # Join only deterministic, future-known fields; preserve target measurements.
    monthly=pd.read_csv(ROOT/"reports/exploration_monthly.csv")
    features=monthly.merge(calendar,on="month",how="left",validate="many_to_one")
    assert len(features)==len(monthly) and features.calendar_month.notna().all()
    features.to_parquet(processed/"category_monthly_with_calendar.parquet",index=False)
    summary={"snapshot_url":URL,"snapshot_sha256":SNAPSHOT_SHA,"snapshot_release":"2026-10-07",
        "baseline_cutoff":cutoff,"supplemental_apps":int(fresh.app_id.nunique()),"raw_monthly_rows":len(fresh),
        "completed_rows":len(completed),"first_month":fresh.month.min(),"last_raw_month":fresh.month.max(),
        "last_completed_month":completed.month.max(),"excluded_partial_rows":len(fresh)-len(completed),
        "overlap_rows":len(overlap),"overlap_mismatches":int((~overlap.within_tolerance).sum()),
        "new_completed_rows":int(completed.month.gt(cutoff).sum()),
        "new_catalog_apps":int((~per_app.app_id.isin(games.app_id)).sum()),
        "baseline_database_sha256":hashlib.sha256((ROOT/"database/steam.sqlite").read_bytes()).hexdigest(),
        "baseline_monthly_sha256":hashlib.sha256((ROOT/"reports/exploration_monthly.csv").read_bytes()).hexdigest(),
        "scope":"Supplemental evidence only; not merged into category targets. Upstream reuse terms unresolved.",
        "calendar_scope":"Deterministic future-known month, days, sine and cosine; no speculative event or review values"}
    (folder/"manifest.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    return summary,per_app,features

if __name__=="__main__":
    summary,_,_=run()
    print(json.dumps(summary,indent=2))

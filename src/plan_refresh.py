"""Prepare a deterministic refresh queue and measure pilot coverage offline."""
from pathlib import Path
from contextlib import closing
import sqlite3
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]

def make_queue(catalog, batch_size=100):
    if batch_size < 1:
        raise ValueError("Batch size must be positive")
    if catalog.app_id.duplicated().any():
        raise ValueError("Duplicate app IDs")
    queue=catalog.loc[catalog.refresh_scope.eq("Existing eligible cohort")].copy()
    queue=queue.sort_values(["baseline_latest_activity","app_id"],ascending=[False,True],na_position="last").reset_index(drop=True)
    queue["priority"]=queue.index+1
    queue["batch_id"]=queue.index//batch_size+1
    queue["collection_state"]="pending_access_method"
    return queue

def run():
    from refresh_readiness import run as rebuild_catalog
    catalog, _ = rebuild_catalog()
    queue=make_queue(catalog)
    with closing(sqlite3.connect((ROOT/"database/steam.sqlite").as_uri()+"?mode=ro",uri=True)) as connection:
        labels=pd.read_sql_query("SELECT gg.app_id, gg.genre AS category FROM game_genres gg JOIN analysis_categories ac ON ac.genre=gg.genre",connection)
    members=labels.merge(queue,on="app_id",how="inner",validate="many_to_one")
    members["pilot_ok"]=members.status.eq("ok")
    members["pilot_activity"]=members.baseline_latest_activity.where(members.pilot_ok)
    summary=members.groupby("category").agg(eligible_apps=("app_id","size"),pilot_success_apps=("pilot_ok","sum"),baseline_activity=("baseline_latest_activity",lambda s:s.sum(min_count=1)),pilot_matched_baseline_activity=("pilot_activity",lambda s:s.sum(min_count=1))).reset_index()
    summary["pilot_app_coverage_pct"]=100*summary.pilot_success_apps/summary.eligible_apps
    summary["pilot_activity_coverage_pct"]=100*summary.pilot_matched_baseline_activity/summary.baseline_activity
    folder=ROOT/"reports/refresh_readiness"
    queue.to_csv(folder/"collection_queue.csv",index=False)
    summary.to_csv(folder/"pilot_category_coverage.csv",index=False)
    return queue,summary

if __name__=="__main__":
    queue,summary=run()
    print(f"{len(queue)} candidates across {queue.batch_id.nunique()} planning batches")
    print(summary.to_string(index=False))

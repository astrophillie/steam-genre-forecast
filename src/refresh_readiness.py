"""Audit refresh scope offline; keep candidate plans separate from model inputs."""
from pathlib import Path
from contextlib import closing
import sqlite3
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
RUN="20261025T085419Z_52879d"

def build_catalog(games, players, audit):
    if games.app_id.duplicated().any() or audit.app_id.duplicated().any():
        raise ValueError("Duplicate app identifiers")
    if players.duplicated(["app_id","month"]).any():
        raise ValueError("Duplicate app/month observations")
    coverage=players.groupby("app_id").agg(first_month=("month","min"),last_month=("month","max"),observed_months=("month","size"))
    catalog=games.merge(coverage,on="app_id",how="left",validate="one_to_one")
    latest=players.month.max()
    activity=players.loc[players.month.eq(latest),["app_id","avg_players"]].rename(columns={"avg_players":"baseline_latest_activity"})
    catalog=catalog.merge(activity,on="app_id",how="left",validate="one_to_one")
    probes=audit.loc[~audit.app_id.isin(catalog.app_id),["app_id","name"]].copy()
    probes["eligible"]=pd.NA
    catalog=pd.concat([catalog,probes],ignore_index=True)
    catalog["refresh_scope"]="Eligibility review"
    catalog.loc[catalog.eligible.eq(1).fillna(False),"refresh_scope"]="Existing eligible cohort"
    catalog.loc[catalog.eligible.eq(0).fillna(False),"refresh_scope"]="Held out under existing rule"
    catalog.loc[~catalog.app_id.isin(games.app_id),"refresh_scope"]="Catalog expansion probe"
    fields=audit[["app_id","status","last_month","has_latest_complete_month","overlap_months","overlap_mismatches"]].rename(columns={"last_month":"pilot_last_month"})
    catalog=catalog.merge(fields,on="app_id",how="left",validate="one_to_one")
    catalog["pilot_checked"]=catalog.status.notna()
    catalog["status"]=catalog.status.fillna("not_requested")
    return catalog.sort_values("app_id").reset_index(drop=True)

def run():
    with closing(sqlite3.connect((ROOT/"database/steam.sqlite").as_uri()+"?mode=ro",uri=True)) as connection:
        games=pd.read_sql_query("SELECT * FROM games",connection)
        players=pd.read_sql_query("SELECT app_id,month,avg_players FROM monthly_players",connection)
    audit=pd.read_csv(ROOT/f"reports/steamcharts_pilot/{RUN}/app_audit.csv")
    catalog=build_catalog(games,players,audit)
    summary=catalog.groupby("refresh_scope",dropna=False).agg(app_count=("app_id","size"),pilot_checked=("pilot_checked","sum"),baseline_latest_activity=("baseline_latest_activity",lambda s:s.sum(min_count=1))).reset_index()
    folder=ROOT/"reports/refresh_readiness";folder.mkdir(exist_ok=True)
    catalog.to_csv(folder/"catalog.csv",index=False)
    summary.to_csv(folder/"scope_summary.csv",index=False)
    return catalog,summary

if __name__=="__main__":
    _,summary=run()
    print(summary.to_string(index=False))

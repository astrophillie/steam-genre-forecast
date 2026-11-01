"""Integrate the fixed approved sources into an isolated v2 archive and cohort."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,uuid
import numpy as np
import pandas as pd
try:
    from .prepare_data import normalise_labels,review_group,CATEGORIES
    from .refresh_gate import validate_import
    from .project_2027 import run as verify_v1
except ImportError:
    from prepare_data import normalise_labels,review_group,CATEGORIES
    from refresh_gate import validate_import
    from project_2027 import run as verify_v1
ROOT=Path(__file__).resolve().parents[1]
VERSION="fixed_sources_v2"
CUTOFF="2026-01-01"
WINDOW_START="2021-02-01"
AS_OF="2026-10-26"

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def canonicalise(observations):
    if observations.duplicated(["source_id","app_id","month"]).any():raise ValueError("Repeated source/app/month observation")
    spread=observations.groupby(["app_id","month"]).avg_players.agg(["min","max","size"])
    conflicts=spread.loc[(spread["max"]-spread["min"]).gt(.011)]
    if not conflicts.empty:raise ValueError(f"Conflicting source activity for{len(conflicts)}app/month keys")
    return observations.sort_values(["priority","app_id","month"]).drop_duplicates(["app_id","month"]).sort_values(["app_id","month"]).reset_index(drop=True)

def choose_cohort(canonical,games,labels,cutoff=CUTOFF,start=WINDOW_START):
    months=pd.date_range(start,cutoff,freq="MS").strftime("%Y-%m-%d").tolist()
    if not months:raise ValueError("Empty modelling window")
    within=canonical.loc[canonical.month.isin(months)]
    counts=within.groupby("app_id").month.nunique()
    selected_labels=set(labels.loc[labels.genre.isin(CATEGORIES),"app_id"])
    audit=games.copy();audit["observed_window_months"]=audit.app_id.map(counts).fillna(0).astype(int)
    audit["cohort_reason"]="Outside selected labels"
    audit.loc[audit.app_id.isin(selected_labels),"cohort_reason"]="Incomplete common window"
    audit.loc[audit.eligible.eq(0),"cohort_reason"]="Held out under metadata inclusion rule"
    keep=audit.eligible.eq(1)&audit.app_id.isin(selected_labels)&audit.observed_window_months.eq(len(months))
    audit["in_cohort"]=keep.astype(int)
    audit.loc[keep,"cohort_reason"]="Included: complete common60-month window and eligible labels"
    return audit,within.loc[within.app_id.isin(audit.loc[keep,"app_id"])].copy()

def run():
    verify_v1()
    original_hash=digest(ROOT/"database/steam.sqlite")
    with closing(sqlite3.connect((ROOT/"database/steam.sqlite").as_uri()+"?mode=ro",uri=True)) as con:
        baseline=pd.read_sql_query("SELECT app_id,month,avg_players FROM monthly_players",con)
        old_names=pd.read_sql_query("SELECT app_id,name FROM games",con).set_index("app_id").name
    frames=[];sources=[]
    def add(source_id,name,path,frame,url,licence):
        record=validate_import(frame.assign(source_url=url),AS_OF)
        record["source_id"]=source_id;record["priority"]=source_id
        frames.append(record[["app_id","month","avg_players","source_id","priority","source_url"]])
        sources.append({"source_id":source_id,"name":name,"path":str(path.relative_to(ROOT)),"sha256":digest(path),"url":url,"licence_note":licence,"rows":len(record)})
    add(1,"Pinned lunthu baseline",ROOT/"database/steam.sqlite",baseline,"https://www.kaggle.com/datasets/lunthu/steam-monthly-average-players","Dataset reportsCC0; original provenance retained")
    path=ROOT/"data/raw/fixed_sources_v2/aanomali_monthly.csv"
    if digest(path)!="7e9df8ef83acf895fa643acd0a198e18777b213d34b2fbb8385caced79631044":raise ValueError("Aanomali source changed")
    a=pd.read_csv(path).rename(columns={"appid":"app_id","date":"month"})
    add(2,"Aanomali multiplayer",path,a,"https://github.com/aanomali/steam-multiplayer-forecasting/tree/582dca92f49d4cb6ff57392a92750ae6024d3ffb","MIT repository; upstream observation redistribution not independently established")
    path=ROOT/"data/raw/fixed_sources_v2/liu_monthly.csv"
    if digest(path)!="3e91cbdb2f186a86ee79225262db81d24acde13e895b164d3acbb8ad3c3881b6":raise ValueError("Liu source changed")
    b=pd.read_csv(path).rename(columns={"appid":"app_id"})
    add(3,"Liu giveaway research",path,b,"https://github.com/liunicholas/egs-steam-research-paper/tree/c920ccf9be4550b9e849423f9f137fbf62d26d8c","No explicit licence detected; local analysis, raw redistribution deferred")
    path=ROOT/"data/processed/supplemental_monthly_validated.parquet"
    supplemental=pd.read_parquet(path)
    if not supplemental.snapshot_sha256.eq("ccb6257ae46617a9dd077b8fb5db1afabacb4b522359a06a10e85229ec4f3c6e").all():raise ValueError("Supplemental lineage changed")
    add(4,"Previously validated Aakash snapshot",path,supplemental,"https://github.com/Aakash-1107/Game-Market-Intelligence/releases/tag/data-2026-10-07","Upstream reuse unresolved; retain local derived analysis")
    path=ROOT/"reports/steamcharts_pilot/20261025T085419Z_52879d/monthly_players.csv"
    add(5,"Existing SteamCharts pilot",path,pd.read_csv(path),"https://steamcharts.com","Existing bounded cache; no new access or bulk collection")
    observations=pd.concat(frames,ignore_index=True)
    canonical=canonicalise(observations)
    metadata_path=ROOT/"data/raw/fronkon_metadata/games.parquet"
    frozen_registry=ROOT/"reports/fixed_sources_v2/source_registry.json"
    if frozen_registry.exists():
        existing=json.loads(frozen_registry.read_text())
        if existing["sources"]!=sources or existing["metadata"]["sha256"]!=digest(metadata_path) or existing["modelling_cutoff"]!=CUTOFF or existing["window_start"]!=WINDOW_START:
            raise ValueError("Fixed source roster or cohort definition changed; create a new version before writing")
    metadata=pd.read_parquet(metadata_path,columns=["appID","name","genres"]).rename(columns={"appID":"app_id"})
    metadata["app_id"]=pd.to_numeric(metadata.app_id,errors="raise").astype(int)
    if metadata.app_id.duplicated().any():raise ValueError("Duplicate metadata keys")
    games=pd.DataFrame({"app_id":sorted(canonical.app_id.unique())}).merge(metadata,on="app_id",how="left",validate="one_to_one")
    fallback={**old_names.to_dict(),**dict(zip(a.app_id,a.game_name)),**dict(zip(b.app_id,b.steam_name))}
    games["name"]=games.name.fillna(games.app_id.map(fallback)).fillna("Unmatched app "+games.app_id.astype(str))
    games["metadata_available"]=games.genres.notna().astype(int)
    games["genres"]=games.genres.map(lambda x:normalise_labels(x) if isinstance(x,(list,tuple,np.ndarray)) else [])
    games["review_group"]=games.genres.map(review_group)
    games["eligible"]=(games.metadata_available.eq(1)&games.review_group.eq("Game-related labels only")).astype(int)
    labels=games[["app_id","genres"]].explode("genres").dropna().rename(columns={"genres":"genre"}).drop_duplicates()
    audit,panel=choose_cohort(canonical,games,labels)
    if panel.empty:raise ValueError("No valid modelling cohort")
    members=labels.loc[labels.genre.isin(CATEGORIES)&labels.app_id.isin(panel.app_id)]
    monthly=panel.merge(members,on="app_id",validate="many_to_many").groupby(["genre","month"],as_index=False).agg(avg_players=("avg_players","sum"),observed_apps=("app_id","nunique")).rename(columns={"genre":"category"})
    expected=pd.MultiIndex.from_product([sorted(CATEGORIES),pd.date_range(WINDOW_START,CUTOFF,freq="MS").strftime("%Y-%m-%d")])
    if not pd.MultiIndex.from_frame(monthly[["category","month"]]).sort_values().equals(expected.sort_values()):raise ValueError("Incomplete category calendar")
    folder=ROOT/"reports/fixed_sources_v2";folder.mkdir(exist_ok=True)
    source_totals=observations.groupby("source_id").agg(rows=("app_id","size"),apps=("app_id","nunique"),last_month=("month","max")).reset_index()
    canonical_counts=canonical.groupby("source_id").size();source_totals["canonical_rows"]=source_totals.source_id.map(canonical_counts).fillna(0).astype(int)
    manifest={"version":VERSION,"frozen_on":AS_OF,"sources":sources,"metadata":{"path":str(metadata_path.relative_to(ROOT)),"sha256":digest(metadata_path),"scope":"Existing snapshot labels applied retrospectively"},"canonical_rows":len(canonical),"canonical_apps":int(canonical.app_id.nunique()),"archive_last_month":canonical.month.max(),"modelling_cutoff":CUTOFF,"window_start":WINDOW_START,"common_months":60,"cohort_apps":int(panel.app_id.nunique()),"category_months":len(monthly),"horizon_to_dec2027":23,"target_2027_leads":[12,23],"policy":"First approved source wins after compatible overlap; reject discrepancies above0.011; no missing-to-zero conversion","scope":"Selected covered cohort; historical reference v1 retained; no additional source search planned","distribution":"Raw sources stay ignored/local; licence caveats retained for publication","no_more_sources":True}
    registry=folder/"source_registry.json"
    if registry.exists() and json.loads(registry.read_text())!=manifest:raise ValueError("Frozen source roster changed; create another version")
    for name,frame in [("source_coverage",source_totals),("cohort_audit",audit.drop(columns="genres")),("category_monthly",monthly)]:frame.to_csv(folder/f"{name}.csv",index=False)
    processed=ROOT/"data/processed/fixed_sources_v2";processed.mkdir(exist_ok=True)
    canonical.to_parquet(processed/"monthly_players.parquet",index=False)
    panel.to_parquet(processed/"cohort_monthly_players.parquet",index=False)
    monthly.to_parquet(processed/"category_monthly.parquet",index=False)
    registry.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    database=ROOT/"database/steam_v2.sqlite";temporary=database.with_name(".v2-"+uuid.uuid4().hex+".sqlite.part")
    try:
        with closing(sqlite3.connect(temporary)) as con,con:
            con.executescript((ROOT/"sql/schema_v2.sql").read_text(encoding="utf-8"))
            games.drop(columns="genres").to_sql("games",con,index=False,if_exists="append")
            labels.to_sql("game_genres",con,index=False,if_exists="append")
            pd.DataFrame(sources).to_sql("sources",con,index=False,if_exists="append")
            observations.to_sql("source_observations",con,index=False,if_exists="append")
            canonical.to_sql("monthly_players",con,index=False,if_exists="append")
            audit.drop(columns="genres").to_sql("cohort_membership",con,index=False,if_exists="append")
            monthly.to_sql("category_monthly",con,index=False,if_exists="append")
            for table,columns in [("games","app_id"),("game_genres","app_id,genre"),("sources","source_id"),("source_observations","source_id,app_id,month"),("monthly_players","app_id,month"),("cohort_membership","app_id"),("category_monthly","category,month")]:con.execute(f"CREATE UNIQUE INDEX key_{table} ON {table}({columns})")
            query="SELECT gg.genre AS category,p.month,SUM(p.avg_players) AS avg_players,COUNT(*) AS observed_apps FROM monthly_players p JOIN cohort_membership c ON p.app_id=c.app_id AND c.in_cohort=1 JOIN game_genres gg ON gg.app_id=p.app_id WHERE p.month BETWEEN ? AND ? GROUP BY gg.genre,p.month"
            check=pd.read_sql_query(query,con,params=[WINDOW_START,CUTOFF]);check=check.loc[check.category.isin(CATEGORIES)]
            pd.testing.assert_frame_equal(check.sort_values(["category","month"]).reset_index(drop=True),monthly.sort_values(["category","month"]).reset_index(drop=True),check_dtype=False,rtol=1e-10,atol=1e-6)
            if con.execute("PRAGMA foreign_key_check").fetchall():raise ValueError("V2 orphan rows")
            if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("V2 database integrity failure")
        temporary.replace(database)
    finally:
        if temporary.exists():temporary.unlink()
    if digest(ROOT/"database/steam.sqlite")!=original_hash:raise ValueError("V1 database changed")
    verify_v1()
    return manifest,monthly

if __name__=="__main__":
    manifest,monthly=run();print(json.dumps({k:v for k,v in manifest.items() if k not in {"sources","metadata"}},indent=2));print(monthly.groupby("category").observed_apps.first())

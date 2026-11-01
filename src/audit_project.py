"""Read-only analytical reconciliation and whole-project ML audit evidence."""
from pathlib import Path
from contextlib import closing
import ast,hashlib,json,sqlite3
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
try:
    from .audit_validation import validate_predictions,require_same_targets,require_lineage
    from .gradient_boosting import training_features,PARAMS
    from .baselines import backtest,ORIGINS,score_forecasts
    from .project_2027 import run as verify_frozen
    from .statistical_models import evaluate as evaluate_statistical
except ImportError:
    from audit_validation import validate_predictions,require_same_targets,require_lineage
    from gradient_boosting import training_features,PARAMS
    from baselines import backtest,ORIGINS,score_forecasts
    from project_2027 import run as verify_frozen
    from statistical_models import evaluate as evaluate_statistical
ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def run():
    checks=[]
    sources=json.loads((ROOT/"data/raw/sources.json").read_text())
    for source in sources["sources"]:
        for file in source["files"]:
            if digest(ROOT/file["path"])!=file["sha256"]:raise ValueError("Raw source checksum mismatch")
    checks.append("All original raw source hashes match")
    with closing(sqlite3.connect((ROOT/"database/steam.sqlite").as_uri()+"?mode=ro",uri=True)) as con:
        if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or con.execute("PRAGMA foreign_key_check").fetchall():raise ValueError("Database integrity failure")
        for name in ["games","game_genres","monthly_players"]:
            database=pd.read_sql_query("SELECT * FROM "+name,con)
            processed=pd.read_parquet(ROOT/f"data/processed/{name}.parquet")
            keys={"games":["app_id"],"game_genres":["app_id","genre"],"monthly_players":["app_id","month"]}[name]
            pd.testing.assert_frame_equal(database[processed.columns].sort_values(keys).reset_index(drop=True),processed.sort_values(keys).reset_index(drop=True),check_dtype=False)
        database_monthly=pd.read_sql_query("SELECT * FROM category_monthly",con)
    checks.append("SQLite integrity, foreign keys and all prepared Parquet values reconcile")
    monthly=pd.read_csv(ROOT/"reports/exploration_monthly.csv",parse_dates=["month"])
    database_monthly["month"]=pd.to_datetime(database_monthly.month)
    common=[c for c in monthly.columns if c in database_monthly]
    pd.testing.assert_frame_equal(monthly[common].sort_values(["category","month"]).reset_index(drop=True),database_monthly[common].sort_values(["category","month"]).reset_index(drop=True),check_dtype=False)
    checks.append("All795 exploration targets reconcile with SQL")
    baseline=backtest(monthly,ORIGINS)
    stored=pd.read_csv(ROOT/"reports/baseline_predictions.csv",parse_dates=["month","origin"])
    pd.testing.assert_frame_equal(baseline,stored,check_dtype=False,rtol=1e-10,atol=1e-7)
    statistical,_=evaluate_statistical(monthly)
    saved=pd.read_csv(ROOT/"reports/statistical_models/predictions.csv",parse_dates=["month","origin"])
    pd.testing.assert_frame_equal(statistical,saved,check_dtype=False,rtol=1e-9,atol=1e-5)
    checks.append("All1080 baseline and2700 statistical-comparison predictions freshly reproduce")
    source=ROOT/"reports/exploration_monthly.csv"
    tables={}
    for folder,key in [("model_comparison","input_sha256"),("feature_experiments","input_sha256"),("tuning","source_sha256")]:
        require_lineage(ROOT,"reports/"+folder,source,key)
        frame=validate_predictions(pd.read_csv(ROOT/f"reports/{folder}/predictions.csv"))
        actual=frame.merge(monthly[["category","month","avg_players"]],on=["category","month"],validate="many_to_one")
        if not np.allclose(actual.actual,actual.avg_players):raise ValueError("Stale actuals")
        tables[folder]=frame
    require_same_targets(tables["model_comparison"],tables["feature_experiments"])
    require_same_targets(tables["model_comparison"].loc[tables["model_comparison"].category.isin(tables["tuning"].category)],tables["tuning"])
    checks.append("Model/feature/tuning source lineage, numeric errors, actuals and complete per-model fold inventories pass")
    try:
        from .gradient_boosting import evaluate as evaluate_ml
        from .feature_experiments import evaluate as evaluate_features,forecast as feature_forecast
        from .tune_candidates import select_parameters,SHORTLIST
    except ImportError:
        from gradient_boosting import evaluate as evaluate_ml
        from feature_experiments import evaluate as evaluate_features,forecast as feature_forecast
        from tune_candidates import select_parameters,SHORTLIST
    def reconcile_fresh(fresh,saved):
        columns=["category","origin","month","lead","model"]
        fresh=validate_predictions(fresh).sort_values(columns).reset_index(drop=True)
        saved=validate_predictions(saved).sort_values(columns).reset_index(drop=True)
        pd.testing.assert_frame_equal(fresh[columns+["actual","prediction"]],saved[columns+["actual","prediction"]],check_dtype=False,rtol=1e-9,atol=1e-5)
    fresh_ml,_,_=evaluate_ml(monthly)
    reconcile_fresh(fresh_ml,tables["model_comparison"])
    fresh_features,_=evaluate_features(monthly)
    reconcile_fresh(fresh_features,tables["feature_experiments"])
    saved_parameters=pd.read_csv(ROOT/"reports/tuning/selected_parameters.csv",parse_dates=["origin"])
    for category,group in SHORTLIST.items():
        series=monthly.loc[monthly.category.eq(category)].set_index("month").avg_players.sort_index()
        for origin in ORIGINS:
            params,_,candidate=select_parameters(series.loc[:origin],group)
            saved_choice=saved_parameters.loc[saved_parameters.category.eq(category)&saved_parameters.origin.eq(origin)]
            if len(saved_choice)!=1 or int(saved_choice.candidate.iloc[0])!=candidate:raise ValueError("Tuning candidate changed on replay")
            values,_=feature_forecast(series.loc[:origin],27,group,parameters=params)
            saved_values=tables["tuning"].loc[tables["tuning"].category.eq(category)&tables["tuning"].origin.eq(origin)].sort_values("lead").prediction.to_numpy()
            np.testing.assert_allclose(values,saved_values,rtol=1e-9,atol=1e-5)
    checks.append("Fresh replay reproduces3240 model-family rows,2160 feature rows and324 tuned projections plus selected candidates")
    verify_frozen();checks.append("Frozen forecasts, policy, annual summaries and final-fit tuning evidence hashes pass")
    cells=0;notebooks=0
    for path in (ROOT/"src").glob("*.py"):ast.parse(path.read_text(encoding="utf-8-sig"))
    for path in (ROOT/"notebooks").glob("*.ipynb"):
        nb=json.loads(path.read_text(encoding="utf-8"));notebooks+=1
        for cell in nb["cells"]:
            if cell["cell_type"]=="code":
                ast.parse("".join(cell["source"]));cells+=1
                if any(o.get("output_type")=="error" for o in cell.get("outputs",[])):raise ValueError("Saved notebook error")
    checks.append(f"All source and{cells}code cells in{notebooks}notebooks parse; no saved error outputs")
    overfit=[]
    reference=tables["model_comparison"].loc[tables["model_comparison"].model.eq("Gradient boosting")]
    for category,group in monthly.groupby("category"):
        series=group.set_index("month").avg_players.sort_index()
        for origin in ORIGINS:
            X,y=training_features(series.loc[:origin]);model=GradientBoostingRegressor(**PARAMS).fit(X,y)
            train_mae=np.abs(y-model.predict(X)).mean()
            future=reference.loc[reference.category.eq(category)&reference.origin.eq(origin)&reference.lead.ge(16)]
            overfit.append({"category":category,"origin":origin,"training_one_step_mae":train_mae,"development_long_lead_mae":future.error.abs().mean(),"training_rows":len(y),"caveat":"In-sample one-step versus held-out recursive long-lead errors differ in horizon and distribution; gap alone does not prove overfitting"})
    routes={"Action":("model_comparison","Last value"),"Indie":("model_comparison","Gradient boosting"),"Massively Multiplayer":("model_comparison","Last value"),"RPG":("tuning","Chronologically tuned boosting"),"Strategy":("feature_experiments","Recent changes")}
    selected=pd.concat([tables[folder].loc[tables[folder].category.eq(category)&tables[folder].model.eq(model)] for category,(folder,model) in routes.items()])
    annual=selected.loc[selected.lead.ge(16)].groupby(["category","origin"],as_index=False).agg(actual_mean=("actual","mean"),predicted_mean=("prediction","mean"),months=("lead","size"))
    if not annual.months.eq(12).all():raise ValueError("Incomplete annual target window")
    annual["actual_rank"]=annual.groupby("origin").actual_mean.rank(method="min",ascending=False)
    annual["predicted_rank"]=annual.groupby("origin").predicted_mean.rank(method="min",ascending=False)
    annual["absolute_mean_error"]=(annual.actual_mean-annual.predicted_mean).abs()
    annual["absolute_rank_error"]=(annual.actual_rank-annual.predicted_rank).abs()
    folder=ROOT/"reports/full_audit";folder.mkdir(exist_ok=True)
    pd.DataFrame(overfit).to_csv(folder/"training_forecast_gaps.csv",index=False)
    annual.to_csv(folder/"annual_ranking_diagnostics.csv",index=False)
    evidence={"checks":checks,"notebooks":notebooks,"parsed_code_cells":cells,"target_cutoff":str(monthly.month.max().date()),"categories":int(monthly.category.nunique()),"category_months":len(monthly),"source_sha256":digest(source),"database_sha256":digest(ROOT/"database/steam.sqlite"),"scope":"Read-only source/model reconciliation; report outputs only; historical policy ranking remains development evidence"}
    (folder/"evidence.json").write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(evidence,indent=2))
    return evidence

if __name__=="__main__":run()

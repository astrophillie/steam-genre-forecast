"""Small nested chronological search on shortlisted development candidates."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
try:
    from .feature_experiments import forecast
    from .gradient_boosting import PARAMS
    from .baselines import ORIGINS,HORIZON,validate_series,score_forecasts,backtest
except ImportError:
    from feature_experiments import forecast
    from gradient_boosting import PARAMS
    from baselines import ORIGINS,HORIZON,validate_series,score_forecasts,backtest
try:
    from .audit_validation import validate_predictions, require_lineage, require_same_targets
except ImportError:
    from audit_validation import validate_predictions, require_lineage, require_same_targets
ROOT=Path(__file__).resolve().parents[1]
SHORTLIST={"Indie":"Reference","RPG":"Rolling variability","Strategy":"Recent changes"}
GRID=[{**PARAMS,"max_depth":depth,"n_estimators":trees} for depth in [1,2] for trees in [100,200]]

def inner_origins(train,horizon=HORIZON):
    validate_series(train)
    # Each inner target window ends at or before the outer training cutoff.
    latest=len(train)-horizon-1
    positions=[latest-12,latest]
    if positions[0]<35:raise ValueError("Insufficient history for two inner windows")
    return [train.index[i] for i in positions]

def select_parameters(train,group):
    rows=[]
    for candidate,params in enumerate(GRID):
        for origin in inner_origins(train):
            values,_=forecast(train.loc[:origin],HORIZON,group,parameters=params)
            dates=pd.date_range(origin+pd.offsets.MonthBegin(),periods=HORIZON,freq="MS")
            actual=train.reindex(dates)
            if actual.isna().any():raise ValueError("Inner outcomes unavailable at outer cutoff")
            rows.append({"candidate":candidate,"inner_origin":origin,"last_target_month":dates[-1],"mae":np.abs(actual.to_numpy()[15:]-values[15:]).mean()})
    scores=pd.DataFrame(rows)
    ranking=scores.groupby("candidate").mae.mean().sort_values(kind="stable")
    return GRID[int(ranking.index[0])],scores,int(ranking.index[0])

def run():
    source=ROOT/"reports/exploration_monthly.csv"
    data=pd.read_csv(source,parse_dates=["month"])
    backtest(data,ORIGINS,HORIZON)
    trials=[];rows=[];selected=[]
    for category,group in SHORTLIST.items():
        series=data.loc[data.category.eq(category)].set_index("month").avg_players.sort_index()
        for origin in ORIGINS:
            train=series.loc[:origin]
            params,search,candidate=select_parameters(train,group)
            search["category"]=category;search["outer_origin"]=origin;trials.append(search)
            values,info=forecast(train,HORIZON,group,parameters=params)
            dates=pd.date_range(origin+pd.offsets.MonthBegin(),periods=HORIZON,freq="MS")
            rows.append(pd.DataFrame({"category":category,"origin":origin,"month":dates,"lead":np.arange(1,HORIZON+1),"model":"Chronologically tuned boosting","actual":series.reindex(dates).to_numpy(),"prediction":values}))
            selected.append({"category":category,"origin":origin,"feature_group":group,"candidate":candidate,**params,**info})
    tuned=pd.concat(rows,ignore_index=True);tuned["error"]=tuned.actual-tuned.prediction
    require_lineage(ROOT,"reports/model_comparison",source)
    require_lineage(ROOT,"reports/feature_experiments",source)
    existing=pd.read_csv(ROOT/"reports/model_comparison/predictions.csv",parse_dates=["origin","month"])
    features=pd.read_csv(ROOT/"reports/feature_experiments/predictions.csv",parse_dates=["origin","month"])
    require_same_targets(existing,features)
    require_same_targets(existing.loc[existing.category.isin(SHORTLIST)],tuned)
    features=features.loc[~features.model.eq("Reference")].copy();features["model"]="Boosting + "+features.model
    combined=pd.concat([existing,features,tuned],ignore_index=True)
    if combined.duplicated(["category","origin","month","model"]).any():raise ValueError("Repeated forecast keys")
    long=combined.loc[combined.lead.ge(16)].assign(absolute_error=lambda d:d.error.abs())
    fold=long.groupby(["category","model","origin"],as_index=False).agg(mae=("absolute_error","mean"),mean_error=("error","mean"))
    summary=fold.groupby(["category","model"],as_index=False).agg(mean_mae=("mae","mean"),worst_fold_mae=("mae","max"),mean_error=("mean_error","mean"),origins=("origin","nunique"))
    folder=ROOT/"reports/tuning";folder.mkdir(exist_ok=True)
    for name,frame in [("search_trials",pd.concat(trials,ignore_index=True)),("selected_parameters",pd.DataFrame(selected)),("predictions",tuned),("comparison",summary),("fold_scores",fold),("scores",score_forecasts(combined))]:frame.to_csv(folder/f"{name}.csv",index=False)
    (folder/"manifest.json").write_text(json.dumps({"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"shortlist":SHORTLIST,"grid":GRID,"inner_windows":2,"inner_horizon":27,"objective":"MAE on leads16–27","scope":"Nested time-aware parameter selection; feature shortlist already informed by development outcomes; not independent final test"},indent=2)+"\n",encoding="utf-8")
    return summary

if __name__=="__main__":
    comparison=run()
    print(comparison.loc[comparison.model.isin(["Chronologically tuned boosting","Last value","Gradient boosting"])].round(2).to_string(index=False))

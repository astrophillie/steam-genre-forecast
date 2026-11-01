"""Controlled past-only feature experiments for recursive category forecasts."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
try:
    from .gradient_boosting import feature_row,FEATURES,PARAMS
    from .baselines import validate_series,backtest,score_forecasts,ORIGINS,HORIZON
except ImportError:
    from gradient_boosting import feature_row,FEATURES,PARAMS
    from baselines import validate_series,backtest,score_forecasts,ORIGINS,HORIZON
try:
    from .audit_validation import validate_predictions, require_lineage, require_same_targets
except ImportError:
    from audit_validation import validate_predictions, require_lineage, require_same_targets
ROOT=Path(__file__).resolve().parents[1]
GROUPS={"Reference":[],"Recent changes":["change_1","change_3"],"Rolling variability":["std_3","std_12"],"Time trend":["elapsed_months"]}

def make_features(history,month,group):
    if group not in GROUPS:
        raise ValueError("Unknown feature group")
    base=feature_row(history,month)
    v=np.asarray(history,dtype=float)
    extras={"Reference":[],"Recent changes":[v[-1]-v[-2],v[-1]-v[-4]],
            "Rolling variability":[v[-3:].std(ddof=0),v[-12:].std(ddof=0)],
            "Time trend":[len(v)]}
    return base+extras[group]

def forecast(train,horizon,group,parameters=None):
    from numbers import Integral
    if isinstance(horizon,bool) or not isinstance(horizon,Integral) or horizon<=0:
        raise ValueError("Positive integer horizon required")
    values=validate_series(train)
    if len(values)<36:
        raise ValueError("At least 36 months required")
    columns=FEATURES+GROUPS[group]
    X=pd.DataFrame([make_features(values[:i],train.index[i],group) for i in range(12,len(values))],columns=columns)
    model=GradientBoostingRegressor(**(PARAMS if parameters is None else parameters)).fit(X,values[12:])
    state=list(values);predicted=[];clipped=0
    for date in pd.date_range(train.index[-1]+pd.offsets.MonthBegin(),periods=horizon,freq="MS"):
        value=float(model.predict(pd.DataFrame([make_features(state,date,group)],columns=columns))[0])
        if not np.isfinite(value):raise ValueError("Nonfinite forecast")
        clipped+=int(value<0);value=max(value,0.)
        predicted.append(value);state.append(value)
    return np.array(predicted),{"training_rows":len(X),"features":len(columns),"clipped_predictions":clipped}

def evaluate(monthly,origins=ORIGINS,horizon=HORIZON):
    backtest(monthly,origins,horizon) # Reuse source, calendar and evaluation validation.
    data=monthly.copy();data["month"]=pd.to_datetime(data.month)
    rows=[];diagnostics=[]
    for category,frame in data.groupby("category"):
        series=frame.set_index("month").avg_players.sort_index()
        for origin in pd.DatetimeIndex(origins):
            dates=pd.date_range(origin+pd.offsets.MonthBegin(),periods=horizon,freq="MS")
            for group in GROUPS:
                values,info=forecast(series.loc[:origin],horizon,group)
                rows.append(pd.DataFrame({"category":category,"origin":origin,"month":dates,"lead":np.arange(1,horizon+1),"model":group,"actual":series.reindex(dates).to_numpy(),"prediction":values}))
                diagnostics.append({"category":category,"origin":origin,"group":group,**info})
    predictions=pd.concat(rows,ignore_index=True);predictions["error"]=predictions.actual-predictions.prediction
    return predictions,pd.DataFrame(diagnostics)

def run():
    source=ROOT/"reports/exploration_monthly.csv"
    predictions,diagnostics=evaluate(pd.read_csv(source))
    scores=score_forecasts(predictions)
    long=predictions.loc[predictions.lead.ge(16)].assign(absolute_error=lambda x:x.error.abs())
    folds=long.groupby(["category","origin","model"],as_index=False).agg(mae=("absolute_error","mean"),mean_error=("error","mean"))
    ref=folds.loc[folds.model.eq("Reference"),["category","origin","mae"]].rename(columns={"mae":"reference_mae"})
    folds=folds.merge(ref,on=["category","origin"],validate="many_to_one")
    folds["wins_vs_reference"]=folds.mae.lt(folds.reference_mae-1e-6)
    stability=folds.groupby(["category","model"],as_index=False).agg(worst_fold_mae=("mae","max"),wins_vs_reference=("wins_vs_reference","sum"))
    # Confirm exact reference reproducibility against the original ML experiment.
    require_lineage(ROOT,"reports/model_comparison",source)
    old=pd.read_csv(ROOT/"reports/model_comparison/predictions.csv",parse_dates=["origin","month"])
    require_same_targets(predictions,old)
    reference=predictions.loc[predictions.model.eq("Reference")]
    check=reference.merge(old.loc[old.model.eq("Gradient boosting")],on=["category","origin","month","lead"],suffixes=("_new","_old"),validate="one_to_one")
    if len(check)!=len(reference) or not np.allclose(check.prediction_new,check.prediction_old,rtol=1e-12,atol=1e-8):
        raise ValueError("Reference forecasts changed")
    folder=ROOT/"reports/feature_experiments";folder.mkdir(exist_ok=True)
    for name,frame in [("predictions",predictions),("scores",scores),("fold_scores",folds),("stability",stability),("diagnostics",diagnostics)]:frame.to_csv(folder/f"{name}.csv",index=False)
    (folder/"manifest.json").write_text(json.dumps({"input_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"groups":GROUPS,"parameters":PARAMS,"origins":[str(x.date()) for x in ORIGINS],"horizon":HORIZON,"scope":"Exploratory feature additions; unchanged model parameters; no final selection"},indent=2)+"\n",encoding="utf-8")
    return scores,folds,stability

if __name__=="__main__":
    scores,_,stability=run()
    print(scores.loc[scores.window.eq("Leads 16 to 27")].pivot(index="category",columns="model",values="mae").round(2).to_string())
    print(stability.to_string(index=False))

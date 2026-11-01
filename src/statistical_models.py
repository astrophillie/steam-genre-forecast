"""Fixed-origin exponential-smoothing comparisons on the pinned historical cohort."""
from pathlib import Path
from numbers import Integral
import warnings
import hashlib
import json
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
try:
    from .baselines import validate_series, backtest, score_forecasts, ORIGINS, HORIZON
except ImportError:
    from baselines import validate_series, backtest, score_forecasts, ORIGINS, HORIZON
ROOT=Path(__file__).resolve().parents[1]
CONFIGS={"SES":{},"Damped trend":{"trend":"add","damped_trend":True},
         "Damped seasonal":{"trend":"add","damped_trend":True,"seasonal":"add","seasonal_periods":12}}

def forecast_statistical(train,horizon,model):
    if isinstance(horizon,bool) or not isinstance(horizon,Integral) or horizon<=0:
        raise ValueError("Positive integer horizon required")
    values=validate_series(train)
    if len(values)<24:
        raise ValueError("At least 24 months required")
    if model not in CONFIGS:
        raise ValueError("Unknown model")
    # Rescaling improves numerical conditioning without adding future information.
    maximum=float(np.max(values))
    scale=max(float(np.mean(values)) if maximum<=np.finfo(float).max/len(values) else float(np.mean(values/maximum)*maximum),1.)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fit=ExponentialSmoothing(values/scale,initialization_method="estimated",**CONFIGS[model]).fit(optimized=True,use_brute=True)
        predicted=np.asarray(fit.forecast(horizon),dtype=float)*scale
    converged=bool(fit.mle_retvals.get("success",True))
    if not np.isfinite(predicted).all():
        raise ValueError("Nonfinite forecast")
    if not converged:raise ValueError("Statistical optimiser did not converge; predictions rejected")
    clipped=int((predicted<0).sum())
    return np.maximum(predicted,0),{"converged":converged,"clipped_predictions":clipped,"warnings":" | ".join(str(w.message) for w in caught)}

def evaluate(monthly,origins=ORIGINS,horizon=HORIZON):
    # Existing validation also enforces complete outcomes and identical fold keys.
    baseline=backtest(monthly,origins,horizon)
    rows=[];diagnostics=[]
    data=monthly.copy();data["month"]=pd.to_datetime(data.month)
    for category,frame in data.groupby("category"):
        series=frame.set_index("month").avg_players.sort_index()
        for origin in pd.DatetimeIndex(origins):
            train=series.loc[:origin]
            dates=pd.date_range(origin+pd.offsets.MonthBegin(),periods=horizon,freq="MS")
            for model in CONFIGS:
                values,info=forecast_statistical(train,horizon,model)
                rows.append(pd.DataFrame({"category":category,"origin":origin,"month":dates,"lead":np.arange(1,horizon+1),"model":model,"actual":series.reindex(dates).to_numpy(),"prediction":values}))
                diagnostics.append({"category":category,"origin":origin,"model":model,**info})
    result=pd.concat([baseline,*rows],ignore_index=True)
    result["error"]=result.actual-result.prediction
    return result,pd.DataFrame(diagnostics)

def run():
    source=ROOT/"reports/exploration_monthly.csv"
    monthly=pd.read_csv(source)
    predictions,diagnostics=evaluate(monthly)
    scores=score_forecasts(predictions)
    fold=predictions.loc[predictions.lead.between(16,27)].assign(absolute_error=lambda d:d.error.abs()).groupby(["category","model","origin"],as_index=False).agg(mae=("absolute_error","mean"))
    folder=ROOT/"reports/statistical_models";folder.mkdir(exist_ok=True)
    for name,frame in [("predictions",predictions),("scores",scores),("diagnostics",diagnostics),("fold_scores",fold)]:frame.to_csv(folder/f"{name}.csv",index=False)
    manifest={"input_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"origins":[x.strftime("%Y-%m-%d") for x in ORIGINS],"horizon":HORIZON,"configs":CONFIGS,"negative_prediction_policy":"Clip at zero and report count","scope":"Historical development comparison; no final selection or current 2027 forecast"}
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return predictions,scores,diagnostics,fold

if __name__=="__main__":
    _,scores,diagnostics,_=run()
    print(scores.loc[scores.window.eq("Leads 16 to 27"),["category","model","mae"]].to_string(index=False))
    print("Unconverged fits:",int((~diagnostics.converged).sum()))

"""Recursive gradient boosting evaluated against the same historical model folds."""
from pathlib import Path
from numbers import Integral
import hashlib
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
import sklearn
try:
    from .baselines import validate_series, ORIGINS, HORIZON, score_forecasts
    from .statistical_models import evaluate as evaluate_statistical
except ImportError:
    from baselines import validate_series, ORIGINS, HORIZON, score_forecasts
    from statistical_models import evaluate as evaluate_statistical
ROOT=Path(__file__).resolve().parents[1]
MODEL="Gradient boosting"
LAGS=(1,2,3,6,12)
FEATURES=[f"lag_{lag}" for lag in LAGS]+["rolling_mean_3","rolling_mean_12","month_sin","month_cos","days_in_month"]
PARAMS={"n_estimators":100,"learning_rate":0.05,"max_depth":2,"min_samples_leaf":5,"loss":"squared_error","random_state":42}

def feature_row(history,month):
    """Only history before this target month is supplied by the caller."""
    values=np.asarray(history,dtype=float)
    if values.ndim!=1 or len(values)<12 or not np.isfinite(values).all() or (values<0).any() or (values>np.finfo(np.float32).max).any():
        raise ValueError("At least 12 finite nonnegative historical values required")
    date=pd.Timestamp(month)
    if pd.isna(date) or not date.is_month_start:raise ValueError("Expected a month-start target date")
    angle=2*np.pi*(date.month-1)/12
    return [values[-lag] for lag in LAGS]+[values[-3:].mean(),values[-12:].mean(),np.sin(angle),np.cos(angle),date.days_in_month]

def training_features(train):
    values=validate_series(train)
    if len(values)<36:
        raise ValueError("At least 36 months required for lag training")
    features=[feature_row(values[:i],train.index[i]) for i in range(12,len(values))]
    return pd.DataFrame(features,columns=FEATURES),values[12:]

def recursive_predict(model,history,first_month,horizon):
    if isinstance(horizon,bool) or not isinstance(horizon,Integral) or horizon<=0:
        raise ValueError("Positive integer horizon required")
    state=list(np.asarray(history,dtype=float));predictions=[];clipped=0
    for month in pd.date_range(first_month,periods=horizon,freq="MS"):
        features=pd.DataFrame([feature_row(state,month)],columns=FEATURES)
        value=float(model.predict(features)[0])
        if not np.isfinite(value):
            raise ValueError("Nonfinite forecast")
        clipped+=int(value<0);value=max(value,0.)
        predictions.append(value);state.append(value)
    return np.asarray(predictions),clipped

def forecast_boosting(train,horizon):
    X,y=training_features(train)
    model=GradientBoostingRegressor(**PARAMS).fit(X,y)
    forecast,clipped=recursive_predict(model,train.to_numpy(),train.index[-1]+pd.offsets.MonthBegin(),horizon)
    return forecast,{"training_rows":len(y),"clipped_predictions":clipped},model.feature_importances_

def evaluate(monthly,origins=ORIGINS,horizon=HORIZON):
    combined,_=evaluate_statistical(monthly,origins,horizon)
    rows=[];diagnostics=[];importance=[]
    data=monthly.copy();data["month"]=pd.to_datetime(data.month)
    for category,frame in data.groupby("category"):
        series=frame.set_index("month").avg_players.sort_index()
        for origin in pd.DatetimeIndex(origins):
            train=series.loc[:origin]
            values,info,weights=forecast_boosting(train,horizon)
            dates=pd.date_range(origin+pd.offsets.MonthBegin(),periods=horizon,freq="MS")
            rows.append(pd.DataFrame({"category":category,"origin":origin,"month":dates,"lead":np.arange(1,horizon+1),"model":MODEL,"actual":series.reindex(dates).to_numpy(),"prediction":values}))
            diagnostics.append({"category":category,"origin":origin,**info})
            importance.extend({"category":category,"origin":origin,"feature":name,"importance":weight} for name,weight in zip(FEATURES,weights))
    predictions=pd.concat([combined,*rows],ignore_index=True)
    predictions["error"]=predictions.actual-predictions.prediction
    return predictions,pd.DataFrame(diagnostics),pd.DataFrame(importance)

def run():
    source=ROOT/"reports/exploration_monthly.csv"
    predictions,diagnostics,importance=evaluate(pd.read_csv(source))
    scores=score_forecasts(predictions)
    fold=predictions.loc[predictions.lead.between(16,27)].assign(absolute_error=lambda x:x.error.abs()).groupby(["category","model","origin"],as_index=False).agg(mae=("absolute_error","mean"))
    folder=ROOT/"reports/model_comparison";folder.mkdir(exist_ok=True)
    for name,frame in [("predictions",predictions),("scores",scores),("fold_scores",fold),("boosting_diagnostics",diagnostics),("feature_importance",importance)]:frame.to_csv(folder/f"{name}.csv",index=False)
    manifest={"input_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"origins":[x.strftime("%Y-%m-%d") for x in ORIGINS],"horizon":HORIZON,"model":MODEL,"parameters":PARAMS,"features":FEATURES,"sklearn_version":sklearn.__version__,"strategy":"Fit once per category/origin; recursively append predictions, never future actuals","scope":"Historical development comparison; selection and final forecast deferred"}
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return predictions,scores,diagnostics,importance,fold

if __name__=="__main__":
    _,scores,_,_,_=run()
    print(scores.loc[scores.window.eq("Leads 16 to 27")].pivot(index="category",columns="model",values="mae").round(2))

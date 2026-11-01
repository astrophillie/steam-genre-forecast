"""Frozen development policy and exploratory 2027 historical-snapshot projections."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
try:
    from .baselines import forecast_baselines,validate_series
    from .feature_experiments import forecast
    from .tune_candidates import select_parameters
    from .gradient_boosting import PARAMS
except ImportError:
    from baselines import forecast_baselines,validate_series
    from feature_experiments import forecast
    from tune_candidates import select_parameters
    from gradient_boosting import PARAMS
ROOT=Path(__file__).resolve().parents[1]
ISSUED="2026-10-26"
POLICY={"Action":{"method":"Last value"},"Indie":{"method":"Boosting","features":"Reference"},
        "Massively Multiplayer":{"method":"Last value"},
        "RPG":{"method":"Tuned boosting","features":"Rolling variability"},
        "Strategy":{"method":"Boosting","features":"Recent changes"}}

def annual_summary(predictions):
    required={"policy","category","month","prediction"}
    if predictions.empty or not required<=set(predictions):raise ValueError("Annual projection input is empty or missing fields")
    predictions=predictions.copy()
    for key in ["policy","category"]:
        if not predictions[key].map(lambda x:isinstance(x,str) and bool(x.strip())).all():raise ValueError("Missing policy/category")
    predictions["month"]=pd.to_datetime(predictions.month,errors="raise")
    if predictions.month.isna().any() or not predictions.month.dt.is_month_start.all():raise ValueError("Invalid month-start date")
    predictions["prediction"]=pd.to_numeric(predictions.prediction,errors="raise")
    if not np.isfinite(predictions.prediction).all() or predictions.prediction.lt(0).any():raise ValueError("Invalid projection value")
    target=predictions.loc[predictions.month.between("2027-01-01","2027-12-01")]
    if target.empty or len(target.groupby(["policy","category"]))!=len(predictions.groupby(["policy","category"])):raise ValueError("Every annual group requires 12 months")
    if target.duplicated(["policy","category","month"]).any():raise ValueError("Repeated target month")
    annual=target.groupby(["policy","category"],as_index=False).agg(projected_mean_activity=("prediction","mean"),months=("month","nunique"))
    if not annual.months.eq(12).all():raise ValueError("Every annual result requires 12 distinct target months")
    annual["rank"]=annual.groupby("policy").projected_mean_activity.rank(method="min",ascending=False).astype(int)
    return annual.sort_values(["policy","rank","category"])

def run():
    source=ROOT/"reports/exploration_monthly.csv"
    frozen_folder=ROOT/"reports/forecast_2027"
    frozen_manifest=frozen_folder/"frozen_policy.json"
    if frozen_manifest.exists():
        frozen=json.loads(frozen_manifest.read_text(encoding="utf-8"))
        if frozen["input_sha256"]!=hashlib.sha256(source.read_bytes()).hexdigest() or frozen["policy"]!=POLICY:
            raise ValueError("Frozen source or policy changed; create a new version")
        hashes=json.loads((frozen_folder/"checksums.json").read_text())
        required={"monthly_projections.csv","annual_summary.csv","frozen_policy.json","final_fit_inner_trials.csv"}
        if set(hashes)!=required:raise ValueError("Incomplete frozen checksum inventory")
        for name,expected in hashes.items():
            if hashlib.sha256((frozen_folder/name).read_bytes()).hexdigest()!=expected:
                raise ValueError("Frozen artifact checksum mismatch")
        return pd.read_csv(frozen_folder/"annual_summary.csv")
    data=pd.read_csv(source,parse_dates=["month"])
    if set(data.category)!=set(POLICY):raise ValueError("Unexpected categories")
    cutoff=data.month.max()
    if cutoff!=pd.Timestamp("2025-09-01"):raise ValueError("Reevaluate policy for a changed cutoff")
    dates=pd.date_range(cutoff+pd.offsets.MonthBegin(),"2027-12-01",freq="MS")
    rows=[];fits=[];inner=[]
    for category,rule in POLICY.items():
        series=data.loc[data.category.eq(category)].set_index("month").avg_players.sort_index()
        validate_series(series)
        if series.index[-1]!=cutoff:raise ValueError("Inconsistent category cutoffs")
        base=forecast_baselines(series,len(dates))["Last value"]
        params=None
        if rule["method"]=="Last value":values=base;info={}
        else:
            params=PARAMS.copy()
            if rule["method"]=="Tuned boosting":
                params,trials,candidate=select_parameters(series,rule["features"])
                trials["category"]=category;inner.append(trials)
            values,info=forecast(series,len(dates),rule["features"],parameters=params)
        if len(values)!=len(dates) or not np.isfinite(values).all() or (values<0).any():raise ValueError("Invalid projection")
        fits.append({"category":category,"feature_group":rule.get("features"),**rule,"parameters":params,**info})
        for name,predicted in [("Last-value reference",base),("Provisional development policy",values)]:
            rows.append(pd.DataFrame({"policy":name,"category":category,"month":dates.strftime("%Y-%m-%d"),"lead":np.arange(1,len(dates)+1),"prediction":predicted,"training_cutoff":cutoff.strftime("%Y-%m-%d"),"issued_on":ISSUED}))
    predictions=pd.concat(rows,ignore_index=True)
    annual=annual_summary(predictions)
    folder=ROOT/"reports/forecast_2027";folder.mkdir(exist_ok=True)
    predictions.to_csv(folder/"monthly_projections.csv",index=False)
    annual.to_csv(folder/"annual_summary.csv",index=False)
    pd.concat(inner,ignore_index=True).to_csv(folder/"final_fit_inner_trials.csv",index=False)
    manifest={"issued_on":ISSUED,"training_cutoff":str(cutoff.date()),"target":"2027 monthly average concurrent category activity; fixed historical cohort",
        "policy":POLICY,"fits":fits,"input_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
        "comparison_sha256":hashlib.sha256((ROOT/"reports/tuning/comparison.csv").read_bytes()).hexdigest(),
        "selection_rationale":{"Action":"Last value retained: challengers did not improve mean error reliably","Massively Multiplayer":"Last value retained: challengers offered no useful average advantage","Indie":"Original boosting retained: tiny trend addition is not persuasive; tuning worsens","RPG":"Tuned variability candidate retained provisionally: improved mean and worst-fold error","Strategy":"Untuned recent changes retained provisionally: three ML fold wins, modest gain over last value; worst-fold limitations retained"},
        "scope":"Exploratory projection, not a validated current-market forecast or untouched-test result",
        "evaluation_policy":"Freeze output bytes now. Future matching 2027 observations may be scored without retuning; source/eligibility changes require separately versioned evaluation. Already-reviewed development outcomes are not a final holdout.",
        "uncertainty":"No calibrated prediction intervals established; model-policy differences are sensitivity comparisons, not confidence bounds"}
    manifest_path=folder/"frozen_policy.json"
    if manifest_path.exists():
        old=json.loads(manifest_path.read_text())
        if old["input_sha256"]!=manifest["input_sha256"] or old["policy"]!=POLICY:raise ValueError("Frozen policy/source changed; use a new version")
    manifest_path.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [folder/"monthly_projections.csv",folder/"annual_summary.csv",manifest_path,folder/"final_fit_inner_trials.csv"]}
    (folder/"checksums.json").write_text(json.dumps(hashes,indent=2)+"\n",encoding="utf-8")
    return annual

if __name__=="__main__":print(run().round(2).to_string(index=False))

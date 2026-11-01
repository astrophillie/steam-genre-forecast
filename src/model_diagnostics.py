"""Investigate historical forecast failures before model selection."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]

def activity_flags(monthly):
    """Retrospective inspection flags, calibrated only on earlier monthly changes."""
    rows=[]
    for category,group in monthly.groupby("category"):
        group=group.sort_values("month").copy()
        change=group.avg_players.pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan)
        center=change.shift(1).rolling(24,min_periods=12).median()
        # Each scale is computed from the same previous-only window.
        scale=change.shift(1).rolling(24,min_periods=12).apply(lambda x:np.median(np.abs(x-np.median(x))),raw=True)*1.4826
        score=(change-center)/scale.where(scale.gt(0))
        group["monthly_change_pct"]=100*change
        group["change_robust_z"]=score
        group["unusual_change"]=pd.Series(pd.NA,index=group.index,dtype="boolean")
        valid=score.notna()
        group.loc[valid,"unusual_change"]=score.loc[valid].abs().gt(3.5)
        group["coverage_change_pp"]=100*group.coverage_rate.diff()
        group["observed_app_change"]=group.observed_apps.diff()
        rows.append(group)
    return pd.concat(rows,ignore_index=True)

def diagnose(predictions,monthly):
    if predictions.duplicated(["category","origin","month","model"]).any():
        raise ValueError("Duplicate forecast keys")
    if not np.allclose(predictions.actual-predictions.prediction,predictions.error):
        raise ValueError("Error sign inconsistent")
    flags=activity_flags(monthly)
    joined=predictions.merge(flags,on=["category","month"],how="left",validate="many_to_one")
    if joined.avg_players.isna().any() or not np.allclose(joined.actual,joined.avg_players):
        raise ValueError("Forecast actuals differ from source activity")
    joined["absolute_error"]=joined.error.abs()
    joined["lead_window"]=np.where(joined.lead.le(15),"Leads 1–15","Leads 16–27")
    bias=joined.groupby(["category","model","lead_window"],as_index=False).agg(mae=("absolute_error","mean"),mean_error=("error","mean"),underprediction_pct=("error",lambda x:100*x.gt(0).mean()),overprediction_pct=("error",lambda x:100*x.lt(0).mean()),scored_rows=("error","size"))
    long=joined.loc[joined.lead.ge(16)]
    folds=long.groupby(["category","origin","model"],as_index=False).agg(mae=("absolute_error","mean"),mean_error=("error","mean"))
    reference=folds.loc[folds.model.eq("Last value"),["category","origin","mae"]].rename(columns={"mae":"last_value_mae"})
    folds=folds.merge(reference,on=["category","origin"],validate="many_to_one")
    folds["improvement_vs_last_value_pct"]=100*(folds.last_value_mae-folds.mae)/folds.last_value_mae.where(folds.last_value_mae.ne(0))
    folds["beats_last_value"]=folds.mae.lt(folds.last_value_mae-1e-6)
    stability=folds.groupby(["category","model"],as_index=False).agg(mean_fold_mae=("mae","mean"),worst_fold_mae=("mae","max"),best_fold_mae=("mae","min"),wins_vs_last_value=("beats_last_value","sum"),folds=("origin","nunique"))
    largest=joined.sort_values("absolute_error",ascending=False).groupby(["category","model"],group_keys=False).head(3)
    return flags,bias,folds,stability,largest

def run():
    path=ROOT/"reports/model_comparison/predictions.csv"
    monthly_path=ROOT/"reports/exploration_monthly.csv"
    manifest=json.loads((ROOT/"reports/model_comparison/manifest.json").read_text())
    if hashlib.sha256(monthly_path.read_bytes()).hexdigest()!=manifest["input_sha256"]:
        raise ValueError("Forecast/source lineage mismatch")
    frames=diagnose(pd.read_csv(path),pd.read_csv(monthly_path))
    folder=ROOT/"reports/model_diagnostics";folder.mkdir(exist_ok=True)
    for name,frame in zip(["activity_flags","bias","fold_comparisons","stability","largest_errors"],frames):frame.to_csv(folder/f"{name}.csv",index=False)
    (folder/"manifest.json").write_text(json.dumps({"predictions_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"activity_sha256":manifest["input_sha256"],"flag_rule":"Absolute robust z >3.5 on monthly fractional changes; median/MAD from previous24 changes; minimum12; unknown with undefined scale","scope":"Exploratory retrospective diagnostics; no rows removed, no alert evaluation, no final selection"},indent=2)+"\n",encoding="utf-8")
    return frames

if __name__=="__main__":
    _,_,_,stability,_=run()
    print(stability.to_string(index=False))

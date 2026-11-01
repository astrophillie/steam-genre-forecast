"""Exploratory historical-error bands with past-only calibration checks."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
try:
    from .audit_validation import validate_predictions, require_lineage, require_same_targets
except ImportError:
    from audit_validation import validate_predictions, require_lineage, require_same_targets
ROOT=Path(__file__).resolve().parents[1]
ROUTES={"Action":("base","Last value"),"Indie":("base","Gradient boosting"),"Massively Multiplayer":("base","Last value"),"RPG":("tuned","Chronologically tuned boosting"),"Strategy":("features","Recent changes")}

def error_radius(history,cutoff,quantile=.9,min_rows=12):
    if not 0<quantile<1 or isinstance(min_rows,bool) or not isinstance(min_rows,int) or min_rows<1:raise ValueError("Invalid calibration settings")
    if not {"month","origin","lead","error"}<=set(history):raise ValueError("Missing calibration fields")
    if not np.isfinite(pd.to_numeric(history.error,errors="raise")).all():raise ValueError("Invalid calibration errors")
    if history.duplicated(["origin","month"]).any():raise ValueError("Duplicate calibration observations")
    available=history.loc[history.month.le(pd.Timestamp(cutoff)) & history.origin.lt(pd.Timestamp(cutoff)) & history.lead.between(16,27)]
    if len(available)<min_rows:return np.nan,len(available)
    return float(np.quantile(available.error.abs(),quantile,method="higher")),len(available)

def run():
    sources={"base":ROOT/"reports/model_comparison/predictions.csv","tuned":ROOT/"reports/tuning/predictions.csv","features":ROOT/"reports/feature_experiments/predictions.csv"}
    activity=ROOT/"reports/exploration_monthly.csv"
    for folder,field in [("reports/model_comparison","input_sha256"),("reports/feature_experiments","input_sha256"),("reports/tuning","source_sha256")]:
        require_lineage(ROOT,folder,activity,field)
    tables={key:validate_predictions(pd.read_csv(path,parse_dates=["month","origin"])) for key,path in sources.items()}
    require_same_targets(tables["base"],tables["features"])
    require_same_targets(tables["base"].loc[tables["base"].category.isin(tables["tuned"].category.unique())],tables["tuned"])
    try:
        from .project_2027 import run as verify_frozen
    except ImportError:
        from project_2027 import run as verify_frozen
    verify_frozen()
    history=pd.concat([tables[key].loc[tables[key].category.eq(category)&tables[key].model.eq(model)] for category,(key,model) in ROUTES.items()],ignore_index=True)
    if history.duplicated(["category","origin","month"]).any():raise ValueError("Repeated policy history")
    if set(history.category)!=set(ROUTES) or any(len(group)!=108 or group.origin.nunique()!=4 for _,group in history.groupby("category")):
        raise ValueError("Incomplete frozen-policy calibration inventory")
    checks=[];bands=[]
    for category,group in history.groupby("category"):
        for origin in sorted(group.origin.unique()):
            radius,count=error_radius(group,origin)
            target=group.loc[group.origin.eq(origin)&group.lead.between(16,27)].copy()
            target["radius"]=radius;target["calibration_rows"]=count
            target["lower"]=np.maximum(target.prediction-radius,0)
            target["upper"]=target.prediction+radius
            target["covered"]=pd.Series(pd.NA,index=target.index,dtype="boolean")
            if np.isfinite(radius):target["covered"]=target.actual.between(target.lower,target.upper)
            checks.append(target)
        radius,count=error_radius(group,"2025-09-01")
        bands.append({"category":category,"radius":radius,"calibration_rows":count})
    checks=pd.concat(checks,ignore_index=True)
    evaluated=checks.loc[checks.radius.notna()]
    coverage=evaluated.groupby("category",as_index=False).agg(coverage_pct=("covered",lambda x:100*x.mean()),evaluated_rows=("covered","size"),origins=("origin","nunique"),mean_width=("upper",lambda x:0.))
    widths=evaluated.assign(width=evaluated.upper-evaluated.lower).groupby("category").width.mean()
    coverage["mean_width"]=coverage.category.map(widths)
    projection_path=ROOT/"reports/forecast_2027/monthly_projections.csv"
    projection=pd.read_csv(projection_path)
    target=projection.loc[projection.policy.eq("Provisional development policy")&projection.month.between("2027-01-01","2027-12-01")].merge(pd.DataFrame(bands),on="category",validate="many_to_one")
    target["lower"]=np.maximum(target.prediction-target.radius,0);target["upper"]=target.prediction+target.radius
    annual=pd.read_csv(ROOT/"reports/forecast_2027/annual_summary.csv")
    sensitivity=annual.pivot(index="category",columns="policy",values="projected_mean_activity").reset_index()
    sensitivity["difference_pct"]=100*(sensitivity["Provisional development policy"]/sensitivity["Last-value reference"]-1)
    folder=ROOT/"reports/forecast_uncertainty";folder.mkdir(exist_ok=True)
    for name,frame in [("historical_band_checks",checks),("coverage",coverage),("monthly_error_bands",target),("policy_sensitivity",sensitivity)]:frame.to_csv(folder/f"{name}.csv",index=False)
    manifest={"method":"Symmetric empirical90th-percentile absolute long-lead errors, higher quantile; lower bound clipped at zero","minimum_calibration_rows":12,"calibration_cutoff":"2025-09-01","projection_sha256":hashlib.sha256(projection_path.read_bytes()).hexdigest(),"history_hashes":{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in sources.items()},"scope":"Exploratory historical-error bands; dependent overlapping development folds; no calibrated90% guarantee, no annual confidence interval or ranking probability"}
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return coverage,sensitivity,target

if __name__=="__main__":
    coverage,sensitivity,_=run();print(coverage.to_string(index=False));print(sensitivity.round(2).to_string(index=False))

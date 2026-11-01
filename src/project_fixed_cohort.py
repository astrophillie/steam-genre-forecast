"""Provisional 2027 projections for the frozen covered cohort, version 2."""
from pathlib import Path
import hashlib
import json
import sqlite3
import numpy as np
import pandas as pd
try:
    from .baselines import validate_series, forecast_baselines
    from .statistical_models import forecast_statistical, CONFIGS
    from .audit_validation import validate_predictions, require_same_targets
except ImportError:
    from baselines import validate_series, forecast_baselines
    from statistical_models import forecast_statistical, CONFIGS
    from audit_validation import validate_predictions, require_same_targets

ROOT = Path(__file__).resolve().parents[1]
POLICY = {"Action":"Last value", "Indie":"Seasonal naive", "Massively Multiplayer":"Last value", "RPG":"Damped seasonal", "Strategy":"Damped seasonal"}
CUTOFF = pd.Timestamp("2026-01-01")
HORIZON = 23
LABEL = "Provisional v2 policy"
REFERENCE = "Last-value reference"


def historical_error_ranges(predictions):
    """Collapse repeated target months using the worst absolute policy error."""
    data = validate_predictions(predictions)
    require_same_targets(data, data)
    rows=[]
    for category, model in POLICY.items():
        chosen=data.loc[data.category.eq(category)&data.model.eq(model)&data.lead.between(12,23)]
        if len(chosen)!=24 or chosen.origin.nunique()!=2 or chosen.month.gt(CUTOFF).any():
            raise ValueError("Expected two complete historical target windows through cutoff")
        grouped=chosen.assign(absolute_error=lambda x:x.error.abs()).groupby("month").absolute_error.max()
        if len(grouped)!=13:
            raise ValueError("Expected thirteen unique target months")
        rows.append({"category":category,"model":model,"radius":float(np.quantile(grouped,0.9,method="higher")),"forecast_cases":len(chosen),"unique_target_months":len(grouped),"origins":chosen.origin.nunique()})
    return pd.DataFrame(rows)


def project(monthly):
    data=monthly.copy();data["month"]=pd.to_datetime(data.month,errors="raise")
    if set(data.category)!=set(POLICY) or data.duplicated(["category","month"]).any():
        raise ValueError("Expected fixed five-category inventory")
    rows=[];fits=[]
    dates=pd.date_range("2026-02-01","2027-12-01",freq="MS")
    for category,model in POLICY.items():
        train=data.loc[data.category.eq(category)].set_index("month").avg_players.sort_index()
        validate_series(train)
        if not train.index.equals(pd.date_range("2021-02-01",CUTOFF,freq="MS")):
            raise ValueError("Expected sixty fixed training months ending January 2026")
        baselines=forecast_baselines(train,HORIZON)
        info={"clipped_predictions":0}
        if model in baselines: values=baselines[model]
        else: values,info=forecast_statistical(train,HORIZON,model)
        fits.append({"category":category,"model":model,"training_months":len(train),**info})
        for label,selected,prediction in [(LABEL,model,values),(REFERENCE,"Last value",baselines["Last value"])]:
            rows.append(pd.DataFrame({"category":category,"policy":label,"model":selected,"month":dates,"lead":np.arange(1,HORIZON+1),"prediction":prediction}))
    result=pd.concat(rows,ignore_index=True)
    if len(result)!=230 or not np.isfinite(result.prediction).all() or result.prediction.lt(0).any():
        raise ValueError("Invalid projection grid or activity")
    return result,pd.DataFrame(fits)


def verify_diagnostic_evidence(folder, pins):
    folder=Path(folder)
    if not pins or set(pins)!={p.name for p in folder.glob("*.csv")}:
        raise ValueError("Diagnostic evidence inventory changed")
    for name,expected in pins.items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=expected:
            raise ValueError("Diagnostic evidence changed after forecast freeze")


def run(root=ROOT):
    root=Path(root);digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    scope_path=root/"config/project_scope.json"
    scope=json.loads(scope_path.read_text(encoding="utf-8"))
    if scope["active_dataset"]!="fixed_sources_v2" or scope["training_cutoff"]!=str(CUTOFF.date()) or scope["forecast_horizon"]!=HORIZON or scope["target_leads"]!=[12,23]:
        raise ValueError("Fixed projection scope changed")
    source=root/scope["category_input"]; registry=root/scope["source_registry"]
    evaluation=root/"reports/fixed_cohort_evaluation"
    manifest=json.loads((evaluation/"manifest.json").read_text(encoding="utf-8"))
    for field,path in [("input_sha256",source),("registry_sha256",registry),("scope_sha256",scope_path),("predictions_sha256",evaluation/"predictions.csv")]:
        if manifest.get(field)!=digest(path):raise ValueError("Stale evaluation lineage")
    diagnostics=root/"reports/fixed_cohort_diagnostics/manifest.json"
    diagnostic_manifest=json.loads(diagnostics.read_text(encoding="utf-8"))
    if diagnostic_manifest["predictions_sha256"]!=digest(evaluation/"predictions.csv") or diagnostic_manifest["evaluation_manifest_sha256"]!=digest(evaluation/"manifest.json") or diagnostic_manifest["database_sha256"]!=digest(root/scope["database"]):
        raise ValueError("Stale error review")
    monthly=pd.read_csv(source)
    connection=sqlite3.connect((root/scope["database"]).resolve().as_uri()+"?mode=ro",uri=True)
    try: database=pd.read_sql_query("SELECT * FROM category_monthly",connection)
    finally: connection.close()
    columns=["category","month","avg_players","observed_apps"]
    pd.testing.assert_frame_equal(monthly[columns].sort_values(columns[:2]).reset_index(drop=True),database[columns].sort_values(columns[:2]).reset_index(drop=True),check_dtype=False,rtol=1e-12,atol=1e-7)
    frozen={"version":"fixed_cohort_forecast_v2","cutoff":str(CUTOFF.date()),"horizon":HORIZON,"target_year":2027,"cohort_apps":519,"routes":POLICY,"statistical_config":CONFIGS["Damped seasonal"],"input_sha256":digest(source),"registry_sha256":digest(registry),"evaluation_manifest_sha256":digest(evaluation/"manifest.json"),"diagnostics_manifest_sha256":digest(diagnostics),"status":"Provisional retrospective development policy; no independent holdout", "reasons":{"Action":"Negligible smoothing gain and cutoff sensitivity","Indie":"Seasonal reference improves both folds","Massively Multiplayer":"Small aggregate smoothing gain hides unstable ranks and underprediction","RPG":"Seasonal smoothing leads both folds, gains vary","Strategy":"Seasonal smoothing leads both folds"},"range_method":"90th percentile (higher) of worst absolute error per unique target month, leads12–23;13 dependent development months; symmetric radius, lower clipped at zero; not a calibrated predictive interval"}
    out=root/"reports/fixed_cohort_forecast_2027"
    freeze_path=out/"frozen_policy.json"
    if freeze_path.exists() and json.loads(freeze_path.read_text(encoding="utf-8"))!=frozen:
        raise ValueError("Frozen policy or inputs changed; use a new forecast version")
    existing_manifest=out/"manifest.json"
    previous=None
    if existing_manifest.exists():
        previous=json.loads(existing_manifest.read_text(encoding="utf-8"))
        verify_diagnostic_evidence(root/"reports/fixed_cohort_diagnostics", previous.get("diagnostic_outputs", {}))
        if not freeze_path.exists() or previous["policy_sha256"]!=digest(freeze_path):
            raise ValueError("Frozen policy fingerprint mismatch")
        for name,expected in previous["outputs"].items():
            if not (out/name).exists() or digest(out/name)!=expected:
                raise ValueError("Frozen forecast output changed")
    predictions,fits=project(monthly)
    history=validate_predictions(pd.read_csv(evaluation/"predictions.csv"))
    radii=historical_error_ranges(history)
    target=predictions.loc[predictions.policy.eq(LABEL)&predictions.lead.between(12,23)].merge(radii,on=["category","model"],validate="many_to_one")
    target["historical_error_lower"]=np.maximum(target.prediction-target.radius,0.)
    target["historical_error_upper"]=target.prediction+target.radius
    annual=predictions.loc[predictions.month.dt.year.eq(2027)].groupby(["category","policy","model"],as_index=False).agg(projected_mean_activity=("prediction","mean"),months=("month","nunique"))
    if len(annual)!=10 or not annual.months.eq(12).all():raise ValueError("Incomplete 2027 target year")
    annual["rank"]=annual.groupby("policy").projected_mean_activity.rank(method="min",ascending=False).astype(int)
    comparison=annual.pivot(index="category",columns="policy",values="projected_mean_activity").reset_index()
    comparison["difference_pct"]=100*(comparison[LABEL]/comparison[REFERENCE].replace(0,np.nan)-1)
    out.mkdir(exist_ok=True)
    outputs={"monthly_projections":predictions,"annual_summary":annual,"baseline_comparison":comparison,"monthly_historical_error_ranges":target,"historical_error_radii":radii,"fit_diagnostics":fits}
    if previous:
        for name,frame in outputs.items():
            reproduced=hashlib.sha256(frame.to_csv(index=False).encode("utf-8")).hexdigest()
            if reproduced!=previous["outputs"].get(name+".csv"):
                raise ValueError("Forecast reproduction changed; preserve this version")
    for name,frame in outputs.items():frame.to_csv(out/f"{name}.csv",index=False)
    freeze_path.write_text(json.dumps(frozen,indent=2)+"\n",encoding="utf-8")
    record={"policy_sha256":digest(freeze_path),"outputs":{name+".csv":digest(out/(name+".csv")) for name in outputs},"range_status":"Uncalibrated development-error sensitivity; no annual interval or ranking probability", "coverage_check":"Unavailable: neither 2024 origin has earlier matured lead12–23 errors from these folds for past-only calibration", "scope":"January2026-cutoff fixed519-game cohort projection; excludes future releases and untracked games; later archive data excluded"}
    record["diagnostic_outputs"]={path.name:digest(path) for path in sorted((root/"reports/fixed_cohort_diagnostics").glob("*.csv"))}
    (out/"manifest.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
    return outputs


if __name__=="__main__":
    results=run()
    print(results["annual_summary"].sort_values(["policy","rank"]).to_string(index=False))
    print(results["baseline_comparison"].round(2).to_string(index=False))

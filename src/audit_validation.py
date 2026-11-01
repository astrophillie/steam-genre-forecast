"""Fail-closed validation for forecast reports and source lineage."""
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd

def require_lineage(root,folder,source,field="input_sha256"):
    manifest=json.loads((Path(root)/folder/"manifest.json").read_text(encoding="utf-8"))
    expected=hashlib.sha256(Path(source).read_bytes()).hexdigest()
    if manifest.get(field)!=expected:raise ValueError(f"Stale report/source lineage: {folder}")
    return manifest

def validate_predictions(frame):
    required={"category","model","origin","lead","actual","prediction","error"}
    if frame.empty or not required<=set(frame):raise ValueError("Forecast rows and required fields must be present")
    data=frame.copy()
    for column in ["category","model"]:
        if not data[column].map(lambda x:isinstance(x,str) and bool(x.strip())).all():raise ValueError("Missing category/model label")
    for column in ["lead","actual","prediction","error"]:
        data[column]=pd.to_numeric(data[column],errors="raise").astype(float)
        if not np.isfinite(data[column].to_numpy(dtype=float)).all():raise ValueError("Nonfinite forecast field")
    if not data.lead.between(1,27).all() or not data.lead.mod(1).eq(0).all():raise ValueError("Forecast leads must be integers from1 to27")
    if (data.actual.lt(0)|data.prediction.lt(0)).any():raise ValueError("Negative activity")
    data["origin"]=pd.to_datetime(data.origin,errors="raise")
    if data.origin.isna().any() or not data.origin.dt.is_month_start.all():raise ValueError("Invalid origin")
    keys=["category","model","origin","lead"]
    if data.duplicated(keys).any():raise ValueError("Repeated forecast key")
    with np.errstate(over="raise",invalid="raise"):
        try: residual=data.actual.to_numpy()-data.prediction.to_numpy()
        except FloatingPointError as error:raise ValueError("Unrepresentable forecast residual") from error
    if not np.allclose(residual,data.error,rtol=1e-10,atol=1e-7):raise ValueError("Forecast errors do not reconcile")
    if "month" in data:
        data["month"]=pd.to_datetime(data.month,errors="raise")
        if data.month.isna().any() or not data.month.dt.is_month_start.all():raise ValueError("Invalid target month")
        elapsed=(data.month.dt.year-data.origin.dt.year)*12+data.month.dt.month-data.origin.dt.month
        if not elapsed.eq(data.lead).all():raise ValueError("Target date and lead disagree")
    expected=list(range(1,int(data.lead.max())+1))
    for _,group in data.groupby(["category","model","origin"]):
        if sorted(group.lead.astype(int))!=expected:raise ValueError("Incomplete per-model forecast horizon")
    return data

def require_same_targets(left,right):
    keys=["category","origin","month","lead"]
    left=validate_predictions(left);right=validate_predictions(right)
    for frame in [left,right]:
        expected=pd.MultiIndex.from_product([sorted(frame.category.unique()),sorted(frame.model.unique()),sorted(frame.origin.unique())])
        observed=pd.MultiIndex.from_frame(frame[["category","model","origin"]].drop_duplicates())
        if len(expected.difference(observed)):raise ValueError("Missing category/model/origin combination")
    a=left[keys+["actual"]].drop_duplicates()
    b=right[keys+["actual"]].drop_duplicates()
    if a.duplicated(keys).any() or b.duplicated(keys).any():raise ValueError("Models disagree on observed actuals")
    joined=a.merge(b,on=keys,how="outer",suffixes=("_left","_right"),validate="one_to_one",indicator=True)
    if not joined["_merge"].eq("both").all() or not np.allclose(joined.actual_left,joined.actual_right,rtol=1e-12,atol=1e-8):raise ValueError("Forecast targets or fold inventory differ")

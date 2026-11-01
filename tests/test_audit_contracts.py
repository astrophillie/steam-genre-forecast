"""Adversarial contracts for scoring, inference summaries and artifact lineage."""
import json
import hashlib
import numpy as np
import pandas as pd
import pytest
from src.baselines import score_forecasts
from src.project_2027 import annual_summary
from src.gradient_boosting import feature_row

def forecasts():
    return pd.DataFrame({"category":"Example","model":"Last value","origin":"2020-01-01","lead":range(1,28),"actual":10.,"prediction":9.,"error":1.})

@pytest.mark.parametrize("column,value",[("actual",np.nan),("prediction",np.inf),("error",np.nan),("actual",-1),("lead",1.5)])
def test_scoring_rejects_corrupt_values(column,value):
    data=forecasts();data[column]=value
    with pytest.raises(ValueError):score_forecasts(data)

def test_scoring_rejects_duplicates_and_empty():
    data=forecasts()
    with pytest.raises(ValueError):score_forecasts(pd.concat([data,data]))
    with pytest.raises(ValueError):score_forecasts(data.iloc[:0])

def test_scoring_detects_stale_errors():
    data=forecasts();data["prediction"]=8.
    with pytest.raises(ValueError):score_forecasts(data)

def test_metrics_do_not_overflow_on_representable_extremes():
    data=forecasts();data["actual"]=0.;data["prediction"]=1e200;data["error"]=-1e200
    result=score_forecasts(data)
    assert np.isfinite(result.rmse).all()
    assert result.rmse.iloc[0]==pytest.approx(1e200)

def test_perfect_predictions_have_zero_regression_loss():
    data=forecasts();data["prediction"]=data.actual;data["error"]=0.
    scores=score_forecasts(data)
    assert scores.mae.eq(0).all() and scores.rmse.eq(0).all()
    assert score_forecasts(forecasts()).mae.gt(0).all()

def annual():
    return pd.DataFrame({"category":"Example","policy":"Example","month":pd.date_range("2027-01-01",periods=12,freq="MS").strftime("%Y-%m-%d"),"prediction":10.})

@pytest.mark.parametrize("value",[np.nan,np.inf,-1.,"invalid"])
def test_annual_summary_rejects_invalid_predictions(value):
    data=annual();data["prediction"]=value
    with pytest.raises(ValueError):annual_summary(data)

def test_annual_summary_rejects_empty_and_invalid_calendar():
    with pytest.raises(ValueError):annual_summary(annual().iloc[:0])
    data=annual();data["month"]=pd.date_range("2027-01-02",periods=12,freq="MS").strftime("%Y-%m-%d")
    with pytest.raises(ValueError):annual_summary(data)

def test_annual_summary_accepts_datetime_months():
    data=annual();data["month"]=pd.to_datetime(data.month)
    assert annual_summary(data).months.eq(12).all()

@pytest.mark.parametrize("history",[np.ones((12,2)),np.full(12,1e308),np.ones(11),np.array([np.nan]*12)])
def test_feature_generation_fails_closed_on_bad_or_overflowing_history(history):
    with pytest.raises(ValueError):feature_row(history,"2027-01-01")


def test_report_lineage_and_per_model_completeness(tmp_path):
    from src.audit_validation import require_lineage,require_same_targets
    source=tmp_path/"source.csv";source.write_text("original")
    folder=tmp_path/"report";folder.mkdir()
    (folder/"manifest.json").write_text(json.dumps({"input_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}))
    require_lineage(tmp_path,"report",source)
    source.write_text("changed")
    with pytest.raises(ValueError,match="lineage"):require_lineage(tmp_path,"report",source)
    data=forecasts();data["month"]=pd.date_range("2020-02-01",periods=27,freq="MS")
    second=data.copy();second["model"]="Other"
    combined=pd.concat([data,second],ignore_index=True)
    with pytest.raises(ValueError,match="horizon"):
        require_same_targets(combined,combined.iloc[:-1])
    changed=data.copy();changed["actual"]+=1;changed["error"]+=1
    with pytest.raises(ValueError,match="targets"):
        require_same_targets(data,changed)

def test_frozen_projection_rejects_missing_checksum_inventory(tmp_path,monkeypatch):
    from src import project_2027 as module
    root=tmp_path;folder=root/"reports/forecast_2027";folder.mkdir(parents=True)
    source=root/"reports/exploration_monthly.csv";source.write_text("data")
    manifest={"policy":module.POLICY,"input_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
    (folder/"frozen_policy.json").write_text(json.dumps(manifest))
    (folder/"checksums.json").write_text("{}")
    monkeypatch.setattr(module,"ROOT",root)
    with pytest.raises(ValueError,match="inventory"):module.run()

def test_tuning_rejects_incomplete_outer_outcomes_before_search(tmp_path,monkeypatch):
    from src import tune_candidates as module
    folder=tmp_path/"reports";folder.mkdir()
    dates=pd.date_range("2012-07-01",periods=159,freq="MS")
    data=pd.concat([pd.DataFrame({"category":category,"month":dates,"avg_players":np.arange(159)+100.}) for category in module.SHORTLIST])
    data=data.loc[~(data.category.eq("RPG") & data.month.eq(dates[-1]))]
    data.to_csv(folder/"exploration_monthly.csv",index=False)
    monkeypatch.setattr(module,"ROOT",tmp_path)
    with pytest.raises(ValueError,match="evaluation months"):module.run()


def test_unsigned_residual_wrap_cannot_bypass_reconciliation():
    data=forecasts()
    data["actual"]=np.uint64(0);data["prediction"]=np.uint64(2)
    data["error"]=np.uint64(2**64-2)
    with pytest.raises(ValueError,match="reconcile"):score_forecasts(data)

def test_integer_minimum_error_cannot_produce_negative_loss():
    data=forecasts()
    data["actual"]=np.int64(0);data["prediction"]=np.uint64(2**63)
    data["error"]=np.int64(-(2**63))
    scores=score_forecasts(data)
    assert scores.mae.gt(0).all() and scores.rmse.gt(0).all()
    assert scores.mae.iloc[0]==pytest.approx(float(2**63))

def test_installed_boosting_squared_loss_and_gradients():
    from sklearn.ensemble import GradientBoostingRegressor
    estimator=GradientBoostingRegressor(n_estimators=1,max_depth=1,random_state=42).fit([[0],[1],[2]],[0.,1.,2.])
    loss=estimator._loss
    truth=np.array([0.,2.]);perfect=truth.copy();wrong=np.array([1.,1.])
    exact,gradient=loss.loss_gradient(y_true=truth,raw_prediction=perfect)
    assert np.all(exact==0) and np.all(gradient==0)
    values,gradient=loss.loss_gradient(y_true=truth,raw_prediction=wrong)
    assert np.all(values>0) and np.isfinite(gradient).all()
    eps=1e-6
    numerical=(loss.loss(y_true=truth,raw_prediction=wrong+eps)-loss.loss(y_true=truth,raw_prediction=wrong-eps))/(2*eps)
    np.testing.assert_allclose(gradient,numerical,rtol=1e-6,atol=1e-8)


def test_unconverged_statistical_fit_is_rejected(monkeypatch):
    from src import statistical_models as module
    class FailedFit:
        mle_retvals={"success":False}
        def forecast(self,horizon):return np.ones(horizon)
    class FakeEstimator:
        def __init__(self,*args,**kwargs):pass
        def fit(self,**kwargs):return FailedFit()
    monkeypatch.setattr(module,"ExponentialSmoothing",FakeEstimator)
    train=pd.Series(np.arange(36)+1.,index=pd.date_range("2020-01-01",periods=36,freq="MS"))
    with pytest.raises(ValueError,match="converge"):
        module.forecast_statistical(train,27,"SES")

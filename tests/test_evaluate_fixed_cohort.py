import numpy as np
import pandas as pd
import pytest
from src.evaluate_fixed_cohort import evaluate, summarise
from src.evaluate_fixed_cohort import run
import json
import sqlite3


def sample():
    dates = pd.date_range('2021-02-01',periods=60,freq='MS')
    return pd.DataFrame({'category':'Test','month':dates,'avg_players':100+np.arange(60)+5*np.sin(np.arange(60))})


def test_future_actuals_cannot_change_forecasts():
    data=sample()
    first, _=evaluate(data, origins=['2024-01-01'])
    data.loc[data.month.gt('2024-01-01'),'avg_players']*=20
    second, _=evaluate(data, origins=['2024-01-01'])
    np.testing.assert_array_equal(first.prediction,second.prediction)
    assert not np.array_equal(first.actual,second.actual)
    assert len(first)==6*23


@pytest.mark.parametrize('problem',['gap','duplicate','negative','short','missing_outcome'])
def test_invalid_evaluation_rejected(problem):
    data=sample()
    if problem=='gap': data=data.drop(4)
    if problem=='duplicate': data=pd.concat([data,data.iloc[[0]]])
    if problem=='negative': data.loc[0,'avg_players']=-1
    if problem=='short': data=data.iloc[1:]
    if problem=='missing_outcome': data=data.iloc[:-1]
    with pytest.raises(ValueError): evaluate(data)


def test_metric_window_and_bias_independently():
    dates=pd.date_range('2024-02-01',periods=23,freq='MS')
    rows=[]
    for model,predicted in [('Last value',90.),('Better',95.)]:
        rows.append(pd.DataFrame({'category':'Test','model':model,'origin':pd.Timestamp('2024-01-01'),'month':dates,'lead':np.arange(1,24),'actual':100.,'prediction':predicted,'error':100.-predicted}))
    folds,scores=summarise(pd.concat(rows))
    best=folds.loc[folds.model.eq('Better') & folds.window.eq('Leads 12 to 23')].iloc[0]
    assert best.observations==12
    assert best.mae==best.rmse==best.mean_error==5
    assert best.wape_pct==5
    assert best.skill_vs_last_value_pct==50
    assert scores.loc[scores.model.eq('Better'),'wins_vs_last_value'].eq(1).all()
    with pytest.raises(ValueError): summarise(pd.concat(rows).loc[lambda x:x.model.eq('Better')])
    with pytest.raises(ValueError): summarise(pd.concat(rows).loc[lambda x:x.lead.le(22)])


def test_changed_csv_rejected_before_modelling(tmp_path):
    (tmp_path/'config').mkdir()
    scope={'active_dataset':'fixed_sources_v2','forecast_horizon':23,'target_leads':[12,23], 'category_input':'category.csv','source_registry':'registry.json','database':'test.sqlite'}
    (tmp_path/'config/project_scope.json').write_text(json.dumps(scope))
    (tmp_path/'registry.json').write_text(json.dumps({'cohort_apps':519,'modelling_cutoff':'2026-01-01','window_start':'2021-02-01'}))
    data=sample().assign(observed_apps=10)
    data['month']=data.month.dt.strftime('%Y-%m-%d')
    with sqlite3.connect(tmp_path/'test.sqlite') as connection:
        data.to_sql('category_monthly',connection,index=False)
    data.loc[0,'avg_players']+=100
    data.to_csv(tmp_path/'category.csv',index=False)
    with pytest.raises(AssertionError): run(tmp_path)


@pytest.mark.parametrize("actual,prediction,expected_wape", [(0.,1e200,None),(0.,1e154,None),(1e308,5e307,50.)])
def test_extreme_finite_v2_metrics_stay_representable(actual,prediction,expected_wape):
    frame=pd.DataFrame({"category":"Test","model":"Last value","origin":pd.Timestamp("2024-01-01"),"month":pd.date_range("2024-02-01",periods=23,freq="MS"),"lead":np.arange(1,24),"actual":actual,"prediction":prediction,"error":actual-prediction})
    folds,scores=summarise(frame)
    assert np.isfinite(folds[["mae","rmse","mean_error"]]).all().all()
    assert folds.rmse.iloc[0]==pytest.approx(abs(actual-prediction))
    if expected_wape is not None:assert folds.wape_pct.iloc[0]==pytest.approx(expected_wape)


def test_extreme_finite_fold_average_does_not_overflow():
    frames=[]
    for origin in ["2024-01-01","2024-02-01"]:
        frames.append(pd.DataFrame({"category":"Test","model":"Last value","origin":pd.Timestamp(origin),"month":pd.date_range(pd.Timestamp(origin)+pd.offsets.MonthBegin(),periods=23,freq="MS"),"lead":np.arange(1,24),"actual":1e308,"prediction":0.,"error":1e308}))
    folds,scores=summarise(pd.concat(frames,ignore_index=True))
    assert np.isfinite(scores[["mae","rmse","mean_error","wape_pct"]]).all().all()
    assert scores.mae.iloc[0]==pytest.approx(1e308)

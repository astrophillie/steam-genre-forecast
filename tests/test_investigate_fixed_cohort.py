import numpy as np
import pandas as pd
import pytest
from src.investigate_fixed_cohort import app_contributions, cutoff_sensitivity
from src.investigate_fixed_cohort import run
import hashlib
import json


def panel():
    return pd.DataFrame({'category':['Test']*6,'app_id':[1,1,1,2,2,2],'name':['One']*3+['Two']*3,
                         'month':pd.to_datetime(['2024-01-01','2024-02-01','2025-02-01']*2),
                         'avg_players':[10.,20.,40.,30.,40.,50.]})


def test_exact_baseline_decomposition_and_share():
    result=app_contributions(panel(),'Test','2024-01-01','2025-02-01')
    assert result.change_since_origin.sum()==90-40
    assert result.year_over_year_change.sum()==90-60
    assert result.target_share_pct.sum()==pytest.approx(100)
    assert result.loc[result.app_id.eq(1),'change_since_origin'].iloc[0]==30


@pytest.mark.parametrize('issue',['gap','duplicate','negative'])
def test_bad_contributions_rejected(issue):
    data=panel()
    if issue=='gap':data=data.drop(0)
    if issue=='duplicate':data=pd.concat([data,data.iloc[[0]]])
    if issue=='negative':data.loc[0,'avg_players']=-1
    with pytest.raises(ValueError):app_contributions(data,'Test','2024-01-01','2025-02-01')


def test_cutoff_comparison_aligns_calendar_not_lead():
    rows=[]
    for origin,prediction in [('2024-01-01',90.),('2024-02-01',95.)]:
        rows.append(pd.DataFrame({'category':'Test','model':'Last value','origin':pd.Timestamp(origin),
            'month':pd.date_range(pd.Timestamp(origin)+pd.offsets.MonthBegin(),periods=23,freq='MS'),
            'lead':np.arange(1,24),'actual':100.,'prediction':prediction,'error':100.-prediction}))
    result=cutoff_sensitivity(pd.concat(rows)).iloc[0]
    assert result.shared_months==11
    assert result.average_forecast_shift==5
    assert result.first_cutoff_mae==10
    assert result.second_cutoff_mae==5


def test_prediction_tampering_stops_before_diagnostics(tmp_path):
    (tmp_path/'config').mkdir()
    folder=tmp_path/'reports/fixed_cohort_evaluation';folder.mkdir(parents=True)
    scope={'category_input':'category.csv','source_registry':'registry.json'}
    (tmp_path/'config/project_scope.json').write_text(json.dumps(scope))
    (tmp_path/'category.csv').write_text('original input')
    (tmp_path/'registry.json').write_text('original registry')
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest={'input_sha256':digest(tmp_path/'category.csv'),'registry_sha256':digest(tmp_path/'registry.json'),'scope_sha256':digest(tmp_path/'config/project_scope.json'),'predictions_sha256':hashlib.sha256(b'original predictions').hexdigest()}
    (folder/'manifest.json').write_text(json.dumps(manifest))
    (folder/'predictions.csv').write_text('modified predictions')
    with pytest.raises(ValueError,match='predictions changed'):run(tmp_path)

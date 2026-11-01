import numpy as np
import pandas as pd
import pytest
from src.project_fixed_cohort import POLICY, project, historical_error_ranges, LABEL, REFERENCE


def monthly():
    return pd.concat([pd.DataFrame({'category':category,'month':pd.date_range('2021-02-01',periods=60,freq='MS'),'avg_players':100.}) for category in POLICY],ignore_index=True)


def test_projection_calendar_and_baseline():
    predictions,fits=project(monthly())
    assert len(predictions)==230
    assert predictions.month.min()==pd.Timestamp('2026-02-01')
    assert predictions.month.max()==pd.Timestamp('2027-12-01')
    target=predictions.loc[predictions.month.dt.year.eq(2027)]
    assert len(target)==120
    assert set(target.lead)==set(range(12,24))
    np.testing.assert_allclose(predictions.prediction,100,atol=1e-4)
    assert fits.training_months.eq(60).all()


@pytest.mark.parametrize('problem',['future','gap','duplicate','negative'])
def test_invalid_training_window_rejected(problem):
    data=monthly()
    if problem=='future':data=pd.concat([data,pd.DataFrame({'category':['Action'],'month':[pd.Timestamp('2026-02-01')],'avg_players':[100.]})])
    if problem=='gap':data=data.drop(0)
    if problem=='duplicate':data=pd.concat([data,data.iloc[[0]]])
    if problem=='negative':data.loc[0,'avg_players']=-1
    with pytest.raises(ValueError):project(data)


def test_ranges_count_unique_targets_and_use_worst_duplicate():
    frames=[]
    for category,model in POLICY.items():
        for origin,err in [('2024-01-01',10.),('2024-02-01',20.)]:
            frames.append(pd.DataFrame({'category':category,'model':model,'origin':pd.Timestamp(origin),'month':pd.date_range(pd.Timestamp(origin)+pd.offsets.MonthBegin(),periods=23,freq='MS'),'lead':np.arange(1,24),'actual':100.,'prediction':100.-err,'error':err}))
    # Policy models differ across categories; this helper validates each selected
    # route, so construct the full cross-model inventory required by the validator.
    chosen=pd.concat(frames,ignore_index=True)
    full=[]
    for category in POLICY:
        base=chosen.loc[chosen.category.eq(category)]
        for model in set(POLICY.values()):full.append(base.assign(model=model))
    data=pd.concat(full,ignore_index=True)
    result=historical_error_ranges(data)
    assert result.radius.eq(20).all()
    assert result.forecast_cases.eq(24).all()
    assert result.unique_target_months.eq(13).all()
    with pytest.raises(ValueError):historical_error_ranges(data.loc[~data.category.eq('Indie')])


def test_diagnostic_evidence_edit_or_inventory_change_rejected(tmp_path):
    import hashlib
    from src.project_fixed_cohort import verify_diagnostic_evidence
    file=tmp_path/"evidence.csv";file.write_text("original")
    pins={file.name:hashlib.sha256(file.read_bytes()).hexdigest()}
    verify_diagnostic_evidence(tmp_path,pins)
    file.write_text("edited")
    with pytest.raises(ValueError,match="evidence changed"):verify_diagnostic_evidence(tmp_path,pins)
    with pytest.raises(ValueError,match="inventory changed"):verify_diagnostic_evidence(tmp_path,{})

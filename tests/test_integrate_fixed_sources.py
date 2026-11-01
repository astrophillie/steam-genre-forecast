import pandas as pd
import pytest
from src.integrate_fixed_sources import canonicalise,choose_cohort

def test_priority_preserves_measurement_and_conflicts_reject():
    frame=pd.DataFrame({"app_id":[1,1],"month":["2026-01-01"]*2,"avg_players":[10.,10.01],"source_id":[1,2],"priority":[1,2]})
    selected=canonicalise(frame)
    assert len(selected)==1 and selected.avg_players.iloc[0]==10 and selected.source_id.iloc[0]==1
    frame.loc[1,"avg_players"]=11.
    with pytest.raises(ValueError,match="Conflicting"):canonicalise(frame)

def test_duplicate_source_keys_rejected():
    row=pd.DataFrame({"app_id":[1],"month":["2026-01-01"],"avg_players":[10.],"source_id":[1],"priority":[1]})
    with pytest.raises(ValueError,match="Repeated"):canonicalise(pd.concat([row,row]))

def test_cohort_requires_observed_months_and_eligible_category():
    months=pd.date_range("2021-02-01","2026-01-01",freq="MS").strftime("%Y-%m-%d")
    records=pd.concat([pd.DataFrame({"app_id":i,"month":months,"avg_players":0.}) for i in [1,2,3,4]],ignore_index=True)
    records=records.loc[~(records.app_id.eq(2)&records.month.eq("2023-01-01"))]
    games=pd.DataFrame({"app_id":[1,2,3,4],"eligible":[1,1,0,1]})
    labels=pd.DataFrame({"app_id":[1,2,3,4],"genre":["Action","Action","Action","Utilities"]})
    audit,panel=choose_cohort(records,games,labels)
    assert panel.app_id.unique().tolist()==[1]
    assert panel.avg_players.eq(0).all() and len(panel)==60
    assert audit.set_index("app_id").loc[2,"observed_window_months"]==59

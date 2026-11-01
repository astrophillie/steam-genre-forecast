import numpy as np
import pandas as pd
import pytest
from src.model_diagnostics import activity_flags,diagnose

def monthly():
    return pd.DataFrame({"category":"Example","month":pd.date_range("2018-01-01",periods=40,freq="MS").strftime("%Y-%m-%d"),"avg_players":100+np.arange(40,dtype=float),"coverage_rate":1.,"observed_apps":10})

def test_later_activity_cannot_change_earlier_flags():
    data=monthly();before=activity_flags(data)
    data.loc[35:,"avg_players"]*=10
    after=activity_flags(data)
    pd.testing.assert_series_equal(before.change_robust_z.iloc[:35],after.change_robust_z.iloc[:35])
    assert before.unusual_change.iloc[:13].isna().all()

def test_bias_direction_and_actual_reconciliation():
    data=monthly();last=data.iloc[-1]
    pred=pd.DataFrame({"category":["Example"],"origin":["2020-01-01"],"month":[last.month],"lead":[16],"model":["Last value"],"actual":[last.avg_players],"prediction":[last.avg_players-5],"error":[5.]})
    _,bias,_,_,_=diagnose(pred,data)
    assert bias.iloc[0].mean_error==5 and bias.iloc[0].underprediction_pct==100
    pred.loc[0,"error"]=-5
    with pytest.raises(ValueError,match="sign"):
        diagnose(pred,data)

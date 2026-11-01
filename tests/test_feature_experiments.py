import numpy as np
import pandas as pd
from src.feature_experiments import make_features,evaluate,GROUPS
from src.gradient_boosting import feature_row

def test_feature_values_are_past_only_and_reference_identical():
    history=np.arange(1.,13.)
    assert make_features(history,"2020-01-01","Reference")==feature_row(history,"2020-01-01")
    assert make_features(history,"2020-01-01","Recent changes")[-2:]==[1.,3.]
    assert make_features(history,"2020-01-01","Time trend")[-1]==12
    assert np.isclose(make_features(history,"2020-01-01","Rolling variability")[-2],np.std([10,11,12]))

def test_future_actuals_do_not_change_any_feature_experiment():
    dates=pd.date_range("2018-01-01",periods=60,freq="MS")
    data=pd.DataFrame({"category":"Example","month":dates,"avg_players":100+np.arange(60)+np.sin(np.arange(60))})
    before,_=evaluate(data,[dates[35]],12)
    data.loc[data.month.gt(dates[35]),"avg_players"]*=5
    after,_=evaluate(data,[dates[35]],12)
    np.testing.assert_allclose(before.prediction,after.prediction)
    assert before.groupby("model").size().eq(12).all()
    assert set(before.model)==set(GROUPS)

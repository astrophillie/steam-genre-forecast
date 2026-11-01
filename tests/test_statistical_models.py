import numpy as np
import pandas as pd
import pytest
from src.statistical_models import evaluate,forecast_statistical,CONFIGS

def series():
    return pd.Series(100+np.arange(60)*.5+4*np.sin(np.arange(60)*2*np.pi/12),index=pd.date_range("2018-01-01",periods=60,freq="MS"))

def test_predictions_are_frozen_against_future_actual_changes():
    s=series()
    data=pd.DataFrame({"category":"Test","month":s.index,"avg_players":s.to_numpy()})
    origin=s.index[35]
    first,_=evaluate(data,[origin],12)
    data.loc[data.month.gt(origin),"avg_players"]*=10
    second,_=evaluate(data,[origin],12)
    np.testing.assert_allclose(first.prediction,second.prediction)
    assert not np.allclose(first.actual,second.actual)
    assert first.groupby("model").size().eq(12).all()

def test_finite_nonnegative_forecasts_and_fit_diagnostics():
    for model in CONFIGS:
        forecast,info=forecast_statistical(series(),27,model)
        assert len(forecast)==27 and np.isfinite(forecast).all() and (forecast>=0).all()
        assert info["converged"]

def test_invalid_horizon_and_short_history_rejected():
    with pytest.raises(ValueError,match="integer"):
        forecast_statistical(series(),True,"SES")
    with pytest.raises(ValueError,match="24"):
        forecast_statistical(series().iloc[:12],2,"SES")
